"""分析程序运行时抽象。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pyfem.io.results import ResultsWriter


@dataclass(slots=True, frozen=True)
class ProcedureReport:
    """描述一次分析程序执行后的基础统计信息。"""

    procedure_name: str
    frame_count: int
    history_count: int


class ProcedureRuntime(ABC):
    """定义分析程序运行时对象的正式接口。"""

    @abstractmethod
    def get_name(self) -> str:
        """返回分析程序运行时名称。"""

    @abstractmethod
    def get_procedure_type(self) -> str:
        """返回分析程序运行时类型。"""

    @abstractmethod
    def describe(self) -> Mapping[str, Any]:
        """返回分析程序运行时的可序列化描述。"""

    @abstractmethod
    def run(self, results_writer: ResultsWriter) -> ProcedureReport:
        """执行分析程序并写出正式结果。"""
