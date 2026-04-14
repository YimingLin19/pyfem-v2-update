"""Reader 窄接口消费者测试。"""

from pathlib import Path
import unittest
from uuid import uuid4

from pyfem.io import (
    AXIS_KIND_FRAME_ID,
    AXIS_KIND_MODE_INDEX,
    AXIS_KIND_TIME,
    FIELD_KEY_FREQUENCY,
    FIELD_KEY_S,
    FIELD_KEY_S_AVG,
    FIELD_KEY_S_IP,
    FIELD_KEY_TIME,
    FIELD_KEY_U,
    GLOBAL_HISTORY_TARGET,
    PAIRED_VALUE_KEY_EIGENVALUE,
    POSITION_ELEMENT_CENTROID,
    POSITION_GLOBAL_HISTORY,
    POSITION_INTEGRATION_POINT,
    POSITION_NODE,
    POSITION_NODE_AVERAGED,
    RESULT_SOURCE_AVERAGED,
    ResultField,
    ResultFrame,
    ResultHistorySeries,
    ResultStep,
    ResultSummary,
    ResultsCapabilities,
    ResultsReader,
    VtkExporter,
)
from pyfem.mesh import ElementRecord, Mesh, NodeRecord, Part
from pyfem.modeldb import ModelDB
from pyfem.post import ResultsProbeService, ResultsQueryService


class NarrowOnlyReader(ResultsReader):
    """只实现窄接口的测试 Reader。"""

    def __init__(self) -> None:
        self._frame = ResultFrame(
            frame_id=0,
            step_name="step-1",
            time=0.0,
            fields=(
                ResultField(
                    name=FIELD_KEY_U,
                    position=POSITION_NODE,
                    values={"part-1.n1": {"UX": 0.0, "UY": 0.0}, "part-1.n2": {"UX": 0.1, "UY": -0.2}},
                ),
                ResultField(name=FIELD_KEY_S, position=POSITION_ELEMENT_CENTROID, values={"part-1.e1": 12.5}),
                ResultField(
                    name=FIELD_KEY_S_IP,
                    position=POSITION_INTEGRATION_POINT,
                    values={"part-1.e1.ip1": {"S11": 13.5}},
                ),
                ResultField(
                    name=FIELD_KEY_S_AVG,
                    position=POSITION_NODE_AVERAGED,
                    values={"part-1.n1": {"S11": 11.0}, "part-1.n2": {"S11": 12.0}},
                    source_type=RESULT_SOURCE_AVERAGED,
                    metadata={"base_target_keys": {"part-1.n1": "part-1.n1", "part-1.n2": "part-1.n2"}},
                ),
            ),
        )
        self._time_history = ResultHistorySeries(
            name=FIELD_KEY_TIME,
            step_name="step-1",
            axis_kind=AXIS_KIND_FRAME_ID,
            axis_values=(0,),
            values={GLOBAL_HISTORY_TARGET: (0.0,)},
            position=POSITION_GLOBAL_HISTORY,
        )
        self._frequency_history = ResultHistorySeries(
            name=FIELD_KEY_FREQUENCY,
            step_name="step-1",
            axis_kind=AXIS_KIND_MODE_INDEX,
            axis_values=(0,),
            values={GLOBAL_HISTORY_TARGET: (12.5,)},
            paired_values={PAIRED_VALUE_KEY_EIGENVALUE: (6168.5,)},
            position=POSITION_GLOBAL_HISTORY,
        )
        self._summary = ResultSummary(name="static_summary", step_name="step-1", data={"load_norm": 1.0})
        self._step = ResultStep(
            name="step-1",
            procedure_type="static_linear",
            step_index=0,
            frames=(self._frame,),
            histories=(self._time_history, self._frequency_history),
            summaries=(self._summary,),
        )

    def read_database(self):
        raise AssertionError("消费者不应直接调用 read_database()。")

    def get_capabilities(self) -> ResultsCapabilities:
        return ResultsCapabilities(
            backend_name="narrow_test_backend",
            is_reference_implementation=False,
            supports_append=False,
            supports_partial_storage_read=False,
            supports_restart_metadata=False,
        )

    def list_steps(self) -> tuple[str, ...]:
        return ("step-1",)

    def read_step(self, step_name: str) -> ResultStep:
        self._assert_step_name(step_name)
        return self._step

    def read_frame(self, step_name: str, frame_id: int) -> ResultFrame:
        self._assert_step_name(step_name)
        if frame_id != 0:
            raise AssertionError("测试 Reader 只提供 frame_id=0。")
        return self._frame

    def read_field(self, step_name: str, frame_id: int, field_name: str) -> ResultField:
        return self.read_frame(step_name, frame_id).get_field(field_name)

    def read_histories(self, step_name: str | None = None, history_name: str | None = None):
        if step_name is not None:
            self._assert_step_name(step_name)
        histories = (self._time_history, self._frequency_history)
        if history_name is None:
            return histories
        return tuple(history for history in histories if history.name == history_name)

    def read_history(self, step_name: str, history_name: str) -> ResultHistorySeries:
        self._assert_step_name(step_name)
        if history_name == FIELD_KEY_TIME:
            return self._time_history
        if history_name == FIELD_KEY_FREQUENCY:
            return self._frequency_history
        raise AssertionError(f"测试 Reader 不存在历史量 {history_name}。")

    def read_summaries(self, step_name: str | None = None, summary_name: str | None = None):
        if step_name is not None:
            self._assert_step_name(step_name)
        summaries = (self._summary,)
        if summary_name is None:
            return summaries
        return tuple(summary for summary in summaries if summary.name == summary_name)

    def read_summary(self, step_name: str, summary_name: str) -> ResultSummary:
        self._assert_step_name(step_name)
        if summary_name != "static_summary":
            raise AssertionError("测试 Reader 只提供 static_summary。")
        return self._summary

    def _assert_step_name(self, step_name: str) -> None:
        if step_name != "step-1":
            raise AssertionError(f"测试 Reader 不存在步骤 {step_name}。")


