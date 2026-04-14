"""B21 几何非线性与材料非线性正式耦合回归测试。"""

from __future__ import annotations

import unittest

import numpy

from pyfem.compiler import Compiler
from pyfem.io import FIELD_KEY_RF, FIELD_KEY_U, InMemoryResultsWriter
from pyfem.mesh import ElementRecord, Mesh, NodeRecord, Part
from pyfem.modeldb import BoundaryDef, JobDef, MaterialDef, ModelDB, NodalLoadDef, OutputRequest, SectionDef, StepDef
from pyfem.solver import LinearAlgebraBackend


class ThresholdScalingBackend(LinearAlgebraBackend):
    """按右端项范数切换缩放策略的测试 backend。"""

    def __init__(self, *, threshold: float, scale_above_threshold: float) -> None:
        self._threshold = float(threshold)
        self._scale_above_threshold = float(scale_above_threshold)

    def solve_linear_system(self, matrix: numpy.ndarray, rhs: numpy.ndarray) -> numpy.ndarray:
        exact_solution = numpy.linalg.solve(numpy.asarray(matrix, dtype=float), numpy.asarray(rhs, dtype=float))
        if float(numpy.linalg.norm(rhs)) > self._threshold:
            return self._scale_above_threshold * exact_solution
        return exact_solution

    def solve_generalized_eigenproblem(
        self,
        stiffness: numpy.ndarray,
        mass: numpy.ndarray,
        num_modes: int,
    ) -> tuple[numpy.ndarray, numpy.ndarray]:
        raise NotImplementedError("当前测试 backend 不覆盖模态分析。")


