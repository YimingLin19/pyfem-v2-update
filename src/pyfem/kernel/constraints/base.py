"""约束运行时抽象。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class ConstrainedDof:
    """描述一个被约束的自由度及目标值。"""

    dof_index: int
    value: float = 0.0


class ConstraintRuntime(ABC):
    """定义约束运行时对象的正式接口。"""

    @abstractmethod
    def get_name(self) -> str:
        """返回约束运行时名称。"""

    @abstractmethod
    def get_constraint_type(self) -> str:
        """返回约束运行时类型。"""

    @abstractmethod
    def collect_constrained_dofs(self) -> tuple[ConstrainedDof, ...]:
        """返回该约束涉及的自由度集合。"""

    @abstractmethod
    def describe(self) -> Mapping[str, Any]:
        """返回约束运行时的可序列化描述。"""
