"""实例 / 作用域语义回归测试。"""

import unittest

from pyfem.compiler import Compiler
from pyfem.foundation import ModelValidationError
from pyfem.io import InMemoryResultsWriter
from pyfem.mesh import Assembly, ElementRecord, Mesh, NodeRecord, Part, PartInstance, RigidTransform
from pyfem.modeldb import BoundaryDef, JobDef, MaterialDef, ModelDB, NodalLoadDef, OutputRequest, SectionDef, StepDef


class ScopeSemanticsRegressionTests(unittest.TestCase):
    """固化双实例与 alias fail-fast 的架构回归。"""

    def test_static_linear_dual_instance_results_remain_scope_separated(self) -> None:
        model = self._build_dual_instance_model()
        writer = InMemoryResultsWriter()

        Compiler().compile(model).get_step_runtime("step-static").run(writer)
        displacement_field = writer.frames[0].get_field("U")

        self.assertEqual(
            tuple(displacement_field.values.keys()),
            ("left.n1", "left.n2", "right.n1", "right.n2"),
        )
        self.assertAlmostEqual(displacement_field.values["left.n2"]["UY"], 0.0, delta=1.0e-12)
        self.assertLess(displacement_field.values["right.n2"]["UY"], 0.0)

    def test_compile_fails_fast_for_part_name_scope_alias_under_assembly(self) -> None:
        model = self._build_dual_instance_model(boundary_scope_name="beam-part")

        with self.assertRaises(ModelValidationError):
            Compiler().compile(model)

    def _build_dual_instance_model(self, boundary_scope_name: str = "left") -> ModelDB:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(2.0, 0.0)))
        mesh.add_element(ElementRecord(name="beam-1", type_key="B21", node_names=("n1", "n2")))
        mesh.add_node_set("root", ("n1",))
        mesh.add_node_set("tip", ("n2",))
        mesh.add_element_set("beam-set", ("beam-1",))

        model = ModelDB(name="scope-regression")
        model.add_part(Part(name="beam-part", mesh=mesh))
        model.add_material(
            MaterialDef(
                name="mat-1",
                material_type="linear_elastic",
                parameters={"young_modulus": 1.0e6, "poisson_ratio": 0.3, "density": 4.0},
            )
        )
        model.add_section(
            SectionDef(
                name="sec-1",
                section_type="beam",
                material_name="mat-1",
                region_name="beam-set",
                parameters={"area": 0.03, "moment_inertia_z": 2.0e-4},
            )
        )

        assembly = Assembly(name="assembly-1")
        assembly.add_instance(PartInstance(name="left", part_name="beam-part"))
        assembly.add_instance(
            PartInstance(name="right", part_name="beam-part", transform=RigidTransform(translation=(5.0, 0.0)))
        )
        model.set_assembly(assembly)

        model.add_boundary(BoundaryDef(name="bc-left-root", target_name="root", scope_name=boundary_scope_name, dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0}))
        model.add_boundary(BoundaryDef(name="bc-right-root", target_name="root", scope_name="right", dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0}))
        model.add_nodal_load(NodalLoadDef(name="load-right-tip", target_name="tip", scope_name="right", components={"FY": -12.0}))
        model.add_output_request(OutputRequest(name="field-u", variables=("U",), target_type="model", position="NODE"))
        model.add_step(
            StepDef(
                name="step-static",
                procedure_type="static_linear",
                boundary_names=("bc-left-root", "bc-right-root"),
                nodal_load_names=("load-right-tip",),
                output_request_names=("field-u",),
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-static",)))
        return model


if __name__ == "__main__":
    unittest.main()
