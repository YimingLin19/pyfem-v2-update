"""多步结果 roundtrip 与 legacy 兼容测试。"""

from pathlib import Path
import json
import unittest
from uuid import uuid4

from pyfem.foundation.errors import PyFEMError
from pyfem.io import (
    AXIS_KIND_FRAME_ID,
    AXIS_KIND_MODE_INDEX,
    FIELD_KEY_FREQUENCY,
    FIELD_KEY_TIME,
    FIELD_KEY_U,
    FRAME_KIND_MODE,
    GLOBAL_HISTORY_TARGET,
    JsonResultsReader,
    JsonResultsWriter,
    MODAL_METADATA_KEY_EIGENVALUE,
    MODAL_METADATA_KEY_FREQUENCY_HZ,
    MODAL_METADATA_KEY_MODE_INDEX,
    PAIRED_VALUE_KEY_EIGENVALUE,
    POSITION_GLOBAL_HISTORY,
    POSITION_NODE,
    RESULTS_SCHEMA_VERSION,
    ResultField,
    ResultFrame,
    ResultHistorySeries,
    ResultStep,
    ResultSummary,
    ResultsDatabase,
    ResultsSession,
)


class ResultsMultiStepRoundtripTests(unittest.TestCase):
    """验证多步 roundtrip 与 legacy 边界。"""

    def test_json_reference_backend_supports_multi_step_roundtrip(self) -> None:
        target_path = Path("tests") / f"_tmp_results_multistep_{uuid4().hex}.json"
        try:
            writer = JsonResultsWriter(target_path)

            writer.open_session(
                ResultsSession(
                    model_name="demo-model",
                    procedure_name="step-static",
                    job_name="job-1",
                    step_name="step-static",
                    procedure_type="static_linear",
                    metadata={
                        "model_metadata": {"units": "SI"},
                        "step_parameters": {"load": 1.0},
                        "output_request_names": ("field-static",),
                    },
                )
            )
            writer.write_frame(
                ResultFrame(
                    frame_id=0,
                    step_name="step-static",
                    time=0.0,
                    fields=(
                        ResultField(
                            name=FIELD_KEY_U,
                            position=POSITION_NODE,
                            values={"part-1.n1": {"UX": 0.0}, "part-1.n2": {"UX": 0.1}},
                        ),
                    ),
                )
            )
            writer.write_history_series(
                ResultHistorySeries(
                    name=FIELD_KEY_TIME,
                    step_name="step-static",
                    axis_kind=AXIS_KIND_FRAME_ID,
                    axis_values=(0,),
                    values={GLOBAL_HISTORY_TARGET: (0.0,)},
                    position=POSITION_GLOBAL_HISTORY,
                )
            )
            writer.write_summary(ResultSummary(name="static_summary", step_name="step-static", data={"load_norm": 1.0}))
            writer.close_session()

            writer.open_session(
                ResultsSession(
                    model_name="demo-model",
                    procedure_name="step-modal",
                    job_name="job-1",
                    step_name="step-modal",
                    procedure_type="modal",
                    metadata={
                        "model_metadata": {"units": "SI"},
                        "step_parameters": {"num_modes": 1},
                        "output_request_names": ("field-modal",),
                    },
                )
            )
            writer.write_frame(
                ResultFrame(
                    frame_id=0,
                    step_name="step-modal",
                    time=0.0,
                    frame_kind=FRAME_KIND_MODE,
                    axis_kind=AXIS_KIND_MODE_INDEX,
                    axis_value=0,
                    metadata={
                        MODAL_METADATA_KEY_MODE_INDEX: 0,
                        MODAL_METADATA_KEY_FREQUENCY_HZ: 12.5,
                        MODAL_METADATA_KEY_EIGENVALUE: 6168.5,
                    },
                    fields=(
                        ResultField(
                            name="MODE_SHAPE",
                            position=POSITION_NODE,
                            values={"part-1.n2": {"UX": 1.0}},
                        ),
                    ),
                )
            )
            writer.write_history_series(
                ResultHistorySeries(
                    name=FIELD_KEY_FREQUENCY,
                    step_name="step-modal",
                    axis_kind=AXIS_KIND_MODE_INDEX,
                    axis_values=(0,),
                    values={GLOBAL_HISTORY_TARGET: (12.5,)},
                    paired_values={PAIRED_VALUE_KEY_EIGENVALUE: (6168.5,)},
                    position=POSITION_GLOBAL_HISTORY,
                )
            )
            writer.close_session()

            reader = JsonResultsReader(target_path)
            database = reader.read_database()
            session = reader.read_session()
            static_step = reader.read_step("step-static")
            modal_step = reader.read_step("step-modal")

            self.assertTrue(database.is_multi_step)
            self.assertTrue(reader.is_multi_step())
            self.assertEqual(reader.list_steps(), ("step-static", "step-modal"))
            self.assertEqual(tuple(step.step_index for step in database.steps), (0, 1))
            self.assertEqual(session.job_name, "job-1")
            self.assertIsNone(session.step_name)
            self.assertIsNone(session.procedure_name)
            self.assertIsNone(session.procedure_type)
            self.assertTrue(session.metadata.get("multi_step"))
            self.assertEqual(static_step.summaries[0].name, "static_summary")
            self.assertEqual(static_step.histories[0].get_series(), (0.0,))
            self.assertEqual(modal_step.frames[0].frame_kind, FRAME_KIND_MODE)
            self.assertEqual(modal_step.histories[0].get_paired_series(PAIRED_VALUE_KEY_EIGENVALUE), (6168.5,))
        finally:
            target_path.unlink(missing_ok=True)

    def test_multi_step_is_structural_semantics_not_metadata_only(self) -> None:
        database = ResultsDatabase(
            session=ResultsSession(model_name="demo-model", job_name="job-1"),
            steps=(
                ResultStep(name="step-a", step_index=0),
                ResultStep(name="step-b", step_index=1),
            ),
        )

        self.assertTrue(database.is_multi_step)
        self.assertNotIn("multi_step", database.session.metadata)
        self.assertEqual(database.list_steps(), ("step-a", "step-b"))

    def test_duplicate_step_name_open_session_fails_fast(self) -> None:
        writer = JsonResultsWriter(Path("tests") / f"_tmp_results_duplicate_{uuid4().hex}.json")
        try:
            writer.open_session(ResultsSession(model_name="demo-model", job_name="job-1", step_name="step-1"))
            writer.close_session()
            with self.assertRaises(PyFEMError):
                writer.open_session(ResultsSession(model_name="demo-model", job_name="job-1", step_name="step-1"))
        finally:
            writer._path.unlink(missing_ok=True)

    def test_legacy_modal_history_payload_converts_to_paired_values(self) -> None:
        target_path = Path("tests") / f"_tmp_results_legacy_modal_{uuid4().hex}.json"
        payload = {
            "schema_version": RESULTS_SCHEMA_VERSION,
            "session": {"model_name": "legacy-model", "procedure_name": "step-modal", "step_name": "step-modal"},
            "frames": [],
            "histories": [
                {
                    "name": FIELD_KEY_FREQUENCY,
                    "position": POSITION_GLOBAL_HISTORY,
                    "data": {"frequencies_hz": [12.5, 18.0], "eigenvalues": [6168.5, 12790.0]},
                }
            ],
        }
        try:
            target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            history = JsonResultsReader(target_path).read_history("step-modal", FIELD_KEY_FREQUENCY)

            self.assertEqual(history.axis_kind, AXIS_KIND_MODE_INDEX)
            self.assertEqual(history.axis_values, (0, 1))
            self.assertEqual(history.get_series(), (12.5, 18.0))
            self.assertEqual(history.get_paired_series(PAIRED_VALUE_KEY_EIGENVALUE), (6168.5, 12790.0))
        finally:
            target_path.unlink(missing_ok=True)

    def test_paired_values_length_mismatch_fails_fast(self) -> None:
        with self.assertRaises(PyFEMError):
            ResultHistorySeries(
                name=FIELD_KEY_FREQUENCY,
                step_name="step-modal",
                axis_kind=AXIS_KIND_MODE_INDEX,
                axis_values=(0, 1),
                values={GLOBAL_HISTORY_TARGET: (10.0, 20.0)},
                paired_values={PAIRED_VALUE_KEY_EIGENVALUE: (1.0,)},
            )


if __name__ == "__main__":
    unittest.main()
