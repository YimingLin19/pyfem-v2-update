"""GUI 测试辅助构件。"""

from __future__ import annotations

import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from pyfem.gui.shell import (
    GuiMeshGeometry,
    GuiModelNavigationSnapshot,
    GuiModelSummary,
    GuiResultsEntry,
    GuiResultsLoadResult,
    GuiResultsViewContext,
    GuiShellState,
)
from pyfem.io import (
    AXIS_KIND_FRAME_ID,
    FIELD_KEY_S,
    FIELD_KEY_S_AVG,
    FIELD_KEY_S_IP,
    FIELD_KEY_S_PRINCIPAL_IP,
    FIELD_KEY_S_REC,
    FIELD_KEY_S_VM_IP,
    FIELD_KEY_TIME,
    FIELD_KEY_U,
    FIELD_KEY_U_MAG,
    FRAME_KIND_SOLUTION,
    GLOBAL_HISTORY_TARGET,
    InMemoryResultsWriter,
    POSITION_ELEMENT_CENTROID,
    POSITION_ELEMENT_NODAL,
    POSITION_GLOBAL_HISTORY,
    POSITION_INTEGRATION_POINT,
    POSITION_NODE,
    POSITION_NODE_AVERAGED,
    RESULT_SOURCE_AVERAGED,
    RESULT_SOURCE_DERIVED,
    RESULT_SOURCE_RECOVERED,
    ResultField,
    ResultFrame,
    ResultHistorySeries,
    ResultSummary,
    ResultsSession,
)
from pyfem.job import JobExecutionReport
from pyfem.post import ResultsFacade
from pyfem.post.common import FIELD_METADATA_KEY_AVERAGING_GROUPS, FIELD_METADATA_KEY_BASE_TARGET_KEYS


def get_application() -> QApplication:
    application = QApplication.instance()
    if application is not None:
        return application
    return QApplication([])


def wait_for(predicate, *, timeout_seconds: float = 5.0) -> None:
    app = get_application()
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("等待 GUI 条件超时。")


def set_combo_data(combo_box, data: object) -> None:
    index = combo_box.findData(data)
    if index < 0:
        raise AssertionError(f"未找到 combo 数据: {data!r}")
    combo_box.setCurrentIndex(index)


