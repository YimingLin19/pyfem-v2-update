"""query / probe Reader-only 集成测试。"""

from pathlib import Path
import unittest
from uuid import uuid4

from pyfem.compiler import Compiler
from pyfem.io import AXIS_KIND_FRAME_ID, FIELD_KEY_TIME, JsonResultsReader, JsonResultsWriter
from pyfem.mesh import ElementRecord, Mesh, NodeRecord, Part
from pyfem.modeldb import BoundaryDef, JobDef, MaterialDef, ModelDB, OutputRequest, SectionDef, StepDef
from pyfem.post import ResultsProbeService, ResultsQueryService


class ResultsQueryProbeIntegrationTests(unittest.TestCase):
    """验证 query / probe 只消费 ResultsReader。"""

    def test_query_and_probe_services_consume_reader_only(self) -> None:
        results_path = Path("tests") / f"_tmp_results_query_probe_{uuid4().hex}.json"
        try:
            model = self._build_dynamic_model()
            Compiler().compile(model).get_step_runtime("step-dynamic").run(JsonResultsWriter(results_path))

            reader = JsonResultsReader(results_path)
            query = ResultsQueryService(reader)
            probe = ResultsProbeService(reader)

            step = query.step("step-dynamic")
            frames = query.frames("step-dynamic", field_name="U")
            histories = query.histories("step-dynamic", axis_kind=AXIS_KIND_FRAME_ID)
            summaries = query.summaries("step-dynamic")
            field = query.field("step-dynamic", 0, "U")
            history_probe = probe.history("step-dynamic", FIELD_KEY_TIME)
            node_probe = probe.node_component("step-dynamic", "part-1.n2", "UX", frame_ids=(0, 2, 4))

            self.assertEqual(query.list_steps(), ("step-dynamic",))
            self.assertGreater(len(step.frames), 1)
            self.assertEqual(tuple(frame.frame_id for frame in frames), tuple(frame.frame_id for frame in step.frames))
            self.assertEqual(histories[0].axis_kind, AXIS_KIND_FRAME_ID)
            self.assertEqual(summaries[0].name, "dynamic_summary")
            self.assertAlmostEqual(field.values["part-1.n2"]["UX"], 0.01, places=12)
            self.assertEqual(history_probe.values[0], 0.0)
            self.assertEqual(len(history_probe.values), len(step.frames))
            self.assertEqual(node_probe.metadata["field_name"], "U")
            self.assertEqual(node_probe.metadata["frame_ids"], (0, 2, 4))
            self.assertEqual(len(node_probe.values), 3)
        finally:
            results_path.unlink(missing_ok=True)

    def _build_dynamic_model(self) -> ModelDB:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(2.0, 0.0)))
        mesh.add_element(ElementRecord(name="beam-1", type_key="B21", node_names=("n1", "n2")))
        mesh.add_node_set("root", ("n1",))
        mesh.add_node_set("tip", ("n2",))
        mesh.add_element_set("beam-set", ("beam-1",))

        model = ModelDB(name="results-query-probe")
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
        model.add_output_request(OutputRequest(name="field-dynamic", variables=("U",), target_type="model", position="NODE"))
        model.add_output_request(OutputRequest(name="history-dynamic", variables=(FIELD_KEY_TIME,), target_type="model", position="GLOBAL_HISTORY"))
        model.add_step(
            StepDef(
                name="step-dynamic",
                procedure_type="implicit_dynamic",
                boundary_names=("bc-root", "bc-guide"),
                output_request_names=("field-dynamic", "history-dynamic"),
                parameters={
                    "time_step": 0.0005,
                    "total_time": 0.002,
                    "beta": 0.25,
                    "gamma": 0.5,
                    "initial_displacement": {"part-1.n2.UX": 0.01},
                },
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-dynamic",)))
        return model


if __name__ == "__main__":
    unittest.main()
