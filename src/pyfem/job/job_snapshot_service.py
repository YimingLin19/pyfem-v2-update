"""定义 Job Snapshot 正式主线服务。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pyfem.foundation.errors import PyFEMError
from pyfem.io import InpExporter
from pyfem.job.execution import JobExecutionReport, JobManager, JobMonitor
from pyfem.modeldb import ModelDB


@dataclass(slots=True, frozen=True)
class JobSnapshot:
    """描述一个冻结后的作业快照。"""

    snapshot_id: str
    snapshot_kind: str
    model_name: str
    snapshot_path: Path
    manifest_path: Path
    results_path: Path
    source_model_path: Path | None
    derived_case_path: Path | None
    created_at: str

    def to_dict(self) -> dict[str, object]:
        """将快照信息序列化为字典。"""

        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_kind": self.snapshot_kind,
            "model_name": self.model_name,
            "snapshot_path": str(self.snapshot_path),
            "manifest_path": str(self.manifest_path),
            "results_path": str(self.results_path),
            "source_model_path": None if self.source_model_path is None else str(self.source_model_path),
            "derived_case_path": None if self.derived_case_path is None else str(self.derived_case_path),
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class JobSnapshotService:
    """负责导出、冻结并运行 Job Snapshot。"""

    exporter: InpExporter = field(default_factory=InpExporter)
    job_manager: JobManager = field(default_factory=JobManager)

    def write_snapshot(
        self,
        model: ModelDB,
        *,
        snapshot_path: str | Path,
        source_model_path: str | Path | None = None,
        snapshot_kind: str = "export",
        derived_case_path: str | Path | None = None,
        results_path: str | Path | None = None,
    ) -> JobSnapshot:
        """将当前模型冻结写出为 snapshot。"""

        resolved_snapshot_path = Path(snapshot_path)
        resolved_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self.exporter.export(model, resolved_snapshot_path)
        resolved_results_path = (
            resolved_snapshot_path.with_suffix(".results.json")
            if results_path is None
            else Path(results_path)
        )
        manifest_path = resolved_snapshot_path.with_suffix(".snapshot.json")
        snapshot = JobSnapshot(
            snapshot_id=uuid4().hex,
            snapshot_kind=snapshot_kind,
            model_name=model.name,
            snapshot_path=resolved_snapshot_path,
            manifest_path=manifest_path,
            results_path=resolved_results_path,
            source_model_path=None if source_model_path is None else Path(source_model_path),
            derived_case_path=None if derived_case_path is None else Path(derived_case_path),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        manifest_path.write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return snapshot

    def build_run_snapshot_path(self, source_model_path: str | Path | None, model_name: str) -> Path:
        """构造运行快照默认路径。"""

        if source_model_path is not None:
            resolved_source = Path(source_model_path)
            snapshot_dir = resolved_source.parent / ".pyfem_snapshots"
            snapshot_name = f"{resolved_source.stem}.run.{uuid4().hex[:8]}.inp"
            return snapshot_dir / snapshot_name
        workspace_dir = Path.cwd() / ".pyfem_snapshots"
        return workspace_dir / f"{model_name}.run.{uuid4().hex[:8]}.inp"

    def run_snapshot(
        self,
        snapshot: JobSnapshot,
        *,
        step_name: str | None = None,
        results_backend: str = "json",
        export_format: str | None = None,
        export_path: str | Path | None = None,
        monitor: JobMonitor | None = None,
    ) -> JobExecutionReport:
        """按正式主线运行一个冻结快照。"""

        if not snapshot.snapshot_path.exists():
            raise PyFEMError(f"快照文件不存在: {snapshot.snapshot_path}")
        report = self.job_manager.run_input_file(
            snapshot.snapshot_path,
            model_name=snapshot.model_name,
            step_name=step_name,
            results_backend=results_backend,
            results_path=snapshot.results_path,
            export_format=export_format,
            export_path=export_path,
            monitor=monitor,
        )
        payload = snapshot.to_dict()
        payload["last_run_report"] = {
            "step_name": report.step_name,
            "procedure_type": report.procedure_type,
            "results_backend": report.results_backend,
            "results_path": None if report.results_path is None else str(report.results_path),
            "export_format": report.export_format,
            "export_path": None if report.export_path is None else str(report.export_path),
            "frame_count": report.frame_count,
            "history_count": report.history_count,
            "summary_count": report.summary_count,
        }
        snapshot.manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return report