def build_semantic_results_view_context() -> GuiResultsViewContext:
    writer = InMemoryResultsWriter()
    writer.open_session(
        ResultsSession(
            model_name="semantic-model",
            procedure_name="STEP-1",
            step_name="STEP-1",
            procedure_type="static_linear",
        )
    )
    writer.write_frame(
        ResultFrame(
            frame_id=0,
            step_name="STEP-1",
            time=0.0,
            frame_kind=FRAME_KIND_SOLUTION,
            axis_kind=AXIS_KIND_FRAME_ID,
            axis_value=0,
            fields=(
                ResultField(
                    name=FIELD_KEY_U,
                    position=POSITION_NODE,
                    values={
                        "part-1.n1": {"UX": 0.0, "UY": 0.0, "UZ": 0.0},
                        "part-1.n2": {"UX": 0.10, "UY": 0.01, "UZ": 0.0},
                        "part-1.n3": {"UX": 0.16, "UY": -0.02, "UZ": 0.0},
                        "part-1.n4": {"UX": 0.04, "UY": 0.03, "UZ": 0.0},
                    },
                    metadata={"unit": "mm"},
                ),
                ResultField(
                    name=FIELD_KEY_U_MAG,
                    position=POSITION_NODE,
                    values={
                        "part-1.n1": {"MAGNITUDE": 0.0},
                        "part-1.n2": {"MAGNITUDE": 0.1005},
                        "part-1.n3": {"MAGNITUDE": 0.1612},
                        "part-1.n4": {"MAGNITUDE": 0.0500},
                    },
                    source_type=RESULT_SOURCE_DERIVED,
                    metadata={"unit": "mm", "derived_from": FIELD_KEY_U},
                ),
                ResultField(
                    name=FIELD_KEY_S,
                    position=POSITION_ELEMENT_CENTROID,
                    values={"part-1.e1": {"S11": 12.0, "S22": 6.0, "S33": 0.0, "S12": 2.5, "S13": 0.0, "S23": 0.0}},
                    metadata={"unit": "MPa", "region": "plate"},
                ),
                ResultField(
                    name=FIELD_KEY_S_IP,
                    position=POSITION_INTEGRATION_POINT,
                    values={
                        "part-1.e1.ip1": {"S11": 10.0, "S22": 4.0, "S33": 0.0, "S12": 2.0, "S13": 0.0, "S23": 0.0},
                        "part-1.e1.ip2": {"S11": 14.0, "S22": 8.0, "S33": 0.0, "S12": 3.0, "S13": 0.0, "S23": 0.0},
                    },
                    metadata={"unit": "MPa", "integration_scheme": "2-point"},
                ),
                ResultField(
                    name=FIELD_KEY_S_REC,
                    position=POSITION_ELEMENT_NODAL,
                    values={
                        "part-1.e1.n1.sp1": {"S11": 9.5, "S22": 3.5, "S33": 0.0, "S12": 1.8, "S13": 0.0, "S23": 0.0},
                        "part-1.e1.n2.sp1": {"S11": 11.0, "S22": 4.5, "S33": 0.0, "S12": 2.1, "S13": 0.0, "S23": 0.0},
                        "part-1.e1.n3.sp1": {"S11": 13.0, "S22": 7.0, "S33": 0.0, "S12": 2.9, "S13": 0.0, "S23": 0.0},
                        "part-1.e1.n4.sp1": {"S11": 10.5, "S22": 4.2, "S33": 0.0, "S12": 2.2, "S13": 0.0, "S23": 0.0},
                    },
                    source_type=RESULT_SOURCE_RECOVERED,
                    metadata={"unit": "MPa", "recovery_source": FIELD_KEY_S_IP},
                ),
                ResultField(
                    name=FIELD_KEY_S_AVG,
                    position=POSITION_NODE_AVERAGED,
                    values={
                        "part-1.n1.avg0": {"S11": 9.5, "S22": 3.5, "S33": 0.0, "S12": 1.8, "S13": 0.0, "S23": 0.0},
                        "part-1.n2.avg0": {"S11": 11.2, "S22": 4.8, "S33": 0.0, "S12": 2.2, "S13": 0.0, "S23": 0.0},
                        "part-1.n2.avg1": {"S11": 12.6, "S22": 5.4, "S33": 0.0, "S12": 2.7, "S13": 0.0, "S23": 0.0},
                        "part-1.n3.avg0": {"S11": 13.0, "S22": 7.0, "S33": 0.0, "S12": 2.9, "S13": 0.0, "S23": 0.0},
                    },
                    source_type=RESULT_SOURCE_AVERAGED,
                    metadata={
                        "unit": "MPa",
                        FIELD_METADATA_KEY_BASE_TARGET_KEYS: {
                            "part-1.n1.avg0": "part-1.n1",
                            "part-1.n2.avg0": "part-1.n2",
                            "part-1.n2.avg1": "part-1.n2",
                            "part-1.n3.avg0": "part-1.n3",
                        },
                        FIELD_METADATA_KEY_AVERAGING_GROUPS: {
                            "part-1.n1.avg0": "group-0",
                            "part-1.n2.avg0": "group-0",
                            "part-1.n2.avg1": "group-1",
                            "part-1.n3.avg0": "group-0",
                        },
                    },
                ),
                ResultField(
                    name=FIELD_KEY_S_VM_IP,
                    position=POSITION_INTEGRATION_POINT,
                    values={
                        "part-1.e1.ip1": {"MISES": 9.8},
                        "part-1.e1.ip2": {"MISES": 13.9},
                    },
                    source_type=RESULT_SOURCE_DERIVED,
                    metadata={"unit": "MPa", "derived_from": FIELD_KEY_S_IP},
                ),
                ResultField(
                    name=FIELD_KEY_S_PRINCIPAL_IP,
                    position=POSITION_INTEGRATION_POINT,
                    values={
                        "part-1.e1.ip1": {"P1": 10.5, "P2": 3.1, "P3": 0.0},
                        "part-1.e1.ip2": {"P1": 14.8, "P2": 5.9, "P3": 0.0},
                    },
                    source_type=RESULT_SOURCE_DERIVED,
                    metadata={"unit": "MPa", "derived_from": FIELD_KEY_S_IP},
                ),
            ),
        )
    )
    writer.write_history_series(
        ResultHistorySeries(
            name=FIELD_KEY_TIME,
            step_name="STEP-1",
            position=POSITION_GLOBAL_HISTORY,
            axis_kind=AXIS_KIND_FRAME_ID,
            axis_values=(0,),
            values={GLOBAL_HISTORY_TARGET: (0.0,)},
        )
    )
    writer.write_summary(ResultSummary(name="run_summary", step_name="STEP-1", data={"max_u": 0.1612, "max_mises": 13.9}))
    writer.close_session()

    return GuiResultsViewContext(
        results_path=Path("semantic.results.json"),
        mesh_geometry=GuiMeshGeometry(
            model_name="semantic-model",
            point_keys=("part-1.n1", "part-1.n2", "part-1.n3", "part-1.n4"),
            points=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)),
            cell_connectivities=((0, 1, 2, 3),),
            cell_keys=("part-1.e1",),
            vtk_cell_types=(9,),
        ),
        results_facade=ResultsFacade(writer),
    )


