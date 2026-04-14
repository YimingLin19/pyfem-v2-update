"""C3D8 nlgeom 解析切线质量回归测试。"""

from __future__ import annotations

import unittest

import numpy

from pyfem.foundation.types import ElementLocation
from pyfem.kernel.elements import C3D8Runtime
from pyfem.kernel.materials import ElasticIsotropicRuntime
from pyfem.kernel.sections import SolidSectionRuntime


class C3D8NlgeomTangentQualityTests(unittest.TestCase):
    """验证 C3D8 total_lagrangian 切线与内力表达一致。"""

    def test_total_lagrangian_analytic_tangent_matches_numerical_helper(self) -> None:
        material = ElasticIsotropicRuntime(name="mat-1", young_modulus=1000.0, poisson_ratio=0.25, density=1.0)
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
                0.08,
                0.01,
                -0.02,
                0.07,
                -0.03,
                0.02,
                0.0,
                -0.02,
                0.01,
                0.0,
                0.01,
                -0.01,
                0.09,
                0.02,
                0.0,
                0.1,
                -0.01,
                0.03,
                0.0,
                -0.03,
                0.02,
            ),
            dtype=float,
        )
        state = {
            "analysis_flags": {"nlgeom": True},
            "integration_points": {},
            "time": 1.0,
            "displacement": tuple(displacement.tolist()),
        }

        analytic_tangent = numpy.asarray(
            element.tangent_residual(displacement=tuple(displacement.tolist()), state=state).stiffness,
            dtype=float,
        )
        numerical_tangent = element._build_total_lagrangian_numerical_tangent(displacement, state=state)
        difference_norm = float(numpy.linalg.norm(analytic_tangent - numerical_tangent))
        reference_norm = float(numpy.linalg.norm(numerical_tangent))

        self.assertGreater(reference_norm, 0.0)
        self.assertLess(difference_norm / reference_norm, 1.0e-8)


if __name__ == "__main__":
    unittest.main()
