"""求解阶段状态对象与生命周期管理。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

import numpy

from pyfem.compiler.compiled_model import CompiledModel


@dataclass(slots=True)
class GlobalKinematicState:
    """描述全局运动学状态。"""

    displacement: numpy.ndarray
    velocity: numpy.ndarray
    acceleration: numpy.ndarray
    time: float = 0.0


@dataclass(slots=True)
class RuntimeState:
    """描述一次试算或提交时刻的全局与局部状态。"""

    kinematics: GlobalKinematicState
    element_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    material_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    integration_point_states: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    interaction_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    constraint_states: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def displacement(self) -> numpy.ndarray:
        """返回全局位移向量。"""

        return self.kinematics.displacement

    @displacement.setter
    def displacement(self, value) -> None:
        self.kinematics.displacement = numpy.asarray(value, dtype=float).copy()

    @property
    def velocity(self) -> numpy.ndarray:
        """返回全局速度向量。"""

        return self.kinematics.velocity

    @velocity.setter
    def velocity(self, value) -> None:
        self.kinematics.velocity = numpy.asarray(value, dtype=float).copy()

    @property
    def acceleration(self) -> numpy.ndarray:
        """返回全局加速度向量。"""

        return self.kinematics.acceleration

    @acceleration.setter
    def acceleration(self, value) -> None:
        self.kinematics.acceleration = numpy.asarray(value, dtype=float).copy()

    @property
    def time(self) -> float:
        """返回当前状态时刻。"""

        return self.kinematics.time

    @time.setter
    def time(self, value: float) -> None:
        self.kinematics.time = float(value)


ProblemState = RuntimeState


class StateManager:
    """负责 RuntimeState 的分配、试算、提交与回滚。"""

    def __init__(self, compiled_model: CompiledModel) -> None:
        """使用编译模型初始化状态管理器。"""

        self._compiled_model = compiled_model
        self._committed_state = self.allocate_runtime_state()
        self._trial_state = self.allocate_runtime_state()

    @property
    def committed_state(self) -> RuntimeState:
        """返回内部已提交状态对象。"""

        return self._committed_state

    @property
    def trial_state(self) -> RuntimeState:
        """返回内部试算状态对象。"""

        return self._trial_state

    def allocate_runtime_state(self, time: float = 0.0) -> RuntimeState:
        """按当前编译模型分配一份新的运行时状态。"""

        size = self._compiled_model.dof_manager.num_dofs()
        return RuntimeState(
            kinematics=GlobalKinematicState(
                displacement=numpy.zeros(size, dtype=float),
                velocity=numpy.zeros(size, dtype=float),
                acceleration=numpy.zeros(size, dtype=float),
                time=float(time),
            ),
            element_states=self._allocate_state_map(self._compiled_model.element_runtimes),
            material_states=self._allocate_state_map(self._compiled_model.material_runtimes),
            # 为未来积分点 owner 语义预留正式状态入口，避免把历史变量按材料名聚合。
            integration_point_states={},
            interaction_states=self._allocate_state_map(self._compiled_model.interaction_runtimes),
            constraint_states=self._allocate_state_map(self._compiled_model.constraint_runtimes),
        )

    def copy_state(self, state: RuntimeState) -> RuntimeState:
        """深拷贝一份运行时状态。"""

        return RuntimeState(
            kinematics=GlobalKinematicState(
                displacement=numpy.asarray(state.displacement, dtype=float).copy(),
                velocity=numpy.asarray(state.velocity, dtype=float).copy(),
                acceleration=numpy.asarray(state.acceleration, dtype=float).copy(),
                time=float(state.time),
            ),
            element_states=deepcopy(state.element_states),
            material_states=deepcopy(state.material_states),
            integration_point_states=deepcopy(state.integration_point_states),
            interaction_states=deepcopy(state.interaction_states),
            constraint_states=deepcopy(state.constraint_states),
        )

    def get_committed_state(self) -> RuntimeState:
        """返回当前已提交状态的副本。"""

        return self.copy_state(self._committed_state)

    def get_trial_state(self) -> RuntimeState:
        """返回当前试算状态的副本。"""

        return self.copy_state(self._trial_state)

    def begin_trial(self, base_state: RuntimeState | None = None) -> RuntimeState:
        """以给定状态或当前提交状态为基准开启试算。"""

        source_state = self._committed_state if base_state is None else base_state
        self._trial_state = self.copy_state(source_state)
        return self._trial_state

    def set_trial_state(self, state: RuntimeState) -> None:
        """直接写入新的试算状态。"""

        self._trial_state = self.copy_state(state)

    def commit(self, state: RuntimeState | None = None) -> None:
        """提交当前试算状态。"""

        if state is not None:
            self._trial_state = self.copy_state(state)
        self._committed_state = self.copy_state(self._trial_state)

    def rollback(self) -> RuntimeState:
        """回滚到最近一次提交状态。"""

        self._trial_state = self.copy_state(self._committed_state)
        return self.get_trial_state()

    def _allocate_state_map(self, runtimes: dict[str, object]) -> dict[str, dict[str, Any]]:
        return {
            name: self._allocate_local_state(runtime)
            for name, runtime in runtimes.items()
        }

    def _allocate_local_state(self, runtime: object) -> dict[str, Any]:
        allocate_state = getattr(runtime, "allocate_state", None)
        if callable(allocate_state):
            raw_state = allocate_state()
            if raw_state is None:
                return {}
            return deepcopy(dict(raw_state))
        return {}
