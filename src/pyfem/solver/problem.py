"""离散问题对象。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy

from pyfem.compiler.compiled_model import CompiledModel
from pyfem.solver.assembler import Assembler, ReducedSystem
from pyfem.solver.state import RuntimeState, StateManager


@dataclass(slots=True)
class DiscreteProblem:
    """封装结构离散系统的装配与状态管理。"""

    _compiled_model: CompiledModel
    _assembler: Assembler
    _state_manager: StateManager

    def __init__(self, compiled_model: CompiledModel, assembler: Assembler | None = None) -> None:
        """使用编译模型初始化离散问题。"""

        self._compiled_model = compiled_model
        self._assembler = assembler if assembler is not None else Assembler(compiled_model)
        self._state_manager = StateManager(compiled_model)

    @property
    def compiled_model(self) -> CompiledModel:
        """返回当前关联的编译模型。"""

        return self._compiled_model

    @property
    def state_manager(self) -> StateManager:
        """返回运行时状态管理器。"""

        return self._state_manager

    def create_zero_state(self, time: float = 0.0) -> RuntimeState:
        """创建一个带正式局部状态容器的零初始状态。"""

        return self._state_manager.allocate_runtime_state(time=time)

    def begin_trial(self, state: RuntimeState | None = None) -> RuntimeState:
        """以给定状态或当前提交状态开启试算。"""

        return self._state_manager.begin_trial(state)

    def get_committed_state(self) -> RuntimeState:
        """返回当前已提交状态的副本。"""

        return self._state_manager.get_committed_state()

    def get_trial_state(self) -> RuntimeState:
        """返回当前试算状态的副本。"""

        return self._state_manager.get_trial_state()

    def set_trial_state(self, state: RuntimeState) -> None:
        """写入新的试算状态。"""

        self._state_manager.set_trial_state(state)

    def assemble_tangent(
        self,
        displacement: numpy.ndarray | None = None,
        state: RuntimeState | None = None,
    ) -> numpy.ndarray:
        """装配当前状态对应的全局切线矩阵。"""

        return self._assembler.assemble_tangent(state=self._resolve_runtime_state(state=state, displacement=displacement))

    def assemble_residual(
        self,
        displacement: numpy.ndarray | None = None,
        state: RuntimeState | None = None,
    ) -> numpy.ndarray:
        """装配当前状态对应的全局残量向量。"""

        return self._assembler.assemble_residual(state=self._resolve_runtime_state(state=state, displacement=displacement))

    def assemble_mass(self, state: RuntimeState | None = None) -> numpy.ndarray:
        """装配全局质量矩阵。"""

        return self._assembler.assemble_mass(state=self._resolve_runtime_state(state=state))

    def assemble_damping(self, state: RuntimeState | None = None) -> numpy.ndarray:
        """装配全局阻尼矩阵。"""

        return self._assembler.assemble_damping(state=self._resolve_runtime_state(state=state))

    def assemble_external_load(
        self,
        step_definition,
        time: float = 0.0,
        state: RuntimeState | None = None,
        load_scale: float = 1.0,
    ) -> numpy.ndarray:
        """装配当前步骤的全局外载荷向量。"""

        return self._assembler.assemble_external_load(
            step_definition,
            time=time,
            state=self._resolve_runtime_state(state=state),
            load_scale=load_scale,
        )

    def collect_constraints(self, boundary_names: tuple[str, ...]):
        """返回步骤涉及的约束自由度集合。"""

        return self._assembler.collect_constraints(boundary_names)

    def build_constraint_value_map(self, boundary_names: tuple[str, ...], scale_factor: float = 1.0) -> dict[int, float]:
        """返回步骤约束自由度的目标值映射。"""

        return self._assembler.build_constraint_value_map(boundary_names, scale_factor=scale_factor)

    def apply_constraints(
        self,
        matrix: numpy.ndarray,
        rhs: numpy.ndarray,
        boundary_names: tuple[str, ...],
        scale_factor: float = 1.0,
    ) -> tuple[numpy.ndarray, numpy.ndarray]:
        """对全局系统施加步骤约束。"""

        return self._assembler.apply_constraints(matrix, rhs, boundary_names, scale_factor=scale_factor)

    def apply_prescribed_values(
        self,
        matrix: numpy.ndarray,
        rhs: numpy.ndarray,
        prescribed_values: dict[int, float],
    ) -> tuple[numpy.ndarray, numpy.ndarray]:
        """对任意系统施加给定值边界。"""

        return self._assembler.apply_prescribed_values(matrix, rhs, prescribed_values)

    def reduce_matrix(self, matrix: numpy.ndarray, boundary_names: tuple[str, ...]) -> ReducedSystem:
        """根据步骤约束构造缩减矩阵。"""

        return self._assembler.reduce_matrix(matrix, boundary_names)

    def expand_reduced_vector(
        self,
        reduced_vector: numpy.ndarray,
        free_indices: tuple[int, ...],
        prescribed_values: dict[int, float] | None = None,
    ) -> numpy.ndarray:
        """将缩减向量恢复到全局自由度空间。"""

        expanded_vector = numpy.zeros(self._compiled_model.dof_manager.num_dofs(), dtype=float)
        expanded_vector[list(free_indices)] = numpy.asarray(reduced_vector, dtype=float)
        if prescribed_values is not None:
            for dof_index, value in prescribed_values.items():
                expanded_vector[dof_index] = float(value)
        return expanded_vector

    def collect_element_outputs(
        self,
        displacement: numpy.ndarray | None = None,
        state: RuntimeState | None = None,
    ) -> dict[str, dict[str, object]]:
        """收集当前状态下的单元输出。"""

        return self._assembler.collect_element_outputs(
            state=self._resolve_runtime_state(state=state, displacement=displacement)
        )

    def commit(self, state: RuntimeState | None = None) -> None:
        """提交当前试算状态。"""

        self._state_manager.commit(state)

    def rollback(self) -> RuntimeState:
        """回滚到最近一次提交状态。"""

        return self._state_manager.rollback()

    def _resolve_runtime_state(
        self,
        state: RuntimeState | None = None,
        displacement: numpy.ndarray | None = None,
    ) -> RuntimeState:
        runtime_state = self._state_manager.trial_state if state is None else state
        if displacement is None:
            return runtime_state
        displaced_state = self._state_manager.copy_state(runtime_state)
        displaced_state.displacement = numpy.asarray(displacement, dtype=float)
        return displaced_state
