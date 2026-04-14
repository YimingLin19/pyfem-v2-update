"""procedure 主线 benchmark 验证测试。"""

import math
import unittest

from pyfem.compiler import Compiler
from pyfem.io import FIELD_KEY_TIME, InMemoryResultsWriter, PAIRED_VALUE_KEY_EIGENVALUE
from pyfem.mesh import ElementRecord, Mesh, NodeRecord, Part
from pyfem.modeldb import BoundaryDef, JobDef, MaterialDef, ModelDB, NodalLoadDef, OutputRequest, SectionDef, StepDef


class ProcedureBenchmarkTests(unittest.TestCase):
    """验证 static、modal、implicit dynamic 三条 procedure 主线。"""

    def test_static_linear_beam_cantilever_benchmark(self) -> None:
        model = self._build_beam_model(
            step=StepDef(
                name="step-static",
                procedure_type="static_linear",
                boundary_names=("bc-root",),
                nodal_load_names=("load-tip",),
                output_request_names=("field-node-static", "field-element-static", "history-static"),
            ),
            boundaries=(
                BoundaryDef(name="bc-root", target_name="root", dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0}),
            ),
            loads=(
                NodalLoadDef(name="load-tip", target_name="tip", components={"FY": -12.0}),
            ),
            output_requests=(
                OutputRequest(name="field-node-static", variables=("U", "RF"), target_type="model", position="NODE"),
                OutputRequest(
                    name="field-element-static",
                    variables=("S", "E", "SECTION"),
                    target_type="model",
                    position="ELEMENT_CENTROID",
                ),
                OutputRequest(name="history-static", variables=("TIME",), target_type="model", position="GLOBAL_HISTORY"),
            ),
        )

        compiled_model = Compiler().compile(model)
        writer = InMemoryResultsWriter()
        report = compiled_model.get_step_runtime("step-static").run(writer)

        displacement_field = self._get_field(writer.frames[0], "U")
        section_field = self._get_field(writer.frames[0], "SECTION")
        reaction_field = self._get_field(writer.frames[0], "RF")
        tip_displacement = displacement_field.values["part-1.n2"]["UY"]

        self.assertEqual(report.frame_count, 1)
        self.assertEqual(report.history_count, 2)
        self.assertAlmostEqual(tip_displacement, -0.16, places=12)
        self.assertAlmostEqual(reaction_field.values["part-1.n1"]["UY"], 12.0, places=12)
        self.assertIn("part-1.beam-1", section_field.values)
        self.assertIn("end_moment_i", section_field.values["part-1.beam-1"])
        self.assertEqual(writer.read_history("step-static", FIELD_KEY_TIME).name, FIELD_KEY_TIME)

    def test_modal_axial_single_dof_benchmark(self) -> None:
        model = self._build_beam_model(
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
                OutputRequest(name="history-modal", variables=("FREQUENCY",), target_type="model", position="GLOBAL_HISTORY"),
            ),
        )

        compiled_model = Compiler().compile(model)
        writer = InMemoryResultsWriter()
        report = compiled_model.get_step_runtime("step-modal").run(writer)
        history = writer.read_history("step-modal", "FREQUENCY")
        frequency = history.get_series()[0]
        eigenvalue = history.get_paired_series(PAIRED_VALUE_KEY_EIGENVALUE)[0]
        mode_shape_field = self._get_field(writer.frames[0], "MODE_SHAPE")
        expected_frequency = math.sqrt(3.0 * 1.0e6 / (4.0 * 2.0**2)) / (2.0 * math.pi)

        self.assertEqual(report.frame_count, 1)
        self.assertEqual(report.history_count, 1)
        self.assertAlmostEqual(frequency, expected_frequency, places=10)
        self.assertAlmostEqual(eigenvalue, 187500.0, places=10)
        self.assertIn("UX", mode_shape_field.values["part-1.n2"])

    def test_implicit_dynamic_free_vibration_benchmark(self) -> None:
        total_time = 0.005
        model = self._build_beam_model(
            step=StepDef(
                name="step-dynamic",
                procedure_type="implicit_dynamic",
                boundary_names=("bc-root", "bc-guide"),
                output_request_names=("field-dynamic", "history-dynamic"),
                parameters={
                    "time_step": 0.0005,
                    "total_time": total_time,
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
                OutputRequest(name="history-dynamic", variables=("TIME",), target_type="model", position="GLOBAL_HISTORY"),
            ),
        )

        compiled_model = Compiler().compile(model)
        writer = InMemoryResultsWriter()
        report = compiled_model.get_step_runtime("step-dynamic").run(writer)

        last_frame = writer.frames[-1]
        displacement_field = self._get_field(last_frame, "U")
        time_history = self._get_history(writer, FIELD_KEY_TIME)
        tip_displacement = displacement_field.values["part-1.n2"]["UX"]
        omega = math.sqrt(3.0 * 1.0e6 / (4.0 * 2.0**2))
        expected_tip = 0.01 * math.cos(omega * total_time)

        self.assertEqual(report.frame_count, 11)
        self.assertEqual(report.history_count, 2)
        self.assertEqual(len(time_history.get_series()), 11)
        self.assertAlmostEqual(tip_displacement, expected_tip, delta=1.0e-4)

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

        part = Part(name="part-1", mesh=mesh)

        model = ModelDB(name="beam-benchmark")
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
        for boundary in boundaries:
            model.add_boundary(boundary)
        for load in loads:
            model.add_nodal_load(load)
        for output_request in output_requests:
            model.add_output_request(output_request)
        model.add_step(step)
        model.set_job(JobDef(name="job-1", step_names=(step.name,)))
        return model

    def _get_field(self, frame, field_name: str):
        for field in frame.fields:
            if field.name == field_name:
                return field
        raise AssertionError(f"未找到结果场 {field_name}。")

    def _get_history(self, writer: InMemoryResultsWriter, history_name: str):
        for history in writer.histories:
            if history.name == history_name:
                return history
        raise AssertionError(f"未找到历史量 {history_name}。")


if __name__ == "__main__":
    unittest.main()
