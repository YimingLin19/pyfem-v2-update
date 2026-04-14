"""基于 ResultsReader 的 probe 服务。"""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyfem.foundation.errors import PyFEMError
from pyfem.io import (
    AXIS_KIND_FRAME_ID,
    FIELD_KEY_S,
    FIELD_KEY_S_AVG,
    FIELD_KEY_S_IP,
    FIELD_KEY_U,
    POSITION_ELEMENT_CENTROID,
    POSITION_INTEGRATION_POINT,
    POSITION_NODE,
    POSITION_NODE_AVERAGED,
    ResultsReader,
)
from pyfem.post.common import FIELD_METADATA_KEY_AVERAGING_GROUPS, FIELD_METADATA_KEY_BASE_TARGET_KEYS


@dataclass(slots=True, frozen=True)
class ProbeSeries:
    """定义 probe 查询返回的轻量序列对象。"""

    step_name: str
    source_name: str
    axis_kind: str
    axis_values: tuple[float | int, ...]
    values: tuple[Any, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ResultsProbeService:
    """封装只依赖 ResultsReader 的正式 probe 服务。"""

    results_reader: ResultsReader

    def history(self, step_name: str, history_name: str, target_key: str | None = None) -> ProbeSeries:
        """将正式历史量投影为 probe 序列。"""

        history = self.results_reader.read_history(step_name, history_name)
        resolved_target_key = target_key
        return ProbeSeries(
            step_name=step_name,
            source_name=history_name,
            axis_kind=history.axis_kind,
            axis_values=history.axis_values,
            values=history.get_series(resolved_target_key),
            metadata={
                "position": history.position,
                "target_key": resolved_target_key,
                **dict(history.metadata),
            },
        )

    def paired_history(self, step_name: str, history_name: str, value_name: str) -> ProbeSeries:
        """将历史量中的 paired_values 投影为 probe 序列。"""

        history = self.results_reader.read_history(step_name, history_name)
        return ProbeSeries(
            step_name=step_name,
            source_name=f"{history_name}:{value_name}",
            axis_kind=history.axis_kind,
            axis_values=history.axis_values,
            values=history.get_paired_series(value_name),
            metadata={
                "position": history.position,
                "paired_value_name": value_name,
                **dict(history.metadata),
            },
        )

    def field_component(
        self,
        step_name: str,
        target_key: str,
        component_name: str | None,
        *,
        field_name: str,
        frame_ids: tuple[int, ...] | None = None,
        expected_position: str | None = None,
    ) -> ProbeSeries:
        """按目标键和分量提取通用结果场 probe。"""

        selected_frames = self._select_frames(step_name, frame_ids=frame_ids)
        axis_values: list[float | int] = []
        values: list[Any] = []
        resolved_component_name: str | None = None
        resolved_target_key: str | None = None
        position: str | None = None
        source_type: str | None = None

        for frame in selected_frames:
            field = self.results_reader.read_field(step_name, frame.frame_id, field_name)
            if expected_position is not None and field.position != expected_position:
                raise PyFEMError(
                    f"结果场 {field_name} 的位置为 {field.position}，与 probe 期望的 {expected_position} 不一致。"
                )
            current_target_key = target_key
            if field.position == POSITION_NODE_AVERAGED:
                current_target_key = self._resolve_averaged_target_key(field.values, dict(field.metadata), base_node_key=target_key)
            target_values = field.values.get(current_target_key)
            if target_values is None:
                raise PyFEMError(f"结果场 {field_name} 中不存在目标 {current_target_key}。")
            current_component_name, component_value = self._extract_component_value(
                target_values,
                component_name=component_name,
                field_name=field_name,
                target_key=current_target_key,
                component_names=field.component_names,
            )
            axis_values.append(frame.axis_value if frame.axis_value is not None else frame.frame_id)
            values.append(component_value)
            resolved_component_name = current_component_name
            resolved_target_key = current_target_key
            position = field.position
            source_type = field.source_type

        return ProbeSeries(
            step_name=step_name,
            source_name=self._build_field_probe_source_name(
                field_name=field_name,
                target_key=resolved_target_key,
                component_name=resolved_component_name,
            ),
            axis_kind=selected_frames[0].axis_kind if selected_frames else AXIS_KIND_FRAME_ID,
            axis_values=tuple(axis_values),
            values=tuple(values),
            metadata={
                "field_name": field_name,
                "target_key": target_key,
                "resolved_target_key": resolved_target_key,
                "component_name": resolved_component_name,
                "position": position,
                "source_type": source_type,
                "frame_ids": None if frame_ids is None else tuple(frame_ids),
            },
        )

    def node_component(
        self,
        step_name: str,
        node_key: str,
        component_name: str | None = None,
        *,
        field_name: str = FIELD_KEY_U,
        frame_ids: tuple[int, ...] | None = None,
    ) -> ProbeSeries:
        """从帧序列中提取一个节点分量的 probe。"""

        return self.field_component(
            step_name,
            node_key,
            component_name,
            field_name=field_name,
            frame_ids=frame_ids,
            expected_position=POSITION_NODE,
        )

    def element_component(
        self,
        step_name: str,
        element_key: str,
        component_name: str | None = None,
        *,
        field_name: str = FIELD_KEY_S,
        frame_ids: tuple[int, ...] | None = None,
    ) -> ProbeSeries:
        """从帧序列中提取一个单元结果分量的 probe。"""

        return self.field_component(
            step_name,
            element_key,
            component_name,
            field_name=field_name,
            frame_ids=frame_ids,
            expected_position=POSITION_ELEMENT_CENTROID,
        )

    def integration_point_component(
        self,
        step_name: str,
        integration_point_key: str,
        component_name: str | None = None,
        *,
        field_name: str = FIELD_KEY_S_IP,
        frame_ids: tuple[int, ...] | None = None,
    ) -> ProbeSeries:
        """从帧序列中提取一个积分点结果分量的 probe。"""

        return self.field_component(
            step_name,
            integration_point_key,
            component_name,
            field_name=field_name,
            frame_ids=frame_ids,
            expected_position=POSITION_INTEGRATION_POINT,
        )

    def averaged_node_component(
        self,
        step_name: str,
        node_key: str,
        component_name: str | None = None,
        *,
        field_name: str = FIELD_KEY_S_AVG,
        frame_ids: tuple[int, ...] | None = None,
    ) -> ProbeSeries:
        """从帧序列中提取一个节点平均场分量的 probe。"""

        return self.field_component(
            step_name,
            node_key,
            component_name,
            field_name=field_name,
            frame_ids=frame_ids,
            expected_position=POSITION_NODE_AVERAGED,
        )

    def export_csv(self, probe_series: ProbeSeries, path: str | Path) -> Path:
        """将 probe 序列导出为 CSV。"""

        target_path = Path(path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        metadata = dict(probe_series.metadata)
        field_name = metadata.pop("field_name", "")
        target_key = metadata.pop("target_key", "")
        resolved_target_key = metadata.pop("resolved_target_key", target_key)
        component_name = metadata.pop("component_name", "")
        position = metadata.pop("position", "")
        source_type = metadata.pop("source_type", "")
        metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True) if metadata else ""

        with target_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                (
                    "step_name",
                    "source_name",
                    "axis_kind",
                    "axis_value",
                    "value",
                    "field_name",
                    "target_key",
                    "resolved_target_key",
                    "component_name",
                    "position",
                    "source_type",
                    "metadata_json",
                )
            )
            for axis_value, value in zip(probe_series.axis_values, probe_series.values, strict=True):
                writer.writerow(
                    (
                        probe_series.step_name,
                        probe_series.source_name,
                        probe_series.axis_kind,
                        axis_value,
                        self._format_csv_value(value),
                        field_name,
                        target_key,
                        resolved_target_key,
                        component_name,
                        position,
                        source_type,
                        metadata_json,
                    )
                )
        return target_path

    def _select_frames(self, step_name: str, *, frame_ids: tuple[int, ...] | None) -> tuple[Any, ...]:
        step = self.results_reader.read_step(step_name)
        if not step.frames:
            raise PyFEMError(f"步骤 {step_name} 中没有可用于 probe 的结果帧。")

        selected_frames = step.frames
        if frame_ids is not None:
            allowed_frame_ids = set(frame_ids)
            selected_frames = tuple(frame for frame in step.frames if frame.frame_id in allowed_frame_ids)
            if not selected_frames:
                raise PyFEMError(f"步骤 {step_name} 中不存在请求的 frame_ids={tuple(frame_ids)}。")
        return selected_frames

    def _extract_component_value(
        self,
        value: Any,
        *,
        component_name: str | None,
        field_name: str,
        target_key: str,
        component_names: tuple[str, ...],
    ) -> tuple[str | None, Any]:
        if isinstance(value, Mapping):
            if component_name is None:
                if len(value) != 1:
                    raise PyFEMError(
                        f"结果场 {field_name} 的目标 {target_key} 包含多个分量，请显式指定 component_name。"
                    )
                resolved_component_name = str(next(iter(value.keys())))
            else:
                resolved_component_name = component_name
            if resolved_component_name not in value:
                raise PyFEMError(f"结果场 {field_name} 中不存在分量 {target_key}.{resolved_component_name}。")
            return resolved_component_name, value[resolved_component_name]
        if isinstance(value, (tuple, list)):
            normalized_component_name = None if component_name is None else str(component_name).strip()
            if component_names:
                if normalized_component_name in {None, "", "VALUE"}:
                    if len(component_names) != 1:
                        raise PyFEMError(
                            f"结果场 {field_name} 的目标 {target_key} 包含多个分量，请显式指定 component_name。"
                        )
                    resolved_component_name = component_names[0]
                else:
                    resolved_component_name = normalized_component_name
                if resolved_component_name not in component_names:
                    raise PyFEMError(f"结果场 {field_name} 中不存在分量 {target_key}.{resolved_component_name}。")
                component_index = component_names.index(resolved_component_name)
                if component_index >= len(value):
                    raise PyFEMError(f"结果场 {field_name} 的目标 {target_key} 缺少分量 {resolved_component_name}。")
                return resolved_component_name, value[component_index]
            if normalized_component_name in {None, "", "VALUE"}:
                if len(value) == 1:
                    return None, value[0]
                return None, value
            raise PyFEMError(f"结果场 {field_name} 的目标 {target_key} 为未命名序列结果，不支持分量 {normalized_component_name}。")
        normalized_component_name = None if component_name is None else str(component_name).strip()
        if normalized_component_name in {None, "", "VALUE"}:
            return None, value
        raise PyFEMError(f"结果场 {field_name} 的目标 {target_key} 为标量结果，不支持分量 {normalized_component_name}。")

    def _build_field_probe_source_name(
        self,
        *,
        field_name: str,
        target_key: str | None,
        component_name: str | None,
    ) -> str:
        source_name = f"{field_name}:{target_key}"
        if component_name:
            return f"{source_name}.{component_name}"
        return source_name

    def _resolve_averaged_target_key(
        self,
        values: Mapping[str, Any],
        metadata: dict[str, Any],
        *,
        base_node_key: str,
    ) -> str:
        if base_node_key in values:
            return base_node_key

        base_target_keys = {
            str(target_key): str(current_base_key)
            for target_key, current_base_key in metadata.get(FIELD_METADATA_KEY_BASE_TARGET_KEYS, {}).items()
        }
        matched_targets = [
            target_key
            for target_key, current_base_key in base_target_keys.items()
            if current_base_key == base_node_key and target_key in values
        ]
        if not matched_targets:
            raise PyFEMError(f"平均场中不存在基节点 {base_node_key} 对应的目标键。")
        if len(matched_targets) == 1:
            return matched_targets[0]

        averaging_groups = metadata.get(FIELD_METADATA_KEY_AVERAGING_GROUPS, {})
        readable_groups = ", ".join(
            f"{target_key} -> {averaging_groups.get(target_key, '-') }" for target_key in matched_targets
        )
        raise PyFEMError(
            f"平均场基节点 {base_node_key} 对应多个目标，请改用具体 target_key。候选为: {readable_groups}。"
        )

    def _format_csv_value(self, value: Any) -> str | float | int:
        if isinstance(value, bool):
            return str(value)
        if isinstance(value, (int, float, str)):
            return value
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
