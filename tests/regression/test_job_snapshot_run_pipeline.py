"""Job Snapshot 主线回归测试。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from uuid import uuid4

from pyfem.gui.shell import GuiShell
from pyfem.io import InpImporter, JsonResultsReader
from pyfem.job import JobSnapshotService
from tests.support.model_builders import build_c3d8_pressure_block_model, build_static_beam_benchmark_model, run_step


class JobSnapshotRunPipelineRegressionTests(unittest.TestCase):
    """验证 snapshot 导出、冻结运行与 Derived Case 主线。"""

    def test_run_snapshot_consumes_frozen_model_not_live_model(self) -> None:
        model = build_static_beam_benchmark_model()
        snapshot_path = Path("tests") / f"_tmp_snapshot_{uuid4().hex}.inp"
        service = JobSnapshotService()

        try:
            snapshot = service.write_snapshot(model, snapshot_path=snapshot_path, source_model_path=Path("tests") / "beam-case.inp")
            model.nodal_loads["load-tip"].components = {"FY": -24.0}

            report = service.run_snapshot(snapshot)
            reader = JsonResultsReader(snapshot.results_path)
            frozen_tip_uy = reader.read_step("step-static").frames[-1].get_field("U").values["part-1.n2"]["UY"]

            _, mutated_writer = run_step(model, "step-static")
            mutated_tip_uy = mutated_writer.read_step("step-static").frames[-1].get_field("U").values["part-1.n2"]["UY"]

            self.assertEqual(report.results_path, snapshot.results_path)
            self.assertNotEqual(frozen_tip_uy, mutated_tip_uy)
            self.assertTrue(snapshot.manifest_path.exists())
            manifest_payload = json.loads(snapshot.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest_payload["snapshot_path"], str(snapshot.snapshot_path))
            self.assertEqual(manifest_payload["results_path"], str(snapshot.results_path))
            self.assertEqual(manifest_payload["last_run_report"]["step_name"], "step-static")
        finally:
            snapshot_path.unlink(missing_ok=True)
            snapshot_path.with_suffix(".snapshot.json").unlink(missing_ok=True)
            snapshot_path.with_suffix(".results.json").unlink(missing_ok=True)
            snapshot_path.with_suffix(".vtk").unlink(missing_ok=True)

    def test_save_as_derived_case_switches_current_source_path(self) -> None:
        model = build_static_beam_benchmark_model()
        shell = GuiShell()
        shell.replace_loaded_model(model, source_path=Path("tests") / "base-case.inp", mark_dirty=True)
        derived_case_path = Path("tests") / f"_tmp_derived_{uuid4().hex}.inp"

        try:
            snapshot = shell.save_current_model_as_derived_case(derived_case_path)
            self.assertEqual(snapshot.snapshot_path, derived_case_path)
            self.assertEqual(shell.state.opened_model.source_path, derived_case_path)
            self.assertFalse(shell.state.model_dirty)
            self.assertTrue(derived_case_path.exists())
        finally:
            derived_case_path.unlink(missing_ok=True)
            derived_case_path.with_suffix(".snapshot.json").unlink(missing_ok=True)

    def test_gui_shell_submit_job_runs_c3d8_surface_pressure_through_snapshot(self) -> None:
        model = build_c3d8_pressure_block_model()
        shell = GuiShell()
        results_path = Path("tests") / f"_tmp_pressure_snapshot_{uuid4().hex}.results.json"
        shell.replace_loaded_model(model, source_path=Path("tests") / "pressure-case.inp", mark_dirty=False)

        try:
            report = shell.submit_job(results_path=results_path)
            self.assertEqual(report.step_name, "step-static")
            self.assertEqual(report.procedure_type, "static_linear")
            self.assertIsNotNone(shell.state.last_run_snapshot)
            self.assertTrue(shell.state.last_run_snapshot.snapshot_path.exists())
            self.assertTrue(results_path.exists())
        finally:
            results_path.unlink(missing_ok=True)
            snapshot = shell.state.last_run_snapshot
            if snapshot is not None:
                snapshot.snapshot_path.unlink(missing_ok=True)
                snapshot.manifest_path.unlink(missing_ok=True)

    def test_gui_shell_submit_job_preserves_assembly_alias_targets_through_snapshot(self) -> None:
        model = InpImporter().import_text(
            """
