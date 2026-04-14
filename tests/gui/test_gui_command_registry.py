"""统一 GUI 命令注册与 Property 管理器入口测试。"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QDialog

from pyfem.gui.gui_command_registry import MODULE_COMMAND_IDS
from pyfem.gui.load_manager_dialogs import BoundaryManagerDialog, LoadManagerDialog, StepManagerDialog
from pyfem.gui.main_window import PyFEMMainWindow
from pyfem.gui.model_edit_dialogs import BoundaryEditDialog, InstanceTransformDialog, LoadEditDialog, MaterialEditDialog, OutputRequestEditDialog, StepEditDialog
from pyfem.gui.property_manager_dialogs import AssignSectionDialog, MaterialManagerDialog, SectionManagerDialog
from pyfem.gui.shell import GuiShell
from pyfem.io import InpExporter
from tests.gui_test_support import get_application, set_combo_data, wait_for
from tests.support.model_builders import build_dual_instance_beam_model


class GuiCommandRegistryGuiTests(unittest.TestCase):
    """验证 toolbox、菜单栏与 Property 管理器入口协同工作。"""

    def setUp(self) -> None:
        self.app = get_application()
        self.input_path = Path("tests") / f"_tmp_gui_command_registry_{uuid4().hex}.inp"
        InpExporter().export(build_dual_instance_beam_model(), self.input_path)
        self.shell = GuiShell()
        self.window = PyFEMMainWindow(shell=self.shell, enable_pyvista_preview=False)
        self.window.show()
        self.app.processEvents()
        self.window.input_path_edit.setText(str(self.input_path))
        self.assertIsNotNone(self.window.load_model_from_editor())
        self.app.processEvents()

    def tearDown(self) -> None:
        try:
            self.window.close()
            self.app.processEvents()
        finally:
            self._cleanup_path(self.input_path)
            snapshot = self.shell.latest_snapshot()
            if snapshot is not None:
                self._cleanup_path(snapshot.snapshot_path)
                self._cleanup_path(snapshot.manifest_path)
                self._cleanup_path(snapshot.results_path)
                if snapshot.derived_case_path is not None:
                    self._cleanup_path(snapshot.derived_case_path)
            if self.shell.state.last_job_report is not None:
                self._cleanup_path(self.shell.state.last_job_report.results_path)
                self._cleanup_path(self.shell.state.last_job_report.export_path)

    def _cleanup_path(self, path: Path | None) -> None:
        if path is None:
            return
        Path(path).unlink(missing_ok=True)

    def _set_module(self, module_name: str) -> None:
        set_combo_data(self.window.module_combo, module_name)
        self.app.processEvents()

    def _select_model_entry(self, kind: str, name: str) -> None:
        self.window.navigation_panel.select_model_entry(kind, name)
        self.app.processEvents()

    def test_command_registry_shares_manager_actions_across_toolbox_and_module_menu(self) -> None:
        self._set_module("Property")
        action = self.window.command_registry.action("open_material_manager")

        self.assertIs(self.window.open_material_manager_action, action)
        self.assertIn(action, self.window.module_menus["Property"].actions())
        self.assertIn(action, self.window.module_toolbox._buttons_by_action)
        self.assertEqual(action.property("command_id"), "open_material_manager")

        material_context_actions = self.window.navigation_panel.model_context_actions_for_entry("material", "mat-1")
        self.assertIn(self.window.edit_material_action, material_context_actions)

        self._set_module("Job")
        job_center_action = self.window.command_registry.action("open_job_center")
        self.assertIs(self.window.open_job_center_action, job_center_action)
        self.assertIn(job_center_action, self.window.module_menus["Job"].actions())
        self.assertIn(job_center_action, self.window.module_toolbox._buttons_by_action)

    def test_module_toolbox_rebuilds_buttons_from_registry_mapping(self) -> None:
        previous_keys: tuple[str, ...] | None = None
        for module_name, expected_ids in MODULE_COMMAND_IDS.items():
            self._set_module(module_name)
            current_keys = tuple(self.window.module_toolbox._buttons_by_key.keys())
            self.assertEqual(current_keys, expected_ids)
            self.assertEqual(len(current_keys), len(expected_ids))
            self.assertEqual(self.window.module_toolbox.module_label.toolTip(), module_name)
            if previous_keys is not None:
                self.assertNotEqual(current_keys, previous_keys)
            previous_keys = current_keys

    def test_property_toolbox_manager_actions_open_manager_dialogs(self) -> None:
        self._set_module("Property")

        self.window.open_material_manager_action.trigger()
        self.app.processEvents()
        self.assertIsInstance(self.window._material_manager_dialog, MaterialManagerDialog)
        self.assertTrue(self.window._material_manager_dialog.isVisible())

        self.window.open_section_manager_action.trigger()
        self.app.processEvents()
        self.assertIsInstance(self.window._section_manager_dialog, SectionManagerDialog)
        self.assertTrue(self.window._section_manager_dialog.isVisible())

        self.window.assign_section_action.trigger()
        self.app.processEvents()
        self.assertIsInstance(self.window._assign_section_dialog, AssignSectionDialog)
        self.assertTrue(self.window._assign_section_dialog.isVisible())

    def test_load_toolbox_manager_actions_open_manager_dialogs(self) -> None:
        self._set_module("Load")

        self.window.open_load_manager_action.trigger()
        self.app.processEvents()
        self.assertIsInstance(self.window._load_manager_dialog, LoadManagerDialog)
        self.assertTrue(self.window._load_manager_dialog.isVisible())

        self.window.open_boundary_manager_action.trigger()
        self.app.processEvents()
        self.assertIsInstance(self.window._boundary_manager_dialog, BoundaryManagerDialog)
        self.assertTrue(self.window._boundary_manager_dialog.isVisible())

        button_keys = tuple(self.window.module_toolbox._buttons_by_key.keys())
        self.assertEqual(
            button_keys,
            ("open_load_manager", "open_boundary_manager", "open_amplitude_manager_placeholder", "validate_load_support"),
        )

    def test_step_toolbox_manager_actions_open_manager_dialogs(self) -> None:
        self._set_module("Step")

        self.window.open_step_manager_action.trigger()
        self.app.processEvents()
        self.assertIsInstance(self.window._step_manager_dialog, StepManagerDialog)
        self.assertTrue(self.window._step_manager_dialog.isVisible())

        button_keys = tuple(self.window.module_toolbox._buttons_by_key.keys())
        self.assertEqual(
            button_keys,
            ("open_step_manager", "open_step_output_controls", "open_step_diagnostics_placeholder", "validate_and_run_step_tools"),
        )

    def test_job_toolbox_uses_job_center_monitor_diagnostics_and_results_entries(self) -> None:
        self._set_module("Job")

        button_keys = tuple(self.window.module_toolbox._buttons_by_key.keys())
        self.assertEqual(
            button_keys,
            ("open_job_center", "open_current_job_monitor", "open_job_diagnostics", "open_results_output"),
        )
        self.assertEqual(self.window.open_job_center_action.text(), "Job Center...")
        self.assertEqual(self.window.open_current_job_monitor_action.text(), "Monitor Current Run...")
        self.assertEqual(self.window.open_job_diagnostics_action.text(), "Diagnostics...")
        self.assertEqual(self.window.open_results_output_action.text(), "Results / Output...")

    def test_property_toolbox_keeps_narrow_width_but_uses_compact_icons(self) -> None:
        self._set_module("Property")

        self.assertEqual(self.window.module_toolbox.minimumWidth(), self.window.module_toolbox.FIXED_WIDTH)
        self.assertEqual(self.window.module_toolbox.maximumWidth(), self.window.module_toolbox.FIXED_WIDTH)

        material_button = self.window.module_toolbox._buttons_by_key["open_material_manager"]
        assign_button = self.window.module_toolbox._buttons_by_key["assign_section"]

        self.assertEqual(material_button.iconSize().width(), 16)
        self.assertEqual(material_button.iconSize().height(), 16)
        self.assertEqual(assign_button.text(), "Assign\nSection...")
        self.assertNotEqual(material_button.icon().cacheKey(), self.window.open_material_manager_action.icon().cacheKey())

    def test_main_window_close_releases_property_dialog_references(self) -> None:
        self._set_module("Property")

        self.window.open_material_manager_action.trigger()
        self.window.open_section_manager_action.trigger()
        self.window.assign_section_action.trigger()
        self.window.open_load_manager_action.trigger()
        self.window.open_boundary_manager_action.trigger()
        self.window.open_step_manager_action.trigger()
        self._select_model_entry("material", "mat-1")
        self.window.edit_material_action.trigger()
        self.app.processEvents()

        destroyed_dialogs: list[str] = []
        for dialog_name, dialog in (
            ("material_manager", self.window._material_manager_dialog),
            ("section_manager", self.window._section_manager_dialog),
            ("assign_section", self.window._assign_section_dialog),
            ("load_manager", self.window._load_manager_dialog),
            ("boundary_manager", self.window._boundary_manager_dialog),
            ("step_manager", self.window._step_manager_dialog),
            ("active_model_edit", self.window._active_model_edit_dialog),
        ):
            self.assertIsNotNone(dialog)
            dialog.destroyed.connect(lambda *_args, key=dialog_name: destroyed_dialogs.append(key))

        self.window.close()
        wait_for(lambda: len(destroyed_dialogs) == 7)

        self.assertIsNone(self.window._material_manager_dialog)
        self.assertIsNone(self.window._section_manager_dialog)
        self.assertIsNone(self.window._assign_section_dialog)
        self.assertIsNone(self.window._load_manager_dialog)
        self.assertIsNone(self.window._boundary_manager_dialog)
        self.assertIsNone(self.window._step_manager_dialog)
        self.assertIsNone(self.window._active_model_edit_dialog)

    def test_step_output_controls_action_uses_current_context(self) -> None:
        self._set_module("Step")

        self._select_model_entry("output_request", "field-u")
        self.window.open_step_output_controls_action.trigger()
        self.app.processEvents()
        self.assertIsInstance(self.window._active_model_edit_dialog, OutputRequestEditDialog)

        self._select_model_entry("step", "step-static")
        self.window.open_step_output_controls_action.trigger()
        self.app.processEvents()
        self.assertIsInstance(self.window._active_model_edit_dialog, OutputRequestEditDialog)

        with (
            patch.object(self.window.navigation_panel, "current_model_entry", return_value=None),
            patch("pyfem.gui.main_window.QMessageBox.information") as message_box,
        ):
            self.window.open_step_output_controls_action.trigger()
            self.app.processEvents()
        message_box.assert_called_once()

    def test_material_manager_create_and_edit_route_into_material_dialog(self) -> None:
        self._set_module("Property")
        self.window.open_material_manager_action.trigger()
        self.app.processEvents()
        manager = self.window._material_manager_dialog
        self.assertIsNotNone(manager)

        def capture_dialog(factory) -> bool:
            dialog = factory()
            manager._active_edit_dialog = dialog
            return True

        with (
            patch("pyfem.gui.property_manager_dialogs.QInputDialog.getText", return_value=("mat-new", True)),
            patch.object(manager, "_run_edit_dialog", side_effect=capture_dialog),
        ):
            manager._create_item()
            self.app.processEvents()

        self.assertIsInstance(manager._active_edit_dialog, MaterialEditDialog)
        self.assertIn("mat-new", self.shell.clone_loaded_model().materials)

        manager.select_name("mat-1")
        with patch.object(manager, "_run_edit_dialog", side_effect=capture_dialog):
            manager._edit_selected_item()
            self.app.processEvents()

        self.assertIsInstance(manager._active_edit_dialog, MaterialEditDialog)

    def test_representative_formal_actions_still_trigger_object_edit_dialogs_and_job_pipeline(self) -> None:
        self._select_model_entry("material", "mat-1")
        self.assertTrue(self.window.edit_material_action.isEnabled())
        self.window.edit_material_action.trigger()
        self.app.processEvents()
        self.assertIsInstance(self.window._active_model_edit_dialog, MaterialEditDialog)

        self._select_model_entry("step", "step-static")
        self._set_module("Step")
        self.window.edit_step_action.trigger()
        self.app.processEvents()
        self.assertIsInstance(self.window._active_model_edit_dialog, StepEditDialog)

        self._select_model_entry("nodal_load", "load-right-tip")
        self._set_module("Load")
        self.window.edit_load_action.trigger()
        self.app.processEvents()
        self.assertIsInstance(self.window._active_model_edit_dialog, LoadEditDialog)

        self._select_model_entry("boundary", "bc-left-root")
        self.window.edit_boundary_action.trigger()
        self.app.processEvents()
        self.assertIsInstance(self.window._active_model_edit_dialog, BoundaryEditDialog)

        self._select_model_entry("instance", "right")
        self._set_module("Assembly")
        self.window.edit_instance_transform_action.trigger()
        self.app.processEvents()
        self.assertIsInstance(self.window._active_model_edit_dialog, InstanceTransformDialog)

        snapshot_path = Path("tests") / f"_tmp_gui_command_snapshot_{uuid4().hex}.inp"
        with patch("pyfem.gui.main_window.QFileDialog.getSaveFileName", return_value=(str(snapshot_path), "INP (*.inp)")):
            self._set_module("Job")
            self.window.write_inp_action.trigger()
            self.app.processEvents()
        self.assertTrue(snapshot_path.exists())
        self.assertIsNotNone(self.shell.state.last_export_snapshot)

        self.window.run_current_model_action.trigger()
        wait_for(lambda: self.window._active_task is None and self.window.results_browser.current_field_name is not None, timeout_seconds=10.0)
        self.assertIsNotNone(self.shell.state.last_run_snapshot)
        self.assertTrue(self.window.run_last_snapshot_action.isEnabled())

        self._set_module("Job")
        self.window.run_last_snapshot_action.trigger()
        wait_for(
            lambda: self.window._active_task is None
            and self.window.module_combo.currentData() == "Visualization"
            and self.window._current_view_context is not None
            and self.window.probe_action.isEnabled(),
            timeout_seconds=10.0,
        )
        self.assertIn("Running latest snapshot", self.window.log_text_edit.toPlainText())

        vtk_path = Path("tests") / f"_tmp_gui_command_{uuid4().hex}.vtk"
        self._set_module("Visualization")
        self.assertTrue(self.window.probe_action.isEnabled())
        self.window.probe_action.trigger()
        wait_for(lambda: self.window.probe_dialog.isVisible())

        self.window.open_legend_settings_action.trigger()
        wait_for(lambda: self.window.legend_settings_dialog.isVisible())

        with (
            patch.object(self.window.export_vtk_dialog, "exec", return_value=QDialog.DialogCode.Accepted),
            patch.object(self.window.export_vtk_dialog, "selected_path", return_value=vtk_path),
            patch.object(self.window.export_vtk_dialog, "selected_step_name", return_value="step-static"),
        ):
            self.window.export_vtk_action.trigger()
            wait_for(lambda: self.window._active_task is None, timeout_seconds=10.0)
        self.assertTrue(vtk_path.exists())
        self._cleanup_path(snapshot_path)
        self._cleanup_path(snapshot_path.with_suffix(".snapshot.json"))
        self._cleanup_path(snapshot_path.with_suffix(".results.json"))
        self._cleanup_path(vtk_path)

    def test_command_states_follow_new_property_context_rules(self) -> None:
        self._set_module("Property")
        self.assertTrue(self.window.open_material_manager_action.isEnabled())
        self.assertTrue(self.window.open_section_manager_action.isEnabled())
        self.assertTrue(self.window.assign_section_action.isEnabled())
        self.assertTrue(self.window.validate_property_data_action.isEnabled())
        self.assertFalse(self.window.edit_material_action.isEnabled())
        self.assertFalse(self.window.edit_section_action.isEnabled())
        self.assertFalse(self.window.edit_output_request_action.isEnabled())

        self._set_module("Job")
        self.assertTrue(self.window.open_job_center_action.isEnabled())
        self.assertTrue(self.window.open_current_job_monitor_action.isEnabled())
        self.assertTrue(self.window.open_job_diagnostics_action.isEnabled())
        self.assertTrue(self.window.open_results_output_action.isEnabled())
        self.assertFalse(self.window.run_last_snapshot_action.isEnabled())
        self.assertFalse(self.window.open_snapshot_manifest_action.isEnabled())

        self._set_module("Visualization")
        self.assertTrue(self.window.open_results_action.isEnabled())
        self.assertFalse(self.window.probe_action.isEnabled())
        self.assertFalse(self.window.open_legend_settings_action.isEnabled())
        self.assertFalse(self.window.export_vtk_action.isEnabled())

        self._set_module("Interaction")
        placeholder_action = self.window.command_registry.action("create_contact_placeholder")
        self.assertTrue(placeholder_action.isEnabled())
        self.assertIn("Planned:", placeholder_action.toolTip())
        with patch("pyfem.gui.main_window.QMessageBox.information") as message_box:
            placeholder_action.trigger()
            self.app.processEvents()
        message_box.assert_called_once()


if __name__ == "__main__":
    unittest.main()
