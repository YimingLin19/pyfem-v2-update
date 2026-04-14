"""InpExporter round-trip 回归测试。"""

from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

from pyfem.compiler import Compiler
from pyfem.io import InMemoryResultsWriter, InpExporter, InpImporter
from pyfem.modeldb import RawKeywordBlockDef
from tests.support.model_builders import build_c3d8_pressure_block_model, build_dual_instance_beam_model
from tests.support.solid_finite_strain_j2_builders import build_cps4_j2_model


class InpExporterRoundtripRegressionTests(unittest.TestCase):
    """验证正式支持子集可以稳定回写并重新进入主线。"""

    def test_exporter_roundtrips_static_nonlinear_j2_output_and_raw_keyword_blocks(self) -> None:
        model = build_cps4_j2_model(
            model_name="exporter-roundtrip-j2",
            nlgeom=True,
            right_displacement=0.004,
            include_material_fields=True,
        )
        model.add_raw_keyword_block(
            RawKeywordBlockDef(
                name="raw-before-steps",
                keyword="CONTACT PAIR",
                placement="before_steps",
                data_lines=("master, slave",),
                order=1,
                description="受控 raw block 回写测试",
            )
        )

        exported_text = InpExporter().export_text(model).text
        self.assertIn("*Static Nonlinear", exported_text)
        self.assertIn("nlgeom=true", exported_text)
        self.assertIn("*Plastic, model=J2", exported_text)
        self.assertIn("*Output Request", exported_text)
        self.assertIn("*Raw Keyword", exported_text)

        imported_model = InpImporter().import_text(exported_text, model_name="roundtrip-j2", source_name="roundtrip-j2.inp")
        self.assertEqual(imported_model.steps["step-static"].procedure_type, "static_nonlinear")
        self.assertTrue(bool(imported_model.steps["step-static"].parameters["nlgeom"]))
        self.assertEqual(imported_model.materials["mat-j2"].material_type, "j2_plasticity")
        self.assertEqual(imported_model.materials["mat-j2"].parameters["yield_stress"], 250.0)
        self.assertIn("field-node", imported_model.output_requests)
        self.assertEqual(imported_model.raw_keyword_blocks["raw-before-steps"].placement, "before_steps")

        compiled_model = Compiler().compile(imported_model)
        writer = InMemoryResultsWriter()
        compiled_model.get_step_runtime("step-static").run(writer)
        summary = writer.read_summary("step-static", "static_nonlinear_summary").data
        self.assertTrue(bool(summary["nlgeom"]))

    def test_exporter_preserves_instance_transform_and_named_step_references(self) -> None:
        model = build_dual_instance_beam_model(boundary_scope_name="left")
        exported_text = InpExporter().export_text(model).text
        imported_model = InpImporter().import_text(exported_text, model_name="roundtrip-assembly", source_name="roundtrip-assembly.inp")

        self.assertIsNotNone(imported_model.assembly)
        self.assertEqual(tuple(imported_model.assembly.instances.keys()), ("left", "right"))
        self.assertEqual(imported_model.assembly.instances["right"].transform.translation, (5.0, 0.0))
        self.assertEqual(imported_model.steps["step-static"].boundary_names, ("bc-left-root", "bc-right-root"))
        self.assertEqual(imported_model.steps["step-static"].nodal_load_names, ("load-right-tip",))

    def test_exporter_preserves_surface_facets_for_c3d8_pressure_model(self) -> None:
        model = build_c3d8_pressure_block_model()
        exported_text = InpExporter().export_text(model).text

        self.assertIn("*Surface, type=ELEMENT, name=PRESSURE_FACE", exported_text)
        self.assertIn("block-1, S1", exported_text)

        imported_model = InpImporter().import_text(exported_text, model_name="roundtrip-pressure", source_name="roundtrip-pressure.inp")
        surface = imported_model.parts["block-part"].mesh.surfaces["PRESSURE_FACE"]
        self.assertEqual(tuple((facet.element_name, facet.local_face) for facet in surface.facets), (("block-1", "S1"),))

        compiled_model = Compiler().compile(imported_model)
        writer = InMemoryResultsWriter()
        compiled_model.get_step_runtime("step-static").run(writer)
        frame = writer.read_step("step-static").frames[-1]
        self.assertIsNotNone(frame.get_field("U"))

    def test_exporter_roundtrips_assembly_instance_alias_sets_and_surfaces(self) -> None:
        imported_model = InpImporter().import_text(
            """
*Part, name=BLOCK
*Node
1, 1.0, 0.0, 1.0
2, 1.0, 1.0, 1.0
3, 1.0, 1.0, 0.0
4, 1.0, 0.0, 0.0
5, 0.0, 0.0, 1.0
6, 0.0, 1.0, 1.0
7, 0.0, 1.0, 0.0
8, 0.0, 0.0, 0.0
*Element, type=C3D8, elset=BLOCK_SET
1, 1, 2, 3, 4, 5, 6, 7, 8
*Solid Section, elset=BLOCK_SET, material=MAT
,
*End Part
*Material, name=MAT
*Elastic
1000.0, 0.3
*Assembly, name=ASM
*Instance, name=Part-1-1, part=BLOCK
*End Instance
*Nset, nset=_PickedSet7, instance=Part-1-1, generate
1, 8, 1
*Elset, elset=_Surf-1_S1, instance=Part-1-1
1
*Surface, type=ELEMENT, name=Surf-1
_Surf-1_S1, S1
*End Assembly
*Boundary
_PickedSet7, 1, 3, 0.0
*Step, name=STEP-1
*Static
*Dsload
Surf-1, P, -2.0
*End Step
""",
            model_name="assembly-alias-roundtrip",
            source_name="assembly-alias-roundtrip.inp",
        )

        exported_text = InpExporter().export_text(imported_model).text
        self.assertIn("*Nset, nset=_PickedSet7, instance=Part-1-1", exported_text)
        self.assertIn("*Elset, elset=_Surf-1_S1, instance=Part-1-1", exported_text)
        self.assertIn("*Surface, type=ELEMENT, name=Surf-1", exported_text)
        self.assertIn("Part-1-1.1, S1", exported_text)

        roundtrip_model = InpImporter().import_text(exported_text, model_name="assembly-alias-reimport", source_name="assembly-alias-reimport.inp")
        scope = roundtrip_model.resolve_compilation_scope("Part-1-1")

        self.assertIsNotNone(scope)
        self.assertEqual(roundtrip_model.boundaries["global-bc-1"].scope_name, "Part-1-1")
        self.assertEqual(roundtrip_model.distributed_loads["STEP-1-dload-1"].scope_name, "Part-1-1")
        self.assertEqual(scope.resolve_node_names("node_set", "_PickedSet7"), tuple(str(index) for index in range(1, 9)))
        self.assertIsNotNone(scope.get_surface("Surf-1"))


if __name__ == "__main__":
    unittest.main()