class ResultsReaderConsumerTests(unittest.TestCase):
    """验证消费者走 Reader 窄接口。"""

    def test_query_and_probe_services_work_with_narrow_only_reader(self) -> None:
        reader = NarrowOnlyReader()
        query = ResultsQueryService(reader)
        probe = ResultsProbeService(reader)

        steps = query.steps(procedure_type="static_linear")
        frames = query.frames("step-1", field_name=FIELD_KEY_U, axis_kind=AXIS_KIND_TIME, frame_ids=(0,))
        histories = query.histories("step-1", axis_kind=AXIS_KIND_FRAME_ID)
        paired_histories = query.histories("step-1", paired_value_name=PAIRED_VALUE_KEY_EIGENVALUE)
        summaries = query.summaries("step-1", data_key="load_norm")
        integration_point_overview = query.field_overview("step-1", 0, FIELD_KEY_S_IP)
        history_probe = probe.history("step-1", FIELD_KEY_TIME)
        paired_probe = probe.paired_history("step-1", FIELD_KEY_FREQUENCY, PAIRED_VALUE_KEY_EIGENVALUE)
        node_probe = probe.node_component("step-1", "part-1.n2", "UX", frame_ids=(0,))
        element_probe = probe.element_component("step-1", "part-1.e1", frame_ids=(0,))
        integration_point_probe = probe.integration_point_component("step-1", "part-1.e1.ip1", "S11", frame_ids=(0,))
        averaged_probe = probe.averaged_node_component("step-1", "part-1.n2", "S11", frame_ids=(0,))

        self.assertEqual(tuple(step.name for step in steps), ("step-1",))
        self.assertEqual(tuple(frame.frame_id for frame in frames), (0,))
        self.assertEqual(histories[0].get_series(), (0.0,))
        self.assertEqual(paired_histories[0].name, FIELD_KEY_FREQUENCY)
        self.assertEqual(summaries[0].data["load_norm"], 1.0)
        self.assertEqual(integration_point_overview.position, POSITION_INTEGRATION_POINT)
        self.assertEqual(integration_point_overview.component_names, ("S11",))
        self.assertEqual(integration_point_overview.min_value, 13.5)
        self.assertEqual(integration_point_overview.max_value, 13.5)
        self.assertEqual(history_probe.values, (0.0,))
        self.assertEqual(paired_probe.values, (6168.5,))
        self.assertEqual(node_probe.values, (0.1,))
        self.assertEqual(element_probe.values, (12.5,))
        self.assertEqual(element_probe.source_name, f"{FIELD_KEY_S}:part-1.e1")
        self.assertIsNone(element_probe.metadata["component_name"])
        self.assertEqual(integration_point_probe.values, (13.5,))
        self.assertEqual(averaged_probe.values, (12.0,))
        self.assertEqual(averaged_probe.metadata["position"], POSITION_NODE_AVERAGED)

    def test_probe_csv_export_and_vtk_exporter_work_with_narrow_only_reader(self) -> None:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(1.0, 0.0)))
        mesh.add_element(ElementRecord(name="e1", type_key="B21", node_names=("n1", "n2")))
        model = ModelDB(name="vtk-demo")
        model.add_part(Part(name="part-1", mesh=mesh))

        csv_path = Path("tests") / f"_tmp_probe_narrow_{uuid4().hex}.csv"
        vtk_path = Path("tests") / f"_tmp_vtk_narrow_{uuid4().hex}.vtk"
        try:
            probe = ResultsProbeService(NarrowOnlyReader())
            csv_probe = probe.integration_point_component("step-1", "part-1.e1.ip1", "S11")
            probe.export_csv(csv_probe, csv_path)
            csv_content = csv_path.read_text(encoding="utf-8")
            self.assertIn("resolved_target_key", csv_content)
            self.assertIn("part-1.e1.ip1", csv_content)
            self.assertIn("S11", csv_content)

            VtkExporter().export(model=model, results_reader=NarrowOnlyReader(), path=vtk_path)
            vtk_content = vtk_path.read_text(encoding="utf-8")
            self.assertIn("VECTORS RAW__U float", vtk_content)
            self.assertIn("SCALARS RAW__S float 1", vtk_content)
            self.assertIn("SCALARS RAW__S_IP__IP1__S11 float 1", vtk_content)
            self.assertIn("SCALARS AVERAGED__S_AVG__S11 float 1", vtk_content)
        finally:
            csv_path.unlink(missing_ok=True)
            vtk_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
