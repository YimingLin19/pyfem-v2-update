"""static_nonlinear 程序骨架回归测试。"""

from __future__ import annotations

import unittest
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

import numpy

from pyfem.compiler import Compiler
from pyfem.foundation.errors import SolverError
from pyfem.io import FIELD_KEY_RF, FIELD_KEY_U, InMemoryResultsWriter
from pyfem.modeldb import ModelDB
from pyfem.solver import LinearAlgebraBackend
from tests.support.model_builders import (
    build_c3d8_pressure_block_model,
    build_cps4_tension_model,
    build_static_beam_benchmark_model,
)


class ThresholdScalingBackend(LinearAlgebraBackend):
    """按右端范数切换缩放策略的测试 backend。"""

    def __init__(self, *, threshold: float, scale_above_threshold: float) -> None:
        self._threshold = float(threshold)
        self._scale_above_threshold = float(scale_above_threshold)

    def solve_linear_system(self, matrix: numpy.ndarray, rhs: numpy.ndarray) -> numpy.ndarray:
        exact_solution = numpy.linalg.solve(numpy.asarray(matrix, dtype=float), numpy.asarray(rhs, dtype=float))
        if float(numpy.linalg.norm(rhs)) > self._threshold:
            return self._scale_above_threshold * exact_solution
        return exact_solution

    def solve_generalized_eigenproblem(
        self,
        stiffness: numpy.ndarray,
        mass: numpy.ndarray,
        num_modes: int,
    ) -> tuple[numpy.ndarray, numpy.ndarray]:
        raise NotImplementedError("当前测试 backend 不覆盖模态分析。")


