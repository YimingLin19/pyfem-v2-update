"""Load 模块的管理器对话框。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QInputDialog, QListWidgetItem, QMessageBox, QWidget

from pyfem.gui.model_edit_dialogs import BoundaryEditDialog, LoadEditDialog, StepEditDialog
from pyfem.gui.model_edit_presenters import BoundaryEditContext, LoadEditContext, ModelEditPresenter
from pyfem.gui.property_manager_dialogs import BasePropertyManagerDialog


class BaseNamedManagerDialog(BasePropertyManagerDialog):
    """为带显示标签的管理器列表提供通用支持。"""

    NAME_ROLE = Qt.ItemDataRole.UserRole
    KIND_ROLE = Qt.ItemDataRole.UserRole + 1

    def current_name(self) -> str | None:
        """返回当前选中对象的真实名称。"""

        item = self.name_list.currentItem()
        if item is None:
            return None
        value = item.data(self.NAME_ROLE)
        return None if value in {None, ""} else str(value)

    def select_name(self, name: str | None) -> None:
        """按真实名称选中列表项。"""

        if name is None:
            self.name_list.clearSelection()
            self._refresh_action_state()
            return
        for index in range(self.name_list.count()):
            item = self.name_list.item(index)
            if item.data(self.NAME_ROLE) == name:
                self.name_list.setCurrentItem(item)
                return
        self.name_list.clearSelection()
        self._refresh_action_state()

    def current_kind(self) -> str | None:
        """返回当前选中对象的类别键。"""

        item = self.name_list.currentItem()
        if item is None:
            return None
        value = item.data(self.KIND_ROLE)
        return None if value in {None, ""} else str(value)

    def _set_display_entries(
        self,
        entries: tuple[tuple[str, str, str | None], ...],
        *,
        selected_name: str | None,
    ) -> None:
        """按显示标签刷新列表内容。"""

        self.name_list.clear()
        for name, display_label, kind in entries:
            item = QListWidgetItem(display_label)
            item.setData(self.NAME_ROLE, name)
            item.setData(self.KIND_ROLE, kind)
            self.name_list.addItem(item)
        has_items = bool(entries)
        self.empty_state_label.setVisible(not has_items)
        self.name_list.setVisible(has_items)
        if has_items:
            self.select_name(selected_name or entries[0][0])
        else:
            self.select_name(None)
        self._refresh_action_state()


class LoadManagerDialog(BaseNamedManagerDialog):
    """定义载荷管理器窗口。"""

    LOAD_TYPE_CHOICES: tuple[tuple[str, str], ...] = (
        ("Nodal Load", "nodal_load"),
        ("Distributed Load", "distributed_load"),
    )

    def __init__(self, parent: QWidget | None, presenter: ModelEditPresenter) -> None:
        super().__init__(
            parent,
            presenter,
            title="Loads",
            empty_message="No loads are available in the current model.",
        )
        self._context = LoadEditContext()
        self.caption_label.setText("Manage nodal loads and distributed loads here, then refine them in the formal editor.")
        self.refresh()

    def refresh(self, *, selected_name: str | None = None, preferred_context: LoadEditContext | None = None) -> None:
        """刷新载荷列表，并按上下文恢复选择。"""

        if preferred_context is not None:
            self._context = preferred_context
        entries = self.presenter.list_load_manager_entries()
        self._set_display_entries(
            tuple((entry.name, entry.display_label, entry.resolved_kind) for entry in entries),
            selected_name=selected_name or self._context.preferred_load_name,
        )

    def _create_item(self) -> None:
        default_name = self.presenter.suggest_new_load_name()
        load_name = self._prompt_for_name(
            title="Create Load",
            label="Load name:",
            default_value=default_name,
        )
        if load_name is None:
            return
        display_items = [label for label, _value in self.LOAD_TYPE_CHOICES]
        selected_label, accepted = QInputDialog.getItem(
            self,
            "Create Load",
            "Load type:",
            display_items,
            0,
            False,
        )
        if not accepted:
            return
        load_kind = next(value for label, value in self.LOAD_TYPE_CHOICES if label == selected_label)
        try:
            committed = self._run_edit_dialog(
                lambda: LoadEditDialog(
                    self,
                    self.presenter,
                    load_kind,
                    load_name,
                    create_mode=True,
                    edit_context=LoadEditContext(
                        preferred_load_name=load_name,
                        preferred_step_name=self._context.preferred_step_name,
                        preferred_scope_name=self._context.preferred_scope_name,
                        preferred_target_name=self._context.preferred_target_name,
                        preferred_target_type=self._context.preferred_target_type,
                        preferred_load_kind=load_kind,
                    ),
                )
            )
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Create Load", error)
            return
        if committed:
            self.refresh(selected_name=load_name)
            self.modelChanged.emit(load_kind, load_name, "created")

    def _edit_selected_item(self) -> None:
        load_name = self.current_name()
        load_kind = self.current_kind()
        if load_name is None or load_kind is None:
            return
        try:
            committed = self._run_edit_dialog(lambda: LoadEditDialog(self, self.presenter, load_kind, load_name))
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Edit Load", error)
            return
        if committed:
            self.refresh(selected_name=load_name)
            self.modelChanged.emit(load_kind, load_name, "updated")

    def _copy_selected_item(self) -> None:
        source_name = self.current_name()
        if source_name is None:
            return
        existing_names = tuple(entry.name for entry in self.presenter.list_load_manager_entries())
        target_name = self._prompt_for_name(
            title="Copy Load",
            label="New load name:",
            default_value=self.presenter.suggest_copy_name(source_name, existing_names),
        )
        if target_name is None:
            return
        try:
            self.presenter.copy_load(source_name, target_name)
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Copy Load", error)
            return
        self.refresh(selected_name=target_name)
        self.modelChanged.emit(self.presenter.resolve_kind("load", target_name), target_name, "copied")

    def _rename_selected_item(self) -> None:
        source_name = self.current_name()
        load_kind = self.current_kind()
        if source_name is None or load_kind is None:
            return
        target_name = self._prompt_for_name(
            title="Rename Load",
            label="New load name:",
            default_value=source_name,
        )
        if target_name is None or target_name == source_name:
            return
        try:
            self.presenter.rename_load(source_name, target_name)
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Rename Load", error)
            return
        self.refresh(selected_name=target_name)
        self.modelChanged.emit(load_kind, target_name, "renamed")

    def _delete_selected_item(self) -> None:
        load_name = self.current_name()
        load_kind = self.current_kind()
        if load_name is None or load_kind is None:
            return
        referenced_steps = self.presenter.load_reference_steps(load_name, resolved_kind=load_kind)
        if referenced_steps:
            joined = ", ".join(referenced_steps)
            QMessageBox.warning(
                self,
                "Delete Load",
                f"Load {load_name} is still referenced by steps: {joined}. Delete is blocked.",
            )
            return
        confirmed = QMessageBox.question(
            self,
            "Delete Load",
            f"Delete load {load_name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self.presenter.delete_load(load_name)
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Delete Load", error)
            return
        self.refresh()
        self.modelChanged.emit(load_kind, load_name, "deleted")


class BoundaryManagerDialog(BaseNamedManagerDialog):
    """定义边界管理器窗口。"""

    def __init__(self, parent: QWidget | None, presenter: ModelEditPresenter) -> None:
        super().__init__(
            parent,
            presenter,
            title="Boundaries",
            empty_message="No boundaries are available in the current model.",
        )
        self._context = BoundaryEditContext()
        self.caption_label.setText("Manage displacement boundaries here, then refine them in the formal editor.")
        self.refresh()

    def refresh(self, *, selected_name: str | None = None, preferred_context: BoundaryEditContext | None = None) -> None:
        """刷新边界列表，并按上下文恢复选择。"""

        if preferred_context is not None:
            self._context = preferred_context
        entries = self.presenter.list_boundary_manager_entries()
        self._set_display_entries(
            tuple((entry.name, entry.display_label, "boundary") for entry in entries),
            selected_name=selected_name or self._context.preferred_boundary_name,
        )

    def _create_item(self) -> None:
        default_name = self.presenter.suggest_new_boundary_name()
        boundary_name = self._prompt_for_name(
            title="Create Boundary",
            label="Boundary name:",
            default_value=default_name,
        )
        if boundary_name is None:
            return
        try:
            committed = self._run_edit_dialog(
                lambda: BoundaryEditDialog(
                    self,
                    self.presenter,
                    boundary_name,
                    create_mode=True,
                    edit_context=BoundaryEditContext(
                        preferred_boundary_name=boundary_name,
                        preferred_step_name=self._context.preferred_step_name,
                        preferred_scope_name=self._context.preferred_scope_name,
                        preferred_target_name=self._context.preferred_target_name,
                        preferred_target_type=self._context.preferred_target_type,
                    ),
                )
            )
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Create Boundary", error)
            return
        if committed:
            self.refresh(selected_name=boundary_name)
            self.modelChanged.emit("boundary", boundary_name, "created")

    def _edit_selected_item(self) -> None:
        boundary_name = self.current_name()
        if boundary_name is None:
            return
        try:
            committed = self._run_edit_dialog(lambda: BoundaryEditDialog(self, self.presenter, boundary_name))
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Edit Boundary", error)
            return
        if committed:
            self.refresh(selected_name=boundary_name)
            self.modelChanged.emit("boundary", boundary_name, "updated")

    def _copy_selected_item(self) -> None:
        source_name = self.current_name()
        if source_name is None:
            return
        existing_names = tuple(entry.name for entry in self.presenter.list_boundary_manager_entries())
        target_name = self._prompt_for_name(
            title="Copy Boundary",
            label="New boundary name:",
            default_value=self.presenter.suggest_copy_name(source_name, existing_names),
        )
        if target_name is None:
            return
        try:
            self.presenter.copy_boundary(source_name, target_name)
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Copy Boundary", error)
            return
        self.refresh(selected_name=target_name)
        self.modelChanged.emit("boundary", target_name, "copied")

    def _rename_selected_item(self) -> None:
        source_name = self.current_name()
        if source_name is None:
            return
        target_name = self._prompt_for_name(
            title="Rename Boundary",
            label="New boundary name:",
            default_value=source_name,
        )
        if target_name is None or target_name == source_name:
            return
        try:
            self.presenter.rename_boundary(source_name, target_name)
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Rename Boundary", error)
            return
        self.refresh(selected_name=target_name)
        self.modelChanged.emit("boundary", target_name, "renamed")

    def _delete_selected_item(self) -> None:
        boundary_name = self.current_name()
        if boundary_name is None:
            return
        referenced_steps = self.presenter.boundary_reference_steps(boundary_name)
        if referenced_steps:
            joined = ", ".join(referenced_steps)
            QMessageBox.warning(
                self,
                "Delete Boundary",
                f"Boundary {boundary_name} is still referenced by steps: {joined}. Delete is blocked.",
            )
            return
        confirmed = QMessageBox.question(
            self,
            "Delete Boundary",
            f"Delete boundary {boundary_name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self.presenter.delete_boundary(boundary_name)
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Delete Boundary", error)
            return
        self.refresh()
        self.modelChanged.emit("boundary", boundary_name, "deleted")


class StepManagerDialog(BaseNamedManagerDialog):
    """定义分析步管理器窗口。"""

    def __init__(self, parent: QWidget | None, presenter: ModelEditPresenter) -> None:
        super().__init__(
            parent,
            presenter,
            title="Steps",
            empty_message="No steps are available in the current model.",
        )
        self.caption_label.setText("Manage formal analysis steps here, then refine details in the step editor.")
        self.refresh()

    def refresh(self, *, selected_name: str | None = None) -> None:
        """刷新步骤列表，并尽量保持当前选择。"""

        entries = self.presenter.list_step_manager_entries()
        self._set_display_entries(
            tuple((entry.name, entry.display_label, "step") for entry in entries),
            selected_name=selected_name,
        )

    def _create_item(self) -> None:
        default_name = self.presenter.suggest_new_step_name()
        step_name = self._prompt_for_name(
            title="Create Step",
            label="Step name:",
            default_value=default_name,
        )
        if step_name is None:
            return
        try:
            committed = self._run_edit_dialog(
                lambda: StepEditDialog(
                    self,
                    self.presenter,
                    step_name,
                    create_mode=True,
                )
            )
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Create Step", error)
            return
        if committed:
            self.refresh(selected_name=step_name)
            self.modelChanged.emit("step", step_name, "created")

    def _edit_selected_item(self) -> None:
        step_name = self.current_name()
        if step_name is None:
            return
        try:
            committed = self._run_edit_dialog(lambda: StepEditDialog(self, self.presenter, step_name))
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Edit Step", error)
            return
        if committed:
            self.refresh(selected_name=step_name)
            self.modelChanged.emit("step", step_name, "updated")

    def _copy_selected_item(self) -> None:
        source_name = self.current_name()
        if source_name is None:
            return
        existing_names = tuple(entry.name for entry in self.presenter.list_step_manager_entries())
        target_name = self._prompt_for_name(
            title="Copy Step",
            label="New step name:",
            default_value=self.presenter.suggest_copy_name(source_name, existing_names),
        )
        if target_name is None:
            return
        try:
            self.presenter.copy_step(source_name, target_name)
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Copy Step", error)
            return
        self.refresh(selected_name=target_name)
        self.modelChanged.emit("step", target_name, "copied")

    def _rename_selected_item(self) -> None:
        source_name = self.current_name()
        if source_name is None:
            return
        target_name = self._prompt_for_name(
            title="Rename Step",
            label="New step name:",
            default_value=source_name,
        )
        if target_name is None or target_name == source_name:
            return
        try:
            self.presenter.rename_step(source_name, target_name)
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Rename Step", error)
            return
        self.refresh(selected_name=target_name)
        self.modelChanged.emit("step", target_name, "renamed")

    def _delete_selected_item(self) -> None:
        step_name = self.current_name()
        if step_name is None:
            return
        referenced_jobs = self.presenter.step_reference_jobs(step_name)
        if referenced_jobs:
            joined = ", ".join(referenced_jobs)
            QMessageBox.warning(
                self,
                "Delete Step",
                f"Step {step_name} is still referenced by jobs: {joined}. Delete is blocked.",
            )
            return
        if len(self.presenter.list_step_names()) <= 1:
            QMessageBox.warning(
                self,
                "Delete Step",
                "The current model must keep at least one step. Delete is blocked for the last remaining step.",
            )
            return
        confirmed = QMessageBox.question(
            self,
            "Delete Step",
            f"Delete step {step_name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self.presenter.delete_step(step_name)
        except Exception as error:  # noqa: BLE001
            self._handle_action_error("Delete Step", error)
            return
        self.refresh()
        self.modelChanged.emit("step", step_name, "deleted")
