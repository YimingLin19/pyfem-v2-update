"""静力线性分析 procedure。"""

from __future__ import annotations

import numpy

from pyfem.io import AXIS_KIND_FRAME_ID, FIELD_KEY_RF, FIELD_KEY_TIME, FIELD_KEY_U, ResultsWriter
from pyfem.procedures.base import ProcedureReport
from pyfem.procedures.support import StepProcedureRuntime


class StaticLinearProcedure(StepProcedureRuntime):
    """实现小变形线弹性静力线性分析。"""

    def run(self, results_writer: ResultsWriter) -> ProcedureReport:
        """执行静力线性分析并写出结果。"""

        frame_count = 0
        history_count = 0
        results_writer.open_session(self.build_results_session())
        try:
            trial_state = self.problem.begin_trial()
            tangent = self.problem.assemble_tangent(state=trial_state)
            external_load = self.problem.assemble_external_load(self.definition, time=0.0, state=trial_state)
            constrained_tangent, constrained_rhs = self.problem.apply_constraints(
                tangent,
                external_load,
                self.definition.boundary_names,
            )
            solved_displacement = self.backend.solve_linear_system(constrained_tangent, constrained_rhs)
            trial_state.displacement = numpy.asarray(solved_displacement, dtype=float)
            trial_state.velocity = numpy.zeros_like(solved_displacement, dtype=float)
            trial_state.acceleration = numpy.zeros_like(solved_displacement, dtype=float)
            trial_state.time = 0.0
            self.problem.commit()

            reaction_vector = self.problem.assemble_residual(state=trial_state) - external_load
            if self.output_planner.should_write_frame(0):
                results_writer.write_frame(
                    self.build_frame(
                        frame_id=0,
                        time=0.0,
                        displacement=trial_state.displacement,
                        state=trial_state,
                        field_vectors={FIELD_KEY_U: trial_state.displacement, FIELD_KEY_RF: reaction_vector},
                    )
                )
                frame_count += 1

            unconstrained_residual = reaction_vector.copy()
            for dof_index in self.problem.build_constraint_value_map(self.definition.boundary_names):
                unconstrained_residual[dof_index] = 0.0
            results_writer.write_summary(
                self.build_summary(
                    name="static_summary",
                    data={
                        "residual_norm": float(numpy.linalg.norm(unconstrained_residual)),
                        "load_norm": float(numpy.linalg.norm(external_load)),
                        "displacement_norm": float(numpy.linalg.norm(trial_state.displacement)),
                    },
                )
            )
            history_count += 1

            if self.output_planner.should_collect_history(FIELD_KEY_TIME, 0):
                results_writer.write_history_series(
                    self.build_global_history_series(
                        name=FIELD_KEY_TIME,
                        axis_kind=AXIS_KIND_FRAME_ID,
                        axis_values=(0,),
                        values=(0.0,),
                    )
                )
                history_count += 1

            return ProcedureReport(procedure_name=self.get_name(), frame_count=frame_count, history_count=history_count)
        finally:
            results_writer.close_session()
