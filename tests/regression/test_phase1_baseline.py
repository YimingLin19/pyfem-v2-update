"""Phase 1 主线最小回归基线。"""

import unittest

from pyfem.compiler import Compiler
from pyfem.io import FIELD_KEY_TIME, InMemoryResultsWriter, PAIRED_VALUE_KEY_EIGENVALUE
from pyfem.mesh import ElementRecord, Mesh, NodeRecord, Part
from pyfem.modeldb import BoundaryDef, JobDef, MaterialDef, ModelDB, NodalLoadDef, OutputRequest, SectionDef, StepDef


STATIC_BASELINE = {
    "tip_uy": -0.16,
    "tip_rz": -0.12,
    "root_rf_y": 12.0,
    "root_rf_rz": 24.0,
    "end_moment_i": 24.0,
    "end_moment_j": 0.0,
    "stress": 0.0,
    "strain": 0.0,
    "residual_norm": 2.0380985511143445e-15,
    "load_norm": 12.0,
    "displacement_norm": 0.2,
    "displacement_tol": 1.0e-12,
    "reaction_tol": 1.0e-12,
    "section_tol": 1.0e-12,
    "history_tol": 1.0e-12,
}

MODAL_BASELINE = {
    "frequency_hz": 68.916111927724,
    "eigenvalue": 187500.0,
    "tip_mode_ux": 1.0,
    "tol": 1.0e-10,
}

DYNAMIC_BASELINE = {
    "frame_count": 11,
    "time_samples": {
        0: 0.0,
        5: 0.0025,
        10: 0.005,
    },
    "displacement_samples": {
        0: 0.01,
        2: 0.00908409236594565,
        5: 0.004727982838109438,
        8: -0.0015392148219957789,
        10: -0.00552923565650851,
    },
    "disp_tol": 1.0e-8,
    "time_tol": 1.0e-12,
}


