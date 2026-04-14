"""Phase 2 最小 benchmark 保护集。"""

import math
import unittest

from tests.support import (
    build_c3d8_pressure_block_model,
    build_cps4_tension_model,
    build_dynamic_beam_benchmark_model,
    build_modal_beam_benchmark_model,
    build_static_beam_benchmark_model,
    run_step,
)


class BenchmarkMinimumSetTests(unittest.TestCase):
    """验证梁 / 平面 / 实体的最小 benchmark 保护集。"""

    def test_b21_static_cantilever_matches_euler_bernoulli_solution(self) -> None:
        _, writer = run_step(build_static_beam_benchmark_model(), "step-static")

        frame = writer.read_frame("step-static", 0)
        displacement = frame.get_field("U").values["part-1.n2"]
        reaction = frame.get_field("RF").values["part-1.n1"]
        section_output = frame.get_field("SECTION").values["part-1.beam-1"]

        self.assertAlmostEqual(displacement["UY"], -0.16, places=12)
        self.assertAlmostEqual(displacement["RZ"], -0.12, places=12)
        self.assertAlmostEqual(reaction["UY"], 12.0, places=12)
        self.assertAlmostEqual(reaction["RZ"], 24.0, places=12)
        self.assertAlmostEqual(section_output["end_moment_i"], 24.0, places=12)
        self.assertAlmostEqual(section_output["end_moment_j"], 0.0, places=12)

    def test_b21_modal_axial_frequency_matches_closed_form(self) -> None:
        _, writer = run_step(build_modal_beam_benchmark_model(), "step-modal")

        frequency = writer.read_history("step-modal", "FREQUENCY").get_series()[0]
        expected_frequency = math.sqrt(3.0 * 1.0e6 / (4.0 * 2.0**2)) / (2.0 * math.pi)

        self.assertAlmostEqual(frequency, expected_frequency, places=10)
        self.assertAlmostEqual(writer.read_frame("step-modal", 0).get_field("MODE_SHAPE").values["part-1.n2"]["UX"], 1.0, places=10)

    def test_b21_implicit_dynamic_free_vibration_matches_closed_form(self) -> None:
        _, writer = run_step(build_dynamic_beam_benchmark_model(), "step-dynamic")

        last_frame = writer.frames[-1]
        tip_ux = last_frame.get_field("U").values["part-1.n2"]["UX"]
        omega = math.sqrt(3.0 * 1.0e6 / (4.0 * 2.0**2))
        expected_tip = 0.01 * math.cos(omega * 0.005)

        self.assertEqual(len(writer.frames), 11)
        self.assertAlmostEqual(tip_ux, expected_tip, delta=1.0e-4)

    def test_cps4_uniaxial_tension_matches_uniform_stress_solution(self) -> None:
        _, writer = run_step(build_cps4_tension_model(), "step-static")

        frame = writer.read_frame("step-static", 0)
        displacement = frame.get_field("U").values
        stress = frame.get_field("S").values["plate-part.plate-1"]
        right_reaction = sum(frame.get_field("RF").values[node_key]["UX"] for node_key in ("plate-part.n2", "plate-part.n3"))

        self.assertAlmostEqual(displacement["plate-part.n2"]["UX"], 0.001, places=12)
        self.assertAlmostEqual(displacement["plate-part.n3"]["UX"], 0.001, places=12)
        self.assertAlmostEqual(displacement["plate-part.n4"]["UY"], -2.5e-4, delta=1.0e-8)
        self.assertAlmostEqual(displacement["plate-part.n3"]["UY"], -2.5e-4, delta=1.0e-8)
        self.assertAlmostEqual(stress[0], 1.0, delta=1.0e-8)
        self.assertAlmostEqual(stress[1], 0.0, delta=1.0e-8)
        self.assertAlmostEqual(stress[2], 0.0, delta=1.0e-8)
        self.assertAlmostEqual(abs(right_reaction), 2.0, delta=1.0e-8)

    def test_c3d8_surface_pressure_keeps_force_equilibrium_and_symmetric_tip_response(self) -> None:
        _, writer = run_step(build_c3d8_pressure_block_model(), "step-static")

        frame = writer.read_frame("step-static", 0)
        displacement = frame.get_field("U").values
        reaction = frame.get_field("RF").values
        loaded_node_keys = ("block-part.1", "block-part.2", "block-part.3", "block-part.4")
        fixed_node_keys = ("block-part.5", "block-part.6", "block-part.7", "block-part.8")
        loaded_ux = tuple(displacement[node_key]["UX"] for node_key in loaded_node_keys)
        fixed_reaction_x = sum(reaction[node_key]["UX"] for node_key in fixed_node_keys)

        self.assertTrue(all(value > 0.0 for value in loaded_ux))
        self.assertAlmostEqual(max(loaded_ux) - min(loaded_ux), 0.0, delta=1.0e-10)
        self.assertAlmostEqual(abs(fixed_reaction_x), 2.0, delta=1.0e-8)


if __name__ == "__main__":
    unittest.main()
