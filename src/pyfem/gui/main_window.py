"""GUI 主窗口与结果消费接层。"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from PySide6.QtCore import QThread, Qt, Slot, QTimer
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStyle,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from pyfem.gui.gui_command_registry import GuiCommandRegistry
from pyfem.gui.job_dialogs import JobCenterDialog, JobDiagnosticsDialog, JobMonitorDialog
from pyfem.gui.job_records import (
    FAILED_JOB_STATUSES,
    RUNNING_JOB_STATUSES,
    GuiJobRecord,
    GuiJobRecordStore,
    JobDiagnosticsSnapshot,
    bucketize_job_messages,
    build_job_display_name,
    create_job_timestamp,
)
from pyfem.gui.load_manager_dialogs import BoundaryManagerDialog, LoadManagerDialog, StepManagerDialog
from pyfem.gui.message_console_panel import MessageConsolePanel
from pyfem.gui.model_edit_capabilities import collect_export_capability_issues, collect_run_capability_issues
from pyfem.gui.model_edit_dialogs import (
    BoundaryEditDialog,
    InstanceTransformDialog,
    LoadEditDialog,
    MaterialEditDialog,
    OutputRequestEditDialog,
    SectionEditDialog,
    StepEditDialog,
)
from pyfem.gui.model_edit_presenters import ModelEditPresenter
from pyfem.gui.module_toolbox import ModuleToolbox
from pyfem.gui.navigation_panel import WorkbenchNavigationPanel
from pyfem.gui.postprocessing_dialogs import ExportOptionsDialog, LegendSettingsDialog, ProbeDialog, SelectionDetailsDialog
from pyfem.gui.property_manager_dialogs import AssignSectionDialog, MaterialManagerDialog, SectionManagerDialog
from pyfem.gui.result_field_presentation import COMMON_VARIANT_KEY, FieldPresentationPolicy
from pyfem.gui.results_browser import ResultsBrowser
from pyfem.gui.results_display import (
    DISPLAY_MODE_CONTOUR_DEFORMED,
    DISPLAY_MODE_DEFORMED,
    DISPLAY_MODE_UNDEFORMED,
    PROBE_KIND_AVERAGED,
    PROBE_KIND_ELEMENT,
    PROBE_KIND_INTEGRATION_POINT,
    PROBE_KIND_NODE,
    build_component_choices,
    resolve_probe_compatibility,
)
from pyfem.gui.shell import GuiModelSummary, GuiResultsLoadResult, GuiResultsViewContext, GuiShell
from pyfem.gui.tasks import GuiTaskHandle, GuiTaskWorker
from pyfem.gui.theme import APP_DISPLAY_NAME, APP_WINDOW_TITLE, build_main_window_stylesheet, build_pill_stylesheet, resolve_task_state_presentation
from pyfem.gui.viewport import ResultsViewportHost
from pyfem.job import InMemoryJobMonitor, JobExecutionReport, JobSnapshot


class TextCallbackJobMonitor(InMemoryJobMonitor):
    """将求解监视消息同步到 GUI 日志。"""

    def __init__(self, sink: Callable[[str], None]) -> None:
        super().__init__()
        self._sink = sink

    def message(self, text: str) -> None:
        super().message(text)
        self._sink(text)


MODULE_ORDER = (
    "Part",
    "Property",
    "Assembly",
    "Step",
    "Interaction",
    "Load",
    "Mesh",
    "Optimization",
    "Job",
    "Visualization",
)
RESULTS_MODULE_NAME = "Visualization"


class PyFEMMainWindow(QMainWindow):
    """提供模型、结果浏览和后处理接层的主窗口。"""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        shell: GuiShell | None = None,
        enable_pyvista_preview: bool = True,
    ) -> None:
        super().__init__(parent)
        self.shell = GuiShell() if shell is None else shell
        self.model_edit_presenter = ModelEditPresenter(self.shell)
        self.viewport_host = ResultsViewportHost(enable_pyvista_preview=enable_pyvista_preview)
        self.results_browser = ResultsBrowser(self)
        self.navigation_panel = WorkbenchNavigationPanel(self)
        self.module_toolbox = ModuleToolbox(self)
        self.message_console_panel = MessageConsolePanel(self)
        self.log_text_edit = self.message_console_panel.messages_edit
        self.task_state = "idle"
        self._is_busy = False
        self._is_closing = False
        self._syncing_context_controls = False
        self._active_task: GuiTaskHandle | None = None
        self._active_process: object | None = None
        self._pending_follow_up: Callable[[], None] | None = None
        self._pending_results_display_mode: str | None = None
        self._current_view_context: GuiResultsViewContext | None = None
        self._current_field_presentation: FieldPresentationPolicy | None = None
        self._context_variant_selection_by_family: dict[str, str] = {}
        self._last_probe_series: Any | None = None
        self._current_model_summary: GuiModelSummary | None = None
        self._active_model_edit_dialog: QDialog | None = None
        self._material_manager_dialog: MaterialManagerDialog | None = None
        self._section_manager_dialog: SectionManagerDialog | None = None
        self._assign_section_dialog: AssignSectionDialog | None = None
        self._load_manager_dialog: LoadManagerDialog | None = None
        self._boundary_manager_dialog: BoundaryManagerDialog | None = None
        self._step_manager_dialog: StepManagerDialog | None = None
        self._job_center_dialog: JobCenterDialog | None = None
        self._job_monitor_dialog: JobMonitorDialog | None = None
        self._job_diagnostics_dialog: JobDiagnosticsDialog | None = None
        self._message_panel_default_height = 96
        self._job_records = GuiJobRecordStore()
        self._active_job_record_id: str | None = None

        self.setWindowTitle(APP_WINDOW_TITLE)
        self.resize(1680, 980)
        self.setMinimumSize(1320, 860)
        self.setStyleSheet(build_main_window_stylesheet())

        self._build_actions()
        self._build_ui()
        self._build_menu_bar()
        self._build_tool_bars()
        self._build_context_toolbar()
        self._build_status_bar()
        self._connect_signals()
        self.navigation_panel.set_model_context_action_resolver(self.command_registry.model_context_actions_for_entry)
        self._sync_module_toolbox(self.module_combo.currentData() or MODULE_ORDER[0])
        self._apply_task_state("idle", "等待加载模型或结果。")
        self._refresh_action_states()
        self.viewport_host.clear_results_context("当前尚未打开结果。")
        self.navigation_panel.set_workspace_context(self.module_combo.currentData() or MODULE_ORDER[0], use_results_tab=False)

    def _build_actions(self) -> None:
        style = self.style()
        open_icon = style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
        save_icon = style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        play_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        refresh_icon = style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        clear_icon = style.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton)
        info_icon = style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)
        file_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)

        self.open_model_action = QAction(open_icon, "Open Model...", self)
        self.open_model_action.setShortcut(QKeySequence.StandardKey.Open)
        self.load_model_action = QAction(refresh_icon, "Reload Model", self)
        self.run_job_action = QAction(play_icon, "Run", self)
        self.run_job_action.setShortcut(QKeySequence("F5"))
        self.show_messages_action = QAction("Show Message Area", self)
        self.show_messages_action.setCheckable(True)
        self.show_messages_action.setChecked(True)
        self.show_navigation_action = QAction("Show Navigation Pane", self)
        self.show_navigation_action.setCheckable(True)
        self.show_navigation_action.setChecked(True)
        self.show_toolbox_action = QAction("Show Toolbox", self)
        self.show_toolbox_action.setCheckable(True)
        self.show_toolbox_action.setChecked(True)
        self.show_navigation_details_action = QAction("Show Object Summary", self)
        self.show_navigation_details_action.setCheckable(True)
        self.show_navigation_details_action.setChecked(False)
        self.show_python_console_action = QAction("Python Console", self)
        self.clear_log_action = QAction(clear_icon, "Clear Messages", self)
        self.reset_view_action = QAction(refresh_icon, "Reset View", self)
        self.activate_preview_action = QAction(refresh_icon, "Enable Preview", self)
        self.refresh_viewport_action = QAction(refresh_icon, "Refresh Viewport", self)
        self.about_action = QAction(info_icon, "About", self)
        self.exit_action = QAction("Exit", self)
        self.exit_action.setShortcut(QKeySequence.StandardKey.Quit)

        self.command_registry = GuiCommandRegistry(self, style)
        self.open_results_action = self.command_registry.action("open_results")
        self.export_vtk_action = self.command_registry.action("export_vtk")
        self.edit_selected_action = self.command_registry.action("edit_selected")
        self.open_material_manager_action = self.command_registry.action("open_material_manager")
        self.open_section_manager_action = self.command_registry.action("open_section_manager")
        self.assign_section_action = self.command_registry.action("assign_section")
        self.validate_property_data_action = self.command_registry.action("validate_property_data")
        self.open_step_manager_action = self.command_registry.action("open_step_manager")
        self.open_step_output_controls_action = self.command_registry.action("open_step_output_controls")
        self.open_step_diagnostics_placeholder_action = self.command_registry.action("open_step_diagnostics_placeholder")
        self.validate_and_run_step_tools_action = self.command_registry.action("validate_and_run_step_tools")
        self.open_load_manager_action = self.command_registry.action("open_load_manager")
        self.open_boundary_manager_action = self.command_registry.action("open_boundary_manager")
        self.open_amplitude_manager_placeholder_action = self.command_registry.action("open_amplitude_manager_placeholder")
        self.edit_material_action = self.command_registry.action("edit_material")
        self.edit_section_action = self.command_registry.action("edit_section")
        self.edit_step_action = self.command_registry.action("edit_step")
        self.edit_load_action = self.command_registry.action("edit_load")
        self.edit_boundary_action = self.command_registry.action("edit_boundary")
        self.edit_output_request_action = self.command_registry.action("edit_output_request")
        self.edit_instance_transform_action = self.command_registry.action("edit_instance_transform")
        self.write_inp_action = self.command_registry.action("write_inp")
        self.run_current_model_action = self.command_registry.action("run_current_model")
        self.run_last_snapshot_action = self.command_registry.action("run_last_snapshot")
        self.open_snapshot_manifest_action = self.command_registry.action("open_snapshot_manifest")
        self.open_job_center_action = self.command_registry.action("open_job_center")
        self.open_current_job_monitor_action = self.command_registry.action("open_current_job_monitor")
        self.open_job_diagnostics_action = self.command_registry.action("open_job_diagnostics")
        self.open_results_output_action = self.command_registry.action("open_results_output")
        self.save_as_derived_case_action = self.command_registry.action("save_as_derived_case")
        self.show_selection_details_action = self.command_registry.action("selection_details")
        self.probe_action = self.command_registry.action("probe")
        self.open_legend_settings_action = self.command_registry.action("legend_settings")

        self.display_undeformed_action = QAction(file_icon, "Undeformed", self)
        self.display_undeformed_action.setCheckable(True)
        self.display_deformed_action = QAction(file_icon, "Deformed", self)
        self.display_deformed_action.setCheckable(True)
        self.display_contour_action = QAction(file_icon, "Contour on Deformed", self)
        self.display_contour_action.setCheckable(True)
        self.display_action_group = QActionGroup(self)
        self.display_action_group.setExclusive(True)
        for action in (self.display_undeformed_action, self.display_deformed_action, self.display_contour_action):
            self.display_action_group.addAction(action)
        self.display_undeformed_action.setChecked(True)

        self.module_action_group = QActionGroup(self)
        self.module_action_group.setExclusive(True)
        self.module_switch_actions: dict[str, QAction] = {}
        for module_name in MODULE_ORDER:
            action = QAction(module_name, self)
            action.setCheckable(True)
            if module_name == MODULE_ORDER[0]:
                action.setChecked(True)
            self.module_action_group.addAction(action)
            self.module_switch_actions[module_name] = action

    def _build_ui(self) -> None:
        self.workspace_root = QWidget(self)
        root_layout = QVBoxLayout(self.workspace_root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.results_dock_tabs = QTabWidget(self)
        self.results_dock_tabs.addTab(self.results_browser, "Results")
        self.results_dock_tabs.addTab(self._build_properties_panel(), "Inspector")
        self.optional_results_dock = QDockWidget("Postprocessing", self)
        self.optional_results_dock.setWidget(self.results_dock_tabs)
        self.optional_results_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.optional_results_dock)
        self.optional_results_dock.hide()

        self._build_postprocessing_dialogs()

        self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal, self.workspace_root)
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.addWidget(self.navigation_panel)
        self.workspace_splitter.addWidget(self.module_toolbox)
        self.workspace_splitter.addWidget(self.viewport_host)
        self.workspace_splitter.setStretchFactor(0, 0)
        self.workspace_splitter.setStretchFactor(1, 0)
        self.workspace_splitter.setStretchFactor(2, 1)
        self.workspace_splitter.setSizes([300, ModuleToolbox.FIXED_WIDTH, 1320])

        self.main_splitter = QSplitter(Qt.Orientation.Vertical, self.workspace_root)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.addWidget(self.workspace_splitter)
        self.main_splitter.addWidget(self.message_console_panel)
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, True)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 0)
        self.main_splitter.setSizes([860, self._message_panel_default_height])

        root_layout.addWidget(self.main_splitter, 1)
        self.setCentralWidget(self.workspace_root)

    def _build_postprocessing_dialogs(self) -> None:
        """创建按需打开的后处理弹窗。"""

        self.selection_details_dialog = SelectionDetailsDialog(self)
        self.legend_settings_dialog = LegendSettingsDialog(self)
        self.legend_settings_dialog.applyRequested.connect(self._apply_legend_dialog_settings)
        self.probe_dialog = ProbeDialog(self)
        self.probe_dialog.finished.connect(lambda _result: self.viewport_host.hide_command_prompt())
        self.export_vtk_dialog = ExportOptionsDialog(self, title="Export VTK", path_label="VTK Path", path_filter="VTK (*.vtk);;All Files (*)")
        self.export_probe_dialog = ExportOptionsDialog(self, title="Export Probe CSV", path_label="CSV Path", path_filter="CSV (*.csv);;All Files (*)")

        self.probe_dialog.probe_kind_combo.addItem("Node", PROBE_KIND_NODE)
        self.probe_dialog.probe_kind_combo.addItem("Element", PROBE_KIND_ELEMENT)
        self.probe_dialog.probe_kind_combo.addItem("Integration Point", PROBE_KIND_INTEGRATION_POINT)
        self.probe_dialog.probe_kind_combo.addItem("Averaged", PROBE_KIND_AVERAGED)

        self.probe_kind_combo = self.probe_dialog.probe_kind_combo
        self.probe_target_combo = self.probe_dialog.probe_target_combo
        self.probe_component_combo = self.probe_dialog.probe_component_combo
        self.probe_status_value = self.probe_dialog.probe_status_value
        self.run_probe_button = self.probe_dialog.run_probe_button
        self.export_probe_button = self.probe_dialog.export_probe_button
        self.probe_output_edit = self.probe_dialog.probe_output_edit

    def _build_properties_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        model_group = QGroupBox("Model", panel)
        model_layout = QFormLayout(model_group)
        self.model_name_value = QLabel("-", model_group)
        self.model_steps_value = QLabel("-", model_group)
        self.model_steps_value.setWordWrap(True)
        self.model_parts_value = QLabel("-", model_group)
        self.model_instances_value = QLabel("-", model_group)
        self.model_dirty_value = QLabel("clean", model_group)
        model_layout.addRow("Name", self.model_name_value)
        model_layout.addRow("Steps", self.model_steps_value)
        model_layout.addRow("Parts", self.model_parts_value)
        model_layout.addRow("Instances", self.model_instances_value)
        model_layout.addRow("Dirty", self.model_dirty_value)

        status_group = QGroupBox("Status", panel)
        status_layout = QVBoxLayout(status_group)
        status_row = QHBoxLayout()
        state_label = QLabel("Task", status_group)
        state_label.setObjectName("ContextCaption")
        self.task_state_value = QLabel("idle", status_group)
        status_row.addWidget(state_label)
        status_row.addStretch(1)
        status_row.addWidget(self.task_state_value)
        form_layout = QFormLayout()
        self.status_label = QLabel("等待操作", status_group)
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("SoftText")
        self.results_summary_value = QLabel("-", status_group)
        self.results_summary_value.setWordWrap(True)
        self.results_summary_value.setObjectName("SoftText")
        self.current_results_value = QLabel("-", status_group)
        self.current_results_value.setWordWrap(True)
        self.current_results_value.setObjectName("SoftText")
        form_layout.addRow("Status", self.status_label)
        form_layout.addRow("Summary", self.results_summary_value)
        form_layout.addRow("Current", self.current_results_value)
        status_layout.addLayout(status_row)
        status_layout.addLayout(form_layout)

        probe_group = QGroupBox("Probe", panel)
        probe_layout = QFormLayout(probe_group)
        self.probe_kind_combo = QComboBox(probe_group)
        self.probe_kind_combo.addItem("Node", PROBE_KIND_NODE)
        self.probe_kind_combo.addItem("Element", PROBE_KIND_ELEMENT)
        self.probe_kind_combo.addItem("Integration Point", PROBE_KIND_INTEGRATION_POINT)
        self.probe_kind_combo.addItem("Averaged", PROBE_KIND_AVERAGED)
        self.probe_target_combo = QComboBox(probe_group)
        self.probe_target_combo.setEditable(True)
        self.probe_component_combo = QComboBox(probe_group)
        self.probe_status_value = QLabel("No probe target", probe_group)
        self.probe_status_value.setWordWrap(True)
        self.probe_status_value.setObjectName("SoftText")
        probe_button_row = QHBoxLayout()
        self.run_probe_button = QPushButton("Run Probe", probe_group)
        self.export_probe_button = QPushButton("Export CSV", probe_group)
        probe_button_row.addWidget(self.run_probe_button)
        probe_button_row.addWidget(self.export_probe_button)
        self.probe_output_edit = QPlainTextEdit(probe_group)
        self.probe_output_edit.setReadOnly(True)
        self.probe_output_edit.setPlaceholderText("Probe result details will appear here.")
        self.probe_output_edit.setMinimumHeight(140)
        probe_layout.addRow("Kind", self.probe_kind_combo)
        probe_layout.addRow("Target", self.probe_target_combo)
        probe_layout.addRow("Component", self.probe_component_combo)
        probe_layout.addRow("State", self.probe_status_value)
        probe_layout.addRow("Action", probe_button_row)
        probe_layout.addRow(self.probe_output_edit)

        layout.addWidget(model_group)
        layout.addWidget(status_group)
        layout.addWidget(probe_group, 1)
        return panel
    def _build_menu_bar(self) -> None:
        menu_bar = QMenuBar(self)
        menu_bar.setNativeMenuBar(False)
        self.setMenuBar(menu_bar)

        file_menu = menu_bar.addMenu("File")
        file_menu.addAction(self.open_model_action)
        file_menu.addAction(self.load_model_action)
        file_menu.addAction(self.write_inp_action)
        file_menu.addAction(self.save_as_derived_case_action)
        file_menu.addSeparator()
        file_menu.addAction(self.open_results_action)
        file_menu.addAction(self.export_vtk_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        model_menu = menu_bar.addMenu("Model")
        model_menu.addAction(self.edit_selected_action)
        model_menu.addAction(self.edit_material_action)
        model_menu.addAction(self.edit_section_action)
        model_menu.addAction(self.edit_step_action)
        model_menu.addAction(self.edit_load_action)
        model_menu.addAction(self.edit_boundary_action)
        model_menu.addAction(self.edit_output_request_action)
        model_menu.addAction(self.edit_instance_transform_action)

        view_menu = menu_bar.addMenu("View")
        view_menu.addAction(self.show_navigation_action)
        view_menu.addAction(self.show_toolbox_action)
        view_menu.addAction(self.show_messages_action)
        view_menu.addAction(self.show_navigation_details_action)
        view_menu.addAction(self.show_selection_details_action)

        viewport_menu = menu_bar.addMenu("Viewport")
        viewport_menu.addAction(self.display_undeformed_action)
        viewport_menu.addAction(self.display_deformed_action)
        viewport_menu.addAction(self.display_contour_action)
        viewport_menu.addSeparator()
        viewport_menu.addAction(self.activate_preview_action)
        viewport_menu.addAction(self.refresh_viewport_action)
        viewport_menu.addAction(self.reset_view_action)
        viewport_menu.addAction(self.open_legend_settings_action)

        self.module_menus: dict[str, object] = {}
        for module_name in MODULE_ORDER:
            module_menu = menu_bar.addMenu(module_name)
            for definition in self.command_registry.definitions_for_module(module_name):
                module_menu.addAction(self.command_registry.action(definition.command_id))
            self.module_menus[module_name] = module_menu

        tools_menu = menu_bar.addMenu("Tools")
        tools_menu.addAction(self.show_python_console_action)
        tools_menu.addAction(self.clear_log_action)
        tools_menu.addAction(self.probe_action)
        tools_menu.addAction(self.show_selection_details_action)

        plugins_menu = menu_bar.addMenu("Plug-ins")
        plugins_menu.addAction(self._create_placeholder_action("Plug-in Manager", module_name="Plug-ins"))

        help_menu = menu_bar.addMenu("Help")
        help_menu.addAction(self.about_action)

    def _build_tool_bars(self) -> None:
        self.main_toolbar = QToolBar("Main", self)
        self.main_toolbar.setObjectName("MainToolBar")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.main_toolbar)
        for action in (
            self.open_model_action,
            self.open_results_action,
            self.run_job_action,
            self.export_vtk_action,
        ):
            self.main_toolbar.addAction(action)

        self.io_toolbar = QToolBar("IO", self)
        self.io_toolbar.setObjectName("FileToolBar")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.io_toolbar)

        self.input_path_edit = QLineEdit(self)
        self.input_path_edit.setPlaceholderText("input .inp path")
        self.results_path_edit = QLineEdit(self)
        self.results_path_edit.setPlaceholderText("results .json path")
        self.vtk_path_edit = QLineEdit(self)
        self.vtk_path_edit.setPlaceholderText("export .vtk path")
        self.export_vtk_checkbox = QCheckBox("Write VTK", self)
        self.export_vtk_checkbox.setChecked(True)
        self.browse_input_button = QPushButton("Browse", self)
        self.load_model_button = QPushButton("Load", self)
        self.browse_results_button = QPushButton("Browse", self)
        self.open_results_button = QPushButton("Open", self)
        self.browse_vtk_button = QPushButton("Browse", self)
        self.export_vtk_button = QPushButton("Export", self)
        self.run_button = QPushButton("Run", self)
        self.run_step_combo = QComboBox(self)
        self.run_step_combo.addItem("All Steps", None)

        for widget in (
            QLabel("INP", self),
            self.input_path_edit,
            self.browse_input_button,
            self.load_model_button,
            QLabel("Results", self),
            self.results_path_edit,
            self.browse_results_button,
            self.open_results_button,
            QLabel("VTK", self),
            self.vtk_path_edit,
            self.export_vtk_checkbox,
            self.browse_vtk_button,
            self.export_vtk_button,
            QLabel("Run Step", self),
            self.run_step_combo,
            self.run_button,
        ):
            self.io_toolbar.addWidget(widget)

    def _build_context_toolbar(self) -> None:
        self.context_toolbar = QToolBar("Context", self)
        self.context_toolbar.setObjectName("ContextToolBar")
        self.context_toolbar.setMovable(False)
        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.context_toolbar)

        self.module_combo = QComboBox(self)
        for module_name in MODULE_ORDER:
            self.module_combo.addItem(module_name, module_name)
        self.context_step_combo = QComboBox(self)
        self.context_frame_combo = QComboBox(self)
        self.context_field_combo = QComboBox(self)
        self.context_field_combo.setMinimumWidth(180)
        self.context_field_variant_combo = QComboBox(self)
        self.context_field_variant_combo.setMinimumWidth(140)
        self.display_mode_combo = QComboBox(self)
        self.display_mode_combo.addItem("Undeformed", DISPLAY_MODE_UNDEFORMED)
        self.display_mode_combo.addItem("Deformed", DISPLAY_MODE_DEFORMED)
        self.display_mode_combo.addItem("Contour on Deformed", DISPLAY_MODE_CONTOUR_DEFORMED)
        self.context_component_combo = QComboBox(self)
        self.context_component_combo.setMinimumWidth(140)

        for label, widget in (
            ("Module", self.module_combo),
            ("Step", self.context_step_combo),
            ("Frame", self.context_frame_combo),
            ("Field", self.context_field_combo),
            ("Variant", self.context_field_variant_combo),
            ("Display", self.display_mode_combo),
            ("Component", self.context_component_combo),
        ):
            container = QWidget(self)
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
            layout.addWidget(QLabel(label, container))
            layout.addWidget(widget)
            self.context_toolbar.addWidget(container)
        self.context_toolbar.addSeparator()
        self.context_toolbar.addAction(self.show_selection_details_action)
        self.context_toolbar.addAction(self.open_legend_settings_action)
        self.context_toolbar.addAction(self.probe_action)

    def _build_status_bar(self) -> None:
        status_bar = self.statusBar()
        status_bar.setSizeGripEnabled(False)
        status_bar.setContentsMargins(6, 2, 6, 2)
        status_bar.setMinimumHeight(32)
        self.footer_message_label = QLabel("Ready", status_bar)
        self.footer_task_state_label = QLabel("idle", status_bar)
        self.footer_model_label = QLabel("Model: -", status_bar)
        self.footer_results_label = QLabel("Results: -", status_bar)
        for label in (
            self.footer_message_label,
            self.footer_task_state_label,
            self.footer_model_label,
            self.footer_results_label,
        ):
            label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        status_bar.addWidget(self.footer_message_label, 1)
        status_bar.addPermanentWidget(self.footer_task_state_label)
        status_bar.addPermanentWidget(self.footer_model_label)
        status_bar.addPermanentWidget(self.footer_results_label)

    def _connect_signals(self) -> None:
        self.open_model_action.triggered.connect(self._browse_and_load_model)
        self.load_model_action.triggered.connect(self.load_model_from_editor)
        self.run_job_action.triggered.connect(self.run_job)
        self.show_messages_action.toggled.connect(self._set_message_panel_expanded)
        self.show_navigation_action.toggled.connect(self.navigation_panel.setVisible)
        self.show_toolbox_action.toggled.connect(self.module_toolbox.setVisible)
        self.show_navigation_details_action.toggled.connect(self.navigation_panel.set_details_visible)
        self.show_python_console_action.triggered.connect(self._show_python_console)
        self.clear_log_action.triggered.connect(self.log_text_edit.clear)
        self.activate_preview_action.triggered.connect(self.viewport_host.ensure_pyvista_preview)
        self.refresh_viewport_action.triggered.connect(self.viewport_host.refresh_view)
        self.reset_view_action.triggered.connect(self.viewport_host.reset_view)
        self.about_action.triggered.connect(self._show_about_dialog)
        self.exit_action.triggered.connect(self.close)

        self.display_undeformed_action.triggered.connect(lambda: self._set_display_mode_value(DISPLAY_MODE_UNDEFORMED))
        self.display_deformed_action.triggered.connect(lambda: self._set_display_mode_value(DISPLAY_MODE_DEFORMED))
        self.display_contour_action.triggered.connect(lambda: self._set_display_mode_value(DISPLAY_MODE_CONTOUR_DEFORMED))

        self.browse_input_button.clicked.connect(self._browse_and_load_model)
        self.load_model_button.clicked.connect(self.load_model_from_editor)
        self.browse_results_button.clicked.connect(self._browse_and_open_results)
        self.open_results_button.clicked.connect(self.open_results_from_editor)
        self.browse_vtk_button.clicked.connect(self._browse_and_export_vtk)
        self.export_vtk_button.clicked.connect(self._browse_and_export_vtk)
        self.run_button.clicked.connect(self.run_job)
        self.message_console_panel.clear_button.clicked.connect(self.log_text_edit.clear)
        self.viewport_host.legend_button.clicked.connect(self._show_legend_settings_dialog)

        self.results_browser.selectionChanged.connect(self._on_browser_selection_changed)
        self.navigation_panel.resultsSelectionRequested.connect(self._on_navigation_results_selection_requested)
        self.navigation_panel.modelSelectionRequested.connect(self._on_navigation_model_selection_requested)
        self.navigation_panel.modelEditRequested.connect(self._open_model_edit_dialog)
        self.module_combo.currentIndexChanged.connect(self._on_module_combo_changed)
        self.context_step_combo.currentIndexChanged.connect(self._on_context_step_changed)
        self.context_frame_combo.currentIndexChanged.connect(self._on_context_frame_changed)
        self.context_field_combo.currentIndexChanged.connect(self._on_context_field_changed)
        self.context_field_variant_combo.currentIndexChanged.connect(self._on_context_field_variant_changed)
        self.display_mode_combo.currentIndexChanged.connect(self._on_display_mode_changed)
        self.context_component_combo.currentIndexChanged.connect(self._on_context_component_changed)
        self.viewport_host.componentChanged.connect(self._on_viewport_component_changed)

        self.probe_kind_combo.currentIndexChanged.connect(self._refresh_probe_controls)
        self.probe_dialog.runRequested.connect(self._run_probe_from_controls)
        self.probe_dialog.exportRequested.connect(self._export_probe_from_dialog)

    def _create_placeholder_action(self, text: str, *, module_name: str, icon: QIcon | None = None, checkable: bool = False) -> QAction:
        action = QAction(icon or QIcon(), text, self)
        action.setCheckable(checkable)
        action.triggered.connect(lambda checked=False, module_name=module_name, text=text: self._set_status(f"{module_name}: {text}"))
        return action

    def _show_about_dialog(self) -> None:
        QMessageBox.information(self, "About", f"{APP_DISPLAY_NAME}\n\n后处理界面通过 ResultsFacade、Query 和 Probe 服务消费结果。")

    def _sync_module_toolbox(self, module_name: str) -> None:
        resolved_module_name = module_name if module_name in MODULE_ORDER else MODULE_ORDER[0]
        self.module_toolbox.set_module(resolved_module_name, self.command_registry.toolbox_specs_for_module(resolved_module_name))

    def _set_message_panel_expanded(self, expanded: bool) -> None:
        if expanded:
            self.main_splitter.setSizes([max(320, self.height() - self._message_panel_default_height), self._message_panel_default_height])
        else:
            self.main_splitter.setSizes([self.height(), 0])
        self.show_messages_action.blockSignals(True)
        self.show_messages_action.setChecked(expanded)
        self.show_messages_action.blockSignals(False)

    def _show_python_console(self) -> None:
        self._set_message_panel_expanded(True)
        self.main_splitter.setSizes([max(320, self.height() - 180), 180])
        self.message_console_panel.show_python_console()
        self._set_status("Python Console placeholder is active.")

    def _append_log(self, text: str) -> None:
        message = text.strip()
        if not message:
            return
        self.log_text_edit.appendPlainText(message)
        self._append_active_job_message(message)
        self.footer_message_label.setText(message)
        self.statusBar().clearMessage()

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)
        self.footer_message_label.setText(text)
        self.statusBar().clearMessage()

    def _set_results_summary_text(self, text: str) -> None:
        self.results_summary_value.setText(text)

    def _apply_task_state(self, task_state: str, detail: str) -> None:
        self.task_state = task_state
        presentation = resolve_task_state_presentation(task_state)
        self.task_state_value.setText(presentation.label)
        self.task_state_value.setStyleSheet(
            build_pill_stylesheet(
                foreground_color=presentation.foreground_color,
                background_color=presentation.background_color,
                border_color=presentation.border_color,
            )
        )
        self.footer_task_state_label.setText(presentation.label)
        self.footer_task_state_label.setStyleSheet(
            build_pill_stylesheet(
                foreground_color=presentation.foreground_color,
                background_color=presentation.background_color,
                border_color=presentation.border_color,
            )
        )
        self._set_status(detail)
        self._refresh_action_states()

    def _refresh_action_states(self) -> None:
        busy = self._active_task is not None or self._is_busy
        model_loaded = self.shell.state.opened_model is not None
        self.run_button.setEnabled(not busy and model_loaded)
        self.load_model_button.setEnabled(not busy)
        self.run_job_action.setEnabled(not busy and model_loaded)
        self.load_model_action.setEnabled(not busy)
        self.command_registry.refresh()
        self.open_results_button.setEnabled(self.open_results_action.isEnabled())
        self.export_vtk_button.setEnabled(self.export_vtk_action.isEnabled())
        self.run_probe_button.setEnabled(not busy and self.run_probe_button.isEnabled())
        self.export_probe_button.setEnabled(not busy and self.export_probe_button.isEnabled())

    def _update_model_summary_widgets(self, summary: GuiModelSummary) -> None:
        self.model_name_value.setText(summary.model_name)
        self.model_steps_value.setText(", ".join(summary.step_names) or "-")
        self.model_parts_value.setText(str(summary.part_count))
        self.model_instances_value.setText(str(summary.instance_count))
        dirty_text = "dirty" if self.shell.state.model_dirty else "clean"
        self.model_dirty_value.setText(dirty_text)
        self.footer_model_label.setText(f"Model: {summary.source_path.name} [{dirty_text}]")

    def _populate_run_step_combo(self, summary: GuiModelSummary) -> None:
        self.run_step_combo.blockSignals(True)
        self.run_step_combo.clear()
        self.run_step_combo.addItem("All Steps", None)
        for step_name in summary.step_names:
            self.run_step_combo.addItem(step_name, step_name)
        self.run_step_combo.blockSignals(False)
    def _set_display_mode_value(self, display_mode: str) -> None:
        index = self.display_mode_combo.findData(display_mode)
        if index >= 0:
            self.display_mode_combo.setCurrentIndex(index)
        self.viewport_host.set_display_mode(display_mode)
        self._sync_display_actions(display_mode)
        self._update_viewport_workspace_context()

    def _sync_display_actions(self, display_mode: str) -> None:
        mapping = {
            DISPLAY_MODE_UNDEFORMED: self.display_undeformed_action,
            DISPLAY_MODE_DEFORMED: self.display_deformed_action,
            DISPLAY_MODE_CONTOUR_DEFORMED: self.display_contour_action,
        }
        action = mapping.get(display_mode)
        if action is not None:
            action.setChecked(True)

    def _sync_results_context_controls(self, *, step_name: str | None = None, frame_id: int | None = None, field_name: str | None = None) -> None:
        previous_family_key = self.context_field_combo.currentData() if isinstance(self.context_field_combo.currentData(), str) else None
        previous_variant_key = (
            self.context_field_variant_combo.currentData()
            if isinstance(self.context_field_variant_combo.currentData(), str)
            else None
        )
        if previous_family_key is not None and previous_variant_key is not None:
            self._context_variant_selection_by_family[previous_family_key] = previous_variant_key
        self._syncing_context_controls = True
        try:
            self.context_step_combo.clear()
            self.context_frame_combo.clear()
            self.context_field_combo.clear()
            self.context_field_variant_combo.clear()
            self.context_component_combo.clear()
            self._current_field_presentation = None
            if self._current_view_context is None:
                return
            results_facade = self._current_view_context.results_facade
            step_names = results_facade.list_steps()
            resolved_step_name = step_name if step_name in step_names else (step_names[0] if step_names else None)
            for item in step_names:
                self.context_step_combo.addItem(item, item)
            if resolved_step_name is not None:
                self._set_combo_data(self.context_step_combo, resolved_step_name)

            frames = () if resolved_step_name is None else results_facade.frames(step_name=resolved_step_name)
            frame_ids = tuple(frame.frame_id for frame in frames)
            resolved_frame_id = frame_id if frame_id in frame_ids else (frame_ids[0] if frame_ids else None)
            for frame in frames:
                text = f"Frame {frame.frame_id} | {frame.axis_kind}={frame.axis_value}"
                self.context_frame_combo.addItem(text, frame.frame_id)
            if resolved_frame_id is not None:
                self._set_combo_data(self.context_frame_combo, resolved_frame_id)

            field_overviews = () if resolved_step_name is None or resolved_frame_id is None else results_facade.fields(step_name=resolved_step_name, frame_id=resolved_frame_id)
            self._current_field_presentation = FieldPresentationPolicy.from_field_overviews(field_overviews)
            presentation = self._current_field_presentation
            resolved_field_name = presentation.default_field_name(field_name)
            resolved_family_key = presentation.default_family_key(resolved_field_name)
            for family in presentation.families:
                item_index = self.context_field_combo.count()
                self.context_field_combo.addItem(family.display_name, family.family_key)
                self._set_combo_item_tooltip(self.context_field_combo, item_index, family.tooltip_text)
            if resolved_family_key is not None:
                self._set_combo_data(self.context_field_combo, resolved_family_key)

            resolved_variant_key = None
            family = presentation.family(resolved_family_key) if resolved_family_key is not None else None
            if family is not None:
                saved_variant_key = self._context_variant_selection_by_family.get(family.family_key)
                if previous_family_key == family.family_key and previous_variant_key is not None:
                    saved_variant_key = previous_variant_key
                if resolved_field_name is not None and saved_variant_key is not None:
                    if presentation.resolve_field_name(family.family_key, saved_variant_key) == resolved_field_name:
                        resolved_variant_key = saved_variant_key
                if resolved_variant_key is None and resolved_field_name is not None:
                    if family.default_field_name == resolved_field_name and saved_variant_key in {None, COMMON_VARIANT_KEY}:
                        resolved_variant_key = COMMON_VARIANT_KEY
                    else:
                        resolved_variant_key = presentation.variant_key_for_field_name(
                            family.family_key,
                            resolved_field_name,
                            prefer_common=False,
                        )
                if resolved_variant_key is None:
                    resolved_variant_key = COMMON_VARIANT_KEY
                for variant in family.variants:
                    item_index = self.context_field_variant_combo.count()
                    self.context_field_variant_combo.addItem(variant.display_name, variant.variant_key)
                    self._set_combo_item_tooltip(self.context_field_variant_combo, item_index, variant.tooltip_text)
                self._set_combo_data(self.context_field_variant_combo, resolved_variant_key)
                self._context_variant_selection_by_family[family.family_key] = resolved_variant_key
                resolved_field_name = presentation.resolve_field_name(family.family_key, resolved_variant_key)
                selection = presentation.describe_selection(
                    resolved_field_name,
                    variant_key=resolved_variant_key,
                    prefer_common=resolved_variant_key == COMMON_VARIANT_KEY,
                )
                self.context_field_combo.setToolTip(family.tooltip_text)
                self.context_field_variant_combo.setToolTip("" if selection is None else selection.tooltip_text)
            else:
                self.context_field_combo.setToolTip("")
                self.context_field_variant_combo.setToolTip("")

            component_names = ()
            if resolved_step_name is not None and resolved_frame_id is not None and resolved_field_name is not None:
                component_names = build_component_choices(results_facade, resolved_step_name, resolved_frame_id, resolved_field_name)
            for component_name in component_names:
                self.context_component_combo.addItem(component_name, component_name)
            current_component_name = self.viewport_host.current_component_name
            if current_component_name in component_names:
                self._set_combo_data(self.context_component_combo, current_component_name)
            elif component_names:
                self.context_component_combo.setCurrentIndex(0)
        finally:
            self._syncing_context_controls = False

    def _set_combo_item_tooltip(self, combo_box: QComboBox, index: int, tooltip: str) -> None:
        """为下拉框条目写入 tooltip。"""

        model = combo_box.model()
        if model is None:
            return
        model_index = model.index(index, 0)
        model.setData(model_index, tooltip, Qt.ItemDataRole.ToolTipRole)

    def _selected_context_family_key(self) -> str | None:
        """返回当前上下文工具条选中的 family。"""

        family_key = self.context_field_combo.currentData()
        return family_key if isinstance(family_key, str) else None

    def _selected_context_variant_key(self) -> str | None:
        """返回当前上下文工具条选中的 variant。"""

        variant_key = self.context_field_variant_combo.currentData()
        return variant_key if isinstance(variant_key, str) else None

    def _resolve_context_field_name(self, *, family_key: str | None = None, variant_key: str | None = None) -> str | None:
        """将当前工具条选择解析为正式字段名。"""

        if self._current_field_presentation is None:
            return None
        resolved_family_key = family_key if family_key is not None else self._selected_context_family_key()
        resolved_variant_key = variant_key if variant_key is not None else self._selected_context_variant_key()
        return self._current_field_presentation.resolve_field_name(resolved_family_key, resolved_variant_key)

    def _selected_field_overview(self, step_name: str | None, frame_id: int | None, field_name: str | None):
        if self._current_view_context is None or step_name is None or frame_id is None or field_name is None:
            return None
        for overview in self._current_view_context.results_facade.fields(step_name=step_name, frame_id=frame_id):
            if overview.field_name == field_name:
                return overview
        return None

    def _update_current_results_text(self, step_name: str | None, frame_id: int | None, field_name: str | None) -> None:
        overview = self._selected_field_overview(step_name, frame_id, field_name)
        if overview is None:
            self.current_results_value.setText("-")
            self.current_results_value.setToolTip("")
            return
        variant_key = self._selected_context_variant_key()
        selection = None if self._current_field_presentation is None else self._current_field_presentation.describe_selection(
            field_name,
            variant_key=variant_key,
            prefer_common=variant_key == COMMON_VARIANT_KEY,
        )
        range_text = "-"
        if overview.min_value is not None and overview.max_value is not None:
            range_text = f"{overview.min_value:.6g} ~ {overview.max_value:.6g}"
        component_text = self.viewport_host.current_component_name or (", ".join(overview.component_names) or "-")
        self.current_results_value.setText(
            "\n".join(
                (
                    f"当前结果: {overview.field_name if selection is None else selection.family_display_name}",
                    f"变体: {'-' if selection is None else selection.variant_display_name}",
                    f"正式字段: {overview.field_name}",
                    f"步: {step_name}",
                    f"帧: {frame_id}",
                    f"分量: {component_text}",
                    f"范围: {range_text}",
                    f"附加信息: source={overview.source_type}, position={overview.position}, targets={overview.target_count}",
                )
            )
        )
        self.current_results_value.setToolTip("" if selection is None else selection.detail_text)

    def _update_viewport_workspace_context(self) -> None:
        module_name = self.module_combo.currentData() or MODULE_ORDER[0]
        family_text = self.context_field_combo.currentText().strip()
        variant_text = self.context_field_variant_combo.currentText().strip()
        object_text = family_text or self.model_name_value.text() or "No object"
        if family_text and variant_text:
            object_text = f"{family_text} | {variant_text}"
        display_text = self.display_mode_combo.currentText().strip()
        if self.viewport_host.current_component_name:
            display_text = f"{display_text} | {self.viewport_host.current_component_name}"
        self.viewport_host.set_workspace_context(module_name, object_text, display_text)
        self.navigation_panel.set_workspace_context(module_name, use_results_tab=module_name == RESULTS_MODULE_NAME and self._current_view_context is not None)

    @Slot(object, object, object)
    def _on_browser_selection_changed(self, step_name: object, frame_id: object, field_name: object) -> None:
        resolved_step_name = step_name if isinstance(step_name, str) else None
        resolved_frame_id = frame_id if isinstance(frame_id, int) else None
        resolved_field_name = field_name if isinstance(field_name, str) else None
        self._sync_results_context_controls(step_name=resolved_step_name, frame_id=resolved_frame_id, field_name=resolved_field_name)
        if self._current_view_context is not None:
            self.viewport_host.apply_selection(step_name=resolved_step_name, frame_id=resolved_frame_id, field_name=resolved_field_name)
            self.navigation_panel.select_results(step_name=resolved_step_name, frame_id=resolved_frame_id, field_name=resolved_field_name)
        self._update_current_results_text(resolved_step_name, resolved_frame_id, resolved_field_name)
        self._refresh_probe_controls()
        self._update_viewport_workspace_context()
        self.command_registry.refresh()

    @Slot(str, object, object, object)
    def _on_navigation_results_selection_requested(self, kind: str, step_name: object, frame_id: object, field_name: object) -> None:
        if kind == "field" and isinstance(step_name, str) and isinstance(frame_id, int) and isinstance(field_name, str):
            self.results_browser.select_step(step_name)
            self.results_browser.select_frame(frame_id)
            self.results_browser.select_field(field_name)
        elif kind == "frame" and isinstance(step_name, str) and isinstance(frame_id, int):
            self.results_browser.select_step(step_name)
            self.results_browser.select_frame(frame_id)
        elif kind == "step" and isinstance(step_name, str):
            self.results_browser.select_step(step_name)
        self.command_registry.refresh()

    @Slot(str, object)
    def _on_navigation_model_selection_requested(self, kind: str, name: object) -> None:
        text = "-" if name in (None, "") else str(name)
        self._set_status(f"{kind}: {text}")
        self.command_registry.refresh()

    @Slot(str, object)
    def _open_model_edit_dialog(self, kind: str, name: object) -> None:
        if name in {None, ""}:
            return
        object_name = str(name)
        try:
            resolved_kind = self.model_edit_presenter.resolve_kind(kind, object_name)
        except Exception as error:
            self._handle_error("Edit Selected", error)
            return

        dialog: BaseException | QDialog
        if resolved_kind == "material":
            dialog = MaterialEditDialog(self, self.model_edit_presenter, object_name)
        elif resolved_kind == "step":
            dialog = StepEditDialog(self, self.model_edit_presenter, object_name)
        elif resolved_kind == "boundary":
            dialog = BoundaryEditDialog(self, self.model_edit_presenter, object_name)
        elif resolved_kind in {"nodal_load", "distributed_load"}:
            dialog = LoadEditDialog(self, self.model_edit_presenter, resolved_kind, object_name)
        elif resolved_kind == "output_request":
            dialog = OutputRequestEditDialog(self, self.model_edit_presenter, object_name)
        elif resolved_kind == "instance":
            dialog = InstanceTransformDialog(self, self.model_edit_presenter, object_name)
        elif resolved_kind == "section":
            dialog = SectionEditDialog(self, self.model_edit_presenter, object_name)
        else:
            self._set_status(f"{resolved_kind}: 当前未提供正式编辑弹窗。")
            return

        if hasattr(dialog, "applied"):
            dialog.applied.connect(lambda: self._refresh_model_views_after_edit(resolved_kind, object_name))
        if hasattr(dialog, "modelChanged"):
            if resolved_kind in {"material", "section"}:
                dialog.modelChanged.connect(self._on_property_model_changed)
            elif resolved_kind == "step":
                dialog.modelChanged.connect(self._on_step_model_changed)
            elif resolved_kind in {"nodal_load", "distributed_load", "boundary"}:
                dialog.modelChanged.connect(self._on_load_model_changed)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.destroyed.connect(lambda *_args: self._clear_tracked_dialog("_active_model_edit_dialog", dialog))
        self._active_model_edit_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _clear_tracked_dialog(self, dialog_name: str, dialog: QDialog | None = None) -> None:
        """在对话框销毁后清空主窗口上的跟踪引用。"""

        current_dialog = getattr(self, dialog_name, None)
        if dialog is None or current_dialog is dialog:
            setattr(self, dialog_name, None)

    def _close_tracked_dialog(self, dialog_name: str) -> None:
        """按名称显式关闭并释放主窗口跟踪的对话框。"""

        dialog = getattr(self, dialog_name, None)
        if dialog is None:
            return
        setattr(self, dialog_name, None)
        dialog.close()

    def _job_records_snapshot(self) -> tuple[GuiJobRecord, ...]:
        """返回当前 GUI 会话中的 Job 记录快照。"""

        return self._job_records.records()

    def _resolve_job_record(self, record_id: object | None = None) -> GuiJobRecord | None:
        """按编号解析记录；若缺省则回退到活动记录或最近记录。"""

        if record_id not in {None, ""}:
            record = self._job_records.get(str(record_id))
            if record is not None:
                return record
        if self._active_job_record_id not in {None, ""}:
            record = self._job_records.get(self._active_job_record_id)
            if record is not None:
                return record
        return self._job_records.latest()

    def _selected_run_step_name(self) -> str:
        """返回当前运行面板中解析后的 step 名称。"""

        step_name = self.run_step_combo.currentData()
        return "All Steps" if step_name in {None, ""} else str(step_name)

    def _expected_results_path(self) -> Path | None:
        """返回当前 GUI 期望写出的结果路径。"""

        results_text = self.results_path_edit.text().strip()
        if results_text:
            return Path(results_text)
        try:
            return self.shell.build_default_results_path()
        except Exception:
            return None

    def _expected_export_path(self) -> Path | None:
        """返回当前 GUI 期望写出的导出路径。"""

        if not self.export_vtk_checkbox.isChecked():
            return None
        export_text = self.vtk_path_edit.text().strip()
        if export_text:
            return Path(export_text)
        try:
            return self.shell.build_default_vtk_path()
        except Exception:
            return None

    def _put_job_record(self, record: GuiJobRecord) -> GuiJobRecord:
        """写回一条 Job 记录并同步相关对话框。"""

        stored_record = self._job_records.put(record)
        self._refresh_job_dialogs()
        return stored_record

    def _start_job_record(self, *, snapshot: JobSnapshot | None, action_text: str) -> GuiJobRecord:
        """在正式运行开始前创建一条运行记录。"""

        timestamp = create_job_timestamp()
        model_summary = self.shell.state.opened_model
        resolved_step_name = self._selected_run_step_name()
        record = GuiJobRecord(
            record_id=uuid4().hex,
            display_name=build_job_display_name(
                model_name=None if model_summary is None else model_summary.model_name,
                step_name=resolved_step_name,
                snapshot_path=None if snapshot is None else snapshot.snapshot_path,
            ),
            step_name=resolved_step_name,
            status="running",
            created_at=timestamp,
            started_at=timestamp,
            finished_at=None,
            results_path=self._expected_results_path() if snapshot is None else snapshot.results_path,
            export_path=self._expected_export_path(),
            snapshot_path=None if snapshot is None else snapshot.snapshot_path,
            manifest_path=None if snapshot is None else snapshot.manifest_path,
            report_path=None,
            frame_count=0,
            history_count=0,
            summary_count=0,
            last_messages=(),
            error_count=0,
            warning_count=0,
            model_name=None if model_summary is None else model_summary.model_name,
            current_action=action_text,
        ).append_message(action_text)
        self._active_job_record_id = record.record_id
        return self._put_job_record(record)

    def _register_snapshot_record(self, snapshot: JobSnapshot, *, status: str, message: str) -> GuiJobRecord:
        """为 snapshot 相关动作登记一条非运行记录。"""

        timestamp = create_job_timestamp()
        record = GuiJobRecord(
            record_id=uuid4().hex,
            display_name=build_job_display_name(
                model_name=snapshot.model_name,
                step_name=self._selected_run_step_name(),
                snapshot_path=snapshot.snapshot_path,
            ),
            step_name=self._selected_run_step_name(),
            status=status,
            created_at=timestamp,
            started_at=None,
            finished_at=timestamp,
            results_path=snapshot.results_path,
            export_path=None,
            snapshot_path=snapshot.snapshot_path,
            manifest_path=snapshot.manifest_path,
            report_path=None,
            frame_count=0,
            history_count=0,
            summary_count=0,
            last_messages=(),
            error_count=0,
            warning_count=0,
            model_name=snapshot.model_name,
            current_action=message,
        ).append_message(message)
        return self._put_job_record(record)

    def _append_active_job_message(self, text: str) -> None:
        """将运行中的监视消息回写到当前活动记录。"""

        if self._active_task is None or self._active_task.task_name not in {"run_job", "run_last_snapshot"}:
            return
        active_record = self._job_records.get(self._active_job_record_id)
        if active_record is None:
            return
        self._put_job_record(active_record.append_message(text))

    def _build_job_report_path(self, record: GuiJobRecord, report: JobExecutionReport) -> Path:
        """为完成的 Job 报告构造正式路径。"""

        if record.snapshot_path is not None:
            return record.snapshot_path.with_suffix(".report.json")
        if report.results_path is not None:
            return report.results_path.with_suffix(".report.json")
        base_dir = Path.cwd() / ".pyfem_snapshots"
        return base_dir / f"{record.record_id}.report.json"

    def _write_job_report_file(self, record: GuiJobRecord, report: JobExecutionReport) -> Path:
        """将 JobExecutionReport 写为可回看的正式报告文件。"""

        report_path = self._build_job_report_path(record, report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model_name": report.model_name,
            "job_name": report.job_name,
            "step_name": report.step_name,
            "procedure_type": report.procedure_type,
            "results_backend": report.results_backend,
            "results_path": None if report.results_path is None else str(report.results_path),
            "export_format": report.export_format,
            "export_path": None if report.export_path is None else str(report.export_path),
            "frame_count": report.frame_count,
            "history_count": report.history_count,
            "summary_count": report.summary_count,
            "monitor_messages": list(report.monitor_messages),
        }
        report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return report_path

    def _finalize_active_job_record(self, report: JobExecutionReport) -> None:
        """用正式运行报告更新当前活动记录。"""

        record = self._job_records.get(self._active_job_record_id)
        snapshot = self.shell.state.last_run_snapshot
        if record is None:
            timestamp = create_job_timestamp()
            record = GuiJobRecord(
                record_id=uuid4().hex,
                display_name=build_job_display_name(
                    model_name=report.model_name,
                    step_name=report.step_name,
                    job_name=report.job_name,
                    snapshot_path=None if snapshot is None else snapshot.snapshot_path,
                ),
                step_name=report.step_name,
                status="completed",
                created_at=timestamp,
                started_at=timestamp,
                finished_at=timestamp,
                results_path=report.results_path,
                export_path=report.export_path,
                snapshot_path=None if snapshot is None else snapshot.snapshot_path,
                manifest_path=None if snapshot is None else snapshot.manifest_path,
                report_path=None,
                frame_count=report.frame_count,
                history_count=report.history_count,
                summary_count=report.summary_count,
                last_messages=(),
                error_count=0,
                warning_count=0,
                model_name=report.model_name,
                job_name=report.job_name,
                procedure_type=report.procedure_type,
                results_backend=report.results_backend,
                export_format=report.export_format,
                current_action=f"Job completed: {report.step_name}",
            )
        if not record.last_messages:
            for message in report.monitor_messages:
                record = record.append_message(message)
        updated_record = replace(
            record,
            display_name=build_job_display_name(
                model_name=report.model_name,
                step_name=report.step_name,
                job_name=report.job_name,
                snapshot_path=record.snapshot_path or (None if snapshot is None else snapshot.snapshot_path),
            ),
            step_name=report.step_name,
            status="completed",
            finished_at=create_job_timestamp(),
            results_path=report.results_path,
            export_path=report.export_path,
            snapshot_path=record.snapshot_path or (None if snapshot is None else snapshot.snapshot_path),
            manifest_path=record.manifest_path or (None if snapshot is None else snapshot.manifest_path),
            frame_count=report.frame_count,
            history_count=report.history_count,
            summary_count=report.summary_count,
            model_name=report.model_name,
            job_name=report.job_name,
            procedure_type=report.procedure_type,
            results_backend=report.results_backend,
            export_format=report.export_format,
            current_action=f"Job completed: {report.step_name}",
        )
        updated_record = updated_record.append_message(
            f"Job completed: step={report.step_name}, frames={report.frame_count}, histories={report.history_count}, summaries={report.summary_count}"
        )
        report_path = self._write_job_report_file(updated_record, report)
        self._put_job_record(replace(updated_record, report_path=report_path))

    def _mark_active_job_failed(self, message: str, *, status: str = "failed") -> None:
        """在后台任务失败或终止时更新当前活动记录。"""

        record = self._job_records.get(self._active_job_record_id)
        if record is None:
            return
        self._put_job_record(
            replace(
                record,
                status=status,
                finished_at=create_job_timestamp(),
                current_action=message,
            )
        )

    def _refresh_job_dialogs(self) -> None:
        """统一刷新 Job Center、Monitor 与 Diagnostics 弹窗。"""

        records = self._job_records_snapshot()
        if self._job_center_dialog is not None:
            self._job_center_dialog.set_records(records, active_record_id=self._active_job_record_id)
        if self._job_monitor_dialog is not None:
            monitor_record_id = self._job_monitor_dialog.current_record_id()
            record = self._resolve_job_record(monitor_record_id)
            if record is None:
                self._job_monitor_dialog.set_empty_state("There is no active or completed job to monitor yet.")
            else:
                self._job_monitor_dialog.set_record(record)
        if self._job_diagnostics_dialog is not None:
            self._job_diagnostics_dialog.set_snapshot(self._build_job_diagnostics_snapshot())

    def _create_job_center_dialog(self) -> JobCenterDialog:
        """构建 Job Center 并接入正式动作。"""

        dialog = JobCenterDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.writeInputRequested.connect(self._write_inp_snapshot)
        dialog.runRequested.connect(self.run_job)
        dialog.runLastSnapshotRequested.connect(self._run_last_snapshot)
        dialog.monitorRequested.connect(self._open_job_monitor_dialog)
        dialog.openResultsRequested.connect(self._open_results_for_record)
        dialog.openManifestRequested.connect(self._open_snapshot_manifest)
        dialog.openReportRequested.connect(self._open_job_report)
        dialog.saveAsDerivedCaseRequested.connect(self._save_as_derived_case)
        dialog.rerunRequested.connect(self._run_last_snapshot)
        dialog.removeRecordRequested.connect(self._remove_job_record)
        return dialog

    def _create_job_monitor_dialog(self) -> JobMonitorDialog:
        """构建 Job Monitor 对话框。"""

        dialog = JobMonitorDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.openResultsRequested.connect(self._open_results_for_record)
        dialog.terminateRequested.connect(
            lambda _record_id=None: self._show_command_unavailable("Terminate Job", "当前后端尚未提供正式的终止任务主线。")
        )
        return dialog

    def _create_job_diagnostics_dialog(self) -> JobDiagnosticsDialog:
        """构建 Job Diagnostics 对话框。"""

        dialog = JobDiagnosticsDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        return dialog

    def _open_job_center_dialog(self) -> None:
        """打开 Job Center 总入口。"""

        dialog = self._show_property_dialog(
            "_job_center_dialog",
            self._create_job_center_dialog,
            refresh_callback=lambda dlg: dlg.set_records(self._job_records_snapshot(), active_record_id=self._active_job_record_id),
        )
        if isinstance(dialog, JobCenterDialog):
            self._job_center_dialog = dialog

    def _open_job_monitor_dialog(self, record_id: object | None = None) -> None:
        """打开当前运行或最近一次记录的 Monitor。"""

        target_record = self._resolve_job_record(record_id)
        dialog = self._show_property_dialog(
            "_job_monitor_dialog",
            self._create_job_monitor_dialog,
            refresh_callback=lambda dlg: dlg.set_record(target_record),
        )
        if isinstance(dialog, JobMonitorDialog):
            self._job_monitor_dialog = dialog
            if target_record is None:
                dialog.set_empty_state("There is no active or completed job to monitor yet.")

    def _open_job_diagnostics_dialog(self) -> None:
        """打开 Diagnostics 摘要窗口。"""

        dialog = self._show_property_dialog(
            "_job_diagnostics_dialog",
            self._create_job_diagnostics_dialog,
            refresh_callback=lambda dlg: dlg.set_snapshot(self._build_job_diagnostics_snapshot()),
        )
        if isinstance(dialog, JobDiagnosticsDialog):
            self._job_diagnostics_dialog = dialog

    def _open_results_for_record(self, record_id: object | None = None) -> bool:
        """按记录中的结果路径打开结果。"""

        record = self._resolve_job_record(record_id)
        if record is None:
            self._show_command_unavailable("Open Results", "当前没有可打开结果的 Job 记录。")
            return False
        if record.results_path is None:
            self._show_command_unavailable("Open Results", "所选 Job 记录尚未生成 results_path。")
            return False
        if not record.results_path.exists():
            self._show_command_unavailable("Open Results", f"结果文件不存在: {record.results_path}")
            return False
        return self.open_results_from_path(record.results_path, auto_display_mode=DISPLAY_MODE_CONTOUR_DEFORMED)

    def _open_job_report(self, record_id: object | None = None) -> None:
        """打开所选记录的正式运行报告。"""

        try:
            record = self._resolve_job_record(record_id)
            if record is None:
                self._show_command_unavailable("Open Report", "当前没有可打开报告的 Job 记录。")
                return
            if record.report_path is not None and record.report_path.exists():
                report_text = record.report_path.read_text(encoding="utf-8")
                self._show_text_details(title=f"Job Report: {record.display_name}", text=report_text)
                return
            report = self.shell.state.last_job_report
            if report is None:
                self._show_command_unavailable("Open Report", "当前没有正式报告文件，也没有可回看的最近运行摘要。")
                return
            fallback_text = json.dumps(
                {
                    "model_name": report.model_name,
                    "job_name": report.job_name,
                    "step_name": report.step_name,
                    "procedure_type": report.procedure_type,
                    "results_backend": report.results_backend,
                    "results_path": None if report.results_path is None else str(report.results_path),
                    "export_format": report.export_format,
                    "export_path": None if report.export_path is None else str(report.export_path),
                    "frame_count": report.frame_count,
                    "history_count": report.history_count,
                    "summary_count": report.summary_count,
                    "monitor_messages": list(report.monitor_messages),
                },
                ensure_ascii=False,
                indent=2,
            )
            self._show_text_details(title=f"Job Report: {record.display_name}", text=fallback_text)
        except Exception as error:
            self._handle_error("Open Report", error)

    def _remove_job_record(self, record_id: object | None = None) -> None:
        """仅从 GUI 历史中移除一条 Job 记录。"""

        record = self._resolve_job_record(record_id)
        if record is None:
            return
        self._job_records.remove(record.record_id)
        if self._active_job_record_id == record.record_id:
            self._active_job_record_id = None
        self._refresh_job_dialogs()

    def _open_results_output_entry(self, record_id: object | None = None) -> None:
        """以正式结果产物入口打开最近的结果、报告或 manifest。"""

        record = self._resolve_job_record(record_id)
        if record is None:
            self._show_command_unavailable("Results / Output", "当前没有 Job 记录，也没有可打开的运行产物。")
            return
        if record.results_path is not None and record.results_path.exists() and self._open_results_for_record(record.record_id):
            return
        if record.report_path is not None and record.report_path.exists():
            self._open_job_report(record.record_id)
            return
        if record.manifest_path is not None and record.manifest_path.exists():
            self._open_snapshot_manifest(record.record_id)
            return
        detail_lines = [
            f"display_name = {record.display_name}",
            f"results_path = {record.results_path or '-'}",
            f"report_path = {record.report_path or '-'}",
            f"manifest_path = {record.manifest_path or '-'}",
            f"snapshot_path = {record.snapshot_path or '-'}",
        ]
        self._show_text_details(title="Results / Output", text="\n".join(detail_lines))

    def _build_job_diagnostics_snapshot(self) -> JobDiagnosticsSnapshot:
        """构建 Diagnostics 对话框消费的摘要对象。"""

        headline = "Diagnostics is ready."
        status_text = "Job module status is available."
        problem_lines: list[str] = []
        recommendation_lines: list[str] = []
        error_lines: list[str] = []
        warning_lines: list[str] = []
        artifact_lines: list[str] = []
        run_ready = self.shell.state.opened_model is not None
        latest_record = self._job_records.latest()

        if self.shell.state.opened_model is None:
            headline = "No model is currently loaded."
            status_text = "Load a model before submitting a new job."
            problem_lines.append("当前未加载模型，无法提交新的 Job。")
            recommendation_lines.append("先加载模型。")
            run_ready = False
        else:
            try:
                model = self.shell.clone_loaded_model()
                run_issues = collect_run_capability_issues(model)
                export_issues = collect_export_capability_issues(model)
            except Exception as error:  # noqa: BLE001
                run_issues = ()
                export_issues = ()
                problem_lines.append(f"无法构建当前模型诊断: {error}")
                run_ready = False
            else:
                if run_issues:
                    run_ready = False
                    headline = "Current model is not ready to run."
                    status_text = f"Detected {len(run_issues)} run capability issue(s)."
                    for issue in run_issues[:5]:
                        problem_lines.append(f"[{issue.severity}] {issue.code}: {issue.message}")
                    recommendation_lines.append("先检查当前 step。")
                    recommendation_lines.append("先检查边界 / 载荷 / 输出请求。")
                if export_issues:
                    warning_lines.append(f"检测到 {len(export_issues)} 个导出相关问题，可能影响结果或后处理入口。")
                    recommendation_lines.append("先检查 results 路径与输出请求。")

        if not self.results_path_edit.text().strip():
            problem_lines.append("当前 results 路径为空。")
            recommendation_lines.append("先检查 results 路径。")
            run_ready = False
        if self.export_vtk_checkbox.isChecked() and not self.vtk_path_edit.text().strip():
            warning_lines.append("当前已勾选导出 VTK，但 VTK 路径为空。")
            recommendation_lines.append("先检查 VTK 路径。")

        if latest_record is None:
            problem_lines.append("当前 GUI 会话还没有 Job 记录。")
            recommendation_lines.append("先写 inp。")
            recommendation_lines.append("先运行当前模型。")
        else:
            artifact_lines.extend(
                (
                    f"latest_status = {latest_record.status}",
                    f"results_path = {latest_record.results_path or '-'}",
                    f"export_path = {latest_record.export_path or '-'}",
                    f"snapshot_path = {latest_record.snapshot_path or '-'}",
                    f"manifest_path = {latest_record.manifest_path or '-'}",
                    f"report_path = {latest_record.report_path or '-'}",
                )
            )
            if latest_record.status in FAILED_JOB_STATUSES:
                headline = "Latest job failed or terminated."
                status_text = f"Latest record ended with status: {latest_record.status}"
                problem_lines.append(f"最近一次运行在 step {latest_record.step_name} 失败或终止。")
                recommendation_lines.append("先打开 Monitor。")
                recommendation_lines.append("先打开 Report。")
            if latest_record.manifest_path is None:
                warning_lines.append("最近一次 Job 记录缺少 manifest 路径。")
                recommendation_lines.append("先打开 manifest。")
            if latest_record.snapshot_path is None:
                warning_lines.append("最近一次 Job 记录缺少 snapshot 路径。")
            if latest_record.results_path is None:
                warning_lines.append("最近一次 Job 记录缺少 results 路径。")
            buckets = bucketize_job_messages(latest_record.last_messages)
            error_lines.extend(buckets.error_messages[-5:])
            warning_lines.extend(buckets.warning_messages[-5:])
            if latest_record.status in RUNNING_JOB_STATUSES:
                headline = "A job is currently running."
                status_text = f"Current status: {latest_record.status}"
                recommendation_lines.append("如需观察进度，请打开 Monitor。")

        if not recommendation_lines:
            recommendation_lines.append("当前可以直接进入 Job Center 或 Results / Output。")
        if not problem_lines:
            problem_lines.append("当前未发现阻止运行的明确问题。")

        return JobDiagnosticsSnapshot(
            headline=headline,
            run_ready=run_ready,
            status_text=status_text,
            problem_lines=tuple(problem_lines),
            recommendation_lines=tuple(recommendation_lines),
            error_lines=tuple(error_lines),
            warning_lines=tuple(warning_lines),
            artifact_lines=tuple(artifact_lines),
            latest_record_id=None if latest_record is None else latest_record.record_id,
        )

    def _show_property_dialog(
        self,
        dialog_name: str,
        factory: Callable[[], QDialog],
        *,
        changed_handler: Callable[[str, object, str], None] | None = None,
        refresh_callback: Callable[[QDialog], None] | None = None,
    ) -> QDialog:
        """按名称显示并跟踪管理器或操作弹窗。"""

        dialog = getattr(self, dialog_name)
        if dialog is None:
            dialog = factory()
            dialog.destroyed.connect(lambda *_args: self._clear_tracked_dialog(dialog_name, dialog))
            if hasattr(dialog, "modelChanged") and changed_handler is not None:
                dialog.modelChanged.connect(changed_handler)
            setattr(self, dialog_name, dialog)
        if refresh_callback is not None:
            refresh_callback(dialog)
        elif hasattr(dialog, "refresh"):
            dialog.refresh()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def _open_material_manager(self) -> None:
        """打开材料管理器。"""

        dialog = self._show_property_dialog(
            "_material_manager_dialog",
            lambda: MaterialManagerDialog(self, self.model_edit_presenter),
            changed_handler=self._on_property_model_changed,
        )
        if isinstance(dialog, MaterialManagerDialog):
            self._material_manager_dialog = dialog

    def _open_section_manager(self) -> None:
        """打开截面管理器。"""

        dialog = self._show_property_dialog(
            "_section_manager_dialog",
            lambda: SectionManagerDialog(self, self.model_edit_presenter),
            changed_handler=self._on_property_model_changed,
        )
        if isinstance(dialog, SectionManagerDialog):
            self._section_manager_dialog = dialog

    def _open_assign_section_dialog(self) -> None:
        """打开正式的截面分配弹窗。"""

        current_entry = self.navigation_panel.current_model_entry()
        assignment_context = self.model_edit_presenter.build_section_assignment_context(
            None if current_entry is None else current_entry[0],
            None if current_entry is None else current_entry[1],
        )
        dialog = self._show_property_dialog(
            "_assign_section_dialog",
            lambda: AssignSectionDialog(self, self.model_edit_presenter),
            changed_handler=self._on_property_model_changed,
        )
        if isinstance(dialog, AssignSectionDialog):
            dialog.refresh(preferred_context=assignment_context)
            self._assign_section_dialog = dialog

    def _open_load_manager(self) -> None:
        """打开载荷管理器。"""

        current_entry = self.navigation_panel.current_model_entry()
        load_context = self.model_edit_presenter.build_load_edit_context(
            None if current_entry is None else current_entry[0],
            None if current_entry is None else current_entry[1],
        )
        dialog = self._show_property_dialog(
            "_load_manager_dialog",
            lambda: LoadManagerDialog(self, self.model_edit_presenter),
            changed_handler=self._on_load_model_changed,
        )
        if isinstance(dialog, LoadManagerDialog):
            dialog.refresh(preferred_context=load_context)
            self._load_manager_dialog = dialog

    def _open_boundary_manager(self) -> None:
        """打开边界管理器。"""

        current_entry = self.navigation_panel.current_model_entry()
        boundary_context = self.model_edit_presenter.build_boundary_edit_context(
            None if current_entry is None else current_entry[0],
            None if current_entry is None else current_entry[1],
        )
        dialog = self._show_property_dialog(
            "_boundary_manager_dialog",
            lambda: BoundaryManagerDialog(self, self.model_edit_presenter),
            changed_handler=self._on_load_model_changed,
        )
        if isinstance(dialog, BoundaryManagerDialog):
            dialog.refresh(preferred_context=boundary_context)
            self._boundary_manager_dialog = dialog

    def _open_step_manager(self) -> None:
        """打开步骤管理器。"""

        current_entry = self.navigation_panel.current_model_entry()
        selected_name = None
        if current_entry is not None and current_entry[1] not in {None, ""}:
            try:
                resolved_kind = self.model_edit_presenter.resolve_kind(str(current_entry[0]), str(current_entry[1]))
            except Exception:
                resolved_kind = str(current_entry[0])
            if resolved_kind == "step":
                selected_name = str(current_entry[1])
        dialog = self._show_property_dialog(
            "_step_manager_dialog",
            lambda: StepManagerDialog(self, self.model_edit_presenter),
            changed_handler=self._on_step_model_changed,
            refresh_callback=lambda widget: widget.refresh(selected_name=selected_name),
        )
        if isinstance(dialog, StepManagerDialog):
            self._step_manager_dialog = dialog

    def _edit_selected_model_object(self) -> None:
        current_entry = self.navigation_panel.current_model_entry()
        if current_entry is None:
            self._set_status("当前没有可编辑的模型对象。")
            return
        kind, name = current_entry
        self._open_model_edit_dialog(kind, name)

    def _trigger_model_edit_for_kind(self, expected_kind: str) -> None:
        """按期望对象类型触发正式模型编辑动作。"""

        current_entry = self.navigation_panel.current_model_entry()
        if current_entry is None:
            self._show_command_unavailable(f"Edit {expected_kind.title()}", "请先在模型树中选择对象。")
            return
        kind, name = current_entry
        resolved_kind = self.model_edit_presenter.resolve_kind(str(kind), str(name)) if name not in {None, ""} else str(kind)
        if expected_kind == "load":
            if resolved_kind not in {"nodal_load", "distributed_load"}:
                self._show_command_unavailable("Edit Load", "当前选择不是节点载荷或分布载荷。")
                return
        elif resolved_kind != expected_kind:
            self._show_command_unavailable(f"Edit {expected_kind.title()}", f"当前选择不是 {expected_kind}。")
            return
        self._open_model_edit_dialog(resolved_kind, name)

    def _open_step_edit_dialog(self, *, focus_nonlinear: bool) -> None:
        """打开正式 Step 编辑弹窗，并按需聚焦非线性控件。"""

        self._trigger_model_edit_for_kind("step")
        if focus_nonlinear and isinstance(self._active_model_edit_dialog, StepEditDialog):
            self._active_model_edit_dialog.nlgeom_checkbox.setFocus()

    def _open_step_output_controls(self) -> None:
        """按当前上下文进入 Step 相关输出控制路径。"""

        current_entry = self.navigation_panel.current_model_entry()
        if current_entry is not None:
            kind, name = current_entry
            resolved_kind = self.model_edit_presenter.resolve_kind(str(kind), str(name)) if name not in {None, ""} else str(kind)
            if resolved_kind == "output_request":
                self._open_model_edit_dialog("output_request", name)
                return
            if resolved_kind == "step" and name not in {None, ""}:
                step = self.model_edit_presenter.step(str(name))
                if step.output_request_names:
                    self._open_model_edit_dialog("output_request", step.output_request_names[0])
                    return
                self._show_command_unavailable(
                    "Output Controls",
                    f"步骤 {name} 当前没有关联的输出请求。请先在模型树中选择 output_request，或为该步骤补充 output_request_names。",
                )
                return
        self._show_command_unavailable(
            "Output Controls",
            "请先在模型树中选择某个 step 或 output_request，再从 Step 模块进入输出控制。",
        )

    def _open_output_controls_shortcut(self) -> None:
        """兼容旧命令入口，复用正式的 Step 输出控制路径。"""

        self._open_step_output_controls()

    def _refresh_geometry_from_shell(self) -> None:
        """从正式 shell 重新刷新模型几何。"""

        geometry = self.shell.build_viewport_geometry()
        self.viewport_host.show_model_geometry(geometry)
        self._set_status("Geometry refreshed from the formal model path.")
        self._refresh_action_states()

    def _show_text_details(self, *, title: str, text: str) -> None:
        """复用统一详情弹窗展示文本信息。"""

        self.selection_details_dialog.set_content(title=title, text=text)
        self.selection_details_dialog.show()
        self.selection_details_dialog.raise_()
        self.selection_details_dialog.activateWindow()

    def _show_command_unavailable(self, title: str, message: str) -> None:
        """统一展示命令不可用说明。"""

        detail = message.strip() or "当前命令不可用。"
        self._set_status(detail)
        QMessageBox.information(self, title, detail)

    def _show_placeholder_command(self, title: str, message: str) -> None:
        """统一展示占位命令说明。"""

        detail = message.strip() or "暂未正式支持。"
        self._set_status(detail)
        QMessageBox.information(self, title, detail)

    def _run_last_snapshot(self, record_id: object | None = None) -> bool:
        """通过正式 snapshot 主线复跑最近一次快照。"""

        if self._active_task is not None:
            return False
        try:
            latest_snapshot: JobSnapshot | None = None
            if record_id not in {None, ""}:
                record = self._resolve_job_record(record_id)
                if record is not None and record.manifest_path is not None:
                    latest_snapshot, _manifest_text = self.shell.read_snapshot_manifest(record.manifest_path)
            if latest_snapshot is None:
                latest_snapshot = self.shell.latest_snapshot()
            if latest_snapshot is None:
                self._show_command_unavailable("Run Last Snapshot", "当前还没有可复用的 snapshot。")
                return False
            export_vtk = self.export_vtk_checkbox.isChecked()
            vtk_path = self.vtk_path_edit.text().strip() or None
            step_name = self.run_step_combo.currentData()
            self.viewport_host.show_transient_status("Running the latest snapshot through the formal Job Snapshot path.", title="Running Snapshot")
            self._append_log(f"Running latest snapshot: {latest_snapshot.snapshot_path}")
            self._start_job_record(snapshot=latest_snapshot, action_text=f"Running latest snapshot: {latest_snapshot.snapshot_path}")

            def workload(log: Callable[[str], None]) -> JobExecutionReport:
                monitor = TextCallbackJobMonitor(log)
                return self.shell.run_snapshot(
                    latest_snapshot,
                    step_name=step_name,
                    export_vtk=export_vtk,
                    vtk_path=vtk_path,
                    monitor=monitor,
                )

            return self._start_background_task("run_last_snapshot", workload, self._on_job_completed)
        except Exception as error:
            self._handle_error("Run Last Snapshot", error)
            return False

    def _open_snapshot_manifest(self, record_id: object | None = None) -> None:
        """读取并展示最近一次 snapshot manifest。"""

        try:
            record = self._resolve_job_record(record_id)
            if record is not None and record.manifest_path is not None:
                snapshot, manifest_text = self.shell.read_snapshot_manifest(record.manifest_path)
            else:
                snapshot, manifest_text = self.shell.read_latest_snapshot_manifest()
            self._show_text_details(title=f"Snapshot Manifest: {snapshot.snapshot_path.name}", text=manifest_text)
        except Exception as error:
            self._handle_error("Open Snapshot Manifest", error)

    @Slot(str, object, str)
    def _on_property_model_changed(self, kind: str, name: object, operation: str) -> None:
        """响应 Property 管理器的模型更新信号。"""

        normalized_kind = str(kind)
        object_name = None if name in {None, ""} else str(name)
        status_text = f"{normalized_kind} {operation}"
        if object_name is not None:
            status_text = f"{normalized_kind} {operation}: {object_name}"
        self._refresh_model_views_after_change(
            preferred_kind=None if operation == "deleted" else normalized_kind,
            preferred_name=None if operation == "deleted" else object_name,
            status_text=status_text,
            module_name="Property",
        )

    def _on_load_model_changed(self, kind: str, name: object, operation: str) -> None:
        """响应 Load 管理器与编辑弹窗的模型更新信号。"""

        normalized_kind = str(kind)
        object_name = None if name in {None, ""} else str(name)
        status_text = f"{normalized_kind} {operation}"
        if object_name is not None:
            status_text = f"{normalized_kind} {operation}: {object_name}"
        self._refresh_model_views_after_change(
            preferred_kind=None if operation == "deleted" else normalized_kind,
            preferred_name=None if operation == "deleted" else object_name,
            status_text=status_text,
            module_name="Load",
        )

    @Slot(str, object, str)
    def _on_step_model_changed(self, kind: str, name: object, operation: str) -> None:
        """响应 Step 管理器与编辑弹窗的模型更新信号。"""

        normalized_kind = str(kind)
        object_name = None if name in {None, ""} else str(name)
        status_text = f"{normalized_kind} {operation}"
        if object_name is not None:
            status_text = f"{normalized_kind} {operation}: {object_name}"
        self._refresh_model_views_after_change(
            preferred_kind=None if operation == "deleted" else normalized_kind,
            preferred_name=None if operation == "deleted" else object_name,
            status_text=status_text,
            module_name="Step",
        )

    def _refresh_model_views_after_change(
        self,
        *,
        preferred_kind: str | None,
        preferred_name: str | None,
        status_text: str,
        module_name: str,
    ) -> None:
        """在模型发生变更后统一刷新导航、视口和结果状态。"""

        summary = self.shell.build_model_summary()
        snapshot = self.shell.build_model_navigation_snapshot()
        geometry = self.shell.build_viewport_geometry()
        self._current_model_summary = summary
        self._update_model_summary_widgets(summary)
        self._populate_run_step_combo(summary)
        self.navigation_panel.set_model_snapshot(snapshot)
        if preferred_kind is not None and preferred_name is not None:
            self.navigation_panel.select_model_entry(preferred_kind, preferred_name)
        self.viewport_host.show_model_geometry(geometry)
        self.results_browser.clear_results("Model edited. Re-run through Job Snapshot to refresh results.")
        self.navigation_panel.clear_results()
        self._current_view_context = None
        self._current_field_presentation = None
        self._context_variant_selection_by_family.clear()
        self.context_step_combo.clear()
        self.context_frame_combo.clear()
        self.context_field_combo.clear()
        self.context_field_variant_combo.clear()
        self.context_component_combo.clear()
        self._last_probe_series = None
        self.probe_output_edit.setPlainText("")
        self.current_results_value.setText("Model edited; existing results are stale.")
        self.footer_results_label.setText("Results: stale")
        self._set_combo_data(self.module_combo, module_name)
        self._sync_module_toolbox(module_name)
        self._update_viewport_workspace_context()
        self._set_status(status_text)
        self._refresh_action_states()
        self._refresh_job_dialogs()

    def _refresh_model_views_after_edit(self, resolved_kind: str, object_name: str) -> None:
        module_name = (
            "Property"
            if resolved_kind in {"material", "section"}
            else "Load"
            if resolved_kind in {"boundary", "nodal_load", "distributed_load"}
            else "Step"
            if resolved_kind == "step"
            else MODULE_ORDER[0]
        )
        self._refresh_model_views_after_change(
            preferred_kind=resolved_kind,
            preferred_name=object_name,
            status_text=f"{resolved_kind} updated: {object_name}",
            module_name=module_name,
        )

    def _write_inp_snapshot(self) -> None:
        if self.shell.state.opened_model is None:
            return
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            "Write INP",
            str(self.shell.state.opened_model.source_path),
            "INP (*.inp);;All Files (*)",
        )
        if not selected_path:
            return
        try:
            snapshot = self.shell.write_current_model_snapshot(selected_path)
            self._append_log(f"INP snapshot written: {snapshot.snapshot_path}")
            self._set_status(f"INP snapshot written: {snapshot.snapshot_path.name}")
            self._register_snapshot_record(snapshot, status="written", message=f"INP snapshot written: {snapshot.snapshot_path}")
        except Exception as error:
            self._handle_error("Write INP", error)

    def _save_as_derived_case(self) -> None:
        if self.shell.state.opened_model is None:
            return
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save As Derived Case",
            str(self.shell.state.opened_model.source_path),
            "INP (*.inp);;All Files (*)",
        )
        if not selected_path:
            return
        try:
            snapshot = self.shell.save_current_model_as_derived_case(selected_path)
            summary = self.shell.build_model_summary()
            self._current_model_summary = summary
            self._update_model_summary_widgets(summary)
            self.navigation_panel.set_model_snapshot(self.shell.build_model_navigation_snapshot())
            self.results_path_edit.setText(str(snapshot.results_path))
            self.vtk_path_edit.setText(str(self.shell.build_default_vtk_path()))
            self._append_log(f"Derived case saved: {snapshot.snapshot_path}")
            self._set_status(f"Derived case saved: {snapshot.snapshot_path.name}")
            self._register_snapshot_record(snapshot, status="derived_case", message=f"Derived case saved: {snapshot.snapshot_path}")
        except Exception as error:
            self._handle_error("Save As Derived Case", error)

    def _on_module_combo_changed(self) -> None:
        module_name = self.module_combo.currentData() or MODULE_ORDER[0]
        self._sync_module_toolbox(module_name)
        self._update_viewport_workspace_context()
        self.command_registry.refresh()

    def _on_context_step_changed(self) -> None:
        if self._syncing_context_controls:
            return
        step_name = self.context_step_combo.currentData()
        if isinstance(step_name, str):
            self.results_browser.select_step(step_name)

    def _on_context_frame_changed(self) -> None:
        if self._syncing_context_controls:
            return
        frame_id = self.context_frame_combo.currentData()
        if isinstance(frame_id, int):
            self.results_browser.select_frame(frame_id)

    def _on_context_field_changed(self) -> None:
        if self._syncing_context_controls:
            return
        family_key = self._selected_context_family_key()
        if family_key is None:
            return
        variant_key = self._context_variant_selection_by_family.get(family_key, COMMON_VARIANT_KEY)
        self._context_variant_selection_by_family[family_key] = variant_key
        field_name = self._resolve_context_field_name(family_key=family_key, variant_key=variant_key)
        if isinstance(field_name, str):
            self._sync_results_context_controls(
                step_name=self.results_browser.current_step_name,
                frame_id=self.results_browser.current_frame_id,
                field_name=field_name,
            )
            self.results_browser.select_field(field_name)

    def _on_context_field_variant_changed(self) -> None:
        if self._syncing_context_controls:
            return
        family_key = self._selected_context_family_key()
        variant_key = self._selected_context_variant_key()
        if family_key is None or variant_key is None:
            return
        self._context_variant_selection_by_family[family_key] = variant_key
        field_name = self._resolve_context_field_name(family_key=family_key, variant_key=variant_key)
        if isinstance(field_name, str):
            self.results_browser.select_field(field_name)

    def _on_context_component_changed(self) -> None:
        if self._syncing_context_controls:
            return
        component_name = self.context_component_combo.currentData()
        self.viewport_host.set_component_name(component_name if isinstance(component_name, str) else None)

    def _on_display_mode_changed(self) -> None:
        if self._syncing_context_controls:
            return
        display_mode = self.display_mode_combo.currentData() or DISPLAY_MODE_UNDEFORMED
        self.viewport_host.set_display_mode(display_mode)
        self._sync_display_actions(display_mode)
        self._update_viewport_workspace_context()

    @Slot(object)
    def _on_viewport_component_changed(self, component_name: object) -> None:
        if isinstance(component_name, str):
            self._syncing_context_controls = True
            try:
                self._set_combo_data(self.context_component_combo, component_name)
            finally:
                self._syncing_context_controls = False
        self._refresh_probe_controls()
        self._update_viewport_workspace_context()
        self._update_probe_context_summary()

    def _focus_probe_panel(self) -> None:
        self._refresh_probe_controls()
        self._update_probe_context_summary()
        self.viewport_host.show_command_prompt("Probe 模式已开启：请选择探测类型、目标与分量，执行后提示条会自动收起。")
        self.probe_dialog.show()
        self.probe_dialog.raise_()
        self.probe_dialog.activateWindow()

    def _update_probe_context_summary(self) -> None:
        """刷新 probe 弹窗顶部的上下文摘要。"""

        step_name = self.results_browser.current_step_name
        frame_id = self.results_browser.current_frame_id
        field_name = self.results_browser.current_field_name
        if step_name is None or frame_id is None or field_name is None:
            self.probe_dialog.set_context_summary("当前没有可用于 probe 的结果场。")
            return
        variant_key = self._selected_context_variant_key()
        selection = None if self._current_field_presentation is None else self._current_field_presentation.describe_selection(
            field_name,
            variant_key=variant_key,
            prefer_common=variant_key == COMMON_VARIANT_KEY,
        )
        if selection is None:
            self.probe_dialog.set_context_summary(f"step={step_name} | frame={frame_id} | field={field_name}")
            return
        self.probe_dialog.set_context_summary(
            f"step={step_name} | frame={frame_id} | result={selection.family_display_name} | variant={selection.variant_display_name} | field={field_name}"
        )

    def _refresh_probe_controls(self) -> None:
        self.probe_target_combo.blockSignals(True)
        self.probe_component_combo.blockSignals(True)
        self.probe_target_combo.clear()
        self.probe_component_combo.clear()
        compatibility = None
        if self._current_view_context is not None:
            step_name = self.results_browser.current_step_name
            frame_id = self.results_browser.current_frame_id
            field_name = self.results_browser.current_field_name
            if step_name is not None and frame_id is not None and field_name is not None:
                compatibility = resolve_probe_compatibility(
                    self._current_view_context.results_facade,
                    step_name,
                    frame_id,
                    field_name,
                    self.probe_kind_combo.currentData(),
                )
        if compatibility is None or compatibility.field_name is None:
            self.probe_status_value.setText("当前结果与所选 probe 类型不兼容。")
            self.probe_output_edit.setPlainText("")
            self.run_probe_button.setEnabled(False)
            self.export_probe_button.setEnabled(self._last_probe_series is not None)
            self.probe_target_combo.blockSignals(False)
            self.probe_component_combo.blockSignals(False)
            return
        for target_key in compatibility.target_keys:
            self.probe_target_combo.addItem(str(target_key), str(target_key))
        component_names = compatibility.component_names
        for component_name in component_names:
            self.probe_component_combo.addItem(str(component_name), str(component_name))
        if self.viewport_host.current_component_name is not None:
            self._set_combo_data(self.probe_component_combo, self.viewport_host.current_component_name)
        self.probe_status_value.setText(
            f"{compatibility.probe_kind} -> 正式字段 {compatibility.field_name}, 目标数 {len(compatibility.target_keys)}"
        )
        self.run_probe_button.setEnabled(self.probe_target_combo.count() > 0)
        self.export_probe_button.setEnabled(self._last_probe_series is not None)
        self.probe_target_combo.blockSignals(False)
        self.probe_component_combo.blockSignals(False)
        self._update_probe_context_summary()

    def _run_probe_from_controls(self) -> None:
        if self._current_view_context is None:
            return
        step_name = self.results_browser.current_step_name
        frame_id = self.results_browser.current_frame_id
        field_name = self.results_browser.current_field_name
        if step_name is None or frame_id is None or field_name is None:
            return
        compatibility = resolve_probe_compatibility(
            self._current_view_context.results_facade,
            step_name,
            frame_id,
            field_name,
            self.probe_kind_combo.currentData(),
        )
        if compatibility.field_name is None:
            self.probe_output_edit.setPlainText(compatibility.message or "Probe is unavailable for the current selection.")
            return
        target_key = self.probe_target_combo.currentData() or self.probe_target_combo.currentText().strip()
        component_name = self.probe_component_combo.currentData()
        if not isinstance(component_name, str):
            component_text = self.probe_component_combo.currentText().strip()
            component_name = component_text or None
        if component_name is None and compatibility.component_names and self.viewport_host.current_component_name is not None:
            component_name = self.viewport_host.current_component_name
        probe_service = self._current_view_context.results_facade.probe()
        if self.probe_kind_combo.currentData() == PROBE_KIND_NODE:
            series = probe_service.node_component(step_name, str(target_key), component_name, field_name=compatibility.field_name)
        elif self.probe_kind_combo.currentData() == PROBE_KIND_ELEMENT:
            series = probe_service.element_component(step_name, str(target_key), component_name, field_name=compatibility.field_name)
        elif self.probe_kind_combo.currentData() == PROBE_KIND_INTEGRATION_POINT:
            series = probe_service.integration_point_component(step_name, str(target_key), component_name, field_name=compatibility.field_name)
        else:
            series = probe_service.averaged_node_component(step_name, str(target_key), component_name, field_name=compatibility.field_name)
        self._last_probe_series = series
        last_value = series.values[-1] if series.values else "-"
        metadata = dict(series.metadata)
        self.probe_output_edit.setPlainText(
            "\n".join(
                (
                    f"source={series.source_name}",
                    f"field={metadata.get('field_name', '-')}",
                    f"target={metadata.get('resolved_target_key', metadata.get('target_key', '-'))}",
                    f"component={metadata.get('component_name') or '-'}",
                    f"axis={series.axis_kind}",
                    f"points={len(series.axis_values)}",
                    f"last={last_value}",
                    f"metadata={metadata}",
                )
            )
        )
        self.probe_status_value.setText(f"Probe completed: {series.source_name}")
        self.export_probe_button.setEnabled(True)
        self._set_status(f"Probe completed for {series.source_name}.")
        self.viewport_host.hide_command_prompt()

    def _export_probe_from_dialog(self) -> None:
        if self._last_probe_series is None or self._current_view_context is None:
            return
        step_names = tuple(self._current_view_context.results_facade.list_steps())
        current_step_name = self.results_browser.current_step_name
        self.export_probe_dialog.set_values(
            step_names=step_names,
            current_step_name=current_step_name,
            path_text=self.results_path_edit.text().strip(),
            description="导出当前 probe 序列为正式 CSV 文件。",
        )
        if self.export_probe_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._export_probe_series_to_path(self.export_probe_dialog.selected_path())
        self.viewport_host.hide_command_prompt()

    def _export_probe_series_to_path(self, path: Path) -> Path | None:
        if self._last_probe_series is None or self._current_view_context is None:
            return None
        export_path = self._current_view_context.results_facade.probe().export_csv(self._last_probe_series, path)
        self._append_log(f"Probe CSV exported: {export_path}")
        self._set_status(f"Probe CSV exported: {export_path.name}")
        return export_path

    def _show_selection_details_dialog(self) -> None:
        """按需弹出当前结果选择详情。"""

        detail_text = self.navigation_panel.current_results_details_text()
        title = detail_text.splitlines()[0].strip() or "Selection Details"
        self._show_text_details(title=title, text=detail_text)

    def _show_legend_settings_dialog(self) -> None:
        """按需弹出 legend 高级设置。"""

        locked, min_value, max_value, colormap_name = self.viewport_host.legend_settings()
        unit_text, range_text = self.viewport_host.legend_summary()
        self.legend_settings_dialog.set_values(
            locked=locked,
            min_value=min_value,
            max_value=max_value,
            unit_label=unit_text.removeprefix("unit="),
            range_text=range_text,
            colormap_name=colormap_name,
            colormap_options=self.viewport_host.legend_colormap_options(),
        )
        self.legend_settings_dialog.show()
        self.legend_settings_dialog.raise_()
        self.legend_settings_dialog.activateWindow()

    def _apply_legend_dialog_settings(self, locked: bool, min_value: object, max_value: object, colormap_name: str) -> None:
        """将 legend 弹窗中的设置写回 viewport。"""

        self.viewport_host.set_legend_controls(
            locked=locked,
            min_value=min_value if isinstance(min_value, (int, float)) else None,
            max_value=max_value if isinstance(max_value, (int, float)) else None,
            colormap_name=colormap_name,
        )

    def load_model_from_editor(self) -> GuiModelSummary | None:
        input_path = self.input_path_edit.text().strip()
        if not input_path:
            self._handle_error("Load Model", "Please provide an input path first.")
            return None
        try:
            summary = self.shell.open_model(input_path)
            snapshot = self.shell.build_model_navigation_snapshot()
            geometry = self.shell.build_viewport_geometry()
        except Exception as error:
            self._handle_error("Load Model", error)
            return None
        self._current_model_summary = summary
        self._update_model_summary_widgets(summary)
        self._populate_run_step_combo(summary)
        self.navigation_panel.set_model_snapshot(snapshot)
        self.navigation_panel.set_workspace_context(self.module_combo.currentData() or MODULE_ORDER[0], use_results_tab=False)
        self.viewport_host.show_model_geometry(geometry)
        self.results_browser.clear_results("Model loaded. Results are not opened yet.")
        self.navigation_panel.clear_results()
        self._current_view_context = None
        self._current_field_presentation = None
        self._context_variant_selection_by_family.clear()
        self.context_step_combo.clear()
        self.context_frame_combo.clear()
        self.context_field_combo.clear()
        self.context_field_variant_combo.clear()
        self.context_component_combo.clear()
        self._last_probe_series = None
        self.probe_output_edit.setPlainText("")
        self.results_path_edit.setText(str(self.shell.build_default_results_path()))
        self.vtk_path_edit.setText(str(self.shell.build_default_vtk_path()))
        self._set_results_summary_text(f"model={summary.model_name}, parts={summary.part_count}, steps={len(summary.step_names)}")
        self.current_results_value.setText("Mesh only")
        self.footer_results_label.setText("Results: -")
        self._set_combo_data(self.module_combo, MODULE_ORDER[0])
        self._sync_module_toolbox(MODULE_ORDER[0])
        self._update_viewport_workspace_context()
        self._apply_task_state("success", f"Model loaded: {summary.model_name}")
        self._refresh_job_dialogs()
        return summary

    def open_results_from_editor(self) -> bool:
        results_path = self.results_path_edit.text().strip() or None
        return self.open_results_from_path(results_path)

    def open_results_from_path(
        self,
        results_path: str | Path | None,
        *,
        auto_display_mode: str | None = None,
    ) -> bool:
        if self._active_task is not None:
            return False
        path_text = None if results_path is None else str(results_path)
        self._pending_results_display_mode = auto_display_mode
        self.viewport_host.show_transient_status("Reading results through ResultsFacade and preparing browser / viewport context.", title="Opening Results")
        self._append_log(f"Opening results: {path_text or '(default)'}")

        def workload(log: Callable[[str], None]) -> GuiResultsLoadResult:
            log(f"Loading results view: {path_text or '(default)'}")
            return self.shell.load_results_view(path_text)

        return self._start_background_task("open_results", workload, self._on_results_loaded)

    def run_job(self) -> bool:
        if self._active_task is not None:
            return False
        results_path = self.results_path_edit.text().strip() or None
        vtk_path = self.vtk_path_edit.text().strip() or None
        step_name = self.run_step_combo.currentData()
        export_vtk = self.export_vtk_checkbox.isChecked()
        self.viewport_host.show_transient_status("Running analysis in background. Results will be reopened automatically when the job finishes.", title="Job Running")
        self._append_log("Background solve task started.")
        self._start_job_record(snapshot=None, action_text="Background solve task started.")

        def workload(log: Callable[[str], None]) -> JobExecutionReport:
            monitor = TextCallbackJobMonitor(log)
            return self.shell.submit_job(
                step_name=step_name,
                results_path=results_path,
                export_vtk=export_vtk,
                vtk_path=vtk_path,
                monitor=monitor,
            )

        return self._start_background_task("run_job", workload, self._on_job_completed)

    def export_vtk_results(self, *, step_name_override: str | None = None, vtk_path_override: str | None = None) -> bool:
        if self._active_task is not None:
            return False
        step_name = step_name_override if step_name_override is not None else (self.context_step_combo.currentData() or self.run_step_combo.currentData())
        results_path = self.results_path_edit.text().strip() or None
        vtk_path = vtk_path_override if vtk_path_override is not None else (self.vtk_path_edit.text().strip() or None)
        self.viewport_host.show_transient_status("Exporting current results to VTK.", title="Exporting VTK")
        self._append_log(f"Exporting VTK: {vtk_path or '(default)'}")

        def workload(log: Callable[[str], None]) -> Path:
            log("VTK export started.")
            return self.shell.export_results_vtk(step_name=step_name, results_path=results_path, vtk_path=vtk_path)

        return self._start_background_task("export_vtk", workload, self._on_vtk_exported)

    def _on_job_completed(self, report: JobExecutionReport) -> None:
        self._finalize_active_job_record(report)
        self._append_log(f"Job finished: step={report.step_name}, frames={report.frame_count}, histories={report.history_count}, summaries={report.summary_count}")
        self.results_path_edit.setText(str(report.results_path))
        if report.export_path is not None:
            self.vtk_path_edit.setText(str(report.export_path))
        self._set_results_summary_text(
            f"job={report.step_name}, frames={report.frame_count}, histories={report.history_count}, summaries={report.summary_count}"
        )
        self._pending_follow_up = lambda: self.open_results_from_path(
            report.results_path,
            auto_display_mode=DISPLAY_MODE_CONTOUR_DEFORMED,
        )

    def _on_results_loaded(self, load_result: GuiResultsLoadResult) -> None:
        pending_display_mode = self._pending_results_display_mode
        self._pending_results_display_mode = None
        self._current_view_context = load_result.view_context
        self._current_field_presentation = None
        self._context_variant_selection_by_family.clear()
        self.context_field_combo.clear()
        self.context_field_variant_combo.clear()
        self.results_path_edit.setText(str(load_result.results_path))
        self.footer_results_label.setText(f"Results: {load_result.results_path.name}")
        entries_text = "; ".join(
            f"step={entry.step_name}, frames={entry.frame_count}, histories={entry.history_count}, summaries={entry.summary_count}"
            for entry in load_result.entries
        )
        self._set_results_summary_text(entries_text or "No result entries")
        preferred_step = load_result.entries[0].step_name if load_result.entries else None
        self.results_browser.set_results_facade(load_result.view_context.results_facade, preferred_step_name=preferred_step)
        self.navigation_panel.set_results_facade(load_result.view_context.results_facade, preferred_step_name=preferred_step)
        self.viewport_host.set_results_context(load_result.view_context, preferred_step_name=preferred_step)
        self._set_combo_data(self.module_combo, RESULTS_MODULE_NAME)
        self._sync_module_toolbox(RESULTS_MODULE_NAME)
        self._sync_results_context_controls(
            step_name=self.results_browser.current_step_name,
            frame_id=self.results_browser.current_frame_id,
            field_name=self.results_browser.current_field_name,
        )
        self._update_current_results_text(
            self.results_browser.current_step_name,
            self.results_browser.current_frame_id,
            self.results_browser.current_field_name,
        )
        if pending_display_mode is not None:
            self._set_display_mode_value(pending_display_mode)
        self._refresh_probe_controls()
        self._update_viewport_workspace_context()
        self._apply_task_state("success", f"Results opened: {load_result.results_path.name}")
        self._refresh_job_dialogs()

    def _on_vtk_exported(self, export_path: Path) -> None:
        self.vtk_path_edit.setText(str(export_path))
        self._append_log(f"VTK export finished: {export_path}")
        self._apply_task_state("success", f"VTK export finished: {export_path.name}")

    def _browse_and_load_model(self) -> None:
        selected_path, _ = QFileDialog.getOpenFileName(self, "Open INP", self.input_path_edit.text().strip(), "INP (*.inp);;All Files (*)")
        if selected_path:
            self.input_path_edit.setText(selected_path)
            self.load_model_from_editor()

    def _browse_and_open_results(self) -> None:
        selected_path, _ = QFileDialog.getOpenFileName(self, "Open Results", self.results_path_edit.text().strip(), "JSON (*.json);;All Files (*)")
        if selected_path:
            self.results_path_edit.setText(selected_path)
            self.open_results_from_editor()

    def _browse_and_export_vtk(self) -> None:
        step_names = tuple(self._current_view_context.results_facade.list_steps()) if self._current_view_context is not None else ()
        current_step_name = self.context_step_combo.currentData() if self._current_view_context is not None else None
        self.export_vtk_dialog.set_values(
            step_names=step_names,
            current_step_name=current_step_name if isinstance(current_step_name, str) else None,
            path_text=self.vtk_path_edit.text().strip(),
            description="导出当前结果为 VTK 文件。低频导出参数放入弹窗，不再长期占用主界面。",
        )
        if self.export_vtk_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected_path = str(self.export_vtk_dialog.selected_path())
        self.vtk_path_edit.setText(selected_path)
        self.export_vtk_results(
            step_name_override=self.export_vtk_dialog.selected_step_name(),
            vtk_path_override=selected_path,
        )

    def _handle_error(self, title: str, error: object) -> None:
        message = str(error).strip() or type(error).__name__
        self._apply_task_state("failed", f"{title}: {message}")
        self._append_log(f"{title}: {message}")
        self._set_message_panel_expanded(True)
        self.message_console_panel.show_messages()
    def _start_background_task(
        self,
        task_name: str,
        workload: Callable[[Callable[[str], None]], Any],
        on_success: Callable[[Any], None],
    ) -> bool:
        if self._active_task is not None:
            return False
        thread = QThread(self)
        worker = GuiTaskWorker(task_name, workload)
        worker.moveToThread(thread)
        handle = GuiTaskHandle(task_name=task_name, thread=thread, worker=worker, on_success=on_success)
        self._active_task = handle
        self._is_busy = True
        self._pending_follow_up = None
        worker.started.connect(self._on_task_started)
        worker.log_message.connect(self._append_log)
        worker.succeeded.connect(self._on_task_succeeded)
        worker.failed.connect(self._on_task_failed)
        worker.finished.connect(self._on_task_finished)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._apply_task_state("running", f"Task started: {task_name}")
        thread.start()
        return True

    @Slot(str)
    def _on_task_started(self, task_name: str) -> None:
        self._apply_task_state("running", f"Task started: {task_name}")

    @Slot(str, object)
    def _on_task_succeeded(self, task_name: str, payload: object) -> None:
        if self._is_closing or self._active_task is None or self._active_task.task_name != task_name:
            return
        self._active_task.on_success(payload)

    @Slot(str, str)
    def _on_task_failed(self, task_name: str, message: str) -> None:
        if self._is_closing:
            return
        if task_name == "open_results":
            self._pending_results_display_mode = None
        if task_name in {"run_job", "run_last_snapshot"}:
            self._mark_active_job_failed(message)
        self._handle_error(task_name, message)

    @Slot(str)
    def _on_task_finished(self, task_name: str) -> None:
        handle = self._active_task
        if handle is None or handle.task_name != task_name:
            return
        self._active_task = None
        self._is_busy = False
        if self.task_state == "running":
            self._apply_task_state("success", f"Task finished: {task_name}")
        else:
            self._refresh_action_states()
        follow_up = self._pending_follow_up
        self._pending_follow_up = None
        if task_name in {"run_job", "run_last_snapshot"}:
            self._active_job_record_id = None
            self._refresh_job_dialogs()
        if follow_up is not None and not self._is_closing:
            QTimer.singleShot(0, follow_up)

    def _set_combo_data(self, combo_box: QComboBox, data: object) -> None:
        index = combo_box.findData(data)
        if index >= 0:
            combo_box.setCurrentIndex(index)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._is_closing = True
        self.viewport_host.shutdown()
        self._close_tracked_dialog("_active_model_edit_dialog")
        self._close_tracked_dialog("_boundary_manager_dialog")
        self._close_tracked_dialog("_load_manager_dialog")
        self._close_tracked_dialog("_step_manager_dialog")
        self._close_tracked_dialog("_assign_section_dialog")
        self._close_tracked_dialog("_section_manager_dialog")
        self._close_tracked_dialog("_material_manager_dialog")
        self._close_tracked_dialog("_job_diagnostics_dialog")
        self._close_tracked_dialog("_job_monitor_dialog")
        self._close_tracked_dialog("_job_center_dialog")
        handle = self._active_task
        if handle is not None:
            if handle.task_name in {"run_job", "run_last_snapshot"}:
                self._mark_active_job_failed("Main window closed before the running job finished.", status="terminated")
            handle.thread.quit()
            handle.thread.wait(3000)
            self._active_task = None
            self._is_busy = False
        super().closeEvent(event)








