"""各向同性线弹性材料运行时。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy

from pyfem.foundation.types import Matrix, StateMap, Vector
from pyfem.kernel.materials.base import MaterialRuntime, MaterialUpdateResult


def _as_matrix(values: numpy.ndarray) -> Matrix:
    """将数组转换为矩阵元组。"""

    return tuple(tuple(float(item) for item in row) for row in values.tolist())


def _as_vector(values: numpy.ndarray) -> Vector:
    """将数组转换为向量元组。"""

    return tuple(float(item) for item in values.tolist())


@dataclass(slots=True)
class ElasticIsotropicRuntime(MaterialRuntime):
    """定义各向同性线弹性材料运行时。"""

    name: str
    young_modulus: float
    poisson_ratio: float
    density: float = 0.0

    def get_name(self) -> str:
        """返回材料运行时名称。"""

        return self.name

    def get_material_type(self) -> str:
        """返回材料运行时类型。"""

        return "linear_elastic"

    def allocate_state(self) -> dict[str, Any]:
        """分配线弹性材料的状态容器。"""

        return {
            "strain": (),
            "stress": (),
            "mode": None,
            "strain_measure": "unspecified",
            "stress_measure": "unspecified",
            "tangent_measure": "unspecified",
        }

    def update(self, strain: Vector, state: StateMap | None = None, mode: str = "3d") -> MaterialUpdateResult:
        """根据应变状态返回线弹性应力与切线。"""

        strain_array = numpy.asarray(strain, dtype=float)
        tangent = self._build_tangent(mode=mode)
        stress = tangent @ strain_array
        strain_measure, stress_measure, tangent_measure = self._resolve_measure_contract(mode)
        next_state = dict(state) if state is not None else self.allocate_state()
        next_state["strain"] = _as_vector(strain_array)
        next_state["stress"] = _as_vector(stress)
        next_state["mode"] = mode
        next_state["strain_measure"] = strain_measure
        next_state["stress_measure"] = stress_measure
        next_state["tangent_measure"] = tangent_measure
        return MaterialUpdateResult(
            stress=_as_vector(stress),
            tangent=_as_matrix(tangent),
            state=next_state,
            strain=_as_vector(strain_array),
            strain_measure=strain_measure,
            stress_measure=stress_measure,
            tangent_measure=tangent_measure,
        )

    def get_density(self) -> float:
        """返回材料密度。"""

        return self.density

    def get_young_modulus(self) -> float:
        """返回弹性模量。"""

        return self.young_modulus

    def get_poisson_ratio(self) -> float:
        """返回泊松比。"""

        return self.poisson_ratio

    def describe(self) -> Mapping[str, Any]:
        """返回材料运行时的可序列化描述。"""

        return {
            "name": self.name,
            "material_type": self.get_material_type(),
            "young_modulus": self.young_modulus,
            "poisson_ratio": self.poisson_ratio,
            "density": self.density,
        }

    def _build_tangent(self, mode: str) -> numpy.ndarray:
        if mode in {"3d", "solid"}:
            return self._build_solid_tangent()
        if mode in {"3d_total_lagrangian", "solid_total_lagrangian"}:
            return self._build_solid_tangent()
        if mode == "plane_stress":
            return self._build_plane_stress_tangent()
        if mode == "plane_stress_total_lagrangian":
            return self._build_plane_stress_tangent()
        if mode == "plane_strain":
            return self._build_plane_strain_tangent()
        if mode == "plane_strain_total_lagrangian":
            return self._build_plane_strain_tangent()
        if mode in {"uniaxial", "beam_axial"}:
            return numpy.asarray(((self.young_modulus,),), dtype=float)
        raise ValueError(f"不支持的材料更新模式: {mode}")

    def _resolve_measure_contract(self, mode: str) -> tuple[str, str, str]:
        if mode in {"3d_total_lagrangian", "solid_total_lagrangian", "plane_strain_total_lagrangian", "plane_stress_total_lagrangian"}:
            return (
                "green_lagrange",
                "second_piola_kirchhoff",
                "d_second_piola_kirchhoff_d_green_lagrange",
            )
        return (
            "small_strain",
            "cauchy_small_strain",
            "d_cauchy_small_strain_d_small_strain",
        )

    def _build_solid_tangent(self) -> numpy.ndarray:
        lam = self.young_modulus * self.poisson_ratio / (
            (1.0 + self.poisson_ratio) * (1.0 - 2.0 * self.poisson_ratio)
        )
        mu = self.young_modulus / (2.0 * (1.0 + self.poisson_ratio))
        tangent = numpy.zeros((6, 6), dtype=float)
        tangent[0:3, 0:3] = lam
        tangent[0, 0] += 2.0 * mu
        tangent[1, 1] += 2.0 * mu
        tangent[2, 2] += 2.0 * mu
        tangent[3, 3] = mu
        tangent[4, 4] = mu
        tangent[5, 5] = mu
        return tangent

    def _build_plane_stress_tangent(self) -> numpy.ndarray:
        factor = self.young_modulus / (1.0 - self.poisson_ratio**2)
        return factor * numpy.asarray(
            (
                (1.0, self.poisson_ratio, 0.0),
                (self.poisson_ratio, 1.0, 0.0),
                (0.0, 0.0, (1.0 - self.poisson_ratio) / 2.0),
            ),
            dtype=float,
        )

    def _build_plane_strain_tangent(self) -> numpy.ndarray:
        factor = self.young_modulus / ((1.0 + self.poisson_ratio) * (1.0 - 2.0 * self.poisson_ratio))
        return factor * numpy.asarray(
            (
                (1.0 - self.poisson_ratio, self.poisson_ratio, 0.0),
                (self.poisson_ratio, 1.0 - self.poisson_ratio, 0.0),
                (0.0, 0.0, (1.0 - 2.0 * self.poisson_ratio) / 2.0),
            ),
            dtype=float,
        )
