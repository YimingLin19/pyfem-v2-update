"""空操作相互作用运行时。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pyfem.kernel.interactions.base import InteractionRuntime


@dataclass(slots=True)
class NoOpInteractionRuntime(InteractionRuntime):
    """定义最小 no-op 相互作用运行时。"""

    name: str
    interaction_type: str
    scope_name: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)

    def get_name(self) -> str:
        """返回相互作用运行时名称。"""

        return self.name

    def get_interaction_type(self) -> str:
        """返回相互作用运行时类型。"""

        return self.interaction_type

    def describe(self) -> Mapping[str, Any]:
        """返回相互作用运行时的可序列化描述。"""

        return {
            "name": self.name,
            "interaction_type": self.interaction_type,
            "scope_name": self.scope_name,
            "parameters": dict(self.parameters),
        }