*Part, name=BLOCK
*Node
1, 1.0, 0.0, 1.0
2, 1.0, 1.0, 1.0
3, 1.0, 1.0, 0.0
4, 1.0, 0.0, 0.0
5, 0.0, 0.0, 1.0
6, 0.0, 1.0, 1.0
7, 0.0, 1.0, 0.0
8, 0.0, 0.0, 0.0
*Element, type=C3D8, elset=BLOCK_SET
1, 1, 2, 3, 4, 5, 6, 7, 8
*Solid Section, elset=BLOCK_SET, material=MAT
,
*End Part
*Material, name=MAT
*Elastic
1000.0, 0.3
*Assembly, name=ASM
*Instance, name=Part-1-1, part=BLOCK
*End Instance
*Nset, nset=_PickedSet7, instance=Part-1-1, generate
1, 8, 1
*Elset, elset=_Surf-1_S1, instance=Part-1-1
1
*Surface, type=ELEMENT, name=Surf-1
_Surf-1_S1, S1
*End Assembly
*Boundary
_PickedSet7, 1, 3, 0.0
*Step, name=STEP-1
*Static
*Dsload
Surf-1, P, -2.0
*End Step
""",
            model_name="assembly-alias-shell",
            source_name="assembly-alias-shell.inp",
        )
        shell = GuiShell()
        results_path = Path("tests") / f"_tmp_alias_snapshot_{uuid4().hex}.results.json"
        shell.replace_loaded_model(model, source_path=Path("tests") / "assembly-alias-shell.inp", mark_dirty=False)

        try:
            report = shell.submit_job(results_path=results_path)
            self.assertEqual(report.step_name, "STEP-1")
            self.assertTrue(results_path.exists())
            self.assertIsNotNone(shell.state.last_run_snapshot)
        finally:
            results_path.unlink(missing_ok=True)
            snapshot = shell.state.last_run_snapshot
            if snapshot is not None:
                snapshot.snapshot_path.unlink(missing_ok=True)
                snapshot.manifest_path.unlink(missing_ok=True)

    def test_gui_shell_submit_job_keeps_part_section_binding_when_assembly_set_name_collides(self) -> None:
        model = InpImporter().import_text(
            """
*Part, name=BEAM
*Node
1, 0.0, 0.0
2, 1.0, 0.0
3, 2.0, 0.0
4, 3.0, 0.0
*Element, type=B21, elset=Set-1
1, 1, 2
2, 2, 3
3, 3, 4
*Nset, nset=ROOT
1
*Beam Section, elset=Set-1, material=STEEL
0.03, 0.0002
*End Part
*Material, name=STEEL
*Elastic
1000000.0, 0.3
*Assembly, name=ASM
*Instance, name=Part-1-1, part=BEAM
*End Instance
*Nset, nset=_PickedSet7, instance=Part-1-1
1
*Elset, elset=Set-1, instance=Part-1-1
1
*End Assembly
*Boundary
_PickedSet7, 1, 2, 0.0
*Step, name=STEP-1
*Static
*End Step
""",
            model_name="section-shadowing-shell",
            source_name="section-shadowing-shell.inp",
        )
        shell = GuiShell()
        results_path = Path("tests") / f"_tmp_section_shadowing_{uuid4().hex}.results.json"
        shell.replace_loaded_model(model, source_path=Path("tests") / "section-shadowing-shell.inp", mark_dirty=False)

        try:
            report = shell.submit_job(results_path=results_path)
            self.assertEqual(report.step_name, "STEP-1")
            self.assertTrue(results_path.exists())
        finally:
            results_path.unlink(missing_ok=True)
            snapshot = shell.state.last_run_snapshot
            if snapshot is not None:
                snapshot.snapshot_path.unlink(missing_ok=True)
                snapshot.manifest_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
