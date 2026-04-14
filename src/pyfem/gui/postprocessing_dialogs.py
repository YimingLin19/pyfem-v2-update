"""后处理工作台使用的轻量弹窗组件。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SelectionDetailsDialog(QDialog):
    """展示当前结果选择详情的通用文本弹窗。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Selection Details")
        self.resize(640, 420)
        self._build_ui()

    def set_content(self, *, title: str, text: str) -> None:
        """刷新弹窗标题与正文。"""

        self.setWindowTitle(title)
        self.title_label.setText(title)
        self.text_edit.setPlainText(text)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QFrame(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        self.title_label = QLabel("Selection Details", header)
        self.title_label.setObjectName("SectionTitle")
        close_button = QPushButton("Close", header)
        close_button.clicked.connect(self.close)

        header_layout.addWidget(self.title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(close_button)

        self.text_edit = QPlainTextEdit(self)
        self.text_edit.setReadOnly(True)

        layout.addWidget(header)
        layout.addWidget(self.text_edit, 1)


class LegendSettingsDialog(QDialog):
    """展示 legend 高级参数的小型弹窗。"""

    applyRequested = Signal(bool, object, object, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Legend Settings")
        self.resize(420, 240)
        self._build_ui()

    def set_values(
        self,
        *,
        locked: bool,
        min_value: float | None,
        max_value: float | None,
        unit_label: str,
        range_text: str,
        colormap_name: str,
        colormap_options: tuple[tuple[str, str], ...],
    ) -> None:
        """根据当前视口状态刷新弹窗控件。"""

        self.lock_checkbox.setChecked(locked)
        self.min_edit.setText("" if min_value is None else f"{min_value:.6g}")
        self.max_edit.setText("" if max_value is None else f"{max_value:.6g}")
        self.unit_value_label.setText(unit_label or "-")
        self.range_value_label.setText(range_text or "-")
        self.colormap_combo.blockSignals(True)
        self.colormap_combo.clear()
        for option_name, option_label in colormap_options:
            self.colormap_combo.addItem(option_label, option_name)
        index = self.colormap_combo.findData(colormap_name)
        if index >= 0:
            self.colormap_combo.setCurrentIndex(index)
        self.colormap_combo.blockSignals(False)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        summary_frame = QFrame(self)
        summary_layout = QFormLayout(summary_frame)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(6)
        self.unit_value_label = QLabel("-", summary_frame)
        self.range_value_label = QLabel("-", summary_frame)
        summary_layout.addRow("Unit", self.unit_value_label)
        summary_layout.addRow("Current Range", self.range_value_label)

        controls_frame = QFrame(self)
        controls_layout = QFormLayout(controls_frame)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)
        self.lock_checkbox = QCheckBox("Lock Range", controls_frame)
        self.colormap_combo = QComboBox(controls_frame)
        self.min_edit = QLineEdit(controls_frame)
        self.min_edit.setPlaceholderText("min")
        self.max_edit = QLineEdit(controls_frame)
        self.max_edit.setPlaceholderText("max")
        controls_layout.addRow("Mode", self.lock_checkbox)
        controls_layout.addRow("Colormap", self.colormap_combo)
        controls_layout.addRow("Minimum", self.min_edit)
        controls_layout.addRow("Maximum", self.max_edit)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(6)
        self.apply_button = QPushButton("Apply", self)
        close_button = QPushButton("Close", self)
        self.apply_button.clicked.connect(self._emit_apply_requested)
        close_button.clicked.connect(self.close)
        button_row.addStretch(1)
        button_row.addWidget(self.apply_button)
        button_row.addWidget(close_button)

        layout.addWidget(summary_frame)
        layout.addWidget(controls_frame)
        layout.addStretch(1)
        layout.addLayout(button_row)

    def _emit_apply_requested(self) -> None:
        self.applyRequested.emit(
            self.lock_checkbox.isChecked(),
            self._parse_optional_float(self.min_edit.text()),
            self._parse_optional_float(self.max_edit.text()),
            str(self.colormap_combo.currentData() or "viridis"),
        )

    def _parse_optional_float(self, text: str) -> float | None:
        stripped = text.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None


class ProbeDialog(QDialog):
    """承接 probe 设置与结果输出的小型弹窗。"""

    runRequested = Signal()
    exportRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Probe")
        self.resize(520, 420)
        self._build_ui()

    def set_context_summary(self, text: str) -> None:
        """刷新当前 probe 上下文说明。"""

        self.context_value_label.setText(text)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QFrame(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        title_label = QLabel("Probe", header)
        title_label.setObjectName("SectionTitle")
        self.context_value_label = QLabel("当前没有可用于 probe 的结果选择。", header)
        self.context_value_label.setWordWrap(True)
        header_layout.addWidget(title_label)
        header_layout.addWidget(self.context_value_label, 1)

        form_frame = QFrame(self)
        form_layout = QFormLayout(form_frame)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(6)

        self.probe_kind_combo = QComboBox(form_frame)
        self.probe_target_combo = QComboBox(form_frame)
        self.probe_target_combo.setEditable(True)
        self.probe_component_combo = QComboBox(form_frame)
        self.probe_status_value = QLabel("No probe target", form_frame)
        self.probe_status_value.setWordWrap(True)
        form_layout.addRow("Kind", self.probe_kind_combo)
        form_layout.addRow("Target", self.probe_target_combo)
        form_layout.addRow("Component", self.probe_component_combo)
        form_layout.addRow("State", self.probe_status_value)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(6)
        self.run_probe_button = QPushButton("Run Probe", self)
        self.export_probe_button = QPushButton("Export CSV", self)
        close_button = QPushButton("Close", self)
        self.run_probe_button.clicked.connect(self.runRequested.emit)
        self.export_probe_button.clicked.connect(self.exportRequested.emit)
        close_button.clicked.connect(self.close)
        button_row.addWidget(self.run_probe_button)
        button_row.addWidget(self.export_probe_button)
        button_row.addStretch(1)
        button_row.addWidget(close_button)

        self.probe_output_edit = QPlainTextEdit(self)
        self.probe_output_edit.setReadOnly(True)
        self.probe_output_edit.setPlaceholderText("Probe result details will appear here.")

        layout.addWidget(header)
        layout.addWidget(form_frame)
        layout.addLayout(button_row)
        layout.addWidget(self.probe_output_edit, 1)


class ExportOptionsDialog(QDialog):
    """承接导出路径与步骤选择的小型弹窗。"""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        title: str,
        path_label: str,
        path_filter: str,
    ) -> None:
        super().__init__(parent)
        self._path_filter = path_filter
        self.setWindowTitle(title)
        self.resize(520, 180)
        self._path_label = path_label
        self._build_ui()

    def set_values(
        self,
        *,
        step_names: tuple[str, ...],
        current_step_name: str | None,
        path_text: str,
        description: str,
    ) -> None:
        """刷新导出弹窗的默认上下文。"""

        self.description_label.setText(description)
        self.step_combo.blockSignals(True)
        self.step_combo.clear()
        self.step_combo.addItem("All Steps", None)
        for step_name in step_names:
            self.step_combo.addItem(step_name, step_name)
        if current_step_name is not None:
            index = self.step_combo.findData(current_step_name)
            if index >= 0:
                self.step_combo.setCurrentIndex(index)
        self.step_combo.blockSignals(False)
        self.path_edit.setText(path_text)

    def selected_step_name(self) -> str | None:
        """返回当前选择的步骤。"""

        data = self.step_combo.currentData()
        return data if isinstance(data, str) else None

    def selected_path(self) -> Path:
        """返回当前选择的导出路径。"""

        return Path(self.path_edit.text().strip())

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.description_label = QLabel("", self)
        self.description_label.setWordWrap(True)
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        form_frame = QFrame(self)
        form_layout = QFormLayout(form_frame)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(6)

        self.step_combo = QComboBox(form_frame)
        path_row = QWidget(form_frame)
        path_layout = QHBoxLayout(path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(6)
        self.path_edit = QLineEdit(path_row)
        browse_button = QPushButton("Browse", path_row)
        browse_button.clicked.connect(self._browse_path)
        path_layout.addWidget(self.path_edit, 1)
        path_layout.addWidget(browse_button)

        form_layout.addRow("Step", self.step_combo)
        form_layout.addRow(self._path_label, path_row)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(6)
        self.confirm_button = QPushButton("Export", self)
        close_button = QPushButton("Cancel", self)
        self.confirm_button.clicked.connect(self.accept)
        close_button.clicked.connect(self.reject)
        button_row.addStretch(1)
        button_row.addWidget(self.confirm_button)
        button_row.addWidget(close_button)

        layout.addWidget(self.description_label)
        layout.addWidget(form_frame)
        layout.addStretch(1)
        layout.addLayout(button_row)

    def _browse_path(self) -> None:
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            self.windowTitle(),
            self.path_edit.text().strip(),
            self._path_filter,
        )
        if selected_path:
            self.path_edit.setText(selected_path)
