"""验证 Job 模块在 GUI 中的运行中心化工作流。"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pyfem.foundation.errors import PyFEMError
from pyfem.gui.job_dialogs import JobCenterDialog, JobDiagnosticsDialog, JobMonitorDialog
from pyfem.gui.main_window import PyFEMMainWindow
from pyfem.gui.shell import GuiShell
from pyfem.io import InpExporter
from tests.gui_test_support import get_application, set_combo_data, wait_for
from tests.support.model_builders import build_dual_instance_beam_model


class JobWorkbenchGuiTests(unittest.TestCase):
    """验证 Job Center、Monitor、Diagnostics 与 Results/Output 入口。"""

    def setUp(self) -> None:
        self.app = get_application()
        self.input_path = Path("tests") / f"_tmp_gui_job_workbench_{uuid4().hex}.inp"
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
            for record in self.window._job_records_snapshot():
                self._cleanup_path(record.results_path)
                self._cleanup_path(record.export_path)
                self._cleanup_path(record.snapshot_path)
                self._cleanup_path(record.manifest_path)
                self._cleanup_path(record.report_path)
            self._cleanup_path(self.input_path)

    def _cleanup_path(self, path: Path | None) -> None:
        if path is None:
            return
        Path(path).unlink(missing_ok=True)

    def _set_module(self, module_name: str) -> None:
        set_combo_data(self.window.module_combo, module_name)
        self.app.processEvents()

    def _latest_record(self):
        return self.window._job_records.latest()

    def _clear_results_context(self) -> None:
        self.window.results_browser.clear_results("Cleared for test.")
        self.window.navigation_panel.clear_results()
        self.window._current_view_context = None
        self.window._set_combo_data(self.window.module_combo, "Job")
        self.window._sync_module_toolbox("Job")
        self.app.processEvents()

    def test_job_center_opens_and_updates_after_completed_run(self) -> None:
        self._set_module("Job")
        self.window.open_job_center_action.trigger()
        self.app.processEvents()

        self.assertIsInstance(self.window._job_center_dialog, JobCenterDialog)
        self.assertTrue(self.window._job_center_dialog.isVisible())

        self.assertTrue(self.window.run_job())
        wait_for(
            lambda: self.window._active_task is None
            and self._latest_record() is not None
            and self._latest_record().status == "completed",
            timeout_seconds=10.0,
        )

        record = self._latest_record()
        dialog = self.window._job_center_dialog
        self.assertIsNotNone(record)
        self.assertIsNotNone(dialog)
        self.assertGreaterEqual(dialog.records_table.rowCount(), 1)
        self.assertEqual(dialog.records_table.item(0, 0).text(), record.display_name)
        self.assertEqual(dialog.records_table.item(0, 2).text(), "completed")
        self.assertIsNotNone(record.results_path)
        self.assertTrue(record.results_path.exists())
        self.assertIsNotNone(record.export_path)
        self.assertTrue(record.export_path.exists())
        self.assertGreater(record.frame_count, 0)
        self.assertGreater(record.history_count, 0)
        self.assertGreater(record.summary_count, 0)
        self.assertIsNotNone(record.report_path)
        self.assertTrue(record.report_path.exists())

    def test_job_center_double_click_routes_running_to_monitor_and_completed_to_results(self) -> None:
        self.assertTrue(self.window.run_job())
        wait_for(
            lambda: self._latest_record() is not None and self._latest_record().status == "running",
            timeout_seconds=5.0,
        )

        self.window._open_job_center_dialog()
        dialog = self.window._job_center_dialog
        self.assertIsNotNone(dialog)
        dialog.records_table.selectRow(0)
        dialog._handle_record_activation()
        wait_for(lambda: self.window._job_monitor_dialog is not None and self.window._job_monitor_dialog.isVisible())

        wait_for(
            lambda: self.window._active_task is None
            and self._latest_record() is not None
            and self._latest_record().status == "completed",
            timeout_seconds=10.0,
        )
        self._clear_results_context()
        dialog.set_records(self.window._job_records_snapshot())
        dialog.records_table.selectRow(0)
        dialog._handle_record_activation()
        wait_for(
            lambda: self.window._active_task is None
            and self.window._current_view_context is not None
            and self.window.module_combo.currentData() == "Visualization",
            timeout_seconds=10.0,
        )

    def test_monitor_dialog_shows_messages_and_keeps_content_after_completion(self) -> None:
        self.assertTrue(self.window.run_job())
        self.window._open_job_monitor_dialog()
        wait_for(lambda: self.window._job_monitor_dialog is not None and self.window._job_monitor_dialog.isVisible())

        dialog = self.window._job_monitor_dialog
        self.assertIsInstance(dialog, JobMonitorDialog)
        wait_for(lambda: "Background solve task started." in dialog.log_edit.toPlainText(), timeout_seconds=5.0)
        wait_for(
            lambda: self.window._active_task is None
            and self._latest_record() is not None
            and self._latest_record().status == "completed",
            timeout_seconds=10.0,
        )

        self.assertEqual(dialog.status_value.text(), "completed")
        self.assertIn("Job completed", dialog.log_edit.toPlainText())
        self.assertNotEqual(dialog.files_edit.toPlainText().strip(), "")

    def test_diagnostics_dialog_reports_empty_state_and_failed_run(self) -> None:
        self.window._open_job_diagnostics_dialog()
        dialog = self.window._job_diagnostics_dialog
        self.assertIsInstance(dialog, JobDiagnosticsDialog)
        self.assertIn("还没有 Job 记录", dialog.problem_edit.toPlainText())

        with patch("pyfem.gui.shell.GuiShell.submit_job", side_effect=PyFEMError("synthetic error")):
            self.assertTrue(self.window.run_job())
            wait_for(lambda: self.window._active_task is None, timeout_seconds=10.0)

        wait_for(
            lambda: self._latest_record() is not None and self._latest_record().status == "failed",
            timeout_seconds=5.0,
        )
        self.window._open_job_diagnostics_dialog()
        self.app.processEvents()

        self.assertIn("失败或终止", dialog.problem_edit.toPlainText())
        self.assertIn("synthetic error", dialog.errors_edit.toPlainText())

    def test_results_output_prefers_results_and_falls_back_to_manifest(self) -> None:
        self.assertTrue(self.window.run_job())
        wait_for(
            lambda: self.window._active_task is None
            and self._latest_record() is not None
            and self._latest_record().status == "completed",
            timeout_seconds=10.0,
        )

        self._clear_results_context()
        self.window.open_results_output_action.trigger()
        wait_for(
            lambda: self.window._active_task is None
            and self.window._current_view_context is not None
            and self.window.module_combo.currentData() == "Visualization",
            timeout_seconds=10.0,
        )

        snapshot_path = Path("tests") / f"_tmp_gui_job_manifest_{uuid4().hex}.inp"
        snapshot = self.shell.write_current_model_snapshot(snapshot_path)
        record = self.window._register_snapshot_record(
            snapshot,
            status="written",
            message=f"INP snapshot written: {snapshot.snapshot_path}",
        )
        self._clear_results_context()
        self.window._open_results_output_entry(record.record_id)
        self.app.processEvents()

        self.assertTrue(self.window.selection_details_dialog.isVisible())
        self.assertIn("Snapshot Manifest", self.window.selection_details_dialog.windowTitle())

    def test_job_dialogs_close_with_main_window_and_reuse_single_instances(self) -> None:
        self.window._open_job_center_dialog()
        self.window._open_job_center_dialog()
        self.window._open_job_monitor_dialog()
        self.window._open_job_monitor_dialog()
        self.window._open_job_diagnostics_dialog()
        self.window._open_job_diagnostics_dialog()
        self.app.processEvents()

        center_dialog = self.window._job_center_dialog
        monitor_dialog = self.window._job_monitor_dialog
        diagnostics_dialog = self.window._job_diagnostics_dialog

        self.assertIs(center_dialog, self.window._job_center_dialog)
        self.assertIs(monitor_dialog, self.window._job_monitor_dialog)
        self.assertIs(diagnostics_dialog, self.window._job_diagnostics_dialog)

        destroyed: list[str] = []
        center_dialog.destroyed.connect(lambda *_args: destroyed.append("center"))
        monitor_dialog.destroyed.connect(lambda *_args: destroyed.append("monitor"))
        diagnostics_dialog.destroyed.connect(lambda *_args: destroyed.append("diagnostics"))

        self.window.close()
        wait_for(lambda: len(destroyed) == 3, timeout_seconds=5.0)

        self.assertIsNone(self.window._job_center_dialog)
        self.assertIsNone(self.window._job_monitor_dialog)
        self.assertIsNone(self.window._job_diagnostics_dialog)


if __name__ == "__main__":
    unittest.main()
