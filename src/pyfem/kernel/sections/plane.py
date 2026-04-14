"""平面截面运行时。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pyfem.kernel.materials import MaterialRuntime
from pyfem.kernel.sections.base import SectionRuntime


@dataclass(slots=True)
class _BasePlaneSectionRuntime(SectionRuntime):
    """定义平面类截面的共享行为。"""

    name: str
    material_runtime: MaterialRuntime
    thickness: float = 1.0
    parameters: dict[str, Any] = field(default_factory=dict)

    def get_name(self) -> str:
        """返回截面运行时名称。"""

        return self.name

    def get_material_runtime(self) -> MaterialRuntime:
        """返回绑定的材料运行时。"""

        return self.material_runtime

    def get_thickness(self) -> float:
        """返回平面截面厚度。"""

        return self.thickness

    def describe(self) -> Mapping[str, Any]:
        """返回截面运行时的可序列化描述。"""

        return {
            "name": self.name,
            "section_type": self.get_section_type(),
            "material_name": self.material_runtime.get_name(),
            "thickness": self.thickness,
            "parameters": dict(self.parameters),
        }


@dataclass(slots=True)
class PlaneStressSectionRuntime(_BasePlaneSectionRuntime):
    """定义平面应力截面运行时。"""

    def get_section_type(self) -> str:
        """返回截面运行时类型。"""

        return "plane_stress"


@dataclass(slots=True)
class PlaneStrainSectionRuntime(_BasePlaneSectionRuntime):
    """定义平面应变截面运行时。"""

    def get_section_type(self) -> str:
        """返回截面运行时类型。"""

        return "plane_strain"
