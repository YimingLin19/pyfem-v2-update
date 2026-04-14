"""结果合同主线集成测试。"""

import unittest

from pyfem.compiler import Compiler
from pyfem.io import (
    AXIS_KIND_FRAME_ID,
    AXIS_KIND_MODE_INDEX,
    AXIS_KIND_TIME,
    FIELD_KEY_FREQUENCY,
    FIELD_KEY_TIME,
    FRAME_KIND_MODE,
    InMemoryResultsWriter,
    MODAL_METADATA_KEY_EIGENVALUE,
    MODAL_METADATA_KEY_FREQUENCY_HZ,
    MODAL_METADATA_KEY_MODE_INDEX,
    PAIRED_VALUE_KEY_EIGENVALUE,
)
from pyfem.mesh import ElementRecord, Mesh, NodeRecord, Part
from pyfem.modeldb import BoundaryDef, JobDef, MaterialDef, ModelDB, NodalLoadDef, OutputRequest, SectionDef, StepDef


class ResultsContractPipelineTests(unittest.TestCase):
    """验证 procedure 到 reader 的正式结果合同。"""

    def test_static_results_separate_history_and_summary(self) -> None:
        writer = InMemoryResultsWriter()
        Compiler().compile(self._build_static_model()).get_step_runtime("step-static").run(writer)

        step = writer.read_step("step-static")
        summary = writer.read_summary("step-static", "static_summary")
        time_history = writer.read_history("step-static", FIELD_KEY_TIME)

        self.assertEqual(writer.list_steps(), ("step-static",))
        self.assertEqual(len(step.frames), 1)
        self.assertEqual(tuple(history.name for history in step.histories), (FIELD_KEY_TIME,))
        self.assertEqual(tuple(item.name for item in step.summaries), ("static_summary",))
        self.assertGreater(summary.data["load_norm"], 0.0)
        self.assertEqual(time_history.axis_kind, AXIS_KIND_FRAME_ID)
        self.assertEqual(time_history.get_series(), (0.0,))

    def test_modal_results_use_standardized_mode_frame_semantics(self) -> None:
        writer = InMemoryResultsWriter()
        Compiler().compile(self._build_modal_model()).get_step_runtime("step-modal").run(writer)

        frame = writer.read_frame("step-modal", 0)
        history = writer.read_history("step-modal", FIELD_KEY_FREQUENCY)

        self.assertEqual(frame.frame_kind, FRAME_KIND_MODE)
        self.assertEqual(frame.axis_kind, AXIS_KIND_MODE_INDEX)
        self.assertEqual(frame.axis_value, 0)
        self.assertEqual(frame.metadata[MODAL_METADATA_KEY_MODE_INDEX], 0)
        self.assertGreater(frame.metadata[MODAL_METADATA_KEY_FREQUENCY_HZ], 0.0)
        self.assertGreater(frame.metadata[MODAL_METADATA_KEY_EIGENVALUE], 0.0)
        self.assertEqual(history.axis_kind, AXIS_KIND_MODE_INDEX)
        self.assertEqual(history.axis_values, (0,))
        self.assertEqual(history.get_series()[0], frame.metadata[MODAL_METADATA_KEY_FREQUENCY_HZ])
        self.assertEqual(history.get_paired_series(PAIRED_VALUE_KEY_EIGENVALUE)[0], frame.metadata[MODAL_METADATA_KEY_EIGENVALUE])

    def test_dynamic_results_can_be_read_via_narrow_reader_api(self) -> None:
        writer = InMemoryResultsWriter()
        Compiler().compile(self._build_dynamic_model()).get_step_runtime("step-dynamic").run(writer)

        step = writer.read_step("step-dynamic")
        first_frame = writer.read_frame("step-dynamic", 0)
        displacement_field = writer.read_field("step-dynamic", 0, "U")
        time_history = writer.read_history("step-dynamic", FIELD_KEY_TIME)
        summary = writer.read_summary("step-dynamic", "dynamic_summary")

        self.assertGreater(len(step.frames), 1)
        self.assertEqual(first_frame.axis_kind, AXIS_KIND_TIME)
        self.assertEqual(displacement_field.name, "U")
        self.assertEqual(time_history.axis_kind, AXIS_KIND_FRAME_ID)
        self.assertEqual(summary.data["scheme"], "newmark")

    def _build_static_model(self) -> ModelDB:
        return self._build_beam_model(
            step=StepDef(
                name="step-static",
                procedure_type="static_linear",
                boundary_names=("bc-root",),
                nodal_load_names=("load-tip",),
                output_request_names=("field-static", "history-static"),
            ),
            boundaries=(BoundaryDef(name="bc-root", target_name="root", dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0}),),
            loads=(NodalLoadDef(name="load-tip", target_name="tip", components={"FY": -12.0}),),
            output_requests=(
                OutputRequest(name="field-static", variables=("U", "RF"), target_type="model", position="NODE"),
                OutputRequest(name="history-static", variables=("TIME",), target_type="model", position="GLOBAL_HISTORY"),
            ),
        )

    def _build_modal_model(self) -> ModelDB:
        return self._build_beam_model(
            step=StepDef(
                name="step-modal",
                procedure_type="modal",
                boundary_names=("bc-root", "bc-guide"),
                output_request_names=("field-modal", "history-modal"),
                parameters={"num_modes": 1},
            ),
            boundaries=(
                BoundaryDef(name="bc-root", target_name="root", dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0}),
                BoundaryDef(name="bc-guide", target_name="tip", dof_values={"UY": 0.0, "RZ": 0.0}),
            ),
            loads=(),
            output_requests=(
                OutputRequest(name="field-modal", variables=("MODE_SHAPE",), target_type="model", position="NODE"),
                OutputRequest(name="history-modal", variables=(FIELD_KEY_FREQUENCY,), target_type="model", position="GLOBAL_HISTORY"),
            ),
        )

    def _build_dynamic_model(self) -> ModelDB:
        return self._build_beam_model(
            step=StepDef(
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
            ),
            boundaries=(
                BoundaryDef(name="bc-root", target_name="root", dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0}),
                BoundaryDef(name="bc-guide", target_name="tip", dof_values={"UY": 0.0, "RZ": 0.0}),
            ),
            loads=(),
            output_requests=(
                OutputRequest(name="field-dynamic", variables=("U",), target_type="model", position="NODE"),
                OutputRequest(name="history-dynamic", variables=(FIELD_KEY_TIME,), target_type="model", position="GLOBAL_HISTORY"),
            ),
        )

    def _build_beam_model(
        self,
        step: StepDef,
        boundaries: tuple[BoundaryDef, ...],
        loads: tuple[NodalLoadDef, ...],
        output_requests: tuple[OutputRequest, ...],
    ) -> ModelDB:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(2.0, 0.0)))
        mesh.add_element(ElementRecord(name="beam-1", type_key="B21", node_names=("n1", "n2")))
        mesh.add_node_set("root", ("n1",))
        mesh.add_node_set("tip", ("n2",))
        mesh.add_element_set("beam-set", ("beam-1",))

        model = ModelDB(name="results-contract")
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
        for boundary in boundaries:
            model.add_boundary(boundary)
        for load in loads:
            model.add_nodal_load(load)
        for output_request in output_requests:
            model.add_output_request(output_request)
        model.add_step(step)
        model.set_job(JobDef(name="job-1", step_names=(step.name,)))
        return model


if __name__ == "__main__":
    unittest.main()
