"""编译后的运行时模型对象。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pyfem.foundation.errors import CompilationError
from pyfem.kernel import DofManager
from pyfem.kernel.constraints import ConstraintRuntime
from pyfem.kernel.elements import ElementRuntime
from pyfem.kernel.interactions import InteractionRuntime
from pyfem.kernel.materials import MaterialRuntime
from pyfem.kernel.sections import SectionRuntime
from pyfem.modeldb import ModelDB
from pyfem.procedures.base import ProcedureRuntime

if TYPE_CHECKING:
    from pyfem.solver.state import RuntimeState


@dataclass(slots=True)
class CompiledModel:
    """保存编译完成后的运行时对象图。"""

    model: ModelDB
    dof_manager: DofManager
    element_runtimes: dict[str, ElementRuntime] = field(default_factory=dict)
    material_runtimes: dict[str, MaterialRuntime] = field(default_factory=dict)
    section_runtimes: dict[str, SectionRuntime] = field(default_factory=dict)
    constraint_runtimes: dict[str, ConstraintRuntime] = field(default_factory=dict)
    interaction_runtimes: dict[str, InteractionRuntime] = field(default_factory=dict)
    step_runtimes: dict[str, ProcedureRuntime] = field(default_factory=dict)
    step_state_snapshots: dict[tuple[str, str], Any] = field(default_factory=dict, repr=False)

    @property
    def model_name(self) -> str:
        """返回编译模型名称。"""

        return self.model.name

    @property
    def source_model(self) -> ModelDB:
        """返回兼容旧接口的原始模型对象。"""

        return self.model

    @property
    def procedure_runtimes(self) -> dict[str, ProcedureRuntime]:
        """返回分析程序运行时字典。"""

        return self.step_runtimes

    def get_element_runtime(self, qualified_name: str) -> ElementRuntime:
        """按限定名称获取单元运行时对象。"""

        try:
            return self.element_runtimes[qualified_name]
        except KeyError as error:
            raise CompilationError(f"编译模型中不存在单元运行时 {qualified_name}。") from error

    def get_step_runtime(self, step_name: str) -> ProcedureRuntime:
        """按名称获取分析步骤运行时对象。"""

        try:
            return self.step_runtimes[step_name]
        except KeyError as error:
            raise CompilationError(f"编译模型中不存在分析步骤 {step_name}。") from error

    def get_procedure(self, step_name: str) -> ProcedureRuntime:
        """返回兼容旧接口的分析步骤运行时对象。"""

        return self.get_step_runtime(step_name)

    def publish_step_state(self, step_name: str, channel: str, state: RuntimeState) -> None:
        """发布一个步骤执行后可供后续步骤继承的 committed 状态。"""

        self.step_state_snapshots[(channel, step_name)] = state

    def resolve_inherited_step_state(self, step_name: str, channel: str) -> RuntimeState | None:
        """解析当前步骤可继承的最近一步 committed 状态。"""

        ordered_steps = tuple(self.iter_step_names())
        try:
            current_index = ordered_steps.index(step_name)
        except ValueError as error:
            raise CompilationError(f"编译模型中不存在分析步骤 {step_name}。") from error

        for previous_step_name in reversed(ordered_steps[:current_index]):
            inherited_state = self.step_state_snapshots.get((channel, previous_step_name))
            if inherited_state is not None:
                return inherited_state
        return None

    def iter_step_names(self) -> Iterable[str]:
        """返回编译模型中的正式步骤顺序。"""

        if self.model.job is not None and self.model.job.step_names:
            return self.model.job.step_names
        return tuple(self.step_runtimes.keys())
