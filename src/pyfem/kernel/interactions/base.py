"""相互作用运行时抽象。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any


class InteractionRuntime(ABC):
    """定义相互作用运行时对象的正式接口。"""

    @abstractmethod
    def get_name(self) -> str:
        """返回相互作用运行时名称。"""

    @abstractmethod
    def get_interaction_type(self) -> str:
        """返回相互作用运行时类型。"""

    @abstractmethod
    def describe(self) -> Mapping[str, Any]:
        """返回相互作用运行时的可序列化描述。"""
