"""脚本友好的平台 session facade。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pyfem.compiler import RuntimeRegistry
from pyfem.job import JobExecutionReport, JobManager, JobMonitor
from pyfem.modeldb import ModelDB
from pyfem.plugins.discovery import DiscoveredPluginManifest, PluginDiscoveryService
from pyfem.post import ResultsFacade


@dataclass(slots=True)
class PyFEMSession:
    """封装脚本友好的正式平台入口。"""

    registry: RuntimeRegistry = field(default_factory=RuntimeRegistry)
    plugin_discovery: PluginDiscoveryService = field(default_factory=PluginDiscoveryService)
    job_manager: JobManager = field(init=False)

    def __post_init__(self) -> None:
        self.job_manager = JobManager(registry=self.registry)

    def load_model_from_file(
        self,
        input_path: str | Path,
        *,
        model_name: str | None = None,
        importer_key: str = "inp",
    ) -> ModelDB:
        """通过正式 importer 加载模型。"""

        return self.job_manager.load_model_from_file(input_path, model_name=model_name, importer_key=importer_key)

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
        """执行一个基于输入文件的标准作业。"""

        return self.job_manager.run_input_file(
            input_path=input_path,
            model_name=model_name,
            importer_key=importer_key,
            step_name=step_name,
            results_backend=results_backend,
            results_path=results_path,
            export_format=export_format,
            export_path=export_path,
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
        """执行一个基于既有 ModelDB 的标准作业。"""

        return self.job_manager.run_model(
            model=model,
            step_name=step_name,
            results_backend=results_backend,
            results_path=results_path,
            export_format=export_format,
            export_path=export_path,
            monitor=monitor,
        )

    def open_results(self, results_path: str | Path, *, backend_key: str = "json") -> ResultsFacade:
        """打开正式结果并返回 reader-only facade。"""

        reader = self.registry.create_results_reader(backend_key, Path(results_path))
        return ResultsFacade(reader)

    def export_results(
        self,
        *,
        input_path: str | Path,
        results_path: str | Path,
        export_path: str | Path,
        export_format: str = "vtk",
        model_name: str | None = None,
        importer_key: str = "inp",
        results_backend: str = "json",
        step_name: str | None = None,
    ) -> Path:
        """通过正式 importer、reader 与 exporter 导出既有结果。"""

        model = self.load_model_from_file(input_path, model_name=model_name, importer_key=importer_key)
        results = self.open_results(results_path, backend_key=results_backend)
        exporter = self.registry.create_exporter(export_format)
        return exporter.export(
            model=model,
            results_reader=results.results_reader,
            path=Path(export_path),
            step_name=step_name,
        )

    def discover_plugin_manifests(
        self,
        *search_roots: str | Path,
    ) -> tuple[DiscoveredPluginManifest, ...]:
        """发现插件 manifest。"""

        return self.plugin_discovery.discover(*search_roots)

    def register_discovered_plugins(self, *search_roots: str | Path) -> tuple[DiscoveredPluginManifest, ...]:
        """发现并注册插件 manifest。"""

        discovered = self.discover_plugin_manifests(*search_roots)
        self.plugin_discovery.register_into_registry(self.registry, discovered)
        return discovered
