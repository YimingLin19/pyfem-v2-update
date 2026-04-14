"""模态分析 procedure。"""

from __future__ import annotations

import math

from pyfem.foundation.errors import SolverError
from pyfem.io import (
    AXIS_KIND_MODE_INDEX,
    FIELD_KEY_FREQUENCY,
    FIELD_KEY_MODE_SHAPE,
    FRAME_KIND_MODE,
    MODAL_METADATA_KEY_EIGENVALUE,
    MODAL_METADATA_KEY_FREQUENCY_HZ,
    MODAL_METADATA_KEY_MODE_INDEX,
    PAIRED_VALUE_KEY_EIGENVALUE,
    ResultsWriter,
)
from pyfem.procedures.base import ProcedureReport
from pyfem.procedures.support import StepProcedureRuntime


class ModalProcedure(StepProcedureRuntime):
    """实现小变形线弹性模态分析。"""

    def run(self, results_writer: ResultsWriter) -> ProcedureReport:
        """执行模态分析并写出模态结果。"""

        frame_count = 0
        history_count = 0
        results_writer.open_session(self.build_results_session())
        try:
            trial_state = self.problem.begin_trial()
            tangent = self.problem.assemble_tangent(state=trial_state)
            mass = self.problem.assemble_mass(state=trial_state)
            reduced_tangent = self.problem.reduce_matrix(tangent, self.definition.boundary_names)
            reduced_mass = self.problem.reduce_matrix(mass, self.definition.boundary_names)
            if reduced_tangent.free_indices != reduced_mass.free_indices:
                raise SolverError("模态分析的缩减刚度矩阵与质量矩阵自由度集合不一致。")

            requested_modes = int(self.definition.parameters.get("num_modes", 6))
            eigenvalues, eigenvectors = self.backend.solve_generalized_eigenproblem(
                reduced_tangent.matrix,
                reduced_mass.matrix,
                requested_modes,
            )
            prescribed_values = self.problem.build_constraint_value_map(self.definition.boundary_names)
            sampled_mode_indices: list[int] = []
            sampled_frequencies: list[float] = []
            sampled_eigenvalues: list[float] = []

            for mode_index in range(eigenvalues.size):
                full_mode = self.problem.expand_reduced_vector(
                    eigenvectors[:, mode_index],
                    reduced_tangent.free_indices,
                    prescribed_values=prescribed_values,
                )
                max_abs = max(abs(value) for value in full_mode.tolist())
                if max_abs > 0.0:
                    full_mode = full_mode / max_abs
                eigenvalue = float(eigenvalues[mode_index])
                frequency_hz = math.sqrt(eigenvalue) / (2.0 * math.pi)
                if self.output_planner.should_write_frame(mode_index):
                    results_writer.write_frame(
                        self.build_frame(
                            frame_id=mode_index,
                            time=0.0,
                            displacement=None,
                            state=trial_state,
                            field_vectors={FIELD_KEY_MODE_SHAPE: full_mode},
                            metadata={
                                MODAL_METADATA_KEY_MODE_INDEX: mode_index,
                                MODAL_METADATA_KEY_FREQUENCY_HZ: frequency_hz,
                                MODAL_METADATA_KEY_EIGENVALUE: eigenvalue,
                            },
                            frame_kind=FRAME_KIND_MODE,
                            axis_kind=AXIS_KIND_MODE_INDEX,
                            axis_value=mode_index,
                        )
                    )
                    frame_count += 1
                if self.output_planner.should_collect_history(FIELD_KEY_FREQUENCY, mode_index):
                    sampled_mode_indices.append(mode_index)
                    sampled_frequencies.append(frequency_hz)
                    sampled_eigenvalues.append(eigenvalue)

            if self.output_planner.requests_history_variable(FIELD_KEY_FREQUENCY):
                results_writer.write_history_series(
                    self.build_global_history_series(
                        name=FIELD_KEY_FREQUENCY,
                        axis_kind=AXIS_KIND_MODE_INDEX,
                        axis_values=tuple(sampled_mode_indices),
                        values=tuple(sampled_frequencies),
                        paired_values={PAIRED_VALUE_KEY_EIGENVALUE: tuple(sampled_eigenvalues)},
                    )
                )
                history_count += 1
            return ProcedureReport(procedure_name=self.get_name(), frame_count=frame_count, history_count=history_count)
        finally:
            results_writer.close_session()
