"""输出请求的解析、校验与执行计划。"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from pyfem.compiler.compiled_model import CompiledModel
from pyfem.foundation.errors import CompilationError
from pyfem.io import (
    FIELD_KEY_E,
    FIELD_KEY_E_IP,
    FIELD_KEY_E_REC,
    FIELD_KEY_FREQUENCY,
    FIELD_KEY_MODE_SHAPE,
    FIELD_KEY_RF,
    FIELD_KEY_S,
    FIELD_KEY_S_AVG,
    FIELD_KEY_S_IP,
    FIELD_KEY_S_PRINCIPAL_AVG,
    FIELD_KEY_S_PRINCIPAL_IP,
    FIELD_KEY_S_PRINCIPAL_REC,
    FIELD_KEY_S_REC,
    FIELD_KEY_S_VM_AVG,
    FIELD_KEY_S_VM_IP,
    FIELD_KEY_S_VM_REC,
    FIELD_KEY_TIME,
    FIELD_KEY_U,
    FIELD_KEY_U_MAG,
    POSITION_ELEMENT_CENTROID,
    POSITION_ELEMENT_NODAL,
    POSITION_GLOBAL_HISTORY,
    POSITION_INTEGRATION_POINT,
    POSITION_NODE,
    POSITION_NODE_AVERAGED,
)
from pyfem.modeldb import OutputRequest, StepDef


_VARIABLE_POSITION = {
    FIELD_KEY_U: POSITION_NODE,
    FIELD_KEY_U_MAG: POSITION_NODE,
    FIELD_KEY_RF: POSITION_NODE,
    FIELD_KEY_MODE_SHAPE: POSITION_NODE,
    FIELD_KEY_S: POSITION_ELEMENT_CENTROID,
    FIELD_KEY_E: POSITION_ELEMENT_CENTROID,
    "SECTION": POSITION_ELEMENT_CENTROID,
    FIELD_KEY_S_IP: POSITION_INTEGRATION_POINT,
    FIELD_KEY_E_IP: POSITION_INTEGRATION_POINT,
    FIELD_KEY_S_REC: POSITION_ELEMENT_NODAL,
    FIELD_KEY_E_REC: POSITION_ELEMENT_NODAL,
    FIELD_KEY_S_AVG: POSITION_NODE_AVERAGED,
    FIELD_KEY_S_VM_IP: POSITION_INTEGRATION_POINT,
    FIELD_KEY_S_PRINCIPAL_IP: POSITION_INTEGRATION_POINT,
    FIELD_KEY_S_VM_REC: POSITION_ELEMENT_NODAL,
    FIELD_KEY_S_PRINCIPAL_REC: POSITION_ELEMENT_NODAL,
    FIELD_KEY_S_VM_AVG: POSITION_NODE_AVERAGED,
    FIELD_KEY_S_PRINCIPAL_AVG: POSITION_NODE_AVERAGED,
    FIELD_KEY_TIME: POSITION_GLOBAL_HISTORY,
    FIELD_KEY_FREQUENCY: POSITION_GLOBAL_HISTORY,
}

_POST_FIELD_VARIABLES = {
    FIELD_KEY_S,
    FIELD_KEY_E,
    "SECTION",
    FIELD_KEY_S_IP,
    FIELD_KEY_E_IP,
    FIELD_KEY_S_REC,
    FIELD_KEY_E_REC,
    FIELD_KEY_S_AVG,
    FIELD_KEY_S_VM_IP,
    FIELD_KEY_S_PRINCIPAL_IP,
    FIELD_KEY_S_VM_REC,
    FIELD_KEY_S_PRINCIPAL_REC,
    FIELD_KEY_S_VM_AVG,
    FIELD_KEY_S_PRINCIPAL_AVG,
    FIELD_KEY_U_MAG,
}

_PROCEDURE_VARIABLES = {
    "static": {FIELD_KEY_U, FIELD_KEY_RF, FIELD_KEY_TIME} | _POST_FIELD_VARIABLES,
    "static_linear": {FIELD_KEY_U, FIELD_KEY_RF, FIELD_KEY_TIME} | _POST_FIELD_VARIABLES,
    "static_nonlinear": {FIELD_KEY_U, FIELD_KEY_RF, FIELD_KEY_TIME} | _POST_FIELD_VARIABLES,
    "dynamic": {FIELD_KEY_U, FIELD_KEY_TIME} | _POST_FIELD_VARIABLES,
    "implicit_dynamic": {FIELD_KEY_U, FIELD_KEY_TIME} | _POST_FIELD_VARIABLES,
    "modal": {FIELD_KEY_MODE_SHAPE, FIELD_KEY_FREQUENCY},
}

_NODE_TARGET_TYPES = {"model", "node", "node_set"}
_ELEMENT_TARGET_TYPES = {"model", "element", "element_set"}
_HISTORY_TARGET_TYPES = {"model"}
_DEFAULT_VARIABLES = {
    "static": ((FIELD_KEY_U, POSITION_NODE),),
    "static_linear": ((FIELD_KEY_U, POSITION_NODE),),
    "static_nonlinear": ((FIELD_KEY_U, POSITION_NODE),),
    "dynamic": ((FIELD_KEY_U, POSITION_NODE),),
    "implicit_dynamic": ((FIELD_KEY_U, POSITION_NODE),),
    "modal": ((FIELD_KEY_MODE_SHAPE, POSITION_NODE),),
}


@dataclass(slots=True, frozen=True)
class ResolvedOutputRequest:
    """描述单个变量级输出请求。"""

    request_name: str
    variable: str
    position: str
    frequency: int
    target_type: str
    target_name: str | None
    scope_name: str | None
    target_keys: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class OutputFieldPlan:
    """描述一个结果场在某一帧的合并输出计划。"""

    variable: str
    position: str
    request_names: tuple[str, ...]
    target_keys: tuple[str, ...]


class OutputRequestPlanner:
    """负责把 OutputRequest 解析为正式执行计划。"""

    def __init__(self, compiled_model: CompiledModel, step_definition: StepDef) -> None:
        """使用编译模型和步骤定义构建输出计划。"""

        self._compiled_model = compiled_model
        self._step_definition = step_definition
        self._resolved_requests = self._build_requests()

    def build_field_plans(self, frame_id: int) -> tuple[OutputFieldPlan, ...]:
        """构建指定帧需要写出的结果场计划。"""

        grouped: OrderedDict[tuple[str, str], dict[str, object]] = OrderedDict()
        for request in self._resolved_requests:
            if request.position == POSITION_GLOBAL_HISTORY or not self._is_active(request, frame_id):
                continue
            group = grouped.setdefault(
                (request.variable, request.position),
                {"request_names": [], "target_keys": []},
            )
            group["request_names"].append(request.request_name)
            group["target_keys"].extend(request.target_keys)

        plans: list[OutputFieldPlan] = []
        for (variable, position), payload in grouped.items():
            plans.append(
                OutputFieldPlan(
                    variable=variable,
                    position=position,
                    request_names=tuple(dict.fromkeys(payload["request_names"])),
                    target_keys=tuple(dict.fromkeys(payload["target_keys"])),
                )
            )
        return tuple(plans)

    def should_write_frame(self, frame_id: int) -> bool:
        """判断指定帧是否存在有效场输出请求。"""

        return bool(self.build_field_plans(frame_id))

    def requests_history_variable(self, variable: str) -> bool:
        """判断某个历史量变量是否被请求。"""

        normalized_variable = variable.upper()
        return any(
            request.variable == normalized_variable and request.position == POSITION_GLOBAL_HISTORY
            for request in self._resolved_requests
        )

    def should_collect_history(self, variable: str, frame_id: int) -> bool:
        """判断某个历史量变量是否应在指定帧采样。"""

        normalized_variable = variable.upper()
        return any(
            request.variable == normalized_variable
            and request.position == POSITION_GLOBAL_HISTORY
            and self._is_active(request, frame_id)
            for request in self._resolved_requests
        )

    def requested_variables(self) -> tuple[str, ...]:
        """返回步骤所有请求变量的去重列表。"""

        return tuple(dict.fromkeys(request.variable for request in self._resolved_requests))

    def _build_requests(self) -> tuple[ResolvedOutputRequest, ...]:
        if not self._step_definition.output_request_names:
            return self._build_default_requests()

        resolved_requests: list[ResolvedOutputRequest] = []
        for request_name in self._step_definition.output_request_names:
            request = self._compiled_model.model.output_requests[request_name]
            resolved_requests.extend(self._resolve_request(request))
        return tuple(resolved_requests)

    def _build_default_requests(self) -> tuple[ResolvedOutputRequest, ...]:
        defaults = _DEFAULT_VARIABLES.get(self._step_definition.procedure_type, ((FIELD_KEY_U, POSITION_NODE),))
        return tuple(
            ResolvedOutputRequest(
                request_name="__default__",
                variable=variable,
                position=position,
                frequency=1,
                target_type="model",
                target_name=None,
                scope_name=None,
                target_keys=self._resolve_target_keys(position=position, target_type="model", target_name=None, scope_name=None),
            )
            for variable, position in defaults
        )

    def _resolve_request(self, request: OutputRequest) -> tuple[ResolvedOutputRequest, ...]:
        if request.frequency <= 0:
            raise CompilationError(f"输出请求 {request.name} 的 frequency 必须大于零。")
        if not request.variables:
            raise CompilationError(f"输出请求 {request.name} 至少需要声明一个变量。")

        normalized_position = self._normalize_position(request.position)
        normalized_target_type = request.target_type.lower()
        resolved_requests: list[ResolvedOutputRequest] = []
        for raw_variable in request.variables:
            variable = raw_variable.upper()
            self._validate_variable(request_name=request.name, variable=variable, position=normalized_position)
            target_keys = self._resolve_target_keys(
                position=normalized_position,
                target_type=normalized_target_type,
                target_name=request.target_name,
                scope_name=request.scope_name,
            )
            resolved_requests.append(
                ResolvedOutputRequest(
                    request_name=request.name,
                    variable=variable,
                    position=normalized_position,
                    frequency=int(request.frequency),
                    target_type=normalized_target_type,
                    target_name=request.target_name,
                    scope_name=request.scope_name,
                    target_keys=target_keys,
                )
            )
        return tuple(resolved_requests)

    def _validate_variable(self, request_name: str, variable: str, position: str) -> None:
        supported_variables = _PROCEDURE_VARIABLES.get(self._step_definition.procedure_type)
        if supported_variables is None:
            raise CompilationError(
                f"步骤 {self._step_definition.name} 的 procedure_type {self._step_definition.procedure_type} 尚未定义输出能力。"
            )
        if variable not in supported_variables:
            raise CompilationError(
                f"步骤 {self._step_definition.name} 的过程类型 {self._step_definition.procedure_type} 暂不支持输出变量 {variable}。"
            )
        expected_position = _VARIABLE_POSITION.get(variable)
        if expected_position != position:
            raise CompilationError(
                f"输出请求 {request_name} 中变量 {variable} 只能写在位置 {expected_position}，不能写在 {position}。"
            )

    def _resolve_target_keys(
        self,
        *,
        position: str,
        target_type: str,
        target_name: str | None,
        scope_name: str | None,
    ) -> tuple[str, ...]:
        if position in {POSITION_NODE, POSITION_NODE_AVERAGED}:
            if target_type not in _NODE_TARGET_TYPES:
                raise CompilationError(f"节点类输出当前仅支持目标类型 {sorted(_NODE_TARGET_TYPES)}，收到 {target_type}。")
            return self._resolve_node_keys(target_type=target_type, target_name=target_name, scope_name=scope_name)
        if position in {POSITION_ELEMENT_CENTROID, POSITION_INTEGRATION_POINT, POSITION_ELEMENT_NODAL}:
            if target_type not in _ELEMENT_TARGET_TYPES:
                raise CompilationError(f"单元类输出当前仅支持目标类型 {sorted(_ELEMENT_TARGET_TYPES)}，收到 {target_type}。")
            return self._resolve_element_keys(target_type=target_type, target_name=target_name, scope_name=scope_name)
        if position == POSITION_GLOBAL_HISTORY:
            if target_type not in _HISTORY_TARGET_TYPES:
                raise CompilationError(f"历史量输出当前仅支持目标类型 {sorted(_HISTORY_TARGET_TYPES)}，收到 {target_type}。")
            if target_name is not None:
                raise CompilationError("历史量输出不允许声明 target_name。")
            if scope_name is not None:
                raise CompilationError("历史量输出当前不允许声明 scope_name。")
            return ()
        raise CompilationError(f"当前尚未实现输出位置 {position}。")

    def _resolve_node_keys(self, *, target_type: str, target_name: str | None, scope_name: str | None) -> tuple[str, ...]:
        scopes = self._compiled_model.model.iter_target_scopes(scope_name)
        if scope_name is not None and not scopes:
            raise CompilationError(f"输出请求引用了不存在的作用域 {scope_name}。")

        keys: list[str] = []
        for scope in scopes:
            if target_type == "model":
                keys.extend(scope.qualify_node_name(name) for name in scope.resolve_node_names("model"))
                continue
            if target_type == "node":
                if target_name is None:
                    raise CompilationError("节点输出请求缺少 target_name。")
                keys.extend(scope.qualify_node_name(name) for name in scope.resolve_node_names("node", target_name))
                continue
            if target_type == "node_set":
                if target_name is None:
                    raise CompilationError("节点集合输出请求缺少 target_name。")
                keys.extend(scope.qualify_node_name(name) for name in scope.resolve_node_names("node_set", target_name))
        if not keys:
            raise CompilationError(f"输出请求未解析到任何节点目标: {target_type}:{target_name}。")
        return tuple(dict.fromkeys(keys))

    def _resolve_element_keys(self, *, target_type: str, target_name: str | None, scope_name: str | None) -> tuple[str, ...]:
        scopes = self._compiled_model.model.iter_target_scopes(scope_name)
        if scope_name is not None and not scopes:
            raise CompilationError(f"输出请求引用了不存在的作用域 {scope_name}。")

        keys: list[str] = []
        for scope in scopes:
            if target_type == "model":
                keys.extend(scope.qualify_element_name(name) for name in scope.resolve_element_names("model"))
                continue
            if target_type == "element":
                if target_name is None:
                    raise CompilationError("单元输出请求缺少 target_name。")
                keys.extend(scope.qualify_element_name(name) for name in scope.resolve_element_names("element", target_name))
                continue
            if target_type == "element_set":
                if target_name is None:
                    raise CompilationError("单元集合输出请求缺少 target_name。")
                keys.extend(scope.qualify_element_name(name) for name in scope.resolve_element_names("element_set", target_name))
        if not keys:
            raise CompilationError(f"输出请求未解析到任何单元目标: {target_type}:{target_name}。")
        return tuple(dict.fromkeys(keys))

    def _normalize_position(self, raw_position: str) -> str:
        mapping = {
            "NODE": POSITION_NODE,
            "ELEMENT_CENTROID": POSITION_ELEMENT_CENTROID,
            "INTEGRATION_POINT": POSITION_INTEGRATION_POINT,
            "ELEMENT_NODAL": POSITION_ELEMENT_NODAL,
            "NODE_AVERAGED": POSITION_NODE_AVERAGED,
            "GLOBAL_HISTORY": POSITION_GLOBAL_HISTORY,
        }
        try:
            return mapping[raw_position.upper()]
        except KeyError as error:
            raise CompilationError(f"当前尚未实现输出位置 {raw_position}。") from error

    def _is_active(self, request: ResolvedOutputRequest, frame_id: int) -> bool:
        return frame_id % request.frequency == 0
