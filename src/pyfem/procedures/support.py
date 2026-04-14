"""???? procedure ??????"""

from __future__ import annotations

from abc import ABC
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy

from pyfem.compiler.compiled_model import CompiledModel
from pyfem.foundation.errors import SolverError
from pyfem.foundation.types import DofLocation
from pyfem.io import (
    AXIS_KIND_TIME,
    FIELD_KEY_E,
    FIELD_KEY_MODE_SHAPE,
    FIELD_KEY_RF,
    FIELD_KEY_S,
    FIELD_KEY_S_REC,
    FIELD_KEY_U,
    FRAME_KIND_SOLUTION,
    GLOBAL_HISTORY_TARGET,
    POSITION_ELEMENT_CENTROID,
    POSITION_ELEMENT_NODAL,
    POSITION_INTEGRATION_POINT,
    POSITION_NODE,
    POSITION_NODE_AVERAGED,
    ResultField,
    ResultFrame,
    ResultHistorySeries,
    ResultSummary,
    ResultsSession,
)
from pyfem.modeldb import StepDef
from pyfem.post import AveragingService, DerivedFieldService, RawFieldService, RecoveryService
from pyfem.post.common import (
    build_component_mapping,
    build_measure_metadata,
    resolve_strain_component_names,
    resolve_stress_component_names,
    subset_result_field,
)
from pyfem.procedures.base import ProcedureRuntime
from pyfem.procedures.output_requests import OutputFieldPlan, OutputRequestPlanner
from pyfem.solver import DiscreteProblem, LinearAlgebraBackend, ProblemState


_NODE_VECTOR_FIELDS = {FIELD_KEY_U, FIELD_KEY_RF, FIELD_KEY_MODE_SHAPE}
_ELEMENT_OUTPUT_POSITIONS = {
    POSITION_ELEMENT_CENTROID,
    POSITION_INTEGRATION_POINT,
    POSITION_ELEMENT_NODAL,
    POSITION_NODE_AVERAGED,
}
_SECTION_EXCLUDED_KEYS = {
    "type_key",
    "location",
    "scope_name",
    "node_names",
    "node_keys",
    "section_name",
    "section_type",
    "material_name",
    "averaging_weight",
    "integration_points",
    "recovery",
    "strain",
    "stress",
    "thickness",
    "axial_strain",
    "axial_stress",
}


