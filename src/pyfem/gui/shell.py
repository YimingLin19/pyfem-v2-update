"""最小 GUI 控制壳。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from pyfem.api import PyFEMSession
from pyfem.foundation.errors import PyFEMError
from pyfem.job import (
    JobExecutionReport,
    JobMonitor,
    JobSnapshot,
    JobSnapshotService,
    build_default_export_path,
    build_default_results_path,
)
from pyfem.modeldb import ModelDB
from pyfem.post import (
    ResultFieldOverview,
    ResultFrameOverview,
    ResultHistoryOverview,
    ResultStepOverview,
    ResultSummaryOverview,
    ResultsFacade,
)


@dataclass(slots=True, frozen=True)
class GuiModelSummary:
    """定义 GUI 侧展示的模型概要。"""

    source_path: Path
    model_name: str
    part_names: tuple[str, ...]
    step_names: tuple[str, ...]
    has_assembly: bool
    part_count: int
    instance_count: int


@dataclass(slots=True, frozen=True)
class GuiModelNavigationSnapshot:
    """定义 GUI 导航树消费的轻量模型快照。"""

    source_path: Path
    model_name: str
    part_names: tuple[str, ...]
    instance_names: tuple[str, ...]
    material_names: tuple[str, ...]
    section_names: tuple[str, ...]
    step_names: tuple[str, ...]
    boundary_names: tuple[str, ...]
    nodal_load_names: tuple[str, ...]
    distributed_load_names: tuple[str, ...]
    output_request_names: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class GuiResultsEntry:
    """定义 GUI 侧展示的结果步骤入口。"""

    step_name: str
    procedure_type: str | None
    frame_count: int
    history_count: int
    summary_count: int
    field_names: tuple[str, ...] = ()
    history_names: tuple[str, ...] = ()
    summary_names: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class GuiMeshGeometry:
    """定义 GUI 视图区使用的稳定网格几何上下文。"""

    model_name: str
    point_keys: tuple[str, ...]
    points: tuple[tuple[float, float, float], ...]
    cell_connectivities: tuple[tuple[int, ...], ...]
    cell_keys: tuple[str, ...]
    vtk_cell_types: tuple[int, ...]


@dataclass(slots=True, frozen=True)
class GuiResultsViewContext:
    """定义结果浏览与视图区共享的正式上下文。"""

    results_path: Path
    mesh_geometry: GuiMeshGeometry
    results_facade: ResultsFacade


@dataclass(slots=True, frozen=True)
class GuiResultsLoadResult:
    """定义一次结果打开操作返回的 GUI 结果包。"""

    results_path: Path
    entries: tuple[GuiResultsEntry, ...]
    view_context: GuiResultsViewContext


@dataclass(slots=True, frozen=True)
class GuiRunProcessRequest:
    """定义 GUI 运行作业时的外进程执行请求。"""

    program: str
    arguments: tuple[str, ...]
    working_directory: Path
    environment: dict[str, str]
    report_path: Path


@dataclass(slots=True)
class GuiShellState:
    """定义最小 GUI 壳的可观察状态。"""

    opened_model: GuiModelSummary | None = None
    last_job_report: JobExecutionReport | None = None
    model_dirty: bool = False
    last_export_snapshot: JobSnapshot | None = None
    last_run_snapshot: JobSnapshot | None = None
    current_results_path: Path | None = None
    results_entries: tuple[GuiResultsEntry, ...] = ()


@dataclass(slots=True)
class GuiShell:
    """封装不侵入内核的最小 GUI 控制壳。"""

    session: PyFEMSession = field(default_factory=PyFEMSession)
    state: GuiShellState = field(default_factory=GuiShellState)
    snapshot_service: JobSnapshotService = field(default_factory=JobSnapshotService)
    _loaded_model: ModelDB | None = field(default=None, init=False, repr=False)

    def open_model(self, input_path: str | Path, *, model_name: str | None = None) -> GuiModelSummary:
        """打开一个模型文件并生成 GUI 概要。"""

        resolved_path = Path(input_path)
        model = self.session.load_model_from_file(resolved_path, model_name=model_name)
        self._loaded_model = model
        summary = self._build_model_summary(model, resolved_path)
        self.state.opened_model = summary
        self.state.model_dirty = False
        self.state.last_export_snapshot = None
        self.state.last_run_snapshot = None
        return summary

    def build_model_summary(self) -> GuiModelSummary:
        """基于当前活模型重新构建 GUI 摘要。"""

        model = self._require_loaded_model()
        summary = self._build_model_summary(model, self._current_source_path())
        self.state.opened_model = summary
        return summary

    def clone_loaded_model(self) -> ModelDB:
        """返回当前活模型的深拷贝。"""

        return deepcopy(self._require_loaded_model())

    def replace_loaded_model(
        self,
        model: ModelDB,
        *,
        source_path: str | Path | None = None,
        mark_dirty: bool,
    ) -> GuiModelSummary:
        """以新的活模型替换 GUI 当前模型状态。"""

        resolved_source_path = self._current_source_path() if source_path is None else Path(source_path)
        self._loaded_model = model
        summary = self._build_model_summary(model, resolved_source_path)
        self.state.opened_model = summary
        self.state.model_dirty = bool(mark_dirty)
        if mark_dirty:
            self.state.last_run_snapshot = None
        return summary

    def mark_model_dirty(self) -> None:
        """显式标记当前活模型已被修改。"""

        self.state.model_dirty = True
        self.state.last_run_snapshot = None

    def write_current_model_snapshot(self, target_path: str | Path) -> JobSnapshot:
        """将当前活模型写出为显式 snapshot。"""

        snapshot = self.snapshot_service.write_snapshot(
            self._require_loaded_model(),
            snapshot_path=target_path,
            source_model_path=self._current_source_path(),
            snapshot_kind="export",
        )
        self.state.last_export_snapshot = snapshot
        return snapshot

    def save_current_model_as_derived_case(self, target_path: str | Path) -> JobSnapshot:
        """将当前活模型另存为 Derived Case 并切换来源路径。"""

        snapshot = self.snapshot_service.write_snapshot(
            self._require_loaded_model(),
            snapshot_path=target_path,
            source_model_path=self._current_source_path(),
            snapshot_kind="derived_case",
            derived_case_path=target_path,
        )
        self.state.last_export_snapshot = snapshot
        self.state.last_run_snapshot = None
        self.replace_loaded_model(self._require_loaded_model(), source_path=Path(target_path), mark_dirty=False)
        return snapshot

    def latest_snapshot(self) -> JobSnapshot | None:
        """返回当前 GUI 状态下最近一次可复用的 snapshot。"""

        candidates = [snapshot for snapshot in (self.state.last_export_snapshot, self.state.last_run_snapshot) if snapshot is not None]
        if not candidates:
            return None
        return max(candidates, key=lambda snapshot: snapshot.created_at)

    def read_snapshot_manifest(self, manifest_path: str | Path) -> tuple[JobSnapshot, str]:
        """按指定 manifest 路径读取 snapshot 文本与对象。"""

        resolved_manifest_path = Path(manifest_path)
        if not resolved_manifest_path.exists():
            raise PyFEMError(f"snapshot manifest 不存在: {resolved_manifest_path}")
        manifest_text = resolved_manifest_path.read_text(encoding="utf-8")
        payload = json.loads(manifest_text)
        return self._snapshot_from_manifest_payload(payload, resolved_manifest_path), manifest_text

    def run_last_snapshot(
        self,
        *,
        step_name: str | None = None,
        export_vtk: bool = False,
        vtk_path: str | Path | None = None,
        monitor: JobMonitor | None = None,
    ) -> JobExecutionReport:
        """复跑最近一次 snapshot，而不是重新冻结当前活动模型。"""

        snapshot = self.latest_snapshot()
        if snapshot is None:
            raise PyFEMError("当前 GUI 壳没有可复用的 snapshot。")
        report = self.snapshot_service.run_snapshot(
            snapshot,
            step_name=step_name,
            monitor=monitor,
            export_format="vtk" if export_vtk else None,
            export_path=vtk_path,
        )
        self.state.last_job_report = report
        self.state.last_run_snapshot = snapshot
        self.state.current_results_path = report.results_path
        return report

    def run_snapshot(
        self,
        snapshot: JobSnapshot,
        *,
        step_name: str | None = None,
        export_vtk: bool = False,
        vtk_path: str | Path | None = None,
        monitor: JobMonitor | None = None,
    ) -> JobExecutionReport:
        """运行指定的 snapshot，并回写 GUI 最近一次运行状态。"""

        report = self.snapshot_service.run_snapshot(
            snapshot,
            step_name=step_name,
            monitor=monitor,
            export_format="vtk" if export_vtk else None,
            export_path=vtk_path,
        )
        self.state.last_job_report = report
        self.state.last_run_snapshot = snapshot
        self.state.current_results_path = report.results_path
        return report

    def read_latest_snapshot_manifest(self) -> tuple[JobSnapshot, str]:
        """读取最近一次 snapshot manifest 的正式文本内容。"""

        snapshot = self.latest_snapshot()
        if snapshot is None:
            raise PyFEMError("当前 GUI 壳没有可读取的 snapshot manifest。")
        return snapshot, snapshot.manifest_path.read_text(encoding="utf-8")

    def build_default_results_path(self) -> Path:
        """返回当前打开模型的默认 results 路径。"""

        if self.state.opened_model is None:
            raise PyFEMError("当前 GUI 壳没有已打开模型，无法生成默认结果路径。")
        return build_default_results_path(self.state.opened_model.source_path)

    def build_default_vtk_path(self) -> Path:
        """返回当前打开模型的默认 VTK 路径。"""

        if self.state.opened_model is None:
            raise PyFEMError("当前 GUI 壳没有已打开模型，无法生成默认 VTK 路径。")
        return build_default_export_path(self.state.opened_model.source_path, "vtk")

    def build_model_navigation_snapshot(self) -> GuiModelNavigationSnapshot:
        """返回当前模型在 GUI 工作台中的导航快照。"""

        model = self._require_loaded_model()
        instance_names = tuple(model.assembly.instances.keys()) if model.assembly is not None else ()
        source_path = self.state.opened_model.source_path if self.state.opened_model is not None else Path(model.name)
        return GuiModelNavigationSnapshot(
            source_path=source_path,
            model_name=model.name,
            part_names=tuple(model.parts.keys()),
            instance_names=instance_names,
            material_names=tuple(model.materials.keys()),
            section_names=tuple(model.sections.keys()),
            step_names=tuple(model.steps.keys()),
            boundary_names=tuple(model.boundaries.keys()),
            nodal_load_names=tuple(model.nodal_loads.keys()),
            distributed_load_names=tuple(model.distributed_loads.keys()),
            output_request_names=tuple(model.output_requests.keys()),
        )

    def submit_job(
        self,
        *,
        step_name: str | None = None,
        results_path: str | Path | None = None,
        export_vtk: bool = False,
        vtk_path: str | Path | None = None,
        monitor: JobMonitor | None = None,
    ) -> JobExecutionReport:
        """提交当前打开模型的最小 job。"""

        if self.state.opened_model is None:
            raise PyFEMError("当前 GUI 壳没有已打开模型，无法提交 job。")

        run_snapshot = self.snapshot_service.write_snapshot(
            self._require_loaded_model(),
            snapshot_path=self.snapshot_service.build_run_snapshot_path(
                self._current_source_path(),
                self.state.opened_model.model_name,
            ),
            source_model_path=self._current_source_path(),
            snapshot_kind="run",
            results_path=results_path,
        )
        report = self.snapshot_service.run_snapshot(
            run_snapshot,
            step_name=step_name,
            monitor=monitor,
            export_format="vtk" if export_vtk else None,
            export_path=vtk_path,
        )
        self.state.last_job_report = report
        self.state.last_run_snapshot = run_snapshot
        self.state.current_results_path = report.results_path
        return report

    def build_run_process_request(
        self,
        *,
        step_name: str | None = None,
        results_path: str | Path | None = None,
        export_vtk: bool = False,
        vtk_path: str | Path | None = None,
    ) -> GuiRunProcessRequest:
        """构建用于 GUI 外进程求解的标准化请求。"""

        if self.state.opened_model is None:
            raise PyFEMError("当前 GUI 壳没有已打开模型，无法构建外进程求解请求。")

        resolved_input_path = self._resolve_process_path(self.state.opened_model.source_path)
        resolved_results_path = self.build_default_results_path() if results_path is None else Path(results_path)
        resolved_results_path = self._resolve_process_path(resolved_results_path)
        resolved_vtk_path = None
        if export_vtk:
            resolved_vtk_path = self.build_default_vtk_path() if vtk_path is None else Path(vtk_path)
            resolved_vtk_path = self._resolve_process_path(resolved_vtk_path)

        report_path = self._build_run_process_report_path(resolved_results_path)
        project_root = self._project_root()
        environment = {
            "PYFEM_INP_PATH": str(resolved_input_path),
            "PYFEM_MODEL_NAME": self.state.opened_model.model_name,
            "PYFEM_RESULTS_PATH": str(resolved_results_path),
            "PYFEM_WRITE_VTK": "1" if export_vtk else "0",
            "PYFEM_REPORT_PATH": str(report_path),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
        if step_name is not None:
            environment["PYFEM_STEP_NAME"] = step_name
        if resolved_vtk_path is not None:
            environment["PYFEM_VTK_PATH"] = str(resolved_vtk_path)

        return GuiRunProcessRequest(
            program=sys.executable,
            arguments=(str(project_root / "run_case.py"),),
            working_directory=project_root,
            environment=environment,
            report_path=report_path,
        )

    def execute_run_process(
        self,
        request: GuiRunProcessRequest,
        *,
        log: Callable[[str], None] | None = None,
    ) -> JobExecutionReport:
        """通过外部 Python 进程执行 GUI 作业请求并回收报告。"""

        merged_environment = dict(os.environ)
        merged_environment.update(request.environment)
        command = [request.program, *request.arguments]
        process = subprocess.Popen(
            command,
            cwd=request.working_directory,
            env=merged_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        captured_lines: list[str] = []
        try:
            if log is not None:
                log(f"外部求解进程已启动: {' '.join(command)}")
            if process.stdout is not None:
                for line in process.stdout:
                    message = line.rstrip()
                    if not message:
                        continue
                    captured_lines.append(message)
                    if log is not None:
                        log(message)
            exit_code = process.wait()
        except Exception:
            process.kill()
            process.wait()
            raise
        finally:
            if process.stdout is not None:
                process.stdout.close()

        if exit_code != 0:
            detail = captured_lines[-1] if captured_lines else "未提供更多错误信息。"
            raise PyFEMError(f"外部求解进程返回退出码 {exit_code}: {detail}")
        if not request.report_path.exists():
            raise PyFEMError("外部求解进程未生成运行报告。")
        return self.load_run_process_report(request.report_path)

    def load_run_process_report(self, report_path: str | Path) -> JobExecutionReport:
        """读取 GUI 外进程求解回写的正式结果报告。"""

        payload = json.loads(Path(report_path).read_text(encoding="utf-8"))
        report = JobExecutionReport(
            model_name=str(payload["model_name"]),
            job_name=self._read_optional_string(payload.get("job_name")),
            step_name=str(payload["step_name"]),
            procedure_type=str(payload["procedure_type"]),
            results_backend=str(payload["results_backend"]),
            results_path=self._read_optional_path(payload.get("results_path")),
            export_format=self._read_optional_string(payload.get("export_format")),
            export_path=self._read_optional_path(payload.get("export_path")),
            frame_count=int(payload["frame_count"]),
            history_count=int(payload["history_count"]),
            summary_count=int(payload["summary_count"]),
            monitor_messages=tuple(str(message) for message in payload.get("monitor_messages", ())),
        )
        self.state.last_job_report = report
        self.state.current_results_path = report.results_path
        return report

    def open_results(self, results_path: str | Path | None = None) -> tuple[GuiResultsEntry, ...]:
        """打开结果并构建 GUI 侧的基础入口。"""

        return self.load_results_view(results_path).entries

    def load_results_view(self, results_path: str | Path | None = None) -> GuiResultsLoadResult:
        """打开结果并返回摘要与视图区正式上下文。"""

        resolved_results_path = self._resolve_results_path(results_path)
        results = self.open_results_facade(resolved_results_path)
        entries = tuple(self._build_results_entry(overview) for overview in results.step_overviews())
        self.state.current_results_path = resolved_results_path
        self.state.results_entries = entries
        return GuiResultsLoadResult(
            results_path=resolved_results_path,
            entries=entries,
            view_context=GuiResultsViewContext(
                results_path=resolved_results_path,
                mesh_geometry=self.build_viewport_geometry(),
                results_facade=results,
            ),
        )

    def describe_results(self) -> tuple[str, ...]:
        """返回适合占位 GUI 展示的基础结果描述。"""

        return tuple(
            "step="
            f"{entry.step_name}, procedure={entry.procedure_type}, frames={entry.frame_count}, "
            f"histories={entry.history_count}, summaries={entry.summary_count}, "
            f"fields={','.join(entry.field_names) or '-'}, "
            f"history_names={','.join(entry.history_names) or '-'}, "
            f"summaries={','.join(entry.summary_names) or '-'}"
            for entry in self.state.results_entries
        )

    def export_results_vtk(
        self,
        *,
        step_name: str | None = None,
        results_path: str | Path | None = None,
        vtk_path: str | Path | None = None,
    ) -> Path:
        """将当前结果通过正式 exporter 导出为 VTK。"""

        if self.state.opened_model is None:
            raise PyFEMError("当前 GUI 壳没有已打开模型，无法导出 VTK。")

        resolved_results_path = self._resolve_results_path(results_path)
        resolved_vtk_path = Path(vtk_path) if vtk_path is not None else self.build_default_vtk_path()
        return self.session.export_results(
            input_path=self.state.opened_model.source_path,
            model_name=self.state.opened_model.model_name,
            results_path=resolved_results_path,
            export_path=resolved_vtk_path,
            export_format="vtk",
            step_name=step_name,
        )

    def open_results_facade(self, results_path: str | Path | None = None) -> ResultsFacade:
        """打开当前结果的正式 ResultsFacade。"""

        return self.session.open_results(self._resolve_results_path(results_path))

    def build_viewport_geometry(self) -> GuiMeshGeometry:
        """构建视图区使用的稳定几何上下文。"""

        model = self._require_loaded_model()
        points: list[tuple[float, float, float]] = []
        point_keys: list[str] = []
        point_indices: dict[str, int] = {}
        cell_connectivities: list[tuple[int, ...]] = []
        cell_keys: list[str] = []
        vtk_cell_types: list[int] = []

        for scope in model.iter_compilation_scopes():
            for node in scope.iter_node_geometry_records():
                qualified_name = scope.qualify_node_name(node.name)
                if qualified_name in point_indices:
                    continue
                coordinates = tuple(float(value) for value in node.coordinates)
                padded_coordinates = coordinates + (0.0,) * (3 - len(coordinates))
                point_indices[qualified_name] = len(points)
                point_keys.append(qualified_name)
                points.append((padded_coordinates[0], padded_coordinates[1], padded_coordinates[2]))

            for element in scope.part.elements.values():
                cell_connectivities.append(
                    tuple(point_indices[scope.qualify_node_name(node_name)] for node_name in element.node_names)
                )
                cell_keys.append(scope.qualify_element_name(element.name))
                vtk_cell_types.append(_vtk_cell_type(element.type_key))

        return GuiMeshGeometry(
            model_name=model.name,
            point_keys=tuple(point_keys),
            points=tuple(points),
            cell_connectivities=tuple(cell_connectivities),
            cell_keys=tuple(cell_keys),
            vtk_cell_types=tuple(vtk_cell_types),
        )

    def browse_step_overviews(
        self,
        *,
        step_name: str | None = None,
        frame_kind: str | None = None,
        axis_kind: str | None = None,
        field_name: str | None = None,
        target_key: str | None = None,
    ) -> tuple[ResultStepOverview, ...]:
        """通过 ResultsFacade 浏览步骤概要。"""

        return self._open_results_facade().step_overviews(
            step_name=step_name,
            frame_kind=frame_kind,
            axis_kind=axis_kind,
            field_name=field_name,
            target_key=target_key,
        )

    def browse_frames(
        self,
        *,
        step_name: str | None = None,
        frame_kind: str | None = None,
        axis_kind: str | None = None,
        field_name: str | None = None,
        target_key: str | None = None,
    ) -> tuple[ResultFrameOverview, ...]:
        """通过 ResultsFacade 浏览结果帧。"""

        return self._open_results_facade().frames(
            step_name=step_name,
            frame_kind=frame_kind,
            axis_kind=axis_kind,
            field_name=field_name,
            target_key=target_key,
        )

    def browse_fields(
        self,
        *,
        step_name: str | None = None,
        frame_id: int | None = None,
        frame_kind: str | None = None,
        axis_kind: str | None = None,
        field_name: str | None = None,
        target_key: str | None = None,
    ) -> tuple[ResultFieldOverview, ...]:
        """通过 ResultsFacade 浏览结果场。"""

        return self._open_results_facade().fields(
            step_name=step_name,
            frame_id=frame_id,
            frame_kind=frame_kind,
            axis_kind=axis_kind,
            field_name=field_name,
            target_key=target_key,
        )

    def browse_histories(
        self,
        *,
        step_name: str | None = None,
        history_name: str | None = None,
        axis_kind: str | None = None,
        target_key: str | None = None,
    ) -> tuple[ResultHistoryOverview, ...]:
        """通过 ResultsFacade 浏览历史量。"""

        return self._open_results_facade().histories(
            step_name=step_name,
            history_name=history_name,
            axis_kind=axis_kind,
            target_key=target_key,
        )

    def browse_summaries(
        self,
        *,
        step_name: str | None = None,
        summary_name: str | None = None,
        data_key: str | None = None,
    ) -> tuple[ResultSummaryOverview, ...]:
        """通过 ResultsFacade 浏览步骤摘要。"""

        return self._open_results_facade().summaries(
            step_name=step_name,
            summary_name=summary_name,
            data_key=data_key,
        )

    def _build_model_summary(self, model: ModelDB, source_path: Path) -> GuiModelSummary:
        instance_count = len(model.assembly.instances) if model.assembly is not None else 0
        return GuiModelSummary(
            source_path=source_path,
            model_name=model.name,
            part_names=tuple(model.parts.keys()),
            step_names=tuple(model.steps.keys()),
            has_assembly=model.assembly is not None,
            part_count=len(model.parts),
            instance_count=instance_count,
        )

    def _current_source_path(self) -> Path:
        if self.state.opened_model is not None:
            return self.state.opened_model.source_path
        model = self._require_loaded_model()
        return Path(f"{model.name}.inp")

    def _project_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

    def _resolve_process_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return (Path.cwd() / candidate).resolve()

    def _build_run_process_report_path(self, results_path: Path) -> Path:
        report_name = f"{results_path.stem}.gui-run-{uuid4().hex}.json"
        return results_path.with_name(report_name)

    def _snapshot_from_manifest_payload(self, payload: dict[str, object], manifest_path: Path) -> JobSnapshot:
        """将 manifest 字典还原为 JobSnapshot。"""

        return JobSnapshot(
            snapshot_id=str(payload["snapshot_id"]),
            snapshot_kind=str(payload["snapshot_kind"]),
            model_name=str(payload["model_name"]),
            snapshot_path=Path(str(payload["snapshot_path"])),
            manifest_path=manifest_path,
            results_path=Path(str(payload["results_path"])),
            source_model_path=self._read_optional_path(payload.get("source_model_path")),
            derived_case_path=self._read_optional_path(payload.get("derived_case_path")),
            created_at=str(payload["created_at"]),
        )

    def _read_optional_path(self, raw_value: object) -> Path | None:
        if raw_value in {None, ""}:
            return None
        return Path(str(raw_value))

    def _read_optional_string(self, raw_value: object) -> str | None:
        if raw_value in {None, ""}:
            return None
        return str(raw_value)

    def _resolve_results_path(self, results_path: str | Path | None) -> Path:
        """解析 GUI 当前需要打开的结果路径。"""

        if results_path is not None:
            return Path(results_path)
        if self.state.current_results_path is None:
            raise PyFEMError("当前 GUI 壳没有可用的结果路径。")
        return self.state.current_results_path

    def _open_results_facade(self) -> ResultsFacade:
        """打开当前 GUI 结果 facade。"""

        return self.open_results_facade(self._resolve_results_path(None))

    def _require_loaded_model(self) -> ModelDB:
        """返回当前已经加载的正式模型定义。"""

        if self._loaded_model is None:
            raise PyFEMError("当前 GUI 壳没有已加载模型，无法构建视图区几何。")
        return self._loaded_model

    def _build_results_entry(self, overview: ResultStepOverview) -> GuiResultsEntry:
        """将通用结果概要转换为 GUI 入口对象。"""

        return GuiResultsEntry(
            step_name=overview.step_name,
            procedure_type=overview.procedure_type,
            frame_count=overview.frame_count,
            history_count=overview.history_count,
            summary_count=overview.summary_count,
            field_names=overview.field_names,
            history_names=overview.history_names,
            summary_names=overview.summary_names,
        )


def _vtk_cell_type(type_key: str) -> int:
    """将当前单元类型映射到 VTK cell type。"""

    mapping = {"B21": 3, "CPS4": 9, "C3D8": 12}
    try:
        return mapping[type_key]
    except KeyError as error:
        raise PyFEMError(f"当前 GUI 视图区暂不支持单元类型 {type_key}。") from error
