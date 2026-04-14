"""结果消费层 facade。"""

from __future__ import annotations

from collections.abc import Iterable

from pyfem.foundation.errors import PyFEMError
from pyfem.io import ResultField, ResultFrame, ResultHistorySeries, ResultStep, ResultSummary, ResultsCapabilities, ResultsReader, ResultsSession
from pyfem.post.common import subset_result_field
from pyfem.post.overviews import (
    ResultFieldOverview,
    ResultFrameOverview,
    ResultHistoryOverview,
    ResultStepOverview,
    ResultSummaryOverview,
)
from pyfem.post.probe import ResultsProbeService
from pyfem.post.query import ResultsQueryService


class ResultsFacade:
    """封装 reader-only 的结果浏览入口。"""

    def __init__(self, results_reader: ResultsReader) -> None:
        self.results_reader = results_reader

    def session(self) -> ResultsSession:
        """读取正式结果会话元数据。"""

        return self.results_reader.read_session()

    def capabilities(self) -> ResultsCapabilities:
        """读取结果后端能力边界。"""

        return self.results_reader.get_capabilities()

    def list_steps(self) -> tuple[str, ...]:
        """列出全部步骤名称。"""

        return self.results_reader.list_steps()

    def step(self, step_name: str) -> ResultStep:
        """读取正式结果步骤对象。"""

        return self.query().step(step_name)

    def frame(self, step_name: str, frame_id: int) -> ResultFrame:
        """读取正式结果帧对象。"""

        return self.query().step(step_name).get_frame(frame_id)

    def field(self, step_name: str, frame_id: int, field_name: str) -> ResultField:
        """读取正式结果场对象。"""

        return self.query().field(step_name, frame_id, field_name)

    def history(self, step_name: str, history_name: str) -> ResultHistorySeries:
        """读取正式历史量对象。"""

        return self.query().history(step_name, history_name)

    def summary(self, step_name: str, summary_name: str) -> ResultSummary:
        """读取正式摘要对象。"""

        return self.query().summary(step_name, summary_name)

    def step_overviews(
        self,
        *,
        step_name: str | None = None,
        procedure_type: str | None = None,
        frame_kind: str | None = None,
        axis_kind: str | None = None,
        field_name: str | None = None,
        target_key: str | None = None,
        result_key: str | None = None,
        source_type: str | None = None,
        position: str | None = None,
    ) -> tuple[ResultStepOverview, ...]:
        """返回适合产品层显示的步骤概览。"""

        resolved_target_key = _resolve_target_key(target_key=target_key, result_key=result_key)
        overviews: list[ResultStepOverview] = []
        for current_step_name in self._iter_step_names(step_name):
            step = self.query().step(current_step_name)
            if procedure_type is not None and step.procedure_type != procedure_type:
                continue

            frame_overviews = self.frames(
                step_name=current_step_name,
                frame_kind=frame_kind,
                axis_kind=axis_kind,
                field_name=field_name,
                target_key=resolved_target_key,
                source_type=source_type,
                position=position,
            )
            history_overviews = self.histories(
                step_name=current_step_name,
                axis_kind=axis_kind,
                target_key=resolved_target_key,
            )
            summary_overviews = self.summaries(step_name=current_step_name)
            field_overviews = self.fields(
                step_name=current_step_name,
                field_name=field_name,
                target_key=resolved_target_key,
                source_type=source_type,
                position=position,
            )

            if _has_step_filters(
                frame_kind=frame_kind,
                axis_kind=axis_kind,
                field_name=field_name,
                target_key=resolved_target_key,
                source_type=source_type,
                position=position,
            ) and not frame_overviews and not history_overviews:
                continue

            overviews.append(
                ResultStepOverview(
                    step_name=step.name,
                    procedure_type=step.procedure_type,
                    frame_count=len(frame_overviews),
                    history_count=len(history_overviews),
                    summary_count=len(summary_overviews),
                    frame_ids=tuple(frame.frame_id for frame in frame_overviews),
                    frame_kinds=tuple(dict.fromkeys(frame.frame_kind for frame in frame_overviews)),
                    axis_kinds=tuple(
                        dict.fromkeys(
                            list(frame.axis_kind for frame in frame_overviews)
                            + list(history.axis_kind for history in history_overviews)
                        )
                    ),
                    field_names=tuple(dict.fromkeys(field.field_name for field in field_overviews)),
                    raw_field_names=_field_names_by_source(field_overviews, "raw"),
                    recovered_field_names=_field_names_by_source(field_overviews, "recovered"),
                    averaged_field_names=_field_names_by_source(field_overviews, "averaged"),
                    derived_field_names=_field_names_by_source(field_overviews, "derived"),
                    history_names=tuple(history.history_name for history in history_overviews),
                    summary_names=tuple(summary.summary_name for summary in summary_overviews),
                    target_keys=tuple(
                        dict.fromkeys(
                            list(_flatten_string_groups(frame.target_keys for frame in frame_overviews))
                            + list(_flatten_string_groups(history.target_keys for history in history_overviews))
                        )
                    ),
                    metadata=dict(step.metadata),
                )
            )
        return tuple(overviews)

    def frames(
        self,
        *,
        step_name: str | None = None,
        frame_kind: str | None = None,
        axis_kind: str | None = None,
        field_name: str | None = None,
        target_key: str | None = None,
        result_key: str | None = None,
        frame_ids: tuple[int, ...] | None = None,
        source_type: str | None = None,
        position: str | None = None,
    ) -> tuple[ResultFrameOverview, ...]:
        """浏览结果帧概览。"""

        resolved_target_key = _resolve_target_key(target_key=target_key, result_key=result_key)
        overviews: list[ResultFrameOverview] = []
        query = self.query()
        for current_step_name in self._iter_step_names(step_name):
            frames = query.frames(
                current_step_name,
                field_name=field_name,
                frame_kind=frame_kind,
                axis_kind=axis_kind,
                frame_ids=frame_ids,
                source_type=source_type,
                position=position,
                target_key=resolved_target_key,
            )
            for frame in frames:
                filtered_fields = self._filter_frame_fields(
                    frame,
                    field_name=field_name,
                    target_key=resolved_target_key,
                    source_type=source_type,
                    position=position,
                )
                if not filtered_fields:
                    continue
                target_keys = tuple(dict.fromkeys(_flatten_string_groups(field.target_keys for field in filtered_fields)))
                overviews.append(
                    ResultFrameOverview(
                        step_name=frame.step_name,
                        frame_id=frame.frame_id,
                        time=frame.time,
                        frame_kind=frame.frame_kind,
                        axis_kind=frame.axis_kind,
                        axis_value=frame.axis_value,
                        field_names=tuple(field.name for field in filtered_fields),
                        raw_field_names=_result_field_names(filtered_fields, "raw"),
                        recovered_field_names=_result_field_names(filtered_fields, "recovered"),
                        averaged_field_names=_result_field_names(filtered_fields, "averaged"),
                        derived_field_names=_result_field_names(filtered_fields, "derived"),
                        field_positions=tuple(dict.fromkeys(field.position for field in filtered_fields)),
                        field_source_types=tuple(dict.fromkeys(field.source_type for field in filtered_fields)),
                        target_keys=target_keys,
                        target_count=len(target_keys),
                        metadata=dict(frame.metadata),
                    )
                )
        return tuple(overviews)

    def fields(
        self,
        *,
        step_name: str | None = None,
        frame_id: int | None = None,
        frame_kind: str | None = None,
        axis_kind: str | None = None,
        field_name: str | None = None,
        target_key: str | None = None,
        result_key: str | None = None,
        source_type: str | None = None,
        position: str | None = None,
    ) -> tuple[ResultFieldOverview, ...]:
        """浏览结果场概览。"""

        resolved_target_key = _resolve_target_key(target_key=target_key, result_key=result_key)
        overviews: list[ResultFieldOverview] = []
        query = self.query()
        for current_step_name in self._iter_step_names(step_name):
            overviews.extend(
                query.field_overviews(
                    current_step_name,
                    frame_id=frame_id,
                    field_name=field_name,
                    frame_kind=frame_kind,
                    axis_kind=axis_kind,
                    source_type=source_type,
                    position=position,
                    target_key=resolved_target_key,
                )
            )
        return tuple(overviews)

    def raw_fields(self, **kwargs: object) -> tuple[ResultFieldOverview, ...]:
        """浏览原始结果场概览。"""

        return self.fields(source_type="raw", **kwargs)

    def recovered_fields(self, **kwargs: object) -> tuple[ResultFieldOverview, ...]:
        """浏览恢复结果场概览。"""

        return self.fields(source_type="recovered", **kwargs)

    def averaged_fields(self, **kwargs: object) -> tuple[ResultFieldOverview, ...]:
        """浏览平均结果场概览。"""

        return self.fields(source_type="averaged", **kwargs)

    def derived_fields(self, **kwargs: object) -> tuple[ResultFieldOverview, ...]:
        """浏览派生结果场概览。"""

        return self.fields(source_type="derived", **kwargs)

    def histories(
        self,
        *,
        step_name: str | None = None,
        history_name: str | None = None,
        axis_kind: str | None = None,
        target_key: str | None = None,
        result_key: str | None = None,
        paired_value_name: str | None = None,
    ) -> tuple[ResultHistoryOverview, ...]:
        """浏览历史量概览。"""

        resolved_target_key = _resolve_target_key(target_key=target_key, result_key=result_key)
        overviews: list[ResultHistoryOverview] = []
        query = self.query()
        for current_step_name in self._iter_step_names(step_name):
            histories = query.histories(
                current_step_name,
                history_name=history_name,
                axis_kind=axis_kind,
                paired_value_name=paired_value_name,
            )
            for history in histories:
                if resolved_target_key is not None and resolved_target_key not in history.values:
                    continue
                target_keys = tuple(
                    key for key in history.values.keys() if resolved_target_key is None or key == resolved_target_key
                )
                overviews.append(
                    ResultHistoryOverview(
                        step_name=history.step_name,
                        history_name=history.name,
                        axis_kind=history.axis_kind,
                        axis_count=len(history.axis_values),
                        position=history.position,
                        target_keys=target_keys,
                        target_count=len(target_keys),
                        paired_value_names=tuple(history.paired_values.keys()),
                        metadata=dict(history.metadata),
                    )
                )
        return tuple(overviews)

    def summaries(
        self,
        *,
        step_name: str | None = None,
        summary_name: str | None = None,
        data_key: str | None = None,
    ) -> tuple[ResultSummaryOverview, ...]:
        """浏览步骤摘要概览。"""

        overviews: list[ResultSummaryOverview] = []
        query = self.query()
        for current_step_name in self._iter_step_names(step_name):
            summaries = query.summaries(current_step_name, summary_name=summary_name, data_key=data_key)
            for summary in summaries:
                overviews.append(
                    ResultSummaryOverview(
                        step_name=summary.step_name,
                        summary_name=summary.name,
                        data_keys=tuple(summary.data.keys()),
                        metadata=dict(summary.metadata),
                    )
                )
        return tuple(overviews)

    def query(self) -> ResultsQueryService:
        """返回 reader-only 查询服务。"""

        return ResultsQueryService(self.results_reader)

    def probe(self) -> ResultsProbeService:
        """返回 reader-only probe 服务。"""

        return ResultsProbeService(self.results_reader)

    def _iter_step_names(self, step_name: str | None) -> tuple[str, ...]:
        """解析当前需要浏览的步骤范围。"""

        if step_name is not None:
            return (step_name,)
        return self.list_steps()

    def _filter_frame_fields(
        self,
        frame: ResultFrame,
        *,
        field_name: str | None,
        target_key: str | None,
        source_type: str | None,
        position: str | None,
    ) -> tuple[ResultField, ...]:
        """按字段条件筛选当前帧内的结果场。"""

        fields = frame.fields if field_name is None else tuple(field for field in frame.fields if field.name == field_name)
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


def _flatten_string_groups(items: Iterable[Iterable[str]]) -> list[str]:
    """将多组字符串键拍平为单一序列。"""

    flattened: list[str] = []
    for group in items:
        for item in group:
            flattened.append(str(item))
    return flattened


def _result_field_names(fields: tuple[ResultField, ...], source_type: str) -> tuple[str, ...]:
    normalized_source_type = str(source_type).strip().lower()
    return tuple(dict.fromkeys(field.name for field in fields if field.source_type == normalized_source_type))


def _field_names_by_source(fields: tuple[ResultFieldOverview, ...], source_type: str) -> tuple[str, ...]:
    normalized_source_type = str(source_type).strip().lower()
    return tuple(dict.fromkeys(field.field_name for field in fields if field.source_type == normalized_source_type))


def _has_step_filters(
    *,
    frame_kind: str | None,
    axis_kind: str | None,
    field_name: str | None,
    target_key: str | None,
    source_type: str | None,
    position: str | None,
) -> bool:
    """判断步骤概览是否带有子结果筛选条件。"""

    return any(value is not None for value in (frame_kind, axis_kind, field_name, target_key, source_type, position))
