"""模型编辑弹窗 GUI 行为测试。"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pyfem.gui.main_window import PyFEMMainWindow
from pyfem.gui.model_edit_dialogs import MaterialEditDialog, StepEditDialog
from pyfem.gui.shell import GuiShell
from pyfem.io import InpExporter
from tests.gui_test_support import get_application
from tests.support.solid_finite_strain_j2_builders import build_c3d8_j2_model


class ModelEditDialogGuiTests(unittest.TestCase):
    """验证编辑弹窗的 Apply / OK / Cancel 与 dirty 刷新行为。"""

    def test_cancel_apply_and_ok_follow_formal_writeback_semantics(self) -> None:
        app = get_application()
        input_path = Path("tests") / f"_tmp_gui_edit_{uuid4().hex}.inp"
        shell = GuiShell()
        exporter = InpExporter()
        exporter.export(
            build_c3d8_j2_model(
                model_name="gui-edit-model",
                nlgeom=False,
                right_displacement=0.004,
                include_material_fields=True,
            ),
            input_path,
        )
        window = PyFEMMainWindow(shell=shell, enable_pyvista_preview=False)
        try:
            window.input_path_edit.setText(str(input_path))
            self.assertIsNotNone(window.load_model_from_editor())
            original_modulus = shell.clone_loaded_model().materials["mat-j2"].parameters["young_modulus"]

            window._open_model_edit_dialog("material", "mat-j2")
            app.processEvents()
            self.assertIsInstance(window._active_model_edit_dialog, MaterialEditDialog)
            material_dialog = window._active_model_edit_dialog
            material_dialog.young_modulus_edit.setText("123456.0")
            material_dialog.cancel_button.click()
            app.processEvents()

            self.assertEqual(shell.clone_loaded_model().materials["mat-j2"].parameters["young_modulus"], original_modulus)
            self.assertFalse(shell.state.model_dirty)

            window._open_model_edit_dialog("material", "mat-j2")
            app.processEvents()
            material_dialog = window._active_model_edit_dialog
            material_dialog.young_modulus_edit.setText("123456.0")
            material_dialog.apply_button.click()
            app.processEvents()

            self.assertEqual(shell.clone_loaded_model().materials["mat-j2"].parameters["young_modulus"], 123456.0)
            self.assertTrue(shell.state.model_dirty)
            self.assertEqual(window.model_dirty_value.text(), "dirty")
            self.assertIn("stale", window.footer_results_label.text())

            window._open_model_edit_dialog("step", "step-static")
            app.processEvents()
            self.assertIsInstance(window._active_model_edit_dialog, StepEditDialog)
            step_dialog = window._active_model_edit_dialog
            step_dialog.nlgeom_checkbox.setChecked(True)
            step_dialog.line_search_checkbox.setChecked(True)
            step_dialog.ok_button.click()
            app.processEvents()

            step = shell.clone_loaded_model().steps["step-static"]
            self.assertTrue(bool(step.parameters["nlgeom"]))
            self.assertTrue(bool(step.parameters["line_search"]))
            self.assertEqual(window.navigation_panel.model_status_label.text().split("|")[0].strip(), "模型: gui-edit-model")
        finally:
            window.close()
            app.processEvents()
            input_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
