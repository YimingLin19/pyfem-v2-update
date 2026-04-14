"""静力非线性 procedure 的辅助对象。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pyfem.foundation.errors import SolverError


@dataclass(slots=True, frozen=True)
class StaticNonlinearParameters:
    """定义静力非线性步骤的统一参数。"""

    max_increments: int
    initial_increment: float
    min_increment: float
    max_iterations: int
    residual_tolerance: float
    displacement_tolerance: float
    allow_cutback: bool
    line_search: bool
    nlgeom: bool

    @classmethod
    def from_step_parameters(cls, parameters: Mapping[str, Any]) -> StaticNonlinearParameters:
        """从 ``StepDef.parameters`` 解析静力非线性参数。"""

        resolved = cls(
            max_increments=int(parameters.get("max_increments", 1)),
            initial_increment=float(parameters.get("initial_increment", 1.0)),
            min_increment=float(parameters.get("min_increment", 1.0e-3)),
            max_iterations=int(parameters.get("max_iterations", 8)),
            residual_tolerance=float(parameters.get("residual_tolerance", 1.0e-8)),
            displacement_tolerance=float(parameters.get("displacement_tolerance", 1.0e-8)),
            allow_cutback=_coerce_bool(parameters.get("allow_cutback", True), parameter_name="allow_cutback"),
            line_search=_coerce_bool(parameters.get("line_search", False), parameter_name="line_search"),
            nlgeom=_coerce_bool(parameters.get("nlgeom", False), parameter_name="nlgeom"),
        )
        resolved.validate()
        return resolved

    def validate(self) -> None:
        """校验参数组合是否合法。"""

        if self.max_increments <= 0:
            raise SolverError("静力非线性参数 max_increments 必须为正整数。")
        if self.initial_increment <= 0.0 or self.initial_increment > 1.0:
            raise SolverError("静力非线性参数 initial_increment 必须位于 (0, 1]。")
        if self.min_increment <= 0.0 or self.min_increment > self.initial_increment:
            raise SolverError("静力非线性参数 min_increment 必须位于 (0, initial_increment]。")
        if self.max_iterations <= 0:
            raise SolverError("静力非线性参数 max_iterations 必须为正整数。")
        if self.residual_tolerance < 0.0:
            raise SolverError("静力非线性参数 residual_tolerance 不能为负数。")
        if self.displacement_tolerance < 0.0:
            raise SolverError("静力非线性参数 displacement_tolerance 不能为负数。")


@dataclass(slots=True, frozen=True)
class NonlinearIterationMetrics:
    """描述一次 Newton 迭代后的收敛指标。"""

    residual_norm: float
    displacement_increment_norm: float
    displacement_norm: float


@dataclass(slots=True, frozen=True)
class NonlinearIncrementResult:
    """描述一个收敛增量的返回结果。"""

    metrics: NonlinearIterationMetrics
    iteration_count: int


class LineSearchController:
    """管理 line search 开关及其占位实现。"""

    def __init__(self, enabled: bool) -> None:
        """使用步骤参数初始化 line search 控制器。"""

        self._enabled = bool(enabled)

    @property
    def enabled(self) -> bool:
        """返回当前是否启用 line search。"""

        return self._enabled

    def describe(self) -> str:
        """返回当前 line search 模式描述。"""

        return "unit_step_placeholder" if self._enabled else "disabled"

    def select_step_length(self) -> float:
        """返回本轮更新使用的步长。"""

        return 1.0


def _coerce_bool(value: Any, *, parameter_name: str) -> bool:
    """将步骤参数安全转换为布尔值。"""

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise SolverError(f"静力非线性参数 {parameter_name} 必须为布尔值。")
