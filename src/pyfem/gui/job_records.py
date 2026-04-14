"""定义 Job 模块在 GUI 会话中的记录模型与摘要工具。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path


RUNNING_JOB_STATUSES = {"queued", "running"}
FAILED_JOB_STATUSES = {"failed", "terminated"}


def create_job_timestamp() -> str:
    """返回统一的 UTC ISO 时间戳。"""

    return datetime.now(timezone.utc).isoformat()


def build_job_display_name(
    *,
    model_name: str | None,
    step_name: str | None,
    job_name: str | None = None,
    snapshot_path: Path | None = None,
) -> str:
    """生成在 Job Center 中使用的显示名称。"""

    if job_name not in {None, ""}:
        return str(job_name)
    if snapshot_path is not None:
        return snapshot_path.stem
    if model_name and step_name:
        return f"{model_name} / {step_name}"
    if model_name:
        return model_name
    if step_name:
        return step_name
    return "Job Record"


def _normalize_path(raw_value: object) -> Path | None:
    if raw_value in {None, ""}:
        return None
    return Path(str(raw_value))


@dataclass(slots=True, frozen=True)
class GuiJobRecord:
    """定义 GUI 会话中的 Job 历史记录。"""

    record_id: str
    display_name: str
    step_name: str
    status: str
    created_at: str
    started_at: str | None
    finished_at: str | None
    results_path: Path | None
    export_path: Path | None
    snapshot_path: Path | None
    manifest_path: Path | None
    report_path: Path | None
    frame_count: int
    history_count: int
    summary_count: int
    last_messages: tuple[str, ...]
    error_count: int
    warning_count: int
    model_name: str | None = None
    job_name: str | None = None
    procedure_type: str | None = None
    results_backend: str | None = None
    export_format: str | None = None
    current_action: str | None = None

    def append_message(self, message: str, *, max_messages: int = 60) -> "GuiJobRecord":
        """返回附加了新消息的记录副本。"""

        normalized_message = message.strip()
        if not normalized_message:
            return self
        messages = (*self.last_messages, normalized_message)
        trimmed_messages = messages[-max_messages:]
        return replace(
            self,
            last_messages=trimmed_messages,
            error_count=sum(1 for item in trimmed_messages if classify_job_message(item) == "error"),
            warning_count=sum(1 for item in trimmed_messages if classify_job_message(item) == "warning"),
            current_action=normalized_message,
        )

    def to_dict(self) -> dict[str, object]:
        """将记录转换为可序列化字典。"""

        return {
            "record_id": self.record_id,
            "display_name": self.display_name,
            "step_name": self.step_name,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "results_path": None if self.results_path is None else str(self.results_path),
            "export_path": None if self.export_path is None else str(self.export_path),
            "snapshot_path": None if self.snapshot_path is None else str(self.snapshot_path),
            "manifest_path": None if self.manifest_path is None else str(self.manifest_path),
            "report_path": None if self.report_path is None else str(self.report_path),
            "frame_count": self.frame_count,
            "history_count": self.history_count,
            "summary_count": self.summary_count,
            "last_messages": list(self.last_messages),
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "model_name": self.model_name,
            "job_name": self.job_name,
            "procedure_type": self.procedure_type,
            "results_backend": self.results_backend,
            "export_format": self.export_format,
            "current_action": self.current_action,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "GuiJobRecord":
        """从字典恢复 GUI Job 记录。"""

        return cls(
            record_id=str(payload["record_id"]),
            display_name=str(payload["display_name"]),
            step_name=str(payload["step_name"]),
            status=str(payload["status"]),
            created_at=str(payload["created_at"]),
            started_at=None if payload.get("started_at") in {None, ""} else str(payload["started_at"]),
            finished_at=None if payload.get("finished_at") in {None, ""} else str(payload["finished_at"]),
            results_path=_normalize_path(payload.get("results_path")),
            export_path=_normalize_path(payload.get("export_path")),
            snapshot_path=_normalize_path(payload.get("snapshot_path")),
            manifest_path=_normalize_path(payload.get("manifest_path")),
            report_path=_normalize_path(payload.get("report_path")),
            frame_count=int(payload.get("frame_count", 0)),
            history_count=int(payload.get("history_count", 0)),
            summary_count=int(payload.get("summary_count", 0)),
            last_messages=tuple(str(message) for message in payload.get("last_messages", ())),
            error_count=int(payload.get("error_count", 0)),
            warning_count=int(payload.get("warning_count", 0)),
            model_name=None if payload.get("model_name") in {None, ""} else str(payload["model_name"]),
            job_name=None if payload.get("job_name") in {None, ""} else str(payload["job_name"]),
            procedure_type=None if payload.get("procedure_type") in {None, ""} else str(payload["procedure_type"]),
            results_backend=None if payload.get("results_backend") in {None, ""} else str(payload["results_backend"]),
            export_format=None if payload.get("export_format") in {None, ""} else str(payload["export_format"]),
            current_action=None if payload.get("current_action") in {None, ""} else str(payload["current_action"]),
        )


@dataclass(slots=True, frozen=True)
class GuiJobMessageBuckets:
    """定义 Job Monitor 中的消息分类结果。"""

    log_messages: tuple[str, ...]
    error_messages: tuple[str, ...]
    warning_messages: tuple[str, ...]
    output_messages: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class JobDiagnosticsSnapshot:
    """定义 Diagnostics 弹窗消费的轻量诊断摘要。"""

    headline: str
    run_ready: bool
    status_text: str
    problem_lines: tuple[str, ...]
    recommendation_lines: tuple[str, ...]
    error_lines: tuple[str, ...]
    warning_lines: tuple[str, ...]
    artifact_lines: tuple[str, ...]
    latest_record_id: str | None = None


class GuiJobRecordStore:
    """负责在当前 GUI 会话中维护 Job 记录。"""

    def __init__(self) -> None:
        self._records_by_id: dict[str, GuiJobRecord] = {}

    def put(self, record: GuiJobRecord) -> GuiJobRecord:
        """新增或覆盖一条记录。"""

        self._records_by_id[record.record_id] = record
        return record

    def get(self, record_id: str | None) -> GuiJobRecord | None:
        """按记录编号返回记录。"""

        if record_id in {None, ""}:
            return None
        return self._records_by_id.get(str(record_id))

    def remove(self, record_id: str | None) -> None:
        """移除一条记录。"""

        if record_id in {None, ""}:
            return
        self._records_by_id.pop(str(record_id), None)

    def clear(self) -> None:
        """清空当前会话中的所有记录。"""

        self._records_by_id.clear()

    def records(self) -> tuple[GuiJobRecord, ...]:
        """返回按创建时间倒序排列的记录列表。"""

        return tuple(sorted(self._records_by_id.values(), key=lambda item: (item.created_at, item.record_id), reverse=True))

    def latest(self) -> GuiJobRecord | None:
        """返回最近的一条记录。"""

        records = self.records()
        return None if not records else records[0]

    def has_records(self) -> bool:
        """返回当前是否已有任何记录。"""

        return bool(self._records_by_id)


def classify_job_message(message: str) -> str:
    """根据关键字对监视消息进行粗分类。"""

    lowered = message.lower()
    if any(token in lowered for token in ("error", "failed", "exception", "traceback", "fatal")):
        return "error"
    if any(token in lowered for token in ("warning", "warn", "unsupported", "stale")):
        return "warning"
    if any(token in lowered for token in ("results", "export", "vtk", "output", "snapshot", "manifest", "report", "written")):
        return "output"
    return "log"


def bucketize_job_messages(messages: tuple[str, ...]) -> GuiJobMessageBuckets:
    """将消息序列按 Monitor 标签页所需类别拆分。"""

    log_messages: list[str] = []
    error_messages: list[str] = []
    warning_messages: list[str] = []
    output_messages: list[str] = []

    for message in messages:
        category = classify_job_message(message)
        log_messages.append(message)
        if category == "error":
            error_messages.append(message)
        elif category == "warning":
            warning_messages.append(message)
        elif category == "output":
            output_messages.append(message)

    return GuiJobMessageBuckets(
        log_messages=tuple(log_messages),
        error_messages=tuple(error_messages),
        warning_messages=tuple(warning_messages),
        output_messages=tuple(output_messages),
    )
