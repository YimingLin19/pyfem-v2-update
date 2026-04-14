"""GUI 后处理消费链接入集成 smoke 测试。"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pyfem.gui.results_display import DISPLAY_MODE_CONTOUR_DEFORMED
from pyfem.gui.main_window import PyFEMMainWindow
from pyfem.gui.result_field_presentation import COMMON_VARIANT_KEY
from pyfem.io import FIELD_KEY_S_AVG, FIELD_KEY_S_REC, FIELD_KEY_U
from tests.gui_test_support import FakeGuiShell, get_application, set_combo_data, wait_for


class GuiMainWindowPostprocessingIntegrationTests(unittest.TestCase):
    """验证主窗口正式串起结果浏览、viewport 和 probe。"""

    def test_navigation_panel_hides_value_column_for_model_and_results_tree(self) -> None:
        app = get_application()
        shell = FakeGuiShell()
        window = PyFEMMainWindow(shell=shell, enable_pyvista_preview=False)
        try:
            window.show()
            app.processEvents()

            self.assertTrue(window.navigation_panel.model_tree.isColumnHidden(1))
            self.assertTrue(window.navigation_panel.model_tree.isHeaderHidden())
            self.assertTrue(window.navigation_panel.results_tree.isColumnHidden(1))
            self.assertTrue(window.navigation_panel.results_tree.isHeaderHidden())
        finally:
            window.close()
            app.processEvents()

    def test_run_job_followed_by_results_consumption_keeps_gui_semantics_consistent(self) -> None:
        app = get_application()
        shell = FakeGuiShell()
        window = PyFEMMainWindow(shell=shell, enable_pyvista_preview=False)
        try:
            window.show()
            app.processEvents()
            window.input_path_edit.setText("semantic.inp")
            self.assertIsNotNone(window.load_model_from_editor())
            self.assertTrue(window.run_job())
            wait_for(lambda: window._active_task is None and window.results_browser.current_field_name is not None)

            self.assertEqual(window.module_combo.currentData(), "Visualization")
            self.assertFalse(window.optional_results_dock.isVisible())
            self.assertEqual(window.navigation_panel.navigation_tabs.currentWidget(), window.navigation_panel.results_tab)
            self.assertEqual(window.results_browser.current_field_name, FIELD_KEY_U)
            self.assertEqual(window.viewport_host.current_field_name, FIELD_KEY_U)
            self.assertEqual(window.display_mode_combo.currentData(), DISPLAY_MODE_CONTOUR_DEFORMED)
            self.assertEqual(window.context_field_combo.currentData(), "displacement")
            self.assertEqual(window.context_field_variant_combo.currentData(), COMMON_VARIANT_KEY)
            self.assertGreaterEqual(window.navigation_panel.results_tree.topLevelItemCount(), 5)
            self.assertEqual(window.results_browser.histories_table.rowCount(), 1)
            self.assertEqual(window.results_browser.summaries_table.rowCount(), 1)
            self.assertIn("fake monitor message", window.log_text_edit.toPlainText())

            window.navigation_panel.select_results(step_name="STEP-1", frame_id=0, field_name=FIELD_KEY_S_REC)
            window.navigation_panel.results_tree.itemSelectionChanged.emit()
            app.processEvents()
            self.assertEqual(window.results_browser.current_field_name, FIELD_KEY_S_REC)
            self.assertEqual(window.context_field_combo.currentData(), "stress")
            self.assertEqual(window.context_field_variant_combo.currentData(), FIELD_KEY_S_REC)
            self.assertEqual(window.viewport_host.current_field_name, FIELD_KEY_S_REC)

            set_combo_data(window.context_field_combo, "stress")
            app.processEvents()
            set_combo_data(window.context_field_variant_combo, FIELD_KEY_S_AVG)
            app.processEvents()
            self.assertEqual(window.results_browser.current_field_name, FIELD_KEY_S_AVG)
            self.assertEqual(window.viewport_host.current_field_name, FIELD_KEY_S_AVG)
            self.assertIn("当前结果: 应力", window.current_results_value.text())
            self.assertIn("正式字段: S_AVG", window.current_results_value.text())

            window.probe_action.trigger()
            app.processEvents()
            set_combo_data(window.probe_kind_combo, "averaged")
            app.processEvents()
            self.assertTrue(window.probe_dialog.isVisible())
            self.assertTrue(window.run_probe_button.isEnabled())
        finally:
            window.close()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
