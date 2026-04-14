"""结果读写基础测试。"""

from pathlib import Path
import json
import unittest
from uuid import uuid4

from pyfem.io import (
    AXIS_KIND_FRAME_ID,
    FIELD_KEY_S,
    FIELD_KEY_TIME,
    FIELD_KEY_U,
    GLOBAL_HISTORY_TARGET,
    JsonResultsReader,
    JsonResultsWriter,
    POSITION_ELEMENT_CENTROID,
    POSITION_GLOBAL_HISTORY,
    POSITION_INTEGRATION_POINT,
    POSITION_NODE,
    RESULTS_SCHEMA_VERSION,
    RESULT_SOURCE_DERIVED,
    RESULT_SOURCE_RAW,
    RESULT_SOURCE_RECOVERED,
    ResultField,
    ResultFrame,
    ResultHistorySeries,
    ResultSummary,
    ResultsDatabase,
    ResultsSession,
)


class ResultsIOTests(unittest.TestCase):
    """验证轻量 ResultsDB 的写入与读回。"""

    def test_json_results_writer_and_reader_roundtrip(self) -> None:
        target_path = Path("tests") / f"_tmp_results_{uuid4().hex}.json"
        try:
            writer = JsonResultsWriter(target_path)
            writer.open_session(
                ResultsSession(
                    model_name="demo-model",
                    procedure_name="step-1",
                    job_name="job-1",
                    step_name="step-1",
                    procedure_type="static_linear",
                    metadata={"author": "task05"},
                )
            )
            writer.write_frame(
                ResultFrame(
                    frame_id=0,
                    step_name="step-1",
                    time=0.0,
                    fields=(
                        ResultField(
                            name=FIELD_KEY_U,
                            position=POSITION_NODE,
                            values={"part-1.n1": {"UX": 0.1, "UY": 0.0}},
                        ),
                    ),
                    metadata={"load_case": "basic"},
                )
            )
            writer.write_history_series(
                ResultHistorySeries(
                    name=FIELD_KEY_TIME,
                    step_name="step-1",
                    position=POSITION_GLOBAL_HISTORY,
                    axis_kind=AXIS_KIND_FRAME_ID,
                    axis_values=(0,),
                    values={GLOBAL_HISTORY_TARGET: (0.0,)},
                )
            )
            writer.write_summary(ResultSummary(name="static_summary", step_name="step-1", data={"residual_norm": 0.0}))
            writer.close_session()

            reader = JsonResultsReader(target_path)
            database = reader.read_database()
            frame = reader.read_frame("step-1", 0)
            history = reader.read_history("step-1", FIELD_KEY_TIME)
            summary = reader.read_summary("step-1", "static_summary")

            self.assertEqual(database.schema_version, RESULTS_SCHEMA_VERSION)
            self.assertEqual(database.session.model_name, "demo-model")
            self.assertEqual(database.session.job_name, "job-1")
            self.assertEqual(reader.list_steps(), ("step-1",))
            self.assertEqual(reader.read_step("step-1").frames[0].frame_id, 0)
            field = reader.read_field("step-1", 0, FIELD_KEY_U)
            self.assertEqual(field.position, POSITION_NODE)
            self.assertEqual(field.source_type, RESULT_SOURCE_RAW)
            self.assertEqual(field.component_names, ("UX", "UY"))
            self.assertEqual(field.target_keys, ("part-1.n1",))
            self.assertEqual(field.target_count, 1)
            self.assertEqual(frame.get_field(FIELD_KEY_U).values["part-1.n1"]["UX"], 0.1)
            self.assertEqual(frame.field_positions, (POSITION_NODE,))
            self.assertEqual(frame.field_source_types, (RESULT_SOURCE_RAW,))
            self.assertEqual(history.get_series(), (0.0,))
            self.assertEqual(summary.data["residual_norm"], 0.0)
        finally:
            target_path.unlink(missing_ok=True)

    def test_result_field_contract_roundtrip_preserves_extended_semantics(self) -> None:
        field = ResultField(
            name="S_IP",
            position=POSITION_INTEGRATION_POINT,
            values={
                "part-1.e1.ip1": {"S11": 10.0, "S22": 2.0, "S12": 1.0},
                "part-1.e1.ip2": {"S11": 12.0, "S22": 3.0, "S12": 1.5},
            },
            source_type=RESULT_SOURCE_RECOVERED,
            component_names=("S11", "S22", "S12"),
            target_keys=("part-1.e1.ip1", "part-1.e1.ip2"),
            target_count=2,
            metadata={"integration_rule": "2x2", "post_stage": "phase1"},
        )

        roundtrip = ResultField.from_dict(field.to_dict())

        self.assertEqual(roundtrip.position, POSITION_INTEGRATION_POINT)
        self.assertEqual(roundtrip.source_type, RESULT_SOURCE_RECOVERED)
        self.assertEqual(roundtrip.result_source, RESULT_SOURCE_RECOVERED)
        self.assertEqual(roundtrip.component_names, ("S11", "S22", "S12"))
        self.assertEqual(roundtrip.target_keys, ("part-1.e1.ip1", "part-1.e1.ip2"))
        self.assertEqual(roundtrip.target_count, 2)
        self.assertEqual(roundtrip.metadata["integration_rule"], "2x2")

    def test_scalar_result_field_does_not_infer_pseudo_value_component(self) -> None:
        field = ResultField(
            name=FIELD_KEY_S,
            position=POSITION_ELEMENT_CENTROID,
            values={"part-1.e1": 12.5},
        )

        roundtrip = ResultField.from_dict(field.to_dict())

        self.assertEqual(field.component_names, ())
        self.assertEqual(roundtrip.component_names, ())
        self.assertEqual(roundtrip.values["part-1.e1"], 12.5)

    def test_json_writer_and_reader_preserve_extended_field_contract(self) -> None:
        target_path = Path("tests") / f"_tmp_results_extended_{uuid4().hex}.json"
        try:
            writer = JsonResultsWriter(target_path)
            writer.open_session(ResultsSession(model_name="post-model", procedure_name="step-post", step_name="step-post"))
            writer.write_frame(
                ResultFrame(
                    frame_id=0,
                    step_name="step-post",
                    time=0.0,
                    fields=(
                        ResultField(
                            name="S_IP",
                            position=POSITION_INTEGRATION_POINT,
                            values={
                                "part-1.e1.ip1": {"S11": 10.0, "S22": 2.0},
                                "part-1.e1.ip2": {"S11": 12.0, "S22": 3.0},
                            },
                            component_names=("S11", "S22"),
                            metadata={"integration_rule": "2x2"},
                        ),
                        ResultField(
                            name="S_VM",
                            position=POSITION_ELEMENT_CENTROID,
                            values={"part-1.e1": {"MISES": 15.0}},
                            source_type=RESULT_SOURCE_DERIVED,
                            component_names=("MISES",),
                            metadata={"derived_from": ("S11", "S22", "S12")},
                        ),
                    ),
                )
            )
            writer.close_session()

            reader = JsonResultsReader(target_path)
            integration_point_field = reader.read_field("step-post", 0, "S_IP")
            derived_field = reader.read_field("step-post", 0, "S_VM")

            self.assertEqual(integration_point_field.position, POSITION_INTEGRATION_POINT)
            self.assertEqual(integration_point_field.source_type, RESULT_SOURCE_RAW)
            self.assertEqual(integration_point_field.component_names, ("S11", "S22"))
            self.assertEqual(integration_point_field.target_keys, ("part-1.e1.ip1", "part-1.e1.ip2"))
            self.assertEqual(integration_point_field.target_count, 2)
            self.assertEqual(integration_point_field.metadata["integration_rule"], "2x2")
            self.assertEqual(derived_field.position, POSITION_ELEMENT_CENTROID)
            self.assertEqual(derived_field.source_type, RESULT_SOURCE_DERIVED)
            self.assertEqual(derived_field.component_names, ("MISES",))
            self.assertEqual(derived_field.metadata["derived_from"], ("S11", "S22", "S12"))
        finally:
            target_path.unlink(missing_ok=True)

    def test_history_series_and_summary_are_separated(self) -> None:
        database = ResultsDatabase(
            session=ResultsSession(model_name="demo-model", procedure_name="step-1", step_name="step-1"),
            steps=(
                ResultsDatabase.from_dict(
                    {
                        "session": {"model_name": "demo-model", "procedure_name": "step-1", "step_name": "step-1"},
                        "steps": [
                            {
                                "name": "step-1",
                                "frames": [],
                                "histories": [
                                    {
                                        "name": FIELD_KEY_TIME,
                                        "step_name": "step-1",
                                        "axis_kind": AXIS_KIND_FRAME_ID,
                                        "axis_values": [0],
                                        "values": {GLOBAL_HISTORY_TARGET: [0.0]},
                                    }
                                ],
                                "summaries": [{"name": "static_summary", "step_name": "step-1", "data": {"residual_norm": 0.0}}],
                            }
                        ],
                    }
                ).steps[0],
            ),
        )

        step = database.get_step("step-1")
        self.assertEqual(tuple(history.name for history in step.histories), (FIELD_KEY_TIME,))
        self.assertEqual(tuple(summary.name for summary in step.summaries), ("static_summary",))

    def test_json_reference_backend_capabilities_are_explicit(self) -> None:
        target_path = Path("tests") / f"_tmp_results_{uuid4().hex}.json"
        try:
            writer = JsonResultsWriter(target_path)
            reader = JsonResultsReader(target_path)
            writer_caps = writer.get_capabilities()
            reader_caps = reader.get_capabilities()

            self.assertTrue(writer_caps.is_reference_implementation)
            self.assertFalse(writer_caps.supports_append)
            self.assertFalse(reader_caps.supports_partial_storage_read)
            self.assertEqual(writer_caps.backend_name, "json_reference")
            self.assertEqual(reader_caps.backend_name, "json_reference")
        finally:
            target_path.unlink(missing_ok=True)

    def test_results_database_supports_legacy_flat_payload(self) -> None:
        target_path = Path("tests") / f"_tmp_results_{uuid4().hex}.json"
        legacy_payload = {
            "schema_version": RESULTS_SCHEMA_VERSION,
            "session": {"model_name": "legacy-model", "procedure_name": "step-1", "step_name": "step-1"},
            "frames": [
                {
                    "frame_id": 0,
                    "step_name": "step-1",
                    "time": 0.0,
                    "fields": [
                        {
                            "name": FIELD_KEY_U,
                            "position": POSITION_NODE,
                            "values": {"part-1.n1": {"UX": 0.0}},
                        }
                    ],
                }
            ],
            "histories": [
                {"name": FIELD_KEY_TIME, "position": POSITION_GLOBAL_HISTORY, "data": {"values": [0.0]}},
                {"name": "static_summary", "data": {"residual_norm": 0.0}},
            ],
        }
        try:
            target_path.write_text(json.dumps(legacy_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            database = JsonResultsReader(target_path).read_database()
            step = database.get_step("step-1")
            legacy_field = step.frames[0].get_field(FIELD_KEY_U)

            self.assertEqual(database.list_steps(), ("step-1",))
            self.assertEqual(legacy_field.position, POSITION_NODE)
            self.assertEqual(legacy_field.source_type, RESULT_SOURCE_RAW)
            self.assertEqual(legacy_field.component_names, ("UX",))
            self.assertEqual(legacy_field.target_keys, ("part-1.n1",))
            self.assertEqual(step.histories[0].get_series(), (0.0,))
            self.assertEqual(step.summaries[0].data["residual_norm"], 0.0)
        finally:
            target_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
