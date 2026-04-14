"""nlgeom 载荷边界 fail-fast 回归测试。"""

from __future__ import annotations

import unittest
from copy import deepcopy

from pyfem.compiler import Compiler
from pyfem.foundation.errors import CompilationError, SolverError
from pyfem.io import InMemoryResultsWriter
from pyfem.solver import Assembler
from tests.support.model_builders import build_c3d8_pressure_block_model, build_static_beam_benchmark_model


class NlgeomLoadBoundaryFailFastRegressionTests(unittest.TestCase):
    """验证 nlgeom 路径下的载荷支持边界已经正式收口。"""

    def test_nlgeom_step_fails_fast_for_surface_pressure_distributed_load(self) -> None:
        model = self._build_nlgeom_pressure_model()

        with self.assertRaisesRegex(CompilationError, "load-pressure\\[type=pressure"):
            Compiler().compile(model)

        with self.assertRaisesRegex(CompilationError, "位移边界与 nodal load"):
            Compiler().compile(model)

    def test_nlgeom_step_fails_fast_for_follower_pressure_distributed_load(self) -> None:
        model = self._build_nlgeom_pressure_model()
        model.distributed_loads["load-pressure"].load_type = "follower_pressure"

        with self.assertRaisesRegex(CompilationError, "load-pressure\\[type=follower_pressure"):
            Compiler().compile(model)

    def test_runtime_assembler_keeps_nlgeom_distributed_load_safety_guard(self) -> None:
        model = build_c3d8_pressure_block_model()
        compiled_model = Compiler().compile(model)
        assembler = Assembler(compiled_model, nlgeom=True)

        with self.assertRaisesRegex(SolverError, "distributed load load-pressure .*load_type=pressure"):
            assembler.assemble_external_load(model.steps["step-static"])

    def test_nodal_load_remains_supported_on_formal_nlgeom_mainline(self) -> None:
        model = deepcopy(build_static_beam_benchmark_model())
        model.nodal_loads["load-tip"].components = {"FY": -1.0}
        step = model.steps["step-static"]
        step.procedure_type = "static_nonlinear"
        step.parameters = {
            "max_increments": 2,
            "initial_increment": 0.5,
            "min_increment": 0.5,
            "max_iterations": 12,
            "residual_tolerance": 1.0e-10,
            "displacement_tolerance": 1.0e-10,
            "allow_cutback": True,
            "line_search": False,
            "nlgeom": True,
        }

        compiled_model = Compiler().compile(model)
        writer = InMemoryResultsWriter()
        compiled_model.get_step_runtime("step-static").run(writer)

        summary = writer.read_summary("step-static", "static_nonlinear_summary").data
        self.assertTrue(bool(summary["nlgeom"]))
        self.assertEqual(float(summary["load_factor"]), 1.0)

    def _build_nlgeom_pressure_model(self):
        model = build_c3d8_pressure_block_model()
        step = model.steps["step-static"]
        step.procedure_type = "static_nonlinear"
        step.parameters = {
            "max_increments": 4,
            "initial_increment": 0.25,
            "min_increment": 0.25,
            "max_iterations": 8,
            "residual_tolerance": 1.0e-10,
            "displacement_tolerance": 1.0e-10,
            "allow_cutback": True,
            "line_search": False,
            "nlgeom": True,
        }
        return model


if __name__ == "__main__":
    unittest.main()