@dataclass(slots=True)
class StepProcedureRuntime(ProcedureRuntime, ABC):
    """??????????? procedure ?????"""

    definition: StepDef
    compiled_model: CompiledModel
    problem: DiscreteProblem
    backend: LinearAlgebraBackend
    output_planner: OutputRequestPlanner = field(init=False, repr=False)
    raw_field_service: RawFieldService = field(init=False, repr=False)
    recovery_service: RecoveryService = field(init=False, repr=False)
    averaging_service: AveragingService = field(init=False, repr=False)
    derived_field_service: DerivedFieldService = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """???????????????"""

        self.output_planner = OutputRequestPlanner(self.compiled_model, self.definition)
        self.raw_field_service = RawFieldService()
        self.recovery_service = RecoveryService()
        self.averaging_service = AveragingService()
        self.derived_field_service = DerivedFieldService()

    def get_name(self) -> str:
        """???????"""

        return self.definition.name

    def get_procedure_type(self) -> str:
        """????????????"""

        return self.definition.procedure_type

    def describe(self) -> Mapping[str, Any]:
        """???????????????"""

        return {
            "name": self.definition.name,
            "procedure_type": self.definition.procedure_type,
            "boundary_names": tuple(self.definition.boundary_names),
            "nodal_load_names": tuple(self.definition.nodal_load_names),
            "distributed_load_names": tuple(self.definition.distributed_load_names),
            "output_request_names": tuple(self.definition.output_request_names),
            "parameters": dict(self.definition.parameters),
        }

    def build_results_session(self) -> ResultsSession:
        """?????????????"""

        job_name = None if self.compiled_model.model.job is None else self.compiled_model.model.job.name
        return ResultsSession(
            model_name=self.compiled_model.model_name,
            procedure_name=self.get_name(),
            job_name=job_name,
            step_name=self.get_name(),
            procedure_type=self.get_procedure_type(),
            metadata={
                "model_metadata": self.compiled_model.model.metadata.to_dict(),
                "step_parameters": dict(self.definition.parameters),
                "output_request_names": tuple(self.definition.output_request_names),
            },
        )

    def build_initial_state(self) -> ProblemState:
        """?????????????"""

        state = self.problem.create_zero_state(time=0.0)
        state.displacement = self._build_parameter_vector("initial_displacement")
        state.velocity = self._build_parameter_vector("initial_velocity")
        state.acceleration = self._build_parameter_vector("initial_acceleration")
        return state

    def build_step_start_state(self) -> ProblemState:
        """构造当前步骤的正式起始状态。"""

        inherited_state = self.resolve_inherited_state()
        if inherited_state is None:
            state = self.problem.create_zero_state(time=0.0)
        else:
            state = self.problem.state_manager.copy_state(inherited_state)
        if "initial_displacement" in self.definition.parameters:
            state.displacement = self._build_parameter_vector("initial_displacement")
        if "initial_velocity" in self.definition.parameters:
            state.velocity = self._build_parameter_vector("initial_velocity")
        if "initial_acceleration" in self.definition.parameters:
            state.acceleration = self._build_parameter_vector("initial_acceleration")
        return state

    def get_state_transfer_channel(self) -> str | None:
        """返回当前步骤的状态继承通道。"""

        return None

    def resolve_inherited_state(self) -> ProblemState | None:
        """解析当前步骤可继承的 committed 状态。"""

        channel = self.get_state_transfer_channel()
        if channel is None:
            return None
        return self.compiled_model.resolve_inherited_step_state(self.get_name(), channel)

    def restore_problem_state_from_previous_step(self) -> None:
        """在步骤执行前将上一步 committed 状态装入当前 problem。"""

        inherited_state = self.resolve_inherited_state()
        if inherited_state is None:
            return
        copied_state = self.problem.state_manager.copy_state(inherited_state)
        self.problem.commit(copied_state)

    def publish_problem_state_to_following_steps(self) -> None:
        """在步骤成功结束后发布 committed 状态供后续步骤继承。"""

        channel = self.get_state_transfer_channel()
        if channel is None:
            return
        self.compiled_model.publish_step_state(self.get_name(), channel, self.problem.get_committed_state())

    def build_result_fields(
        self,
        frame_id: int,
        displacement: numpy.ndarray | None = None,
        state: ProblemState | None = None,
        field_vectors: Mapping[str, numpy.ndarray] | None = None,
    ) -> tuple[ResultField, ...]:
        """????????????????"""

        field_plans = self.output_planner.build_field_plans(frame_id)
        if not field_plans:
            return ()

        vector_sources = {key.upper(): numpy.asarray(value, dtype=float) for key, value in (field_vectors or {}).items()}
        if displacement is not None and FIELD_KEY_U not in vector_sources:
            vector_sources[FIELD_KEY_U] = numpy.asarray(displacement, dtype=float)

        field_registry = self._build_field_registry(
            field_plans=field_plans,
            vector_sources=vector_sources,
            displacement=displacement,
            state=state,
        )
        fields: list[ResultField] = []
        for plan in field_plans:
            field_result = field_registry.get(plan.variable)
            if field_result is None:
                if plan.variable in _NODE_VECTOR_FIELDS:
                    raise SolverError(f"?? {self.get_name()} ???? {plan.variable} ????????")
                continue
            filtered_field = subset_result_field(field_result, plan.target_keys)
            if filtered_field.values:
                fields.append(filtered_field)
        return tuple(fields)

    def build_frame(
        self,
        frame_id: int,
        time: float,
        displacement: numpy.ndarray | None = None,
        state: ProblemState | None = None,
        field_vectors: Mapping[str, numpy.ndarray] | None = None,
        metadata: Mapping[str, Any] | None = None,
        frame_kind: str = FRAME_KIND_SOLUTION,
        axis_kind: str = AXIS_KIND_TIME,
        axis_value: float | int | None = None,
    ) -> ResultFrame:
        """????????????"""

        return ResultFrame(
            frame_id=frame_id,
            step_name=self.get_name(),
            time=float(time),
            fields=self.build_result_fields(
                frame_id=frame_id,
                displacement=displacement,
                state=state,
                field_vectors=field_vectors,
            ),
            metadata={} if metadata is None else dict(metadata),
            frame_kind=frame_kind,
            axis_kind=axis_kind,
            axis_value=axis_value,
        )

    def build_global_history_series(
        self,
        name: str,
        axis_kind: str,
        axis_values: tuple[float | int, ...],
        values: tuple[Any, ...],
        metadata: Mapping[str, Any] | None = None,
        paired_values: Mapping[str, tuple[Any, ...]] | None = None,
    ) -> ResultHistorySeries:
        """????????????"""

        serialized_paired_values = (
            {}
            if paired_values is None
            else {key: tuple(series) for key, series in paired_values.items()}
        )
        return ResultHistorySeries(
            name=name,
            step_name=self.get_name(),
            axis_kind=axis_kind,
            axis_values=tuple(axis_values),
            values={GLOBAL_HISTORY_TARGET: tuple(values)},
            position="GLOBAL_HISTORY",
            metadata={} if metadata is None else dict(metadata),
            paired_values=serialized_paired_values,
        )

    def build_summary(self, name: str, data: Mapping[str, Any], metadata: Mapping[str, Any] | None = None) -> ResultSummary:
        """???????????"""

        return ResultSummary(
            name=name,
            step_name=self.get_name(),
            data=dict(data),
            metadata={} if metadata is None else dict(metadata),
        )

    def build_nodal_vector_field(
        self,
        field_name: str,
        vector: numpy.ndarray,
        target_keys: tuple[str, ...] | None = None,
    ) -> ResultField:
        """?????????????????"""

        values = self._build_nodal_vector_values(vector)
        if target_keys is not None:
            allowed_keys = set(target_keys)
            values = {key: value for key, value in values.items() if key in allowed_keys}
        return ResultField(name=field_name, position=POSITION_NODE, values=values)

    def _resolve_requested_variables(self) -> tuple[str, ...]:
        return self.output_planner.requested_variables()

    def _build_field_registry(
        self,
        *,
        field_plans: tuple[OutputFieldPlan, ...],
        vector_sources: Mapping[str, numpy.ndarray],
        displacement: numpy.ndarray | None,
        state: ProblemState | None,
    ) -> dict[str, ResultField]:
        field_registry: dict[str, ResultField] = {}
        for field_name, vector in vector_sources.items():
            if field_name in _NODE_VECTOR_FIELDS:
                field_registry[field_name] = self.build_nodal_vector_field(field_name, vector)

        if any(plan.position in _ELEMENT_OUTPUT_POSITIONS for plan in field_plans):
            element_outputs = self.problem.collect_element_outputs(displacement=displacement, state=state)
            for field in self._build_element_fields(element_outputs):
                field_registry[field.name] = field

        for field in self.derived_field_service.build_fields(field_registry):
            field_registry[field.name] = field
        return field_registry

    def _build_element_fields(self, element_outputs: Mapping[str, Mapping[str, Any]]) -> tuple[ResultField, ...]:
        fields: list[ResultField] = []
        for variable in (FIELD_KEY_E, FIELD_KEY_S):
            field = self._build_centroid_measure_field(variable, element_outputs)
            if field is not None:
                fields.append(field)

        section_values = self._build_element_output_values("SECTION", element_outputs, tuple(element_outputs.keys()))
        if section_values:
            fields.append(ResultField(name="SECTION", position=POSITION_ELEMENT_CENTROID, values=section_values))

        raw_fields = self.raw_field_service.build_fields(element_outputs)
        fields.extend(raw_fields)
        recovered_fields = self.recovery_service.build_fields(element_outputs)
        fields.extend(recovered_fields)
        recovered_stress_field = next((field for field in recovered_fields if field.name == FIELD_KEY_S_REC), None)
        fields.extend(self.averaging_service.build_fields(recovered_stress_field))
        return tuple(fields)

    def _build_centroid_measure_field(
        self,
        variable: str,
        element_outputs: Mapping[str, Mapping[str, Any]],
    ) -> ResultField | None:
        target_keys = tuple(element_outputs.keys())
        values = self._build_element_output_values(variable, element_outputs, target_keys)
        if not values:
            return None

        if variable == FIELD_KEY_E:
            metadata = build_measure_metadata(
                target_keys=tuple(values.keys()),
                strain_measures={
                    qualified_name: str(output.get("strain_measure", "unspecified"))
                    for qualified_name, output in element_outputs.items()
                    if qualified_name in values
                },
                tangent_measures={
                    qualified_name: str(output.get("tangent_measure", "unspecified"))
                    for qualified_name, output in element_outputs.items()
                    if qualified_name in values
                },
            )
        elif variable == FIELD_KEY_S:
            metadata = build_measure_metadata(
                target_keys=tuple(values.keys()),
                stress_measures={
                    qualified_name: str(output.get("stress_measure", "unspecified"))
                    for qualified_name, output in element_outputs.items()
                    if qualified_name in values
                },
                tangent_measures={
                    qualified_name: str(output.get("tangent_measure", "unspecified"))
                    for qualified_name, output in element_outputs.items()
                    if qualified_name in values
                },
            )
        else:
            raise SolverError(f"步骤 {self.get_name()} 无法为变量 {variable} 构造 centroid measure metadata。")

        return ResultField(
            name=variable,
            position=POSITION_ELEMENT_CENTROID,
            values=values,
            metadata=metadata,
        )

    def _build_parameter_vector(self, parameter_name: str) -> numpy.ndarray:
        vector = numpy.zeros(self.compiled_model.dof_manager.num_dofs(), dtype=float)
        raw_mapping = self.definition.parameters.get(parameter_name, {})
        if not isinstance(raw_mapping, Mapping):
            raise SolverError(f"???? {parameter_name} ????????????????")

        for qualified_name, value in raw_mapping.items():
            scope_name, node_name, dof_name = self._parse_qualified_dof_name(str(qualified_name))
            dof_index = self.compiled_model.dof_manager.get_global_id(
                DofLocation(scope_name=scope_name, node_name=node_name, dof_name=dof_name)
            )
            vector[dof_index] = float(value)
        return vector

    def _parse_qualified_dof_name(self, qualified_name: str) -> tuple[str, str, str]:
        parts = qualified_name.split(".")
        if len(parts) != 3:
            raise SolverError(f"?????? {qualified_name} ??? scope.node.dof ???")
        scope_name, node_name, dof_name = parts
        return scope_name, node_name, dof_name.upper()

    def _build_nodal_vector_values(self, vector: numpy.ndarray) -> dict[str, dict[str, float]]:
        values: dict[str, dict[str, float]] = {}
        for descriptor in self.compiled_model.dof_manager.iter_descriptors():
            node_key = descriptor.location.get_result_key()
            if node_key is None:
                continue
            node_values = values.setdefault(node_key, {})
            node_values[descriptor.location.dof_name] = float(vector[descriptor.index])
        return values

    def _build_element_output_values(
        self,
        variable: str,
        element_outputs: Mapping[str, Mapping[str, Any]],
        target_keys: tuple[str, ...],
    ) -> dict[str, Any]:
        allowed_keys = set(target_keys)
        values: dict[str, Any] = {}
        for qualified_name, output in element_outputs.items():
            if qualified_name not in allowed_keys:
                continue
            if variable == FIELD_KEY_E:
                selected_value = output.get("axial_strain", output.get("strain"))
            elif variable == FIELD_KEY_S:
                selected_value = output.get("axial_stress", output.get("stress"))
            elif variable == "SECTION":
                selected_value = {
                    key: value
                    for key, value in output.items()
                    if key not in _SECTION_EXCLUDED_KEYS
                }
            else:
                raise SolverError(f"?? {self.get_name()} ????????? {variable} ??????")

            if selected_value is None:
                continue
            if isinstance(selected_value, dict) and not selected_value:
                continue
            if isinstance(selected_value, tuple) and not selected_value:
                continue
            if variable in {FIELD_KEY_E, FIELD_KEY_S}:
                selected_value = self._build_named_centroid_measure_value(variable, output, selected_value)
            values[qualified_name] = selected_value
        return values

    def _build_named_centroid_measure_value(
        self,
        variable: str,
        output: Mapping[str, Any],
        raw_value: Any,
    ) -> dict[str, float] | Any:
        if isinstance(raw_value, Mapping):
            return dict(raw_value)

        type_key = str(output["type_key"])
        if variable == FIELD_KEY_E:
            component_names = resolve_strain_component_names(type_key)
        elif variable == FIELD_KEY_S:
            component_names = resolve_stress_component_names(type_key)
        else:
            return raw_value

        if isinstance(raw_value, numpy.ndarray):
            component_values = tuple(float(item) for item in raw_value.reshape(-1).tolist())
        elif isinstance(raw_value, (tuple, list)):
            component_values = tuple(float(item) for item in raw_value)
        else:
            component_values = (float(raw_value),)
        return build_component_mapping(component_values, component_names)
