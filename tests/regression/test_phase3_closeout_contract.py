"""Phase 3 closeout 合同回归测试。"""

from __future__ import annotations

import unittest

from pyfem.compiler import Compiler
from pyfem.foundation.errors import CompilationError
from pyfem.io import (
    FIELD_KEY_E,
    FIELD_KEY_E_IP,
    FIELD_KEY_E_REC,
    FIELD_KEY_S,
    FIELD_KEY_S_AVG,
    FIELD_KEY_S_IP,
    FIELD_KEY_S_REC,
    InMemoryResultsWriter,
)
from pyfem.modeldb import OutputRequest, SectionDef
from pyfem.post.common import (
    FIELD_METADATA_KEY_KINEMATIC_REGIME,
    FIELD_METADATA_KEY_STRAIN_MEASURE,
    FIELD_METADATA_KEY_STRESS_MEASURE,
    FIELD_METADATA_KEY_TANGENT_MEASURE,
)
from tests.support.solid_finite_strain_j2_builders import build_c3d8_j2_model, build_cps4_j2_model


class Phase3CloseoutContractRegressionTests(unittest.TestCase):
    """验证 Phase 3 已支持与未支持边界都已正式收口。"""

    def test_supported_finite_strain_subsets_publish_consistent_measure_contract(self) -> None:
        for model in (
            self._build_extended_material_output_model(
                build_cps4_j2_model(
                    model_name="phase3-closeout-cps4",
                    nlgeom=True,
                    right_displacement=0.004,
                    include_material_fields=True,
                )
            ),
            self._build_extended_material_output_model(
                build_c3d8_j2_model(
                    model_name="phase3-closeout-c3d8",
                    nlgeom=True,
                    right_displacement=0.004,
                    include_material_fields=True,
                )
            ),
        ):
            writer = self._run_single_step(model)
            frame = writer.read_step("step-static").frames[-1]

            for field_name in (FIELD_KEY_E, FIELD_KEY_E_IP, FIELD_KEY_E_REC):
                field = frame.get_field(field_name)
                self.assertEqual(field.metadata[FIELD_METADATA_KEY_STRAIN_MEASURE], "green_lagrange")
                self.assertEqual(field.metadata[FIELD_METADATA_KEY_KINEMATIC_REGIME], "finite_strain")
                self.assertEqual(
                    field.metadata[FIELD_METADATA_KEY_TANGENT_MEASURE],
                    "d_second_piola_kirchhoff_d_green_lagrange",
                )

            for field_name in (FIELD_KEY_S, FIELD_KEY_S_IP, FIELD_KEY_S_REC, FIELD_KEY_S_AVG):
                field = frame.get_field(field_name)
                self.assertEqual(field.metadata[FIELD_METADATA_KEY_STRESS_MEASURE], "second_piola_kirchhoff")
                self.assertEqual(field.metadata[FIELD_METADATA_KEY_KINEMATIC_REGIME], "finite_strain")
                self.assertEqual(
                    field.metadata[FIELD_METADATA_KEY_TANGENT_MEASURE],
                    "d_second_piola_kirchhoff_d_green_lagrange",
                )

    def test_cps4_plane_stress_j2_nlgeom_boundary_remains_explicit_fail_fast(self) -> None:
        model = build_cps4_j2_model(
            model_name="phase3-closeout-plane-stress-j2",
            nlgeom=True,
            right_displacement=0.004,
        )
        model.sections["sec-1"] = SectionDef(
            name="sec-1",
            section_type="plane_stress",
            material_name="mat-j2",
            region_name="plate-set",
            scope_name="part-1",
            parameters={"thickness": 1.0},
        )

        with self.assertRaises(CompilationError) as caught:
            Compiler().compile(model)

        message = str(caught.exception)
        self.assertIn("PlaneStrainSection + J2", message)
        self.assertIn("PlaneStressSection + J2", message)
        self.assertIn("暂不支持", message)

    def _build_extended_material_output_model(self, model):
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
        step = model.steps["step-static"]
        step.output_request_names = tuple(step.output_request_names) + ("field-centroid", "field-avg")
        return model

    def _run_single_step(self, model) -> InMemoryResultsWriter:
        compiled_model = Compiler().compile(model)
        writer = InMemoryResultsWriter()
        compiled_model.get_step_runtime("step-static").run(writer)
        return writer


if __name__ == "__main__":
    unittest.main()
