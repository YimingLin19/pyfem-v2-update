"""梁截面运行时。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pyfem.kernel.materials import MaterialRuntime
from pyfem.kernel.sections.base import SectionRuntime


@dataclass(slots=True)
class BeamSectionRuntime(SectionRuntime):
    """定义二维梁截面运行时。"""

    name: str
    material_runtime: MaterialRuntime
    area: float
    moment_inertia_z: float
    shear_factor: float = 1.0
    parameters: dict[str, Any] = field(default_factory=dict)

    def get_name(self) -> str:
        """返回截面运行时名称。"""

        return self.name

    def get_section_type(self) -> str:
        """返回截面运行时类型。"""

        return "beam"

    def get_material_runtime(self) -> MaterialRuntime:
        """返回绑定的材料运行时。"""

        return self.material_runtime

    def get_area(self) -> float:
        """返回梁截面积。"""

        return self.area

    def get_moment_inertia_z(self) -> float:
        """返回绕局部 z 轴的截面惯性矩。"""

        return self.moment_inertia_z

    def describe(self) -> Mapping[str, Any]:
        """返回截面运行时的可序列化描述。"""

        return {
            "name": self.name,
            "section_type": self.get_section_type(),
            "material_name": self.material_runtime.get_name(),
            "area": self.area,
            "moment_inertia_z": self.moment_inertia_z,
            "shear_factor": self.shear_factor,
            "parameters": dict(self.parameters),
        }
