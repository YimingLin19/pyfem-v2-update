"""材料运行时抽象。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pyfem.foundation.types import Matrix, StateMap, Vector


@dataclass(slots=True, frozen=True)
class MaterialUpdateResult:
    """描述材料更新后的应力、切线与状态。"""

    stress: Vector
    tangent: Matrix
    state: dict[str, Any]
    strain: Vector = ()
    strain_measure: str = "unspecified"
    stress_measure: str = "unspecified"
    tangent_measure: str = "unspecified"


MaterialResponse = MaterialUpdateResult


class MaterialRuntime(ABC):
    """定义材料运行时对象的正式接口。"""

    @abstractmethod
    def get_name(self) -> str:
        """返回材料运行时名称。"""

    @abstractmethod
    def get_material_type(self) -> str:
        """返回材料运行时类型。"""

    @abstractmethod
    def allocate_state(self) -> dict[str, Any]:
        """分配材料点级状态容器。"""

    @abstractmethod
    def update(self, strain: Vector, state: StateMap | None = None, mode: str = "3d") -> MaterialUpdateResult:
        """根据指定测度的应变状态更新应力、切线与内部状态。"""

    @abstractmethod
    def get_density(self) -> float:
        """返回材料密度。"""

    @abstractmethod
    def describe(self) -> Mapping[str, Any]:
        """返回材料运行时的可序列化描述。"""
