import unittest
from pathlib import Path
from uuid import uuid4

from pyfem.io import (
    AXIS_KIND_FRAME_ID,
    FIELD_KEY_TIME,
    GLOBAL_HISTORY_TARGET,
    JsonResultsReader,
    JsonResultsWriter,
    POSITION_ELEMENT_CENTROID,
    POSITION_GLOBAL_HISTORY,
    POSITION_INTEGRATION_POINT,
    POSITION_NODE,
    RESULT_SOURCE_DERIVED,
    RESULT_SOURCE_RAW,
    RESULT_SOURCE_RECOVERED,
    ResultField,
    ResultFrame,
    ResultHistorySeries,
    ResultsSession,
)
from pyfem.post import ResultsFacade


class ResultsPostContractPhase1IntegrationTests(unittest.TestCase):
    def test_json_reader_and_facade_expose_extended_field_contract(self) -> None:
        target_path = Path("tests") / f"_tmp_results_post_contract_{uuid4().hex}.json"
        try:
            writer = JsonResultsWriter(target_path)
            writer.open_session(
                ResultsSession(
                    model_name="post-model",
                    procedure_name="step-post",
                    step_name="step-post",
                )
            )
            writer.write_frame(
                ResultFrame(
                    frame_id=0,
                    step_name="step-post",
                    time=0.0,
                    fields=(
                        ResultField(
                            name="U",
                            position=POSITION_NODE,
                            values={
                                "part-1.n1": {"UX": 0.0, "UY": 0.0},
                                "part-1.n2": {"UX": 0.2, "UY": -0.1},
                            },
                        ),
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
                            name="S_REC",
                            position=POSITION_NODE,
                            values={
                                "part-1.n1": {"S11": 9.0, "S22": 1.0},
                                "part-1.n2": {"S11": 11.0, "S22": 1.5},
                            },
                            source_type=RESULT_SOURCE_RECOVERED,
                            component_names=("S11", "S22"),
                            metadata={"recovery_method": "patch"},
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
                    metadata={"phase": "phase1"},
                )
            )
            writer.write_history_series(
                ResultHistorySeries(
                    name=FIELD_KEY_TIME,
                    step_name="step-post",
                    position=POSITION_GLOBAL_HISTORY,
                    axis_kind=AXIS_KIND_FRAME_ID,
                    axis_values=(0,),
                    values={GLOBAL_HISTORY_TARGET: (0.0,)},
                )
            )
            writer.close_session()

            reader = JsonResultsReader(target_path)
            facade = ResultsFacade(reader)
            frame = reader.read_frame("step-post", 0)
            field_overviews = {item.field_name: item for item in facade.fields(step_name="step-post", frame_id=0)}
            frame_overview = facade.frames(step_name="step-post", frame_ids=(0,))[0]
            history_overview = facade.histories(step_name="step-post", history_name=FIELD_KEY_TIME)[0]

            self.assertEqual(reader.read_field("step-post", 0, "U").position, POSITION_NODE)
            self.assertEqual(reader.read_field("step-post", 0, "U").source_type, RESULT_SOURCE_RAW)
            self.assertEqual(reader.read_field("step-post", 0, "S_IP").position, POSITION_INTEGRATION_POINT)
            self.assertEqual(reader.read_field("step-post", 0, "S_REC").source_type, RESULT_SOURCE_RECOVERED)
            self.assertEqual(reader.read_field("step-post", 0, "S_VM").source_type, RESULT_SOURCE_DERIVED)
            self.assertEqual(frame.field_positions, (POSITION_NODE, POSITION_INTEGRATION_POINT, POSITION_ELEMENT_CENTROID))
            self.assertEqual(frame.field_source_types, (RESULT_SOURCE_RAW, RESULT_SOURCE_RECOVERED, RESULT_SOURCE_DERIVED))
            self.assertEqual(field_overviews["S_IP"].component_names, ("S11", "S22"))
            self.assertEqual(field_overviews["S_IP"].target_count, 2)
            self.assertEqual(field_overviews["S_IP"].metadata["integration_rule"], "2x2")
            self.assertEqual(field_overviews["S_REC"].source_type, RESULT_SOURCE_RECOVERED)
            self.assertEqual(field_overviews["S_REC"].target_keys, ("part-1.n1", "part-1.n2"))
            self.assertEqual(field_overviews["S_VM"].source_type, RESULT_SOURCE_DERIVED)
            self.assertEqual(frame_overview.field_positions, (POSITION_NODE, POSITION_INTEGRATION_POINT, POSITION_ELEMENT_CENTROID))
            self.assertEqual(frame_overview.field_source_types, (RESULT_SOURCE_RAW, RESULT_SOURCE_RECOVERED, RESULT_SOURCE_DERIVED))
            self.assertEqual(frame_overview.target_keys, ("part-1.n1", "part-1.n2", "part-1.e1.ip1", "part-1.e1.ip2", "part-1.e1"))
            self.assertEqual(frame_overview.target_count, 5)
            self.assertEqual(history_overview.position, POSITION_GLOBAL_HISTORY)
            self.assertEqual(history_overview.target_keys, (GLOBAL_HISTORY_TARGET,))
            self.assertEqual(history_overview.target_count, 1)
        finally:
            target_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
