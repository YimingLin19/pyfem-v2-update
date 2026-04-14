"""Raw keyword exporter 边界回归测试。"""

from __future__ import annotations

import unittest

from pyfem.io import InpExporter
from pyfem.modeldb import RawKeywordBlockDef
from tests.support.model_builders import build_static_beam_benchmark_model


class RawKeywordExportBoundaryRegressionTests(unittest.TestCase):
    """验证 raw keyword block 的位置与顺序可控。"""

    def test_raw_keyword_block_order_and_position_remain_stable(self) -> None:
        model = build_static_beam_benchmark_model()
        model.add_raw_keyword_block(
            RawKeywordBlockDef(name="raw-a", keyword="AMPLITUDE", placement="before_steps", data_lines=("A, 1.0",), order=1)
        )
        model.add_raw_keyword_block(
            RawKeywordBlockDef(name="raw-b", keyword="AMPLITUDE", placement="before_steps", data_lines=("B, 2.0",), order=2)
        )
        model.add_raw_keyword_block(
            RawKeywordBlockDef(name="raw-step-end", keyword="RESTART", placement="step_end", step_name="step-static", data_lines=("WRITE",), order=1)
        )

        exported_text = InpExporter().export_text(model).text
        raw_a_index = exported_text.index("name=raw-a")
        raw_b_index = exported_text.index("name=raw-b")
        step_index = exported_text.index("*Step, name=step-static")
        raw_step_end_index = exported_text.index("name=raw-step-end")
        end_step_index = exported_text.index("*End Step")

        self.assertLess(raw_a_index, raw_b_index)
        self.assertLess(raw_b_index, step_index)
        self.assertGreater(raw_step_end_index, step_index)
        self.assertLess(raw_step_end_index, end_step_index)


if __name__ == "__main__":
    unittest.main()
