"""左侧工作台导航组件。"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import QPoint, QThread, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pyfem.gui.results_display import format_field_label, join_items, summarize_field_metadata, summarize_source_field_names
from pyfem.gui.model_edit_capabilities import is_object_editable
from pyfem.gui.shell import GuiModelNavigationSnapshot
from pyfem.post import ResultsFacade


class WorkbenchNavigationPanel(QWidget):
    """提供模型与结果的树形导航。"""

    modelSelectionRequested = Signal(str, object)
    modelEditRequested = Signal(str, object)
    resultsSelectionRequested = Signal(str, object, object, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._results_facade: ResultsFacade | None = None
        self._result_item_index: dict[tuple[object, ...], QTreeWidgetItem] = {}
        self._model_context_action_resolver: Callable[[str, object], Iterable[QAction]] | None = None
        self._build_ui()
        self.clear_model()
        self.clear_results()

    def _assert_gui_thread(self) -> None:
        if QThread.currentThread() is not self.thread():
            raise RuntimeError("WorkbenchNavigationPanel 只能在 GUI 主线程更新。")

    def set_model_snapshot(self, snapshot: GuiModelNavigationSnapshot) -> None:
        self._assert_gui_thread()
        self.model_tree.clear()
        self.model_status_label.setText(f"模型: {snapshot.model_name} | 部件 {len(snapshot.part_names)} | 实例 {len(snapshot.instance_names)} | 步 {len(snapshot.step_names)}")
        self.model_tree.addTopLevelItem(self._category_item("Models", [self._model_item(snapshot.model_name, "model", snapshot.model_name)]))
        self.model_tree.addTopLevelItem(self._category_item("Parts", [self._model_item(name, "part", name) for name in snapshot.part_names] or [self._model_item("(none)", "part", None)]))
        self.model_tree.addTopLevelItem(self._category_item("Materials", [self._model_item(name, "material", name) for name in snapshot.material_names] or [self._model_item("(none)", "material", None)]))
        self.model_tree.addTopLevelItem(self._category_item("Sections", [self._model_item(name, "section", name) for name in snapshot.section_names] or [self._model_item("(none)", "section", None)]))
        self.model_tree.addTopLevelItem(self._category_item("Assembly", [self._model_item(name, "instance", name) for name in snapshot.instance_names] or [self._model_item("(none)", "instance", None)]))
        self.model_tree.addTopLevelItem(self._category_item("Steps", [self._model_item(name, "step", name) for name in snapshot.step_names] or [self._model_item("(none)", "step", None)]))
        load_items = [self._model_item(name, "nodal_load", name) for name in snapshot.nodal_load_names]
        load_items.extend(self._model_item(name, "distributed_load", name) for name in snapshot.distributed_load_names)
        self.model_tree.addTopLevelItem(self._category_item("Loads", load_items or [self._model_item("(none)", "load", None)]))
        self.model_tree.addTopLevelItem(self._category_item("BCs", [self._model_item(name, "boundary", name) for name in snapshot.boundary_names] or [self._model_item("(none)", "boundary", None)]))
        self.model_tree.addTopLevelItem(self._category_item("Output Requests", [self._model_item(name, "output_request", name) for name in snapshot.output_request_names] or [self._model_item("(none)", "output_request", None)]))
        self.model_tree.expandToDepth(1)
        self.navigation_tabs.setCurrentWidget(self.model_tab)

    def clear_model(self) -> None:
        self.model_tree.clear()
        self.model_tree.addTopLevelItem(self._category_item("Models", [self._model_item("No model loaded", "model", None)]))
        for title, kind in (("Parts", "part"), ("Materials", "material"), ("Sections", "section"), ("Assembly", "instance"), ("Steps", "step"), ("Loads", "load"), ("BCs", "boundary"), ("Output Requests", "output_request")):
            self.model_tree.addTopLevelItem(self._category_item(title, [self._model_item("(none)", kind, None)]))
        self.model_status_label.setText("未加载模型")

    def set_results_facade(self, results_facade: ResultsFacade, *, preferred_step_name: str | None = None, preferred_frame_id: int | None = None, preferred_field_name: str | None = None) -> None:
        self._assert_gui_thread()
        self._results_facade = results_facade
        self._result_item_index.clear()
        self.results_tree.clear()
        steps_root = self._result_item("步骤", "", "category", None, None, None)
        frames_root = self._result_item("帧", "", "category", None, None, None)
        fields_root = self._result_item("字段", "", "category", None, None, None)
        histories_root = self._result_item("历史", "", "category", None, None, None)
        summaries_root = self._result_item("摘要", "", "category", None, None, None)
        total_frames = 0
        total_fields = 0
        total_histories = 0
        total_summaries = 0
        for step_name in results_facade.list_steps():
            step_overview = next(iter(results_facade.step_overviews(step_name=step_name)), None)
            frames = results_facade.frames(step_name=step_name)
            histories = results_facade.histories(step_name=step_name)
            summaries = results_facade.summaries(step_name=step_name)
            total_frames += len(frames)
            total_histories += len(histories)
            total_summaries += len(summaries)
            step_item = self._result_item(step_name, f"{len(frames)} 帧", "step", step_name, None, None)
            if step_overview is not None:
                for label, text in summarize_source_field_names(step_overview):
                    step_item.addChild(QTreeWidgetItem([label, text]))
            steps_root.addChild(step_item)
            self._result_item_index[("step", step_name)] = step_item
            frame_group = self._result_item(step_name, str(len(frames)), "group", step_name, None, None)
            field_group = self._result_item(step_name, "", "group", step_name, None, None)
            for frame in frames:
                frame_item = self._result_item(f"Frame {frame.frame_id}", f"{frame.frame_kind} | {frame.axis_kind}={frame.axis_value}", "frame", step_name, frame.frame_id, None)
                frame_group.addChild(frame_item)
                self._result_item_index[("frame", step_name, frame.frame_id)] = frame_item
                frame_fields = results_facade.fields(step_name=step_name, frame_id=frame.frame_id)
                total_fields += len(frame_fields)
                field_frame_item = self._result_item(f"Frame {frame.frame_id}", str(len(frame_fields)), "group", step_name, frame.frame_id, None)
                for field in frame_fields:
                    field_item = self._result_item(format_field_label(field), f"{field.source_type} | {field.position} | {field.target_count}", "field", step_name, frame.frame_id, field.field_name)
                    field_frame_item.addChild(field_item)
                    self._result_item_index[("field", step_name, frame.frame_id, field.field_name)] = field_item
                field_group.addChild(field_frame_item)
            history_group = self._result_item(step_name, str(len(histories)), "group", step_name, None, None)
            for history in histories:
                history_item = self._result_item(history.history_name, f"{history.position} | {history.axis_kind}", "history", step_name, None, history.history_name)
                history_group.addChild(history_item)
                self._result_item_index[("history", step_name, history.history_name)] = history_item
            summary_group = self._result_item(step_name, str(len(summaries)), "group", step_name, None, None)
            for summary in summaries:
                summary_item = self._result_item(summary.summary_name, join_items(summary.data_keys), "summary", step_name, None, summary.summary_name)
                summary_group.addChild(summary_item)
                self._result_item_index[("summary", step_name, summary.summary_name)] = summary_item
            frames_root.addChild(frame_group)
            fields_root.addChild(field_group)
            histories_root.addChild(history_group)
            summaries_root.addChild(summary_group)
        steps_root.setText(1, str(len(results_facade.list_steps())))
        frames_root.setText(1, str(total_frames))
        fields_root.setText(1, str(total_fields))
        histories_root.setText(1, str(total_histories))
        summaries_root.setText(1, str(total_summaries))
        for root in (steps_root, frames_root, fields_root, histories_root, summaries_root):
            self.results_tree.addTopLevelItem(root)
        self.results_tree.expandToDepth(1)
        self.results_status_label.setText(f"已发现 {len(results_facade.list_steps())} 个结果步")
        self.navigation_tabs.setCurrentWidget(self.results_tab)
        self.select_results(step_name=preferred_step_name or (results_facade.list_steps()[0] if results_facade.list_steps() else None), frame_id=preferred_frame_id, field_name=preferred_field_name)

    def clear_results(self) -> None:
        self._results_facade = None
        self._result_item_index.clear()
        self.results_tree.clear()
        self.results_tree.addTopLevelItem(self._result_item("结果", "未打开结果", "category", None, None, None))
        self.results_status_label.setText("未打开结果")
        self.results_details_edit.setPlainText(self._build_empty_results_details_text())
    def select_results(self, *, step_name: str | None = None, frame_id: int | None = None, field_name: str | None = None) -> None:
        target_item = None
        if step_name is not None and frame_id is not None and field_name is not None:
            target_item = self._result_item_index.get(("field", step_name, frame_id, field_name))
        if target_item is None and step_name is not None and frame_id is not None:
            target_item = self._result_item_index.get(("frame", step_name, frame_id))
        if target_item is None and step_name is not None:
            target_item = self._result_item_index.get(("step", step_name))
        if target_item is None:
            self.results_details_edit.setPlainText(self._build_empty_results_details_text())
            return
        self.results_tree.blockSignals(True)
        self.results_tree.setCurrentItem(target_item)
        self.results_tree.scrollToItem(target_item)
        self.results_tree.blockSignals(False)
        self._refresh_results_details(target_item)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QFrame(self)
        header_layout = QHBoxLayout(header)
        header_layout.addWidget(QLabel("Navigation", self))
        header_layout.addStretch(1)
        self.context_badge = QLabel("Part", self)
        header_layout.addWidget(self.context_badge)
        self.navigation_tabs = QTabWidget(self)
        self.model_tab = QWidget(self)
        self.results_tab = QWidget(self)
        self.navigation_tabs.addTab(self.model_tab, "Model")
        self.navigation_tabs.addTab(self.results_tab, "Results")
        self.model_tree = self._create_tree_widget(show_value_column=False, show_header=False)
        self.results_tree = self._create_tree_widget(show_value_column=False, show_header=False)
        self.model_status_label = QLabel("等待模型", self)
        self.results_status_label = QLabel("等待结果", self)
        model_layout = QVBoxLayout(self.model_tab)
        model_layout.addWidget(self.model_status_label)
        model_layout.addWidget(self.model_tree, 1)
        self.results_details_container = QFrame(self)
        details_layout = QVBoxLayout(self.results_details_container)
        details_layout.addWidget(QLabel("Summary", self))
        self.results_details_edit = QPlainTextEdit(self)
        self.results_details_edit.setReadOnly(True)
        self.results_details_edit.setMaximumHeight(136)
        details_layout.addWidget(self.results_details_edit)
        self.results_details_container.hide()
        results_layout = QVBoxLayout(self.results_tab)
        results_layout.addWidget(self.results_status_label)
        results_layout.addWidget(self.results_tree, 1)
        results_layout.addWidget(self.results_details_container)
        layout.addWidget(header)
        layout.addWidget(self.navigation_tabs, 1)
        self.navigation_tabs.currentChanged.connect(self._on_tab_changed)
        self.model_tree.itemSelectionChanged.connect(self._on_model_item_selected)
        self.model_tree.itemDoubleClicked.connect(self._on_model_item_double_clicked)
        self.model_tree.customContextMenuRequested.connect(self._show_model_context_menu)
        self.results_tree.itemSelectionChanged.connect(self._on_results_item_selected)

    def _create_tree_widget(self, *, show_value_column: bool, show_header: bool) -> QTreeWidget:
        tree = QTreeWidget(self)
        tree.setHeaderLabels(("Object", "Value"))
        tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        if not show_value_column:
            # 模型树第二列仅承载少量计数信息，隐藏后可避免无意义留白。
            tree.setColumnHidden(1, True)
        if not show_header:
            # 模型树表头不承载额外语义，隐藏后更接近 Abaqus 式导航观感。
            tree.setHeaderHidden(True)
        return tree

    def set_details_visible(self, visible: bool) -> None:
        self.results_details_container.setVisible(visible)

    def details_visible(self) -> bool:
        return self.results_details_container.isVisible()

    def current_results_details_text(self) -> str:
        text = self.results_details_edit.toPlainText().strip()
        return text or self._build_empty_results_details_text()

    def set_workspace_context(self, module_name: str, *, use_results_tab: bool) -> None:
        self.context_badge.setText(module_name)
        self.navigation_tabs.setCurrentWidget(self.results_tab if use_results_tab else self.model_tab)

    def set_model_context_action_resolver(self, resolver: Callable[[str, object], Iterable[QAction]] | None) -> None:
        """设置模型树右键菜单的统一命令解析器。"""

        self._model_context_action_resolver = resolver

    def select_model_entry(self, kind: str, name: object) -> None:
        for index in range(self.model_tree.topLevelItemCount()):
            item = self._find_model_item(self.model_tree.topLevelItem(index), kind, name)
            if item is not None:
                self.model_tree.blockSignals(True)
                self.model_tree.setCurrentItem(item)
                self.model_tree.blockSignals(False)
                self._on_model_item_selected()
                return

    def current_model_entry(self) -> tuple[str, object] | None:
        item = self.model_tree.currentItem()
        if item is None:
            return None
        user_data = self._read_pair_user_data(item)
        if user_data is None:
            return None
        return user_data

    def _find_model_item(self, item: QTreeWidgetItem, kind: str, name: object) -> QTreeWidgetItem | None:
        user_data = self._read_pair_user_data(item)
        if user_data is not None and user_data[0] == kind and user_data[1] == name:
            return item
        for index in range(item.childCount()):
            found = self._find_model_item(item.child(index), kind, name)
            if found is not None:
                return found
        return None

    def model_context_actions_for_entry(self, kind: str, name: object) -> tuple[QAction, ...]:
        """返回指定模型树条目的共享右键动作。"""

        if self._model_context_action_resolver is None:
            return ()
        return tuple(self._model_context_action_resolver(kind, name))

    def _read_pair_user_data(self, item: QTreeWidgetItem) -> tuple[str, object] | None:
        user_data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(user_data, (list, tuple)) or len(user_data) < 2:
            return None
        return str(user_data[0]), user_data[1]

    def _category_item(self, title: str, children: list[QTreeWidgetItem]) -> QTreeWidgetItem:
        item = QTreeWidgetItem([title, str(len(children))])
        item.setData(0, Qt.ItemDataRole.UserRole, ("category", None))
        for child in children:
            item.addChild(child)
        return item

    def _model_item(self, label: str, kind: str, value: object) -> QTreeWidgetItem:
        item = QTreeWidgetItem([label, ""])
        item.setData(0, Qt.ItemDataRole.UserRole, (kind, value))
        return item

    def _result_item(self, label: str, value: str, kind: str, step_name: str | None, frame_id: int | None, field_name: str | None) -> QTreeWidgetItem:
        item = QTreeWidgetItem([label, value])
        item.setData(0, Qt.ItemDataRole.UserRole, (kind, step_name, frame_id, field_name))
        return item

    def _refresh_results_details(self, item: QTreeWidgetItem) -> None:
        kind, step_name, frame_id, entry_name = item.data(0, Qt.ItemDataRole.UserRole)
        self.results_details_edit.setPlainText(self._build_results_details_text(kind=str(kind), step_name=step_name if isinstance(step_name, str) else None, frame_id=frame_id if isinstance(frame_id, int) else None, entry_name=entry_name if isinstance(entry_name, str) else None, label=item.text(0)))

    def _build_results_details_text(self, *, kind: str, step_name: str | None, frame_id: int | None, entry_name: str | None, label: str) -> str:
        if self._results_facade is None:
            return self._build_empty_results_details_text()
        if kind in {"category", "group"}:
            return self._build_detail_block(label, (("结果步数", len(self._results_facade.list_steps())), ("提示", "请选择步骤、帧、字段、历史或摘要查看说明。")))
        if kind == "step" and step_name is not None:
            overview = next(iter(self._results_facade.step_overviews(step_name=step_name)), None)
            if overview is None:
                return self._build_empty_results_details_text()
            groups = summarize_source_field_names(overview)
            return self._build_detail_block(f"步骤 {overview.step_name}", (("分析程序", overview.procedure_type or "-"), ("帧数", overview.frame_count), ("历史数", overview.history_count), ("摘要数", overview.summary_count), ("字段", groups[0][1]), ("恢复场", groups[1][1]), ("平均场", groups[2][1]), ("派生场", groups[3][1])))
        if kind == "frame" and step_name is not None and frame_id is not None:
            frame = self._results_facade.frame(step_name, frame_id)
            return self._build_detail_block(f"帧 {frame.frame_id}", (("步骤", frame.step_name), ("类型", frame.frame_kind), ("坐标轴", f"{frame.axis_kind} = {frame.axis_value}"), ("结果场", join_items(tuple(field.name for field in frame.fields))), ("来源类型", join_items(frame.field_source_types))))
        if kind == "field" and step_name is not None and frame_id is not None and entry_name is not None:
            field = self._results_facade.field(step_name, frame_id, entry_name)
            overview = next((item for item in self._results_facade.fields(step_name=step_name, frame_id=frame_id) if item.field_name == entry_name), None)
            range_text = "-" if overview is None or overview.min_value is None or overview.max_value is None else f"{overview.min_value:.6g} ~ {overview.max_value:.6g}"
            return self._build_detail_block(f"字段 {field.name}", (("步骤", step_name), ("帧", frame_id), ("来源", field.source_type), ("位置", field.position), ("分量", join_items(field.component_names)), ("目标数", "-" if overview is None else overview.target_count), ("范围", range_text), ("元数据", summarize_field_metadata(field.metadata)), ("示例目标", next(iter(field.values.keys()), "-"))))
        if kind == "history" and step_name is not None and entry_name is not None:
            history = self._results_facade.history(step_name, entry_name)
            return self._build_detail_block(f"历史 {history.name}", (("步骤", history.step_name), ("坐标轴", history.axis_kind), ("点数", len(history.axis_values)), ("目标", join_items(tuple(history.values.keys())))))
        if kind == "summary" and step_name is not None and entry_name is not None:
            summary = self._results_facade.summary(step_name, entry_name)
            return self._build_detail_block(f"摘要 {summary.name}", (("步骤", summary.step_name), ("数据键", join_items(tuple(summary.data.keys()))), ("元数据", self._stringify(summary.metadata))))
        return self._build_empty_results_details_text()
    def _build_empty_results_details_text(self) -> str:
        return "当前说明\n----\n当前尚未打开结果，或没有可用于说明的当前选择。"

    def _build_detail_block(self, title: str, rows: tuple[tuple[str, object], ...]) -> str:
        return "\n".join([title, "-" * len(title), *(f"{label}: {value}" for label, value in rows)])

    def _stringify(self, data: object) -> str:
        if isinstance(data, dict) and data:
            return ", ".join(f"{key}={value}" for key, value in data.items())
        return "-" if data in (None, "") else str(data)

    def _on_tab_changed(self, index: int) -> None:
        if self.context_badge.text() in {"Visualization", "Results"}:
            return
        self.context_badge.setText("Model" if index == 0 else "Results")

    def _on_model_item_selected(self) -> None:
        item = self.model_tree.currentItem()
        if item is None:
            return
        kind, name = item.data(0, Qt.ItemDataRole.UserRole)
        self.modelSelectionRequested.emit(str(kind), name)

    def _on_model_item_double_clicked(self, *_args) -> None:
        current_entry = self.current_model_entry()
        if current_entry is None:
            return
        kind, name = current_entry
        if name in {None, ""} or not is_object_editable(kind):
            return
        self.modelEditRequested.emit(kind, name)

    def _show_model_context_menu(self, position: QPoint) -> None:
        item = self.model_tree.itemAt(position)
        if item is None:
            return
        if item is not self.model_tree.currentItem():
            self.model_tree.setCurrentItem(item)
        kind, name = item.data(0, Qt.ItemDataRole.UserRole)
        if name in {None, ""} or not is_object_editable(str(kind)):
            return
        actions = self.model_context_actions_for_entry(str(kind), name)
        if actions:
            menu = QMenu(self)
            for action in actions:
                menu.addAction(action)
            menu.exec(self.model_tree.viewport().mapToGlobal(position))
            return
        menu = QMenu(self)
        edit_action = menu.addAction("Edit...")
        selected_action = menu.exec(self.model_tree.viewport().mapToGlobal(position))
        if selected_action is edit_action:
            self.modelEditRequested.emit(str(kind), name)

    def _on_results_item_selected(self) -> None:
        item = self.results_tree.currentItem()
        if item is None:
            return
        self._refresh_results_details(item)
        kind, step_name, frame_id, field_name = item.data(0, Qt.ItemDataRole.UserRole)
        self.resultsSelectionRequested.emit(str(kind), step_name, frame_id, field_name)
