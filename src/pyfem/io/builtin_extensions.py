"""内置 IO 扩展注册。"""

from __future__ import annotations

from pyfem.io.inp import InpImporter
from pyfem.io.results import InMemoryResultsWriter, JsonResultsReader, JsonResultsWriter
from pyfem.io.vtk import VtkExporter


def register_builtin_io_extensions(registry) -> None:
    """向统一注册表写入内置 importer / exporter / results IO 扩展。"""

    registry.register_importer("inp", InpImporter)
    registry.register_results_writer("json", JsonResultsWriter)
    registry.register_results_writer("memory", InMemoryResultsWriter)
    registry.register_results_reader("json", JsonResultsReader)
    registry.register_exporter("vtk", VtkExporter)
