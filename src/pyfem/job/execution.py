"""作业执行外壳与标准化运行入口。"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from pyfem.compiler import Compiler, RuntimeRegistry
from pyfem.foundation.errors import PyFEMError
from pyfem.io import ResultsReader
from pyfem.modeldb import ModelDB
from pyfem.procedures.base import ProcedureReport


def resolve_step_name(model: ModelDB, requested_step_name: str | None) -> str:
    """解析本次需要执行的正式步骤名称。"""

    if requested_step_name is not None:
        if requested_step_name not in model.steps:
            raise PyFEMError(f"模型中不存在步骤 {requested_step_name}。")
        return requested_step_name

    if model.job is not None and model.job.step_names:
        if len(model.job.step_names) == 1:
            return model.job.step_names[0]
        raise PyFEMError("当前作业包含多个步骤，请显式指定 step_name。")

    if len(model.steps) == 1:
        return next(iter(model.steps))
    if not model.steps:
        raise PyFEMError("当前模型中没有可运行的步骤。")
    raise PyFEMError("当前模型包含多个步骤，请显式指定 step_name。")


def build_default_results_path(input_path: Path) -> Path:
    """为输入文件构造默认结果路径。"""

    return input_path.with_suffix(".results.json")


def build_default_export_path(input_path: Path, export_format: str) -> Path:
    """为输入文件构造默认导出路径。"""

    normalized_export_format = export_format.lstrip(".")
    return input_path.with_suffix(f".{normalized_export_format}")


@dataclass(slots=True, frozen=True)
class JobExecutionRequest:
    """定义一次标准化作业执行请求。"""

    input_path: str | Path | None = None
    model: ModelDB | None = None
    model_name: str | None = None
    importer_key: str = "inp"
    step_name: str | None = None
    results_backend: str = "json"
    results_path: str | Path | None = None
    export_format: str | None = None
    export_path: str | Path | None = None

    def __post_init__(self) -> None:
        source_count = int(self.input_path is not None) + int(self.model is not None)
        if source_count != 1:
            raise PyFEMError("JobExecutionRequest 必须且只能提供 input_path 或 model 之一。")
        if self.export_format is None and self.export_path is not None:
            raise PyFEMError("仅在指定 export_format 时才允许提供 export_path。")


@dataclass(slots=True, frozen=True)
class JobExecutionReport:
    """描述一次标准化作业执行结果。"""

    model_name: str
    job_name: str | None
    step_name: str
    procedure_type: str
    results_backend: str
    results_path: Path | None
    export_format: str | None
    export_path: Path | None
    frame_count: int
    history_count: int
    summary_count: int
    monitor_messages: tuple[str, ...] = ()


class JobMonitor:
    """定义最小作业监控输出接口。"""

    def message(self, text: str) -> None:
        """记录一条作业消息。"""

    def snapshot(self) -> tuple[str, ...]:
        """返回当前已经记录的消息。"""

        return ()


class InMemoryJobMonitor(JobMonitor):
    """基于内存的最小 monitor。"""

    def __init__(self) -> None:
        self._messages: list[str] = []

    def message(self, text: str) -> None:
        self._messages.append(text)

    def snapshot(self) -> tuple[str, ...]:
        return tuple(self._messages)


class ConsoleJobMonitor(InMemoryJobMonitor):
    """将 monitor 消息同时输出到终端。"""

    def __init__(self, stream: TextIO | None = None) -> None:
        super().__init__()
        self._stream = sys.stdout if stream is None else stream

    def message(self, text: str) -> None:
        super().message(text)
        print(f"[job] {text}", file=self._stream)


@dataclass(slots=True)
class JobManager:
    """封装统一的模型加载、编译、执行、结果写出与导出流程。"""

    registry: RuntimeRegistry = field(default_factory=RuntimeRegistry)

    def execute(self, request: JobExecutionRequest, monitor: JobMonitor | None = None) -> JobExecutionReport:
        """按正式主线执行一次作业请求。"""

        job_monitor = InMemoryJobMonitor() if monitor is None else monitor

        model = self._load_model(request, job_monitor)
        results_path = self._resolve_results_path(request)
        export_path = self._resolve_export_path(request)

        job_monitor.message(f"编译模型 {model.name}")
        compiled_model = Compiler(registry=self.registry).compile(model)

        step_name = resolve_step_name(model, request.step_name)
        step_definition = model.steps[step_name]
        job_monitor.message(f"执行步骤 {step_name}")
        results_writer = self._create_results_writer(request.results_backend, results_path)
        procedure_report = compiled_model.get_step_runtime(step_name).run(results_writer)

        results_reader = self._resolve_results_reader(
            results_backend=request.results_backend,
            results_path=results_path,
            results_writer=results_writer,
        )

        if request.export_format is not None:
            if export_path is None:
                raise PyFEMError("导出请求缺少 export_path。")
            if results_reader is None:
                raise PyFEMError("当前作业无法为 exporter 提供正式 ResultsReader。")
            job_monitor.message(f"导出结果 {request.export_format} -> {export_path}")
            exporter = self.registry.create_exporter(request.export_format)
            exporter.export(
                model=model,
                results_reader=results_reader,
                path=export_path,
                step_name=step_name,
            )

        summary_count = self._resolve_summary_count(step_name, results_reader)
        job_monitor.message(f"作业完成 {model.name}:{step_name}")

        return JobExecutionReport(
            model_name=model.name,
            job_name=None if model.job is None else model.job.name,
            step_name=step_name,
            procedure_type=step_definition.procedure_type,
            results_backend=request.results_backend,
            results_path=results_path,
            export_format=request.export_format,
            export_path=export_path,
            frame_count=procedure_report.frame_count,
            history_count=procedure_report.history_count,
            summary_count=summary_count,
            monitor_messages=job_monitor.snapshot(),
        )

    def run_input_file(
        self,
        input_path: str | Path,
        *,
        model_name: str | None = None,
        importer_key: str = "inp",
        step_name: str | None = None,
        results_backend: str = "json",
        results_path: str | Path | None = None,
        export_format: str | None = None,
        export_path: str | Path | None = None,
        monitor: JobMonitor | None = None,
    ) -> JobExecutionReport:
        """执行一个基于输入文件的标准化作业。"""

        return self.execute(
            JobExecutionRequest(
                input_path=input_path,
                model_name=model_name,
                importer_key=importer_key,
                step_name=step_name,
                results_backend=results_backend,
                results_path=results_path,
                export_format=export_format,
                export_path=export_path,
            ),
            monitor=monitor,
        )

    def run_model(
        self,
        model: ModelDB,
        *,
        step_name: str | None = None,
        results_backend: str = "json",
        results_path: str | Path | None = None,
        export_format: str | None = None,
        export_path: str | Path | None = None,
        monitor: JobMonitor | None = None,
    ) -> JobExecutionReport:
        """执行一个基于既有 ModelDB 的标准化作业。"""

        return self.execute(
            JobExecutionRequest(
                model=model,
                step_name=step_name,
                results_backend=results_backend,
                results_path=results_path,
                export_format=export_format,
                export_path=export_path,
            ),
            monitor=monitor,
        )

    def load_model_from_file(
        self,
        input_path: str | Path,
        *,
        model_name: str | None = None,
        importer_key: str = "inp",
    ) -> ModelDB:
        """通过正式 importer 加载模型。"""

        resolved_input_path = Path(input_path)
        if not resolved_input_path.exists():
            raise PyFEMError(f"输入文件不存在: {resolved_input_path}")
        importer = self.registry.create_importer(importer_key)
        return importer.import_file(resolved_input_path, model_name=model_name)

    def _load_model(self, request: JobExecutionRequest, monitor: JobMonitor) -> ModelDB:
        """根据执行请求解析模型来源。"""

        if request.model is not None:
            monitor.message(f"使用内存模型 {request.model.name}")
            return request.model

        if request.input_path is None:
            raise PyFEMError("作业请求缺少 input_path。")

        input_path = Path(request.input_path)
        if not input_path.exists():
            raise PyFEMError(f"输入文件不存在: {input_path}")
        monitor.message(f"加载模型 {input_path}")
        importer = self.registry.create_importer(request.importer_key)
        return importer.import_file(input_path, model_name=request.model_name)

    def _resolve_results_path(self, request: JobExecutionRequest) -> Path | None:
        """解析结果写出路径。"""

        if request.results_path is not None:
            return Path(request.results_path)
        if request.results_backend == "json":
            if request.input_path is None:
                raise PyFEMError("JSON results backend 需要 results_path，或提供 input_path 以生成默认路径。")
            return build_default_results_path(Path(request.input_path))
        return None

    def _resolve_export_path(self, request: JobExecutionRequest) -> Path | None:
        """解析导出路径。"""

        if request.export_format is None:
            return None
        if request.export_path is not None:
            return Path(request.export_path)
        if request.input_path is None:
            raise PyFEMError("导出请求需要 export_path，或提供 input_path 以生成默认导出路径。")
        return build_default_export_path(Path(request.input_path), request.export_format)

    def _create_results_writer(self, results_backend: str, results_path: Path | None):
        """创建正式结果写出器。"""

        if results_path is None:
            return self.registry.create_results_writer(results_backend)
        return self.registry.create_results_writer(results_backend, results_path)

    def _resolve_results_reader(
        self,
        *,
        results_backend: str,
        results_path: Path | None,
        results_writer,
    ) -> ResultsReader | None:
        """为导出与后处理解析正式 ResultsReader。"""

        if isinstance(results_writer, ResultsReader):
            return results_writer
        if results_path is None:
            return None
        return self.registry.create_results_reader(results_backend, results_path)

    def _resolve_summary_count(self, step_name: str, results_reader: ResultsReader | None) -> int:
        """读取执行后步骤摘要数量。"""

        if results_reader is None:
            return 0
        return len(results_reader.read_step(step_name).summaries)