class B21MaterialNlgeomCouplingTests(unittest.TestCase):
    """验证 B21 corotational 与最小轴向弹塑性正式耦合主线。"""

    def test_b21_nlgeom_with_j2_material_runs_through_formal_pipeline(self) -> None:
        load_value = 3.0
        compiled_model, writer = self._run_step(self._build_single_step_axial_plastic_model(load_value=load_value))

        summary = writer.read_summary("step-load", "static_nonlinear_summary").data
        frame = writer.read_step("step-load").frames[-1]
        tip_displacement = frame.get_field(FIELD_KEY_U).values["part-1.n2"]["UX"]
        tip_reaction = frame.get_field(FIELD_KEY_RF).values["part-1.n2"]["UX"]
        section_output = frame.get_field("SECTION").values["part-1.beam-1"]
        point_state = compiled_model.get_step_runtime("step-load").problem.get_committed_state().integration_point_states[
            "part-1.beam-1"
        ]["ip1"]

        elastic_displacement = load_value / (200000.0 * 0.01)
        self.assertTrue(bool(summary["nlgeom"]))
        self.assertEqual(float(summary["load_factor"]), 1.0)
        self.assertIn("increment_attempt_count", summary)
        self.assertIn("final_increment_size", summary)
        self.assertGreater(float(tip_displacement), elastic_displacement)
        self.assertAlmostEqual(abs(float(tip_reaction)), 0.0, delta=1.0e-8)
        self.assertAlmostEqual(abs(float(section_output["axial_force"])), load_value, delta=1.0e-6)
        self.assertGreater(point_state["material_state"]["equivalent_plastic_strain"], 0.0)
        self.assertIn("generalized_strain", point_state)
        self.assertIn("generalized_stress", point_state)
        self.assertEqual(point_state["debug_metadata"]["owner"], "part-1.beam-1")

    def test_b21_owner_based_material_history_survives_manual_rollback(self) -> None:
        compiled_model, _ = self._run_step(self._build_single_step_axial_plastic_model(load_value=3.0))
        problem = compiled_model.get_step_runtime("step-load").problem
        committed_state = problem.get_committed_state()
        committed_value = committed_state.integration_point_states["part-1.beam-1"]["ip1"]["material_state"][
            "equivalent_plastic_strain"
        ]

        trial_state = problem.begin_trial()
        trial_state.integration_point_states["part-1.beam-1"]["ip1"]["material_state"]["equivalent_plastic_strain"] = -1.0
        rolled_back_state = problem.rollback()
        rolled_back_value = rolled_back_state.integration_point_states["part-1.beam-1"]["ip1"]["material_state"][
            "equivalent_plastic_strain"
        ]

        self.assertGreater(committed_value, 0.0)
        self.assertEqual(rolled_back_value, committed_value)

    def test_b21_cutback_path_preserves_committed_material_state(self) -> None:
        reference_model = self._build_single_step_axial_plastic_model(load_value=3.0)
        reference_compiled_model, reference_writer = self._run_step(reference_model)
        reference_problem = reference_compiled_model.get_step_runtime("step-load").problem
        reference_state = reference_problem.get_committed_state().integration_point_states["part-1.beam-1"]["ip1"]
        reference_eqps = reference_state["material_state"]["equivalent_plastic_strain"]
        reference_tip_ux = reference_writer.read_step("step-load").frames[-1].get_field(FIELD_KEY_U).values["part-1.n2"][
            "UX"
        ]

        cutback_model = self._build_single_step_axial_plastic_model(
            load_value=3.0,
            step_parameters={
                "max_increments": 8,
                "initial_increment": 1.0,
                "min_increment": 0.0625,
                "max_iterations": 3,
                "residual_tolerance": 1.0e-10,
                "displacement_tolerance": 1.0e-10,
                "allow_cutback": True,
                "line_search": False,
                "nlgeom": True,
            },
        )
        cutback_compiled_model, cutback_writer = self._run_step(
            cutback_model,
            backend=ThresholdScalingBackend(threshold=2.5, scale_above_threshold=0.0),
        )
        cutback_summary = cutback_writer.read_summary("step-load", "static_nonlinear_summary").data
        cutback_problem = cutback_compiled_model.get_step_runtime("step-load").problem
        cutback_state = cutback_problem.get_committed_state().integration_point_states["part-1.beam-1"]["ip1"]
        cutback_eqps = cutback_state["material_state"]["equivalent_plastic_strain"]
        cutback_tip_ux = cutback_writer.read_step("step-load").frames[-1].get_field(FIELD_KEY_U).values["part-1.n2"][
            "UX"
        ]

        self.assertGreaterEqual(int(cutback_summary["cutback_count"]), 1)
        self.assertGreater(int(cutback_summary["increment_attempt_count"]), int(cutback_summary["converged_increment_count"]))
        self.assertAlmostEqual(float(cutback_eqps), float(reference_eqps), delta=1.0e-10)
        self.assertAlmostEqual(float(cutback_tip_ux), float(reference_tip_ux), delta=1.0e-10)

    def test_b21_multistep_unload_preserves_history_and_leaves_residual_displacement(self) -> None:
        model = self._build_multistep_axial_plastic_model(load_value=3.0)
        compiled_model = Compiler().compile(model)
        writer = InMemoryResultsWriter()

        compiled_model.get_step_runtime("step-load").run(writer)
        inherited_state = compiled_model.resolve_inherited_step_state("step-unload", "solid_mechanics_history")
        inherited_eqps = inherited_state.integration_point_states["part-1.beam-1"]["ip1"]["material_state"][
            "equivalent_plastic_strain"
        ]
        compiled_model.get_step_runtime("step-unload").run(writer)

        load_step = writer.read_step("step-load")
        unload_step = writer.read_step("step-unload")
        load_final_ux = load_step.frames[-1].get_field(FIELD_KEY_U).values["part-1.n2"]["UX"]
        unload_initial_ux = unload_step.frames[0].get_field(FIELD_KEY_U).values["part-1.n2"]["UX"]
        unload_final_ux = unload_step.frames[-1].get_field(FIELD_KEY_U).values["part-1.n2"]["UX"]
        unload_problem = compiled_model.get_step_runtime("step-unload").problem
        unload_eqps = unload_problem.get_committed_state().integration_point_states["part-1.beam-1"]["ip1"]["material_state"][
            "equivalent_plastic_strain"
        ]

        self.assertIsNotNone(inherited_state)
        self.assertGreater(inherited_eqps, 0.0)
        self.assertAlmostEqual(float(unload_initial_ux), float(load_final_ux), delta=1.0e-12)
        self.assertGreater(float(unload_final_ux), 0.0)
        self.assertGreaterEqual(float(unload_eqps), float(inherited_eqps))

    def _run_step(
        self,
        model: ModelDB,
        *,
        backend: LinearAlgebraBackend | None = None,
    ) -> tuple[object, InMemoryResultsWriter]:
        compiled_model = Compiler().compile(model)
        step_runtime = compiled_model.get_step_runtime("step-load")
        if backend is not None:
            step_runtime.backend = backend
        writer = InMemoryResultsWriter()
        step_runtime.run(writer)
        return compiled_model, writer

    def _build_single_step_axial_plastic_model(
        self,
        *,
        load_value: float,
        step_parameters: dict[str, object] | None = None,
    ) -> ModelDB:
        model = self._build_base_axial_plastic_model(model_name="b21-nlgeom-j2-single", load_value=load_value)
        resolved_step_parameters = {
            "max_increments": 8,
            "initial_increment": 0.25,
            "min_increment": 0.0625,
            "max_iterations": 20,
            "residual_tolerance": 1.0e-10,
            "displacement_tolerance": 1.0e-10,
            "allow_cutback": True,
            "line_search": False,
            "nlgeom": True,
        }
        if step_parameters is not None:
            resolved_step_parameters.update(step_parameters)
        model.add_step(
            StepDef(
                name="step-load",
                procedure_type="static_nonlinear",
                boundary_names=("bc-root", "bc-tip-guide"),
                nodal_load_names=("load-tip",),
                output_request_names=("field-node", "field-element"),
                parameters=resolved_step_parameters,
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-load",)))
        return model

    def _build_multistep_axial_plastic_model(self, *, load_value: float) -> ModelDB:
        model = self._build_base_axial_plastic_model(model_name="b21-nlgeom-j2-multistep", load_value=load_value)
        step_parameters = {
            "max_increments": 8,
            "initial_increment": 0.25,
            "min_increment": 0.0625,
            "max_iterations": 20,
            "residual_tolerance": 1.0e-10,
            "displacement_tolerance": 1.0e-10,
            "allow_cutback": True,
            "line_search": False,
            "nlgeom": True,
        }
        model.add_step(
            StepDef(
                name="step-load",
                procedure_type="static_nonlinear",
                boundary_names=("bc-root", "bc-tip-guide"),
                nodal_load_names=("load-tip",),
                output_request_names=("field-node", "field-element"),
                parameters=dict(step_parameters),
            )
        )
        model.add_step(
            StepDef(
                name="step-unload",
                procedure_type="static_nonlinear",
                boundary_names=("bc-root", "bc-tip-guide"),
                nodal_load_names=(),
                output_request_names=("field-node", "field-element"),
                parameters=dict(step_parameters),
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-load", "step-unload")))
        return model

    def _build_base_axial_plastic_model(self, *, model_name: str, load_value: float) -> ModelDB:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(1.0, 0.0)))
        mesh.add_element(ElementRecord(name="beam-1", type_key="B21", node_names=("n1", "n2")))
        mesh.add_node_set("root", ("n1",))
        mesh.add_node_set("tip", ("n2",))
        mesh.add_element_set("beam-set", ("beam-1",))

        model = ModelDB(name=model_name)
        model.add_part(Part(name="part-1", mesh=mesh))
        model.add_material(
            MaterialDef(
                name="mat-j2",
                material_type="j2_plasticity",
                parameters={
                    "young_modulus": 200000.0,
                    "poisson_ratio": 0.3,
                    "yield_stress": 250.0,
                    "hardening_modulus": 1000.0,
                    "density": 1.0,
                    "tangent_mode": "consistent",
                },
            )
        )
        model.add_section(
            SectionDef(
                name="sec-1",
                section_type="beam",
                material_name="mat-j2",
                region_name="beam-set",
                scope_name="part-1",
                parameters={"area": 0.01, "moment_inertia_z": 1.0e-6},
            )
        )
        model.add_boundary(BoundaryDef(name="bc-root", target_name="root", dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0}))
        model.add_boundary(BoundaryDef(name="bc-tip-guide", target_name="tip", dof_values={"UY": 0.0, "RZ": 0.0}))
        model.add_nodal_load(NodalLoadDef(name="load-tip", target_name="tip", components={"FX": load_value}))
        model.add_output_request(OutputRequest(name="field-node", variables=("U", "RF"), target_type="model", position="NODE"))
        model.add_output_request(
            OutputRequest(
                name="field-element",
                variables=("S", "E", "SECTION"),
                target_type="model",
                position="ELEMENT_CENTROID",
            )
        )
        return model


if __name__ == "__main__":
    unittest.main()
