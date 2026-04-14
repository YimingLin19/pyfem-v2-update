"""GUI 结果浏览独立组件。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pyfem.gui.result_field_presentation import FieldPresentationPolicy
from pyfem.gui.results_display import format_field_label, join_items, summarize_field_metadata, summarize_source_field_names
from pyfem.gui.theme import build_pill_stylesheet
from pyfem.post import ResultFieldOverview, ResultHistoryOverview, ResultSummaryOverview, ResultsFacade


class ResultsBrowser(QWidget):
    """封装 GUI 中的结果浏览与选择能力。"""

    selectionChanged = Signal(object, object, object)
    stepChanged = Signal(object)
    frameChanged = Signal(object)
    fieldChanged = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._results_facade: ResultsFacade | None = None
        self._frame_overviews: tuple[Any, ...] = ()
        self._field_overviews: tuple[ResultFieldOverview, ...] = ()
        self._history_overviews: tuple[ResultHistoryOverview, ...] = ()
        self._summary_overviews: tuple[ResultSummaryOverview, ...] = ()
        self._current_frame_id: int | None = None
        self._current_field_name: str | None = None
        self._build_ui()
        self.clear_results()

    @property
    def results_facade(self) -> ResultsFacade | None:
        return self._results_facade

    @property
    def current_step_name(self) -> str | None:
        return self.step_combo.currentData()

    @property
    def current_frame_id(self) -> int | None:
        return self._current_frame_id

    @property
    def current_field_name(self) -> str | None:
        return self._current_field_name

    def _assert_gui_thread(self) -> None:
        if QThread.currentThread() is not self.thread():
            raise RuntimeError("ResultsBrowser 只能在 GUI 主线程更新。")

    def set_results_facade(
        self,
        results_facade: ResultsFacade,
        *,
        preferred_step_name: str | None = None,
        preferred_frame_id: int | None = None,
        preferred_field_name: str | None = None,
    ) -> None:
        self._assert_gui_thread()
        self._results_facade = results_facade
        self.step_combo.blockSignals(True)
        self.step_combo.clear()
        for step_name in results_facade.list_steps():
            self.step_combo.addItem(step_name, step_name)
        self._set_combo_data(self.step_combo, preferred_step_name)
        self.step_combo.blockSignals(False)
        self.refresh_browser(preferred_frame_id=preferred_frame_id, preferred_field_name=preferred_field_name)

    def clear_results(self, message: str | None = None) -> None:
        self._assert_gui_thread()
        self._results_facade = None
        self._frame_overviews = ()
        self._field_overviews = ()
        self._history_overviews = ()
        self._summary_overviews = ()
        self._current_frame_id = None
        self._current_field_name = None
        self.step_combo.clear()
        self.step_overview_tree.clear()
        self._populate_table(self.frames_table, (), ())
        self._populate_table(self.fields_table, (), ())
        self._populate_table(self.histories_table, (), ())
        self._populate_table(self.summaries_table, (), ())
        self.empty_state_title_label.setText("尚未打开结果")
        self.empty_state_message_label.setText(message or "请先加载模型并运行作业，或打开已有 results 文件。")
        self.details_text_edit.setPlainText("详情\n----\n当前结果选择没有可显示的详情。")
        self._content_stack.setCurrentWidget(self.empty_page)
        self.dataset_summary_label.setText("未打开结果")
        self.selection_context_label.setText("当前选择: -")
        self._emit_selection()

    def refresh_browser(self, *, preferred_frame_id: int | None = None, preferred_field_name: str | None = None) -> None:
        self._assert_gui_thread()
        if self._results_facade is None or self.current_step_name is None:
            self.clear_results("当前尚未绑定可浏览的结果。")
            return
        step_name = self.current_step_name
        step_overview = next(iter(self._results_facade.step_overviews(step_name=step_name)), None)
        self._frame_overviews = self._results_facade.frames(step_name=step_name)
        self._history_overviews = self._results_facade.histories(step_name=step_name)
        self._summary_overviews = self._results_facade.summaries(step_name=step_name)
        self._current_frame_id = self._resolve_frame_id(preferred_frame_id)
        self._field_overviews = () if self._current_frame_id is None else self._results_facade.fields(step_name=step_name, frame_id=self._current_frame_id)
        self._current_field_name = self._resolve_field_name(preferred_field_name)
        self._populate_overview_tree(step_overview)
        self._populate_frames_table()
        self._populate_fields_table()
        self._populate_histories_table()
        self._populate_summaries_table()
        self._refresh_details()
        self._content_stack.setCurrentWidget(self.content_page)
        self.dataset_summary_label.setText(f"步骤 {step_name} | {len(self._frame_overviews)} 帧 | {len(self._field_overviews)} 个字段 | {len(self._history_overviews)} 条历史 | {len(self._summary_overviews)} 个摘要")
        frame_text = self._current_frame_id if self._current_frame_id is not None else "-"
        self.selection_context_label.setText(f"步骤 {step_name} | 帧 {frame_text} | 字段 {self._current_field_name or '仅网格'}")
        self._emit_selection()

    def select_step(self, step_name: str | None) -> None:
        if step_name is None:
            return
        self._set_combo_data(self.step_combo, step_name)
        self.refresh_browser()

    def select_frame(self, frame_id: int | None) -> None:
        if frame_id is None:
            return
        self._select_row(self.frames_table, self._frame_overviews, "frame_id", frame_id)
        self._on_frame_selected()

    def select_field(self, field_name: str | None) -> None:
        if field_name is None:
            return
        self._select_row(self.fields_table, self._field_overviews, "field_name", field_name)
        self._on_field_selected()
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        header = QFrame(self)
        header_layout = QHBoxLayout(header)
        title_box = QVBoxLayout()
        title_box.addWidget(QLabel("结果浏览"))
        title_box.addWidget(QLabel("展示 fields、histories、summaries 以及 recovered / averaged / derived 语义。"))
        meta_box = QVBoxLayout()
        self.dataset_summary_label = QLabel("未打开结果")
        self.selection_context_label = QLabel("当前选择: -")
        self.selection_context_label.setStyleSheet(build_pill_stylesheet(foreground_color="#27425c", background_color="#eef3f6", border_color="#c7d1d9"))
        meta_box.addWidget(self.dataset_summary_label)
        meta_box.addWidget(self.selection_context_label, 0, Qt.AlignmentFlag.AlignRight)
        header_layout.addLayout(title_box, 1)
        header_layout.addLayout(meta_box)
        self._content_stack = QStackedWidget(self)
        self.empty_page = QFrame(self)
        empty_layout = QVBoxLayout(self.empty_page)
        self.empty_state_title_label = QLabel("尚未打开结果")
        self.empty_state_message_label = QLabel("请先加载模型并运行作业，或打开已有 results 文件。")
        self.empty_state_message_label.setWordWrap(True)
        empty_layout.addStretch(1)
        empty_layout.addWidget(self.empty_state_title_label, 0, Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_state_message_label, 0, Qt.AlignmentFlag.AlignCenter)
        empty_layout.addStretch(1)
        self.content_page = QWidget(self)
        content_layout = QVBoxLayout(self.content_page)
        toolbar = QFrame(self)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.addWidget(QLabel("步骤"))
        self.step_combo = QComboBox(self)
        self.step_combo.setMinimumWidth(220)
        self.refresh_button = QPushButton("刷新", self)
        self.browser_hint_label = QLabel("字段列表会展示位置、来源、分量、元数据摘要、目标数与范围。")
        self.browser_hint_label.setWordWrap(True)
        toolbar_layout.addWidget(self.step_combo)
        toolbar_layout.addWidget(self.refresh_button)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self.browser_hint_label)
        splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.step_overview_tree = QTreeWidget(self)
        self.step_overview_tree.setHeaderLabels(("项目", "值"))
        self.step_overview_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.step_overview_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        bottom = QSplitter(Qt.Orientation.Vertical, self)
        self.results_tabs = QTabWidget(self)
        self.frames_table = self._create_table()
        self.fields_table = self._create_table()
        self.histories_table = self._create_table()
        self.summaries_table = self._create_table()
        self.results_tabs.addTab(self.frames_table, "Frames")
        self.results_tabs.addTab(self.fields_table, "Fields")
        self.results_tabs.addTab(self.histories_table, "Histories")
        self.results_tabs.addTab(self.summaries_table, "Summaries")
        details_group = QGroupBox("详情", self)
        details_layout = QVBoxLayout(details_group)
        self.details_text_edit = QPlainTextEdit(self)
        self.details_text_edit.setReadOnly(True)
        details_layout.addWidget(self.details_text_edit)
        bottom.addWidget(self.results_tabs)
        bottom.addWidget(details_group)
        splitter.addWidget(self.step_overview_tree)
        splitter.addWidget(bottom)
        content_layout.addWidget(toolbar)
        content_layout.addWidget(splitter, 1)
        self._content_stack.addWidget(self.empty_page)
        self._content_stack.addWidget(self.content_page)
        layout.addWidget(header)
        layout.addWidget(self._content_stack, 1)
        self.step_combo.currentIndexChanged.connect(self._on_step_changed)
        self.refresh_button.clicked.connect(self.refresh_browser)
        self.frames_table.itemSelectionChanged.connect(self._on_frame_selected)
        self.fields_table.itemSelectionChanged.connect(self._on_field_selected)
        self.histories_table.itemSelectionChanged.connect(self._refresh_details)
        self.summaries_table.itemSelectionChanged.connect(self._refresh_details)
        self.results_tabs.currentChanged.connect(self._refresh_details)

    def _create_table(self) -> QTableWidget:
        table = QTableWidget(self)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    def _populate_overview_tree(self, overview: Any) -> None:
        self.step_overview_tree.clear()
        if overview is None:
            return
        root = QTreeWidgetItem([overview.step_name, f"帧={overview.frame_count}, 历史={overview.history_count}, 摘要={overview.summary_count}"])
        font = root.font(0)
        font.setBold(True)
        root.setFont(0, font)
        root.addChild(QTreeWidgetItem(["分析程序", overview.procedure_type or "-"]))
        root.addChild(QTreeWidgetItem(["帧编号", join_items(overview.frame_ids)]))
        for label, text in summarize_source_field_names(overview):
            root.addChild(QTreeWidgetItem([label, text]))
        root.addChild(QTreeWidgetItem(["历史", join_items(overview.history_names)]))
        root.addChild(QTreeWidgetItem(["摘要", join_items(overview.summary_names)]))
        root.addChild(QTreeWidgetItem(["目标", join_items(overview.target_keys)]))
        self.step_overview_tree.addTopLevelItem(root)
        self.step_overview_tree.expandAll()

    def _populate_frames_table(self) -> None:
        self._populate_table(self.frames_table, ("步骤", "帧", "类型", "轴", "轴值", "场", "来源", "目标"), [
            (frame.step_name, frame.frame_id, frame.frame_kind, frame.axis_kind, frame.axis_value, join_items(frame.field_names), join_items(frame.field_source_types), join_items(frame.target_keys))
            for frame in self._frame_overviews
        ])
        self._select_row(self.frames_table, self._frame_overviews, "frame_id", self._current_frame_id)

    def _populate_fields_table(self) -> None:
        self._populate_table(self.fields_table, ("步骤", "帧", "字段", "来源", "位置", "分量", "目标数", "元数据", "范围"), [
            (field.step_name, field.frame_id, format_field_label(field), field.source_type, field.position, join_items(field.component_names), field.target_count, summarize_field_metadata(field.metadata), self._format_range(field.min_value, field.max_value))
            for field in self._field_overviews
        ])
        self._select_row(self.fields_table, self._field_overviews, "field_name", self._current_field_name)

    def _populate_histories_table(self) -> None:
        self._populate_table(self.histories_table, ("步骤", "历史", "轴", "点数", "位置", "目标", "配对值"), [
            (item.step_name, item.history_name, item.axis_kind, item.axis_count, item.position, join_items(item.target_keys), join_items(item.paired_value_names))
            for item in self._history_overviews
        ])
        if self.histories_table.rowCount():
            self.histories_table.selectRow(0)

    def _populate_summaries_table(self) -> None:
        self._populate_table(self.summaries_table, ("步骤", "摘要", "数据键"), [
            (item.step_name, item.summary_name, join_items(item.data_keys))
            for item in self._summary_overviews
        ])
        if self.summaries_table.rowCount():
            self.summaries_table.selectRow(0)

    def _refresh_details(self, *_args: object) -> None:
        if self._results_facade is None or self.current_step_name is None:
            self.details_text_edit.setPlainText("详情\n----\n当前结果选择没有可显示的详情。")
            return
        if self.results_tabs.currentWidget() is self.frames_table and self._current_frame_id is not None:
            frame = self._results_facade.frame(self.current_step_name, self._current_frame_id)
            self.details_text_edit.setPlainText(self._build_section_text(f"帧 {frame.frame_id}", (("步骤", frame.step_name), ("类型", frame.frame_kind), ("坐标轴", f"{frame.axis_kind} = {frame.axis_value}"), ("字段", join_items(tuple(field.name for field in frame.fields))), ("来源类型", join_items(frame.field_source_types)), ("目标数", frame.target_count), ("元数据", self._stringify(frame.metadata)))))
            return
        if self.results_tabs.currentWidget() is self.fields_table and self._current_frame_id is not None and self._current_field_name is not None:
            field = self._results_facade.field(self.current_step_name, self._current_frame_id, self._current_field_name)
            overview = next((item for item in self._field_overviews if item.field_name == self._current_field_name), None)
            self.details_text_edit.setPlainText(self._build_section_text(f"字段 {field.name}", (("步骤", self.current_step_name), ("帧", self._current_frame_id), ("来源", field.source_type), ("位置", field.position), ("分量", join_items(field.component_names)), ("目标数", overview.target_count if overview is not None else len(field.values)), ("范围", self._format_range(None if overview is None else overview.min_value, None if overview is None else overview.max_value)), ("目标", join_items(tuple(field.values.keys()))), ("元数据", self._stringify(field.metadata)))))
            return
        if self.results_tabs.currentWidget() is self.histories_table and self.histories_table.currentRow() >= 0 and self.histories_table.currentRow() < len(self._history_overviews):
            overview = self._history_overviews[self.histories_table.currentRow()]
            history = self._results_facade.history(overview.step_name, overview.history_name)
            self.details_text_edit.setPlainText(self._build_section_text(f"历史 {history.name}", (("步骤", history.step_name), ("坐标轴", history.axis_kind), ("点数", len(history.axis_values)), ("位置", history.position), ("目标", join_items(tuple(history.values.keys()))), ("配对值", join_items(tuple(history.paired_values.keys()))), ("元数据", self._stringify(history.metadata)))))
            return
        if self.results_tabs.currentWidget() is self.summaries_table and self.summaries_table.currentRow() >= 0 and self.summaries_table.currentRow() < len(self._summary_overviews):
            overview = self._summary_overviews[self.summaries_table.currentRow()]
            summary = self._results_facade.summary(overview.step_name, overview.summary_name)
            self.details_text_edit.setPlainText(self._build_section_text(f"摘要 {summary.name}", (("步骤", summary.step_name), ("数据键", join_items(tuple(summary.data.keys()))), ("元数据", self._stringify(summary.metadata)))))
            return
        self.details_text_edit.setPlainText("详情\n----\n当前结果选择没有可显示的详情。")

    def _on_step_changed(self) -> None:
        self.refresh_browser()
        self.stepChanged.emit(self.current_step_name)

    def _on_frame_selected(self) -> None:
        row = self.frames_table.currentRow()
        if row < 0 or row >= len(self._frame_overviews) or self._results_facade is None or self.current_step_name is None:
            return
        self._current_frame_id = self._frame_overviews[row].frame_id
        self._field_overviews = self._results_facade.fields(step_name=self.current_step_name, frame_id=self._current_frame_id)
        self._current_field_name = self._resolve_field_name(self._current_field_name)
        self._populate_fields_table()
        self._refresh_details()
        self.selection_context_label.setText(f"步骤 {self.current_step_name} | 帧 {self._current_frame_id} | 字段 {self._current_field_name or '仅网格'}")
        self.frameChanged.emit(self._current_frame_id)
        self._emit_selection()

    def _on_field_selected(self) -> None:
        row = self.fields_table.currentRow()
        if row < 0 or row >= len(self._field_overviews):
            return
        self._current_field_name = self._field_overviews[row].field_name
        frame_text = self._current_frame_id if self._current_frame_id is not None else "-"
        self.selection_context_label.setText(f"步骤 {self.current_step_name} | 帧 {frame_text} | 字段 {self._current_field_name}")
        self._refresh_details()
        self.fieldChanged.emit(self._current_field_name)
        self._emit_selection()

    def _resolve_frame_id(self, preferred_frame_id: int | None) -> int | None:
        if preferred_frame_id is not None and any(item.frame_id == preferred_frame_id for item in self._frame_overviews):
            return preferred_frame_id
        return self._frame_overviews[0].frame_id if self._frame_overviews else None

    def _resolve_field_name(self, preferred_field_name: str | None) -> str | None:
        policy = FieldPresentationPolicy.from_field_overviews(self._field_overviews)
        return policy.default_field_name(preferred_field_name)

    def _populate_table(self, table: QTableWidget, headers: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
        table.clear()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(tuple(headers))
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                table.setItem(row_index, column_index, QTableWidgetItem("" if value is None else str(value)))

    def _select_row(self, table: QTableWidget, overviews: Sequence[Any], attribute_name: str, target_value: object) -> None:
        if table.rowCount() == 0:
            return
        target_row = 0
        if target_value is not None:
            for row_index, overview in enumerate(overviews):
                if getattr(overview, attribute_name) == target_value:
                    target_row = row_index
                    break
        table.setCurrentCell(target_row, 0)
        table.selectRow(target_row)

    def _set_combo_data(self, combo: QComboBox, target_value: object) -> None:
        if target_value is None and combo.count():
            combo.setCurrentIndex(0)
            return
        for index in range(combo.count()):
            if combo.itemData(index) == target_value:
                combo.setCurrentIndex(index)
                return
        if combo.count():
            combo.setCurrentIndex(0)

    def _build_section_text(self, title: str, rows: Sequence[tuple[str, object]]) -> str:
        return "\n".join([title, "-" * len(title), *(f"{label}: {value}" for label, value in rows)])

    def _format_range(self, min_value: float | None, max_value: float | None) -> str:
        return "-" if min_value is None or max_value is None else f"{min_value:.6g} ~ {max_value:.6g}"

    def _stringify(self, data: Any) -> str:
        if isinstance(data, dict) and data:
            return ", ".join(f"{key}={value}" for key, value in data.items())
        return "-" if not data else str(data)

    def _emit_selection(self) -> None:
        self.selectionChanged.emit(self.current_step_name, self.current_frame_id, self.current_field_name)
