"""J2 塑性与 static_nonlinear 主线回归测试。"""

from __future__ import annotations

import unittest

from pyfem.compiler import Compiler
from pyfem.foundation.errors import CompilationError
from pyfem.io import FIELD_KEY_RF, FIELD_KEY_U, InMemoryResultsWriter
from pyfem.mesh import ElementRecord, Mesh, NodeRecord, Part
from pyfem.modeldb import BoundaryDef, JobDef, MaterialDef, ModelDB, OutputRequest, SectionDef, StepDef


class J2StaticNonlinearRegressionTests(unittest.TestCase):
    """验证 J2 塑性材料已进入 static_nonlinear 主线。"""

    def test_cps4_static_nonlinear_j2_response_shows_post_yield_softening_slope(self) -> None:
        model = self._build_cps4_j2_model()
        compiled_model = Compiler().compile(model)
        step_runtime = compiled_model.get_step_runtime("step-plastic")
        writer = InMemoryResultsWriter()

        step_runtime.run(writer)

        step = writer.read_step("step-plastic")
        summary = writer.read_summary("step-plastic", "static_nonlinear_summary").data
        right_displacements = []
        right_reactions = []
        for frame in step.frames[1:]:
            displacement_field = frame.get_field(FIELD_KEY_U).values
            reaction_field = frame.get_field(FIELD_KEY_RF).values
            right_displacements.append(displacement_field["part-1.n2"]["UX"])
            right_reactions.append(reaction_field["part-1.n2"]["UX"] + reaction_field["part-1.n3"]["UX"])

        elastic_slope = (right_reactions[1] - right_reactions[0]) / (right_displacements[1] - right_displacements[0])
        plastic_slope = (right_reactions[-1] - right_reactions[-2]) / (right_displacements[-1] - right_displacements[-2])
        committed_state = step_runtime.problem.get_committed_state()
        ip_state = committed_state.integration_point_states["part-1.plate-1"]["ip1"]["material_state"]

        self.assertGreater(summary["converged_increment_count"], 3)
        self.assertLess(plastic_slope, 0.8 * elastic_slope)
        self.assertGreater(ip_state["equivalent_plastic_strain"], 0.0)

    def test_cps4_integration_point_material_history_survives_commit_and_rollback(self) -> None:
        model = self._build_cps4_j2_model()
        compiled_model = Compiler().compile(model)
        step_runtime = compiled_model.get_step_runtime("step-plastic")

        step_runtime.run(InMemoryResultsWriter())
        problem = step_runtime.problem
        committed_state = problem.get_committed_state()
        committed_value = committed_state.integration_point_states["part-1.plate-1"]["ip1"]["material_state"][
            "equivalent_plastic_strain"
        ]

        trial_state = problem.begin_trial()
        trial_state.integration_point_states["part-1.plate-1"]["ip1"]["material_state"]["equivalent_plastic_strain"] = -1.0
        rolled_back_state = problem.rollback()
        rolled_back_value = rolled_back_state.integration_point_states["part-1.plate-1"]["ip1"]["material_state"][
            "equivalent_plastic_strain"
        ]

        self.assertGreater(committed_value, 0.0)
        self.assertEqual(rolled_back_value, committed_value)

    def test_c3d8_static_nonlinear_j2_minimum_3d_path_runs(self) -> None:
        model = self._build_c3d8_j2_model()
        compiled_model = Compiler().compile(model)
        step_runtime = compiled_model.get_step_runtime("step-3d-plastic")
        writer = InMemoryResultsWriter()

        step_runtime.run(writer)

        summary = writer.read_summary("step-3d-plastic", "static_nonlinear_summary").data
        committed_state = step_runtime.problem.get_committed_state()
        point_states = committed_state.integration_point_states["part-1.block-1"]
        max_equivalent_plastic_strain = max(
            point_state["material_state"]["equivalent_plastic_strain"] for point_state in point_states.values()
        )

        self.assertGreater(summary["converged_increment_count"], 1)
        self.assertEqual(len(point_states), 8)
        self.assertGreater(max_equivalent_plastic_strain, 0.0)

    def test_consistent_tangent_requires_no_more_iterations_than_numerical_tangent(self) -> None:
        consistent_summary, consistent_iterations = self._run_single_step_summary(
            self._build_cps4_j2_model(material_parameters={"tangent_mode": "consistent"})
        )
        numerical_summary, numerical_iterations = self._run_single_step_summary(
            self._build_cps4_j2_model(material_parameters={"tangent_mode": "numerical"})
        )

        self.assertLessEqual(sum(consistent_iterations[1:]), sum(numerical_iterations[1:]))
        self.assertLessEqual(consistent_summary["cutback_count"], numerical_summary["cutback_count"])
        self.assertLessEqual(
            consistent_summary["average_iteration_per_increment"],
            numerical_summary["average_iteration_per_increment"],
        )

    def test_multistep_static_nonlinear_inherits_committed_plastic_history(self) -> None:
        model = self._build_multistep_cps4_j2_model()
        compiled_model = Compiler().compile(model)
        writer = InMemoryResultsWriter()

        compiled_model.get_step_runtime("step-load").run(writer)
        inherited_state = compiled_model.resolve_inherited_step_state("step-unload", "solid_mechanics_history")
        inherited_equivalent_plastic_strain = inherited_state.integration_point_states["part-1.plate-1"]["ip1"][
            "material_state"
        ]["equivalent_plastic_strain"]
        compiled_model.get_step_runtime("step-unload").run(writer)

        load_step = writer.read_step("step-load")
        unload_step = writer.read_step("step-unload")
        load_final_ux = load_step.frames[-1].get_field(FIELD_KEY_U).values["part-1.n2"]["UX"]
        unload_initial_ux = unload_step.frames[0].get_field(FIELD_KEY_U).values["part-1.n2"]["UX"]
        unload_final_ux = unload_step.frames[-1].get_field(FIELD_KEY_U).values["part-1.n2"]["UX"]
        unload_problem = compiled_model.get_step_runtime("step-unload").problem
        committed_state = unload_problem.get_committed_state()
        equivalent_plastic_strain = committed_state.integration_point_states["part-1.plate-1"]["ip1"]["material_state"][
            "equivalent_plastic_strain"
        ]

        self.assertIsNotNone(inherited_state)
        self.assertAlmostEqual(unload_initial_ux, load_final_ux, delta=1.0e-10)
        self.assertAlmostEqual(unload_final_ux, 0.0, delta=1.0e-10)
        self.assertGreater(inherited_equivalent_plastic_strain, 0.0)
        self.assertGreater(equivalent_plastic_strain, 0.0)
        self.assertGreaterEqual(equivalent_plastic_strain, inherited_equivalent_plastic_strain)

    def test_plane_stress_section_with_j2_fails_fast(self) -> None:
        model = self._build_cps4_j2_model(section_type="plane_stress")
        with self.assertRaisesRegex(CompilationError, "暂不支持 PlaneStressSection \\+ J2"):
            Compiler().compile(model)

    def _run_single_step_summary(self, model: ModelDB) -> tuple[dict[str, object], tuple[object, ...]]:
        compiled_model = Compiler().compile(model)
        writer = InMemoryResultsWriter()
        compiled_model.get_step_runtime("step-plastic").run(writer)
        summary = writer.read_summary("step-plastic", "static_nonlinear_summary").data
        iteration_history = writer.read_history("step-plastic", "iteration_count").get_series()
        return summary, iteration_history

    def _build_cps4_j2_model(
        self,
        *,
        material_parameters: dict[str, object] | None = None,
        section_type: str = "plane_strain",
    ) -> ModelDB:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(1.0, 0.0)))
        mesh.add_node(NodeRecord(name="n3", coordinates=(1.0, 1.0)))
        mesh.add_node(NodeRecord(name="n4", coordinates=(0.0, 1.0)))
        mesh.add_element(ElementRecord(name="plate-1", type_key="CPS4", node_names=("n1", "n2", "n3", "n4")))
        mesh.add_node_set("left", ("n1", "n4"))
        mesh.add_node_set("right", ("n2", "n3"))
        mesh.add_node_set("anchor", ("n1",))
        mesh.add_element_set("plate-set", ("plate-1",))

        model = ModelDB(name="cps4-j2-static-nonlinear")
        model.add_part(Part(name="part-1", mesh=mesh))
        resolved_material_parameters = {
            "young_modulus": 200000.0,
            "poisson_ratio": 0.3,
            "yield_stress": 250.0,
            "hardening_modulus": 1000.0,
        }
        if material_parameters is not None:
            resolved_material_parameters.update(material_parameters)
        model.add_material(
            MaterialDef(
                name="mat-j2",
                material_type="j2_plasticity",
                parameters=resolved_material_parameters,
            )
        )
        model.add_section(
            SectionDef(
                name="sec-1",
                section_type=section_type,
                material_name="mat-j2",
                region_name="plate-set",
                scope_name="part-1",
                parameters={"thickness": 1.0},
            )
        )
        model.add_boundary(BoundaryDef(name="bc-left-x", target_name="left", dof_values={"UX": 0.0}))
        model.add_boundary(BoundaryDef(name="bc-right-x", target_name="right", dof_values={"UX": 0.004}))
        model.add_boundary(BoundaryDef(name="bc-anchor-y", target_name="anchor", dof_values={"UY": 0.0}))
        model.add_output_request(OutputRequest(name="field-node", variables=("U", "RF"), target_type="model", position="NODE"))
        model.add_step(
            StepDef(
                name="step-plastic",
                procedure_type="static_nonlinear",
                boundary_names=("bc-left-x", "bc-right-x", "bc-anchor-y"),
                output_request_names=("field-node",),
                parameters={
                    "max_increments": 16,
                    "initial_increment": 0.0625,
                    "min_increment": 0.015625,
                    "max_iterations": 20,
                    "residual_tolerance": 1.0e-8,
                    "displacement_tolerance": 1.0e-8,
                    "allow_cutback": True,
                    "line_search": False,
                    "nlgeom": False,
                },
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-plastic",)))
        return model

    def _build_multistep_cps4_j2_model(self) -> ModelDB:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(1.0, 0.0)))
        mesh.add_node(NodeRecord(name="n3", coordinates=(1.0, 1.0)))
        mesh.add_node(NodeRecord(name="n4", coordinates=(0.0, 1.0)))
        mesh.add_element(ElementRecord(name="plate-1", type_key="CPS4", node_names=("n1", "n2", "n3", "n4")))
        mesh.add_node_set("left", ("n1", "n4"))
        mesh.add_node_set("right", ("n2", "n3"))
        mesh.add_node_set("anchor", ("n1",))
        mesh.add_element_set("plate-set", ("plate-1",))

        model = ModelDB(name="cps4-j2-multistep")
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
                    "tangent_mode": "consistent",
                },
            )
        )
        model.add_section(
            SectionDef(
                name="sec-1",
                section_type="plane_strain",
                material_name="mat-j2",
                region_name="plate-set",
                scope_name="part-1",
                parameters={"thickness": 1.0},
            )
        )
        model.add_boundary(BoundaryDef(name="bc-left-x", target_name="left", dof_values={"UX": 0.0}))
        model.add_boundary(BoundaryDef(name="bc-right-load", target_name="right", dof_values={"UX": 0.004}))
        model.add_boundary(BoundaryDef(name="bc-right-unload", target_name="right", dof_values={"UX": 0.0}))
        model.add_boundary(BoundaryDef(name="bc-anchor-y", target_name="anchor", dof_values={"UY": 0.0}))
        model.add_output_request(OutputRequest(name="field-node", variables=("U", "RF"), target_type="model", position="NODE"))
        model.add_step(
            StepDef(
                name="step-load",
                procedure_type="static_nonlinear",
                boundary_names=("bc-left-x", "bc-right-load", "bc-anchor-y"),
                output_request_names=("field-node",),
                parameters={
                    "max_increments": 16,
                    "initial_increment": 0.0625,
                    "min_increment": 0.015625,
                    "max_iterations": 20,
                    "residual_tolerance": 1.0e-8,
                    "displacement_tolerance": 1.0e-8,
                    "allow_cutback": True,
                    "line_search": False,
                    "nlgeom": False,
                },
            )
        )
        model.add_step(
            StepDef(
                name="step-unload",
                procedure_type="static_nonlinear",
                boundary_names=("bc-left-x", "bc-right-unload", "bc-anchor-y"),
                output_request_names=("field-node",),
                parameters={
                    "max_increments": 16,
                    "initial_increment": 0.0625,
                    "min_increment": 0.015625,
                    "max_iterations": 20,
                    "residual_tolerance": 1.0e-8,
                    "displacement_tolerance": 1.0e-8,
                    "allow_cutback": True,
                    "line_search": False,
                    "nlgeom": False,
                },
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-load", "step-unload")))
        return model

    def _build_c3d8_j2_model(self) -> ModelDB:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(1.0, 0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n3", coordinates=(1.0, 1.0, 0.0)))
        mesh.add_node(NodeRecord(name="n4", coordinates=(0.0, 1.0, 0.0)))
        mesh.add_node(NodeRecord(name="n5", coordinates=(0.0, 0.0, 1.0)))
        mesh.add_node(NodeRecord(name="n6", coordinates=(1.0, 0.0, 1.0)))
        mesh.add_node(NodeRecord(name="n7", coordinates=(1.0, 1.0, 1.0)))
        mesh.add_node(NodeRecord(name="n8", coordinates=(0.0, 1.0, 1.0)))
        mesh.add_element(
            ElementRecord(name="block-1", type_key="C3D8", node_names=("n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8"))
        )
        mesh.add_node_set("left", ("n1", "n4", "n5", "n8"))
        mesh.add_node_set("right", ("n2", "n3", "n6", "n7"))
        mesh.add_element_set("block-set", ("block-1",))

        model = ModelDB(name="c3d8-j2-static-nonlinear")
        model.add_part(Part(name="part-1", mesh=mesh))
        model.add_material(
            MaterialDef(
                name="mat-j2",
                material_type="j2_plastic",
                parameters={
                    "young_modulus": 200000.0,
                    "poisson_ratio": 0.3,
                    "yield_stress": 250.0,
                    "hardening_modulus": 1000.0,
                    "tangent_mode": "consistent",
                },
            )
        )
        model.add_section(
            SectionDef(
                name="sec-1",
                section_type="solid",
                material_name="mat-j2",
                region_name="block-set",
                scope_name="part-1",
                parameters={},
            )
        )
        model.add_boundary(BoundaryDef(name="bc-left-fix", target_name="left", dof_values={"UX": 0.0, "UY": 0.0, "UZ": 0.0}))
        model.add_boundary(BoundaryDef(name="bc-right-ux", target_name="right", dof_values={"UX": 0.004}))
        model.add_output_request(OutputRequest(name="field-node", variables=("U", "RF"), target_type="model", position="NODE"))
        model.add_step(
            StepDef(
                name="step-3d-plastic",
                procedure_type="static_nonlinear",
                boundary_names=("bc-left-fix", "bc-right-ux"),
                output_request_names=("field-node",),
                parameters={
                    "max_increments": 16,
                    "initial_increment": 0.0625,
                    "min_increment": 0.03125,
                    "max_iterations": 16,
                    "residual_tolerance": 1.0e-8,
                    "displacement_tolerance": 1.0e-8,
                    "allow_cutback": True,
                    "line_search": False,
                    "nlgeom": False,
                },
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-3d-plastic",)))
        return model


if __name__ == "__main__":
    unittest.main()
