"""Load 管理器与编辑弹窗 GUI 流程测试。"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog

from pyfem.gui.load_manager_dialogs import BoundaryManagerDialog, LoadManagerDialog
from pyfem.gui.main_window import PyFEMMainWindow
from pyfem.gui.model_edit_dialogs import BoundaryEditDialog, LoadEditDialog
from pyfem.gui.shell import GuiShell
from pyfem.io import InpExporter
from tests.gui_test_support import get_application, set_combo_data, wait_for
from tests.support.model_builders import build_dual_instance_beam_model


class LoadManagerDialogGuiTests(unittest.TestCase):
    """验证 Load 模块 manager 风格入口与真实操作路径。"""

    def setUp(self) -> None:
        self.app = get_application()
        self.shell = GuiShell()
        self.window = PyFEMMainWindow(shell=self.shell, enable_pyvista_preview=False)
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        if self.window.isVisible():
            self.window.close()
        self.app.processEvents()

    def _load_model_from_export(self) -> Path:
        input_path = Path("tests") / f"_tmp_load_manager_{uuid4().hex}.inp"
        InpExporter().export(build_dual_instance_beam_model(), input_path)
        self.window.input_path_edit.setText(str(input_path))
        self.assertIsNotNone(self.window.load_model_from_editor())
        self.app.processEvents()
        return input_path

    def _find_visible_dialog(self, dialog_type: type[QDialog]) -> QDialog | None:
        def belongs_to_current_window(dialog: QDialog) -> bool:
            parent = dialog.parentWidget()
            while parent is not None:
                if parent is self.window:
                    return True
                parent = parent.parentWidget()
            return False

        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, dialog_type) and widget.isVisible() and belongs_to_current_window(widget):
                return widget
        active_modal = QApplication.activeModalWidget()
        if isinstance(active_modal, dialog_type) and belongs_to_current_window(active_modal):
            return active_modal
        return None

    def _schedule_load_dialog_completion(
        self,
        *,
        load_kind: str,
        step_name: str,
        scope_name: str,
        target_type: str,
        target_name: str,
        components_text: str = "FY=-5.0",
        load_value_text: str = "-2.5",
    ) -> None:
        def callback() -> None:
            dialog = self._find_visible_dialog(LoadEditDialog)
            if dialog is None:
                QTimer.singleShot(0, callback)
                return
            set_combo_data(dialog.load_kind_combo, load_kind)
            self.app.processEvents()
            set_combo_data(dialog.step_combo, step_name)
            self.app.processEvents()
            set_combo_data(dialog.scope_combo, scope_name)
            self.app.processEvents()
            set_combo_data(dialog.target_type_combo, target_type)
            self.app.processEvents()
            set_combo_data(dialog.target_combo, target_name)
            self.app.processEvents()
            if load_kind == "nodal_load":
                dialog.components_edit.setText(components_text)
            else:
                dialog.load_value_edit.setText(load_value_text)
            dialog.ok_button.click()

        QTimer.singleShot(0, callback)

    def _schedule_boundary_dialog_completion(
        self,
        *,
        step_name: str,
        scope_name: str,
        target_type: str,
        target_name: str,
        dof_key: str,
        dof_value: str,
    ) -> None:
        def callback() -> None:
            dialog = self._find_visible_dialog(BoundaryEditDialog)
            if dialog is None:
                QTimer.singleShot(0, callback)
                return
            set_combo_data(dialog.step_combo, step_name)
            self.app.processEvents()
            set_combo_data(dialog.scope_combo, scope_name)
            self.app.processEvents()
            set_combo_data(dialog.target_type_combo, target_type)
            self.app.processEvents()
            set_combo_data(dialog.target_combo, target_name)
            self.app.processEvents()
            dialog._dof_checks[dof_key].setChecked(True)
            dialog._dof_edits[dof_key].setText(dof_value)
            dialog.ok_button.click()

        QTimer.singleShot(0, callback)

    def test_load_manager_create_flow_updates_manager_list_and_refreshes_views(self) -> None:
        input_path = self._load_model_from_export()
        try:
            self.window.open_load_manager_action.trigger()
            self.app.processEvents()
            manager = self.window._load_manager_dialog
            self.assertIsInstance(manager, LoadManagerDialog)

            with (
                patch("pyfem.gui.load_manager_dialogs.QInputDialog.getText", return_value=("load-flow-a", True)),
                patch("pyfem.gui.load_manager_dialogs.QInputDialog.getItem", return_value=("Nodal Load", True)),
                patch.object(self.window.viewport_host, "show_model_geometry", wraps=self.window.viewport_host.show_model_geometry) as geometry_refresh,
            ):
                self._schedule_load_dialog_completion(
                    load_kind="nodal_load",
                    step_name="step-static",
                    scope_name="right",
                    target_type="node_set",
                    target_name="tip",
                    components_text="FY=-7.5",
                )
                manager.create_button.click()
                self.app.processEvents()

            updated_model = self.shell.clone_loaded_model()
            self.assertIn("load-flow-a", updated_model.nodal_loads)
            self.assertIn("load-flow-a", updated_model.steps["step-static"].nodal_load_names)
            listed_names = [manager.name_list.item(index).text() for index in range(manager.name_list.count())]
            self.assertTrue(any("load-flow-a [Nodal]" in item for item in listed_names))
            self.assertGreaterEqual(geometry_refresh.call_count, 1)
        finally:
            input_path.unlink(missing_ok=True)

    def test_boundary_manager_create_flow_updates_manager_list_and_refreshes_views(self) -> None:
        input_path = self._load_model_from_export()
        try:
            self.window.open_boundary_manager_action.trigger()
            self.app.processEvents()
            manager = self.window._boundary_manager_dialog
            self.assertIsInstance(manager, BoundaryManagerDialog)

            with patch.object(self.window.viewport_host, "show_model_geometry", wraps=self.window.viewport_host.show_model_geometry) as geometry_refresh:
                with patch("pyfem.gui.load_manager_dialogs.QInputDialog.getText", return_value=("bc-flow-a", True)):
                    self._schedule_boundary_dialog_completion(
                        step_name="step-static",
                        scope_name="right",
                        target_type="node_set",
                        target_name="tip",
                        dof_key="UY",
                        dof_value="0.0",
                    )
                    manager.create_button.click()
                    self.app.processEvents()

            updated_model = self.shell.clone_loaded_model()
            self.assertIn("bc-flow-a", updated_model.boundaries)
            self.assertIn("bc-flow-a", updated_model.steps["step-static"].boundary_names)
            listed_names = [manager.name_list.item(index).text() for index in range(manager.name_list.count())]
            self.assertTrue(any("bc-flow-a [Boundary]" in item for item in listed_names))
            self.assertGreaterEqual(geometry_refresh.call_count, 1)
        finally:
            input_path.unlink(missing_ok=True)

    def test_manager_edit_and_tree_double_click_keep_object_level_edit_entry(self) -> None:
        input_path = self._load_model_from_export()
        try:
            self.window.open_load_manager_action.trigger()
            self.window.open_boundary_manager_action.trigger()
            self.app.processEvents()
            load_manager = self.window._load_manager_dialog
            boundary_manager = self.window._boundary_manager_dialog
            self.assertIsNotNone(load_manager)
            self.assertIsNotNone(boundary_manager)

            captured_dialogs: list[QDialog] = []

            def capture_dialog(factory) -> bool:
                dialog = factory()
                captured_dialogs.append(dialog)
                return False

            load_manager.select_name("load-right-tip")
            boundary_manager.select_name("bc-left-root")
            with (
                patch.object(load_manager, "_run_edit_dialog", side_effect=capture_dialog),
                patch.object(boundary_manager, "_run_edit_dialog", side_effect=capture_dialog),
            ):
                load_manager.edit_button.click()
                boundary_manager.edit_button.click()

            self.assertTrue(any(isinstance(dialog, LoadEditDialog) for dialog in captured_dialogs))
            self.assertTrue(any(isinstance(dialog, BoundaryEditDialog) for dialog in captured_dialogs))

            self.window.navigation_panel.select_model_entry("nodal_load", "load-right-tip")
            self.app.processEvents()
            current_item = self.window.navigation_panel.model_tree.currentItem()
            self.assertIsNotNone(current_item)
            self.window.navigation_panel.model_tree.itemDoubleClicked.emit(current_item, 0)
            self.app.processEvents()
            self.assertIsInstance(self.window._active_model_edit_dialog, LoadEditDialog)

            self.window.navigation_panel.select_model_entry("boundary", "bc-left-root")
            self.app.processEvents()
            current_item = self.window.navigation_panel.model_tree.currentItem()
            self.assertIsNotNone(current_item)
            self.window.navigation_panel.model_tree.itemDoubleClicked.emit(current_item, 0)
            self.app.processEvents()
            self.assertIsInstance(self.window._active_model_edit_dialog, BoundaryEditDialog)
        finally:
            input_path.unlink(missing_ok=True)

    def test_delete_protection_blocks_referenced_load_and_boundary(self) -> None:
        input_path = self._load_model_from_export()
        try:
            self.window.open_load_manager_action.trigger()
            self.window.open_boundary_manager_action.trigger()
            self.app.processEvents()
            load_manager = self.window._load_manager_dialog
            boundary_manager = self.window._boundary_manager_dialog
            self.assertIsNotNone(load_manager)
            self.assertIsNotNone(boundary_manager)

            load_manager.select_name("load-right-tip")
            boundary_manager.select_name("bc-left-root")
            with (
                patch("pyfem.gui.load_manager_dialogs.QMessageBox.warning") as load_warning,
                patch("pyfem.gui.load_manager_dialogs.QMessageBox.question") as question_box,
            ):
                load_manager.delete_button.click()
                boundary_manager.delete_button.click()
                self.app.processEvents()

            self.assertEqual(load_warning.call_count, 2)
            question_box.assert_not_called()
            current_model = self.shell.clone_loaded_model()
            self.assertIn("load-right-tip", current_model.nodal_loads)
            self.assertIn("bc-left-root", current_model.boundaries)
        finally:
            input_path.unlink(missing_ok=True)

    def test_manager_close_and_main_window_close_close_child_dialogs(self) -> None:
        input_path = self._load_model_from_export()
        try:
            self.window.open_load_manager_action.trigger()
            self.window.open_boundary_manager_action.trigger()
            self.app.processEvents()
            load_manager = self.window._load_manager_dialog
            boundary_manager = self.window._boundary_manager_dialog
            self.assertIsNotNone(load_manager)
            self.assertIsNotNone(boundary_manager)

            load_child = QDialog(load_manager)
            load_child.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            load_child.show()
            load_manager._active_edit_dialog = load_child
            load_destroyed: list[str] = []
            load_child.destroyed.connect(lambda *_args: load_destroyed.append("load"))

            load_manager.close()
            wait_for(lambda: "load" in load_destroyed)

            boundary_child = QDialog(boundary_manager)
            boundary_child.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            boundary_child.show()
            boundary_manager._active_edit_dialog = boundary_child
            boundary_destroyed: list[str] = []
            boundary_child.destroyed.connect(lambda *_args: boundary_destroyed.append("boundary"))

            self.window.close()
            wait_for(lambda: "boundary" in boundary_destroyed)

            self.assertIsNone(self.window._load_manager_dialog)
            self.assertIsNone(self.window._boundary_manager_dialog)
        finally:
            input_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
