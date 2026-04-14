"""单元运行时抽象。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pyfem.foundation.types import ElementLocation, Matrix, StateMap, Vector


@dataclass(slots=True, frozen=True)
class ElementContribution:
    """描述单元局部切线矩阵与残量向量。"""

    stiffness: Matrix
    residual: Vector


class ElementRuntime(ABC):
    """定义单元运行时对象的正式接口。"""

    @abstractmethod
    def get_type_key(self) -> str:
        """返回单元运行时类型键。"""

    @abstractmethod
    def get_dof_layout(self) -> tuple[str, ...]:
        """返回单元节点自由度布局。"""

    @abstractmethod
    def get_location(self) -> ElementLocation:
        """返回单元在编译作用域中的位置。"""

    @abstractmethod
    def get_dof_indices(self) -> tuple[int, ...]:
        """返回单元关联的全局自由度编号。"""

    @abstractmethod
    def allocate_state(self) -> dict[str, Any]:
        """分配单元级状态容器。"""

    @abstractmethod
    def compute_tangent_and_residual(
        self,
        displacement: Vector | None = None,
        state: StateMap | None = None,
    ) -> ElementContribution:
        """计算单元切线矩阵与残量向量。"""

    @abstractmethod
    def compute_mass(self, state: StateMap | None = None) -> Matrix:
        """计算单元质量矩阵。"""

    @abstractmethod
    def compute_damping(self, state: StateMap | None = None) -> Matrix | None:
        """计算单元阻尼矩阵，若当前未实现则返回空值。"""

    @abstractmethod
    def collect_output(
        self,
        displacement: Vector | None = None,
        state: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """收集单元输出字段。"""

    def get_supported_geometric_nonlinearity_modes(self) -> tuple[str, ...]:
        """返回当前单元支持的几何非线性模式。"""

        return ()

    def compute_surface_load(
        self,
        local_face: str,
        load_type: str,
        components: Mapping[str, float],
        state: StateMap | None = None,
    ) -> Vector:
        """计算单元局部表面分布载荷等效节点力。"""

        del local_face, load_type, components, state
        raise NotImplementedError(f"单元类型 {self.get_type_key()} 尚未实现表面分布载荷。")

    def tangent_residual(
        self,
        displacement: Vector | None = None,
        state: StateMap | None = None,
    ) -> ElementContribution:
        """返回兼容任务术语的切线矩阵与残量向量。"""

        return self.compute_tangent_and_residual(displacement=displacement, state=state)

    def mass(self, state: StateMap | None = None) -> Matrix:
        """返回兼容任务术语的质量矩阵。"""

        return self.compute_mass(state=state)

    def damping(self, state: StateMap | None = None) -> Matrix | None:
        """返回兼容任务术语的阻尼矩阵。"""

        return self.compute_damping(state=state)

    def output(
        self,
        displacement: Vector | None = None,
        state: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """返回兼容任务术语的单元输出。"""

        return self.collect_output(displacement=displacement, state=state)

    def surface_load(
        self,
        local_face: str,
        load_type: str,
        components: Mapping[str, float],
        state: StateMap | None = None,
    ) -> Vector:
        """返回兼容任务术语的表面分布载荷等效节点力。"""

        return self.compute_surface_load(local_face=local_face, load_type=load_type, components=components, state=state)
