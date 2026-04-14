"""GUI 后处理消费层单元 smoke 测试。"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QWidget

from pyfem.gui.main_window import PyFEMMainWindow
from pyfem.gui.result_field_presentation import COMMON_VARIANT_KEY
from pyfem.gui.results_browser import ResultsBrowser
from pyfem.gui.viewport import (
    ResultsViewportHost,
    _load_pyvista_backend,
    _resolve_qt_interactor_binding_error,
)
from pyfem.io import FIELD_KEY_S, FIELD_KEY_S_AVG, FIELD_KEY_S_IP, FIELD_KEY_U, RESULT_SOURCE_AVERAGED, RESULT_SOURCE_DERIVED, RESULT_SOURCE_RAW, RESULT_SOURCE_RECOVERED
from tests.gui_test_support import FakeGuiShell, build_semantic_results_view_context, get_application, set_combo_data, wait_for


class GuiPostprocessingSmokeTests(unittest.TestCase):
    """验证 GUI 正式消费新的结果语义。"""

    def test_viewport_qt_binding_matches_pyside6_when_preview_is_available(self) -> None:
        _loaded_pyvista, qt_interactor, import_error = _load_pyvista_backend()
        if qt_interactor is None:
            self.assertIsNotNone(import_error)
            return
        self.assertIsNone(_resolve_qt_interactor_binding_error(qt_interactor))
        self.assertTrue(qt_interactor.mro()[2].__module__.startswith("PySide6."))

    def test_viewport_shutdown_releases_embedded_preview_widget(self) -> None:
        app = get_application()

        class FakePlotterWidget(QWidget):
            """模拟可关闭的预览控件。"""

            def __init__(self, parent: QWidget | None = None) -> None:
                super().__init__(parent)
                self.closed = False

            def close(self) -> bool:
                self.closed = True
                return super().close()

        viewport = ResultsViewportHost(enable_pyvista_preview=False)
        fake_widget = FakePlotterWidget(viewport)
        try:
            viewport._pyvista_widget = fake_widget
            viewport._stack_layout.addWidget(fake_widget)
            viewport._stack_layout.setCurrentWidget(fake_widget)

            viewport.shutdown()
            app.processEvents()

            self.assertIsNone(viewport._pyvista_widget)
            self.assertTrue(fake_widget.closed)
            self.assertIs(viewport._stack_layout.currentWidget(), viewport._placeholder_frame)
        finally:
            viewport.close()
            app.processEvents()

    def test_results_browser_shows_semantic_field_history_and_summary_information(self) -> None:
        app = get_application()
        browser = ResultsBrowser()
        try:
            browser.set_results_facade(build_semantic_results_view_context().results_facade, preferred_step_name="STEP-1")
            app.processEvents()

            self.assertEqual(browser.current_step_name, "STEP-1")
            self.assertEqual(browser.frames_table.rowCount(), 1)
            self.assertEqual(browser.fields_table.rowCount(), 8)
            self.assertEqual(browser.histories_table.rowCount(), 1)
            self.assertEqual(browser.summaries_table.rowCount(), 1)
            self.assertEqual(browser.current_field_name, FIELD_KEY_U)

            source_types = {browser.fields_table.item(row, 3).text() for row in range(browser.fields_table.rowCount())}
            positions = {browser.fields_table.item(row, 4).text() for row in range(browser.fields_table.rowCount())}
            self.assertTrue({RESULT_SOURCE_RAW, RESULT_SOURCE_RECOVERED, RESULT_SOURCE_AVERAGED, RESULT_SOURCE_DERIVED}.issubset(source_types))
            self.assertIn("NODE_AVERAGED", positions)
            self.assertIn("INTEGRATION_POINT", positions)

            root = browser.step_overview_tree.topLevelItem(0)
            overview_labels = {root.child(index).text(0) for index in range(root.childCount())}
            self.assertIn("恢复场", overview_labels)
            self.assertIn("平均场", overview_labels)
            self.assertIn("派生场", overview_labels)

            browser.select_field(FIELD_KEY_S_AVG)
            browser.results_tabs.setCurrentWidget(browser.fields_table)
            app.processEvents()
            self.assertIn("averaging_groups", browser.details_text_edit.toPlainText())
        finally:
            browser.close()
            app.processEvents()

    def test_loading_model_no_longer_prompts_user_to_click_preview(self) -> None:
        app = get_application()
        window = PyFEMMainWindow(shell=FakeGuiShell(), enable_pyvista_preview=True)
        try:
            window.show()
            app.processEvents()
            window.input_path_edit.setText("semantic.inp")
            self.assertIsNotNone(window.load_model_from_editor())
            app.processEvents()

            self.assertNotIn("Click Preview", window.viewport_host.placeholder_label.text())
            self.assertNotIn("Click Enable Preview", window.viewport_host.status_label.text())
        finally:
            window.close()
            app.processEvents()

    def test_main_window_supports_field_switch_component_switch_and_legend_lock(self) -> None:
        app = get_application()
        window = PyFEMMainWindow(shell=FakeGuiShell(), enable_pyvista_preview=False)
        try:
            window.show()
            app.processEvents()
            window.input_path_edit.setText("semantic.inp")
            self.assertIsNotNone(window.load_model_from_editor())
            self.assertTrue(window.open_results_from_editor())
            wait_for(lambda: window._active_task is None and window.results_browser.current_field_name is not None)

            self.assertFalse(window.optional_results_dock.isVisible())
            self.assertEqual(window.module_combo.currentData(), "Visualization")
            self.assertEqual(window.results_browser.fields_table.rowCount(), 8)
            self.assertEqual(window.context_field_combo.currentData(), "displacement")
            self.assertEqual(window.context_field_variant_combo.currentData(), COMMON_VARIANT_KEY)
            self.assertEqual(window.context_field_combo.currentText(), "位移")
            self.assertNotIn(FIELD_KEY_U, {window.context_field_combo.itemText(index) for index in range(window.context_field_combo.count())})
            self.assertIn("当前结果: 位移", window.current_results_value.text())

            set_combo_data(window.context_field_combo, "displacement")
            app.processEvents()
            u_components = {window.viewport_host.component_combo.itemText(index) for index in range(window.viewport_host.component_combo.count())}
            self.assertTrue({"UX", "UY"}.issubset(u_components))
            self.assertNotIn("MAGNITUDE", u_components)

            set_combo_data(window.context_field_combo, "stress")
            app.processEvents()
            set_combo_data(window.context_field_variant_combo, FIELD_KEY_S_IP)
            app.processEvents()
            s_components = {window.viewport_host.component_combo.itemText(index) for index in range(window.viewport_host.component_combo.count())}
            self.assertIn("S11", s_components)
            self.assertNotIn("MISES", s_components)
            set_combo_data(window.context_field_combo, "von_mises_stress")
            app.processEvents()
            mises_components = {window.viewport_host.component_combo.itemText(index) for index in range(window.viewport_host.component_combo.count())}
            self.assertEqual(mises_components, {"MISES"})
            set_combo_data(window.viewport_host.component_combo, "MISES")
            app.processEvents()
            self.assertEqual(window.viewport_host.current_component_name, "MISES")

            set_combo_data(window.context_field_combo, "stress")
            app.processEvents()
            set_combo_data(window.context_field_variant_combo, FIELD_KEY_S_IP)
            app.processEvents()
            set_combo_data(window.display_mode_combo, "deformed")
            app.processEvents()
            set_combo_data(window.display_mode_combo, "contour_deformed")
            app.processEvents()
            self.assertEqual(window.display_mode_combo.currentData(), "contour_deformed")
            self.assertEqual(window.viewport_host.current_field_name, FIELD_KEY_S_IP)
            self.assertIn("当前结果: 应力", window.current_results_value.text())
            self.assertIn("正式字段: S_IP", window.current_results_value.text())

            window.viewport_host.legend_lock_checkbox.setChecked(True)
            window.viewport_host.legend_min_edit.setText("5.0")
            window.viewport_host.legend_max_edit.setText("15.0")
            window.viewport_host.legend_apply_button.click()
            window.viewport_host.refresh_view()
            app.processEvents()
            self.assertIn("unit=MPa", window.viewport_host.legend_unit_label.text())
            self.assertIn("locked=5", window.viewport_host.legend_range_label.text())
            self.assertIn("cmap=Rainbow", window.viewport_host.legend_range_label.text())

            window._show_legend_settings_dialog()
            app.processEvents()
            colormap_labels = {
                window.legend_settings_dialog.colormap_combo.itemText(index)
                for index in range(window.legend_settings_dialog.colormap_combo.count())
            }
            self.assertTrue({"Rainbow", "Viridis", "Plasma", "Cool to Warm", "Grayscale"}.issubset(colormap_labels))
            set_combo_data(window.legend_settings_dialog.colormap_combo, "plasma")
            window.legend_settings_dialog.apply_button.click()
            app.processEvents()
            self.assertIn("cmap=Plasma", window.viewport_host.legend_range_label.text())
        finally:
            window.close()
            app.processEvents()

    def test_probe_panel_supports_node_element_ip_and_averaged_csv_export(self) -> None:
        app = get_application()
        window = PyFEMMainWindow(shell=FakeGuiShell(), enable_pyvista_preview=False)
        csv_path = Path("tests") / f"_tmp_gui_probe_{uuid4().hex}.csv"
        try:
            window.input_path_edit.setText("semantic.inp")
            self.assertIsNotNone(window.load_model_from_editor())
            self.assertTrue(window.open_results_from_editor())
            wait_for(lambda: window._active_task is None and window.results_browser.current_field_name is not None)

            window._focus_probe_panel()
            set_combo_data(window.context_field_combo, "displacement")
            app.processEvents()
            set_combo_data(window.probe_kind_combo, "node")
            app.processEvents()
            set_combo_data(window.probe_component_combo, "UX")
            window.run_probe_button.click()
            app.processEvents()
            self.assertIn("field=U", window.probe_output_edit.toPlainText())

            set_combo_data(window.context_field_combo, "stress")
            app.processEvents()
            set_combo_data(window.context_field_variant_combo, FIELD_KEY_S)
            app.processEvents()
            set_combo_data(window.probe_kind_combo, "element")
            app.processEvents()
            window.run_probe_button.click()
            app.processEvents()
            self.assertIn("field=S", window.probe_output_edit.toPlainText())

            set_combo_data(window.context_field_combo, "stress")
            app.processEvents()
            set_combo_data(window.context_field_variant_combo, FIELD_KEY_S_IP)
            app.processEvents()
            set_combo_data(window.probe_kind_combo, "integration_point")
            app.processEvents()
            set_combo_data(window.probe_component_combo, "S11")
            window.run_probe_button.click()
            app.processEvents()
            self.assertIn("field=S_IP", window.probe_output_edit.toPlainText())

            set_combo_data(window.context_field_combo, "stress")
            app.processEvents()
            set_combo_data(window.context_field_variant_combo, FIELD_KEY_S_AVG)
            app.processEvents()
            set_combo_data(window.probe_kind_combo, "averaged")
            app.processEvents()
            self.assertGreaterEqual(window.probe_target_combo.count(), 4)
            set_combo_data(window.probe_component_combo, "S11")
            window.run_probe_button.click()
            app.processEvents()
            self.assertIn("field=S_AVG", window.probe_output_edit.toPlainText())
            self.assertIn("Probe completed", window.probe_status_value.text())

            export_path = window._export_probe_series_to_path(csv_path)
            self.assertIsNotNone(export_path)
            csv_text = csv_path.read_text(encoding="utf-8")
            self.assertIn("step_name,source_name,axis_kind,axis_value,value,field_name", csv_text)
            self.assertIn("S_AVG", csv_text)
        finally:
            window.close()
            app.processEvents()
            csv_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
