"""多步执行链路集成测试。"""

import unittest

from pyfem.compiler import Compiler
from pyfem.io import FIELD_KEY_FREQUENCY, FIELD_KEY_TIME, InMemoryResultsWriter, PAIRED_VALUE_KEY_EIGENVALUE
from pyfem.mesh import ElementRecord, Mesh, NodeRecord, Part
from pyfem.modeldb import BoundaryDef, JobDef, MaterialDef, ModelDB, NodalLoadDef, OutputRequest, SectionDef, StepDef
from pyfem.post import ResultsProbeService, ResultsQueryService


class MultiStepExecutionPipelineTests(unittest.TestCase):
    """验证真实多步 procedure 执行链路。"""

    def test_compiled_model_runs_multiple_steps_in_job_order_and_writes_ordered_results(self) -> None:
        model = self._build_multi_step_model()
        compiled_model = Compiler().compile(model)
        writer = InMemoryResultsWriter()

        for step_name in model.job.step_names:
            compiled_model.get_step_runtime(step_name).run(writer)

        query = ResultsQueryService(writer)
        probe = ResultsProbeService(writer)

        static_step = query.step("step-static")
        modal_step = query.step("step-modal")
        static_time = probe.history("step-static", FIELD_KEY_TIME)
        modal_frequency = probe.history("step-modal", FIELD_KEY_FREQUENCY)
        modal_eigenvalue = probe.paired_history("step-modal", FIELD_KEY_FREQUENCY, PAIRED_VALUE_KEY_EIGENVALUE)

        self.assertTrue(writer.is_multi_step())
        self.assertEqual(writer.list_steps(), ("step-static", "step-modal"))
        self.assertEqual(tuple(step.name for step in query.steps()), ("step-static", "step-modal"))
        self.assertEqual(tuple(step.step_index for step in query.steps()), (0, 1))
        self.assertEqual(static_step.summaries[0].name, "static_summary")
        self.assertEqual(static_time.values, (0.0,))
        self.assertGreater(len(modal_step.frames), 0)
        self.assertGreater(modal_frequency.values[0], 0.0)
        self.assertGreater(modal_eigenvalue.values[0], 0.0)
        self.assertEqual(query.frames("step-modal", field_name="MODE_SHAPE")[0].frame_id, 0)
        self.assertEqual(query.summaries("step-static", data_key="load_norm")[0].name, "static_summary")
        self.assertEqual(query.histories("step-modal", paired_value_name=PAIRED_VALUE_KEY_EIGENVALUE)[0].name, FIELD_KEY_FREQUENCY)

    def _build_multi_step_model(self) -> ModelDB:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(2.0, 0.0)))
        mesh.add_element(ElementRecord(name="beam-1", type_key="B21", node_names=("n1", "n2")))
        mesh.add_node_set("root", ("n1",))
        mesh.add_node_set("tip", ("n2",))
        mesh.add_element_set("beam-set", ("beam-1",))

        model = ModelDB(name="multi-step-execution")
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
        model.add_boundary(BoundaryDef(name="bc-guide", target_name="tip", dof_values={"UY": 0.0, "RZ": 0.0}))
        model.add_nodal_load(NodalLoadDef(name="load-tip", target_name="tip", components={"FY": -12.0}))
        model.add_output_request(OutputRequest(name="field-static", variables=("U", "RF"), target_type="model", position="NODE"))
        model.add_output_request(OutputRequest(name="history-static", variables=(FIELD_KEY_TIME,), target_type="model", position="GLOBAL_HISTORY"))
        model.add_output_request(OutputRequest(name="field-modal", variables=("MODE_SHAPE",), target_type="model", position="NODE"))
        model.add_output_request(OutputRequest(name="history-modal", variables=(FIELD_KEY_FREQUENCY,), target_type="model", position="GLOBAL_HISTORY"))
        model.add_step(
            StepDef(
                name="step-static",
                procedure_type="static_linear",
                boundary_names=("bc-root",),
                nodal_load_names=("load-tip",),
                output_request_names=("field-static", "history-static"),
            )
        )
        model.add_step(
            StepDef(
                name="step-modal",
                procedure_type="modal",
                boundary_names=("bc-root", "bc-guide"),
                output_request_names=("field-modal", "history-modal"),
                parameters={"num_modes": 1},
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-static", "step-modal")))
        return model


if __name__ == "__main__":
    unittest.main()
