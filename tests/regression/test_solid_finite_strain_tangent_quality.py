"""solid finite-strain J2 切线质量回归测试。"""

from __future__ import annotations

import unittest

import numpy

from pyfem.foundation.types import ElementLocation
from pyfem.kernel.elements import C3D8Runtime, CPS4Runtime
from pyfem.kernel.materials import J2PlasticityRuntime
from pyfem.kernel.sections import PlaneStrainSectionRuntime, SolidSectionRuntime


class SolidFiniteStrainJ2TangentQualityTests(unittest.TestCase):
    """验证 finite-strain J2 解析切线与数值差分切线的一致性。"""

    def test_cps4_finite_strain_j2_analytic_tangent_matches_numerical_helper(self) -> None:
        material = J2PlasticityRuntime(
            name="mat-j2",
            young_modulus=200000.0,
            poisson_ratio=0.3,
            yield_stress=250.0,
            hardening_modulus=1000.0,
        )
        section = PlaneStrainSectionRuntime(name="sec-1", material_runtime=material, thickness=1.0)
        element = CPS4Runtime(
            location=ElementLocation(scope_name="part-1", element_name="plate-1"),
            coordinates=((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
            node_names=("n1", "n2", "n3", "n4"),
            dof_indices=tuple(range(8)),
            section_runtime=section,
            material_runtime=material,
        )
        displacement = numpy.asarray((0.0, 0.0, 0.0045, 0.0004, 0.0040, -0.0002, 0.0, -0.0001), dtype=float)
        preload_displacement = numpy.asarray((0.0, 0.0, 0.0038, 0.0003, 0.0035, -0.0002, 0.0, -0.0001), dtype=float)
        state = {
            "analysis_flags": {"nlgeom": True},
            "integration_points": {},
            "time": 0.0,
            "displacement": tuple(preload_displacement.tolist()),
        }
        element.tangent_residual(displacement=tuple(preload_displacement.tolist()), state=state)
        state["time"] = 1.0
        state["displacement"] = tuple(displacement.tolist())

        analytic_tangent = numpy.asarray(
            element.tangent_residual(displacement=tuple(displacement.tolist()), state=state).stiffness,
            dtype=float,
        )
        numerical_tangent = element._build_total_lagrangian_numerical_tangent(displacement, state=state, relative_step=1.0e-7)
        difference_norm = float(numpy.linalg.norm(analytic_tangent - numerical_tangent))
        reference_norm = float(numpy.linalg.norm(numerical_tangent))

        self.assertGreater(reference_norm, 0.0)
        self.assertLess(difference_norm / reference_norm, 1.0e-6)

    def test_c3d8_finite_strain_j2_analytic_tangent_matches_numerical_helper(self) -> None:
        material = J2PlasticityRuntime(
            name="mat-j2",
            young_modulus=200000.0,
            poisson_ratio=0.3,
            yield_stress=250.0,
            hardening_modulus=1000.0,
        )
        section = SolidSectionRuntime(name="sec-1", material_runtime=material)
        element = C3D8Runtime(
            location=ElementLocation(scope_name="part-1", element_name="block-1"),
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
        displacement = numpy.asarray(
            (
                0.0,
                0.0,
                0.0,
                0.0045,
                0.0003,
                -0.0002,
                0.0042,
                -0.0002,
                0.0001,
                0.0,
                -0.0001,
                0.0001,
                0.0,
                0.0002,
                -0.0001,
                0.0048,
                0.0003,
                0.0,
                0.0046,
                -0.0001,
                0.0002,
                0.0,
                -0.0002,
                0.0001,
            ),
            dtype=float,
        )
        preload_displacement = numpy.asarray(
            (
                0.0,
                0.0,
                0.0,
                0.0038,
                0.0002,
                -0.0002,
                0.0036,
                -0.0002,
                0.0001,
                0.0,
                -0.0001,
                0.0001,
                0.0,
                0.0002,
                -0.0001,
                0.0040,
                0.0003,
                0.0,
                0.0039,
                -0.0001,
                0.0002,
                0.0,
                -0.0002,
                0.0001,
            ),
            dtype=float,
        )
        state = {
            "analysis_flags": {"nlgeom": True},
            "integration_points": {},
            "time": 0.0,
            "displacement": tuple(preload_displacement.tolist()),
        }
        element.tangent_residual(displacement=tuple(preload_displacement.tolist()), state=state)
        state["time"] = 1.0
        state["displacement"] = tuple(displacement.tolist())

        analytic_tangent = numpy.asarray(
            element.tangent_residual(displacement=tuple(displacement.tolist()), state=state).stiffness,
            dtype=float,
        )
        numerical_tangent = element._build_total_lagrangian_numerical_tangent(displacement, state=state, relative_step=1.0e-7)
        difference_norm = float(numpy.linalg.norm(analytic_tangent - numerical_tangent))
        reference_norm = float(numpy.linalg.norm(numerical_tangent))

        self.assertGreater(reference_norm, 0.0)
        self.assertLess(difference_norm / reference_norm, 1.0e-6)


if __name__ == "__main__":
    unittest.main()
