import unittest

import numpy

from pyfem.foundation.types import ElementLocation
from pyfem.io import (
    FIELD_KEY_S_AVG,
    FIELD_KEY_S_IP,
    FIELD_KEY_S_PRINCIPAL_AVG,
    FIELD_KEY_S_PRINCIPAL_IP,
    FIELD_KEY_S_REC,
    FIELD_KEY_S_VM_AVG,
    FIELD_KEY_S_VM_IP,
    FIELD_KEY_S_VM_REC,
)
from pyfem.kernel.elements import B21Runtime, C3D8Runtime, CPS4Runtime
from pyfem.kernel.materials import ElasticIsotropicRuntime
from pyfem.kernel.sections import BeamSectionRuntime, PlaneStressSectionRuntime, SolidSectionRuntime
from pyfem.post import AveragingService, DerivedFieldService, RawFieldService, RecoveryService
from pyfem.post.common import FIELD_METADATA_KEY_SECTION_NODAL_SEMANTICS, FIELD_METADATA_KEY_SECTION_POINT_LABELS


class PostProcessingVerificationTests(unittest.TestCase):
    """??????????????????????"""

    def test_cps4_constant_strain_pipeline_matches_exact_solution(self) -> None:
        material = ElasticIsotropicRuntime(name="plane-mat", young_modulus=1200.0, poisson_ratio=0.25, density=1.0)
        section = PlaneStressSectionRuntime(name="plane-sec", material_runtime=material, thickness=1.0)
        element = CPS4Runtime(
            location=ElementLocation(scope_name="part-1", element_name="e1"),
            coordinates=((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
            node_names=("n1", "n2", "n3", "n4"),
            dof_indices=tuple(range(8)),
            section_runtime=section,
            material_runtime=material,
        )
        displacement = (0.0, 0.0, 1.0e-3, 0.0, 1.0e-3, 0.0, 0.0, 0.0)
        expected_stress = material.update((1.0e-3, 0.0, 0.0), mode="plane_stress").stress
        fields = self._build_post_fields(element_output={"part-1.e1": dict(element.output(displacement=displacement))})

        for target_value in fields[FIELD_KEY_S_IP].values.values():
            self.assertAlmostEqual(target_value["S11"], expected_stress[0], places=12)
            self.assertAlmostEqual(target_value["S22"], expected_stress[1], places=12)
            self.assertAlmostEqual(target_value["S12"], expected_stress[2], places=12)
        for target_value in fields[FIELD_KEY_S_REC].values.values():
            self.assertAlmostEqual(target_value["S11"], expected_stress[0], places=12)
        for target_value in fields[FIELD_KEY_S_AVG].values.values():
            self.assertAlmostEqual(target_value["S11"], expected_stress[0], places=12)
        self.assertAlmostEqual(
            fields[FIELD_KEY_S_VM_IP].values["part-1.e1.ip1"]["MISES"],
            self._von_mises_from_plane_stress(*expected_stress),
            places=12,
        )
        principal = fields[FIELD_KEY_S_PRINCIPAL_AVG].values["part-1.n1"]
        expected_principal = self._principal_from_plane_stress(*expected_stress)
        self.assertAlmostEqual(principal["P1"], expected_principal[0], places=12)
        self.assertAlmostEqual(principal["P2"], expected_principal[1], places=12)
        self.assertAlmostEqual(principal["P3"], expected_principal[2], places=12)

    def test_c3d8_uniform_extension_pipeline_matches_exact_solution(self) -> None:
        material = ElasticIsotropicRuntime(name="solid-mat", young_modulus=1000.0, poisson_ratio=0.25, density=1.0)
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
        displacement = (
            0.0, 0.0, 0.0,
            1.0e-3, 0.0, 0.0,
            1.0e-3, 0.0, 0.0,
            0.0, 0.0, 0.0,
            0.0, 0.0, 0.0,
            1.0e-3, 0.0, 0.0,
            1.0e-3, 0.0, 0.0,
            0.0, 0.0, 0.0,
        )
        expected_stress = material.update((1.0e-3, 0.0, 0.0, 0.0, 0.0, 0.0), mode="3d").stress
        fields = self._build_post_fields(element_output={"part-1.e1": dict(element.output(displacement=displacement))})

        self.assertEqual(fields[FIELD_KEY_S_IP].target_count, 8)
        self.assertEqual(fields[FIELD_KEY_S_REC].target_count, 8)
        self.assertEqual(fields[FIELD_KEY_S_AVG].target_count, 8)
        self.assertAlmostEqual(fields[FIELD_KEY_S_VM_REC].values["part-1.e1.n1"]["MISES"], self._von_mises_from_tensor(expected_stress), places=12)
        principal = fields[FIELD_KEY_S_PRINCIPAL_IP].values["part-1.e1.ip1"]
        expected_principal = tuple(sorted((expected_stress[0], expected_stress[1], expected_stress[2]), reverse=True))
        self.assertAlmostEqual(principal["P1"], expected_principal[0], places=12)
        self.assertAlmostEqual(principal["P2"], expected_principal[1], places=12)
        self.assertAlmostEqual(principal["P3"], expected_principal[2], places=12)

    def test_b21_reference_section_semantics_are_consistent(self) -> None:
        material = ElasticIsotropicRuntime(name="beam-mat", young_modulus=1.0e6, poisson_ratio=0.3, density=1.0)
        section = BeamSectionRuntime(name="beam-sec", material_runtime=material, area=0.03, moment_inertia_z=2.0e-4)
        element = B21Runtime(
            location=ElementLocation(scope_name="part-1", element_name="e1"),
            coordinates=((0.0, 0.0), (2.0, 0.0)),
            node_names=("n1", "n2"),
            dof_indices=tuple(range(6)),
            section_runtime=section,
            material_runtime=material,
        )
        displacement = (0.0, 0.0, 0.0, 2.0e-3, 0.0, 0.0)
        expected_stress = 1000.0
        fields = self._build_post_fields(element_output={"part-1.e1": dict(element.output(displacement=displacement))})

        self.assertEqual(fields[FIELD_KEY_S_IP].target_keys, ("part-1.e1.ip1.sp1", "part-1.e1.ip2.sp1"))
        self.assertEqual(fields[FIELD_KEY_S_REC].target_keys, ("part-1.e1.n1.sp1", "part-1.e1.n2.sp1"))
        self.assertEqual(fields[FIELD_KEY_S_AVG].target_keys, ("part-1.n1", "part-1.n2"))
        self.assertEqual(fields[FIELD_KEY_S_IP].metadata[FIELD_METADATA_KEY_SECTION_POINT_LABELS]["part-1.e1.ip1.sp1"], "sp1")
        self.assertEqual(fields[FIELD_KEY_S_REC].metadata[FIELD_METADATA_KEY_SECTION_NODAL_SEMANTICS]["part-1.e1.n1.sp1"], "reference_section")
        self.assertAlmostEqual(fields[FIELD_KEY_S_VM_AVG].values["part-1.n1"]["MISES"], expected_stress, places=12)
        principal = fields[FIELD_KEY_S_PRINCIPAL_AVG].values["part-1.n1"]
        self.assertAlmostEqual(principal["P1"], expected_stress, places=12)
        self.assertAlmostEqual(principal["P2"], 0.0, places=12)
        self.assertAlmostEqual(principal["P3"], 0.0, places=12)

    def _build_post_fields(self, *, element_output: dict[str, dict[str, object]]) -> dict[str, object]:
        raw_fields = RawFieldService().build_fields(element_output)
        recovered_fields = RecoveryService().build_fields(element_output)
        averaged_fields = AveragingService().build_fields(next(field for field in recovered_fields if field.name == FIELD_KEY_S_REC))
        field_registry = {field.name: field for field in (*raw_fields, *recovered_fields, *averaged_fields)}
        for field in DerivedFieldService().build_fields(field_registry):
            field_registry[field.name] = field
        return field_registry

    def _von_mises_from_plane_stress(self, s11: float, s22: float, s12: float) -> float:
        return float(numpy.sqrt(s11**2 - s11 * s22 + s22**2 + 3.0 * s12**2))

    def _principal_from_plane_stress(self, s11: float, s22: float, s12: float) -> tuple[float, float, float]:
        center = 0.5 * (s11 + s22)
        radius = float(numpy.sqrt((0.5 * (s11 - s22)) ** 2 + s12**2))
        return (center + radius, center - radius, 0.0)

    def _von_mises_from_tensor(self, stress: tuple[float, float, float, float, float, float]) -> float:
        s11, s22, s33, s12, s23, s13 = stress
        return float(
            numpy.sqrt(
                0.5 * ((s11 - s22) ** 2 + (s22 - s33) ** 2 + (s33 - s11) ** 2)
                + 3.0 * (s12**2 + s23**2 + s13**2)
            )
        )


if __name__ == "__main__":
    unittest.main()
