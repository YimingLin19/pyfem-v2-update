"""C3D8 solid nlgeom 正式主线回归测试。"""

from __future__ import annotations

import unittest

from pyfem.compiler import Compiler
from pyfem.foundation.errors import CompilationError
from pyfem.io import FIELD_KEY_RF, FIELD_KEY_U, InMemoryResultsWriter
from pyfem.mesh import ElementRecord, Mesh, NodeRecord, Part
from pyfem.modeldb import BoundaryDef, JobDef, MaterialDef, ModelDB, NodalLoadDef, OutputRequest, SectionDef, StepDef


class C3D8NlgeomRegressionTests(unittest.TestCase):
    """验证 C3D8 total_lagrangian 主线与边界约束。"""

    def test_c3d8_nlgeom_path_runs_through_formal_pipeline(self) -> None:
        compiled_model = Compiler().compile(self._build_force_driven_block_model(model_name="c3d8-nlgeom-formal"))
        writer = InMemoryResultsWriter()

        compiled_model.get_step_runtime("step-static").run(writer)

        summary = writer.read_summary("step-static", "static_nonlinear_summary").data
        load_history = writer.read_history("step-static", "load_factor").get_series()
        iteration_history = writer.read_history("step-static", "iteration_count").get_series()

        self.assertTrue(bool(summary["nlgeom"]))
        self.assertEqual(float(summary["load_factor"]), 1.0)
        self.assertEqual(int(summary["converged_increment_count"]), 8)
        self.assertEqual(load_history, (0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0))
        self.assertEqual(len(iteration_history), 9)
        self.assertTrue(all(int(value) >= 4 for value in iteration_history[1:]))

    def test_c3d8_nlgeom_matches_small_strain_limit_under_small_displacement(self) -> None:
        linear_writer = self._run_single_step(
            self._build_uniform_extension_model(
                model_name="c3d8-small-strain-linear",
                procedure_type="static_linear",
                nlgeom=False,
                right_displacement=1.0e-5,
            )
        )
        nonlinear_writer = self._run_single_step(
            self._build_uniform_extension_model(
                model_name="c3d8-small-strain-nlgeom",
                procedure_type="static_nonlinear",
                nlgeom=True,
                right_displacement=1.0e-5,
            )
        )

        linear_frame = linear_writer.read_step("step-static").frames[-1]
        nonlinear_frame = nonlinear_writer.read_step("step-static").frames[-1]
        linear_reaction = self._sum_reaction_x(
            linear_frame,
            node_names=("part-1.n2", "part-1.n3", "part-1.n6", "part-1.n7"),
        )
        nonlinear_reaction = self._sum_reaction_x(
            nonlinear_frame,
            node_names=("part-1.n2", "part-1.n3", "part-1.n6", "part-1.n7"),
        )

        self.assertAlmostEqual(
            nonlinear_reaction,
            linear_reaction,
            delta=max(1.0e-10, abs(linear_reaction) * 2.0e-4),
        )
        self.assertAlmostEqual(
            nonlinear_frame.get_field(FIELD_KEY_U).values["part-1.n2"]["UX"],
            linear_frame.get_field(FIELD_KEY_U).values["part-1.n2"]["UX"],
            delta=1.0e-12,
        )

    def test_c3d8_nlgeom_cutback_keeps_committed_point_state_clean(self) -> None:
        reference_compiled, reference_writer = self._run_model(
            self._build_force_driven_block_model(
                model_name="c3d8-nlgeom-reference",
                initial_increment=0.5,
                min_increment=0.125,
                max_iterations=5,
            )
        )
        cutback_compiled, cutback_writer = self._run_model(
            self._build_force_driven_block_model(
                model_name="c3d8-nlgeom-cutback",
                initial_increment=1.0,
                min_increment=0.125,
                max_iterations=5,
            )
        )

        reference_summary = reference_writer.read_summary("step-static", "static_nonlinear_summary").data
        cutback_summary = cutback_writer.read_summary("step-static", "static_nonlinear_summary").data
        reference_state = reference_compiled.get_step_runtime("step-static").problem.get_committed_state()
        cutback_state = cutback_compiled.get_step_runtime("step-static").problem.get_committed_state()
        reference_point = reference_state.integration_point_states["part-1.block-1"]["ip1"]
        cutback_point = cutback_state.integration_point_states["part-1.block-1"]["ip1"]

        self.assertEqual(int(reference_summary["cutback_count"]), 0)
        self.assertEqual(int(cutback_summary["cutback_count"]), 1)
        self.assertEqual(int(cutback_summary["failed_attempt_count"]), 1)
        self.assertEqual(int(cutback_summary["increment_attempt_count"]), 3)
        self._assert_float_tuple_close(reference_point["strain"], cutback_point["strain"])
        self._assert_float_tuple_close(reference_point["stress"], cutback_point["stress"])
        self.assertAlmostEqual(
            float(reference_point["jacobian_ratio"]),
            float(cutback_point["jacobian_ratio"]),
            delta=1.0e-12,
        )

    def test_c3d8_j2_with_nlgeom_enabled_runs_formal_pipeline(self) -> None:
        compiled_model = Compiler().compile(self._build_c3d8_j2_nlgeom_model())
        writer = InMemoryResultsWriter()

        compiled_model.get_step_runtime("step-static").run(writer)

        summary = writer.read_summary("step-static", "static_nonlinear_summary").data
        committed_state = compiled_model.get_step_runtime("step-static").problem.get_committed_state()
        point_state = committed_state.integration_point_states["part-1.block-1"]["ip1"]

        self.assertGreater(int(summary["converged_increment_count"]), 1)
        self.assertGreater(float(point_state["material_state"]["equivalent_plastic_strain"]), 0.0)
        self.assertEqual(point_state["strain_measure"], "green_lagrange")
        self.assertEqual(point_state["stress_measure"], "second_piola_kirchhoff")

    def _run_single_step(self, model: ModelDB) -> InMemoryResultsWriter:
        _, writer = self._run_model(model)
        return writer

    def _run_model(self, model: ModelDB) -> tuple[object, InMemoryResultsWriter]:
        compiled_model = Compiler().compile(model)
        writer = InMemoryResultsWriter()
        compiled_model.get_step_runtime("step-static").run(writer)
        return compiled_model, writer

    def _sum_reaction_x(self, frame, *, node_names: tuple[str, ...]) -> float:
        reaction_field = frame.get_field(FIELD_KEY_RF).values
        return sum(float(reaction_field[node_name]["UX"]) for node_name in node_names)

    def _assert_float_tuple_close(
        self,
        expected: tuple[float, ...],
        actual: tuple[float, ...],
        *,
        tolerance: float = 1.0e-12,
    ) -> None:
        self.assertEqual(len(expected), len(actual))
        for expected_value, actual_value in zip(expected, actual, strict=True):
            self.assertAlmostEqual(float(actual_value), float(expected_value), delta=tolerance)

    def _build_uniform_extension_model(
        self,
        *,
        model_name: str,
        procedure_type: str,
        nlgeom: bool,
        right_displacement: float,
    ) -> ModelDB:
        mesh = self._build_block_mesh()
        mesh.add_node_set("all", tuple(self._node_names()))

        model = ModelDB(name=model_name)
        model.add_part(Part(name="part-1", mesh=mesh))
        model.add_material(
            MaterialDef(
                name="mat-1",
                material_type="linear_elastic",
                parameters={"young_modulus": 1000.0, "poisson_ratio": 0.25},
            )
        )
        model.add_section(
            SectionDef(
                name="sec-1",
                section_type="solid",
                material_name="mat-1",
                region_name="block-set",
                scope_name="part-1",
                parameters={},
            )
        )
        model.add_boundary(BoundaryDef(name="bc-left-x", target_name="left", dof_values={"UX": 0.0}))
        model.add_boundary(BoundaryDef(name="bc-right-x", target_name="right", dof_values={"UX": right_displacement}))
        model.add_boundary(BoundaryDef(name="bc-all-yz", target_name="all", dof_values={"UY": 0.0, "UZ": 0.0}))
        model.add_output_request(OutputRequest(name="field-node", variables=("U", "RF"), target_type="model", position="NODE"))
        step_parameters = {}
        if procedure_type == "static_nonlinear":
            step_parameters = {
                "max_increments": 2,
                "initial_increment": 0.5,
                "min_increment": 0.5,
                "max_iterations": 8,
                "residual_tolerance": 1.0e-12,
                "displacement_tolerance": 1.0e-12,
                "allow_cutback": True,
                "line_search": False,
                "nlgeom": nlgeom,
            }
        model.add_step(
            StepDef(
                name="step-static",
                procedure_type=procedure_type,
                boundary_names=("bc-left-x", "bc-right-x", "bc-all-yz"),
                output_request_names=("field-node",),
                parameters=step_parameters,
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-static",)))
        return model

    def _build_force_driven_block_model(
        self,
        *,
        model_name: str,
        initial_increment: float = 0.125,
        min_increment: float = 0.125,
        max_iterations: int = 12,
    ) -> ModelDB:
        mesh = self._build_block_mesh()
        for node_name in ("n2", "n3", "n6", "n7"):
            mesh.add_node_set(f"load-{node_name}", (node_name,))

        model = ModelDB(name=model_name)
        model.add_part(Part(name="part-1", mesh=mesh))
        model.add_material(
            MaterialDef(
                name="mat-1",
                material_type="linear_elastic",
                parameters={"young_modulus": 1000.0, "poisson_ratio": 0.25},
            )
        )
        model.add_section(
            SectionDef(
                name="sec-1",
                section_type="solid",
                material_name="mat-1",
                region_name="block-set",
                scope_name="part-1",
                parameters={},
            )
        )
        model.add_boundary(BoundaryDef(name="bc-left", target_name="left", dof_values={"UX": 0.0, "UY": 0.0, "UZ": 0.0}))
        for node_name in ("n2", "n3", "n6", "n7"):
            model.add_nodal_load(
                NodalLoadDef(
                    name=f"load-{node_name}",
                    target_name=f"load-{node_name}",
                    components={"FX": 100.0},
                )
            )
        model.add_output_request(OutputRequest(name="field-node", variables=("U", "RF"), target_type="model", position="NODE"))
        model.add_step(
            StepDef(
                name="step-static",
                procedure_type="static_nonlinear",
                boundary_names=("bc-left",),
                nodal_load_names=("load-n2", "load-n3", "load-n6", "load-n7"),
                output_request_names=("field-node",),
                parameters={
                    "max_increments": 32,
                    "initial_increment": initial_increment,
                    "min_increment": min_increment,
                    "max_iterations": max_iterations,
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

    def _build_c3d8_j2_nlgeom_model(self) -> ModelDB:
        mesh = self._build_block_mesh()

        model = ModelDB(name="c3d8-j2-nlgeom")
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
        model.add_boundary(BoundaryDef(name="bc-left", target_name="left", dof_values={"UX": 0.0, "UY": 0.0, "UZ": 0.0}))
        model.add_boundary(BoundaryDef(name="bc-right-x", target_name="right", dof_values={"UX": 0.004}))
        model.add_output_request(OutputRequest(name="field-node", variables=(FIELD_KEY_U, FIELD_KEY_RF), target_type="model", position="NODE"))
        model.add_step(
            StepDef(
                name="step-static",
                procedure_type="static_nonlinear",
                boundary_names=("bc-left", "bc-right-x"),
                output_request_names=("field-node",),
                parameters={
                    "max_increments": 4,
                    "initial_increment": 0.25,
                    "min_increment": 0.25,
                    "max_iterations": 20,
                    "residual_tolerance": 1.0e-8,
                    "displacement_tolerance": 1.0e-8,
                    "allow_cutback": True,
                    "line_search": False,
                    "nlgeom": True,
                },
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-static",)))
        return model

    def _build_block_mesh(self) -> Mesh:
        mesh = Mesh()
        for node_name, coordinates in zip(
            self._node_names(),
            (
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (1.0, 1.0, 0.0),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0),
                (1.0, 0.0, 1.0),
                (1.0, 1.0, 1.0),
                (0.0, 1.0, 1.0),
            ),
            strict=True,
        ):
            mesh.add_node(NodeRecord(name=node_name, coordinates=coordinates))
        mesh.add_element(
            ElementRecord(
                name="block-1",
                type_key="C3D8",
                node_names=("n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8"),
            )
        )
        mesh.add_node_set("left", ("n1", "n4", "n5", "n8"))
        mesh.add_node_set("right", ("n2", "n3", "n6", "n7"))
        mesh.add_element_set("block-set", ("block-1",))
        return mesh

    def _node_names(self) -> tuple[str, ...]:
        return ("n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8")


if __name__ == "__main__":
    unittest.main()
