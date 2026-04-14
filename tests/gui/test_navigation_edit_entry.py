"""模型树编辑入口 GUI 测试。"""

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


class NavigationEditEntryGuiTests(unittest.TestCase):
    """验证模型树双击与菜单动作可以打开对应编辑弹窗。"""

    def test_double_click_and_edit_selected_action_open_matching_dialogs(self) -> None:
        app = get_application()
        input_path = Path("tests") / f"_tmp_navigation_edit_{uuid4().hex}.inp"
        shell = GuiShell()
        InpExporter().export(
            build_c3d8_j2_model(
                model_name="navigation-edit-model",
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

            window.navigation_panel.select_model_entry("material", "mat-j2")
            item = window.navigation_panel.model_tree.currentItem()
            self.assertIsNotNone(item)
            window.navigation_panel.model_tree.itemDoubleClicked.emit(item, 0)
            app.processEvents()
            self.assertIsInstance(window._active_model_edit_dialog, MaterialEditDialog)

            window.navigation_panel.select_model_entry("step", "step-static")
            window.edit_selected_action.trigger()
            app.processEvents()
            self.assertIsInstance(window._active_model_edit_dialog, StepEditDialog)
        finally:
            window.close()
            app.processEvents()
            input_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
