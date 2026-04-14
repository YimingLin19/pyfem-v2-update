"""结果消费层使用的正式概览对象。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pyfem.io import RESULT_SOURCE_RAW, ResultField


@dataclass(slots=True, frozen=True)
class ResultStepOverview:
    """定义供产品层消费的轻量步骤概览。"""

    step_name: str
    procedure_type: str | None
    frame_count: int
    history_count: int
    summary_count: int
    frame_ids: tuple[int, ...] = ()
    frame_kinds: tuple[str, ...] = ()
    axis_kinds: tuple[str, ...] = ()
    field_names: tuple[str, ...] = ()
    raw_field_names: tuple[str, ...] = ()
    recovered_field_names: tuple[str, ...] = ()
    averaged_field_names: tuple[str, ...] = ()
    derived_field_names: tuple[str, ...] = ()
    history_names: tuple[str, ...] = ()
    summary_names: tuple[str, ...] = ()
    target_keys: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ResultFrameOverview:
    """定义供产品层消费的结果帧概览。"""

    step_name: str
    frame_id: int
    time: float
    frame_kind: str
    axis_kind: str
    axis_value: float | int | None
    field_names: tuple[str, ...] = ()
    raw_field_names: tuple[str, ...] = ()
    recovered_field_names: tuple[str, ...] = ()
    averaged_field_names: tuple[str, ...] = ()
    derived_field_names: tuple[str, ...] = ()
    field_positions: tuple[str, ...] = ()
    field_source_types: tuple[str, ...] = ()
    target_keys: tuple[str, ...] = ()
    target_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ResultFieldOverview:
    """定义供产品层消费的结果场概览。"""

    step_name: str
    frame_id: int
    field_name: str
    position: str
    source_type: str = RESULT_SOURCE_RAW
    target_keys: tuple[str, ...] = ()
    target_count: int = 0
    component_names: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    min_value: float | None = None
    max_value: float | None = None


@dataclass(slots=True, frozen=True)
class ResultHistoryOverview:
    """定义供产品层消费的历史量概览。"""

    step_name: str
    history_name: str
    axis_kind: str
    axis_count: int
    position: str
    target_keys: tuple[str, ...] = ()
    target_count: int = 0
    paired_value_names: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ResultSummaryOverview:
    """定义供产品层浏览的步骤摘要概览。"""

    step_name: str
    summary_name: str
    data_keys: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


def build_result_field_overview(step_name: str, frame_id: int, field: ResultField) -> ResultFieldOverview:
    """从正式结果场构造轻量概览对象。"""

    min_value, max_value = calculate_field_value_range(field)
    return ResultFieldOverview(
        step_name=step_name,
        frame_id=frame_id,
        field_name=field.name,
        position=field.position,
        source_type=field.source_type,
        target_keys=field.target_keys,
        target_count=field.target_count,
        component_names=field.component_names,
        metadata=dict(field.metadata),
        min_value=min_value,
        max_value=max_value,
    )


def calculate_field_value_range(field: ResultField) -> tuple[float | None, float | None]:
    """统计结果场中全部数值分量的最小值与最大值。"""

    numbers = list(_iter_numeric_values(field.values))
    if not numbers:
        return None, None
    return min(numbers), max(numbers)


def _iter_numeric_values(value: Any) -> tuple[float, ...]:
    if isinstance(value, bool):
        return ()
    if isinstance(value, (int, float)):
        return (float(value),)
    if isinstance(value, dict):
        collected: list[float] = []
        for item in value.values():
            collected.extend(_iter_numeric_values(item))
        return tuple(collected)
    if isinstance(value, (list, tuple)):
        collected: list[float] = []
        for item in value:
            collected.extend(_iter_numeric_values(item))
        return tuple(collected)
    return ()
