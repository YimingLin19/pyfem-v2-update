"""定义 Job Center、Monitor 与 Diagnostics 弹窗。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pyfem.gui.job_records import JobDiagnosticsSnapshot, GuiJobRecord, RUNNING_JOB_STATUSES, bucketize_job_messages


def _path_text(path: Path | None) -> str:
    """格式化路径文本。"""

    return "-" if path is None else str(path)


def _exists_text(path: Path | None) -> str:
    """返回产物存在性描述。"""

    return "Yes" if path is not None and path.exists() else "No"


def _status_text(value: object | None) -> str:
    """统一格式化摘要值。"""

    if value in {None, ""}:
        return "-"
    return str(value)


class JobCenterDialog(QDialog):
    """展示 Job 历史记录与正式动作入口。"""

    writeInputRequested = Signal()
    runRequested = Signal()
    runLastSnapshotRequested = Signal(object)
    monitorRequested = Signal(object)
    openResultsRequested = Signal(object)
    openManifestRequested = Signal(object)
    openReportRequested = Signal(object)
    saveAsDerivedCaseRequested = Signal()
    rerunRequested = Signal(object)
    removeRecordRequested = Signal(object)

    COLUMN_HEADERS = (
        "Job",
        "Step",
        "Status",
        "Started",
        "Finished",
        "Results",
        "Export",
        "Frames",
        "Histories",
        "Summaries",
        "Snapshot",
        "Manifest",
        "Report",
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._records_by_id: dict[str, GuiJobRecord] = {}

        self.setWindowTitle("Job Center")
        self.resize(1220, 520)

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        left_panel = QWidget(self)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self.summary_label = QLabel("Recent job records will appear here.", left_panel)
        self.summary_label.setWordWrap(True)
        left_layout.addWidget(self.summary_label)

        self.records_table = QTableWidget(0, len(self.COLUMN_HEADERS), left_panel)
        self.records_table.setHorizontalHeaderLabels(self.COLUMN_HEADERS)
        self.records_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.records_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.records_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.records_table.setAlternatingRowColors(True)
        self.records_table.verticalHeader().setVisible(False)
        self.records_table.horizontalHeader().setStretchLastSection(False)
        self.records_table.setWordWrap(False)
        self.records_table.itemSelectionChanged.connect(self._update_button_states)
        self.records_table.itemDoubleClicked.connect(lambda _item: self._handle_record_activation())
        left_layout.addWidget(self.records_table, 1)

        right_panel = QWidget(self)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self.write_input_button = QPushButton("Write Input", right_panel)
        self.run_button = QPushButton("Run", right_panel)
        self.run_last_snapshot_button = QPushButton("Run Last Snapshot", right_panel)
        self.monitor_button = QPushButton("Monitor", right_panel)
        self.open_results_button = QPushButton("Open Results", right_panel)
        self.open_manifest_button = QPushButton("Open Snapshot Manifest", right_panel)
        self.open_report_button = QPushButton("Open Report", right_panel)
        self.save_as_derived_case_button = QPushButton("Save As Derived Case", right_panel)
        self.rerun_button = QPushButton("Re-run", right_panel)
        self.remove_record_button = QPushButton("Remove Record", right_panel)
        self.close_button = QPushButton("Close", right_panel)

        for button in (
            self.write_input_button,
            self.run_button,
            self.run_last_snapshot_button,
            self.monitor_button,
            self.open_results_button,
            self.open_manifest_button,
            self.open_report_button,
            self.save_as_derived_case_button,
            self.rerun_button,
            self.remove_record_button,
            self.close_button,
        ):
            button.setMinimumWidth(190)
            right_layout.addWidget(button)

        right_layout.addStretch(1)
        root_layout.addWidget(left_panel, 1)
        root_layout.addWidget(right_panel, 0)

        self.write_input_button.clicked.connect(self.writeInputRequested.emit)
        self.run_button.clicked.connect(self.runRequested.emit)
        self.run_last_snapshot_button.clicked.connect(lambda: self.runLastSnapshotRequested.emit(self.selected_record_id()))
        self.monitor_button.clicked.connect(lambda: self.monitorRequested.emit(self.selected_record_id()))
        self.open_results_button.clicked.connect(lambda: self.openResultsRequested.emit(self.selected_record_id()))
        self.open_manifest_button.clicked.connect(lambda: self.openManifestRequested.emit(self.selected_record_id()))
        self.open_report_button.clicked.connect(lambda: self.openReportRequested.emit(self.selected_record_id()))
        self.save_as_derived_case_button.clicked.connect(self.saveAsDerivedCaseRequested.emit)
        self.rerun_button.clicked.connect(lambda: self.rerunRequested.emit(self.selected_record_id()))
        self.remove_record_button.clicked.connect(lambda: self.removeRecordRequested.emit(self.selected_record_id()))
        self.close_button.clicked.connect(self.close)

        self._update_button_states()

    def selected_record_id(self) -> str | None:
        """返回当前表格选中的记录编号。"""

        current_row = self.records_table.currentRow()
        if current_row < 0:
            return None
        item = self.records_table.item(current_row, 0)
        if item is None:
            return None
        raw_record_id = item.data(Qt.ItemDataRole.UserRole)
        return None if raw_record_id in {None, ""} else str(raw_record_id)

    def set_records(self, records: tuple[GuiJobRecord, ...], *, active_record_id: str | None = None) -> None:
        """刷新 Job Center 中显示的记录。"""

        self._records_by_id = {record.record_id: record for record in records}
        self.records_table.setRowCount(len(records))

        for row_index, record in enumerate(records):
            row_values = (
                record.display_name,
                record.step_name,
                record.status,
                _status_text(record.started_at),
                _status_text(record.finished_at),
                _path_text(record.results_path),
                _path_text(record.export_path),
                str(record.frame_count),
                str(record.history_count),
                str(record.summary_count),
                _exists_text(record.snapshot_path),
                _exists_text(record.manifest_path),
                _exists_text(record.report_path),
            )
            for column_index, value in enumerate(row_values):
                item = QTableWidgetItem(value)
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, record.record_id)
                if column_index >= 7:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.records_table.setItem(row_index, column_index, item)

        self.records_table.resizeColumnsToContents()

        selected_row = 0 if records else -1
        if active_record_id not in {None, ""}:
            for row_index, record in enumerate(records):
                if record.record_id == active_record_id:
                    selected_row = row_index
                    break
        if selected_row >= 0:
            self.records_table.selectRow(selected_row)
        self.summary_label.setText(
            "No job records yet."
            if not records
            else f"Showing {len(records)} recent job records. Double-click opens results or monitor."
        )
        self._update_button_states()

    def _current_record(self) -> GuiJobRecord | None:
        record_id = self.selected_record_id()
        if record_id is None:
            return None
        return self._records_by_id.get(record_id)

    def _update_button_states(self) -> None:
        record = self._current_record()
        has_record = record is not None
        has_snapshot = has_record and record.snapshot_path is not None
        has_manifest = has_record and record.manifest_path is not None
        has_report = has_record and record.report_path is not None
        has_results = has_record and record.results_path is not None and record.results_path.exists()
        is_running = has_record and record.status in RUNNING_JOB_STATUSES

        self.run_last_snapshot_button.setEnabled(bool(has_snapshot))
        self.monitor_button.setEnabled(bool(has_record))
        self.open_results_button.setEnabled(bool(has_results))
        self.open_manifest_button.setEnabled(bool(has_manifest))
        self.open_report_button.setEnabled(bool(has_report))
        self.rerun_button.setEnabled(bool(has_snapshot))
        self.remove_record_button.setEnabled(bool(has_record))

        if is_running:
            self.monitor_button.setText("Monitor")
        else:
            self.monitor_button.setText("Monitor")

    def _handle_record_activation(self) -> None:
        record = self._current_record()
        if record is None:
            return
        if record.status in RUNNING_JOB_STATUSES:
            self.monitorRequested.emit(record.record_id)
            return
        if record.results_path is not None and record.results_path.exists():
            self.openResultsRequested.emit(record.record_id)
            return
        self.monitorRequested.emit(record.record_id)


class JobMonitorDialog(QDialog):
    """展示当前或最近一次 Job 的运行监控内容。"""

    openResultsRequested = Signal(object)
    terminateRequested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_record_id: str | None = None

        self.setWindowTitle("Job Monitor")
        self.resize(960, 680)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        summary_frame = QFrame(self)
        summary_layout = QGridLayout(summary_frame)
        summary_layout.setContentsMargins(10, 10, 10, 10)
        summary_layout.setHorizontalSpacing(16)
        summary_layout.setVerticalSpacing(8)

        self.job_name_value = QLabel("-", summary_frame)
        self.step_name_value = QLabel("-", summary_frame)
        self.status_value = QLabel("-", summary_frame)
        self.started_at_value = QLabel("-", summary_frame)
        self.finished_at_value = QLabel("-", summary_frame)
        self.results_path_value = QLabel("-", summary_frame)
        self.export_path_value = QLabel("-", summary_frame)
        self.results_path_value.setWordWrap(True)
        self.export_path_value.setWordWrap(True)

        summary_layout.addWidget(QLabel("Job", summary_frame), 0, 0)
        summary_layout.addWidget(self.job_name_value, 0, 1)
        summary_layout.addWidget(QLabel("Step", summary_frame), 0, 2)
        summary_layout.addWidget(self.step_name_value, 0, 3)
        summary_layout.addWidget(QLabel("Status", summary_frame), 1, 0)
        summary_layout.addWidget(self.status_value, 1, 1)
        summary_layout.addWidget(QLabel("Started", summary_frame), 1, 2)
        summary_layout.addWidget(self.started_at_value, 1, 3)
        summary_layout.addWidget(QLabel("Finished", summary_frame), 2, 0)
        summary_layout.addWidget(self.finished_at_value, 2, 1)
        summary_layout.addWidget(QLabel("Results", summary_frame), 2, 2)
        summary_layout.addWidget(self.results_path_value, 2, 3)
        summary_layout.addWidget(QLabel("Export", summary_frame), 3, 0)
        summary_layout.addWidget(self.export_path_value, 3, 1, 1, 3)
        root_layout.addWidget(summary_frame)

        metrics_frame = QFrame(self)
        metrics_layout = QGridLayout(metrics_frame)
        metrics_layout.setContentsMargins(10, 10, 10, 10)
        metrics_layout.setHorizontalSpacing(16)
        metrics_layout.setVerticalSpacing(8)

        self.frame_count_value = QLabel("-", metrics_frame)
        self.history_count_value = QLabel("-", metrics_frame)
        self.summary_count_value = QLabel("-", metrics_frame)
        self.last_message_value = QLabel("-", metrics_frame)
        self.current_action_value = QLabel("-", metrics_frame)
        self.last_message_value.setWordWrap(True)
        self.current_action_value.setWordWrap(True)

        metrics_layout.addWidget(QLabel("Frames", metrics_frame), 0, 0)
        metrics_layout.addWidget(self.frame_count_value, 0, 1)
        metrics_layout.addWidget(QLabel("Histories", metrics_frame), 0, 2)
        metrics_layout.addWidget(self.history_count_value, 0, 3)
        metrics_layout.addWidget(QLabel("Summaries", metrics_frame), 1, 0)
        metrics_layout.addWidget(self.summary_count_value, 1, 1)
        metrics_layout.addWidget(QLabel("Last Message", metrics_frame), 1, 2)
        metrics_layout.addWidget(self.last_message_value, 1, 3)
        metrics_layout.addWidget(QLabel("Current Action", metrics_frame), 2, 0)
        metrics_layout.addWidget(self.current_action_value, 2, 1, 1, 3)
        root_layout.addWidget(metrics_frame)

        self.tab_widget = QTabWidget(self)
        self.log_edit = self._build_readonly_editor("Job log messages will appear here.")
        self.errors_edit = self._build_readonly_editor("No errors recorded.")
        self.warnings_edit = self._build_readonly_editor("No warnings recorded.")
        self.output_edit = self._build_readonly_editor("No output artifacts recorded.")
        self.files_edit = self._build_readonly_editor("No artifact files are available.")
        self.tab_widget.addTab(self.log_edit, "Log")
        self.tab_widget.addTab(self.errors_edit, "Errors")
        self.tab_widget.addTab(self.warnings_edit, "Warnings")
        self.tab_widget.addTab(self.output_edit, "Output")
        self.tab_widget.addTab(self.files_edit, "Files")
        root_layout.addWidget(self.tab_widget, 1)

        action_row = QHBoxLayout()
        self.open_results_button = QPushButton("Open Results", self)
        self.terminate_button = QPushButton("Terminate", self)
        self.close_button = QPushButton("Close", self)
        self.terminate_button.setEnabled(False)
        action_row.addStretch(1)
        action_row.addWidget(self.open_results_button)
        action_row.addWidget(self.terminate_button)
        action_row.addWidget(self.close_button)
        root_layout.addLayout(action_row)

        self.open_results_button.clicked.connect(lambda: self.openResultsRequested.emit(self._current_record_id))
        self.terminate_button.clicked.connect(lambda: self.terminateRequested.emit(self._current_record_id))
        self.close_button.clicked.connect(self.close)

        self.set_empty_state("There is no active or completed job to monitor yet.")

    def _build_readonly_editor(self, placeholder: str) -> QPlainTextEdit:
        editor = QPlainTextEdit(self)
        editor.setReadOnly(True)
        editor.setPlaceholderText(placeholder)
        return editor

    def set_record(self, record: GuiJobRecord | None) -> None:
        """根据记录刷新 Monitor 内容。"""

        if record is None:
            self.set_empty_state("There is no active or completed job to monitor yet.")
            return

        buckets = bucketize_job_messages(record.last_messages)
        self._current_record_id = record.record_id
        self.job_name_value.setText(record.display_name)
        self.step_name_value.setText(_status_text(record.step_name))
        self.status_value.setText(_status_text(record.status))
        self.started_at_value.setText(_status_text(record.started_at))
        self.finished_at_value.setText(_status_text(record.finished_at))
        self.results_path_value.setText(_path_text(record.results_path))
        self.export_path_value.setText(_path_text(record.export_path))
        self.frame_count_value.setText(str(record.frame_count))
        self.history_count_value.setText(str(record.history_count))
        self.summary_count_value.setText(str(record.summary_count))
        self.last_message_value.setText(_status_text(record.last_messages[-1] if record.last_messages else None))
        self.current_action_value.setText(_status_text(record.current_action))

        self.log_edit.setPlainText("\n".join(buckets.log_messages) or "No log messages recorded.")
        self.errors_edit.setPlainText("\n".join(buckets.error_messages) or "No errors recorded.")
        self.warnings_edit.setPlainText("\n".join(buckets.warning_messages) or "No warnings recorded.")
        self.output_edit.setPlainText("\n".join(buckets.output_messages) or "No output artifacts recorded.")
        self.files_edit.setPlainText(
            "\n".join(
                (
                    f"results_path = {_path_text(record.results_path)}",
                    f"export_path = {_path_text(record.export_path)}",
                    f"snapshot_path = {_path_text(record.snapshot_path)}",
                    f"manifest_path = {_path_text(record.manifest_path)}",
                    f"report_path = {_path_text(record.report_path)}",
                )
            )
        )
        self.open_results_button.setEnabled(record.results_path is not None and record.results_path.exists())

    def set_empty_state(self, message: str) -> None:
        """显示 Monitor 的空状态。"""

        self._current_record_id = None
        self.job_name_value.setText("-")
        self.step_name_value.setText("-")
        self.status_value.setText("idle")
        self.started_at_value.setText("-")
        self.finished_at_value.setText("-")
        self.results_path_value.setText("-")
        self.export_path_value.setText("-")
        self.frame_count_value.setText("0")
        self.history_count_value.setText("0")
        self.summary_count_value.setText("0")
        self.last_message_value.setText(message)
        self.current_action_value.setText(message)
        self.log_edit.setPlainText(message)
        self.errors_edit.setPlainText("No errors recorded.")
        self.warnings_edit.setPlainText("No warnings recorded.")
        self.output_edit.setPlainText("No output artifacts recorded.")
        self.files_edit.setPlainText("No artifact files are available.")
        self.open_results_button.setEnabled(False)

    def current_record_id(self) -> str | None:
        """返回当前 Monitor 正在显示的记录编号。"""

        return self._current_record_id


class JobDiagnosticsDialog(QDialog):
    """展示当前运行能力、最近失败原因与建议动作。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Job Diagnostics")
        self.resize(820, 620)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        header_frame = QFrame(self)
        header_layout = QFormLayout(header_frame)
        header_layout.setContentsMargins(10, 10, 10, 10)
        header_layout.setSpacing(8)

        self.headline_value = QLabel("-", header_frame)
        self.status_value = QLabel("-", header_frame)
        self.run_ready_value = QLabel("-", header_frame)
        self.headline_value.setWordWrap(True)
        self.status_value.setWordWrap(True)
        self.run_ready_value.setWordWrap(True)
        header_layout.addRow("Headline", self.headline_value)
        header_layout.addRow("Status", self.status_value)
        header_layout.addRow("Run Ready", self.run_ready_value)
        root_layout.addWidget(header_frame)

        self.problem_edit = self._build_readonly_editor("Diagnostics summary will appear here.")
        self.recommendation_edit = self._build_readonly_editor("Next-step suggestions will appear here.")
        self.errors_edit = self._build_readonly_editor("No recent errors.")
        self.warnings_edit = self._build_readonly_editor("No recent warnings.")
        self.artifacts_edit = self._build_readonly_editor("No artifact status available.")

        self.tab_widget = QTabWidget(self)
        self.tab_widget.addTab(self.problem_edit, "Problems")
        self.tab_widget.addTab(self.recommendation_edit, "Next Steps")
        self.tab_widget.addTab(self.errors_edit, "Errors")
        self.tab_widget.addTab(self.warnings_edit, "Warnings")
        self.tab_widget.addTab(self.artifacts_edit, "Artifacts")
        root_layout.addWidget(self.tab_widget, 1)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        self.close_button = QPushButton("Close", self)
        action_row.addWidget(self.close_button)
        root_layout.addLayout(action_row)

        self.close_button.clicked.connect(self.close)
        self.set_snapshot(
            JobDiagnosticsSnapshot(
                headline="No diagnostics context yet.",
                run_ready=False,
                status_text="Load a model or run a job to populate diagnostics.",
                problem_lines=("No run records are available in this GUI session.",),
                recommendation_lines=("Write Input or run the current model first.",),
                error_lines=(),
                warning_lines=(),
                artifact_lines=(),
            )
        )

    def _build_readonly_editor(self, placeholder: str) -> QPlainTextEdit:
        editor = QPlainTextEdit(self)
        editor.setReadOnly(True)
        editor.setPlaceholderText(placeholder)
        return editor

    def set_snapshot(self, snapshot: JobDiagnosticsSnapshot) -> None:
        """根据诊断快照刷新弹窗内容。"""

        self.headline_value.setText(snapshot.headline)
        self.status_value.setText(snapshot.status_text)
        self.run_ready_value.setText("Ready" if snapshot.run_ready else "Not Ready")
        self.problem_edit.setPlainText("\n".join(snapshot.problem_lines) or "No diagnostic problems were found.")
        self.recommendation_edit.setPlainText("\n".join(snapshot.recommendation_lines) or "No next-step recommendations.")
        self.errors_edit.setPlainText("\n".join(snapshot.error_lines) or "No recent errors.")
        self.warnings_edit.setPlainText("\n".join(snapshot.warning_lines) or "No recent warnings.")
        self.artifacts_edit.setPlainText("\n".join(snapshot.artifact_lines) or "No artifact status available.")
