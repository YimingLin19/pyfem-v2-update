"""solid finite-strain J2 正式耦合回归测试。"""

from __future__ import annotations

import unittest

from pyfem.compiler import Compiler
from pyfem.foundation.errors import CompilationError
from pyfem.io import FIELD_KEY_RF, FIELD_KEY_U, InMemoryResultsWriter
from pyfem.modeldb import SectionDef
from tests.support.solid_finite_strain_j2_builders import (
    build_c3d8_j2_model,
    build_c3d8_j2_multistep_model,
    build_cps4_j2_model,
)


class SolidFiniteStrainJ2CouplingRegressionTests(unittest.TestCase):
    """验证 solid finite-strain J2 的正式主线闭环。"""

    def test_c3d8_finite_strain_j2_monotonic_loading_shows_plastic_response(self) -> None:
        compiled_model = Compiler().compile(
            build_c3d8_j2_model(
                model_name="c3d8-finite-strain-j2-monotonic",
                nlgeom=True,
                right_displacement=0.004,
            )
        )
        writer = InMemoryResultsWriter()

        compiled_model.get_step_runtime("step-static").run(writer)

        step = writer.read_step("step-static")
        right_displacements: list[float] = []
        right_reactions: list[float] = []
        for frame in step.frames[1:]:
            displacement_field = frame.get_field(FIELD_KEY_U).values
            reaction_field = frame.get_field(FIELD_KEY_RF).values
            right_displacements.append(float(displacement_field["part-1.n2"]["UX"]))
            right_reactions.append(
                sum(float(reaction_field[node_name]["UX"]) for node_name in ("part-1.n2", "part-1.n3", "part-1.n6", "part-1.n7"))
            )

        elastic_slope = (right_reactions[1] - right_reactions[0]) / (right_displacements[1] - right_displacements[0])
        plastic_slope = (right_reactions[-1] - right_reactions[-2]) / (right_displacements[-1] - right_displacements[-2])
        point_state = compiled_model.get_step_runtime("step-static").problem.get_committed_state().integration_point_states[
            "part-1.block-1"
        ]["ip1"]

        self.assertLess(plastic_slope, 0.8 * elastic_slope)
        self.assertGreater(float(point_state["material_state"]["equivalent_plastic_strain"]), 0.0)
        self.assertEqual(point_state["strain_measure"], "green_lagrange")
        self.assertEqual(point_state["stress_measure"], "second_piola_kirchhoff")

    def test_cps4_finite_strain_j2_cutback_keeps_committed_history_clean(self) -> None:
        reference_compiled = Compiler().compile(
            build_cps4_j2_model(
                model_name="cps4-finite-strain-j2-reference",
                nlgeom=True,
                right_displacement=0.004,
                initial_increment=0.125,
                min_increment=0.125,
                max_increments=8,
                max_iterations=12,
            )
        )
        reference_writer = InMemoryResultsWriter()
        reference_compiled.get_step_runtime("step-static").run(reference_writer)

        cutback_compiled = Compiler().compile(
            build_cps4_j2_model(
                model_name="cps4-finite-strain-j2-cutback",
                nlgeom=True,
                right_displacement=0.004,
                initial_increment=1.0,
                min_increment=0.125,
                max_increments=16,
                max_iterations=4,
            )
        )
        cutback_writer = InMemoryResultsWriter()
        cutback_compiled.get_step_runtime("step-static").run(cutback_writer)

        reference_summary = reference_writer.read_summary("step-static", "static_nonlinear_summary").data
        cutback_summary = cutback_writer.read_summary("step-static", "static_nonlinear_summary").data
        reference_point = reference_compiled.get_step_runtime("step-static").problem.get_committed_state().integration_point_states[
            "part-1.plate-1"
        ]["ip1"]
        cutback_point = cutback_compiled.get_step_runtime("step-static").problem.get_committed_state().integration_point_states[
            "part-1.plate-1"
        ]["ip1"]

        self.assertEqual(int(reference_summary["cutback_count"]), 0)
        self.assertGreater(int(cutback_summary["cutback_count"]), 0)
        self.assertAlmostEqual(
            float(reference_point["material_state"]["equivalent_plastic_strain"]),
            float(cutback_point["material_state"]["equivalent_plastic_strain"]),
            delta=2.0e-6,
        )
        self.assertAlmostEqual(float(reference_point["stress"][0]), float(cutback_point["stress"][0]), delta=2.0e-1)
        self.assertAlmostEqual(float(reference_point["stress"][1]), float(cutback_point["stress"][1]), delta=2.0e-1)

    def test_c3d8_finite_strain_j2_multistep_inherits_committed_history(self) -> None:
        compiled_model = Compiler().compile(
            build_c3d8_j2_multistep_model(
                model_name="c3d8-finite-strain-j2-multistep",
                nlgeom=True,
            )
        )
        writer = InMemoryResultsWriter()

        compiled_model.get_step_runtime("step-load").run(writer)
        inherited_state = compiled_model.resolve_inherited_step_state("step-unload", "solid_mechanics_history")
        compiled_model.get_step_runtime("step-unload").run(writer)

        load_step = writer.read_step("step-load")
        unload_step = writer.read_step("step-unload")
        committed_state = compiled_model.get_step_runtime("step-unload").problem.get_committed_state()
        inherited_point = inherited_state.integration_point_states["part-1.block-1"]["ip1"]
        committed_point = committed_state.integration_point_states["part-1.block-1"]["ip1"]

        self.assertIsNotNone(inherited_state)
        self.assertAlmostEqual(
            float(unload_step.frames[0].get_field(FIELD_KEY_U).values["part-1.n2"]["UX"]),
            float(load_step.frames[-1].get_field(FIELD_KEY_U).values["part-1.n2"]["UX"]),
            delta=1.0e-10,
        )
        self.assertGreater(float(inherited_point["material_state"]["equivalent_plastic_strain"]), 0.0)
        self.assertGreaterEqual(
            float(committed_point["material_state"]["equivalent_plastic_strain"]),
            float(inherited_point["material_state"]["equivalent_plastic_strain"]),
        )

    def test_cps4_plane_stress_finite_strain_j2_keeps_clear_fail_fast_boundary(self) -> None:
        model = build_cps4_j2_model(
            model_name="cps4-plane-stress-finite-strain-j2",
            nlgeom=True,
            right_displacement=0.004,
        )
        model.sections["sec-1"] = SectionDef(
            name="sec-1",
            section_type="plane_stress",
            material_name="mat-j2",
            region_name="plate-set",
            scope_name="part-1",
            parameters={"thickness": 1.0},
        )

        with self.assertRaisesRegex(CompilationError, "PlaneStressSection \\+ J2"):
            Compiler().compile(model)


if __name__ == "__main__":
    unittest.main()
