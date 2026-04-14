"""可编辑配置的 INP 求解脚本。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pyfem.foundation.errors import PyFEMError
from pyfem.job import ConsoleJobMonitor, JobExecutionReport, JobManager

# 直接修改这里即可运行自己的算例。
INP_PATH = "Job-1.inp"
MODEL_NAME = None
STEP_NAME = None
WRITE_VTK = True
RESULTS_PATH = None
VTK_PATH = None
REPORT_PATH = None


def _read_text_override(name: str, default_value: str | None) -> str | None:
    value = os.getenv(name)
    return default_value if value in {None, ""} else value


def _read_bool_override(name: str, default_value: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default_value
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _resolve_path(raw_path: str | None) -> Path | None:
    if raw_path is None:
        return None
    path = Path(raw_path)
    return path if path.is_absolute() else (ROOT / path).resolve()


def _build_report_payload(report: JobExecutionReport) -> dict[str, object]:
    return {
        "model_name": report.model_name,
        "job_name": report.job_name,
        "step_name": report.step_name,
        "procedure_type": report.procedure_type,
        "results_backend": report.results_backend,
        "results_path": None if report.results_path is None else str(report.results_path),
        "export_format": report.export_format,
        "export_path": None if report.export_path is None else str(report.export_path),
        "frame_count": report.frame_count,
        "history_count": report.history_count,
        "summary_count": report.summary_count,
        "monitor_messages": list(report.monitor_messages),
    }


def _write_report(path: Path, report: JobExecutionReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_build_report_payload(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    """按脚本顶部配置运行一次算例。"""

    inp_path = _resolve_path(_read_text_override("PYFEM_INP_PATH", INP_PATH))
    if inp_path is None or not inp_path.exists():
        raise PyFEMError(f"输入文件不存在: {inp_path}")

    model_name = _read_text_override("PYFEM_MODEL_NAME", MODEL_NAME)
    step_name = _read_text_override("PYFEM_STEP_NAME", STEP_NAME)
    results_path = _resolve_path(_read_text_override("PYFEM_RESULTS_PATH", RESULTS_PATH))
    write_vtk = _read_bool_override("PYFEM_WRITE_VTK", WRITE_VTK)
    vtk_path = _resolve_path(_read_text_override("PYFEM_VTK_PATH", VTK_PATH))
    report_path = _resolve_path(_read_text_override("PYFEM_REPORT_PATH", REPORT_PATH))

    job_manager = JobManager()
    monitor = ConsoleJobMonitor()
    report = job_manager.run_input_file(
        inp_path,
        model_name=model_name,
        step_name=step_name,
        results_path=results_path,
        export_format="vtk" if write_vtk else None,
        export_path=vtk_path,
        monitor=monitor,
    )

    print(f"model = {report.model_name}")
    print(f"step = {report.step_name}")
    print(f"results = {report.results_path}")
    print(f"frame_count = {report.frame_count}")
    print(f"history_count = {report.history_count}")
    if report.export_path is not None:
        print(f"vtk = {report.export_path}")
    if report_path is not None:
        _write_report(report_path, report)
        print(f"report = {report_path}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PyFEMError as error:
        print(f"求解失败: {error}", file=sys.stderr)
        raise SystemExit(1)
