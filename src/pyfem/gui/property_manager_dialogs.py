"""定义 Property 模块的管理器与分配对话框。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pyfem.gui.model_edit_dialogs import MaterialEditDialog, SectionEditDialog
from pyfem.gui.model_edit_presenters import (
    ModelEditPresenter,
    SectionAssignmentCandidate,
    SectionAssignmentContext,
    SectionAssignmentScope,
)


class BasePropertyManagerDialog(QDialog):
    """提供 Property 管理器共用的壳层。"""

    modelChanged = Signal(str, object, str)

    def __init__(self, parent: QWidget | None, presenter: ModelEditPresenter, *, title: str, empty_message: str) -> None:
        super().__init__(parent)
        self.presenter = presenter
        self._empty_message = empty_message
        self._active_edit_dialog: QDialog | None = None
        self.setWindowTitle(title)
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.resize(420, 280)
        self._build_shell()

    def current_name(self) -> str | None:
        """返回当前选中的对象名称。"""

        item = self.name_list.currentItem()
        if item is None:
            return None
        return str(item.text())

    def select_name(self, name: str | None) -> None:
        """按名称选中列表项。"""

        if name is None:
            self.name_list.clearSelection()
            self._refresh_action_state()
            return
        matches = self.name_list.findItems(name, Qt.MatchFlag.MatchExactly)
        if not matches:
            self.name_list.clearSelection()
            self._refresh_action_state()
            return
        self.name_list.setCurrentItem(matches[0])

    def refresh(self, *, selected_name: str | None = None) -> None:
        """由子类刷新列表内容。"""

        raise NotImplementedError

    def _build_shell(self) -> None:
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(10)

        list_container = QWidget(self)
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(6)

        self.caption_label = QLabel("", self)
        self.caption_label.setWordWrap(True)
        self.empty_state_label = QLabel(self._empty_message, self)
        self.empty_state_label.setWordWrap(True)
        self.name_list = QListWidget(self)
        self.name_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.name_list.itemSelectionChanged.connect(self._refresh_action_state)

        list_layout.addWidget(self.caption_label)
        list_layout.addWidget(self.empty_state_label)
        list_layout.addWidget(self.name_list, 1)

        button_container = QWidget(self)
        button_layout = QVBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(6)

        self.create_button = QPushButton("Create...", button_container)
        self.edit_button = QPushButton("Edit...", button_container)
        self.copy_button = QPushButton("Copy...", button_container)
        self.rename_button = QPushButton("Rename...", button_container)
        self.delete_button = QPushButton("Delete...", button_container)
        self.close_button = QPushButton("Close", button_container)

        self.create_button.clicked.connect(self._create_item)
        self.edit_button.clicked.connect(self._edit_selected_item)
        self.copy_button.clicked.connect(self._copy_selected_item)
        self.rename_button.clicked.connect(self._rename_selected_item)
        self.delete_button.clicked.connect(self._delete_selected_item)
        self.close_button.clicked.connect(self.close)

        for button in (
            self.create_button,
            self.edit_button,
            self.copy_button,
            self.rename_button,
            self.delete_button,
        ):
            button_layout.addWidget(button)
        button_layout.addStretch(1)
        button_layout.addWidget(self.close_button)

        root_layout.addWidget(list_container, 1)
        root_layout.addWidget(button_container)

    def _set_list_state(self, names: Sequence[str], *, selected_name: str | None) -> None:
        """刷新列表显示。"""

        self.name_list.clear()
        for name in names:
            self.name_list.addItem(name)
        has_items = bool(names)
        self.empty_state_label.setVisible(not has_items)
        self.name_list.setVisible(has_items)
        if has_items:
            self.select_name(selected_name or names[0])
        else:
            self.select_name(None)
        self._refresh_action_state()

    def _refresh_action_state(self) -> None:
        """同步按钮可用状态。"""

        has_selection = self.current_name() is not None
        self.edit_button.setEnabled(has_selection)
        self.copy_button.setEnabled(has_selection)
        self.rename_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)

    def _prompt_for_name(self, *, title: str, label: str, default_value: str) -> str | None:
        """弹出名称输入框。"""

        value, accepted = QInputDialog.getText(self, title, label, text=default_value)
        if not accepted:
            return None
        normalized_value = str(value).strip()
        return normalized_value or None

    def _run_edit_dialog(self, factory: Callable[[], QDialog]) -> bool:
        """执行子编辑弹窗，并返回是否已提交改动。"""

        dialog = factory()
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._active_edit_dialog = dialog
        dialog.destroyed.connect(lambda *_args: self._clear_active_edit_dialog())
        dialog_applied = {"value": False}
        if hasattr(dialog, "applied"):
            dialog.applied.connect(lambda: dialog_applied.__setitem__("value", True))
        try:
            result = dialog.exec()
        finally:
            self._active_edit_dialog = None
        return dialog_applied["value"] or result == QDialog.DialogCode.Accepted

    def _clear_active_edit_dialog(self) -> None:
        """在子编辑弹窗销毁后清空跟踪引用。"""

        self._active_edit_dialog = None

    def closeEvent(self, event) -> None:
        """关闭管理器时同步收拢仍在编辑中的子弹窗。"""

        dialog = self._active_edit_dialog
        self._active_edit_dialog = None
        if dialog is not None:
            dialog.close()
        super().closeEvent(event)

    def _handle_action_error(self, title: str, error: Exception) -> None:
        """统一展示管理器操作错误。"""

        QMessageBox.critical(self, title, str(error))

    def _on_item_double_clicked(self, _item: QListWidgetItem) -> None:
        self._edit_selected_item()

    def _create_item(self) -> None:
        raise NotImplementedError

    def _edit_selected_item(self) -> None:
        raise NotImplementedError

    def _copy_selected_item(self) -> None:
        raise NotImplementedError

    def _rename_selected_item(self) -> None:
        raise NotImplementedError

    def _delete_selected_item(self) -> None:
        raise NotImplementedError


class MaterialManagerDialog(BasePropertyManagerDialog):
    """定义材料管理器窗口。"""

    def __init__(self, parent: QWidget | None, presenter: ModelEditPresenter) -> None:
        super().__init__(
            parent,
            presenter,
            title="Materials",
            empty_message="No materials are available in the current model.",
        )
        self.caption_label.setText("Manage model materials here, then open the formal editor for details.")
        self.refresh()

    def refresh(self, *, selected_name: str | None = None) -> None:
        """刷新材料列表。"""

        names = self.presenter.list_material_names()
        self._set_list_state(names, selected_name=selected_name)

    def _create_item(self) -> None:
        default_name = self.presenter.suggest_new_material_name()
        material_name = self._prompt_for_name(
            title="Create Material",
            label="Material name:",
            default_value=default_name,
        )
        if material_name is None:
            return
        original_model = self.presenter.snapshot_model()
        original_dirty = self.presenter.model_dirty()
        try:
            self.presenter.create_material(material_name)
            committed = self._run_edit_dialog(lambda: MaterialEditDialog(self, self.presenter, material_name))
            if not committed:
                self.presenter.restore_model(original_model, mark_dirty=original_dirty)
                self.refresh()
                return
        except Exception as error:  # noqa: BLE001
            self.presenter.restore_model(original_model, mark_dirty=original_dirty)
            self._handle_action_error("Create Material", error)
            return
        self.refresh(selected_name=material_name)
        self.modelChanged.emit("material", material_name, "created")

    def _edit_selected_item(self) -> None:
        material_name = self.current_name()
        if material_name is None:
            return
        try:
            committed = self._run_edit_dialog(lambda: MaterialEditDialog(self, self.presenter, material_name))
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Edit Material", error)
            return
        if committed:
            self.refresh(selected_name=material_name)
            self.modelChanged.emit("material", material_name, "updated")

    def _copy_selected_item(self) -> None:
        source_name = self.current_name()
        if source_name is None:
            return
        target_name = self._prompt_for_name(
            title="Copy Material",
            label="New material name:",
            default_value=self.presenter.suggest_copy_name(source_name, self.presenter.list_material_names()),
        )
        if target_name is None:
            return
        try:
            self.presenter.copy_material(source_name, target_name)
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Copy Material", error)
            return
        self.refresh(selected_name=target_name)
        self.modelChanged.emit("material", target_name, "copied")

    def _rename_selected_item(self) -> None:
        source_name = self.current_name()
        if source_name is None:
            return
        target_name = self._prompt_for_name(
            title="Rename Material",
            label="New material name:",
            default_value=source_name,
        )
        if target_name is None or target_name == source_name:
            return
        try:
            self.presenter.rename_material(source_name, target_name)
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Rename Material", error)
            return
        self.refresh(selected_name=target_name)
        self.modelChanged.emit("material", target_name, "renamed")

    def _delete_selected_item(self) -> None:
        material_name = self.current_name()
        if material_name is None:
            return
        referenced_sections = self.presenter.material_reference_sections(material_name)
        if referenced_sections:
            joined = ", ".join(referenced_sections)
            QMessageBox.warning(
                self,
                "Delete Material",
                f"Material {material_name} is still referenced by sections: {joined}. Delete is blocked.",
            )
            return
        confirmed = QMessageBox.question(
            self,
            "Delete Material",
            f"Delete material {material_name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self.presenter.delete_material(material_name)
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Delete Material", error)
            return
        self.refresh()
        self.modelChanged.emit("material", material_name, "deleted")


class SectionManagerDialog(BasePropertyManagerDialog):
    """定义截面管理器窗口。"""

    SECTION_TYPE_CHOICES: tuple[tuple[str, str], ...] = (
        ("Solid", "solid"),
        ("Plane Stress", "plane_stress"),
        ("Plane Strain", "plane_strain"),
        ("Beam", "beam"),
    )

    def __init__(self, parent: QWidget | None, presenter: ModelEditPresenter) -> None:
        super().__init__(
            parent,
            presenter,
            title="Sections",
            empty_message="No sections are available in the current model.",
        )
        self.caption_label.setText("Manage section definitions here, then refine parameters in the formal editor.")
        self.refresh()

    def refresh(self, *, selected_name: str | None = None) -> None:
        """刷新截面列表。"""

        names = self.presenter.list_section_names()
        self._set_list_state(names, selected_name=selected_name)

    def _create_item(self) -> None:
        default_name = self.presenter.suggest_new_section_name()
        section_name = self._prompt_for_name(
            title="Create Section",
            label="Section name:",
            default_value=default_name,
        )
        if section_name is None:
            return
        display_items = [label for label, _value in self.SECTION_TYPE_CHOICES]
        selected_label, accepted = QInputDialog.getItem(
            self,
            "Create Section",
            "Section type:",
            display_items,
            0,
            False,
        )
        if not accepted:
            return
        selected_type = next(value for label, value in self.SECTION_TYPE_CHOICES if label == selected_label)
        material_names = self.presenter.list_material_names()
        assignment_candidates = self.presenter.list_section_assignment_candidates()
        original_model = self.presenter.snapshot_model()
        original_dirty = self.presenter.model_dirty()
        try:
            self.presenter.create_section(
                section_name,
                section_type=selected_type,
                material_name=material_names[0] if material_names else None,
                scope_name=assignment_candidates[0].scope_name if assignment_candidates else None,
                region_name=assignment_candidates[0].region_name if assignment_candidates else None,
            )
            committed = self._run_edit_dialog(lambda: SectionEditDialog(self, self.presenter, section_name))
            if not committed:
                self.presenter.restore_model(original_model, mark_dirty=original_dirty)
                self.refresh()
                return
        except Exception as error:  # noqa: BLE001
            self.presenter.restore_model(original_model, mark_dirty=original_dirty)
            self._handle_action_error("Create Section", error)
            return
        self.refresh(selected_name=section_name)
        self.modelChanged.emit("section", section_name, "created")

    def _edit_selected_item(self) -> None:
        section_name = self.current_name()
        if section_name is None:
            return
        try:
            committed = self._run_edit_dialog(lambda: SectionEditDialog(self, self.presenter, section_name))
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Edit Section", error)
            return
        if committed:
            self.refresh(selected_name=section_name)
            self.modelChanged.emit("section", section_name, "updated")

    def _copy_selected_item(self) -> None:
        source_name = self.current_name()
        if source_name is None:
            return
        target_name = self._prompt_for_name(
            title="Copy Section",
            label="New section name:",
            default_value=self.presenter.suggest_copy_name(source_name, self.presenter.list_section_names()),
        )
        if target_name is None:
            return
        try:
            self.presenter.copy_section(source_name, target_name)
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Copy Section", error)
            return
        self.refresh(selected_name=target_name)
        self.modelChanged.emit("section", target_name, "copied")

    def _rename_selected_item(self) -> None:
        source_name = self.current_name()
        if source_name is None:
            return
        target_name = self._prompt_for_name(
            title="Rename Section",
            label="New section name:",
            default_value=source_name,
        )
        if target_name is None or target_name == source_name:
            return
        try:
            self.presenter.rename_section(source_name, target_name)
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Rename Section", error)
            return
        self.refresh(selected_name=target_name)
        self.modelChanged.emit("section", target_name, "renamed")

    def _delete_selected_item(self) -> None:
        section_name = self.current_name()
        if section_name is None:
            return
        direct_references = self.presenter.section_direct_reference_elements(section_name)
        if direct_references:
            joined = ", ".join(direct_references)
            QMessageBox.warning(
                self,
                "Delete Section",
                f"Section {section_name} is still referenced by elements: {joined}. Delete is blocked.",
            )
            return
        section = self.presenter.section(section_name)
        binding_text = f"scope={section.scope_name or '-'}, region={section.region_name or '-'}"
        confirmed = QMessageBox.question(
            self,
            "Delete Section",
            f"Delete section {section_name}?\nCurrent binding: {binding_text}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self.presenter.delete_section(section_name)
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Delete Section", error)
            return
        self.refresh()
        self.modelChanged.emit("section", section_name, "deleted")


class AssignSectionDialog(QDialog):
    """定义正式的截面分配操作窗口。"""

    modelChanged = Signal(str, object, str)

    def __init__(self, parent: QWidget | None, presenter: ModelEditPresenter) -> None:
        super().__init__(parent)
        self.presenter = presenter
        self._targets_by_scope: dict[str, list[SectionAssignmentCandidate]] = {}
        self._scopes_by_name: dict[str, SectionAssignmentScope] = {}
        self._section_names: tuple[str, ...] = ()
        self._assignment_context = SectionAssignmentContext()
        self.setWindowTitle("Assign Section")
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.resize(420, 250)
        self._build_shell()
        self.refresh()

    def refresh(self, *, preferred_context: SectionAssignmentContext | None = None) -> None:
        """刷新当前可分配数据。"""

        if preferred_context is not None:
            self._assignment_context = preferred_context

        self._section_names = self.presenter.list_section_names()
        scopes = self.presenter.list_section_assignment_scopes()
        candidates = self.presenter.list_section_assignment_candidates()
        self._scopes_by_name = {scope.scope_name: scope for scope in scopes}
        self._targets_by_scope = defaultdict(list)
        for candidate in candidates:
            self._targets_by_scope[candidate.scope_name].append(candidate)
        self._rebuild_section_choices()
        self._rebuild_scope_choices()
        self._sync_from_section(initial_refresh=True)

    def _build_shell(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.description_label = QLabel(
            "Choose an existing section and bind it to a concrete scope/region pair.",
            self,
        )
        self.description_label.setWordWrap(True)
        self.empty_state_label = QLabel(self)
        self.empty_state_label.setWordWrap(True)

        self.form_container = QWidget(self)
        form_layout = QFormLayout(self.form_container)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(6)

        self.section_combo = QComboBox(self.form_container)
        self.scope_combo = QComboBox(self.form_container)
        self.region_combo = QComboBox(self.form_container)
        self.part_value = QLabel("-", self.form_container)
        self.part_value.setWordWrap(True)

        self.section_combo.setPlaceholderText("Select a section")
        self.scope_combo.setPlaceholderText("Select a scope")
        self.region_combo.setPlaceholderText("Select a region")

        form_layout.addRow("Section", self.section_combo)
        form_layout.addRow("Scope", self.scope_combo)
        form_layout.addRow("Region", self.region_combo)
        form_layout.addRow("Part", self.part_value)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(6)
        button_row.addStretch(1)
        self.apply_button = QPushButton("Apply", self)
        self.cancel_button = QPushButton("Cancel", self)
        button_row.addWidget(self.apply_button)
        button_row.addWidget(self.cancel_button)

        self.section_combo.currentIndexChanged.connect(self._sync_from_section)
        self.scope_combo.currentIndexChanged.connect(self._rebuild_region_choices)
        self.region_combo.currentIndexChanged.connect(self._refresh_state_feedback)
        self.apply_button.clicked.connect(self._apply_assignment)
        self.cancel_button.clicked.connect(self.close)

        layout.addWidget(self.description_label)
        layout.addWidget(self.empty_state_label)
        layout.addWidget(self.form_container)
        layout.addStretch(1)
        layout.addLayout(button_row)

    def _rebuild_section_choices(self) -> None:
        """按当前上下文重建截面选择框。"""

        self.section_combo.blockSignals(True)
        self.section_combo.clear()
        for section_name in self._section_names:
            self.section_combo.addItem(section_name, section_name)
        preferred_name = self._assignment_context.preferred_section_name
        if preferred_name in self._section_names:
            self.section_combo.setCurrentIndex(self.section_combo.findData(preferred_name))
        elif self._section_names:
            self.section_combo.setCurrentIndex(-1)
        self.section_combo.blockSignals(False)
        self.section_combo.setEnabled(bool(self._section_names))

    def _rebuild_scope_choices(self) -> None:
        """按当前上下文重建作用域选择框。"""

        scope_names = tuple(sorted(self._scopes_by_name.keys()))
        self.scope_combo.blockSignals(True)
        self.scope_combo.clear()
        for scope_name in scope_names:
            self.scope_combo.addItem(scope_name, scope_name)
        preferred_scope = self._assignment_context.preferred_scope_name
        if preferred_scope in self._scopes_by_name:
            self.scope_combo.setCurrentIndex(self.scope_combo.findData(preferred_scope))
        elif scope_names:
            self.scope_combo.setCurrentIndex(-1)
        self.scope_combo.blockSignals(False)
        self.scope_combo.setEnabled(bool(scope_names))

    def _sync_from_section(self, *_args, initial_refresh: bool = False) -> None:
        """根据当前截面回填作用域与区域。"""

        preferred_region = self._assignment_context.preferred_region_name if initial_refresh else None
        section_name = self.section_combo.currentData()
        if isinstance(section_name, str):
            section = self.presenter.section(section_name)
            preferred_scope = self.scope_combo.currentData()
            if not isinstance(preferred_scope, str):
                preferred_scope = section.scope_name or self._assignment_context.preferred_scope_name
            if preferred_scope in self._scopes_by_name:
                scope_index = self.scope_combo.findData(preferred_scope)
                if scope_index >= 0:
                    self.scope_combo.blockSignals(True)
                    self.scope_combo.setCurrentIndex(scope_index)
                    self.scope_combo.blockSignals(False)
            if preferred_region is None:
                preferred_region = section.region_name
        self._rebuild_region_choices(preferred_region=preferred_region)

    def _rebuild_region_choices(self, *_args, preferred_region: str | None = None) -> None:
        """按当前作用域刷新区域列表。"""

        scope_name = self.scope_combo.currentData()
        self.region_combo.blockSignals(True)
        self.region_combo.clear()
        if not isinstance(scope_name, str):
            self.part_value.setText("-")
            self.region_combo.blockSignals(False)
            self._refresh_state_feedback()
            return
        scope = self._scopes_by_name.get(scope_name)
        self.part_value.setText("-" if scope is None else scope.part_name)
        candidates = self._targets_by_scope.get(scope_name, [])
        for candidate in candidates:
            self.region_combo.addItem(candidate.region_name, candidate.region_name)
        if preferred_region is not None:
            region_index = self.region_combo.findData(preferred_region)
            if region_index >= 0:
                self.region_combo.setCurrentIndex(region_index)
            elif candidates:
                self.region_combo.setCurrentIndex(-1)
        elif candidates:
            self.region_combo.setCurrentIndex(-1)
        self.region_combo.blockSignals(False)
        self.region_combo.setEnabled(bool(candidates))
        self._refresh_state_feedback()

    def _refresh_state_feedback(self) -> None:
        """同步空状态提示、部件显示与 Apply 按钮状态。"""

        section_name = self.section_combo.currentData()
        scope_name = self.scope_combo.currentData()
        region_name = self.region_combo.currentData()

        if not self._section_names:
            self.empty_state_label.setText("No sections are available. Create a section first.")
            self.empty_state_label.setVisible(True)
            self.form_container.setEnabled(False)
            self.apply_button.setEnabled(False)
            self.part_value.setText("-")
            return

        if not self._scopes_by_name or not any(self._targets_by_scope.values()):
            self.empty_state_label.setText("No assignable element regions are available in the current model.")
            self.empty_state_label.setVisible(True)
            self.form_container.setEnabled(False)
            self.apply_button.setEnabled(False)
            self.part_value.setText("-")
            return

        self.form_container.setEnabled(True)
        if not isinstance(scope_name, str):
            self.empty_state_label.setText("Select a scope to filter the available regions.")
            self.empty_state_label.setVisible(True)
            self.apply_button.setEnabled(False)
            return

        if not self._targets_by_scope.get(scope_name):
            self.empty_state_label.setText(f"Scope {scope_name} currently has no assignable regions.")
            self.empty_state_label.setVisible(True)
            self.apply_button.setEnabled(False)
            return

        if not isinstance(section_name, str):
            self.empty_state_label.setText("Select a section before applying the assignment.")
            self.empty_state_label.setVisible(True)
            self.apply_button.setEnabled(False)
            return

        if not isinstance(region_name, str):
            self.empty_state_label.setText(f"Select a region under scope {scope_name} before applying.")
            self.empty_state_label.setVisible(True)
            self.apply_button.setEnabled(False)
            return

        self.empty_state_label.setVisible(False)
        self.empty_state_label.setText("")
        self.apply_button.setEnabled(True)

    def _apply_assignment(self) -> None:
        """提交截面分配。"""

        section_name = self.section_combo.currentData()
        scope_name = self.scope_combo.currentData()
        region_name = self.region_combo.currentData()
        if not isinstance(section_name, str):
            QMessageBox.information(self, "Assign Section", "Select a section before applying the assignment.")
            return
        if not isinstance(scope_name, str):
            QMessageBox.information(self, "Assign Section", "Select a scope before applying the assignment.")
            return
        if not isinstance(region_name, str):
            QMessageBox.information(self, "Assign Section", "Select a valid region before applying the assignment.")
            return
        try:
            self.presenter.assign_section(
                section_name,
                scope_name=scope_name,
                region_name=region_name,
            )
        except Exception as error:  # noqa: BLE001
            QMessageBox.critical(self, "Assign Section", str(error))
            return
        self._assignment_context = SectionAssignmentContext(
            preferred_section_name=section_name,
            preferred_scope_name=scope_name,
            preferred_region_name=region_name,
            preferred_part_name=self.part_value.text(),
        )
        self.modelChanged.emit("section", section_name, "assigned")
        QMessageBox.information(
            self,
            "Assign Section",
            f"Section {section_name} is now assigned to {scope_name}:{region_name}.",
        )
