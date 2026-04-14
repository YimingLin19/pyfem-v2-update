"""Property 管理器与截面分配对话框 GUI 流程测试。"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QDialog

from pyfem.gui.main_window import PyFEMMainWindow
from pyfem.gui.model_edit_dialogs import MaterialEditDialog, SectionEditDialog
from pyfem.gui.property_manager_dialogs import MaterialManagerDialog
from pyfem.gui.shell import GuiShell
from pyfem.io import InpExporter
from tests.gui_test_support import get_application, set_combo_data, wait_for
from tests.support.model_builders import build_dual_instance_beam_model


class PropertyManagerDialogGuiTests(unittest.TestCase):
    """验证 Property 模块的正式 manager 与对话框用户路径。"""

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
        input_path = Path("tests") / f"_tmp_property_manager_{uuid4().hex}.inp"
        InpExporter().export(build_dual_instance_beam_model(), input_path)
        self.window.input_path_edit.setText(str(input_path))
        self.assertIsNotNone(self.window.load_model_from_editor())
        self.app.processEvents()
        return input_path

    def _load_model_direct(self, model_name: str, model) -> None:
        source_path = Path("tests") / f"{model_name}.inp"
        self.shell.replace_loaded_model(model, source_path=source_path, mark_dirty=False)
        first_part_name = next(iter(model.parts.keys()))
        self.window._refresh_model_views_after_change(
            preferred_kind="part",
            preferred_name=first_part_name,
            status_text=f"model loaded: {model.name}",
            module_name="Part",
        )
        self.app.processEvents()

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

    def _schedule_material_dialog_completion(self, *, young_modulus: str) -> None:
        def callback() -> None:
            dialog = self._find_visible_dialog(MaterialEditDialog)
            if dialog is None:
                QTimer.singleShot(0, callback)
                return
            dialog.young_modulus_edit.setText(young_modulus)
            dialog.ok_button.click()

        QTimer.singleShot(0, callback)

    def _schedule_section_dialog_property_flow(
        self,
        *,
        expected_material_name: str,
        created_material_modulus: str,
        edited_material_modulus: str,
    ) -> None:
        def callback() -> None:
            dialog = self._find_visible_dialog(SectionEditDialog)
            if dialog is None:
                QTimer.singleShot(0, callback)
                return

            self.assertFalse(dialog.material_name_combo.isEnabled())
            self.assertFalse(dialog.material_edit_button.isEnabled())
            self.assertTrue(dialog.material_new_button.isEnabled())
            self.assertIn("No materials are available", dialog.material_hint_label.text())

            self._schedule_material_dialog_completion(young_modulus=created_material_modulus)
            dialog.material_new_button.click()

            self.assertEqual(dialog.material_name_combo.currentData(), expected_material_name)
            self.assertTrue(dialog.material_name_combo.isEnabled())
            self.assertTrue(dialog.material_edit_button.isEnabled())

            self._schedule_material_dialog_completion(young_modulus=edited_material_modulus)
            dialog.material_edit_button.click()

            self.assertEqual(dialog.material_name_combo.currentData(), expected_material_name)
            dialog.ok_button.click()

        QTimer.singleShot(0, callback)

    def test_section_edit_dialog_uses_material_combo_box(self) -> None:
        input_path = self._load_model_from_export()
        try:
            dialog = SectionEditDialog(self.window, self.window.model_edit_presenter, "sec-1")
            self.assertIsInstance(dialog.material_name_combo, QComboBox)
            self.assertEqual(dialog.material_name_combo.currentData(), "mat-1")
            self.assertTrue(dialog.material_name_combo.isEnabled())
            self.assertTrue(dialog.material_new_button.isEnabled())
            self.assertTrue(dialog.material_edit_button.isEnabled())
        finally:
            input_path.unlink(missing_ok=True)

    def test_section_edit_dialog_reports_material_empty_state(self) -> None:
        model = build_dual_instance_beam_model()
        model.materials.clear()
        model.sections["sec-1"].material_name = None
        self._load_model_direct("section-no-materials", model)

        dialog = SectionEditDialog(self.window, self.window.model_edit_presenter, "sec-1")
        self.assertFalse(dialog.material_name_combo.isEnabled())
        self.assertTrue(dialog.material_new_button.isEnabled())
        self.assertFalse(dialog.material_edit_button.isEnabled())
        self.assertIn("No materials are available", dialog.material_hint_label.text())

    def test_assign_section_dialog_reports_missing_sections(self) -> None:
        model = build_dual_instance_beam_model()
        model.sections.clear()
        self._load_model_direct("no-sections", model)

        self.window._open_assign_section_dialog()
        self.app.processEvents()

        dialog = self.window._assign_section_dialog
        self.assertIsNotNone(dialog)
        self.assertIn("No sections are available", dialog.empty_state_label.text())
        self.assertFalse(dialog.apply_button.isEnabled())

    def test_assign_section_dialog_reports_missing_regions(self) -> None:
        model = build_dual_instance_beam_model()
        for part in model.parts.values():
            part.mesh.element_sets.clear()
        model.sections["sec-1"].region_name = None
        self._load_model_direct("no-regions", model)

        self.window._open_assign_section_dialog()
        self.app.processEvents()

        dialog = self.window._assign_section_dialog
        self.assertIsNotNone(dialog)
        self.assertIn("No assignable element regions", dialog.empty_state_label.text())
        self.assertFalse(dialog.apply_button.isEnabled())

    def test_material_create_flow_updates_manager_and_closes_cleanly(self) -> None:
        input_path = self._load_model_from_export()
        try:
            self.window.open_material_manager_action.trigger()
            self.app.processEvents()

            manager = self.window._material_manager_dialog
            self.assertIsInstance(manager, MaterialManagerDialog)

            with patch("pyfem.gui.property_manager_dialogs.QInputDialog.getText", return_value=("mat-flow-a", True)):
                self._schedule_material_dialog_completion(young_modulus="123456.0")
                manager.create_button.click()
                self.app.processEvents()

            material_names = self.window.model_edit_presenter.list_material_names()
            self.assertIn("mat-flow-a", material_names)
            listed_names = [manager.name_list.item(index).text() for index in range(manager.name_list.count())]
            self.assertIn("mat-flow-a", listed_names)
            self.assertIsNone(self._find_visible_dialog(MaterialEditDialog))

            manager.close()
            wait_for(lambda: self.window._material_manager_dialog is None)

            self.window.close()
            self.app.processEvents()

            self.assertIsNone(self.window._material_manager_dialog)
            self.assertIsNone(self.window._active_model_edit_dialog)
            self.assertFalse(self.window.isVisible())
        finally:
            input_path.unlink(missing_ok=True)

    def test_section_create_then_assign_flow_updates_model_and_refreshes_views(self) -> None:
        model = build_dual_instance_beam_model()
        model.materials.clear()
        model.sections.clear()
        self._load_model_direct("property-flow-b", model)

        self.window.open_section_manager_action.trigger()
        self.app.processEvents()
        manager = self.window._section_manager_dialog
        self.assertIsNotNone(manager)

        with (
            patch(
                "pyfem.gui.property_manager_dialogs.QInputDialog.getText",
                side_effect=[("sec-flow-b", True), ("mat-flow-b", True)],
            ),
            patch("pyfem.gui.property_manager_dialogs.QInputDialog.getItem", return_value=("Beam", True)),
        ):
            self._schedule_section_dialog_property_flow(
                expected_material_name="mat-flow-b",
                created_material_modulus="210000.0",
                edited_material_modulus="345678.0",
            )
            manager.create_button.click()
            self.app.processEvents()

        current_model = self.shell.clone_loaded_model()
        self.assertIn("mat-flow-b", current_model.materials)
        self.assertIn("sec-flow-b", current_model.sections)
        self.assertEqual(current_model.materials["mat-flow-b"].parameters["young_modulus"], 345678.0)
        self.assertEqual(current_model.sections["sec-flow-b"].material_name, "mat-flow-b")

        self.window.assign_section_action.trigger()
        self.app.processEvents()
        dialog = self.window._assign_section_dialog
        self.assertIsNotNone(dialog)
        self.assertEqual(dialog.section_combo.currentData(), "sec-flow-b")
        self.assertEqual(dialog.scope_combo.currentData(), "left")
        self.assertEqual(dialog.region_combo.currentData(), "beam-set")
        self.assertTrue(dialog.apply_button.isEnabled())

        set_combo_data(dialog.scope_combo, "right")
        self.app.processEvents()
        self.assertEqual(dialog.part_value.text(), "beam-part")
        self.assertEqual(dialog.region_combo.count(), 1)
        self.assertIsNone(dialog.region_combo.currentData())
        self.assertFalse(dialog.apply_button.isEnabled())

        set_combo_data(dialog.region_combo, "beam-set")
        self.app.processEvents()
        self.assertTrue(dialog.apply_button.isEnabled())

        with (
            patch.object(self.window.viewport_host, "show_model_geometry", wraps=self.window.viewport_host.show_model_geometry) as geometry_refresh,
            patch("pyfem.gui.property_manager_dialogs.QMessageBox.information") as info_box,
        ):
            dialog.apply_button.click()
            self.app.processEvents()

        updated_model = self.shell.clone_loaded_model()
        self.assertEqual(updated_model.sections["sec-flow-b"].scope_name, "right")
        self.assertEqual(updated_model.sections["sec-flow-b"].region_name, "beam-set")
        self.assertGreaterEqual(geometry_refresh.call_count, 1)
        info_box.assert_called()

    def test_material_manager_close_also_closes_active_child_dialog(self) -> None:
        input_path = self._load_model_from_export()
        try:
            manager = MaterialManagerDialog(self.window, self.window.model_edit_presenter)
            manager.show()
            self.app.processEvents()

            child_dialog = QDialog(manager)
            child_dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            child_dialog.show()
            manager._active_edit_dialog = child_dialog

            destroyed: list[str] = []
            child_dialog.destroyed.connect(lambda *_args: destroyed.append("child"))

            manager.close()
            wait_for(lambda: "child" in destroyed)
        finally:
            input_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
