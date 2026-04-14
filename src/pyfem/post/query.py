"""基于 ResultsReader 的查询服务。"""

from __future__ import annotations

from dataclasses import dataclass

from pyfem.foundation.errors import PyFEMError
from pyfem.io import ResultField, ResultFrame, ResultHistorySeries, ResultStep, ResultSummary, ResultsReader
from pyfem.post.common import subset_result_field
from pyfem.post.overviews import ResultFieldOverview, build_result_field_overview


@dataclass(slots=True, frozen=True)
class ResultsQueryService:
    """封装基于 ResultsReader 的窄接口查询。"""

    results_reader: ResultsReader

    def list_steps(self) -> tuple[str, ...]:
        """列出结果步骤。"""

        return self.results_reader.list_steps()

    def steps(self, *, procedure_type: str | None = None) -> tuple[ResultStep, ...]:
        """按顺序读取并筛选结果步骤。"""

        steps = tuple(self.results_reader.read_step(step_name) for step_name in self.results_reader.list_steps())
        if procedure_type is not None:
            steps = tuple(step for step in steps if step.procedure_type == procedure_type)
        return steps

    def step(self, step_name: str) -> ResultStep:
        """读取单个结果步骤。"""

        return self.results_reader.read_step(step_name)

    def frames(
        self,
        step_name: str,
        *,
        field_name: str | None = None,
        frame_kind: str | None = None,
        axis_kind: str | None = None,
        frame_ids: tuple[int, ...] | None = None,
        source_type: str | None = None,
        position: str | None = None,
        target_key: str | None = None,
        result_key: str | None = None,
    ) -> tuple[ResultFrame, ...]:
        """按步骤读取并筛选结果帧。"""

        resolved_target_key = _resolve_target_key(target_key=target_key, result_key=result_key)
        frames = self.results_reader.read_step(step_name).frames
        if frame_kind is not None:
            frames = tuple(frame for frame in frames if frame.frame_kind == frame_kind)
        if axis_kind is not None:
            frames = tuple(frame for frame in frames if frame.axis_kind == axis_kind)
        if frame_ids is not None:
            allowed_frame_ids = set(frame_ids)
            frames = tuple(frame for frame in frames if frame.frame_id in allowed_frame_ids)
        if any(value is not None for value in (field_name, source_type, position, resolved_target_key)):
            frames = tuple(
                frame
                for frame in frames
                if self._filter_fields(
                    frame,
                    field_name=field_name,
                    source_type=source_type,
                    position=position,
                    target_key=resolved_target_key,
                )
            )
        return frames

    def field(self, step_name: str, frame_id: int, field_name: str) -> ResultField:
        """读取指定结果场。"""

        return self.results_reader.read_field(step_name, frame_id, field_name)

    def field_overview(
        self,
        step_name: str,
        frame_id: int,
        field_name: str,
        *,
        target_key: str | None = None,
        result_key: str | None = None,
    ) -> ResultFieldOverview:
        """读取单个结果场概览。"""

        overviews = self.field_overviews(
            step_name=step_name,
            frame_id=frame_id,
            field_name=field_name,
            target_key=target_key,
            result_key=result_key,
        )
        if not overviews:
            raise PyFEMError(f"步骤 {step_name} 的帧 {frame_id} 中不存在结果场 {field_name}。")
        return overviews[0]

    def field_overviews(
        self,
        step_name: str,
        *,
        frame_id: int | None = None,
        field_name: str | None = None,
        frame_kind: str | None = None,
        axis_kind: str | None = None,
        source_type: str | None = None,
        position: str | None = None,
        target_key: str | None = None,
        result_key: str | None = None,
    ) -> tuple[ResultFieldOverview, ...]:
        """按步骤读取并筛选结果场概览。"""

        selected_frame_ids = None if frame_id is None else (frame_id,)
        resolved_target_key = _resolve_target_key(target_key=target_key, result_key=result_key)
        overviews: list[ResultFieldOverview] = []
        for frame in self.frames(
            step_name,
            field_name=field_name,
            frame_kind=frame_kind,
            axis_kind=axis_kind,
            frame_ids=selected_frame_ids,
            source_type=source_type,
            position=position,
            target_key=resolved_target_key,
        ):
            for field in self._filter_fields(
                frame,
                field_name=field_name,
                source_type=source_type,
                position=position,
                target_key=resolved_target_key,
            ):
                overviews.append(build_result_field_overview(frame.step_name, frame.frame_id, field))
        return tuple(overviews)

    def raw_field_overviews(self, step_name: str, **kwargs: object) -> tuple[ResultFieldOverview, ...]:
        """筛选原始结果场概览。"""

        return self.field_overviews(step_name, source_type="raw", **kwargs)

    def recovered_field_overviews(self, step_name: str, **kwargs: object) -> tuple[ResultFieldOverview, ...]:
        """筛选恢复结果场概览。"""

        return self.field_overviews(step_name, source_type="recovered", **kwargs)

    def averaged_field_overviews(self, step_name: str, **kwargs: object) -> tuple[ResultFieldOverview, ...]:
        """筛选平均结果场概览。"""

        return self.field_overviews(step_name, source_type="averaged", **kwargs)

    def derived_field_overviews(self, step_name: str, **kwargs: object) -> tuple[ResultFieldOverview, ...]:
        """筛选派生结果场概览。"""

        return self.field_overviews(step_name, source_type="derived", **kwargs)

    def history(self, step_name: str, history_name: str) -> ResultHistorySeries:
        """读取单个步骤历史量。"""

        return self.results_reader.read_history(step_name, history_name)

    def histories(
        self,
        step_name: str,
        history_name: str | None = None,
        *,
        axis_kind: str | None = None,
        paired_value_name: str | None = None,
    ) -> tuple[ResultHistorySeries, ...]:
        """读取并筛选步骤历史量。"""

        histories = self.results_reader.read_histories(step_name=step_name, history_name=history_name)
        if axis_kind is not None:
            histories = tuple(history for history in histories if history.axis_kind == axis_kind)
        if paired_value_name is not None:
            histories = tuple(history for history in histories if paired_value_name in history.paired_values)
        return histories

    def summaries(
        self,
        step_name: str,
        summary_name: str | None = None,
        *,
        data_key: str | None = None,
    ) -> tuple[ResultSummary, ...]:
        """读取并筛选步骤摘要。"""

        summaries = self.results_reader.read_summaries(step_name=step_name, summary_name=summary_name)
        if data_key is not None:
            summaries = tuple(summary for summary in summaries if data_key in summary.data)
        return summaries

    def summary(self, step_name: str, summary_name: str) -> ResultSummary:
        """读取步骤摘要。"""

        return self.results_reader.read_summary(step_name, summary_name)

    def _filter_fields(
        self,
        frame: ResultFrame,
        *,
        field_name: str | None,
        source_type: str | None,
        position: str | None,
        target_key: str | None,
    ) -> tuple[ResultField, ...]:
        fields = frame.fields
        if field_name is not None:
            fields = tuple(field for field in fields if field.name == field_name)
        if source_type is not None:
            normalized_source_type = str(source_type).strip().lower()
            fields = tuple(field for field in fields if field.source_type == normalized_source_type)
        if position is not None:
            normalized_position = str(position).strip().upper()
            fields = tuple(field for field in fields if field.position == normalized_position)
        if target_key is None:
            return fields

        filtered_fields: list[ResultField] = []
        for field in fields:
            filtered_field = subset_result_field(field, (target_key,))
            if filtered_field.values:
                filtered_fields.append(filtered_field)
        return tuple(filtered_fields)


def _resolve_target_key(*, target_key: str | None, result_key: str | None) -> str | None:
    """统一解析 target_key / result_key 别名。"""

    if target_key is not None and result_key is not None and target_key != result_key:
        raise PyFEMError("target_key 与 result_key 不允许传入不同值。")
    return target_key if target_key is not None else result_key
