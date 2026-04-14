"""静力非线性分析 procedure。"""

from __future__ import annotations

import numpy

from pyfem.foundation.errors import SolverError
from pyfem.io import AXIS_KIND_FRAME_ID, FIELD_KEY_RF, FIELD_KEY_TIME, FIELD_KEY_U, ResultsWriter
from pyfem.procedures.base import ProcedureReport
from pyfem.procedures.nonlinear_support import (
    LineSearchController,
    NonlinearIncrementResult,
    NonlinearIterationMetrics,
    StaticNonlinearParameters,
)
from pyfem.procedures.support import StepProcedureRuntime
from pyfem.solver import ProblemState


class StaticNonlinearProcedure(StepProcedureRuntime):
    """实现静力非线性步骤控制骨架。"""

    def get_state_transfer_channel(self) -> str | None:
        """返回静力非线性步骤的状态继承通道。"""

        return "solid_mechanics_history"

    def run(self, results_writer: ResultsWriter) -> ProcedureReport:
        """执行静力非线性增量迭代并写出正式结果。"""

        parameters = StaticNonlinearParameters.from_step_parameters(self.definition.parameters)
        line_search = LineSearchController(parameters.line_search)
        frame_count = 0
        history_count = 0
        converged_increment_count = 0
        cutback_count = 0
        failed_attempt_count = 0

        self.restore_problem_state_from_previous_step()
        initial_state = self.problem.begin_trial(self.build_step_start_state())
        initial_state.velocity = numpy.zeros_like(initial_state.displacement)
        initial_state.acceleration = numpy.zeros_like(initial_state.displacement)
        initial_state.time = 0.0
        self.problem.commit(initial_state)

        frame_ids = [0]
        load_factors = [0.0]
        residual_norms = [self._compute_residual_norm(state=self.problem.get_committed_state(), load_factor=0.0)]
        displacement_norms = [float(numpy.linalg.norm(initial_state.displacement))]
        iteration_counts = [0]
        time_history_frame_ids: list[int] = []
        time_history_values: list[float] = []

        results_writer.open_session(self.build_results_session())
        try:
            if self.output_planner.should_write_frame(0):
                results_writer.write_frame(
                    self._build_solution_frame(
                        frame_id=0,
                        load_factor=0.0,
                        iteration_count=0,
                        state=self.problem.get_committed_state(),
                    )
                )
                frame_count += 1
            if self.output_planner.should_collect_history(FIELD_KEY_TIME, 0):
                time_history_frame_ids.append(0)
                time_history_values.append(0.0)

            current_load_factor = 0.0
            current_increment = parameters.initial_increment
            while current_load_factor < 1.0 - 1.0e-12:
                if converged_increment_count >= parameters.max_increments:
                    raise SolverError(
                        f"静力非线性步骤 {self.get_name()} 在达到总载荷前已耗尽 max_increments={parameters.max_increments}。"
                    )

                target_increment = min(current_increment, 1.0 - current_load_factor)
                target_load_factor = current_load_factor + target_increment
                frame_id = converged_increment_count + 1

                try:
                    increment_result = self._solve_increment(
                        target_load_factor=target_load_factor,
                        parameters=parameters,
                        line_search=line_search,
                    )
                except SolverError as error:
                    failed_attempt_count += 1
                    self.problem.rollback()
                    if not parameters.allow_cutback:
                        raise SolverError(
                            f"静力非线性步骤 {self.get_name()} 在 load_factor={target_load_factor:.6g} 未收敛，"
                            f"且已禁用 cutback。原因为: {error}"
                        ) from error
                    reduced_increment = target_increment * 0.5
                    if reduced_increment < parameters.min_increment - 1.0e-12:
                        raise SolverError(
                            f"静力非线性步骤 {self.get_name()} 在 load_factor={target_load_factor:.6g} 未收敛，"
                            f"cutback 后增量 {reduced_increment:.6g} 已小于 min_increment={parameters.min_increment:.6g}。"
                            f"原因为: {error}"
                        ) from error
                    current_increment = max(parameters.min_increment, reduced_increment)
                    cutback_count += 1
                    continue

                converged_state = self.problem.get_committed_state()
                current_load_factor = target_load_factor
                converged_increment_count += 1
                current_increment = min(target_increment, 1.0 - current_load_factor)

                frame_ids.append(frame_id)
                load_factors.append(current_load_factor)
                residual_norms.append(increment_result.metrics.residual_norm)
                displacement_norms.append(increment_result.metrics.displacement_norm)
                iteration_counts.append(increment_result.iteration_count)

                if self.output_planner.should_write_frame(frame_id):
                    results_writer.write_frame(
                        self._build_solution_frame(
                            frame_id=frame_id,
                            load_factor=current_load_factor,
                            iteration_count=increment_result.iteration_count,
                            state=converged_state,
                        )
                    )
                    frame_count += 1
                if self.output_planner.should_collect_history(FIELD_KEY_TIME, frame_id):
                    time_history_frame_ids.append(frame_id)
                    time_history_values.append(current_load_factor)

            results_writer.write_history_series(
                self.build_global_history_series(
                    name="load_factor",
                    axis_kind=AXIS_KIND_FRAME_ID,
                    axis_values=tuple(frame_ids),
                    values=tuple(load_factors),
                )
            )
            results_writer.write_history_series(
                self.build_global_history_series(
                    name="residual_norm",
                    axis_kind=AXIS_KIND_FRAME_ID,
                    axis_values=tuple(frame_ids),
                    values=tuple(residual_norms),
                )
            )
            results_writer.write_history_series(
                self.build_global_history_series(
                    name="displacement_norm",
                    axis_kind=AXIS_KIND_FRAME_ID,
                    axis_values=tuple(frame_ids),
                    values=tuple(displacement_norms),
                )
            )
            results_writer.write_history_series(
                self.build_global_history_series(
                    name="iteration_count",
                    axis_kind=AXIS_KIND_FRAME_ID,
                    axis_values=tuple(frame_ids),
                    values=tuple(iteration_counts),
                )
            )
            history_count += 4

            if self.output_planner.requests_history_variable(FIELD_KEY_TIME):
                results_writer.write_history_series(
                    self.build_global_history_series(
                        name=FIELD_KEY_TIME,
                        axis_kind=AXIS_KIND_FRAME_ID,
                        axis_values=tuple(time_history_frame_ids),
                        values=tuple(time_history_values),
                    )
                )
                history_count += 1

            final_state = self.problem.get_committed_state()
            final_residual_norm = self._compute_residual_norm(state=final_state, load_factor=current_load_factor)
            average_iteration_per_increment = (
                0.0 if converged_increment_count == 0 else float(sum(iteration_counts[1:]) / converged_increment_count)
            )
            results_writer.write_summary(
                self.build_summary(
                    name="static_nonlinear_summary",
                    data={
                        "residual_norm": final_residual_norm,
                        "displacement_norm": float(numpy.linalg.norm(final_state.displacement)),
                        "iteration_count": iteration_counts[-1],
                        "converged_increment_count": converged_increment_count,
                        "cutback_count": cutback_count,
                        "failed_attempt_count": failed_attempt_count,
                        "increment_attempt_count": converged_increment_count + failed_attempt_count,
                        "average_iteration_per_increment": average_iteration_per_increment,
                        "final_increment_size": 0.0 if len(load_factors) < 2 else load_factors[-1] - load_factors[-2],
                        "load_factor": current_load_factor,
                        "line_search": line_search.enabled,
                        "line_search_mode": line_search.describe(),
                        "nlgeom": parameters.nlgeom,
                    },
                )
            )
            history_count += 1
            self.publish_problem_state_to_following_steps()
            return ProcedureReport(
                procedure_name=self.get_name(),
                frame_count=frame_count,
                history_count=history_count,
            )
        finally:
            results_writer.close_session()

    def _solve_increment(
        self,
        *,
        target_load_factor: float,
        parameters: StaticNonlinearParameters,
        line_search: LineSearchController,
    ) -> NonlinearIncrementResult:
        """求解一个目标载荷增量。"""

        trial_state = self.problem.begin_trial(self.problem.get_committed_state())
        trial_state.time = target_load_factor
        trial_state.velocity = numpy.zeros_like(trial_state.displacement)
        trial_state.acceleration = numpy.zeros_like(trial_state.displacement)

        prescribed_values = self.problem.build_constraint_value_map(
            self.definition.boundary_names,
            scale_factor=target_load_factor,
        )
        last_metrics = NonlinearIterationMetrics(
            residual_norm=self._compute_residual_norm(state=trial_state, load_factor=target_load_factor),
            displacement_increment_norm=0.0,
            displacement_norm=float(numpy.linalg.norm(trial_state.displacement)),
        )

        for iteration_index in range(1, parameters.max_iterations + 1):
            tangent = self.problem.assemble_tangent(state=trial_state)
            residual_vector = self._build_equilibrium_residual_vector(
                state=trial_state,
                load_factor=target_load_factor,
            )
            prescribed_corrections = {
                dof_index: float(target_value - trial_state.displacement[dof_index])
                for dof_index, target_value in prescribed_values.items()
            }
            constrained_tangent, constrained_rhs = self.problem.apply_prescribed_values(
                tangent,
                residual_vector,
                prescribed_corrections,
            )
            displacement_increment = self.backend.solve_linear_system(constrained_tangent, constrained_rhs)
            step_length = line_search.select_step_length()
            scaled_increment = step_length * numpy.asarray(displacement_increment, dtype=float)
            trial_state.displacement = trial_state.displacement + scaled_increment
            trial_state.time = target_load_factor

            last_metrics = NonlinearIterationMetrics(
                residual_norm=self._compute_residual_norm(state=trial_state, load_factor=target_load_factor),
                displacement_increment_norm=float(numpy.linalg.norm(scaled_increment)),
                displacement_norm=float(numpy.linalg.norm(trial_state.displacement)),
            )
            if self._is_converged(iteration_index=iteration_index, metrics=last_metrics, parameters=parameters):
                self.problem.commit(trial_state)
                return NonlinearIncrementResult(metrics=last_metrics, iteration_count=iteration_index)

        raise SolverError(
            f"静力非线性步骤 {self.get_name()} 在 load_factor={target_load_factor:.6g} "
            f"超过 max_iterations={parameters.max_iterations} 仍未收敛。"
        )

    def _is_converged(
        self,
        *,
        iteration_index: int,
        metrics: NonlinearIterationMetrics,
        parameters: StaticNonlinearParameters,
    ) -> bool:
        """判断当前增量是否满足收敛条件。"""

        residual_converged = metrics.residual_norm <= parameters.residual_tolerance
        displacement_converged = metrics.displacement_increment_norm <= parameters.displacement_tolerance
        # 线性问题在首轮 Newton 更新后应直接收敛，因此首轮允许仅按残量判据结束。
        return residual_converged and (displacement_converged or iteration_index == 1)

    def _build_equilibrium_residual_vector(self, *, state: ProblemState, load_factor: float) -> numpy.ndarray:
        """构造当前 Newton 迭代的平衡残量向量。"""

        external_load = self.problem.assemble_external_load(
            self.definition,
            time=load_factor,
            state=state,
            load_scale=load_factor,
        )
        internal_force = self.problem.assemble_residual(state=state)
        return numpy.asarray(external_load - internal_force, dtype=float)

    def _compute_residual_norm(self, *, state: ProblemState, load_factor: float) -> float:
        """计算忽略约束自由度后的残量范数。"""

        residual_vector = -self._build_equilibrium_residual_vector(state=state, load_factor=load_factor)
        constrained_dofs = self.problem.build_constraint_value_map(
            self.definition.boundary_names,
            scale_factor=load_factor,
        )
        unconstrained_residual = numpy.asarray(residual_vector, dtype=float).copy()
        for dof_index in constrained_dofs:
            unconstrained_residual[dof_index] = 0.0
        return float(numpy.linalg.norm(unconstrained_residual))

    def _build_solution_frame(
        self,
        *,
        frame_id: int,
        load_factor: float,
        iteration_count: int,
        state: ProblemState,
    ):
        """构造一个收敛状态结果帧。"""

        external_load = self.problem.assemble_external_load(
            self.definition,
            time=load_factor,
            state=state,
            load_scale=load_factor,
        )
        reaction_vector = self.problem.assemble_residual(state=state) - external_load
        return self.build_frame(
            frame_id=frame_id,
            time=load_factor,
            displacement=state.displacement,
            state=state,
            field_vectors={FIELD_KEY_U: state.displacement, FIELD_KEY_RF: reaction_vector},
            metadata={
                "load_factor": load_factor,
                "iteration_count": iteration_count,
            },
            axis_kind=AXIS_KIND_FRAME_ID,
            axis_value=frame_id,
        )
