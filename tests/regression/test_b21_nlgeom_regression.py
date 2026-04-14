"""B21 nlgeom 主线与支持边界回归测试。"""

from __future__ import annotations

import unittest

from pyfem.compiler import Compiler
from pyfem.io import InMemoryResultsWriter
from pyfem.mesh import ElementRecord, Mesh, NodeRecord, Part
from pyfem.modeldb import BoundaryDef, JobDef, MaterialDef, ModelDB, NodalLoadDef, OutputRequest, SectionDef, StepDef
from tests.support.model_builders import build_cps4_tension_model


class B21NlgeomRegressionTests(unittest.TestCase):
    """验证 B21 既有主线仍然稳定，且 nlgeom 支持边界保持清晰。"""

    def test_static_nonlinear_b21_nlgeom_path_runs_through_formal_pipeline(self) -> None:
        compiled_model = Compiler().compile(self._build_b21_nlgeom_model())
        writer = InMemoryResultsWriter()
        compiled_model.get_step_runtime("step-static").run(writer)

        summary = writer.read_summary("step-static", "static_nonlinear_summary").data
        load_history = writer.read_history("step-static", "load_factor").get_series()
        iteration_history = writer.read_history("step-static", "iteration_count").get_series()

        self.assertTrue(bool(summary["nlgeom"]))
        self.assertEqual(float(summary["load_factor"]), 1.0)
        self.assertEqual(int(summary["converged_increment_count"]), 4)
        self.assertEqual(load_history, (0.0, 0.25, 0.5, 0.75, 1.0))
        self.assertEqual(len(iteration_history), 5)

    def test_cps4_with_nlgeom_enabled_runs_through_formal_pipeline(self) -> None:
        model = build_cps4_tension_model()
        step = model.steps["step-static"]
        step.procedure_type = "static_nonlinear"
        step.parameters = {
            "max_increments": 4,
            "initial_increment": 0.25,
            "min_increment": 0.25,
            "max_iterations": 8,
            "residual_tolerance": 1.0e-12,
            "displacement_tolerance": 1.0e-12,
            "allow_cutback": True,
            "line_search": False,
            "nlgeom": True,
        }

        compiled_model = Compiler().compile(model)
        writer = InMemoryResultsWriter()
        compiled_model.get_step_runtime("step-static").run(writer)

        summary = writer.read_summary("step-static", "static_nonlinear_summary").data
        self.assertTrue(bool(summary["nlgeom"]))
        self.assertEqual(int(summary["converged_increment_count"]), 4)

    def _build_b21_nlgeom_model(self) -> ModelDB:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(2.0, 0.0)))
        mesh.add_element(ElementRecord(name="beam-1", type_key="B21", node_names=("n1", "n2")))
        mesh.add_node_set("root", ("n1",))
        mesh.add_node_set("tip", ("n2",))
        mesh.add_element_set("beam-set", ("beam-1",))

        model = ModelDB(name="b21-nlgeom-regression")
        model.add_part(Part(name="part-1", mesh=mesh))
        model.add_material(
            MaterialDef(
                name="mat-1",
                material_type="linear_elastic",
                parameters={"young_modulus": 1.0e6, "poisson_ratio": 0.3, "density": 4.0},
            )
        )
        model.add_section(
            SectionDef(
                name="sec-1",
                section_type="beam",
                material_name="mat-1",
                region_name="beam-set",
                scope_name="part-1",
                parameters={"area": 0.03, "moment_inertia_z": 2.0e-4},
            )
        )
        model.add_boundary(BoundaryDef(name="bc-root", target_name="root", dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0}))
        model.add_nodal_load(NodalLoadDef(name="load-tip", target_name="tip", components={"FY": -12.0}))
        model.add_output_request(OutputRequest(name="field-node", variables=("U", "RF"), target_type="model", position="NODE"))
        model.add_output_request(OutputRequest(name="history-time", variables=("TIME",), target_type="model", position="GLOBAL_HISTORY"))
        model.add_step(
            StepDef(
                name="step-static",
                procedure_type="static_nonlinear",
                boundary_names=("bc-root",),
                nodal_load_names=("load-tip",),
                output_request_names=("field-node", "history-time"),
                parameters={
                    "max_increments": 4,
                    "initial_increment": 0.25,
                    "min_increment": 0.25,
                    "max_iterations": 20,
                    "residual_tolerance": 1.0e-10,
                    "displacement_tolerance": 1.0e-10,
                    "allow_cutback": True,
                    "line_search": False,
                    "nlgeom": True,
                },
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-static",)))
        return model


if __name__ == "__main__":
    unittest.main()
