"""结果 facade 测试。"""

import unittest

from pyfem.foundation.errors import PyFEMError
from pyfem.io import (
    AXIS_KIND_FRAME_ID,
    FIELD_KEY_FREQUENCY,
    FIELD_KEY_S_AVG,
    FIELD_KEY_S_REC,
    FIELD_KEY_TIME,
    FIELD_KEY_U,
    FIELD_KEY_U_MAG,
    FRAME_KIND_MODE,
    FRAME_KIND_SOLUTION,
    GLOBAL_HISTORY_TARGET,
    InMemoryResultsWriter,
    PAIRED_VALUE_KEY_EIGENVALUE,
    POSITION_GLOBAL_HISTORY,
    POSITION_NODE,
    POSITION_NODE_AVERAGED,
    RESULT_SOURCE_AVERAGED,
    RESULT_SOURCE_DERIVED,
    RESULT_SOURCE_RAW,
    RESULT_SOURCE_RECOVERED,
    ResultField,
    ResultFrame,
    ResultHistorySeries,
    ResultSummary,
    ResultsSession,
)
from pyfem.post import ResultsFacade


class ResultsFacadeTests(unittest.TestCase):
    """验证 reader-only facade 会收口结果浏览能力。"""

    def test_results_facade_supports_browsing_filters_selection_and_field_categories(self) -> None:
        writer = InMemoryResultsWriter()

        writer.open_session(
            ResultsSession(
                model_name="demo-model",
                procedure_name="step-static",
                step_name="step-static",
                procedure_type="static_linear",
            )
        )
        writer.write_frame(
            ResultFrame(
                frame_id=0,
                step_name="step-static",
                time=0.0,
                frame_kind=FRAME_KIND_SOLUTION,
                axis_kind=AXIS_KIND_FRAME_ID,
                axis_value=0,
                fields=(
                    ResultField(
                        name=FIELD_KEY_U,
                        position=POSITION_NODE,
                        values={
                            "part-1.n1": {"UX": 0.0, "UY": 0.0},
                            "part-1.n2": {"UX": 0.25, "UY": -0.5},
                        },
                    ),
                    ResultField(
                        name=FIELD_KEY_S_REC,
                        position="ELEMENT_NODAL",
                        values={"part-1.e1.n1": {"S11": 1.0}, "part-1.e1.n2": {"S11": 2.0}},
                        source_type=RESULT_SOURCE_RECOVERED,
                        metadata={"owner_element_keys": {"part-1.e1.n1": "part-1.e1", "part-1.e1.n2": "part-1.e1"}},
                    ),
                    ResultField(
                        name=FIELD_KEY_S_AVG,
                        position=POSITION_NODE_AVERAGED,
                        values={"part-1.n1": {"S11": 1.5}, "part-1.n2": {"S11": 1.75}},
                        source_type=RESULT_SOURCE_AVERAGED,
                        metadata={"base_target_keys": {"part-1.n1": "part-1.n1", "part-1.n2": "part-1.n2"}},
                    ),
                    ResultField(
                        name=FIELD_KEY_U_MAG,
                        position=POSITION_NODE,
                        values={"part-1.n1": {"MAGNITUDE": 0.0}, "part-1.n2": {"MAGNITUDE": 0.5590169943749475}},
                        source_type=RESULT_SOURCE_DERIVED,
                    ),
                ),
                metadata={"stage": "static"},
            )
        )
        writer.write_history_series(
            ResultHistorySeries(
                name=FIELD_KEY_TIME,
                step_name="step-static",
                position=POSITION_GLOBAL_HISTORY,
                axis_kind=AXIS_KIND_FRAME_ID,
                axis_values=(0,),
                values={GLOBAL_HISTORY_TARGET: (0.0,)},
            )
        )
        writer.write_summary(ResultSummary(name="static_summary", step_name="step-static", data={"load_norm": 1.0}))
        writer.close_session()

        writer.open_session(
            ResultsSession(
                model_name="demo-model",
                procedure_name="step-modal",
                step_name="step-modal",
                procedure_type="modal",
            )
        )
        writer.write_frame(
            ResultFrame(
                frame_id=0,
                step_name="step-modal",
                time=0.0,
                frame_kind=FRAME_KIND_MODE,
                axis_kind=AXIS_KIND_FRAME_ID,
                axis_value=0,
                fields=(
                    ResultField(
                        name=FIELD_KEY_U,
                        position=POSITION_NODE,
                        values={"part-1.n1": {"UX": 1.0, "UY": 0.0}},
                    ),
                ),
                metadata={"mode_index": 0},
            )
        )
        writer.write_history_series(
            ResultHistorySeries(
                name=FIELD_KEY_FREQUENCY,
                step_name="step-modal",
                position=POSITION_GLOBAL_HISTORY,
                axis_kind=AXIS_KIND_FRAME_ID,
                axis_values=(0,),
                values={GLOBAL_HISTORY_TARGET: (12.5,)},
                paired_values={PAIRED_VALUE_KEY_EIGENVALUE: (6250.0,)},
            )
        )
        writer.write_summary(ResultSummary(name="modal_summary", step_name="step-modal", data={"mode_count": 1}))
        writer.close_session()

        facade = ResultsFacade(writer)

        all_steps = facade.step_overviews()
        static_only = facade.step_overviews(target_key="part-1.n2")
        mode_frames = facade.frames(step_name="step-modal", frame_kind=FRAME_KIND_MODE, result_key="part-1.n1")
        displacement_fields = facade.fields(step_name="step-static", field_name=FIELD_KEY_U, target_key="part-1.n2")
        recovered_fields = facade.recovered_fields(step_name="step-static", frame_id=0)
        averaged_fields = facade.averaged_fields(step_name="step-static", frame_id=0)
        derived_fields = facade.derived_fields(step_name="step-static", frame_id=0)
        time_histories = facade.histories(step_name="step-static", target_key=GLOBAL_HISTORY_TARGET)
        modal_histories = facade.histories(step_name="step-modal", axis_kind=AXIS_KIND_FRAME_ID)
        summaries = facade.summaries(step_name="step-static")

        self.assertEqual(facade.list_steps(), ("step-static", "step-modal"))
        self.assertEqual(facade.session().model_name, "demo-model")
        self.assertEqual(facade.capabilities().backend_name, "memory_reference")
        self.assertEqual(len(all_steps), 2)
        self.assertEqual(all_steps[0].field_names, (FIELD_KEY_U, FIELD_KEY_S_REC, FIELD_KEY_S_AVG, FIELD_KEY_U_MAG))
        self.assertEqual(all_steps[0].raw_field_names, (FIELD_KEY_U,))
        self.assertEqual(all_steps[0].recovered_field_names, (FIELD_KEY_S_REC,))
        self.assertEqual(all_steps[0].averaged_field_names, (FIELD_KEY_S_AVG,))
        self.assertEqual(all_steps[0].derived_field_names, (FIELD_KEY_U_MAG,))
        self.assertEqual(all_steps[0].frame_ids, (0,))
        self.assertEqual(all_steps[0].frame_kinds, (FRAME_KIND_SOLUTION,))
        self.assertEqual(all_steps[0].axis_kinds, (AXIS_KIND_FRAME_ID,))
        self.assertEqual(all_steps[0].target_keys, ("part-1.n1", "part-1.n2", "part-1.e1.n1", "part-1.e1.n2", GLOBAL_HISTORY_TARGET))
        self.assertEqual(len(static_only), 1)
        self.assertEqual(static_only[0].step_name, "step-static")
        self.assertEqual(mode_frames[0].frame_kind, FRAME_KIND_MODE)
        self.assertEqual(mode_frames[0].field_positions, (POSITION_NODE,))
        self.assertEqual(mode_frames[0].field_source_types, (RESULT_SOURCE_RAW,))
        self.assertEqual(mode_frames[0].target_keys, ("part-1.n1",))
        self.assertEqual(mode_frames[0].target_count, 1)
        self.assertEqual(displacement_fields[0].component_names, ("UX", "UY"))
        self.assertEqual(displacement_fields[0].source_type, RESULT_SOURCE_RAW)
        self.assertEqual(displacement_fields[0].target_keys, ("part-1.n2",))
        self.assertEqual(displacement_fields[0].target_count, 1)
        self.assertEqual(displacement_fields[0].min_value, -0.5)
        self.assertEqual(displacement_fields[0].max_value, 0.25)
        self.assertEqual(recovered_fields[0].position, "ELEMENT_NODAL")
        self.assertEqual(recovered_fields[0].source_type, RESULT_SOURCE_RECOVERED)
        self.assertEqual(averaged_fields[0].position, POSITION_NODE_AVERAGED)
        self.assertEqual(averaged_fields[0].source_type, RESULT_SOURCE_AVERAGED)
        self.assertEqual(derived_fields[0].field_name, FIELD_KEY_U_MAG)
        self.assertEqual(derived_fields[0].source_type, RESULT_SOURCE_DERIVED)
        self.assertEqual(time_histories[0].history_name, FIELD_KEY_TIME)
        self.assertEqual(time_histories[0].target_count, 1)
        self.assertEqual(modal_histories[0].paired_value_names, (PAIRED_VALUE_KEY_EIGENVALUE,))
        self.assertEqual(summaries[0].summary_name, "static_summary")
        self.assertEqual(facade.frame("step-static", 0).metadata["stage"], "static")
        self.assertEqual(facade.field("step-static", 0, FIELD_KEY_U).values["part-1.n2"]["UX"], 0.25)
        self.assertEqual(facade.history("step-modal", FIELD_KEY_FREQUENCY).get_series(), (12.5,))
        self.assertEqual(facade.summary("step-static", "static_summary").data["load_norm"], 1.0)
        self.assertEqual(facade.probe().node_component("step-static", "part-1.n2", "UY").values, (-0.5,))
        with self.assertRaisesRegex(PyFEMError, "target_key"):
            facade.frames(step_name="step-static", target_key="part-1.n1", result_key="part-1.n2")


if __name__ == "__main__":
    unittest.main()

