"""INP importer 基础测试。"""

import unittest

from pyfem.foundation import ModelValidationError
from pyfem.io import InpImporter


class InpImporterTests(unittest.TestCase):
    """验证 INP importer 与 translator 的基础行为。"""

    def test_importer_builds_beam_modeldb_from_inp_text(self) -> None:
        importer = InpImporter()
        model = importer.import_text(
            text="""
*Heading
Task 05 beam example
*Node
1, 0.0, 0.0
2, 2.0, 0.0
*Element, type=B21, elset=BEAM_SET
1, 1, 2
*Nset, nset=ROOT
1
*Nset, nset=TIP
2
*Material, name=STEEL
*Elastic
1000000.0, 0.3
*Density
4.0
*Beam Section, elset=BEAM_SET, material=STEEL
0.03, 0.0002
*Step, name=LOAD_STEP
*Static
*Boundary
ROOT, 1, 2, 0.0
ROOT, 6, 6, 0.0
*Cload
TIP, 2, -12.0
*End Step
""",
            model_name="imported-beam",
            source_name="beam.inp",
        )

        self.assertEqual(model.name, "imported-beam")
        self.assertEqual(model.metadata.description, "Task 05 beam example")
        self.assertIn("part-1", model.parts)
        self.assertIn("STEEL", model.materials)
        self.assertEqual(model.materials["STEEL"].parameters["young_modulus"], 1000000.0)
        self.assertEqual(model.sections["section-BEAM_SET"].section_type, "beam")
        self.assertEqual(model.steps["LOAD_STEP"].procedure_type, "static_linear")
        self.assertEqual(model.job.step_names, ("LOAD_STEP",))
        self.assertEqual(
            model.steps["LOAD_STEP"].output_request_names,
            ("output-1", "output-2", "output-3", "output-4", "output-5", "output-6"),
        )
        self.assertEqual(model.output_requests["output-1"].variables, ("U", "RF", "U_MAG"))
        self.assertEqual(model.output_requests["output-1"].position, "NODE")
        self.assertEqual(model.output_requests["output-2"].variables, ("S", "E", "SECTION"))
        self.assertEqual(model.output_requests["output-2"].position, "ELEMENT_CENTROID")
        self.assertEqual(model.output_requests["output-3"].variables, ("S_IP", "E_IP", "S_VM_IP", "S_PRINCIPAL_IP"))
        self.assertEqual(model.output_requests["output-3"].position, "INTEGRATION_POINT")
        self.assertEqual(model.output_requests["output-4"].variables, ("S_REC", "E_REC", "S_VM_REC", "S_PRINCIPAL_REC"))
        self.assertEqual(model.output_requests["output-4"].position, "ELEMENT_NODAL")
        self.assertEqual(model.output_requests["output-5"].variables, ("S_AVG", "S_VM_AVG", "S_PRINCIPAL_AVG"))
        self.assertEqual(model.output_requests["output-5"].position, "NODE_AVERAGED")
        self.assertEqual(model.output_requests["output-6"].variables, ("TIME",))
        self.assertEqual(model.output_requests["output-6"].position, "GLOBAL_HISTORY")

    def test_importer_ignores_preprint_control_keyword(self) -> None:
        importer = InpImporter()
        model = importer.import_text(
            text="""
*Heading
pyFEM exported model: preprint-beam
*Preprint, echo=NO, model=NO, history=NO, contact=NO
*Node
1, 0.0, 0.0
2, 1.0, 0.0
*Element, type=B21, elset=BEAM_SET
1, 1, 2
*Nset, nset=ROOT
1
*Nset, nset=TIP
2
*Material, name=STEEL
*Elastic
1000.0, 0.3
*Beam Section, elset=BEAM_SET, material=STEEL
0.03, 0.0002
*Step, name=STEP-1
*Static
*Boundary
ROOT, 1, 2, 0.0
ROOT, 6, 6, 0.0
*Cload
TIP, 2, -1.0
*End Step
""",
            source_name="preprint.inp",
        )

        self.assertEqual(model.name, "preprint-beam")
        self.assertIn("part-1", model.parts)
        self.assertIn("STEP-1", model.steps)
        self.assertEqual(model.steps["STEP-1"].procedure_type, "static_linear")

    def test_importer_accepts_empty_system_control_keyword(self) -> None:
        importer = InpImporter()
        model = importer.import_text(
            text="""
*Heading
pyFEM exported model: system-beam
*Node
1, 0.0, 0.0
2, 1.0, 0.0
*Element, type=B21, elset=BEAM_SET
1, 1, 2
*System
*Nset, nset=ROOT
1
*Nset, nset=TIP
2
*Material, name=STEEL
*Elastic
1000.0, 0.3
*Beam Section, elset=BEAM_SET, material=STEEL
0.03, 0.0002
*Step, name=STEP-1
*Static
*Boundary
ROOT, 1, 2, 0.0
ROOT, 6, 6, 0.0
*Cload
TIP, 2, -1.0
*End Step
""",
            source_name="system.inp",
        )

        self.assertEqual(model.name, "system-beam")
        self.assertIn("part-1", model.parts)
        self.assertEqual(model.parts["part-1"].nodes["1"].coordinates, (0.0, 0.0))

    def test_importer_rejects_system_with_coordinate_definition(self) -> None:
        importer = InpImporter()
        with self.assertRaisesRegex(ModelValidationError, "SYSTEM"):
            importer.import_text(
                text="""
*Heading
system-transform
*System
0.0, 0.0, 0.0, 1.0, 0.0, 0.0
*Node
1, 0.0, 0.0
""",
                source_name="system-transform.inp",
            )

    def test_importer_accepts_restart_and_output_preselect_controls(self) -> None:
        importer = InpImporter()
        model = importer.import_text(
            text="""
*Heading
output-controls
*Node
1, 0.0, 0.0
2, 1.0, 0.0
*Element, type=B21, elset=BEAM_SET
1, 1, 2
*Nset, nset=ROOT
1
*Nset, nset=TIP
2
*Material, name=STEEL
*Elastic
1000.0, 0.3
*Beam Section, elset=BEAM_SET, material=STEEL
0.03, 0.0002
*Step, name=STEP-1
*Static
*Boundary
ROOT, 1, 2, 0.0
ROOT, 6, 6, 0.0
*Cload
TIP, 2, -1.0
*Restart, write, frequency=0
*Output, field, variable=PRESELECT
*Output, history, variable=PRESELECT
*End Step
""",
            source_name="output-controls.inp",
        )

        self.assertEqual(model.steps["STEP-1"].procedure_type, "static_linear")
        self.assertEqual(
            model.steps["STEP-1"].output_request_names,
            ("output-1", "output-2", "output-3", "output-4", "output-5", "output-6"),
        )

    def test_importer_builds_surface_and_dsload_from_inp_text(self) -> None:
        importer = InpImporter()
        model = importer.import_text(
            text="""
*Heading
Task 06 dsload example
*Node
1, 1.0, 0.0, 1.0
2, 1.0, 1.0, 1.0
3, 1.0, 1.0, 0.0
4, 1.0, 0.0, 0.0
5, 0.0, 0.0, 1.0
6, 0.0, 1.0, 1.0
7, 0.0, 1.0, 0.0
8, 0.0, 0.0, 0.0
*Element, type=C3D8, elset=BLOCK
1, 1, 2, 3, 4, 5, 6, 7, 8
*Nset, nset=FIXED
5, 6, 7, 8
*Elset, elset=PRESSURE_SET
1
*Solid Section, elset=BLOCK, material=MAT
,
*Surface, type=ELEMENT, name=PRESSURE_FACE
PRESSURE_SET, S1
*Material, name=MAT
*Elastic
1000.0, 0.3
*Step, name=STEP-1
*Static
*Boundary
FIXED, 1, 3, 0.0
*Dsload
PRESSURE_FACE, P, -2.0
*End Step
""",
            model_name="imported-dsload",
            source_name="dsload.inp",
        )

        self.assertIn("PRESSURE_FACE", model.parts["part-1"].mesh.surfaces)
        surface = model.parts["part-1"].mesh.surfaces["PRESSURE_FACE"]
        self.assertEqual(tuple((facet.element_name, facet.local_face) for facet in surface.facets), (("1", "S1"),))
        self.assertEqual(model.steps["STEP-1"].distributed_load_names, ("STEP-1-dload-1",))
        self.assertEqual(model.distributed_loads["STEP-1-dload-1"].target_name, "PRESSURE_FACE")
        self.assertEqual(model.distributed_loads["STEP-1-dload-1"].load_type, "pressure")
        self.assertEqual(model.distributed_loads["STEP-1-dload-1"].components, {"P": -2.0})

    def test_importer_builds_part_instance_transform_without_flatten_copy(self) -> None:
        importer = InpImporter()
        model = importer.import_text(
            text="""
*Part, name=BEAM
*Node
1, 0.0, 0.0
2, 2.0, 0.0
*Element, type=B21, elset=BEAM_SET
1, 1, 2
*Nset, nset=ROOT
1
*Nset, nset=TIP
2
*Beam Section, elset=BEAM_SET, material=STEEL
0.03, 0.0002
*End Part
*Material, name=STEEL
*Elastic
1000000.0, 0.3
*Assembly, name=ASM
*Instance, name=left, part=BEAM
*End Instance
*Instance, name=right, part=BEAM
0.0, -1.0
1.0, 0.0
5.0, 0.0
*End Instance
*End Assembly
""",
            model_name="assembly-import",
            source_name="assembly.inp",
        )

        self.assertEqual(tuple(model.parts.keys()), ("BEAM",))
        self.assertIsNotNone(model.assembly)
        self.assertEqual(tuple(model.assembly.instances.keys()), ("left", "right"))
        self.assertEqual(tuple(model.parts["BEAM"].mesh.node_sets.keys()), ("ROOT", "TIP"))
        self.assertEqual(model.parts["BEAM"].nodes["1"].coordinates, (0.0, 0.0))
        self.assertEqual(model.parts["BEAM"].nodes["2"].coordinates, (2.0, 0.0))
        self.assertEqual(model.assembly.instances["left"].transform.translation, ())
        self.assertEqual(model.assembly.instances["right"].transform.rotation, ((0.0, -1.0), (1.0, 0.0)))
        self.assertEqual(model.assembly.instances["right"].transform.translation, (5.0, 0.0))

    def test_importer_imports_orientation_and_model_validate_passes(self) -> None:
        importer = InpImporter()
        model = importer.import_text(
            text="""
*Part, name=PLATE
*Node
1, 0.0, 0.0
2, 1.0, 0.0
3, 1.0, 1.0
4, 0.0, 1.0
*Element, type=CPS4, elset=PLATE_SET, orientation=ORI-1
1, 1, 2, 3, 4
*Orientation, name=ORI-1
1.0, 0.0, 0.0, 1.0
*Solid Section, elset=PLATE_SET, material=STEEL
1.0
*End Part
*Material, name=STEEL
*Elastic
1000.0, 0.3
""",
            model_name="orientation-import",
            source_name="orientation.inp",
        )

        part = model.parts["PLATE"]
        self.assertIn("ORI-1", part.mesh.orientations)
        self.assertEqual(part.mesh.orientations["ORI-1"].axis_1, (1.0, 0.0))
        self.assertEqual(part.mesh.orientations["ORI-1"].axis_2, (0.0, 1.0))
        self.assertEqual(part.elements["1"].orientation_name, "ORI-1")
        model.validate()

    def test_importer_resolves_instance_scoped_set_and_surface_targets(self) -> None:
        importer = InpImporter()
        model = importer.import_text(
            text="""
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
*Nset, nset=FIXED
5, 6, 7, 8
*Elset, elset=PRESSURE_SET
1
*Surface, type=ELEMENT, name=PRESSURE_FACE
PRESSURE_SET, S1
*Solid Section, elset=BLOCK_SET, material=MAT
,
*End Part
*Material, name=MAT
*Elastic
1000.0, 0.3
*Assembly, name=ASM
*Instance, name=left, part=BLOCK
*End Instance
*Instance, name=right, part=BLOCK
1.0, 0.0, 0.0
*End Instance
*End Assembly
*Step, name=STEP-1
*Static
*Boundary
left.FIXED, 1, 3, 0.0
*Dsload
right.PRESSURE_FACE, P, -2.0
*End Step
""",
            model_name="scoped-targets",
            source_name="scoped-targets.inp",
        )

        boundary = model.boundaries["STEP-1-bc-1"]
        distributed_load = model.distributed_loads["STEP-1-dload-1"]
        self.assertEqual(boundary.scope_name, "left")
        self.assertEqual(boundary.target_name, "FIXED")
        self.assertEqual(distributed_load.scope_name, "right")
        self.assertEqual(distributed_load.target_name, "PRESSURE_FACE")
        self.assertIn("PRESSURE_FACE", model.parts["BLOCK"].mesh.surfaces)

    def test_importer_accepts_assembly_alias_sets_and_surfaces_for_unique_instance(self) -> None:
        importer = InpImporter()
        model = importer.import_text(
            text="""
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
*Step, name=STEP-1
*Static
*Boundary
_PickedSet7, 1, 3, 0.0
*Dsload
Surf-1, P, -2.0
*End Step
""",
            model_name="assembly-alias-import",
            source_name="assembly-alias.inp",
        )

        boundary = model.boundaries["STEP-1-bc-1"]
        distributed_load = model.distributed_loads["STEP-1-dload-1"]
        scope = model.resolve_compilation_scope("Part-1-1")

        self.assertIsNotNone(scope)
        self.assertEqual(boundary.scope_name, "Part-1-1")
        self.assertEqual(boundary.target_name, "_PickedSet7")
        self.assertEqual(boundary.target_type, "node_set")
        self.assertEqual(distributed_load.scope_name, "Part-1-1")
        self.assertEqual(distributed_load.target_name, "Surf-1")
        self.assertEqual(scope.resolve_node_names("node_set", "_PickedSet7"), tuple(str(index) for index in range(1, 9)))
        self.assertIsNotNone(scope.get_surface("Surf-1"))

    def test_importer_rejects_part_name_alias_under_assembly(self) -> None:
        importer = InpImporter()

        with self.assertRaises(ModelValidationError):
            importer.import_text(
                text="""
*Part, name=BEAM
*Node
1, 0.0, 0.0
2, 2.0, 0.0
*Element, type=B21, elset=BEAM_SET
1, 1, 2
*Nset, nset=ROOT
1
*Beam Section, elset=BEAM_SET, material=STEEL
0.03, 0.0002
*End Part
*Material, name=STEEL
*Elastic
1000000.0, 0.3
*Assembly, name=ASM
*Instance, name=left, part=BEAM
*End Instance
*End Assembly
*Step, name=STEP-1
*Static
*Boundary
BEAM.ROOT, 1, 2, 0.0
*End Step
""",
                model_name="alias-fail-fast",
                source_name="alias.inp",
            )


if __name__ == "__main__":
    unittest.main()
