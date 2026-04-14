"""GUI 结果消费层的公共格式化与选择辅助。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pyfem.io import (
    FIELD_KEY_E,
    FIELD_KEY_E_IP,
    FIELD_KEY_E_REC,
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
    FIELD_KEY_U,
    FIELD_KEY_U_MAG,
    ResultField,
)
from pyfem.post import ResultFieldOverview, ResultsFacade

DISPLAY_MODE_AUTO = "auto"
DISPLAY_MODE_UNDEFORMED = "undeformed"
DISPLAY_MODE_DEFORMED = "deformed"
DISPLAY_MODE_CONTOUR_DEFORMED = "contour_deformed"

PROBE_KIND_NODE = "node"
PROBE_KIND_ELEMENT = "element"
PROBE_KIND_INTEGRATION_POINT = "integration_point"
PROBE_KIND_AVERAGED = "averaged"

DISPLACEMENT_FIELDS = {FIELD_KEY_U}
DISPLACEMENT_MAGNITUDE_FIELDS = {FIELD_KEY_U_MAG}
MODE_SHAPE_FIELDS = {FIELD_KEY_MODE_SHAPE}
STRESS_DIRECT_FIELDS = {FIELD_KEY_S, FIELD_KEY_S_IP, FIELD_KEY_S_REC, FIELD_KEY_S_AVG}
STRESS_VM_FIELDS = {FIELD_KEY_S_VM_IP, FIELD_KEY_S_VM_REC, FIELD_KEY_S_VM_AVG}
STRESS_PRINCIPAL_FIELDS = {FIELD_KEY_S_PRINCIPAL_IP, FIELD_KEY_S_PRINCIPAL_REC, FIELD_KEY_S_PRINCIPAL_AVG}
STRAIN_FIELDS = {FIELD_KEY_E, FIELD_KEY_E_IP, FIELD_KEY_E_REC}


@dataclass(slots=True, frozen=True)
class DisplayFieldChoice:
    """描述 GUI 当前应显示的正式结果场与分量。"""

    field_name: str
    component_name: str
    field: ResultField
    label: str
    unit_label: str


@dataclass(slots=True, frozen=True)
class ProbeCompatibility:
    """描述某一 probe 类型与当前选择的兼容字段。"""

    probe_kind: str
    field_name: str | None
    component_names: tuple[str, ...]
    target_keys: tuple[str, ...]
    message: str | None = None


@dataclass(slots=True, frozen=True)
class FieldFamilyDescriptor:
    """描述当前字段所属的 GUI 展示族。"""

    family: str
    position_kind: str


def format_field_label(overview: ResultFieldOverview) -> str:
    """为字段下拉框与树节点生成更有语义的标签。"""

    summary = f"{overview.field_name} [{overview.source_type} | {overview.position}]"
    if overview.target_count:
        summary += f" ({overview.target_count})"
    return summary


def summarize_field_metadata(metadata: Mapping[str, Any], *, limit: int = 4) -> str:
    """生成字段元数据摘要。"""

    if not metadata:
        return "-"
    items: list[str] = []
    for index, (key, value) in enumerate(metadata.items()):
        if index >= limit:
            items.append("...")
            break
        if isinstance(value, Mapping):
            items.append(f"{key}={len(value)}项")
        elif isinstance(value, (tuple, list)):
            items.append(f"{key}={len(value)}项")
        else:
            items.append(f"{key}={value}")
    return ", ".join(items) if items else "-"


def summarize_source_field_names(step_overview: Any) -> tuple[tuple[str, str], ...]:
    """将步骤概览中的分类字段名整理为便于 GUI 展示的分组。"""

    groups = (
        ("字段", tuple(getattr(step_overview, "field_names", ()) or ())),
        ("恢复场", tuple(getattr(step_overview, "recovered_field_names", ()) or ())),
        ("平均场", tuple(getattr(step_overview, "averaged_field_names", ()) or ())),
        ("派生场", tuple(getattr(step_overview, "derived_field_names", ()) or ())),
    )
    return tuple((label, ", ".join(names) if names else "-") for label, names in groups)


def build_component_choices(
    results_facade: ResultsFacade,
    step_name: str,
    frame_id: int,
    field_name: str | None,
) -> tuple[str, ...]:
    """根据当前正式字段生成 GUI component 选项。"""

    if field_name is None:
        return ()
    current_field = results_facade.field(step_name, frame_id, field_name)
    if current_field.component_names:
        return current_field.component_names
    return ()


def resolve_display_field_choice(
    results_facade: ResultsFacade,
    step_name: str,
    frame_id: int,
    field_name: str,
    component_name: str | None,
) -> DisplayFieldChoice:
    """根据当前正式字段与 component 选择解析真正用于显示的结果场。"""

    resolved_field = results_facade.field(step_name, frame_id, field_name)
    resolved_component_name = _resolve_display_component_name(resolved_field, component_name)
    return DisplayFieldChoice(
        field_name=field_name,
        component_name=resolved_component_name,
        field=resolved_field,
        label=_format_display_choice_label(field_name, resolved_component_name),
        unit_label=infer_unit_label(field_name, resolved_field.metadata),
    )


def resolve_probe_compatibility(
    results_facade: ResultsFacade,
    step_name: str,
    frame_id: int,
    field_name: str | None,
    probe_kind: str,
) -> ProbeCompatibility:
    """解析当前字段对某一 probe 类型的兼容字段与目标列表。"""

    if field_name is None:
        return ProbeCompatibility(probe_kind=probe_kind, field_name=None, component_names=(), target_keys=(), message="当前没有选中的结果场。")

    descriptor = describe_field_family(field_name)
    available = {overview.field_name: overview for overview in results_facade.fields(step_name=step_name, frame_id=frame_id)}
    resolved_field_name = _resolve_probe_field_name(
        descriptor.family,
        probe_kind=probe_kind,
        available_field_names=tuple(available.keys()),
    )
    if resolved_field_name is None or resolved_field_name not in available:
        return ProbeCompatibility(
            probe_kind=probe_kind,
            field_name=None,
            component_names=(),
            target_keys=(),
            message="当前字段与所选 probe 类型不兼容。",
        )

    overview = available[resolved_field_name]
    return ProbeCompatibility(
        probe_kind=probe_kind,
        field_name=resolved_field_name,
        component_names=overview.component_names,
        target_keys=overview.target_keys,
        message=None,
    )


def describe_field_family(field_name: str) -> FieldFamilyDescriptor:
    """描述字段所属的 GUI 展示族。"""

    if field_name in DISPLACEMENT_FIELDS:
        return FieldFamilyDescriptor(family="displacement", position_kind="node")
    if field_name in DISPLACEMENT_MAGNITUDE_FIELDS:
        return FieldFamilyDescriptor(family="displacement_magnitude", position_kind="node")
    if field_name in MODE_SHAPE_FIELDS:
        return FieldFamilyDescriptor(family="mode_shape", position_kind="node")
    if field_name in STRESS_DIRECT_FIELDS:
        if field_name == FIELD_KEY_S:
            return FieldFamilyDescriptor(family="stress", position_kind="element")
        if field_name == FIELD_KEY_S_IP:
            return FieldFamilyDescriptor(family="stress", position_kind="integration_point")
        if field_name == FIELD_KEY_S_REC:
            return FieldFamilyDescriptor(family="stress", position_kind="element_nodal")
        return FieldFamilyDescriptor(family="stress", position_kind="averaged")
    if field_name in STRESS_VM_FIELDS:
        if field_name == FIELD_KEY_S_VM_IP:
            return FieldFamilyDescriptor(family="von_mises_stress", position_kind="integration_point")
        if field_name == FIELD_KEY_S_VM_REC:
            return FieldFamilyDescriptor(family="von_mises_stress", position_kind="element_nodal")
        return FieldFamilyDescriptor(family="von_mises_stress", position_kind="averaged")
    if field_name in STRESS_PRINCIPAL_FIELDS:
        if field_name == FIELD_KEY_S_PRINCIPAL_IP:
            return FieldFamilyDescriptor(family="principal_stress", position_kind="integration_point")
        if field_name == FIELD_KEY_S_PRINCIPAL_REC:
            return FieldFamilyDescriptor(family="principal_stress", position_kind="element_nodal")
        return FieldFamilyDescriptor(family="principal_stress", position_kind="averaged")
    if field_name in STRAIN_FIELDS:
        if field_name == FIELD_KEY_E:
            return FieldFamilyDescriptor(family="strain", position_kind="element")
        if field_name == FIELD_KEY_E_IP:
            return FieldFamilyDescriptor(family="strain", position_kind="integration_point")
        if field_name == FIELD_KEY_E_REC:
            return FieldFamilyDescriptor(family="strain", position_kind="element_nodal")
        return FieldFamilyDescriptor(family="strain", position_kind="averaged")
    if field_name == FIELD_KEY_RF:
        return FieldFamilyDescriptor(family="reaction_force", position_kind="node")
    return FieldFamilyDescriptor(family="generic", position_kind="other")


def infer_unit_label(field_name: str, metadata: Mapping[str, Any] | None = None) -> str:
    """推断 GUI legend 中显示的单位标签。"""

    if metadata is not None and "unit" in metadata:
        return str(metadata["unit"])
    if field_name in {FIELD_KEY_U, FIELD_KEY_U_MAG, FIELD_KEY_MODE_SHAPE}:
        return "displacement"
    if field_name == FIELD_KEY_RF:
        return "force"
    if field_name in {FIELD_KEY_S, FIELD_KEY_S_IP, FIELD_KEY_S_REC, FIELD_KEY_S_AVG, FIELD_KEY_S_VM_IP, FIELD_KEY_S_VM_REC, FIELD_KEY_S_VM_AVG, FIELD_KEY_S_PRINCIPAL_IP, FIELD_KEY_S_PRINCIPAL_REC, FIELD_KEY_S_PRINCIPAL_AVG}:
        return "stress"
    if field_name in {FIELD_KEY_E, FIELD_KEY_E_IP, FIELD_KEY_E_REC}:
        return "strain"
    return "-"


def join_items(values: Iterable[object]) -> str:
    """将序列压平成逗号分隔字符串。"""

    items = [str(value) for value in values if str(value)]
    return ", ".join(items) if items else "-"


def extract_component_scalar(value: Any, component_name: str | None, component_names: tuple[str, ...] = ()) -> float:
    """按分量名称提取单个标量。"""

    is_scalar_request = component_name in {None, "", "VALUE"}
    if value is None:
        return float("nan")
    if isinstance(value, Mapping):
        candidate = None
        if not is_scalar_request:
            candidate = value.get(component_name)
        elif len(value) == 1:
            candidate = next(iter(value.values()))
        return float(candidate) if candidate is not None else float("nan")
    if isinstance(value, (int, float)):
        return float(value) if is_scalar_request else float("nan")
    if isinstance(value, (tuple, list)) and value:
        candidate = _extract_sequence_component(value, component_name, component_names)
        return float(candidate) if candidate is not None else float("nan")
    return float("nan")


def extract_vector_value(value: Any) -> tuple[float, float, float]:
    """提取节点矢量值。"""

    if isinstance(value, Mapping):
        return (
            float(value.get("UX", 0.0)),
            float(value.get("UY", 0.0)),
            float(value.get("UZ", 0.0)),
        )
    if isinstance(value, (tuple, list)):
        padded = tuple(float(item) for item in value) + (0.0, 0.0, 0.0)
        return padded[0], padded[1], padded[2]
    if isinstance(value, (int, float)):
        return float(value), 0.0, 0.0
    return 0.0, 0.0, 0.0


def _resolve_display_component_name(field: ResultField, component_name: str | None) -> str:
    if field.component_names:
        return str(component_name) if component_name else field.component_names[0]
    if component_name in {None, "", "VALUE"}:
        return ""
    return str(component_name)


def _format_display_choice_label(field_name: str, component_name: str) -> str:
    if not component_name:
        return field_name
    return f"{field_name} | {component_name}"


def _extract_sequence_component(
    value: tuple[Any, ...] | list[Any],
    component_name: str | None,
    component_names: tuple[str, ...],
) -> Any | None:
    if component_names:
        if component_name in {None, "", "VALUE"}:
            if len(component_names) != 1:
                return None
            component_index = 0
        else:
            try:
                component_index = component_names.index(str(component_name))
            except ValueError:
                return None
        if component_index >= len(value):
            return None
        return value[component_index]
    if component_name not in {None, "", "VALUE"} or len(value) != 1:
        return None
    return value[0]

def _resolve_probe_field_name(
    family: str,
    *,
    probe_kind: str,
    available_field_names: tuple[str, ...],
) -> str | None:
    available = set(available_field_names)
    family_probe_preferences: dict[str, dict[str, tuple[str, ...]]] = {
        "displacement": {PROBE_KIND_NODE: (FIELD_KEY_U,)},
        "displacement_magnitude": {PROBE_KIND_NODE: (FIELD_KEY_U_MAG,)},
        "mode_shape": {PROBE_KIND_NODE: (FIELD_KEY_MODE_SHAPE,)},
        "reaction_force": {PROBE_KIND_NODE: (FIELD_KEY_RF,)},
        "stress": {
            PROBE_KIND_ELEMENT: (FIELD_KEY_S,),
            PROBE_KIND_INTEGRATION_POINT: (FIELD_KEY_S_IP,),
            PROBE_KIND_AVERAGED: (FIELD_KEY_S_AVG,),
        },
        "strain": {
            PROBE_KIND_ELEMENT: (FIELD_KEY_E,),
            PROBE_KIND_INTEGRATION_POINT: (FIELD_KEY_E_IP,),
        },
        "von_mises_stress": {
            PROBE_KIND_INTEGRATION_POINT: (FIELD_KEY_S_VM_IP,),
            PROBE_KIND_AVERAGED: (FIELD_KEY_S_VM_AVG,),
        },
        "principal_stress": {
            PROBE_KIND_INTEGRATION_POINT: (FIELD_KEY_S_PRINCIPAL_IP,),
            PROBE_KIND_AVERAGED: (FIELD_KEY_S_PRINCIPAL_AVG,),
        },
    }
    for field_name in family_probe_preferences.get(family, {}).get(probe_kind, ()):
        if field_name in available:
            return field_name
    return None
