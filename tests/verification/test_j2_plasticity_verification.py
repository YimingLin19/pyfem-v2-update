"""J2 塑性材料验证测试。"""

from __future__ import annotations

import unittest

import numpy

from pyfem.kernel.materials import J2PlasticityRuntime


class J2PlasticityVerificationTests(unittest.TestCase):
    """验证 J2 塑性材料的基础路径行为。"""

    def test_j2_material_exhibits_post_yield_tangent_reduction(self) -> None:
        material = J2PlasticityRuntime(
            name="j2-steel",
            young_modulus=200000.0,
            poisson_ratio=0.3,
            yield_stress=250.0,
            hardening_modulus=1000.0,
        )

        first_response = material.update((5.0e-4, 0.0, 0.0), mode="plane_strain")
        second_response = material.update((2.0e-3, 0.0, 0.0), state=first_response.state, mode="plane_strain")
        elastic_tangent = first_response.tangent[0][0]
        plastic_tangent = second_response.tangent[0][0]

        self.assertGreater(first_response.stress[0], 0.0)
        self.assertGreater(second_response.state["equivalent_plastic_strain"], 0.0)
        self.assertLess(plastic_tangent, 0.7 * elastic_tangent)

    def test_j2_material_unloading_path_contains_residual_plastic_strain(self) -> None:
        material = J2PlasticityRuntime(
            name="j2-steel",
            young_modulus=200000.0,
            poisson_ratio=0.3,
            yield_stress=250.0,
            hardening_modulus=1500.0,
        )

        loaded_response = material.update((4.0e-3, 0.0, 0.0, 0.0, 0.0, 0.0), mode="3d")
        self.assertGreater(loaded_response.state["equivalent_plastic_strain"], 0.0)

        unload_strains = [0.0040, 0.0030, 0.0020, 0.0010, 0.0005, 0.0002, 0.0001, 0.0]
        previous_strain = unload_strains[0]
        previous_stress = loaded_response.stress[0]
        zero_stress_strain = None

        for current_strain in unload_strains[1:]:
            response = material.update(
                (current_strain, 0.0, 0.0, 0.0, 0.0, 0.0),
                state=loaded_response.state,
                mode="3d",
            )
            current_stress = response.stress[0]
            if previous_stress >= 0.0 >= current_stress:
                weight = previous_stress / (previous_stress - current_stress)
                zero_stress_strain = previous_strain + weight * (current_strain - previous_strain)
                break
            previous_strain = current_strain
            previous_stress = current_stress

        self.assertIsNotNone(zero_stress_strain)
        self.assertGreater(zero_stress_strain, 0.0)
        self.assertGreater(loaded_response.state["plastic_strain"][0], 0.0)

    def test_j2_consistent_tangent_matches_numerical_debug_branch_at_plastic_point(self) -> None:
        consistent_material = J2PlasticityRuntime(
            name="j2-consistent",
            young_modulus=200000.0,
            poisson_ratio=0.3,
            yield_stress=250.0,
            hardening_modulus=1000.0,
            tangent_mode="consistent",
        )
        numerical_material = J2PlasticityRuntime(
            name="j2-numerical",
            young_modulus=200000.0,
            poisson_ratio=0.3,
            yield_stress=250.0,
            hardening_modulus=1000.0,
            tangent_mode="numerical",
        )

        preload_response = consistent_material.update((2.0e-3, 0.0, 0.0), mode="plane_strain")
        consistent_response = consistent_material.update(
            (2.4e-3, 0.0, 2.0e-4),
            state=preload_response.state,
            mode="plane_strain",
        )
        numerical_response = numerical_material.update(
            (2.4e-3, 0.0, 2.0e-4),
            state=preload_response.state,
            mode="plane_strain",
        )

        consistent_tangent = numpy.asarray(consistent_response.tangent, dtype=float)
        numerical_tangent = numpy.asarray(numerical_response.tangent, dtype=float)
        self.assertTrue(numpy.allclose(consistent_tangent, numerical_tangent, rtol=5.0e-2, atol=5.0e1))


if __name__ == "__main__":
    unittest.main()
