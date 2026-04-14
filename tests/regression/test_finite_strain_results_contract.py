"""finite-strain 结果语义合同回归测试。"""

from __future__ import annotations

import unittest

from pyfem.compiler import Compiler
from pyfem.io import (
    FIELD_KEY_E,
    FIELD_KEY_E_IP,
    FIELD_KEY_E_REC,
    FIELD_KEY_S,
    FIELD_KEY_S_AVG,
    FIELD_KEY_S_IP,
    FIELD_KEY_S_REC,
    FIELD_KEY_S_VM_IP,
    InMemoryResultsWriter,
)
from pyfem.modeldb import OutputRequest
from pyfem.post.common import (
    FIELD_METADATA_KEY_DERIVED_FROM,
    FIELD_METADATA_KEY_KINEMATIC_REGIME,
    FIELD_METADATA_KEY_STRAIN_MEASURE,
    FIELD_METADATA_KEY_STRAIN_MEASURES,
    FIELD_METADATA_KEY_STRESS_MEASURE,
    FIELD_METADATA_KEY_STRESS_MEASURES,
    FIELD_METADATA_KEY_TANGENT_MEASURE,
)
from tests.support.solid_finite_strain_j2_builders import build_c3d8_j2_model, build_cps4_j2_model


class FiniteStrainResultsContractRegressionTests(unittest.TestCase):
    """验证 finite-strain 与 small-strain 的结果测度语义不会混淆。"""

    def test_cps4_finite_and_small_strain_paths_write_clear_measure_metadata(self) -> None:
        finite_model = build_cps4_j2_model(
            model_name="cps4-finite-results-contract",
            nlgeom=True,
            right_displacement=0.004,
            include_material_fields=True,
        )
        self._extend_measure_output_requests(finite_model)
        finite_writer = self._run_single_step(
            finite_model
        )

        small_model = build_cps4_j2_model(
            model_name="cps4-small-results-contract",
            nlgeom=False,
            right_displacement=0.004,
            include_material_fields=True,
        )
        self._extend_measure_output_requests(small_model)
        small_writer = self._run_single_step(
            small_model
        )

        finite_frame = finite_writer.read_step("step-static").frames[-1]
        small_frame = small_writer.read_step("step-static").frames[-1]
        finite_e = finite_frame.get_field(FIELD_KEY_E)
        finite_s = finite_frame.get_field(FIELD_KEY_S)
        finite_e_ip = finite_frame.get_field(FIELD_KEY_E_IP)
        finite_s_ip = finite_frame.get_field(FIELD_KEY_S_IP)
        finite_e_rec = finite_frame.get_field(FIELD_KEY_E_REC)
        finite_s_rec = finite_frame.get_field(FIELD_KEY_S_REC)
        finite_s_avg = finite_frame.get_field(FIELD_KEY_S_AVG)
        finite_s_vm_ip = finite_frame.get_field(FIELD_KEY_S_VM_IP)
        small_e = small_frame.get_field(FIELD_KEY_E)
        small_s = small_frame.get_field(FIELD_KEY_S)
        small_e_ip = small_frame.get_field(FIELD_KEY_E_IP)
        small_s_ip = small_frame.get_field(FIELD_KEY_S_IP)

        self.assertEqual(finite_e.metadata[FIELD_METADATA_KEY_STRAIN_MEASURE], "green_lagrange")
        self.assertEqual(finite_s.metadata[FIELD_METADATA_KEY_STRESS_MEASURE], "second_piola_kirchhoff")
        self.assertEqual(finite_e.metadata[FIELD_METADATA_KEY_KINEMATIC_REGIME], "finite_strain")
        self.assertEqual(finite_s.metadata[FIELD_METADATA_KEY_TANGENT_MEASURE], "d_second_piola_kirchhoff_d_green_lagrange")
        self.assertEqual(finite_e_ip.metadata[FIELD_METADATA_KEY_STRAIN_MEASURE], "green_lagrange")
        self.assertEqual(finite_s_ip.metadata[FIELD_METADATA_KEY_STRESS_MEASURE], "second_piola_kirchhoff")
        self.assertEqual(finite_s_avg.metadata[FIELD_METADATA_KEY_STRESS_MEASURE], "second_piola_kirchhoff")
        self.assertEqual(finite_s_avg.metadata[FIELD_METADATA_KEY_KINEMATIC_REGIME], "finite_strain")
        self.assertEqual(finite_s_vm_ip.metadata[FIELD_METADATA_KEY_DERIVED_FROM], FIELD_KEY_S_IP)
        self.assertEqual(finite_s_vm_ip.metadata[FIELD_METADATA_KEY_STRESS_MEASURE], "second_piola_kirchhoff")
        self.assertEqual(small_e_ip.metadata[FIELD_METADATA_KEY_STRAIN_MEASURE], "small_strain")
        self.assertEqual(small_s_ip.metadata[FIELD_METADATA_KEY_STRESS_MEASURE], "cauchy_small_strain")
        self.assertEqual(small_e.metadata[FIELD_METADATA_KEY_KINEMATIC_REGIME], "small_strain")
        self.assertEqual(small_s.metadata[FIELD_METADATA_KEY_TANGENT_MEASURE], "d_cauchy_small_strain_d_small_strain")
        self.assertEqual(
            set(finite_e_ip.metadata[FIELD_METADATA_KEY_STRAIN_MEASURES].values()),
            {"green_lagrange"},
        )
        self.assertEqual(
            set(finite_s_ip.metadata[FIELD_METADATA_KEY_STRESS_MEASURES].values()),
            {"second_piola_kirchhoff"},
        )
        self.assertEqual(finite_e_rec.metadata[FIELD_METADATA_KEY_STRAIN_MEASURE], "green_lagrange")
        self.assertEqual(finite_s_rec.metadata[FIELD_METADATA_KEY_STRESS_MEASURE], "second_piola_kirchhoff")

    def test_c3d8_finite_strain_results_reader_contract_remains_intact(self) -> None:
        writer = self._run_single_step(
            self._build_extended_c3d8_model()
        )

        step = writer.read_step("step-static")
        frame = step.frames[-1]
        field_names = tuple(field.name for field in frame.fields)
        self.assertIn(FIELD_KEY_E, field_names)
        self.assertIn(FIELD_KEY_S, field_names)
        self.assertIn(FIELD_KEY_E_IP, field_names)
        self.assertIn(FIELD_KEY_S_IP, field_names)
        self.assertIn(FIELD_KEY_S_AVG, field_names)
        self.assertIn(FIELD_KEY_S_VM_IP, field_names)
        self.assertEqual(frame.get_field(FIELD_KEY_E).metadata[FIELD_METADATA_KEY_KINEMATIC_REGIME], "finite_strain")
        self.assertEqual(frame.get_field(FIELD_KEY_E_IP).metadata[FIELD_METADATA_KEY_STRAIN_MEASURE], "green_lagrange")
        self.assertEqual(frame.get_field(FIELD_KEY_S_IP).metadata[FIELD_METADATA_KEY_STRESS_MEASURE], "second_piola_kirchhoff")
        self.assertEqual(
            frame.get_field(FIELD_KEY_S_AVG).metadata[FIELD_METADATA_KEY_TANGENT_MEASURE],
            "d_second_piola_kirchhoff_d_green_lagrange",
        )

    def _run_single_step(self, model) -> InMemoryResultsWriter:
        compiled_model = Compiler().compile(model)
        writer = InMemoryResultsWriter()
        compiled_model.get_step_runtime("step-static").run(writer)
        return writer

    def _build_extended_c3d8_model(self):
        model = build_c3d8_j2_model(
            model_name="c3d8-finite-results-contract",
            nlgeom=True,
            right_displacement=0.004,
            include_material_fields=True,
        )
        self._extend_measure_output_requests(model)
        return model

    def _extend_measure_output_requests(self, model) -> None:
        model.add_output_request(
            OutputRequest(
                name="field-centroid",
                variables=(FIELD_KEY_E, FIELD_KEY_S),
                target_type="model",
                position="ELEMENT_CENTROID",
            )
        )
        model.add_output_request(
            OutputRequest(
                name="field-avg",
                variables=(FIELD_KEY_S_AVG,),
                target_type="model",
                position="NODE_AVERAGED",
            )
        )
        model.add_output_request(
            OutputRequest(
                name="field-derived",
                variables=(FIELD_KEY_S_VM_IP,),
                target_type="model",
                position="INTEGRATION_POINT",
            )
        )
        step = model.steps["step-static"]
        step.output_request_names = tuple(step.output_request_names) + ("field-centroid", "field-avg", "field-derived")


if __name__ == "__main__":
    unittest.main()