class StaticNonlinearRegressionTests(unittest.TestCase):
    """验证 static_nonlinear 与现有主线的兼容性。"""

    def test_static_nonlinear_matches_static_linear_on_b21_benchmark(self) -> None:
        self._assert_linear_equivalence(build_static_beam_benchmark_model(), expected_increment_count=2)

    def test_static_nonlinear_matches_static_linear_on_cps4_benchmark(self) -> None:
        self._assert_linear_equivalence(build_cps4_tension_model(), expected_increment_count=2)

    def test_static_nonlinear_matches_static_linear_on_c3d8_benchmark(self) -> None:
        self._assert_linear_equivalence(build_c3d8_pressure_block_model(), expected_increment_count=2)

    def test_static_nonlinear_rolls_back_and_cutbacks_when_large_increment_fails(self) -> None:
        linear_model = build_static_beam_benchmark_model()
        nonlinear_model = self._build_nonlinear_variant(
            linear_model,
            parameters={
                "max_increments": 4,
                "initial_increment": 1.0,
                "min_increment": 0.25,
                "max_iterations": 1,
                "residual_tolerance": 1.0e-10,
                "displacement_tolerance": 1.0e-10,
                "allow_cutback": True,
                "line_search": False,
                "nlgeom": False,
            },
        )

        linear_writer = self._run_step(linear_model)
        nonlinear_writer = self._run_step(
            nonlinear_model,
            backend=ThresholdScalingBackend(threshold=8.0, scale_above_threshold=0.5),
        )

        nonlinear_summary = nonlinear_writer.read_summary("step-static", "static_nonlinear_summary").data
        nonlinear_load_history = nonlinear_writer.read_history("step-static", "load_factor").get_series()
        nonlinear_iteration_history = nonlinear_writer.read_history("step-static", "iteration_count").get_series()

        self.assertEqual(nonlinear_summary["cutback_count"], 1)
        self.assertEqual(nonlinear_summary["failed_attempt_count"], 1)
        self.assertEqual(nonlinear_summary["converged_increment_count"], 2)
        self.assertEqual(nonlinear_load_history, (0.0, 0.5, 1.0))
        self.assertEqual(nonlinear_iteration_history, (0, 1, 1))
        self._assert_fields_close(
            linear_writer.read_step("step-static").frames[-1].get_field(FIELD_KEY_U).values,
            nonlinear_writer.read_step("step-static").frames[-1].get_field(FIELD_KEY_U).values,
        )

    def test_static_nonlinear_fails_fast_when_max_iterations_is_exceeded(self) -> None:
        model = self._build_nonlinear_variant(
            build_static_beam_benchmark_model(),
            parameters={
                "max_increments": 1,
                "initial_increment": 1.0,
                "min_increment": 1.0,
                "max_iterations": 1,
                "residual_tolerance": 1.0e-10,
                "displacement_tolerance": 1.0e-10,
                "allow_cutback": False,
                "line_search": False,
                "nlgeom": False,
            },
        )

        with self.assertRaisesRegex(SolverError, "max_iterations=1"):
            self._run_step(model, backend=ThresholdScalingBackend(threshold=-1.0, scale_above_threshold=0.5))

    def test_static_nonlinear_reports_error_when_cutback_is_disabled(self) -> None:
        model = self._build_nonlinear_variant(
            build_static_beam_benchmark_model(),
            parameters={
                "max_increments": 1,
                "initial_increment": 1.0,
                "min_increment": 1.0,
                "max_iterations": 1,
                "residual_tolerance": 1.0e-10,
                "displacement_tolerance": 1.0e-10,
                "allow_cutback": False,
                "line_search": False,
                "nlgeom": False,
            },
        )

        with self.assertRaisesRegex(SolverError, "已禁用 cutback"):
            self._run_step(model, backend=ThresholdScalingBackend(threshold=-1.0, scale_above_threshold=0.5))

    def _assert_linear_equivalence(self, linear_model: ModelDB, *, expected_increment_count: int) -> None:
        nonlinear_model = self._build_nonlinear_variant(
            linear_model,
            parameters={
                "max_increments": expected_increment_count,
                "initial_increment": 1.0 / expected_increment_count,
                "min_increment": 1.0 / expected_increment_count,
                "max_iterations": 4,
                "residual_tolerance": 1.0e-12,
                "displacement_tolerance": 1.0e-12,
                "allow_cutback": True,
                "line_search": False,
                "nlgeom": False,
            },
        )

        linear_writer = self._run_step(linear_model)
        nonlinear_writer = self._run_step(nonlinear_model)

        linear_frame = linear_writer.read_step("step-static").frames[-1]
        nonlinear_frame = nonlinear_writer.read_step("step-static").frames[-1]
        nonlinear_summary = nonlinear_writer.read_summary("step-static", "static_nonlinear_summary").data
        nonlinear_iteration_history = nonlinear_writer.read_history("step-static", "iteration_count").get_series()
        nonlinear_load_history = nonlinear_writer.read_history("step-static", "load_factor").get_series()

        self._assert_fields_close(linear_frame.get_field(FIELD_KEY_U).values, nonlinear_frame.get_field(FIELD_KEY_U).values)
        self._assert_fields_close(linear_frame.get_field(FIELD_KEY_RF).values, nonlinear_frame.get_field(FIELD_KEY_RF).values)
        self.assertEqual(nonlinear_summary["converged_increment_count"], expected_increment_count)
        self.assertEqual(nonlinear_iteration_history[1:], tuple(1 for _ in range(expected_increment_count)))
        self.assertEqual(nonlinear_load_history[-1], 1.0)

    def _run_step(self, model: ModelDB, backend: LinearAlgebraBackend | None = None) -> InMemoryResultsWriter:
        compiled_model = Compiler().compile(model)
        step_runtime = compiled_model.get_step_runtime("step-static")
        if backend is not None:
            step_runtime.backend = backend
        writer = InMemoryResultsWriter()
        step_runtime.run(writer)
        return writer

    def _build_nonlinear_variant(self, model: ModelDB, *, parameters: dict[str, Any]) -> ModelDB:
        nonlinear_model = deepcopy(model)
        step_definition = nonlinear_model.steps["step-static"]
        step_definition.procedure_type = "static_nonlinear"
        step_definition.parameters = dict(parameters)
        return nonlinear_model

    def _assert_fields_close(self, expected: Mapping[str, Any], actual: Mapping[str, Any], tol: float = 1.0e-10) -> None:
        self.assertEqual(set(expected.keys()), set(actual.keys()))
        for key in expected:
            self._assert_value_close(expected[key], actual[key], tol=tol)

    def _assert_value_close(self, expected: Any, actual: Any, *, tol: float) -> None:
        if isinstance(expected, Mapping):
            self.assertIsInstance(actual, Mapping)
            self._assert_fields_close(expected, actual, tol=tol)
            return
        self.assertAlmostEqual(float(expected), float(actual), delta=tol)


if __name__ == "__main__":
    unittest.main()
