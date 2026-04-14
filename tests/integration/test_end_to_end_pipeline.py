"""端到端 IO 主线测试。"""

from pathlib import Path
import unittest
from uuid import uuid4

from pyfem.compiler import Compiler
from pyfem.io import (
    FIELD_KEY_RF,
    FIELD_KEY_S_AVG,
    FIELD_KEY_S_IP,
    FIELD_KEY_S_PRINCIPAL_IP,
    FIELD_KEY_S_REC,
    FIELD_KEY_S_VM_IP,
    FIELD_KEY_U,
    FIELD_KEY_U_MAG,
    InpImporter,
    JsonResultsReader,
    JsonResultsWriter,
    VtkExporter,
)


class EndToEndPipelineTests(unittest.TestCase):
    """验证 INP 到结果读回与 VTK 导出的最小链路。"""

    def test_inp_to_resultsdb_and_vtk_pipeline(self) -> None:
        importer = InpImporter()
        model = importer.import_text(
            text="""
*Heading
Task 05 end to end example
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
            model_name="e2e-beam",
            source_name="beam_e2e.inp",
        )
        compiled_model = Compiler().compile(model)

        results_path = Path("tests") / f"_tmp_results_{uuid4().hex}.json"
        vtk_path = Path("tests") / f"_tmp_results_{uuid4().hex}.vtk"
        try:
            compiled_model.get_step_runtime("LOAD_STEP").run(JsonResultsWriter(results_path))
            reader = JsonResultsReader(results_path)
            VtkExporter().export(model=model, results_reader=reader, path=vtk_path, step_name="LOAD_STEP")

            session = reader.read_session()
            frame = reader.find_frame("LOAD_STEP", 0)
            displacement_field = frame.get_field(FIELD_KEY_U)
            reaction_field = frame.get_field(FIELD_KEY_RF)
            tip_displacement = displacement_field.values["part-1.2"]["UY"]
            root_reaction = reaction_field.values["part-1.1"]["UY"]
            vtk_content = vtk_path.read_text(encoding="utf-8")

            self.assertEqual(session.model_name, "e2e-beam")
            self.assertEqual(session.step_name, "LOAD_STEP")
            self.assertAlmostEqual(tip_displacement, -0.16, places=12)
            self.assertAlmostEqual(root_reaction, 12.0, places=12)
            field_names = tuple(field.name for field in frame.fields)
            self.assertIn(FIELD_KEY_U_MAG, field_names)
            self.assertIn(FIELD_KEY_S_IP, field_names)
            self.assertIn(FIELD_KEY_S_REC, field_names)
            self.assertIn(FIELD_KEY_S_AVG, field_names)
            self.assertIn(FIELD_KEY_S_VM_IP, field_names)
            self.assertIn(FIELD_KEY_S_PRINCIPAL_IP, field_names)
            self.assertIn("VECTORS RAW__U float", vtk_content)
        finally:
            results_path.unlink(missing_ok=True)
            vtk_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
