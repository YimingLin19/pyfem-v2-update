"""RuntimeState 主线集成测试。"""

import unittest

from pyfem.compiler import Compiler
from pyfem.io import InMemoryResultsWriter
from pyfem.mesh import ElementRecord, Mesh, NodeRecord, Part
from pyfem.modeldb import BoundaryDef, InteractionDef, JobDef, MaterialDef, ModelDB, OutputRequest, SectionDef, StepDef


class RuntimeStatePipelineTests(unittest.TestCase):
    """验证 procedure / problem / state manager 的主线闭环。"""

    def test_procedure_problem_manages_constraint_and_interaction_state_lifecycle(self) -> None:
        compiled_model = Compiler().compile(self._build_beam_model())
        step_runtime = compiled_model.get_step_runtime("step-static")

        report = step_runtime.run(InMemoryResultsWriter())
        problem = step_runtime.problem
        committed_state = problem.get_committed_state()

        self.assertEqual(report.frame_count, 1)
        self.assertIn("part-1.beam-1", committed_state.element_states)
        self.assertIn("bc-root", committed_state.constraint_states)
        self.assertIn("phase1-noop", committed_state.interaction_states)

        trial_state = problem.begin_trial()
        trial_state.constraint_states["bc-root"]["trial_marker"] = "temp"
        trial_state.interaction_states["phase1-noop"]["trial_marker"] = "temp"
        rolled_back_state = problem.rollback()

        self.assertNotIn("trial_marker", rolled_back_state.constraint_states["bc-root"])
        self.assertNotIn("trial_marker", rolled_back_state.interaction_states["phase1-noop"])

    def _build_beam_model(self) -> ModelDB:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(2.0, 0.0)))
        mesh.add_element(ElementRecord(name="beam-1", type_key="B21", node_names=("n1", "n2")))
        mesh.add_node_set("root", ("n1",))
        mesh.add_node_set("tip", ("n2",))
        mesh.add_element_set("beam-set", ("beam-1",))

        part = Part(name="part-1", mesh=mesh)
        model = ModelDB(name="runtime-state-beam")
        model.add_part(part)
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
        model.add_boundary(
            BoundaryDef(name="bc-root", target_name="root", dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0})
        )
        model.add_interaction(
            InteractionDef(
                name="phase1-noop",
                interaction_type="noop",
                scope_name="part-1",
                parameters={"reason": "state-lifecycle"},
            )
        )
        model.add_output_request(OutputRequest(name="field-static", variables=("U",), target_type="model"))
        model.add_step(
            StepDef(
                name="step-static",
                procedure_type="static_linear",
                boundary_names=("bc-root",),
                output_request_names=("field-static",),
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-static",)))
        return model


if __name__ == "__main__":
    unittest.main()
