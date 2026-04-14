"""结果合同回归测试。"""

from pathlib import Path
import unittest
from uuid import uuid4

from pyfem.compiler import Compiler
from pyfem.io import FIELD_KEY_FREQUENCY, FIELD_KEY_TIME, JsonResultsReader, JsonResultsWriter, PAIRED_VALUE_KEY_EIGENVALUE
from pyfem.post import ResultsProbeService, ResultsQueryService
from tests.support import build_multi_step_beam_model


class ResultsContractRegressionTests(unittest.TestCase):
    """固化 Reader-only 结果合同与多步 roundtrip 主线。"""

    def test_json_roundtrip_preserves_multistep_contract_and_reader_only_consumers(self) -> None:
        results_path = Path("tests") / f"_tmp_results_contract_{uuid4().hex}.json"
        try:
            model = build_multi_step_beam_model()
            compiled_model = Compiler().compile(model)
            writer = JsonResultsWriter(results_path)
            for step_name in model.job.step_names:
                compiled_model.get_step_runtime(step_name).run(writer)

            reader = JsonResultsReader(results_path)
            query = ResultsQueryService(reader)
            probe = ResultsProbeService(reader)
            session = reader.read_session()

            static_step = reader.read_step("step-static")
            modal_step = reader.read_step("step-modal")
            dynamic_step = reader.read_step("step-dynamic")
            modal_frequency = probe.history("step-modal", FIELD_KEY_FREQUENCY)
            modal_eigenvalue = probe.paired_history("step-modal", FIELD_KEY_FREQUENCY, PAIRED_VALUE_KEY_EIGENVALUE)
            dynamic_field = query.field("step-dynamic", 0, "U")

            self.assertEqual(query.list_steps(), ("step-static", "step-modal", "step-dynamic"))
            self.assertIsNone(session.step_name)
            self.assertIsNone(session.procedure_name)
            self.assertIsNone(session.procedure_type)
            self.assertTrue(session.metadata.get("multi_step"))
            self.assertEqual(tuple(history.name for history in static_step.histories), (FIELD_KEY_TIME,))
            self.assertEqual(tuple(summary.name for summary in static_step.summaries), ("static_summary",))
            self.assertEqual(modal_step.frames[0].metadata["mode_index"], 0)
            self.assertEqual(modal_frequency.axis_values, (0,))
            self.assertEqual(modal_frequency.values[0], modal_step.frames[0].metadata["frequency_hz"])
            self.assertEqual(modal_eigenvalue.values[0], modal_step.frames[0].metadata["eigenvalue"])
            self.assertEqual(tuple(dynamic_field.values.keys()), ("part-1.n1", "part-1.n2"))
            self.assertEqual(dynamic_step.histories[0].axis_values, tuple(frame.frame_id for frame in dynamic_step.frames))
        finally:
            results_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
