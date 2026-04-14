"""Step 管理器与编辑弹窗 GUI 流程测试。"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from pyfem.gui.load_manager_dialogs import StepManagerDialog
from pyfem.gui.main_window import PyFEMMainWindow
from pyfem.gui.model_edit_dialogs import OutputRequestEditDialog, StepEditDialog
from pyfem.gui.shell import GuiShell
from pyfem.io import InpExporter
from tests.gui_test_support import get_application, set_combo_data, wait_for
from tests.support.model_builders import build_dual_instance_beam_model


class StepManagerDialogGuiTests(unittest.TestCase):
    """验证 Step 模块 manager 风格入口与真实操作路径。"""

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
        input_path = Path("tests") / f"_tmp_step_manager_{uuid4().hex}.inp"
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

    def _schedule_step_dialog_completion(
        self,
        *,
        procedure_type: str,
        nlgeom: bool = False,
        line_search: bool = False,
    ) -> None:
        def callback() -> None:
            dialog = self._find_visible_dialog(StepEditDialog)
            if dialog is None:
                QTimer.singleShot(0, callback)
                return
            set_combo_data(dialog.procedure_type_combo, procedure_type)
            self.app.processEvents()
            if procedure_type == "static_nonlinear":
                dialog.nlgeom_checkbox.setChecked(nlgeom)
                dialog.initial_increment_edit.setText("0.1")
                dialog.max_increments_edit.setText("20")
                dialog.min_increment_edit.setText("1.0e-6")
                dialog.max_iterations_edit.setText("15")
                dialog.residual_tolerance_edit.setText("1.0e-8")
                dialog.displacement_tolerance_edit.setText("1.0e-6")
                dialog.allow_cutback_checkbox.setChecked(True)
                dialog.line_search_checkbox.setChecked(line_search)
            elif procedure_type == "modal":
                dialog.num_modes_edit.setText("3")
            elif procedure_type == "implicit_dynamic":
                dialog.time_step_edit.setText("0.001")
                dialog.total_time_edit.setText("0.01")
            dialog.ok_button.click()

        QTimer.singleShot(0, callback)

    def test_step_manager_create_flow_updates_manager_list_and_refreshes_views(self) -> None:
        input_path = self._load_model_from_export()
        try:
            self.window.open_step_manager_action.trigger()
            self.app.processEvents()
            manager = self.window._step_manager_dialog
            self.assertIsInstance(manager, StepManagerDialog)

            with (
                patch("pyfem.gui.load_manager_dialogs.QInputDialog.getText", return_value=("step-new", True)),
                patch.object(self.window.viewport_host, "show_model_geometry", wraps=self.window.viewport_host.show_model_geometry) as geometry_refresh,
            ):
                self._schedule_step_dialog_completion(procedure_type="static_linear")
                manager.create_button.click()
                self.app.processEvents()

            updated_model = self.shell.clone_loaded_model()
            self.assertIn("step-new", updated_model.steps)
            self.assertEqual(updated_model.steps["step-new"].procedure_type, "static_linear")
            listed_names = [manager.name_list.item(index).text() for index in range(manager.name_list.count())]
            self.assertTrue(any("step-new [Static Linear]" in item for item in listed_names))
            self.assertGreaterEqual(geometry_refresh.call_count, 1)
        finally:
            input_path.unlink(missing_ok=True)

    def test_step_manager_edit_copy_rename_and_delete_flow_work(self) -> None:
        input_path = self._load_model_from_export()
        try:
            self.window.open_step_manager_action.trigger()
            self.app.processEvents()
            manager = self.window._step_manager_dialog
            self.assertIsNotNone(manager)

            manager.select_name("step-static")
            self._schedule_step_dialog_completion(
                procedure_type="static_nonlinear",
                nlgeom=True,
                line_search=True,
            )
            manager.edit_button.click()
            self.app.processEvents()

            updated_step = self.shell.clone_loaded_model().steps["step-static"]
            self.assertEqual(updated_step.procedure_type, "static_nonlinear")
            self.assertTrue(bool(updated_step.parameters["nlgeom"]))
            self.assertTrue(bool(updated_step.parameters["line_search"]))

            with patch("pyfem.gui.load_manager_dialogs.QInputDialog.getText", return_value=("step-copy", True)):
                manager.copy_button.click()
                self.app.processEvents()
            self.assertIn("step-copy", self.shell.clone_loaded_model().steps)

            manager.select_name("step-copy")
            with patch("pyfem.gui.load_manager_dialogs.QInputDialog.getText", return_value=("step-renamed", True)):
                manager.rename_button.click()
                self.app.processEvents()
            self.assertIn("step-renamed", self.shell.clone_loaded_model().steps)
            self.assertNotIn("step-copy", self.shell.clone_loaded_model().steps)

            manager.select_name("step-renamed")
            with patch(
                "pyfem.gui.load_manager_dialogs.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ):
                manager.delete_button.click()
                self.app.processEvents()
            self.assertNotIn("step-renamed", self.shell.clone_loaded_model().steps)
        finally:
            input_path.unlink(missing_ok=True)

    def test_manager_edit_tree_double_click_and_edit_selected_keep_object_level_entry(self) -> None:
        input_path = self._load_model_from_export()
        try:
            self.window.open_step_manager_action.trigger()
            self.app.processEvents()
            manager = self.window._step_manager_dialog
            self.assertIsNotNone(manager)

            captured_dialogs: list[QDialog] = []

            def capture_dialog(factory) -> bool:
                dialog = factory()
                captured_dialogs.append(dialog)
                return False

            manager.select_name("step-static")
            with patch.object(manager, "_run_edit_dialog", side_effect=capture_dialog):
                manager.edit_button.click()

            self.assertTrue(any(isinstance(dialog, StepEditDialog) for dialog in captured_dialogs))

            self.window.navigation_panel.select_model_entry("step", "step-static")
            self.app.processEvents()
            current_item = self.window.navigation_panel.model_tree.currentItem()
            self.assertIsNotNone(current_item)
            self.window.navigation_panel.model_tree.itemDoubleClicked.emit(current_item, 0)
            self.app.processEvents()
            self.assertIsInstance(self.window._active_model_edit_dialog, StepEditDialog)

            self.window.edit_selected_action.trigger()
            self.app.processEvents()
            self.assertIsInstance(self.window._active_model_edit_dialog, StepEditDialog)
        finally:
            input_path.unlink(missing_ok=True)

    def test_delete_protection_blocks_job_referenced_and_last_remaining_step(self) -> None:
        input_path = self._load_model_from_export()
        try:
            self.window.open_step_manager_action.trigger()
            self.app.processEvents()
            manager = self.window._step_manager_dialog
            self.assertIsNotNone(manager)

            manager.select_name("step-static")
            with (
                patch("pyfem.gui.load_manager_dialogs.QMessageBox.warning") as warning_box,
                patch("pyfem.gui.load_manager_dialogs.QMessageBox.question") as question_box,
            ):
                manager.delete_button.click()
                self.app.processEvents()
            warning_box.assert_called_once()
            question_box.assert_not_called()

            model = self.shell.clone_loaded_model()
            model.job = None
            self.shell.replace_loaded_model(model, mark_dirty=False)
            manager.refresh(selected_name="step-static")

            with (
                patch("pyfem.gui.load_manager_dialogs.QMessageBox.warning") as warning_box,
                patch("pyfem.gui.load_manager_dialogs.QMessageBox.question") as question_box,
            ):
                manager.delete_button.click()
                self.app.processEvents()
            warning_box.assert_called_once()
            question_box.assert_not_called()
        finally:
            input_path.unlink(missing_ok=True)

    def test_output_controls_path_and_lifecycle_are_safe(self) -> None:
        input_path = self._load_model_from_export()
        try:
            self.window.navigation_panel.select_model_entry("output_request", "field-u")
            self.app.processEvents()
            self.window.open_step_output_controls_action.trigger()
            self.app.processEvents()
            self.assertIsInstance(self.window._active_model_edit_dialog, OutputRequestEditDialog)

            self.window.open_step_manager_action.trigger()
            self.app.processEvents()
            manager = self.window._step_manager_dialog
            self.assertIsNotNone(manager)

            child_dialog = QDialog(manager)
            child_dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            child_dialog.show()
            manager._active_edit_dialog = child_dialog
            destroyed_markers: list[str] = []
            child_dialog.destroyed.connect(lambda *_args: destroyed_markers.append("manager-child"))

            manager.close()
            wait_for(lambda: "manager-child" in destroyed_markers)

            self.window.open_step_manager_action.trigger()
            self.app.processEvents()
            manager = self.window._step_manager_dialog
            self.assertIsNotNone(manager)

            child_dialog = QDialog(manager)
            child_dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            child_dialog.show()
            manager._active_edit_dialog = child_dialog
            child_dialog.destroyed.connect(lambda *_args: destroyed_markers.append("window-child"))

            self.window.close()
            wait_for(lambda: "window-child" in destroyed_markers)
            self.assertIsNone(self.window._step_manager_dialog)
        finally:
            input_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
