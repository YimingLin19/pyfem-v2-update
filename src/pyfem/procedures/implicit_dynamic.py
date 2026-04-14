"""隐式动力学 procedure。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy

from pyfem.foundation.errors import SolverError
from pyfem.io import AXIS_KIND_FRAME_ID, FIELD_KEY_TIME, FIELD_KEY_U, ResultsWriter
from pyfem.procedures.base import ProcedureReport
from pyfem.procedures.support import StepProcedureRuntime


@dataclass(slots=True, frozen=True)
class NewmarkParameters:
    """定义 Newmark 积分参数。"""

    time_step: float
    num_steps: int
    beta: float
    gamma: float


class ImplicitDynamicProcedure(StepProcedureRuntime):
    """实现基于 Newmark 的基础隐式动力学分析。"""

    def run(self, results_writer: ResultsWriter) -> ProcedureReport:
        """执行隐式动力学分析并写出结果。"""

        integration = self._resolve_integration_parameters()
        frame_count = 0
        history_count = 0
        results_writer.open_session(self.build_results_session())
        try:
            state = self.problem.begin_trial(self.build_initial_state())
            constraint_values = self.problem.build_constraint_value_map(self.definition.boundary_names)
            for dof_index, value in constraint_values.items():
                state.displacement[dof_index] = float(value)
                state.velocity[dof_index] = 0.0
                state.acceleration[dof_index] = 0.0

            mass = self.problem.assemble_mass(state=state)
            damping = self.problem.assemble_damping(state=state)
            tangent = self.problem.assemble_tangent(state=state)
            zero_acceleration_constraints = {dof_index: 0.0 for dof_index in constraint_values}
            initial_load = self.problem.assemble_external_load(self.definition, time=0.0, state=state)
            acceleration_rhs = initial_load - damping @ state.velocity - tangent @ state.displacement
            constrained_mass, constrained_rhs = self.problem.apply_prescribed_values(
                mass,
                acceleration_rhs,
                zero_acceleration_constraints,
            )
            state.acceleration = self.backend.solve_linear_system(constrained_mass, constrained_rhs)
            for dof_index in zero_acceleration_constraints:
                state.acceleration[dof_index] = 0.0
            self.problem.commit()

            sampled_frame_ids: list[int] = []
            sampled_times: list[float] = []
            times = [0.0]
            displacement_norms = [float(numpy.linalg.norm(state.displacement))]
            if self.output_planner.should_write_frame(0):
                results_writer.write_frame(
                    self.build_frame(
                        frame_id=0,
                        time=0.0,
                        displacement=state.displacement,
                        state=state,
                        field_vectors={FIELD_KEY_U: state.displacement},
                    )
                )
                frame_count += 1
            if self.output_planner.should_collect_history(FIELD_KEY_TIME, 0):
                sampled_frame_ids.append(0)
                sampled_times.append(0.0)

            a0 = 1.0 / (integration.beta * integration.time_step**2)
            a1 = integration.gamma / (integration.beta * integration.time_step)
            a2 = 1.0 / (integration.beta * integration.time_step)
            a3 = 1.0 / (2.0 * integration.beta) - 1.0
            a4 = integration.gamma / integration.beta - 1.0
            a5 = integration.time_step * (integration.gamma / (2.0 * integration.beta) - 1.0)
            a6 = integration.time_step * (1.0 - integration.gamma)
            a7 = integration.gamma * integration.time_step

            for step_index in range(1, integration.num_steps + 1):
                time = step_index * integration.time_step
                external_load = self.problem.assemble_external_load(self.definition, time=time, state=state)
                effective_tangent = tangent + a0 * mass + a1 * damping
                effective_rhs = (
                    external_load
                    + mass @ (a0 * state.displacement + a2 * state.velocity + a3 * state.acceleration)
                    + damping @ (a1 * state.displacement + a4 * state.velocity + a5 * state.acceleration)
                )
                constrained_tangent, constrained_rhs = self.problem.apply_prescribed_values(
                    effective_tangent,
                    effective_rhs,
                    constraint_values,
                )
                next_displacement = self.backend.solve_linear_system(constrained_tangent, constrained_rhs)
                next_acceleration = (
                    a0 * (next_displacement - state.displacement)
                    - a2 * state.velocity
                    - a3 * state.acceleration
                )
                next_velocity = state.velocity + a6 * state.acceleration + a7 * next_acceleration

                next_state = self.problem.begin_trial(state)
                next_state.displacement = numpy.asarray(next_displacement, dtype=float)
                next_state.velocity = numpy.asarray(next_velocity, dtype=float)
                next_state.acceleration = numpy.asarray(next_acceleration, dtype=float)
                next_state.time = time
                for dof_index, value in constraint_values.items():
                    next_state.displacement[dof_index] = float(value)
                    next_state.velocity[dof_index] = 0.0
                    next_state.acceleration[dof_index] = 0.0

                state = next_state
                self.problem.commit()
                if self.output_planner.should_write_frame(step_index):
                    results_writer.write_frame(
                        self.build_frame(
                            frame_id=step_index,
                            time=time,
                            displacement=state.displacement,
                            state=state,
                            field_vectors={FIELD_KEY_U: state.displacement},
                        )
                    )
                    frame_count += 1
                if self.output_planner.should_collect_history(FIELD_KEY_TIME, step_index):
                    sampled_frame_ids.append(step_index)
                    sampled_times.append(time)
                times.append(time)
                displacement_norms.append(float(numpy.linalg.norm(state.displacement)))

            if self.output_planner.requests_history_variable(FIELD_KEY_TIME):
                results_writer.write_history_series(
                    self.build_global_history_series(
                        name=FIELD_KEY_TIME,
                        axis_kind=AXIS_KIND_FRAME_ID,
                        axis_values=tuple(sampled_frame_ids),
                        values=tuple(sampled_times),
                    )
                )
                history_count += 1
            results_writer.write_summary(
                self.build_summary(
                    name="dynamic_summary",
                    data={
                        "scheme": "newmark",
                        "time_step": integration.time_step,
                        "num_steps": integration.num_steps,
                        "times": tuple(times),
                        "displacement_norms": tuple(displacement_norms),
                    },
                )
            )
            history_count += 1
            return ProcedureReport(procedure_name=self.get_name(), frame_count=frame_count, history_count=history_count)
        finally:
            results_writer.close_session()

    def _resolve_integration_parameters(self) -> NewmarkParameters:
        time_step = float(self.definition.parameters.get("time_step", 1.0))
        beta = float(self.definition.parameters.get("beta", 0.25))
        gamma = float(self.definition.parameters.get("gamma", 0.5))
        if "num_steps" in self.definition.parameters:
            num_steps = int(self.definition.parameters["num_steps"])
        else:
            total_time = float(self.definition.parameters.get("total_time", time_step))
            num_steps = int(round(total_time / time_step))
        if time_step <= 0.0:
            raise SolverError("隐式动力学时间步长必须大于零。")
        if num_steps <= 0:
            raise SolverError("隐式动力学步数必须为正整数。")
        return NewmarkParameters(time_step=time_step, num_steps=num_steps, beta=beta, gamma=gamma)
