"""位移约束运行时。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pyfem.kernel.constraints.base import ConstrainedDof, ConstraintRuntime


@dataclass(slots=True)
class DisplacementConstraintRuntime(ConstraintRuntime):
    """定义位移边界条件运行时。"""

    name: str
    boundary_type: str
    target_name: str
    target_type: str
    scope_name: str | None = None
    constrained_dofs: tuple[ConstrainedDof, ...] = ()
    dof_values: dict[str, float] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)

    def get_name(self) -> str:
        """返回约束运行时名称。"""

        return self.name

    def get_constraint_type(self) -> str:
        """返回约束运行时类型。"""

        return self.boundary_type

    def collect_constrained_dofs(self) -> tuple[ConstrainedDof, ...]:
        """返回该约束涉及的自由度集合。"""

        return self.constrained_dofs

    def describe(self) -> Mapping[str, Any]:
        """返回约束运行时的可序列化描述。"""

        return {
            "name": self.name,
            "boundary_type": self.boundary_type,
            "target_name": self.target_name,
            "target_type": self.target_type,
            "scope_name": self.scope_name,
            "constrained_dof_count": len(self.constrained_dofs),
            "dof_values": dict(self.dof_values),
            "parameters": dict(self.parameters),
        }
