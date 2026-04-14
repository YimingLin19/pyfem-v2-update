"""材料与截面运行时测试。"""

import unittest

import numpy

from pyfem.kernel.materials import ElasticIsotropicRuntime
from pyfem.kernel.sections import (
    BeamSectionRuntime,
    PlaneStrainSectionRuntime,
    PlaneStressSectionRuntime,
    SolidSectionRuntime,
)


class MaterialSectionRuntimeTests(unittest.TestCase):
    """验证材料与截面运行时的基础行为。"""

    def test_elastic_isotropic_runtime_returns_expected_plane_stress_response(self) -> None:
        material = ElasticIsotropicRuntime(
            name="steel",
            young_modulus=210000.0,
            poisson_ratio=0.3,
            density=7850.0,
        )
        strain = numpy.asarray((1.0e-3, -2.0e-4, 5.0e-4), dtype=float)

        response = material.update(tuple(strain.tolist()), mode="plane_stress")
        tangent = numpy.asarray(response.tangent, dtype=float)
        stress = numpy.asarray(response.stress, dtype=float)
        expected_tangent = 210000.0 / (1.0 - 0.3**2) * numpy.asarray(
            (
                (1.0, 0.3, 0.0),
                (0.3, 1.0, 0.0),
                (0.0, 0.0, (1.0 - 0.3) / 2.0),
            ),
            dtype=float,
        )
        expected_stress = expected_tangent @ strain

        self.assertTrue(numpy.allclose(tangent, expected_tangent))
        self.assertTrue(numpy.allclose(stress, expected_stress))
        self.assertEqual(response.state["mode"], "plane_stress")
        self.assertEqual(material.get_density(), 7850.0)

    def test_section_runtimes_preserve_material_and_section_parameters(self) -> None:
        material = ElasticIsotropicRuntime(
            name="steel",
            young_modulus=210000.0,
            poisson_ratio=0.3,
            density=7850.0,
        )

        solid = SolidSectionRuntime(name="solid-sec", material_runtime=material, parameters={"family": "solid"})
        plane_stress = PlaneStressSectionRuntime(
            name="ps-sec",
            material_runtime=material,
            thickness=2.5,
            parameters={"integration": "full"},
        )
        plane_strain = PlaneStrainSectionRuntime(name="pe-sec", material_runtime=material, thickness=1.2)
        beam = BeamSectionRuntime(
            name="beam-sec",
            material_runtime=material,
            area=0.02,
            moment_inertia_z=3.0e-5,
            shear_factor=0.85,
            parameters={"profile": "rect"},
        )

        self.assertIs(solid.get_material_runtime(), material)
        self.assertIs(plane_stress.get_material_runtime(), material)
        self.assertIs(plane_strain.get_material_runtime(), material)
        self.assertIs(beam.get_material_runtime(), material)
        self.assertEqual(plane_stress.get_thickness(), 2.5)
        self.assertEqual(plane_strain.get_thickness(), 1.2)
        self.assertEqual(beam.get_area(), 0.02)
        self.assertEqual(beam.get_moment_inertia_z(), 3.0e-5)
        self.assertEqual(solid.describe()["material_name"], "steel")
        self.assertEqual(plane_stress.describe()["thickness"], 2.5)
        self.assertEqual(beam.describe()["shear_factor"], 0.85)


if __name__ == "__main__":
    unittest.main()
