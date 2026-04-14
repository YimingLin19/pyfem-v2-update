"""产品壳层集成测试。"""

from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

from pyfem.api import PyFEMSession
from pyfem.gui import GuiShell
from pyfem.io import AXIS_KIND_FRAME_ID, FIELD_KEY_TIME, FIELD_KEY_U, FRAME_KIND_SOLUTION, GLOBAL_HISTORY_TARGET
from pyfem.job import InMemoryJobMonitor, JobManager


class ProductShellIntegrationTests(unittest.TestCase):
    """验证 Job / API / GUI 壳遵守正式主数据流。"""

    def test_job_manager_executes_input_file_and_exports_vtk(self) -> None:
        inp_path = Path("tests") / f"_tmp_job_shell_{uuid4().hex}.inp"
        results_path = Path("tests") / f"_tmp_job_shell_{uuid4().hex}.json"
        vtk_path = Path("tests") / f"_tmp_job_shell_{uuid4().hex}.vtk"
        monitor = InMemoryJobMonitor()
        try:
            inp_path.write_text(self._build_beam_inp(), encoding="utf-8")
            report = JobManager().run_input_file(
                inp_path,
                results_path=results_path,
                export_format="vtk",
                export_path=vtk_path,
                monitor=monitor,
            )

            self.assertTrue(results_path.exists())
            self.assertTrue(vtk_path.exists())
            self.assertEqual(report.step_name, "LOAD_STEP")
            self.assertEqual(report.frame_count, 1)
            self.assertGreaterEqual(report.history_count, 1)
            self.assertGreaterEqual(report.summary_count, 1)
            self.assertTrue(any("加载模型" in message for message in report.monitor_messages))
            self.assertTrue(any("导出结果 vtk" in message for message in report.monitor_messages))
        finally:
            inp_path.unlink(missing_ok=True)
            results_path.unlink(missing_ok=True)
            vtk_path.unlink(missing_ok=True)

    def test_api_session_opens_results_through_reader_only_facade(self) -> None:
        inp_path = Path("tests") / f"_tmp_api_shell_{uuid4().hex}.inp"
        results_path = Path("tests") / f"_tmp_api_shell_{uuid4().hex}.json"
        try:
            inp_path.write_text(self._build_beam_inp(), encoding="utf-8")
            session = PyFEMSession()
            report = session.run_input_file(inp_path, results_path=results_path)
            results = session.open_results(results_path)

            self.assertEqual(report.results_path, results_path)
            self.assertEqual(results.list_steps(), ("LOAD_STEP",))
            self.assertEqual(results.step_overviews()[0].frame_count, 1)
            self.assertIn("part-1.2", results.query().field("LOAD_STEP", 0, FIELD_KEY_U).values)
            self.assertEqual(results.probe().node_component("LOAD_STEP", "part-1.2", "UY").axis_values, (0,))
        finally:
            inp_path.unlink(missing_ok=True)
            results_path.unlink(missing_ok=True)

    def test_gui_shell_follows_open_submit_open_results_flow(self) -> None:
        inp_path = Path("tests") / f"_tmp_gui_shell_{uuid4().hex}.inp"
        results_path = Path("tests") / f"_tmp_gui_shell_{uuid4().hex}.json"
        try:
            inp_path.write_text(self._build_beam_inp(), encoding="utf-8")
            gui = GuiShell()

            summary = gui.open_model(inp_path)
            report = gui.submit_job(results_path=results_path)
            entries = gui.open_results()
            descriptions = gui.describe_results()
            step_overviews = gui.browse_step_overviews(step_name="LOAD_STEP")
            frames = gui.browse_frames(step_name="LOAD_STEP", frame_kind=FRAME_KIND_SOLUTION, field_name=FIELD_KEY_U)
            fields = gui.browse_fields(step_name="LOAD_STEP", field_name=FIELD_KEY_U, target_key="part-1.2")
            histories = gui.browse_histories(
                step_name="LOAD_STEP",
                history_name=FIELD_KEY_TIME,
                axis_kind=AXIS_KIND_FRAME_ID,
                target_key=GLOBAL_HISTORY_TARGET,
            )
            summaries = gui.browse_summaries(step_name="LOAD_STEP")

            self.assertEqual(summary.step_names, ("LOAD_STEP",))
            self.assertEqual(report.results_path, results_path)
            self.assertEqual(entries[0].step_name, "LOAD_STEP")
            self.assertIn("step=LOAD_STEP", descriptions[0])
            self.assertEqual(step_overviews[0].step_name, "LOAD_STEP")
            self.assertEqual(frames[0].field_names, (FIELD_KEY_U,))
            self.assertEqual(fields[0].target_keys, ("part-1.2",))
            self.assertEqual(histories[0].history_name, FIELD_KEY_TIME)
            self.assertGreaterEqual(len(summaries), 1)
            self.assertEqual(gui.state.current_results_path, results_path)
        finally:
            inp_path.unlink(missing_ok=True)
            results_path.unlink(missing_ok=True)

    def _build_beam_inp(self) -> str:
        return """
*Heading
Phase 6A product shell example
*Node
1, 0.0, 0.0
2, 2.0, 0.0
*Element, type=B21, elset=BEAM_SET
1, 1, 2
*Nset, nset=ROOT
1
*Nset, nset=TIP
2
*Material, name=STEEL
*Elastic
1000000.0, 0.3
*Density
4.0
*Beam Section, elset=BEAM_SET, material=STEEL
0.03, 0.0002
*Step, name=LOAD_STEP
*Static
*Boundary
ROOT, 1, 2, 0.0
ROOT, 6, 6, 0.0
*Cload
TIP, 2, -12.0
*End Step
""".strip()


if __name__ == "__main__":
    unittest.main()
