"""后处理层的公共常量与元数据辅助函数。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy

from pyfem.foundation.errors import PyFEMError
from pyfem.io import (
    POSITION_ELEMENT_CENTROID,
    POSITION_ELEMENT_NODAL,
    POSITION_INTEGRATION_POINT,
    POSITION_NODE,
    POSITION_NODE_AVERAGED,
    ResultField,
)

FIELD_METADATA_KEY_OWNER_ELEMENT_KEYS = "owner_element_keys"
FIELD_METADATA_KEY_BASE_TARGET_KEYS = "base_target_keys"
FIELD_METADATA_KEY_NATURAL_COORDINATES = "natural_coordinates"
FIELD_METADATA_KEY_SAMPLE_WEIGHTS = "sample_weights"
FIELD_METADATA_KEY_SECTION_POINT_LABELS = "section_point_labels"
FIELD_METADATA_KEY_RECOVERY_METHOD = "recovery_method"
FIELD_METADATA_KEY_RECOVERY_SOURCE_FIELD = "recovery_source_field"
FIELD_METADATA_KEY_AVERAGING_DOMAINS = "averaging_domains"
FIELD_METADATA_KEY_AVERAGING_WEIGHTS = "averaging_weights"
FIELD_METADATA_KEY_DERIVED_FROM = "derived_from"
FIELD_METADATA_KEY_SECTION_NODAL_SEMANTICS = "section_nodal_semantics"
FIELD_METADATA_KEY_AVERAGING_GROUPS = "averaging_groups"
FIELD_METADATA_KEY_STRAIN_MEASURE = "strain_measure"
FIELD_METADATA_KEY_STRESS_MEASURE = "stress_measure"
FIELD_METADATA_KEY_TANGENT_MEASURE = "tangent_measure"
FIELD_METADATA_KEY_STRAIN_MEASURES = "strain_measures"
FIELD_METADATA_KEY_STRESS_MEASURES = "stress_measures"
FIELD_METADATA_KEY_TANGENT_MEASURES = "tangent_measures"
FIELD_METADATA_KEY_KINEMATIC_REGIME = "kinematic_regime"
FIELD_METADATA_KEY_KINEMATIC_REGIMES = "kinematic_regimes"

MEASURE_VALUE_UNSPECIFIED = "unspecified"
MEASURE_VALUE_MIXED = "mixed"
KINEMATIC_REGIME_SMALL_STRAIN = "small_strain"
KINEMATIC_REGIME_FINITE_STRAIN = "finite_strain"

STRAIN_COMPONENT_NAMES = {
    "C3D8": ("E11", "E22", "E33", "E12", "E23", "E13"),
    "CPS4": ("E11", "E22", "E12"),
    "B21": ("E11",),
}
STRESS_COMPONENT_NAMES = {
    "C3D8": ("S11", "S22", "S33", "S12", "S23", "S13"),
    "CPS4": ("S11", "S22", "S12"),
    "B21": ("S11",),
}
PRINCIPAL_COMPONENT_NAMES = ("P1", "P2", "P3")
TARGET_KEY_METADATA_KEYS = {
    FIELD_METADATA_KEY_OWNER_ELEMENT_KEYS,
    FIELD_METADATA_KEY_BASE_TARGET_KEYS,
    FIELD_METADATA_KEY_NATURAL_COORDINATES,
    FIELD_METADATA_KEY_SAMPLE_WEIGHTS,
    FIELD_METADATA_KEY_SECTION_POINT_LABELS,
    FIELD_METADATA_KEY_AVERAGING_DOMAINS,
    FIELD_METADATA_KEY_AVERAGING_WEIGHTS,
    FIELD_METADATA_KEY_AVERAGING_GROUPS,
    FIELD_METADATA_KEY_SECTION_NODAL_SEMANTICS,
    FIELD_METADATA_KEY_STRAIN_MEASURES,
    FIELD_METADATA_KEY_STRESS_MEASURES,
    FIELD_METADATA_KEY_TANGENT_MEASURES,
    FIELD_METADATA_KEY_KINEMATIC_REGIMES,
}

_MEASURE_TO_KINEMATIC_REGIME = {
    "small_strain": KINEMATIC_REGIME_SMALL_STRAIN,
    "cauchy_small_strain": KINEMATIC_REGIME_SMALL_STRAIN,
    "d_cauchy_small_strain_d_small_strain": KINEMATIC_REGIME_SMALL_STRAIN,
    "green_lagrange": KINEMATIC_REGIME_FINITE_STRAIN,
    "second_piola_kirchhoff": KINEMATIC_REGIME_FINITE_STRAIN,
    "d_second_piola_kirchhoff_d_green_lagrange": KINEMATIC_REGIME_FINITE_STRAIN,
}


def resolve_strain_component_names(type_key: str) -> tuple[str, ...]:
    """返回指定单元类型的应变分量名称。"""

    try:
        return STRAIN_COMPONENT_NAMES[type_key]
    except KeyError as error:
        raise PyFEMError(f"未定义单元类型 {type_key} 的应变分量名称。") from error


def resolve_stress_component_names(type_key: str) -> tuple[str, ...]:
    """返回指定单元类型的应力分量名称。"""

    try:
        return STRESS_COMPONENT_NAMES[type_key]
    except KeyError as error:
        raise PyFEMError(f"未定义单元类型 {type_key} 的应力分量名称。") from error


def merge_component_names(*groups: Sequence[str]) -> tuple[str, ...]:
    """按首次出现顺序合并多个分量名称序列。"""

    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for component_name in group:
            normalized_name = str(component_name)
            if normalized_name in seen:
                continue
            seen.add(normalized_name)
            merged.append(normalized_name)
    return tuple(merged)


def build_component_mapping(values: Sequence[float], component_names: Sequence[str]) -> dict[str, float]:
    """将分量向量转换为名称到数值的映射。"""

    array = numpy.asarray(tuple(values), dtype=float)
    normalized_component_names = tuple(str(name) for name in component_names)
    if array.size != len(normalized_component_names):
        raise PyFEMError(
            f"分量数量 {array.size} 与 component_names={normalized_component_names} 不一致。"
        )
    return {
        normalized_component_names[index]: float(array[index])
        for index in range(array.size)
    }


def extract_component_vector(
    value: Mapping[str, Any] | Sequence[float] | float | int,
    component_names: Sequence[str],
) -> numpy.ndarray:
    """从字段值中提取与分量名称一致的数值向量。"""

    normalized_component_names = tuple(str(name) for name in component_names)
    if isinstance(value, Mapping):
        return numpy.asarray(
            [float(value.get(component_name, 0.0)) for component_name in normalized_component_names],
            dtype=float,
        )
    if isinstance(value, (int, float)):
        if len(normalized_component_names) != 1:
            raise PyFEMError(f"标量值无法匹配分量集合 {normalized_component_names}。")
        return numpy.asarray((float(value),), dtype=float)
    array = numpy.asarray(tuple(value), dtype=float)
    if array.size != len(normalized_component_names):
        raise PyFEMError(
            f"分量数量 {array.size} 与 component_names={normalized_component_names} 不一致。"
        )
    return array


def build_integration_point_key(element_key: str, point_index: int, *, section_point_label: str | None = None) -> str:
    """构造积分点 target_key。"""

    base_key = f"{element_key}.ip{int(point_index)}"
    if section_point_label is None:
        return base_key
    return f"{base_key}.{section_point_label.lower()}"


def build_element_nodal_key(element_key: str, node_name: str, *, section_point_label: str | None = None) -> str:
    """构造单元节点 target_key。"""

    base_key = f"{element_key}.{node_name}"
    if section_point_label is None:
        return base_key
    return f"{base_key}.{section_point_label.lower()}"


def build_averaging_group_key(scope_name: str, section_name: str, material_name: str) -> str:
    """构造节点平均时使用的分组键。"""

    return f"{scope_name}|{section_name}|{material_name}"


def normalize_measure_value(value: str | None) -> str:
    """规范化单个测度标签。"""

    if value is None:
        return MEASURE_VALUE_UNSPECIFIED
    normalized_value = str(value).strip()
    if not normalized_value:
        return MEASURE_VALUE_UNSPECIFIED
    return normalized_value


def resolve_uniform_measure_value(values: Sequence[str]) -> str:
    """将一组测度标签归并为统一值。"""

    normalized_values = tuple(
        dict.fromkeys(normalize_measure_value(value) for value in values if normalize_measure_value(value))
    )
    if not normalized_values:
        return MEASURE_VALUE_UNSPECIFIED
    if len(normalized_values) == 1:
        return normalized_values[0]
    return MEASURE_VALUE_MIXED


def resolve_kinematic_regime(*measure_values: str | None) -> str:
    """根据测度标签解析 small-strain / finite-strain 语义。"""

    regimes = tuple(
        dict.fromkeys(
            _MEASURE_TO_KINEMATIC_REGIME[normalized_value]
            for normalized_value in (normalize_measure_value(value) for value in measure_values)
            if normalized_value in _MEASURE_TO_KINEMATIC_REGIME
        )
    )
    if not regimes:
        return MEASURE_VALUE_UNSPECIFIED
    if len(regimes) == 1:
        return regimes[0]
    return MEASURE_VALUE_MIXED


def build_measure_metadata(
    *,
    target_keys: Sequence[str],
    strain_measures: Mapping[str, str] | None = None,
    stress_measures: Mapping[str, str] | None = None,
    tangent_measures: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """构造统一的 measure metadata。"""

    normalized_target_keys = tuple(str(target_key) for target_key in target_keys)
    normalized_strain_measures = _normalize_measure_map(strain_measures, normalized_target_keys)
    normalized_stress_measures = _normalize_measure_map(stress_measures, normalized_target_keys)
    normalized_tangent_measures = _normalize_measure_map(tangent_measures, normalized_target_keys)

    metadata: dict[str, Any] = {}
    _write_measure_metadata_entries(
        metadata,
        scalar_key=FIELD_METADATA_KEY_STRAIN_MEASURE,
        map_key=FIELD_METADATA_KEY_STRAIN_MEASURES,
        measures=normalized_strain_measures,
    )
    _write_measure_metadata_entries(
        metadata,
        scalar_key=FIELD_METADATA_KEY_STRESS_MEASURE,
        map_key=FIELD_METADATA_KEY_STRESS_MEASURES,
        measures=normalized_stress_measures,
    )
    _write_measure_metadata_entries(
        metadata,
        scalar_key=FIELD_METADATA_KEY_TANGENT_MEASURE,
        map_key=FIELD_METADATA_KEY_TANGENT_MEASURES,
        measures=normalized_tangent_measures,
    )

    kinematic_regimes = {
        target_key: resolve_kinematic_regime(
            normalized_strain_measures.get(target_key),
            normalized_stress_measures.get(target_key),
            normalized_tangent_measures.get(target_key),
        )
        for target_key in normalized_target_keys
        if any(
            target_key in measure_map
            for measure_map in (normalized_strain_measures, normalized_stress_measures, normalized_tangent_measures)
        )
    }
    if kinematic_regimes:
        metadata[FIELD_METADATA_KEY_KINEMATIC_REGIMES] = kinematic_regimes
        metadata[FIELD_METADATA_KEY_KINEMATIC_REGIME] = resolve_uniform_measure_value(tuple(kinematic_regimes.values()))
    else:
        scalar_regime = resolve_kinematic_regime(
            metadata.get(FIELD_METADATA_KEY_STRAIN_MEASURE),
            metadata.get(FIELD_METADATA_KEY_STRESS_MEASURE),
            metadata.get(FIELD_METADATA_KEY_TANGENT_MEASURE),
        )
        if scalar_regime != MEASURE_VALUE_UNSPECIFIED:
            metadata[FIELD_METADATA_KEY_KINEMATIC_REGIME] = scalar_regime
    return metadata


def subset_result_field(field: ResultField, selection_keys: tuple[str, ...]) -> ResultField:
    """按 target_key 过滤结果场，并同步裁剪相关 metadata。"""

    if not selection_keys:
        return field

    selected_value_keys = [
        target_key
        for target_key in field.target_keys
        if _match_selection_key(field, target_key=target_key, selection_keys=selection_keys)
    ]
    if tuple(selected_value_keys) == field.target_keys:
        return field

    filtered_values = {
        target_key: field.values[target_key]
        for target_key in selected_value_keys
        if target_key in field.values
    }
    filtered_metadata = subset_target_metadata(dict(field.metadata), tuple(selected_value_keys))
    return ResultField(
        name=field.name,
        position=field.position,
        values=filtered_values,
        source_type=field.source_type,
        component_names=field.resolve_component_names(tuple(selected_value_keys)),
        target_keys=tuple(selected_value_keys),
        target_count=len(selected_value_keys),
        metadata=filtered_metadata,
    )


def subset_target_metadata(metadata: dict[str, Any], target_keys: tuple[str, ...]) -> dict[str, Any]:
    """裁剪与 target_key 绑定的 metadata。"""

    selected_key_set = set(target_keys)
    for metadata_key in TARGET_KEY_METADATA_KEYS:
        current_value = metadata.get(metadata_key)
        if isinstance(current_value, Mapping):
            metadata[metadata_key] = {
                str(target_key): value
                for target_key, value in current_value.items()
                if str(target_key) in selected_key_set
            }
    return metadata


def _normalize_measure_map(
    measures: Mapping[str, str] | None,
    target_keys: Sequence[str],
) -> dict[str, str]:
    if not measures:
        return {}
    target_key_set = {str(target_key) for target_key in target_keys}
    return {
        str(target_key): normalize_measure_value(value)
        for target_key, value in measures.items()
        if str(target_key) in target_key_set
    }


def _write_measure_metadata_entries(
    metadata: dict[str, Any],
    *,
    scalar_key: str,
    map_key: str,
    measures: Mapping[str, str],
) -> None:
    if not measures:
        return
    metadata[map_key] = {
        str(target_key): normalize_measure_value(value)
        for target_key, value in measures.items()
    }
    metadata[scalar_key] = resolve_uniform_measure_value(tuple(measures.values()))


def _match_selection_key(field: ResultField, *, target_key: str, selection_keys: tuple[str, ...]) -> bool:
    selection_key_set = set(str(item) for item in selection_keys)
    if field.position in {POSITION_NODE, POSITION_NODE_AVERAGED}:
        base_target_keys = field.metadata.get(FIELD_METADATA_KEY_BASE_TARGET_KEYS, {})
        base_target_key = str(base_target_keys.get(target_key, target_key))
        return base_target_key in selection_key_set
    if field.position in {POSITION_ELEMENT_CENTROID, POSITION_INTEGRATION_POINT, POSITION_ELEMENT_NODAL}:
        owner_element_keys = field.metadata.get(FIELD_METADATA_KEY_OWNER_ELEMENT_KEYS, {})
        owner_element_key = str(owner_element_keys.get(target_key, target_key))
        return owner_element_key in selection_key_set
    return target_key in selection_key_set
