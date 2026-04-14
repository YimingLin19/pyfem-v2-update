"""分布载荷主线集成测试。"""

import unittest

from pyfem.compiler import Compiler
from pyfem.io import InMemoryResultsWriter, InpImporter


class DistributedLoadPipelineTests(unittest.TestCase):
    """验证 *Dsload 经过 importer 到 solver 的最小主线。"""

    def test_dsload_surface_pressure_is_assembled_and_affects_static_solution(self) -> None:
        model = InpImporter().import_text(
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
            model_name="dsload-pipeline",
            source_name="dsload_pipeline.inp",
        )
        compiled_model = Compiler().compile(model)
        step_runtime = compiled_model.get_step_runtime("STEP-1")

        trial_state = step_runtime.problem.begin_trial()
        external_load = step_runtime.problem.assemble_external_load(step_runtime.definition, time=0.0, state=trial_state)

        x_components = external_load[0::3]
        y_components = external_load[1::3]
        z_components = external_load[2::3]
        self.assertAlmostEqual(float(sum(x_components)), 2.0, places=10)
        self.assertAlmostEqual(float(sum(y_components)), 0.0, places=10)
        self.assertAlmostEqual(float(sum(z_components)), 0.0, places=10)

        writer = InMemoryResultsWriter()
        report = step_runtime.run(writer)
        displacement_field = writer.frames[0].get_field("U")

        self.assertEqual(report.frame_count, 1)
        self.assertGreater(displacement_field.values["part-1.1"]["UX"], 0.0)
        self.assertGreater(displacement_field.values["part-1.2"]["UX"], 0.0)
        self.assertGreater(displacement_field.values["part-1.3"]["UX"], 0.0)
        self.assertGreater(displacement_field.values["part-1.4"]["UX"], 0.0)


if __name__ == "__main__":
    unittest.main()
