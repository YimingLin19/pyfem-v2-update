"""solid finite-strain J2 验证测试。"""

from __future__ import annotations

import unittest

from pyfem.compiler import Compiler
from pyfem.io import FIELD_KEY_RF, InMemoryResultsWriter
from tests.support.solid_finite_strain_j2_builders import build_c3d8_j2_model, build_cps4_j2_model


class SolidFiniteStrainJ2VerificationTests(unittest.TestCase):
    """验证 finite-strain J2 在小变形极限下退化到 small-strain J2。"""

    def test_cps4_finite_strain_j2_matches_small_strain_j2_in_small_deformation_limit(self) -> None:
        small_compiled = Compiler().compile(
            build_cps4_j2_model(
                model_name="cps4-small-strain-j2-limit",
                nlgeom=False,
                right_displacement=1.0e-5,
            )
        )
        finite_compiled = Compiler().compile(
            build_cps4_j2_model(
                model_name="cps4-finite-strain-j2-limit",
                nlgeom=True,
                right_displacement=1.0e-5,
            )
        )

        small_writer = InMemoryResultsWriter()
        finite_writer = InMemoryResultsWriter()
        small_compiled.get_step_runtime("step-static").run(small_writer)
        finite_compiled.get_step_runtime("step-static").run(finite_writer)

        small_frame = small_writer.read_step("step-static").frames[-1]
        finite_frame = finite_writer.read_step("step-static").frames[-1]
        small_reaction = sum(
            float(small_frame.get_field(FIELD_KEY_RF).values[node_name]["UX"])
            for node_name in ("part-1.n2", "part-1.n3")
        )
        finite_reaction = sum(
            float(finite_frame.get_field(FIELD_KEY_RF).values[node_name]["UX"])
            for node_name in ("part-1.n2", "part-1.n3")
        )
        small_point = small_compiled.get_step_runtime("step-static").problem.get_committed_state().integration_point_states[
            "part-1.plate-1"
        ]["ip1"]
        finite_point = finite_compiled.get_step_runtime("step-static").problem.get_committed_state().integration_point_states[
            "part-1.plate-1"
        ]["ip1"]

        self.assertAlmostEqual(finite_reaction, small_reaction, delta=max(1.0e-8, abs(small_reaction) * 5.0e-4))
        self.assertAlmostEqual(float(finite_point["stress"][0]), float(small_point["stress"][0]), delta=5.0e-3)
        self.assertAlmostEqual(float(finite_point["stress"][1]), float(small_point["stress"][1]), delta=5.0e-3)

    def test_c3d8_finite_strain_j2_matches_small_strain_j2_in_small_deformation_limit(self) -> None:
        small_compiled = Compiler().compile(
            build_c3d8_j2_model(
                model_name="c3d8-small-strain-j2-limit",
                nlgeom=False,
                right_displacement=1.0e-5,
            )
        )
        finite_compiled = Compiler().compile(
            build_c3d8_j2_model(
                model_name="c3d8-finite-strain-j2-limit",
                nlgeom=True,
                right_displacement=1.0e-5,
            )
        )

        small_writer = InMemoryResultsWriter()
        finite_writer = InMemoryResultsWriter()
        small_compiled.get_step_runtime("step-static").run(small_writer)
        finite_compiled.get_step_runtime("step-static").run(finite_writer)

        small_frame = small_writer.read_step("step-static").frames[-1]
        finite_frame = finite_writer.read_step("step-static").frames[-1]
        small_reaction = sum(
            float(small_frame.get_field(FIELD_KEY_RF).values[node_name]["UX"])
            for node_name in ("part-1.n2", "part-1.n3", "part-1.n6", "part-1.n7")
        )
        finite_reaction = sum(
            float(finite_frame.get_field(FIELD_KEY_RF).values[node_name]["UX"])
            for node_name in ("part-1.n2", "part-1.n3", "part-1.n6", "part-1.n7")
        )
        small_point = small_compiled.get_step_runtime("step-static").problem.get_committed_state().integration_point_states[
            "part-1.block-1"
        ]["ip1"]
        finite_point = finite_compiled.get_step_runtime("step-static").problem.get_committed_state().integration_point_states[
            "part-1.block-1"
        ]["ip1"]

        self.assertAlmostEqual(finite_reaction, small_reaction, delta=max(1.0e-8, abs(small_reaction) * 5.0e-4))
        self.assertAlmostEqual(float(finite_point["stress"][0]), float(small_point["stress"][0]), delta=5.0e-3)
        self.assertAlmostEqual(float(finite_point["stress"][1]), float(small_point["stress"][1]), delta=5.0e-3)
        self.assertAlmostEqual(float(finite_point["stress"][2]), float(small_point["stress"][2]), delta=5.0e-3)


if __name__ == "__main__":
    unittest.main()
