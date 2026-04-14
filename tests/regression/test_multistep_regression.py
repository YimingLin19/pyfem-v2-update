"""多步结果路径回归测试。"""

import unittest

from pyfem.foundation.errors import PyFEMError
from pyfem.io import InMemoryResultsWriter, ResultsSession
from tests.support import build_multi_step_beam_model, run_job


class MultiStepRegressionTests(unittest.TestCase):
    """固化多步结果路径与 fail-fast 语义。"""

    def test_multistep_root_session_keeps_order_and_separates_step_local_metadata(self) -> None:
        _, writer = run_job(build_multi_step_beam_model())

        session = writer.read_session()
        static_step = writer.read_step("step-static")
        modal_step = writer.read_step("step-modal")
        dynamic_step = writer.read_step("step-dynamic")

        self.assertTrue(writer.is_multi_step())
        self.assertEqual(writer.list_steps(), ("step-static", "step-modal", "step-dynamic"))
        self.assertTrue(session.metadata.get("multi_step"))
        self.assertNotIn("step_parameters", session.metadata)
        self.assertNotIn("output_request_names", session.metadata)
        self.assertEqual(static_step.step_index, 0)
        self.assertEqual(modal_step.step_index, 1)
        self.assertEqual(dynamic_step.step_index, 2)
        self.assertEqual(static_step.metadata["output_request_names"], ("field-static", "history-static"))
        self.assertEqual(modal_step.metadata["step_parameters"], {"num_modes": 1})
        self.assertEqual(dynamic_step.metadata["step_parameters"]["time_step"], 0.0005)
        self.assertEqual(tuple(static_step.histories[0].values.keys()), ("__global__",))
        self.assertEqual(tuple(dynamic_step.frames[0].get_field("U").values.keys()), ("part-1.n1", "part-1.n2"))

    def test_inmemory_writer_duplicate_step_name_fails_fast(self) -> None:
        writer = InMemoryResultsWriter()
        session = ResultsSession(model_name="demo-model", job_name="job-1", step_name="step-1")

        writer.open_session(session)
        writer.close_session()
        with self.assertRaises(PyFEMError):
            writer.open_session(session)


if __name__ == "__main__":
    unittest.main()
