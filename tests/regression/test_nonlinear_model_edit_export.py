"""非线性对象编辑与导出回归测试。"""

from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

from pyfem.foundation.errors import CompilationError
from pyfem.gui.model_edit_presenters import ModelEditPresenter
from pyfem.gui.shell import GuiShell
from pyfem.io import InpExporter, InpImporter
from tests.support.model_builders import build_c3d8_pressure_block_model
from tests.support.solid_finite_strain_j2_builders import build_c3d8_j2_model


class NonlinearModelEditExportRegressionTests(unittest.TestCase):
    """验证非线性对象经 GUI/API 编辑后可正确导出，并在不支持组合下 fail-fast。"""

    def test_step_and_j2_material_updates_roundtrip_through_exporter(self) -> None:
        model = build_c3d8_j2_model(
            model_name="edit-export-j2",
            nlgeom=False,
            right_displacement=0.004,
            include_material_fields=True,
        )
        source_path = Path("tests") / f"_tmp_edit_source_{uuid4().hex}.inp"
        snapshot_path = Path("tests") / f"_tmp_edit_snapshot_{uuid4().hex}.inp"
        exporter = InpExporter()
        exporter.export(model, source_path)

        shell = GuiShell()
        presenter = ModelEditPresenter(shell)
        try:
            shell.open_model(source_path, model_name="edit-export-j2")
            presenter.apply_material_update(
                "mat-j2",
                material_type="j2_plasticity",
                young_modulus_text="210000.0",
                poisson_ratio_text="0.29",
                density_text="",
                yield_stress_text="275.0",
                hardening_modulus_text="1500.0",
                tangent_mode="numerical",
            )
            presenter.apply_step_update(
                "step-static",
                procedure_type="static_nonlinear",
                nlgeom=True,
                initial_increment_text="0.05",
                max_increments_text="20",
                min_increment_text="0.02",
                max_iterations_text="25",
                residual_tolerance_text="1e-9",
                displacement_tolerance_text="1e-9",
                allow_cutback=True,
                line_search=True,
                num_modes_text="",
                time_step_text="",
                total_time_text="",
            )
            shell.write_current_model_snapshot(snapshot_path)
            imported_model = InpImporter().import_file(snapshot_path, model_name="edited-roundtrip")

            self.assertTrue(bool(imported_model.steps["step-static"].parameters["nlgeom"]))
            self.assertEqual(imported_model.steps["step-static"].parameters["line_search"], True)
            self.assertEqual(imported_model.materials["mat-j2"].parameters["yield_stress"], 275.0)
            self.assertEqual(imported_model.materials["mat-j2"].parameters["hardening_modulus"], 1500.0)
            self.assertEqual(imported_model.materials["mat-j2"].parameters["tangent_mode"], "numerical")
        finally:
            source_path.unlink(missing_ok=True)
            snapshot_path.unlink(missing_ok=True)
            snapshot_path.with_suffix(".snapshot.json").unlink(missing_ok=True)

    def test_run_chain_fails_fast_for_unsupported_nlgeom_distributed_load(self) -> None:
        model = build_c3d8_pressure_block_model()
        step = model.steps["step-static"]
        step.procedure_type = "static_nonlinear"
        step.parameters = {
            "max_increments": 4,
            "initial_increment": 0.25,
            "min_increment": 0.25,
            "max_iterations": 8,
            "residual_tolerance": 1.0e-10,
            "displacement_tolerance": 1.0e-10,
            "allow_cutback": True,
            "line_search": False,
            "nlgeom": True,
        }

        shell = GuiShell()
        shell.replace_loaded_model(model, source_path=Path("tests") / "unsupported-nlgeom-pressure.inp", mark_dirty=False)
        with self.assertRaisesRegex(CompilationError, "distributed load"):
            shell.submit_job()


if __name__ == "__main__":
    unittest.main()
