"""正式结果读写接口与参考 ResultsDB 实现。"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pyfem.foundation.errors import PyFEMError

RESULTS_SCHEMA_VERSION = "2.0"
GLOBAL_HISTORY_TARGET = "__global__"
PAIRED_VALUE_KEY_EIGENVALUE = "EIGENVALUE"

FIELD_KEY_U = "U"
FIELD_KEY_U_MAG = "U_MAG"
FIELD_KEY_RF = "RF"
FIELD_KEY_S = "S"
FIELD_KEY_S_IP = "S_IP"
FIELD_KEY_S_REC = "S_REC"
FIELD_KEY_S_AVG = "S_AVG"
FIELD_KEY_S_VM_IP = "S_VM_IP"
FIELD_KEY_S_VM_REC = "S_VM_REC"
FIELD_KEY_S_VM_AVG = "S_VM_AVG"
FIELD_KEY_S_PRINCIPAL_IP = "S_PRINCIPAL_IP"
FIELD_KEY_S_PRINCIPAL_REC = "S_PRINCIPAL_REC"
FIELD_KEY_S_PRINCIPAL_AVG = "S_PRINCIPAL_AVG"
FIELD_KEY_E = "E"
FIELD_KEY_E_IP = "E_IP"
FIELD_KEY_E_REC = "E_REC"
FIELD_KEY_MODE_SHAPE = "MODE_SHAPE"
FIELD_KEY_FREQUENCY = "FREQUENCY"
FIELD_KEY_TIME = "TIME"

RECOVERY_METHOD_DIRECT_EXTRAPOLATION = "direct_extrapolation"
RECOVERY_METHOD_LEAST_SQUARES = "least_squares"
RECOVERY_METHOD_PATCH = "patch"

POSITION_NODE = "NODE"
POSITION_ELEMENT_CENTROID = "ELEMENT_CENTROID"
POSITION_INTEGRATION_POINT = "INTEGRATION_POINT"
POSITION_ELEMENT_NODAL = "ELEMENT_NODAL"
POSITION_NODE_AVERAGED = "NODE_AVERAGED"
POSITION_GLOBAL_HISTORY = "GLOBAL_HISTORY"

RESULT_FIELD_POSITIONS = (
    POSITION_NODE,
    POSITION_ELEMENT_CENTROID,
    POSITION_INTEGRATION_POINT,
    POSITION_ELEMENT_NODAL,
    POSITION_NODE_AVERAGED,
)
RESULT_POSITIONS = RESULT_FIELD_POSITIONS + (POSITION_GLOBAL_HISTORY,)

RESULT_SOURCE_RAW = "raw"
RESULT_SOURCE_RECOVERED = "recovered"
RESULT_SOURCE_AVERAGED = "averaged"
RESULT_SOURCE_DERIVED = "derived"
RESULT_SOURCE_TYPES = (
    RESULT_SOURCE_RAW,
    RESULT_SOURCE_RECOVERED,
    RESULT_SOURCE_AVERAGED,
    RESULT_SOURCE_DERIVED,
)

FRAME_KIND_SOLUTION = "SOLUTION"
FRAME_KIND_MODE = "MODE"

AXIS_KIND_TIME = "TIME"
AXIS_KIND_FRAME_ID = "FRAME_ID"
AXIS_KIND_MODE_INDEX = "MODE_INDEX"

MODAL_METADATA_KEY_MODE_INDEX = "mode_index"
MODAL_METADATA_KEY_FREQUENCY_HZ = "frequency_hz"
MODAL_METADATA_KEY_EIGENVALUE = "eigenvalue"


def normalize_result_position(position: str, *, allow_global_history: bool = True) -> str:
    """??????????"""

    normalized_position = str(position).strip().upper()
    allowed_positions = RESULT_POSITIONS if allow_global_history else RESULT_FIELD_POSITIONS
    if normalized_position not in allowed_positions:
        raise PyFEMError(f"?????????? {position}?")
    return normalized_position


def normalize_result_source_type(source_type: str) -> str:
    """??????????"""

    normalized_source_type = str(source_type).strip().lower()
    if normalized_source_type not in RESULT_SOURCE_TYPES:
        raise PyFEMError(f"?????????? {source_type}?")
    return normalized_source_type


def infer_result_component_names(values: Mapping[str, Any]) -> tuple[str, ...]:
    """????????????"""

    component_names: list[str] = []
    for target_value in values.values():
        if isinstance(target_value, Mapping):
            component_names.extend(str(component_name) for component_name in target_value.keys())
    return tuple(dict.fromkeys(component_names))


@dataclass(slots=True, frozen=True)
class ResultsCapabilities:
    """描述一个结果后端的能力边界。"""

    backend_name: str
    is_reference_implementation: bool
    supports_append: bool
    supports_partial_storage_read: bool
    supports_restart_metadata: bool


@dataclass(slots=True, frozen=True)
class ResultField:
    """??????????"""

    name: str
    position: str
    values: Mapping[str, Any]
    source_type: str = RESULT_SOURCE_RAW
    component_names: tuple[str, ...] = ()
    target_keys: tuple[str, ...] = ()
    target_count: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """??????????????"""

        normalized_position = normalize_result_position(self.position, allow_global_history=False)
        normalized_source_type = normalize_result_source_type(self.source_type)
        normalized_target_keys = (
            tuple(str(key) for key in self.target_keys)
            if self.target_keys
            else tuple(str(key) for key in self.values.keys())
        )
        value_target_keys = tuple(str(key) for key in self.values.keys())
        if value_target_keys:
            missing_value_targets = [key for key in value_target_keys if key not in normalized_target_keys]
            if missing_value_targets:
                raise PyFEMError(f"??? {self.name} ? target_keys ??? values ???? {missing_value_targets}?")

        normalized_target_count = len(normalized_target_keys) if self.target_count is None else int(self.target_count)
        if normalized_target_count < 0:
            raise PyFEMError(f"??? {self.name} ? target_count ??????")
        if normalized_target_count < len(normalized_target_keys):
            raise PyFEMError(f"??? {self.name} ? target_count ?? target_keys ???")

        component_names = (
            tuple(str(component_name) for component_name in self.component_names)
            if self.component_names
            else infer_result_component_names(self.values)
        )
        object.__setattr__(self, "position", normalized_position)
        object.__setattr__(self, "source_type", normalized_source_type)
        object.__setattr__(self, "component_names", component_names)
        object.__setattr__(self, "target_keys", normalized_target_keys)
        object.__setattr__(self, "target_count", normalized_target_count)

    @property
    def result_source(self) -> str:
        """????????????"""

        return self.source_type

    def resolve_component_names(self, target_keys: tuple[str, ...] | None = None) -> tuple[str, ...]:
        """??????????????????"""

        if target_keys is None or target_keys == self.target_keys:
            return self.component_names

        allowed_keys = {str(item) for item in target_keys}
        filtered_values = {key: value for key, value in self.values.items() if key in allowed_keys}
        filtered_component_names = infer_result_component_names(filtered_values)
        return self.component_names if not filtered_component_names else filtered_component_names

    def to_dict(self) -> dict[str, Any]:
        """???????????"""

        return {
            "name": self.name,
            "position": self.position,
            "values": _to_jsonable(self.values),
            "source_type": self.source_type,
            "component_names": _to_jsonable(self.component_names),
            "target_keys": _to_jsonable(self.target_keys),
            "target_count": self.target_count,
            "metadata": _to_jsonable(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResultField:
        """?????????"""

        values = _from_jsonable(payload.get("values", {}))
        raw_component_names = payload.get("component_names")
        component_names = (
            infer_result_component_names(values)
            if raw_component_names is None
            else tuple(str(item) for item in _from_jsonable(raw_component_names))
        )
        return cls(
            name=str(payload["name"]),
            position=str(payload["position"]),
            values=values,
            source_type=str(payload.get("source_type", payload.get("result_source", RESULT_SOURCE_RAW))),
            component_names=component_names,
            target_keys=tuple(str(item) for item in _from_jsonable(payload.get("target_keys", ()))),
            target_count=None if payload.get("target_count") is None else int(payload.get("target_count")),
            metadata=_from_jsonable(payload.get("metadata", {})),
        )


@dataclass(slots=True, frozen=True)
class ResultFrame:
    """????????"""

    frame_id: int
    step_name: str
    time: float
    fields: tuple[ResultField, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    frame_kind: str = FRAME_KIND_SOLUTION
    axis_kind: str = AXIS_KIND_TIME
    axis_value: float | int | None = None
    restart_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """???????"""

        if self.axis_value is None:
            default_axis_value: float | int = self.time if self.axis_kind == AXIS_KIND_TIME else self.frame_id
            object.__setattr__(self, "axis_value", default_axis_value)

    def get_field(self, field_name: str) -> ResultField:
        """?????????"""

        for result_field in self.fields:
            if result_field.name == field_name:
                return result_field
        raise PyFEMError(f"??? {self.step_name}:{self.frame_id} ??????? {field_name}?")

    @property
    def field_positions(self) -> tuple[str, ...]:
        """???????????????"""

        return tuple(dict.fromkeys(field.position for field in self.fields))

    @property
    def field_source_types(self) -> tuple[str, ...]:
        """???????????????"""

        return tuple(dict.fromkeys(field.source_type for field in self.fields))

    @property
    def target_keys(self) -> tuple[str, ...]:
        """??????????????"""

        collected_target_keys: list[str] = []
        for field in self.fields:
            collected_target_keys.extend(field.target_keys)
        return tuple(dict.fromkeys(collected_target_keys))

    @property
    def target_count(self) -> int:
        """??????????????"""

        return len(self.target_keys)

    def to_dict(self) -> dict[str, Any]:
        """???????????"""

        return {
            "frame_id": self.frame_id,
            "step_name": self.step_name,
            "time": self.time,
            "fields": [result_field.to_dict() for result_field in self.fields],
            "metadata": _to_jsonable(self.metadata),
            "frame_kind": self.frame_kind,
            "axis_kind": self.axis_kind,
            "axis_value": self.axis_value,
            "restart_metadata": _to_jsonable(self.restart_metadata),
            "field_positions": _to_jsonable(self.field_positions),
            "field_source_types": _to_jsonable(self.field_source_types),
            "target_keys": _to_jsonable(self.target_keys),
            "target_count": self.target_count,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResultFrame:
        """?????????"""

        return cls(
            frame_id=int(payload["frame_id"]),
            step_name=str(payload["step_name"]),
            time=float(payload.get("time", 0.0)),
            fields=tuple(ResultField.from_dict(item) for item in payload.get("fields", ())),
            metadata=_from_jsonable(payload.get("metadata", {})),
            frame_kind=str(payload.get("frame_kind", FRAME_KIND_SOLUTION)),
            axis_kind=str(payload.get("axis_kind", AXIS_KIND_TIME)),
            axis_value=payload.get("axis_value"),
            restart_metadata=_from_jsonable(payload.get("restart_metadata", {})),
        )


@dataclass(slots=True, frozen=True)
class ResultHistorySeries:
    """????????????"""

    name: str
    step_name: str
    axis_kind: str
    axis_values: tuple[float | int, ...]
    values: Mapping[str, tuple[Any, ...]]
    position: str = POSITION_GLOBAL_HISTORY
    metadata: Mapping[str, Any] = field(default_factory=dict)
    paired_values: Mapping[str, tuple[Any, ...]] = field(default_factory=dict)
    restart_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """?????????"""

        object.__setattr__(self, "position", normalize_result_position(self.position))
        axis_count = len(self.axis_values)
        for target_key, series in self.values.items():
            if len(series) != axis_count:
                raise PyFEMError(f"??? {self.name} ??? {target_key} ? axis_values ??????")
        for value_name, series in self.paired_values.items():
            if not str(value_name).strip():
                raise PyFEMError(f"??? {self.name} ? paired_values ???????")
            if len(series) != axis_count:
                raise PyFEMError(f"??? {self.name} ? paired_values[{value_name}] ? axis_values ??????")

    @property
    def target_keys(self) -> tuple[str, ...]:
        """???????????"""

        return tuple(self.values.keys())

    @property
    def target_count(self) -> int:
        """??????????"""

        return len(self.target_keys)

    def get_series(self, target_key: str | None = None) -> tuple[Any, ...]:
        """????????????"""

        resolved_target_key = GLOBAL_HISTORY_TARGET if target_key is None else target_key
        try:
            return self.values[resolved_target_key]
        except KeyError as error:
            raise PyFEMError(f"??? {self.name} ?????? {resolved_target_key}?") from error

    def get_paired_series(self, value_name: str) -> tuple[Any, ...]:
        """???????"""

        try:
            return self.paired_values[value_name]
        except KeyError as error:
            raise PyFEMError(f"??? {self.name} ???????? {value_name}?") from error

    def to_dict(self) -> dict[str, Any]:
        """?????????????"""

        return {
            "name": self.name,
            "step_name": self.step_name,
            "position": self.position,
            "axis_kind": self.axis_kind,
            "axis_values": _to_jsonable(self.axis_values),
            "values": _to_jsonable(self.values),
            "metadata": _to_jsonable(self.metadata),
            "paired_values": _to_jsonable(self.paired_values),
            "restart_metadata": _to_jsonable(self.restart_metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResultHistorySeries:
        """???????????"""

        return cls(
            name=str(payload["name"]),
            step_name=str(payload["step_name"]),
            position=str(payload.get("position", POSITION_GLOBAL_HISTORY)),
            axis_kind=str(payload.get("axis_kind", AXIS_KIND_FRAME_ID)),
            axis_values=tuple(_from_jsonable(payload.get("axis_values", ()))),
            values=_from_jsonable(payload.get("values", {})),
            metadata=_from_jsonable(payload.get("metadata", {})),
            paired_values=_from_jsonable(payload.get("paired_values", {})),
            restart_metadata=_from_jsonable(payload.get("restart_metadata", {})),
        )


ResultHistory = ResultHistorySeries


@dataclass(slots=True, frozen=True)
class ResultSummary:
    """定义一个步骤级摘要结果。"""

    name: str
    step_name: str
    data: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)
    restart_metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将摘要结果序列化为字典。"""

        return {
            "name": self.name,
            "step_name": self.step_name,
            "data": _to_jsonable(self.data),
            "metadata": _to_jsonable(self.metadata),
            "restart_metadata": _to_jsonable(self.restart_metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResultSummary:
        """从字典恢复摘要结果。"""

        return cls(
            name=str(payload["name"]),
            step_name=str(payload["step_name"]),
            data=_from_jsonable(payload.get("data", {})),
            metadata=_from_jsonable(payload.get("metadata", {})),
            restart_metadata=_from_jsonable(payload.get("restart_metadata", {})),
        )

@dataclass(slots=True, frozen=True)
class ResultStep:
    """定义一个结果步骤。"""

    name: str
    procedure_type: str | None = None
    step_index: int | None = None
    frames: tuple[ResultFrame, ...] = ()
    histories: tuple[ResultHistorySeries, ...] = ()
    summaries: tuple[ResultSummary, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    restart_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """校验步骤内部对象归属一致。"""

        frame_ids: set[int] = set()
        for result_frame in self.frames:
            if result_frame.step_name != self.name:
                raise PyFEMError(f"结果帧 {result_frame.frame_id} 的 step_name 与步骤 {self.name} 不一致。")
            if result_frame.frame_id in frame_ids:
                raise PyFEMError(f"步骤 {self.name} 中存在重复的 frame_id {result_frame.frame_id}。")
            frame_ids.add(result_frame.frame_id)
        for history in self.histories:
            if history.step_name != self.name:
                raise PyFEMError(f"历史量 {history.name} 的 step_name 与步骤 {self.name} 不一致。")
        for summary in self.summaries:
            if summary.step_name != self.name:
                raise PyFEMError(f"摘要 {summary.name} 的 step_name 与步骤 {self.name} 不一致。")

    def get_frame(self, frame_id: int) -> ResultFrame:
        """按编号获取结果帧。"""

        for result_frame in self.frames:
            if result_frame.frame_id == frame_id:
                return result_frame
        raise PyFEMError(f"步骤 {self.name} 中不存在帧 {frame_id}。")

    def get_field(self, frame_id: int, field_name: str) -> ResultField:
        """获取步骤内指定帧的结果场。"""

        return self.get_frame(frame_id).get_field(field_name)

    def get_history(self, history_name: str) -> ResultHistorySeries:
        """按名称获取历史量序列。"""

        for history in self.histories:
            if history.name == history_name:
                return history
        raise PyFEMError(f"步骤 {self.name} 中不存在历史量 {history_name}。")

    def get_summary(self, summary_name: str) -> ResultSummary:
        """按名称获取步骤摘要。"""

        for summary in self.summaries:
            if summary.name == summary_name:
                return summary
        raise PyFEMError(f"步骤 {self.name} 中不存在摘要 {summary_name}。")

    def to_dict(self) -> dict[str, Any]:
        """将结果步骤序列化为字典。"""

        return {
            "name": self.name,
            "procedure_type": self.procedure_type,
            "step_index": self.step_index,
            "frames": [result_frame.to_dict() for result_frame in self.frames],
            "histories": [history.to_dict() for history in self.histories],
            "summaries": [summary.to_dict() for summary in self.summaries],
            "metadata": _to_jsonable(self.metadata),
            "restart_metadata": _to_jsonable(self.restart_metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResultStep:
        """从字典恢复结果步骤。"""

        return cls(
            name=str(payload["name"]),
            procedure_type=None if payload.get("procedure_type") is None else str(payload.get("procedure_type")),
            step_index=None if payload.get("step_index") is None else int(payload.get("step_index")),
            frames=tuple(ResultFrame.from_dict(item) for item in payload.get("frames", ())),
            histories=tuple(ResultHistorySeries.from_dict(item) for item in payload.get("histories", ())),
            summaries=tuple(ResultSummary.from_dict(item) for item in payload.get("summaries", ())),
            metadata=_from_jsonable(payload.get("metadata", {})),
            restart_metadata=_from_jsonable(payload.get("restart_metadata", {})),
        )


@dataclass(slots=True, frozen=True)
class ResultsSession:
    """定义一次结果写出会话。"""

    model_name: str
    procedure_name: str | None = None
    job_name: str | None = None
    step_name: str | None = None
    procedure_type: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    database_id: str = field(default_factory=lambda: uuid4().hex)
    schema_version: str = RESULTS_SCHEMA_VERSION
    writer_backend: str = "unknown"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    restart_lineage: tuple[str, ...] = ()
    restart_metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将结果会话序列化为字典。"""

        return {
            "model_name": self.model_name,
            "procedure_name": self.procedure_name,
            "job_name": self.job_name,
            "step_name": self.step_name,
            "procedure_type": self.procedure_type,
            "metadata": _to_jsonable(self.metadata),
            "database_id": self.database_id,
            "schema_version": self.schema_version,
            "writer_backend": self.writer_backend,
            "created_at": self.created_at,
            "restart_lineage": _to_jsonable(self.restart_lineage),
            "restart_metadata": _to_jsonable(self.restart_metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResultsSession:
        """从字典恢复结果会话。"""

        return cls(
            model_name=str(payload["model_name"]),
            procedure_name=None if payload.get("procedure_name") is None else str(payload.get("procedure_name")),
            job_name=None if payload.get("job_name") is None else str(payload.get("job_name")),
            step_name=None if payload.get("step_name") is None else str(payload.get("step_name")),
            procedure_type=None if payload.get("procedure_type") is None else str(payload.get("procedure_type")),
            metadata=_from_jsonable(payload.get("metadata", {})),
            database_id=str(payload.get("database_id", uuid4().hex)),
            schema_version=str(payload.get("schema_version", RESULTS_SCHEMA_VERSION)),
            writer_backend=str(payload.get("writer_backend", "unknown")),
            created_at=str(payload.get("created_at", datetime.now(timezone.utc).isoformat())),
            restart_lineage=tuple(_from_jsonable(payload.get("restart_lineage", ()))),
            restart_metadata=_from_jsonable(payload.get("restart_metadata", {})),
        )


@dataclass(slots=True, frozen=True)
class ResultsDatabase:
    """定义逻辑 ResultsDB 的正式层级。"""

    session: ResultsSession
    steps: tuple[ResultStep, ...] = ()
    schema_version: str = RESULTS_SCHEMA_VERSION
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """校验结果数据库层级。"""

        step_names: set[str] = set()
        for result_step in self.steps:
            if result_step.name in step_names:
                raise PyFEMError(f"结果数据库中存在重复步骤名 {result_step.name}。")
            step_names.add(result_step.name)

    @property
    def is_multi_step(self) -> bool:
        """返回结果数据库是否包含多个正式步骤。"""

        return len(self.steps) > 1

    @property
    def frames(self) -> tuple[ResultFrame, ...]:
        """返回全部帧的扁平视图。"""

        return tuple(result_frame for result_step in self.steps for result_frame in result_step.frames)

    @property
    def histories(self) -> tuple[ResultHistorySeries, ...]:
        """返回全部历史量的扁平视图。"""

        return tuple(history for result_step in self.steps for history in result_step.histories)

    @property
    def summaries(self) -> tuple[ResultSummary, ...]:
        """返回全部摘要的扁平视图。"""

        return tuple(summary for result_step in self.steps for summary in result_step.summaries)

    def list_steps(self) -> tuple[str, ...]:
        """返回步骤名称列表。"""

        return tuple(result_step.name for result_step in self.steps)

    def get_step(self, step_name: str) -> ResultStep:
        """按名称获取结果步骤。"""

        for result_step in self.steps:
            if result_step.name == step_name:
                return result_step
        raise PyFEMError(f"结果数据库中不存在步骤 {step_name}。")

    def find_frame(self, step_name: str, frame_id: int) -> ResultFrame:
        """按步骤名和帧号查找结果帧。"""

        return self.get_step(step_name).get_frame(frame_id)

    def to_dict(self) -> dict[str, Any]:
        """将结果数据库序列化为字典。"""

        return {
            "schema_version": self.schema_version,
            "session": self.session.to_dict(),
            "steps": [result_step.to_dict() for result_step in self.steps],
            "metadata": _to_jsonable(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResultsDatabase:
        """从字典恢复结果数据库。"""

        schema_version = str(payload.get("schema_version", RESULTS_SCHEMA_VERSION))
        if _schema_major(schema_version) != _schema_major(RESULTS_SCHEMA_VERSION):
            raise PyFEMError(
                f"结果数据库 schema_version={schema_version} 与当前支持的 {RESULTS_SCHEMA_VERSION} 不兼容。"
            )
        if "steps" not in payload:
            return _load_legacy_database_payload(payload, schema_version=schema_version)
        return cls(
            session=ResultsSession.from_dict(payload["session"]),
            steps=tuple(ResultStep.from_dict(item) for item in payload.get("steps", ())),
            schema_version=schema_version,
            metadata=_from_jsonable(payload.get("metadata", {})),
        )


class ResultsWriter(ABC):
    """定义正式结果写出接口。"""

    @abstractmethod
    def open_session(self, session: ResultsSession) -> None:
        """开启一个步骤结果写出会话。"""

    @abstractmethod
    def close_session(self) -> None:
        """关闭当前步骤结果写出会话。"""

    @abstractmethod
    def write_frame(self, frame: ResultFrame) -> None:
        """写入一个结果帧。"""

    @abstractmethod
    def write_history_series(self, history: ResultHistorySeries) -> None:
        """写入一个历史量序列。"""

    def write_history(self, history: ResultHistorySeries) -> None:
        """兼容旧调用名，内部仍写入正式历史量序列。"""

        self.write_history_series(history)

    @abstractmethod
    def write_summary(self, summary: ResultSummary) -> None:
        """写入一个步骤摘要。"""

    @abstractmethod
    def get_capabilities(self) -> ResultsCapabilities:
        """返回结果写出后端能力边界。"""


class ResultsReader(ABC):
    """定义正式结果读取接口。"""

    @abstractmethod
    def read_database(self) -> ResultsDatabase:
        """读取完整结果数据库。"""

    @abstractmethod
    def get_capabilities(self) -> ResultsCapabilities:
        """返回结果读取后端能力边界。"""

    def read_session(self) -> ResultsSession:
        """读取结果会话。"""

        return self.read_database().session

    def is_multi_step(self) -> bool:
        """返回当前结果数据库是否包含多个正式步骤。"""

        return self.read_database().is_multi_step

    def list_steps(self) -> tuple[str, ...]:
        """列出结果数据库中的步骤。"""

        return self.read_database().list_steps()

    def read_step(self, step_name: str) -> ResultStep:
        """读取单个结果步骤。"""

        return self.read_database().get_step(step_name)

    def read_frames(self, step_name: str | None = None) -> tuple[ResultFrame, ...]:
        """读取步骤帧，未指定步骤时返回全部帧。"""

        database = self.read_database()
        if step_name is None:
            return database.frames
        return database.get_step(step_name).frames

    def read_frame(self, step_name: str, frame_id: int) -> ResultFrame:
        """读取指定步骤帧。"""

        return self.read_database().find_frame(step_name, frame_id)

    def find_frame(self, step_name: str, frame_id: int) -> ResultFrame:
        """兼容旧调用名，按步骤名和帧号查找结果帧。"""

        return self.read_frame(step_name, frame_id)

    def read_field(self, step_name: str, frame_id: int, field_name: str) -> ResultField:
        """读取指定步骤帧中的结果场。"""

        return self.read_frame(step_name, frame_id).get_field(field_name)

    def read_histories(
        self,
        step_name: str | None = None,
        history_name: str | None = None,
    ) -> tuple[ResultHistorySeries, ...]:
        """读取历史量序列。"""

        database = self.read_database()
        histories = database.histories if step_name is None else database.get_step(step_name).histories
        if history_name is None:
            return histories
        return tuple(history for history in histories if history.name == history_name)

    def read_history(self, step_name: str, history_name: str) -> ResultHistorySeries:
        """读取单个历史量序列。"""

        return self.read_step(step_name).get_history(history_name)

    def read_summaries(
        self,
        step_name: str | None = None,
        summary_name: str | None = None,
    ) -> tuple[ResultSummary, ...]:
        """读取步骤摘要。"""

        database = self.read_database()
        summaries = database.summaries if step_name is None else database.get_step(step_name).summaries
        if summary_name is None:
            return summaries
        return tuple(summary for summary in summaries if summary.name == summary_name)

    def read_summary(self, step_name: str, summary_name: str) -> ResultSummary:
        """读取单个步骤摘要。"""

        return self.read_step(step_name).get_summary(summary_name)

@dataclass(slots=True)
class _MutableStepBuffer:
    """定义写出阶段的可变步骤缓冲区。"""

    name: str
    procedure_type: str | None
    step_index: int
    metadata: dict[str, Any] = field(default_factory=dict)
    restart_metadata: dict[str, Any] = field(default_factory=dict)
    frames: list[ResultFrame] = field(default_factory=list)
    histories: list[ResultHistorySeries] = field(default_factory=list)
    summaries: list[ResultSummary] = field(default_factory=list)

    def freeze(self) -> ResultStep:
        """冻结为不可变结果步骤。"""

        return ResultStep(
            name=self.name,
            procedure_type=self.procedure_type,
            step_index=self.step_index,
            frames=tuple(self.frames),
            histories=tuple(self.histories),
            summaries=tuple(self.summaries),
            metadata=dict(self.metadata),
            restart_metadata=dict(self.restart_metadata),
        )


class InMemoryResultsWriter(ResultsWriter, ResultsReader):
    """基于内存的参考结果后端。"""

    def __init__(self) -> None:
        self._root_session: ResultsSession | None = None
        self._active_step_name: str | None = None
        self._step_buffers: OrderedDict[str, _MutableStepBuffer] = OrderedDict()

    @property
    def frames(self) -> tuple[ResultFrame, ...]:
        """返回全部帧的扁平视图。"""

        return self.read_database().frames

    @property
    def histories(self) -> tuple[ResultHistorySeries, ...]:
        """返回全部历史量的扁平视图。"""

        return self.read_database().histories

    @property
    def summaries(self) -> tuple[ResultSummary, ...]:
        """返回全部摘要的扁平视图。"""

        return self.read_database().summaries

    def open_session(self, session: ResultsSession) -> None:
        """开启一个步骤结果写出会话。"""

        if self._active_step_name is not None:
            raise PyFEMError(f"结果写出会话 {self._active_step_name} 尚未关闭。")
        if not session.step_name:
            raise PyFEMError("ResultsSession.step_name 不能为空。")

        if self._root_session is None:
            self._root_session = ResultsSession(
                model_name=session.model_name,
                procedure_name=session.procedure_name,
                job_name=session.job_name,
                step_name=session.step_name,
                procedure_type=session.procedure_type,
                metadata=dict(session.metadata),
                database_id=session.database_id,
                schema_version=RESULTS_SCHEMA_VERSION,
                writer_backend=self.get_capabilities().backend_name,
                created_at=session.created_at,
                restart_lineage=tuple(session.restart_lineage),
                restart_metadata=dict(session.restart_metadata),
            )
        else:
            self._validate_session_compatibility(session)

        if session.step_name in self._step_buffers:
            raise PyFEMError(f"结果数据库中不允许重复步骤名 {session.step_name}。")
        if self._step_buffers:
            self._root_session = self._build_multistep_root_session()
        self._step_buffers[session.step_name] = _MutableStepBuffer(
            name=session.step_name,
            procedure_type=session.procedure_type,
            step_index=len(self._step_buffers),
            metadata=dict(session.metadata),
            restart_metadata=dict(session.restart_metadata),
        )
        self._active_step_name = session.step_name

    def close_session(self) -> None:
        """关闭当前步骤结果写出会话。"""

        if self._active_step_name is None:
            return
        self._active_step_name = None

    def write_frame(self, frame: ResultFrame) -> None:
        """写入一个结果帧。"""

        step_buffer = self._require_active_step_buffer(expected_step_name=frame.step_name)
        step_buffer.frames.append(frame)

    def write_history_series(self, history: ResultHistorySeries) -> None:
        """写入一个历史量序列。"""

        step_buffer = self._require_active_step_buffer(expected_step_name=history.step_name)
        step_buffer.histories.append(history)

    def write_summary(self, summary: ResultSummary) -> None:
        """写入一个步骤摘要。"""

        step_buffer = self._require_active_step_buffer(expected_step_name=summary.step_name)
        step_buffer.summaries.append(summary)

    def get_capabilities(self) -> ResultsCapabilities:
        """返回内存参考后端能力。"""

        return ResultsCapabilities(
            backend_name="memory_reference",
            is_reference_implementation=True,
            supports_append=False,
            supports_partial_storage_read=False,
            supports_restart_metadata=True,
        )

    def read_database(self) -> ResultsDatabase:
        """读取当前内存中的完整结果数据库。"""

        if self._root_session is None:
            raise PyFEMError("当前结果写出器尚未生成任何结果会话。")
        return ResultsDatabase(
            session=self._root_session,
            steps=tuple(step_buffer.freeze() for step_buffer in self._step_buffers.values()),
            schema_version=RESULTS_SCHEMA_VERSION,
            metadata={"capabilities": self.get_capabilities().backend_name},
        )

    def _validate_session_compatibility(self, session: ResultsSession) -> None:
        if self._root_session is None:
            return
        if session.model_name != self._root_session.model_name:
            raise PyFEMError("同一个 ResultsWriter 不允许混写多个 model_name。")
        if session.job_name != self._root_session.job_name:
            raise PyFEMError("同一个 ResultsWriter 不允许混写多个 job_name。")

    def _build_multistep_root_session(self) -> ResultsSession:
        if self._root_session is None:
            raise PyFEMError("多步结果会话需要已存在的根会话。")
        metadata = {
            key: value
            for key, value in self._root_session.metadata.items()
            if key not in {"step_parameters", "output_request_names"}
        }
        metadata["multi_step"] = True
        return ResultsSession(
            model_name=self._root_session.model_name,
            procedure_name=None,
            job_name=self._root_session.job_name,
            step_name=None,
            procedure_type=None,
            metadata=metadata,
            database_id=self._root_session.database_id,
            schema_version=self._root_session.schema_version,
            writer_backend=self._root_session.writer_backend,
            created_at=self._root_session.created_at,
            restart_lineage=self._root_session.restart_lineage,
            restart_metadata=dict(self._root_session.restart_metadata),
        )

    def _require_active_step_buffer(self, expected_step_name: str) -> _MutableStepBuffer:
        if self._active_step_name is None:
            raise PyFEMError("当前没有处于打开状态的结果会话。")
        if expected_step_name != self._active_step_name:
            raise PyFEMError(
                f"当前活动结果会话为 {self._active_step_name}，但收到属于 {expected_step_name} 的结果对象。"
            )
        return self._step_buffers[self._active_step_name]


class JsonResultsWriter(InMemoryResultsWriter):
    """基于 JSON 文件的参考结果写出器。"""

    def __init__(self, path: str | Path) -> None:
        super().__init__()
        self._path = Path(path)

    def close_session(self) -> None:
        """关闭当前步骤会话并将结果落盘。"""

        super().close_session()
        if self._root_session is None:
            return
        payload = self.read_database().to_dict()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_capabilities(self) -> ResultsCapabilities:
        """返回 JSON 参考后端能力。"""

        return ResultsCapabilities(
            backend_name="json_reference",
            is_reference_implementation=True,
            supports_append=False,
            supports_partial_storage_read=False,
            supports_restart_metadata=True,
        )


class JsonResultsReader(ResultsReader):
    """基于 JSON 文件的参考结果读取器。"""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def read_database(self) -> ResultsDatabase:
        """读取 JSON 结果数据库。"""

        payload = json.loads(self._path.read_text(encoding="utf-8"))
        return ResultsDatabase.from_dict(payload)

    def get_capabilities(self) -> ResultsCapabilities:
        """返回 JSON 参考后端能力。"""

        return ResultsCapabilities(
            backend_name="json_reference",
            is_reference_implementation=True,
            supports_append=False,
            supports_partial_storage_read=False,
            supports_restart_metadata=True,
        )


def _schema_major(schema_version: str) -> str:
    """提取 schema major 版本号。"""

    return str(schema_version).split(".", maxsplit=1)[0]


def _load_legacy_database_payload(payload: Mapping[str, Any], *, schema_version: str) -> ResultsDatabase:
    """兼容读取旧版扁平 results payload。"""

    session = ResultsSession.from_dict(payload["session"])
    step_name = session.step_name or session.procedure_name or "step-1"
    frames = tuple(ResultFrame.from_dict(item) for item in payload.get("frames", ()))
    histories: list[ResultHistorySeries] = []
    summaries: list[ResultSummary] = []
    for item in payload.get("histories", ()):
        if "data" not in item:
            histories.append(ResultHistorySeries.from_dict(item))
            continue
        name = str(item["name"])
        data = _from_jsonable(item.get("data", {}))
        position = normalize_result_position(str(item.get("position", POSITION_GLOBAL_HISTORY)))
        if isinstance(data, Mapping) and "frequencies_hz" in data:
            frequencies = tuple(data["frequencies_hz"])
            eigenvalues = tuple(data.get("eigenvalues", ()))
            if eigenvalues and len(eigenvalues) != len(frequencies):
                raise PyFEMError(f"旧版历史量 {name} 的 eigenvalues 与 frequencies_hz 长度不一致。")
            histories.append(
                ResultHistorySeries(
                    name=name,
                    step_name=step_name,
                    axis_kind=AXIS_KIND_MODE_INDEX,
                    axis_values=tuple(range(len(frequencies))),
                    values={GLOBAL_HISTORY_TARGET: frequencies},
                    position=position,
                    paired_values={} if not eigenvalues else {PAIRED_VALUE_KEY_EIGENVALUE: eigenvalues},
                )
            )
            continue
        if isinstance(data, Mapping) and "values" in data:
            axis_values = tuple(range(len(tuple(data["values"]))))
            histories.append(
                ResultHistorySeries(
                    name=name,
                    step_name=step_name,
                    axis_kind=AXIS_KIND_FRAME_ID,
                    axis_values=axis_values,
                    values={GLOBAL_HISTORY_TARGET: tuple(data["values"])},
                    position=position,
                )
            )
            continue
        summaries.append(ResultSummary(name=name, step_name=step_name, data=data))

    step = ResultStep(
        name=step_name,
        procedure_type=session.procedure_type,
        step_index=0,
        frames=frames,
        histories=tuple(histories),
        summaries=tuple(summaries),
        metadata=dict(session.metadata),
        restart_metadata=dict(session.restart_metadata),
    )
    return ResultsDatabase(session=session, steps=(step,), schema_version=schema_version, metadata=_from_jsonable(payload.get("metadata", {})))


def _to_jsonable(value: Any) -> Any:
    """将 Python 数据递归转换为 JSON 友好结构。"""

    if isinstance(value, Mapping):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    return value


def _from_jsonable(value: Any) -> Any:
    """将 JSON 数据递归恢复为内部常用结构。"""

    if isinstance(value, dict):
        return {str(key): _from_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return tuple(_from_jsonable(item) for item in value)
    return value









