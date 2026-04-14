"""GUI 中央模型与结果视口宿主。"""

from __future__ import annotations

import inspect
import math
import os
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from pyfem.gui.results_display import (
    DISPLAY_MODE_AUTO,
    DISPLAY_MODE_CONTOUR_DEFORMED,
    DISPLAY_MODE_DEFORMED,
    DISPLAY_MODE_UNDEFORMED,
    build_component_choices,
    extract_component_scalar,
    extract_vector_value,
    infer_unit_label,
    resolve_display_field_choice,
)
from pyfem.gui.shell import GuiMeshGeometry, GuiResultsEntry, GuiResultsViewContext
from pyfem.gui.theme import build_pill_stylesheet
from pyfem.io import FIELD_KEY_MODE_SHAPE, FIELD_KEY_U, POSITION_ELEMENT_CENTROID, POSITION_ELEMENT_NODAL, POSITION_INTEGRATION_POINT, POSITION_NODE, POSITION_NODE_AVERAGED
from pyfem.post.common import FIELD_METADATA_KEY_BASE_TARGET_KEYS

os.environ.setdefault("QT_API", "pyside6")

pyvista = None
QtInteractor = None
_PYVISTA_IMPORT_ERROR: Exception | None = None
_PYVISTA_IMPORT_ATTEMPTED = False


def _resolve_qt_interactor_binding_error(interactor_class: type[object]) -> RuntimeError | None:
    """校验 QtInteractor 是否绑定到 PySide6，避免混用 Qt 绑定导致原生崩溃。"""

    for base_class in interactor_class.mro():
        module_name = getattr(base_class, "__module__", "")
        if module_name.startswith("PySide6.QtWidgets"):
            return None
        if module_name.startswith(("PyQt5.QtWidgets", "PyQt6.QtWidgets", "PySide2.QtWidgets")):
            return RuntimeError(
                f"pyvistaqt 当前绑定到 {module_name}，与 GUI 主程序使用的 PySide6 不一致，已禁用 3D 预览。"
            )
    return RuntimeError("无法识别 pyvistaqt 的 Qt 绑定来源，已禁用 3D 预览。")


def _load_pyvista_backend() -> tuple[object | None, type[object] | None, Exception | None]:
    """按需加载 PyVista / pyvistaqt，避免普通 GUI 路径提前触发 VTK 原生依赖。"""

    global pyvista, QtInteractor, _PYVISTA_IMPORT_ERROR, _PYVISTA_IMPORT_ATTEMPTED
    if _PYVISTA_IMPORT_ATTEMPTED:
        return pyvista, QtInteractor, _PYVISTA_IMPORT_ERROR
    _PYVISTA_IMPORT_ATTEMPTED = True
    try:
        import pyvista as imported_pyvista
        from pyvistaqt import QtInteractor as imported_qt_interactor
    except Exception as error:  # pragma: no cover
        _PYVISTA_IMPORT_ERROR = error
        return None, None, error
    binding_error = _resolve_qt_interactor_binding_error(imported_qt_interactor)
    if binding_error is not None:
        _PYVISTA_IMPORT_ERROR = binding_error
        return None, None, binding_error
    pyvista = imported_pyvista
    QtInteractor = imported_qt_interactor
    _PYVISTA_IMPORT_ERROR = None
    return pyvista, QtInteractor, None


COLORMAP_OPTIONS: tuple[tuple[str, str, str], ...] = (
    ("rainbow", "Rainbow", "jet"),
    ("viridis", "Viridis", "viridis"),
    ("plasma", "Plasma", "plasma"),
    ("cool_to_warm", "Cool to Warm", "coolwarm"),
    ("grayscale", "Grayscale", "gray"),
)
COLORMAP_PLOT_KEYS: dict[str, str] = {name: plot_key for name, _label, plot_key in COLORMAP_OPTIONS}
COLORMAP_LABELS: dict[str, str] = {name: label for name, label, _plot_key in COLORMAP_OPTIONS}


def _should_use_offscreen_pyvista() -> bool:
    platform_name = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
    if platform_name in {"offscreen", "minimal", "minimalegl"}:
        return True
    return os.environ.get("PYFEM_PYVISTA_OFFSCREEN", "").strip().lower() in {"1", "true", "yes", "on"}


def _should_auto_initialize_preview() -> bool:
    """仅在正常桌面会话中自动初始化 3D 预览。"""

    return not _should_use_offscreen_pyvista()