class FakeGuiShell:
    """提供 GUI 后处理 smoke 测试所需的最小壳层。"""

    def __init__(self) -> None:
        self.state = GuiShellState()
        self.calls: list[tuple[str, object]] = []
        self._view_context = build_semantic_results_view_context()

    def open_model(self, input_path: str | Path, *, model_name: str | None = None) -> GuiModelSummary:
        del model_name
        resolved_path = Path(input_path)
        self.calls.append(("open_model", resolved_path))
        summary = GuiModelSummary(
            source_path=resolved_path,
            model_name="semantic-model",
            part_names=("part-1",),
            step_names=("STEP-1",),
            has_assembly=False,
            part_count=1,
            instance_count=0,
        )
        self.state.opened_model = summary
        return summary

    def build_default_results_path(self) -> Path:
        return Path("semantic.results.json")

    def build_default_vtk_path(self) -> Path:
        return Path("semantic.vtk")

    def build_model_navigation_snapshot(self) -> GuiModelNavigationSnapshot:
        return GuiModelNavigationSnapshot(
            source_path=Path("semantic.inp"),
            model_name="semantic-model",
            part_names=("part-1",),
            instance_names=("part-1-1",),
            material_names=("steel",),
            section_names=("sec-1",),
            step_names=("STEP-1",),
            boundary_names=("bc-1",),
            nodal_load_names=("load-1",),
            distributed_load_names=(),
            output_request_names=("node", "stress", "post"),
        )

    def build_viewport_geometry(self) -> GuiMeshGeometry:
        return self._view_context.mesh_geometry

    def load_results_view(self, results_path: str | Path | None = None) -> GuiResultsLoadResult:
        resolved_path = self._view_context.results_path if results_path is None else Path(results_path)
        self.calls.append(("load_results_view", resolved_path))
        time.sleep(0.02)
        entries = (
            GuiResultsEntry(
                step_name="STEP-1",
                procedure_type="static_linear",
                frame_count=1,
                history_count=1,
                summary_count=1,
                field_names=(FIELD_KEY_U, FIELD_KEY_U_MAG, FIELD_KEY_S, FIELD_KEY_S_IP, FIELD_KEY_S_REC, FIELD_KEY_S_AVG, FIELD_KEY_S_VM_IP, FIELD_KEY_S_PRINCIPAL_IP),
                history_names=(FIELD_KEY_TIME,),
                summary_names=("run_summary",),
            ),
        )
        self.state.current_results_path = resolved_path
        self.state.results_entries = entries
        return GuiResultsLoadResult(results_path=resolved_path, entries=entries, view_context=self._view_context)

    def submit_job(
        self,
        *,
        step_name: str | None = None,
        results_path: str | Path | None = None,
        export_vtk: bool = False,
        vtk_path: str | Path | None = None,
        monitor=None,
    ) -> JobExecutionReport:
        self.calls.append(("submit_job", {"step_name": step_name, "results_path": results_path, "export_vtk": export_vtk, "vtk_path": vtk_path}))
        time.sleep(0.03)
        if monitor is not None:
            monitor.message("fake monitor message")
        report = JobExecutionReport(
            model_name="semantic-model",
            job_name=None,
            step_name="STEP-1",
            procedure_type="static_linear",
            results_backend="memory",
            results_path=Path("semantic.results.json") if results_path is None else Path(results_path),
            export_format="vtk" if export_vtk else None,
            export_path=None if vtk_path is None else Path(vtk_path),
            frame_count=1,
            history_count=1,
            summary_count=1,
            monitor_messages=() if monitor is None else monitor.snapshot(),
        )
        self.state.last_job_report = report
        self.state.current_results_path = report.results_path
        return report
