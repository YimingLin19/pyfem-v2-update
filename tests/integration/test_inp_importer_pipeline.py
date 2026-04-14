"""INP importer 与编译主线集成测试。"""

from pathlib import Path
import unittest
from uuid import uuid4

from pyfem.compiler import Compiler
from pyfem.io import InMemoryResultsWriter, InpImporter, VtkExporter


class InpImporterPipelineTests(unittest.TestCase):
    """验证 importer 生成的装配模型能进入 compile / results / vtk 主线。"""

    def test_imported_dual_instance_model_compiles_and_exports_transformed_vtk_geometry(self) -> None:
        model = InpImporter().import_text(
            text="""
*Heading
Imported dual instance beam
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
*Density
4.0
*Assembly, name=ASM
*Instance, name=left, part=BEAM
*End Instance
*Instance, name=right, part=BEAM
5.0, 0.0
*End Instance
*End Assembly
*Step, name=LOAD_STEP
*Static
*Boundary
left.ROOT, 1, 2, 0.0
left.ROOT, 6, 6, 0.0
right.ROOT, 1, 2, 0.0
right.ROOT, 6, 6, 0.0
*Cload
right.TIP, 2, -12.0
*End Step
""",
            model_name="imported-dual-instance",
            source_name="dual-instance.inp",
        )

        compiled_model = Compiler().compile(model)
        writer = InMemoryResultsWriter()
        compiled_model.get_step_runtime("LOAD_STEP").run(writer)

        self.assertEqual(tuple(model.parts.keys()), ("BEAM",))
        self.assertEqual(tuple(model.assembly.instances.keys()), ("left", "right"))
        self.assertEqual(compiled_model.get_element_runtime("left.1").coordinates, ((0.0, 0.0), (2.0, 0.0)))
        self.assertEqual(compiled_model.get_element_runtime("right.1").coordinates, ((5.0, 0.0), (7.0, 0.0)))

        target_path = Path("tests") / f"_tmp_inp_vtk_{uuid4().hex}.vtk"
        try:
            VtkExporter().export(model=model, results_reader=writer, path=target_path)
            content = target_path.read_text(encoding="utf-8")
            self.assertIn("POINTS 4 float", content)
            self.assertIn("0 0 0", content)
            self.assertIn("2 0 0", content)
            self.assertIn("5 0 0", content)
            self.assertIn("7 0 0", content)
        finally:
            target_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