class ResultsViewportHost(QWidget):
    """定义 GUI 中央舞台的结果视口宿主。"""

    componentChanged = Signal(object)

    def __init__(self, parent: QWidget | None = None, *, enable_pyvista_preview: bool = True) -> None:
        super().__init__(parent)
        self._enable_pyvista_preview = enable_pyvista_preview
        self._pyvista_widget: QWidget | None = None
        self._preview_requested = False
        self._model_geometry: GuiMeshGeometry | None = None
        self._view_context: GuiResultsViewContext | None = None
        self._current_step_name: str | None = None
        self._current_frame_id: int | None = None
        self._current_field_name: str | None = None
        self._current_component_name: str | None = None
        self._display_mode = DISPLAY_MODE_AUTO
        self._legend_locked = False
        self._legend_min: float | None = None
        self._legend_max: float | None = None
        self._colormap_name = "rainbow"
        self._auto_min: float | None = None
        self._auto_max: float | None = None
        self._workspace_module_name = "Part"
        self._workspace_object_hint = "No object"
        self._workspace_display_hint = "Mesh"
        self._build_ui()
        self._update_context_labels()
        self._sync_component_choices()
        self._set_controls_enabled(False)

    @property
    def pyvista_available(self) -> bool:
        loaded_pyvista, loaded_interactor, _error = _load_pyvista_backend()
        return loaded_pyvista is not None and loaded_interactor is not None

    @property
    def current_step_name(self) -> str | None:
        return self._current_step_name

    @property
    def current_frame_id(self) -> int | None:
        return self._current_frame_id

    @property
    def current_field_name(self) -> str | None:
        return self._current_field_name

    @property
    def current_component_name(self) -> str | None:
        return self._current_component_name

    @property
    def has_scene_geometry(self) -> bool:
        return self._model_geometry is not None

    def _assert_gui_thread(self) -> None:
        if QThread.currentThread() is not self.thread():
            raise RuntimeError("ResultsViewportHost 只能在 GUI 主线程更新。")

    def show_results_context(self, entries: tuple[GuiResultsEntry, ...]) -> None:
        self._assert_gui_thread()
        if not entries:
            self.clear_results_context("当前尚未打开结果。")
            return
        step_names = ", ".join(entry.step_name for entry in entries)
        self.show_placeholder(f"Results are ready for step={step_names}. The 3D viewport will display mesh, deformed shape and contour when preview is available.", title="Preview Pending")
        self._set_view_state("idle", "Results are ready for 3D preview.")

    def show_model_geometry(self, geometry: GuiMeshGeometry) -> None:
        self._assert_gui_thread()
        self._model_geometry = geometry
        self._view_context = None
        self._current_step_name = None
        self._current_frame_id = None
        self._current_field_name = None
        self._current_component_name = None
        self._display_mode = DISPLAY_MODE_UNDEFORMED
        self._update_context_labels()
        self._sync_component_choices()
        self._set_controls_enabled(True)
        self.refresh_view()

    def set_results_context(self, view_context: GuiResultsViewContext, *, preferred_step_name: str | None = None, preferred_frame_id: int | None = None, preferred_field_name: str | None = None) -> None:
        self._assert_gui_thread()
        self._model_geometry = view_context.mesh_geometry
        self._view_context = view_context
        self._set_controls_enabled(True)
        self.apply_selection(step_name=preferred_step_name, frame_id=preferred_frame_id, field_name=preferred_field_name)

    def apply_selection(self, *, step_name: str | None = None, frame_id: int | None = None, field_name: str | None = None) -> None:
        self._assert_gui_thread()
        if self._view_context is None:
            return
        step_names = self._view_context.results_facade.list_steps()
        self._current_step_name = step_name if step_name in step_names else (step_names[0] if step_names else None)
        frames = () if self._current_step_name is None else self._view_context.results_facade.frames(step_name=self._current_step_name)
        frame_ids = tuple(item.frame_id for item in frames)
        self._current_frame_id = frame_id if frame_id in frame_ids else (frame_ids[0] if frame_ids else None)
        fields = () if self._current_step_name is None or self._current_frame_id is None else self._view_context.results_facade.fields(step_name=self._current_step_name, frame_id=self._current_frame_id)
        field_names = tuple(item.field_name for item in fields)
        self._current_field_name = field_name if field_name in field_names else (field_names[0] if field_names else None)
        self._sync_component_choices()
        self._update_context_labels()
        self.refresh_view()
    def set_display_mode(self, display_mode: str | None) -> None:
        self._assert_gui_thread()
        self._display_mode = self._normalize_display_mode(display_mode)
        self.refresh_view()

    def set_component_name(self, component_name: str | None) -> None:
        self._assert_gui_thread()
        self._current_component_name = component_name
        self._sync_component_choices()
        self.refresh_view()
        self.componentChanged.emit(self._current_component_name)

    def clear_results_context(self, message: str | None = None) -> None:
        self._assert_gui_thread()
        self._model_geometry = None
        self._view_context = None
        self._current_step_name = None
        self._current_frame_id = None
        self._current_field_name = None
        self._current_component_name = None
        self._set_controls_enabled(False)
        self._sync_component_choices()
        self._update_context_labels()
        self.show_placeholder(message or "No model or results are currently bound to the viewport.", title="Viewport")
        self._set_view_state("idle", message or "Viewport is idle.")

    def show_placeholder(self, message: str, *, title: str | None = None) -> None:
        self.placeholder_title_label.setText(title or "Viewport")
        self.placeholder_label.setText(message)
        self._stack_layout.setCurrentWidget(self._placeholder_frame)

    def show_transient_status(self, message: str, *, title: str | None = None, state: str = "running") -> None:
        self.placeholder_title_label.setText(title or self.placeholder_title_label.text())
        self.placeholder_label.setText(message)
        if self._model_geometry is not None and self._pyvista_widget is not None:
            self._stack_layout.setCurrentWidget(self._pyvista_widget)
        else:
            self._stack_layout.setCurrentWidget(self._placeholder_frame)
        self._set_view_state(state, message)

    def ensure_pyvista_preview(self) -> bool:
        self._assert_gui_thread()
        self._preview_requested = True
        if self._pyvista_widget is not None:
            self._stack_layout.setCurrentWidget(self._pyvista_widget)
            self.refresh_view()
            return True
        if not self._enable_pyvista_preview:
            self.show_placeholder("PyVista preview remains disabled for this session. The reserved 3D widget stays in placeholder mode.", title="Preview Reserved")
            self._set_view_state("idle", "Placeholder mode is active. The reserved 3D widget is not created in this session.")
            return False
        loaded_pyvista, loaded_interactor, import_error = _load_pyvista_backend()
        if loaded_pyvista is None or loaded_interactor is None:
            self.show_placeholder("PyVista / pyvistaqt is unavailable, so the reserved 3D stage stays as a placeholder.", title="Preview Unavailable")
            self._set_view_state("failed", f"Preview dependencies are unavailable: {import_error}")
            return False
        try:
            self._pyvista_widget = self._build_pyvista_widget()
        except Exception as error:  # pragma: no cover
            self.show_placeholder("The reserved 3D stage could not be initialized, so the viewport stays in placeholder mode.", title="Preview Init Failed")
            self._set_view_state("failed", f"Preview initialization failed: {error}")
            return False
        self._stack_layout.addWidget(self._pyvista_widget)
        self._stack_layout.setCurrentWidget(self._pyvista_widget)
        self.refresh_view()
        return True

    def refresh_view(self) -> None:
        self._assert_gui_thread()
        if self._model_geometry is None:
            self.show_placeholder("Model mesh, contour and 3D interaction will appear here.", title="Viewport")
            self._set_view_state("idle", "Viewport is waiting for model or results.")
            return
        if self._view_context is None:
            if self._pyvista_widget is None:
                if self._enable_pyvista_preview and _should_auto_initialize_preview():
                    if not self.ensure_pyvista_preview():
                        return
                elif self._enable_pyvista_preview:
                    self.show_placeholder(
                        f"Model {self._model_geometry.model_name} loaded. 3D preview will auto-initialize only in a normal desktop session; placeholder mode is active in the current environment.",
                        title="Model Loaded",
                    )
                    self._set_view_state("idle", "Model geometry is ready. Current environment keeps 3D preview in safe placeholder mode.")
                    return
                else:
                    self.show_placeholder(
                        f"Model {self._model_geometry.model_name} loaded. 3D preview is disabled for this session, so placeholder mode remains active.",
                        title="Model Loaded",
                    )
                    self._set_view_state("idle", "Model geometry is ready. 3D preview is disabled for this session.")
                    return
            self._render_model_geometry()
            return
        if self._current_step_name is None or self._current_frame_id is None:
            self.show_placeholder("Results are loaded, but the current step or frame is not selected yet.", title="Preview Pending")
            self._set_view_state("idle", "Select a step and frame to continue browsing results.")
            return
        if self._pyvista_widget is None:
            if self._enable_pyvista_preview and _should_auto_initialize_preview():
                if not self.ensure_pyvista_preview():
                    self._update_placeholder_legend()
                    return
            elif self._enable_pyvista_preview:
                self._update_placeholder_legend()
                field_hint = self._current_field_name or "mesh"
                self.show_placeholder(
                    f"Preview data is ready: step={self._current_step_name}, frame={self._current_frame_id}, field={field_hint}. 3D preview auto-initialization is skipped in the current environment.",
                    title="Preview Pending",
                )
                self._set_view_state("idle", "Results are ready. Current environment keeps 3D preview in safe placeholder mode.")
                return
            self._update_placeholder_legend()
            field_hint = self._current_field_name or "mesh"
            self.show_placeholder(
                f"Preview data is ready: step={self._current_step_name}, frame={self._current_frame_id}, field={field_hint}. 3D preview is disabled for this session.",
                title="Preview Pending",
            )
            self._set_view_state("idle", "Results are ready. 3D preview is disabled for this session.")
            return
        self._render_current_selection()

    def reset_view(self) -> None:
        self._assert_gui_thread()
        if self._pyvista_widget is not None and hasattr(self._pyvista_widget, "reset_camera"):
            self._pyvista_widget.reset_camera()
            if hasattr(self._pyvista_widget, "render"):
                self._pyvista_widget.render()
            self._set_view_state("success", "Viewport camera has been reset.")
            return
        self.refresh_view()

    def shutdown(self) -> None:
        """显式释放 viewport 内部持有的 PyVista / VTK 资源。"""

        self._shutdown_pyvista_widget()

    def closeEvent(self, event) -> None:
        """在宿主关闭前先收拢底层 3D 预览控件。"""

        self.shutdown()
        super().closeEvent(event)

    def set_workspace_context(self, module_name: str, object_text: str, display_text: str) -> None:
        self._workspace_module_name = module_name
        self._workspace_object_hint = object_text
        self._workspace_display_hint = display_text
        self._update_context_labels()

    def add_strip_widget(self, widget: QWidget) -> None:
        self._strip_tools_layout.addWidget(widget)

    def show_command_prompt(self, message: str) -> None:
        """显示仅在临时命令模式下出现的提示条。"""

        self.command_prompt_label.setText(message)
        self.command_prompt_frame.show()

    def hide_command_prompt(self) -> None:
        """隐藏临时命令提示条。"""

        self.command_prompt_frame.hide()

    def set_legend_controls(
        self,
        *,
        locked: bool,
        min_value: float | None,
        max_value: float | None,
        colormap_name: str | None = None,
    ) -> None:
        """由外部对话框同步 legend 高级参数。"""

        self.legend_lock_checkbox.setChecked(locked)
        self.legend_min_edit.setText("" if min_value is None else f"{min_value:.6g}")
        self.legend_max_edit.setText("" if max_value is None else f"{max_value:.6g}")
        if colormap_name is not None:
            self._colormap_name = self._normalize_colormap_name(colormap_name)
        self._apply_legend_controls()

    def legend_settings(self) -> tuple[bool, float | None, float | None, str]:
        """返回当前 legend 设置。"""

        return self._legend_locked, self._legend_min, self._legend_max, self._colormap_name

    def legend_summary(self) -> tuple[str, str]:
        """返回当前 legend 摘要文本。"""

        return self.legend_unit_label.text(), self.legend_range_label.text()

    def legend_colormap_options(self) -> tuple[tuple[str, str], ...]:
        """返回 legend 可选 colormap 列表。"""

        return tuple((name, label) for name, label, _plot_key in COLORMAP_OPTIONS)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.command_prompt_frame = QFrame(self)
        self.command_prompt_frame.setObjectName("ViewportPromptStrip")
        prompt_layout = QHBoxLayout(self.command_prompt_frame)
        prompt_layout.setContentsMargins(8, 4, 8, 4)
        prompt_layout.setSpacing(6)
        prompt_title_label = QLabel("Command", self.command_prompt_frame)
        prompt_title_label.setObjectName("PromptModuleLabel")
        self.command_prompt_label = QLabel("", self.command_prompt_frame)
        self.command_prompt_label.setWordWrap(True)
        prompt_layout.addWidget(prompt_title_label)
        prompt_layout.addWidget(self.command_prompt_label, 1)
        self.command_prompt_frame.hide()

        context_bar = QFrame(self)
        context_layout = QHBoxLayout(context_bar)
        self._strip_tools_layout = QHBoxLayout()
        self.view_state_badge = QLabel("Ready", self)
        self.context_value_label = QLabel("Part | No object", self)
        self.context_value_label.setStyleSheet(build_pill_stylesheet(foreground_color="#27425c", background_color="#eef3f6", border_color="#c3ccd5", font_size=11, padding="2px 8px"))
        self.status_label = QLabel("Load a model or results to inspect the viewport state.", self)
        self.legend_unit_label = QLabel("unit=-", self)
        self.legend_range_label = QLabel("range=-", self)
        self.legend_button = QPushButton("Legend...", self)
        self.preview_button = QPushButton("Preview", self)
        self.refresh_button = QPushButton("Refresh", self)
        context_layout.addWidget(self.view_state_badge)
        context_layout.addWidget(self.context_value_label)
        context_layout.addWidget(self.status_label, 1)
        context_layout.addLayout(self._strip_tools_layout)
        context_layout.addWidget(self.legend_unit_label)
        context_layout.addWidget(self.legend_range_label)
        context_layout.addWidget(self.legend_button)
        context_layout.addWidget(self.preview_button)
        context_layout.addWidget(self.refresh_button)

        self.component_combo = QComboBox(self)
        self.component_combo.hide()
        self.legend_lock_checkbox = QCheckBox("Lock Range", self)
        self.legend_lock_checkbox.hide()
        self.legend_min_edit = QLineEdit(self)
        self.legend_min_edit.setPlaceholderText("min")
        self.legend_min_edit.hide()
        self.legend_max_edit = QLineEdit(self)
        self.legend_max_edit.setPlaceholderText("max")
        self.legend_max_edit.hide()
        self.legend_apply_button = QPushButton("Apply", self)
        self.legend_apply_button.hide()

        self._placeholder_frame = QFrame(self)
        placeholder_layout = QVBoxLayout(self._placeholder_frame)
        self.placeholder_title_label = QLabel("Viewport", self)
        self.placeholder_label = QLabel("Model mesh, contour and interactive 3D view will appear here.", self)
        self.placeholder_label.setWordWrap(True)
        placeholder_layout.addWidget(self.placeholder_title_label)
        placeholder_layout.addWidget(self.placeholder_label)
        placeholder_layout.addStretch(1)
        self._stack_layout = QStackedLayout()
        self._stack_layout.addWidget(self._placeholder_frame)
        body = QWidget(self)
        body.setLayout(self._stack_layout)

        layout.addWidget(self.command_prompt_frame)
        layout.addWidget(context_bar)
        layout.addWidget(body, 1)

        self.preview_button.clicked.connect(self.ensure_pyvista_preview)
        self.refresh_button.clicked.connect(self.refresh_view)
        self.component_combo.currentIndexChanged.connect(self._on_component_combo_changed)
        self.legend_apply_button.clicked.connect(self._apply_legend_controls)
        self.legend_lock_checkbox.toggled.connect(self._apply_legend_controls)

    def _update_context_labels(self) -> None:
        if self._view_context is None and self._model_geometry is not None:
            self.context_value_label.setText(f"Model {self._model_geometry.model_name} | Mesh")
            return
        if self._current_step_name is None:
            self.context_value_label.setText(f"{self._workspace_module_name} | {self._workspace_object_hint}")
            return
        frame_text = self._current_frame_id if self._current_frame_id is not None else "-"
        field_text = self._current_field_name or "Mesh"
        component_text = self._current_component_name or "-"
        self.context_value_label.setText(f"{self._workspace_module_name} | {field_text}")
        self.context_value_label.setToolTip(
            f"{self._workspace_module_name} | Step {self._current_step_name} | Frame {frame_text} | Field {field_text} | Component {component_text} | {self._workspace_display_hint}"
        )

    def _set_view_state(self, state: str, message: str) -> None:
        styles = {"idle": ("Idle", "#31527d", "#eef5ff", "#cadef8"), "success": ("Ready", "#1e6f43", "#e8f8ee", "#b7e3c9"), "failed": ("Failed", "#9e2330", "#fdecee", "#f4bac0"), "running": ("Working", "#8a4b00", "#fff6dc", "#f0d79c")}
        label, fg, bg, border = styles[state]
        self.view_state_badge.setText(label)
        self.view_state_badge.setStyleSheet(build_pill_stylesheet(foreground_color=fg, background_color=bg, border_color=border))
        self.status_label.setText(message)
        self.status_label.setToolTip(message)

    def _sync_component_choices(self) -> None:
        self.component_combo.blockSignals(True)
        self.component_combo.clear()
        choices: tuple[str, ...] = ()
        if self._view_context is not None and self._current_step_name is not None and self._current_frame_id is not None and self._current_field_name is not None:
            choices = build_component_choices(self._view_context.results_facade, self._current_step_name, self._current_frame_id, self._current_field_name)
        for choice in choices:
            self.component_combo.addItem(choice, choice)
        if self._current_component_name in choices:
            index = self.component_combo.findData(self._current_component_name)
            self.component_combo.setCurrentIndex(index)
        elif choices:
            self._current_component_name = choices[0]
            self.component_combo.setCurrentIndex(0)
        else:
            self._current_component_name = None
        self.component_combo.blockSignals(False)

    def _on_component_combo_changed(self) -> None:
        component_name = self.component_combo.currentData()
        self._current_component_name = component_name if isinstance(component_name, str) else None
        self.refresh_view()
        self.componentChanged.emit(self._current_component_name)

    def _apply_legend_controls(self) -> None:
        self._legend_locked = self.legend_lock_checkbox.isChecked()
        self._legend_min = self._parse_optional_float(self.legend_min_edit.text())
        self._legend_max = self._parse_optional_float(self.legend_max_edit.text())
        self.refresh_view()

    def _normalize_colormap_name(self, colormap_name: str | None) -> str:
        raw_name = "rainbow" if colormap_name is None else str(colormap_name).strip().lower()
        return raw_name if raw_name in COLORMAP_PLOT_KEYS else "rainbow"

    def _parse_optional_float(self, text: str) -> float | None:
        stripped = text.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None

    def _normalize_display_mode(self, display_mode: str | None) -> str:
        raw_mode = DISPLAY_MODE_AUTO if display_mode is None else str(display_mode)
        mapping = {"mesh": DISPLAY_MODE_UNDEFORMED, "scalar": DISPLAY_MODE_CONTOUR_DEFORMED, DISPLAY_MODE_AUTO: DISPLAY_MODE_AUTO, DISPLAY_MODE_UNDEFORMED: DISPLAY_MODE_UNDEFORMED, DISPLAY_MODE_DEFORMED: DISPLAY_MODE_DEFORMED, DISPLAY_MODE_CONTOUR_DEFORMED: DISPLAY_MODE_CONTOUR_DEFORMED}
        return mapping.get(raw_mode, DISPLAY_MODE_AUTO)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.preview_button.setEnabled(enabled)
        self.refresh_button.setEnabled(enabled)
        self.legend_button.setEnabled(enabled)
        self.component_combo.setEnabled(enabled and self.component_combo.count() > 0)
        self.legend_lock_checkbox.setEnabled(enabled)
        self.legend_min_edit.setEnabled(enabled)
        self.legend_max_edit.setEnabled(enabled)
        self.legend_apply_button.setEnabled(enabled)

    def _build_pyvista_widget(self) -> QWidget:
        loaded_pyvista, loaded_interactor, _error = _load_pyvista_backend()
        if loaded_interactor is None or loaded_pyvista is None:  # pragma: no cover
            raise RuntimeError("PyVista preview dependencies are unavailable.")
        kwargs: dict[str, object] = {}
        try:
            signature = inspect.signature(loaded_interactor)
        except (TypeError, ValueError):  # pragma: no cover
            signature = None
        if signature is not None and "off_screen" in signature.parameters and _should_use_offscreen_pyvista():
            kwargs["off_screen"] = True
        widget = loaded_interactor(self, **kwargs)
        widget.set_background("#dce4ec")
        widget.add_axes()
        return widget

    def _shutdown_pyvista_widget(self) -> None:
        """显式关闭 QtInteractor，避免退出阶段残留 VTK 资源。"""

        widget = self._pyvista_widget
        if widget is None:
            return
        self._pyvista_widget = None
        try:
            self._stack_layout.setCurrentWidget(self._placeholder_frame)
        except Exception:
            pass
        try:
            self._stack_layout.removeWidget(widget)
        except Exception:
            pass
        try:
            if hasattr(widget, "close"):
                widget.close()
        except Exception:
            pass
        try:
            widget.setParent(None)
        except Exception:
            pass
        try:
            widget.deleteLater()
        except Exception:
            pass

    def _build_unstructured_grid(self, geometry: GuiMeshGeometry) -> Any:
        loaded_pyvista, _loaded_interactor, _error = _load_pyvista_backend()
        if loaded_pyvista is None:  # pragma: no cover
            raise RuntimeError("PyVista preview dependencies are unavailable.")
        import numpy as np
        vtk_cells: list[int] = []
        for cell in geometry.cell_connectivities:
            vtk_cells.append(len(cell))
            vtk_cells.extend(int(index) for index in cell)
        return loaded_pyvista.UnstructuredGrid(
            np.array(vtk_cells, dtype=np.int64),
            np.array(geometry.vtk_cell_types, dtype=np.uint8),
            np.array(geometry.points, dtype=float),
        )

    def _render_model_geometry(self) -> None:
        plotter = self._pyvista_widget
        if plotter is None or self._model_geometry is None:
            return
        grid = self._build_unstructured_grid(self._model_geometry)
        plotter.clear()
        plotter.add_mesh(grid, color="lightgray", show_edges=True, opacity=0.92)
        plotter.add_text(f"{self._model_geometry.model_name} | mesh", position="upper_left", font_size=11)
        if hasattr(plotter, "reset_camera"):
            plotter.reset_camera()
        if hasattr(plotter, "render"):
            plotter.render()
        self._set_view_state("success", f"Mesh scene ready: model={self._model_geometry.model_name}")

    def _update_placeholder_legend(self) -> None:
        if self._view_context is None or self._current_step_name is None or self._current_frame_id is None or self._current_field_name is None:
            self._update_legend(None, None, unit_label='-')
            return
        try:
            choice = resolve_display_field_choice(self._view_context.results_facade, self._current_step_name, self._current_frame_id, self._current_field_name, self._current_component_name)
        except Exception:
            self._update_legend(None, self._current_field_name, unit_label='-')
            return
        _association, scalar_values = self._build_scalar_payload(choice.field, choice.component_name)
        self._update_legend(scalar_values, choice.field_name, unit_label=choice.unit_label)

    def _render_current_selection(self) -> None:
        if self._pyvista_widget is None or self._view_context is None or self._current_step_name is None or self._current_frame_id is None or self._model_geometry is None:
            return
        plotter = self._pyvista_widget
        geometry = self._model_geometry
        grid = self._build_unstructured_grid(geometry)
        mode = self._display_mode
        if mode == DISPLAY_MODE_AUTO:
            mode = DISPLAY_MODE_CONTOUR_DEFORMED if self._current_field_name is not None else DISPLAY_MODE_UNDEFORMED
        deformation_vectors = self._build_deformation_vectors() if mode in {DISPLAY_MODE_DEFORMED, DISPLAY_MODE_CONTOUR_DEFORMED} else None
        if deformation_vectors is not None and hasattr(grid, "points"):
            try:
                import numpy as np
                grid.points = np.array([[point[0] + vector[0], point[1] + vector[1], point[2] + vector[2]] for point, vector in zip(geometry.points, deformation_vectors, strict=True)], dtype=float)
            except Exception:
                pass
        plotter.clear()
        if mode in {DISPLAY_MODE_UNDEFORMED, DISPLAY_MODE_DEFORMED} or self._current_field_name is None:
            plotter.add_mesh(grid, color="lightgray", show_edges=True, opacity=0.92)
            plotter.add_text(f"{self._current_step_name} | frame={self._current_frame_id} | shape={mode}", position="upper_left", font_size=11)
            if hasattr(plotter, "reset_camera"):
                plotter.reset_camera()
            if hasattr(plotter, "render"):
                plotter.render()
            self._update_legend(None, None, unit_label="-")
            self._set_view_state("success", f"Displayed {mode}: step={self._current_step_name}, frame={self._current_frame_id}, field={self._current_field_name or 'mesh'}")
            return
        choice = resolve_display_field_choice(self._view_context.results_facade, self._current_step_name, self._current_frame_id, self._current_field_name, self._current_component_name)
        association, scalar_values = self._build_scalar_payload(choice.field, choice.component_name)
        scalar_name = choice.field_name if not choice.component_name else f"{choice.field_name}_{choice.component_name}"
        if association == "point" and hasattr(grid, "point_data"):
            grid.point_data[scalar_name] = scalar_values
        elif association == "cell" and hasattr(grid, "cell_data"):
            grid.cell_data[scalar_name] = scalar_values
        plot_kwargs = {"scalars": scalar_name, "show_edges": True, "cmap": COLORMAP_PLOT_KEYS[self._colormap_name]}
        if self._legend_locked and self._legend_min is not None and self._legend_max is not None:
            plot_kwargs["clim"] = [self._legend_min, self._legend_max]
        plotter.add_mesh(grid, **plot_kwargs)
        plotter.add_text(f"{self._current_step_name} | frame={self._current_frame_id} | field={choice.label}", position="upper_left", font_size=11)
        if hasattr(plotter, "reset_camera"):
            plotter.reset_camera()
        if hasattr(plotter, "render"):
            plotter.render()
        self._update_legend(scalar_values, choice.field_name, unit_label=choice.unit_label)
        self._set_view_state("success", f"Displayed contour: step={self._current_step_name}, frame={self._current_frame_id}, field={choice.label}")

    def _build_deformation_vectors(self) -> list[tuple[float, float, float]] | None:
        if self._view_context is None or self._current_step_name is None or self._current_frame_id is None or self._model_geometry is None:
            return None
        facade = self._view_context.results_facade
        field_names = {item.field_name for item in facade.fields(step_name=self._current_step_name, frame_id=self._current_frame_id)}
        deformation_field_name = FIELD_KEY_U if FIELD_KEY_U in field_names else (FIELD_KEY_MODE_SHAPE if FIELD_KEY_MODE_SHAPE in field_names else None)
        if deformation_field_name is None:
            return None
        field = facade.field(self._current_step_name, self._current_frame_id, deformation_field_name)
        return [extract_vector_value(field.values.get(node_key)) for node_key in self._model_geometry.point_keys]

    def _build_scalar_payload(self, field: Any, component_name: str) -> tuple[str, list[float]]:
        geometry = self._model_geometry
        if geometry is None:
            return "point", []
        if field.position == POSITION_NODE:
            return "point", [self._safe_scalar(field.values.get(node_key), component_name, field.component_names) for node_key in geometry.point_keys]
        if field.position == POSITION_NODE_AVERAGED:
            base_map = {str(key): str(value) for key, value in dict(field.metadata).get(FIELD_METADATA_KEY_BASE_TARGET_KEYS, {}).items()}
            grouped: dict[str, list[float]] = defaultdict(list)
            for target_key, value in field.values.items():
                grouped[base_map.get(str(target_key), str(target_key))].append(
                    self._safe_scalar(value, component_name, field.component_names)
                )
            return "point", [self._average(grouped.get(node_key, [])) for node_key in geometry.point_keys]
        if field.position == POSITION_ELEMENT_CENTROID:
            return "cell", [self._safe_scalar(field.values.get(cell_key), component_name, field.component_names) for cell_key in geometry.cell_keys]
        grouped_values: dict[str, list[float]] = defaultdict(list)
        for target_key, value in field.values.items():
            grouped_values[self._owner_key(str(target_key))].append(
                self._safe_scalar(value, component_name, field.component_names)
            )
        return "cell", [self._average(grouped_values.get(cell_key, [])) for cell_key in geometry.cell_keys]

    def _owner_key(self, target_key: str) -> str:
        upper_key = target_key.upper()
        for marker in (".IP", ".N", "@"):
            index = upper_key.find(marker)
            if index > 0:
                return target_key[:index]
        return target_key

    def _safe_scalar(self, value: Any, component_name: str, component_names: tuple[str, ...]) -> float:
        scalar = extract_component_scalar(value, component_name, component_names)
        return 0.0 if math.isnan(scalar) else float(scalar)

    def _average(self, values: Sequence[float]) -> float:
        return 0.0 if not values else sum(values) / len(values)

    def _update_legend(self, scalar_values: Sequence[float] | None, field_name: str | None, *, unit_label: str) -> None:
        if not scalar_values:
            self._auto_min = None
            self._auto_max = None
            self.legend_unit_label.setText(f"unit={unit_label}")
            self.legend_range_label.setText(f"range=- | cmap={COLORMAP_LABELS[self._colormap_name]}")
            return
        self._auto_min = min(scalar_values)
        self._auto_max = max(scalar_values)
        shown_min = self._legend_min if self._legend_locked and self._legend_min is not None else self._auto_min
        shown_max = self._legend_max if self._legend_locked and self._legend_max is not None else self._auto_max
        self.legend_unit_label.setText(f"unit={unit_label or infer_unit_label(field_name or '-', {})}")
        if shown_min is None or shown_max is None:
            self.legend_range_label.setText(f"range=- | cmap={COLORMAP_LABELS[self._colormap_name]}")
        else:
            prefix = "locked" if self._legend_locked and self._legend_min is not None and self._legend_max is not None else "auto"
            self.legend_range_label.setText(f"{prefix}={shown_min:.6g} ~ {shown_max:.6g} | cmap={COLORMAP_LABELS[self._colormap_name]}")

