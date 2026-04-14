"""全局装配器。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy

from pyfem.compiler.compiled_model import CompiledModel
from pyfem.foundation.errors import CompilationError, SolverError
from pyfem.foundation.types import DofLocation
from pyfem.kernel.constraints import ConstrainedDof
from pyfem.kernel.elements import ElementRuntime
from pyfem.modeldb import DistributedLoadDef, NodalLoadDef, StepDef
from pyfem.modeldb.scopes import CompilationScope
from pyfem.solver.state import GlobalKinematicState, RuntimeState


@dataclass(slots=True, frozen=True)
class ReducedSystem:
    """描述施加约束后的缩减系统。"""

    matrix: numpy.ndarray
    free_indices: tuple[int, ...]


class Assembler:
    """负责从单元贡献构造全局离散系统。"""

    def __init__(self, compiled_model: CompiledModel, *, nlgeom: bool = False) -> None:
        """使用编译模型初始化装配器。"""

        self._compiled_model = compiled_model
        self._nlgeom = bool(nlgeom)

    def assemble_tangent(self, state: RuntimeState | None = None) -> numpy.ndarray:
        """装配全局切线矩阵。"""

        runtime_state = self._resolve_runtime_state(state)
        global_displacement = self._resolve_global_displacement(runtime_state.displacement)
        tangent = self._zero_matrix()
        for qualified_name, element_runtime in self._compiled_model.element_runtimes.items():
            local_displacement = self.extract_element_displacement(element_runtime, global_displacement)
            contribution = element_runtime.tangent_residual(
                displacement=tuple(local_displacement.tolist()),
                state=self._resolve_element_state(qualified_name, runtime_state, local_displacement),
            )
            self._scatter_matrix(tangent, contribution.stiffness, element_runtime.get_dof_indices())
        return tangent

    def assemble_residual(self, state: RuntimeState | None = None) -> numpy.ndarray:
        """装配全局内力残量向量。"""

        runtime_state = self._resolve_runtime_state(state)
        global_displacement = self._resolve_global_displacement(runtime_state.displacement)
        residual = self._zero_vector()
        for qualified_name, element_runtime in self._compiled_model.element_runtimes.items():
            local_displacement = self.extract_element_displacement(element_runtime, global_displacement)
            contribution = element_runtime.tangent_residual(
                displacement=tuple(local_displacement.tolist()),
                state=self._resolve_element_state(qualified_name, runtime_state, local_displacement),
            )
            self._scatter_vector(residual, contribution.residual, element_runtime.get_dof_indices())
        return residual

    def assemble_mass(self, state: RuntimeState | None = None) -> numpy.ndarray:
        """装配全局质量矩阵。"""

        runtime_state = self._resolve_runtime_state(state)
        mass = self._zero_matrix()
        for qualified_name, element_runtime in self._compiled_model.element_runtimes.items():
            self._scatter_matrix(
                mass,
                element_runtime.mass(state=self._resolve_element_state(qualified_name, runtime_state)),
                element_runtime.get_dof_indices(),
            )
        return mass

    def assemble_damping(self, state: RuntimeState | None = None) -> numpy.ndarray:
        """装配全局阻尼矩阵。"""

        runtime_state = self._resolve_runtime_state(state)
        damping = self._zero_matrix()
        for qualified_name, element_runtime in self._compiled_model.element_runtimes.items():
            local_damping = element_runtime.damping(state=self._resolve_element_state(qualified_name, runtime_state))
            if local_damping is None:
                continue
            self._scatter_matrix(damping, local_damping, element_runtime.get_dof_indices())
        return damping

    def assemble_external_load(
        self,
        step_definition: StepDef,
        time: float = 0.0,
        state: RuntimeState | None = None,
        load_scale: float = 1.0,
    ) -> numpy.ndarray:
        """根据步骤定义装配全局外载荷向量。"""

        runtime_state = self._resolve_runtime_state(state)
        external_load = self._zero_vector()
        for load_name in step_definition.nodal_load_names:
            load_definition = self._compiled_model.model.nodal_loads[load_name]
            scale = float(load_definition.parameters.get("scale", 1.0))
            self._assemble_nodal_load(external_load, load_definition, scale=load_scale * scale, time=time)
        for load_name in step_definition.distributed_load_names:
            load_definition = self._compiled_model.model.distributed_loads[load_name]
            scale = float(load_definition.parameters.get("scale", 1.0))
            self._assemble_distributed_load(
                external_load,
                load_definition,
                scale=load_scale * scale,
                time=time,
                state=runtime_state,
            )
        return external_load

    def collect_constraints(self, boundary_names: tuple[str, ...]) -> tuple[ConstrainedDof, ...]:
        """收集步骤涉及的全部约束自由度。"""

        constrained_values: dict[int, float] = {}
        for boundary_name in boundary_names:
            try:
                runtime = self._compiled_model.constraint_runtimes[boundary_name]
            except KeyError as error:
                raise CompilationError(f"编译模型中不存在约束运行时 {boundary_name}。") from error
            for constrained_dof in runtime.collect_constrained_dofs():
                existing_value = constrained_values.get(constrained_dof.dof_index)
                if existing_value is not None and abs(existing_value - constrained_dof.value) > 1.0e-12:
                    raise SolverError(f"自由度 {constrained_dof.dof_index} 收到了冲突的位移约束值。")
                constrained_values[constrained_dof.dof_index] = constrained_dof.value
        return tuple(
            ConstrainedDof(dof_index=dof_index, value=value)
            for dof_index, value in sorted(constrained_values.items())
        )

    def build_constraint_value_map(self, boundary_names: tuple[str, ...], scale_factor: float = 1.0) -> dict[int, float]:
        """将约束集合转换为自由度到目标值的映射。"""

        return {item.dof_index: float(scale_factor) * item.value for item in self.collect_constraints(boundary_names)}

    def apply_constraints(
        self,
        matrix: numpy.ndarray,
        rhs: numpy.ndarray,
        boundary_names: tuple[str, ...],
        scale_factor: float = 1.0,
    ) -> tuple[numpy.ndarray, numpy.ndarray]:
        """对全局系统施加位移约束。"""

        return self.apply_prescribed_values(
            matrix,
            rhs,
            self.build_constraint_value_map(boundary_names, scale_factor=scale_factor),
        )

    def apply_prescribed_values(
        self,
        matrix: numpy.ndarray,
        rhs: numpy.ndarray,
        prescribed_values: Mapping[int, float],
    ) -> tuple[numpy.ndarray, numpy.ndarray]:
        """对任意线性系统施加给定位移值。"""

        constrained_matrix = numpy.asarray(matrix, dtype=float).copy()
        constrained_rhs = numpy.asarray(rhs, dtype=float).copy()
        original_matrix = constrained_matrix.copy()

        for dof_index, value in prescribed_values.items():
            constrained_rhs -= original_matrix[:, dof_index] * float(value)

        for dof_index, value in prescribed_values.items():
            constrained_matrix[dof_index, :] = 0.0
            constrained_matrix[:, dof_index] = 0.0
            constrained_matrix[dof_index, dof_index] = 1.0
            constrained_rhs[dof_index] = float(value)

        return constrained_matrix, constrained_rhs

    def reduce_matrix(self, matrix: numpy.ndarray, boundary_names: tuple[str, ...]) -> ReducedSystem:
        """根据位移约束构造缩减矩阵。"""

        prescribed_values = self.build_constraint_value_map(boundary_names)
        free_indices = tuple(
            index for index in range(self._compiled_model.dof_manager.num_dofs()) if index not in prescribed_values
        )
        reduced_matrix = numpy.asarray(matrix, dtype=float)[numpy.ix_(free_indices, free_indices)]
        return ReducedSystem(matrix=reduced_matrix, free_indices=free_indices)

    def collect_element_outputs(self, state: RuntimeState | None = None) -> dict[str, dict[str, Any]]:
        """汇总全部单元的输出字典。"""

        runtime_state = self._resolve_runtime_state(state)
        global_displacement = self._resolve_global_displacement(runtime_state.displacement)
        outputs: dict[str, dict[str, Any]] = {}
        for qualified_name, element_runtime in self._compiled_model.element_runtimes.items():
            local_displacement = self.extract_element_displacement(element_runtime, global_displacement)
            outputs[qualified_name] = dict(
                element_runtime.output(
                    displacement=tuple(local_displacement.tolist()),
                    state=self._resolve_element_state(qualified_name, runtime_state, local_displacement),
                )
            )
        return outputs

    def extract_element_displacement(
        self,
        element_runtime: ElementRuntime,
        global_displacement: numpy.ndarray,
    ) -> numpy.ndarray:
        """提取单元对应的局部自由度位移。"""

        return numpy.asarray(
            [global_displacement[index] for index in element_runtime.get_dof_indices()],
            dtype=float,
        )

    def _assemble_nodal_load(
        self,
        external_load: numpy.ndarray,
        load_definition: NodalLoadDef,
        scale: float,
        time: float,
    ) -> None:
        del time
        scopes = self._compiled_model.model.iter_target_scopes(load_definition.scope_name)
        if load_definition.scope_name is not None and not scopes:
            raise SolverError(f"未找到作用域 {load_definition.scope_name}。")

        for scope in scopes:
            node_names = self._resolve_target_nodes(scope, load_definition.target_type, load_definition.target_name)
            for node_name in node_names:
                for component_name, value in load_definition.components.items():
                    dof_name = self._resolve_load_dof_name(component_name)
                    dof_index = self._compiled_model.dof_manager.get_global_id(
                        DofLocation(scope_name=scope.scope_name, node_name=node_name, dof_name=dof_name)
                    )
                    external_load[dof_index] += scale * float(value)

    def _assemble_distributed_load(
        self,
        external_load: numpy.ndarray,
        load_definition: DistributedLoadDef,
        scale: float,
        time: float,
        state: RuntimeState,
    ) -> None:
        del time
        if self._nlgeom:
            normalized_load_type = self._normalize_distributed_load_type(load_definition.load_type)
            raise SolverError(
                f"distributed load {load_definition.name} 在 nlgeom=True 下暂不支持。"
                f"收到 load_type={normalized_load_type}, target_type={load_definition.target_type}, target={load_definition.target_name}。"
                "当前正式支持的 nlgeom 载荷范围仅包括位移边界与 nodal load；"
                "distributed load、surface pressure 与 follower pressure 仍需后续正式当前构形实现。"
            )
        if load_definition.target_type != "surface":
            raise SolverError(f"当前阶段仅支持 surface 目标的分布载荷，收到 {load_definition.target_type}。")

        scopes = self._compiled_model.model.iter_target_scopes(load_definition.scope_name)
        if load_definition.scope_name is not None and not scopes:
            raise SolverError(f"未找到作用域 {load_definition.scope_name}。")

        matched_surface = False
        for scope in scopes:
            surface = scope.get_surface(load_definition.target_name)
            if surface is None:
                continue
            matched_surface = True
            for facet in surface.facets:
                qualified_name = scope.qualify_element_name(facet.element_name)
                try:
                    element_runtime = self._compiled_model.element_runtimes[qualified_name]
                except KeyError as error:
                    raise SolverError(f"分布载荷目标表面 {load_definition.target_name} 引用了不存在的单元 {qualified_name}。") from error
                try:
                    local_vector = numpy.asarray(
                        element_runtime.surface_load(
                            local_face=facet.local_face,
                            load_type=load_definition.load_type,
                            components=load_definition.components,
                            state=self._resolve_element_state(qualified_name, state),
                        ),
                        dtype=float,
                    )
                except NotImplementedError as error:
                    raise SolverError(
                        f"单元 {qualified_name} 当前不支持分布载荷 {load_definition.load_type}。"
                    ) from error
                self._scatter_vector(external_load, scale * local_vector, element_runtime.get_dof_indices())

        if not matched_surface:
            raise SolverError(f"未找到分布载荷目标表面 {load_definition.target_name}。")

    def _normalize_distributed_load_type(self, load_type: str) -> str:
        normalized_load_type = str(load_type).strip().lower()
        aliases = {
            "p": "pressure",
            "pressure": "pressure",
            "follower": "follower_pressure",
            "follower_pressure": "follower_pressure",
            "follower-pressure": "follower_pressure",
        }
        return aliases.get(normalized_load_type, normalized_load_type)

    def _resolve_target_nodes(
        self,
        scope: CompilationScope,
        target_type: str,
        target_name: str,
    ) -> tuple[str, ...]:
        if target_type not in {"node", "node_set"}:
            raise SolverError(f"当前载荷装配暂不支持目标类型 {target_type}。")
        return scope.resolve_node_names(target_type, target_name)

    def _resolve_load_dof_name(self, component_name: str) -> str:
        normalized_name = component_name.upper()
        direct_names = {"UX", "UY", "UZ", "RX", "RY", "RZ"}
        if normalized_name in direct_names:
            return normalized_name
        mapping = {
            "FX": "UX",
            "FY": "UY",
            "FZ": "UZ",
            "MX": "RX",
            "MY": "RY",
            "MZ": "RZ",
        }
        try:
            return mapping[normalized_name]
        except KeyError as error:
            raise SolverError(f"当前不支持载荷分量 {component_name}。") from error

    def _resolve_runtime_state(self, state: RuntimeState | None) -> RuntimeState:
        if state is not None:
            return state
        return RuntimeState(
            kinematics=GlobalKinematicState(
                displacement=self._zero_vector(),
                velocity=self._zero_vector(),
                acceleration=self._zero_vector(),
                time=0.0,
            ),
        )

    def _resolve_element_state(
        self,
        qualified_name: str,
        runtime_state: RuntimeState,
        local_displacement: numpy.ndarray | None = None,
    ) -> dict[str, Any]:
        element_state = runtime_state.element_states.setdefault(qualified_name, {})
        if local_displacement is not None:
            element_state["displacement"] = tuple(local_displacement.tolist())
        element_state["time"] = float(runtime_state.time)
        element_state["integration_points"] = runtime_state.integration_point_states.setdefault(qualified_name, {})
        analysis_flags = element_state.setdefault("analysis_flags", {})
        analysis_flags["nlgeom"] = self._nlgeom
        return element_state

    def _resolve_global_displacement(self, displacement: numpy.ndarray | None) -> numpy.ndarray:
        if displacement is None:
            return self._zero_vector()
        vector = numpy.asarray(displacement, dtype=float)
        if vector.shape != (self._compiled_model.dof_manager.num_dofs(),):
            raise SolverError("全局位移向量维度与自由度总数不一致。")
        return vector

    def _zero_vector(self) -> numpy.ndarray:
        return numpy.zeros(self._compiled_model.dof_manager.num_dofs(), dtype=float)

    def _zero_matrix(self) -> numpy.ndarray:
        size = self._compiled_model.dof_manager.num_dofs()
        return numpy.zeros((size, size), dtype=float)

    def _scatter_matrix(self, global_matrix: numpy.ndarray, local_matrix, dof_indices: tuple[int, ...]) -> None:
        dense_local = numpy.asarray(local_matrix, dtype=float)
        for row_offset, global_row in enumerate(dof_indices):
            for column_offset, global_column in enumerate(dof_indices):
                global_matrix[global_row, global_column] += dense_local[row_offset, column_offset]

    def _scatter_vector(self, global_vector: numpy.ndarray, local_vector, dof_indices: tuple[int, ...]) -> None:
        dense_local = numpy.asarray(local_vector, dtype=float)
        for offset, global_index in enumerate(dof_indices):
            global_vector[global_index] += dense_local[offset]
