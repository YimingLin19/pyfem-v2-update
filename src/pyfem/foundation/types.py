"""基础位置类型与数值别名。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias

Scalar: TypeAlias = float
Vector: TypeAlias = tuple[Scalar, ...]
Matrix: TypeAlias = tuple[tuple[Scalar, ...], ...]
StateMap: TypeAlias = Mapping[str, Any]


def _validate_non_empty_text(value: str | None, label: str) -> str:
    """校验文本字段非空。"""

    if value is None or not value.strip():
        raise ValueError(f"{label} 不能为空。")
    return value


@dataclass(slots=True, frozen=True)
class NodeLocation:
    """描述一个节点在编译作用域中的唯一位置。"""

    scope_name: str
    node_name: str

    @property
    def qualified_name(self) -> str:
        return f"{self.scope_name}.{self.node_name}"


@dataclass(slots=True, frozen=True)
class ElementLocation:
    """描述一个单元在编译作用域中的唯一位置。"""

    scope_name: str
    element_name: str

    @property
    def qualified_name(self) -> str:
        return f"{self.scope_name}.{self.element_name}"


@dataclass(slots=True, frozen=True)
class DofLocation:
    """描述一个自由度在编译作用域中的唯一位置。"""

    scope_name: str
    node_name: str | None
    dof_name: str
    owner_kind: str = "node"
    owner_name: str | None = None

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.scope_name, "scope_name")
        _validate_non_empty_text(self.dof_name, "dof_name")
        owner_kind = _validate_non_empty_text(self.owner_kind, "owner_kind")

        if owner_kind == "node":
            node_name = _validate_non_empty_text(self.node_name, "节点自由度的 node_name")
            if self.owner_name is None:
                object.__setattr__(self, "owner_name", node_name)
                return

            owner_name = _validate_non_empty_text(self.owner_name, "节点自由度的 owner_name")
            if owner_name != node_name:
                raise ValueError("节点自由度的 owner_name 必须与 node_name 一致。")
            return

        owner_name = _validate_non_empty_text(self.owner_name, f"{owner_kind} 自由度的 owner_name")
        if self.node_name is not None and self.node_name != owner_name:
            raise ValueError("非节点自由度不应混用 node_name 与 owner_name。")
        object.__setattr__(self, "node_name", None)

    @classmethod
    def node(cls, scope_name: str, node_name: str, dof_name: str) -> DofLocation:
        """构造节点自由度位置。"""

        return cls(scope_name=scope_name, node_name=node_name, dof_name=dof_name, owner_kind="node", owner_name=node_name)

    @classmethod
    def auxiliary(cls, scope_name: str, owner_name: str, dof_name: str) -> DofLocation:
        """构造辅助自由度位置。"""

        return cls(scope_name=scope_name, node_name=None, dof_name=dof_name, owner_kind="auxiliary", owner_name=owner_name)

    @property
    def qualified_name(self) -> str:
        if self.owner_kind == "node" and self.node_name is not None:
            return f"{self.scope_name}.{self.node_name}.{self.dof_name}"
        return f"{self.scope_name}.{self.owner_kind}:{self.owner_name}.{self.dof_name}"

    def get_result_key(self) -> str | None:
        """返回结果系统可识别的拥有者键。"""

        if self.owner_kind != "node" or self.node_name is None:
            return None
        return f"{self.scope_name}.{self.node_name}"