class Phase1RegressionBaselineTests(unittest.TestCase):
    """固化 static / modal / dynamic 三条主线的最小基线。"""

    def test_static_linear_baseline(self) -> None:
        model = self._build_beam_model(
            step=StepDef(
                name="step-static",
                procedure_type="static_linear",
                boundary_names=("bc-root",),
                nodal_load_names=("load-tip",),
                output_request_names=("field-node-static", "field-element-static", "history-static"),
            ),
            boundaries=(BoundaryDef(name="bc-root", target_name="root", dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0}),),
            loads=(NodalLoadDef(name="load-tip", target_name="tip", components={"FY": -12.0}),),
            output_requests=(
                OutputRequest(name="field-node-static", variables=("U", "RF"), target_type="model", position="NODE"),
                OutputRequest(name="field-element-static", variables=("SECTION", "S", "E"), target_type="model", position="ELEMENT_CENTROID"),
                OutputRequest(name="history-static", variables=("TIME",), target_type="model", position="GLOBAL_HISTORY"),
            ),
        )

        writer = InMemoryResultsWriter()
        Compiler().compile(model).get_step_runtime("step-static").run(writer)

        frame = writer.frames[0]
        static_summary = writer.read_summary("step-static", "static_summary").data
        tip_uy = frame.get_field("U").values["part-1.n2"]["UY"]
        tip_rz = frame.get_field("U").values["part-1.n2"]["RZ"]
        root_rf_y = frame.get_field("RF").values["part-1.n1"]["UY"]
        root_rf_rz = frame.get_field("RF").values["part-1.n1"]["RZ"]
        end_moment_i = frame.get_field("SECTION").values["part-1.beam-1"]["end_moment_i"]
        end_moment_j = frame.get_field("SECTION").values["part-1.beam-1"]["end_moment_j"]
        stress = frame.get_field("S").values["part-1.beam-1"]
        strain = frame.get_field("E").values["part-1.beam-1"]

        self.assertAlmostEqual(tip_uy, STATIC_BASELINE["tip_uy"], delta=STATIC_BASELINE["displacement_tol"])
        self.assertAlmostEqual(tip_rz, STATIC_BASELINE["tip_rz"], delta=STATIC_BASELINE["displacement_tol"])
        self.assertAlmostEqual(root_rf_y, STATIC_BASELINE["root_rf_y"], delta=STATIC_BASELINE["reaction_tol"])
        self.assertAlmostEqual(root_rf_rz, STATIC_BASELINE["root_rf_rz"], delta=STATIC_BASELINE["reaction_tol"])
        self.assertAlmostEqual(end_moment_i, STATIC_BASELINE["end_moment_i"], delta=STATIC_BASELINE["section_tol"])
        self.assertAlmostEqual(end_moment_j, STATIC_BASELINE["end_moment_j"], delta=STATIC_BASELINE["section_tol"])
        self.assertAlmostEqual(stress, STATIC_BASELINE["stress"], delta=STATIC_BASELINE["section_tol"])
        self.assertAlmostEqual(strain, STATIC_BASELINE["strain"], delta=STATIC_BASELINE["section_tol"])
        self.assertAlmostEqual(static_summary["residual_norm"], STATIC_BASELINE["residual_norm"], delta=STATIC_BASELINE["history_tol"])
        self.assertAlmostEqual(static_summary["load_norm"], STATIC_BASELINE["load_norm"], delta=STATIC_BASELINE["history_tol"])
        self.assertAlmostEqual(static_summary["displacement_norm"], STATIC_BASELINE["displacement_norm"], delta=STATIC_BASELINE["history_tol"])

    def test_modal_baseline(self) -> None:
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

        writer = InMemoryResultsWriter()
        Compiler().compile(model).get_step_runtime("step-modal").run(writer)
        history = writer.read_history("step-modal", "FREQUENCY")
        frequency_hz = history.get_series()[0]
        eigenvalue = history.get_paired_series(PAIRED_VALUE_KEY_EIGENVALUE)[0]
        tip_mode_ux = writer.frames[0].get_field("MODE_SHAPE").values["part-1.n2"]["UX"]

        self.assertAlmostEqual(frequency_hz, MODAL_BASELINE["frequency_hz"], delta=MODAL_BASELINE["tol"])
        self.assertAlmostEqual(eigenvalue, MODAL_BASELINE["eigenvalue"], delta=MODAL_BASELINE["tol"])
        self.assertAlmostEqual(tip_mode_ux, MODAL_BASELINE["tip_mode_ux"], delta=MODAL_BASELINE["tol"])

    def test_implicit_dynamic_baseline(self) -> None:
        model = self._build_beam_model(
            step=StepDef(
                name="step-dynamic",
                procedure_type="implicit_dynamic",
                boundary_names=("bc-root", "bc-guide"),
                output_request_names=("field-dynamic", "history-dynamic"),
                parameters={
                    "time_step": 0.0005,
                    "total_time": 0.005,
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

        writer = InMemoryResultsWriter()
        Compiler().compile(model).get_step_runtime("step-dynamic").run(writer)
        history = writer.read_history("step-dynamic", FIELD_KEY_TIME)
        time_values = history.get_series()

        self.assertEqual(len(writer.frames), DYNAMIC_BASELINE["frame_count"])
        self.assertEqual(len(time_values), DYNAMIC_BASELINE["frame_count"])
        for frame_index, expected_tip_ux in DYNAMIC_BASELINE["displacement_samples"].items():
            tip_ux = writer.frames[frame_index].get_field("U").values["part-1.n2"]["UX"]
            self.assertAlmostEqual(tip_ux, expected_tip_ux, delta=DYNAMIC_BASELINE["disp_tol"])
        for frame_index, expected_time in DYNAMIC_BASELINE["time_samples"].items():
            time_value = time_values[frame_index]
            self.assertAlmostEqual(time_value, expected_time, delta=DYNAMIC_BASELINE["time_tol"])

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
        model = ModelDB(name="phase1-regression")
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


if __name__ == "__main__":
    unittest.main()
