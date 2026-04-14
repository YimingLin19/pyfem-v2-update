"""Phase 2 patch tests。"""

import unittest

import numpy

from pyfem.foundation.types import ElementLocation
from pyfem.kernel.elements import B21Runtime, C3D8Runtime, CPS4Runtime
from pyfem.kernel.materials import ElasticIsotropicRuntime
from pyfem.kernel.sections import BeamSectionRuntime, PlaneStressSectionRuntime, SolidSectionRuntime


class PatchVerificationTests(unittest.TestCase):
    """验证 C3D8 / CPS4 / B21 的 patch 响应。"""

    def test_c3d8_rigid_translation_patch_produces_zero_strain_and_zero_residual(self) -> None:
        material = ElasticIsotropicRuntime(name="solid-mat", young_modulus=1000.0, poisson_ratio=0.25, density=2.5)
        section = SolidSectionRuntime(name="solid-sec", material_runtime=material)
        element = C3D8Runtime(
            location=ElementLocation(scope_name="part-1", element_name="e1"),
            coordinates=(
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (1.0, 1.0, 0.0),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0),
                (1.0, 0.0, 1.0),
                (1.0, 1.0, 1.0),
                (0.0, 1.0, 1.0),
            ),
            node_names=("n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8"),
            dof_indices=tuple(range(24)),
            section_runtime=section,
            material_runtime=material,
        )
        rigid_translation = (
            0.1,
            -0.2,
            0.05,
            0.1,
            -0.2,
            0.05,
            0.1,
            -0.2,
            0.05,
            0.1,
            -0.2,
            0.05,
            0.1,
            -0.2,
            0.05,
            0.1,
            -0.2,
            0.05,
            0.1,
            -0.2,
            0.05,
            0.1,
            -0.2,
            0.05,
        )

        contribution = element.tangent_residual(displacement=rigid_translation)
        stiffness = numpy.asarray(contribution.stiffness, dtype=float)
        residual = numpy.asarray(contribution.residual, dtype=float)
        mass = numpy.asarray(element.mass(), dtype=float)
        output = element.output()

        self.assertTrue(numpy.allclose(stiffness, stiffness.T, atol=1.0e-8, rtol=1.0e-10))
        self.assertTrue(numpy.allclose(residual, 0.0, atol=1.0e-10, rtol=1.0e-10))
        self.assertAlmostEqual(float(numpy.sum(numpy.diag(mass)[0::3])), 2.5)
        self.assertAlmostEqual(float(numpy.sum(numpy.diag(mass)[1::3])), 2.5)
        self.assertAlmostEqual(float(numpy.sum(numpy.diag(mass)[2::3])), 2.5)
        self.assertTrue(numpy.allclose(output["strain"], 0.0))
        self.assertTrue(numpy.allclose(output["stress"], 0.0))

    def test_cps4_constant_strain_patch_matches_centroid_response(self) -> None:
        material = ElasticIsotropicRuntime(name="plane-mat", young_modulus=1200.0, poisson_ratio=0.25, density=3.0)
        section = PlaneStressSectionRuntime(name="plane-sec", material_runtime=material, thickness=2.0)
        element = CPS4Runtime(
            location=ElementLocation(scope_name="part-1", element_name="e2"),
            coordinates=((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
            node_names=("n1", "n2", "n3", "n4"),
            dof_indices=tuple(range(8)),
            section_runtime=section,
            material_runtime=material,
        )
        strain = numpy.asarray((2.0e-3, -1.0e-3, 5.0e-4), dtype=float)
        displacement = (
            0.0,
            0.0,
            strain[0],
            0.5 * strain[2],
            strain[0] + 0.5 * strain[2],
            strain[1] + 0.5 * strain[2],
            0.5 * strain[2],
            strain[1],
        )

        contribution = element.tangent_residual(displacement=displacement)
        stiffness = numpy.asarray(contribution.stiffness, dtype=float)
        mass = numpy.asarray(element.mass(), dtype=float)
        output = element.output(displacement=displacement)
        expected_response = material.update(tuple(strain.tolist()), mode="plane_stress")

        self.assertTrue(numpy.allclose(stiffness, stiffness.T, atol=1.0e-8, rtol=1.0e-10))
        self.assertTrue(numpy.allclose(output["strain"], strain, atol=1.0e-12, rtol=1.0e-12))
        self.assertTrue(numpy.allclose(output["stress"], expected_response.stress, atol=1.0e-12, rtol=1.0e-12))
        self.assertAlmostEqual(float(numpy.sum(numpy.diag(mass)[0::2])), 6.0)
        self.assertAlmostEqual(float(numpy.sum(numpy.diag(mass)[1::2])), 6.0)
        self.assertEqual(output["thickness"], 2.0)

    def test_b21_rigid_body_patch_has_zero_internal_force_and_section_output(self) -> None:
        material = ElasticIsotropicRuntime(name="beam-mat", young_modulus=1.0e6, poisson_ratio=0.3, density=4.0)
        section = BeamSectionRuntime(name="beam-sec", material_runtime=material, area=0.03, moment_inertia_z=2.0e-4)
        element = B21Runtime(
            location=ElementLocation(scope_name="part-1", element_name="e3"),
            coordinates=((0.0, 0.0), (2.0, 0.0)),
            node_names=("n1", "n2"),
            dof_indices=tuple(range(6)),
            section_runtime=section,
            material_runtime=material,
        )
        rigid_body_motion = (0.3, -0.2, 0.0, 0.3, -0.2, 0.0)

        contribution = element.tangent_residual(displacement=rigid_body_motion)
        stiffness = numpy.asarray(contribution.stiffness, dtype=float)
        residual = numpy.asarray(contribution.residual, dtype=float)
        output = element.output(displacement=rigid_body_motion)

        self.assertTrue(numpy.allclose(stiffness, stiffness.T, atol=1.0e-8, rtol=1.0e-10))
        self.assertTrue(numpy.allclose(residual, 0.0, atol=1.0e-10, rtol=1.0e-10))
        self.assertAlmostEqual(float(output["axial_strain"]), 0.0, places=12)
        self.assertAlmostEqual(float(output["axial_stress"]), 0.0, places=12)
        self.assertAlmostEqual(float(output["axial_force"]), 0.0, places=12)
        self.assertAlmostEqual(float(output["end_moment_i"]), 0.0, places=12)
        self.assertAlmostEqual(float(output["end_moment_j"]), 0.0, places=12)


if __name__ == "__main__":
    unittest.main()
