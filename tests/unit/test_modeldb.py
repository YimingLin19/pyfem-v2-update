"""模型定义层基础测试。"""

import unittest

from pyfem.foundation.errors import ModelValidationError
from pyfem.mesh import Assembly, ElementRecord, Mesh, NodeRecord, Orientation, Part, PartInstance, Surface, SurfaceFacet
from pyfem.modeldb import (
    BoundaryDef,
    JobDef,
    MaterialDef,
    Metadata,
    ModelDB,
    NodalLoadDef,
    OutputRequest,
    SectionDef,
    StepDef,
)


class ModelDBTests(unittest.TestCase):
    """验证模型定义层的基本行为。"""

    def test_modeldb_validate_and_serialize(self) -> None:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(1.0, 0.0)))
        mesh.add_node(NodeRecord(name="n3", coordinates=(1.0, 1.0)))
        mesh.add_node(NodeRecord(name="n4", coordinates=(0.0, 1.0)))
        mesh.add_orientation(Orientation(name="ori-1"))
        mesh.add_element(
            ElementRecord(
                name="element-1",
                type_key="CPS4",
                node_names=("n1", "n2", "n3", "n4"),
                orientation_name="ori-1",
            )
        )
        mesh.add_node_set("fixed", ("n1", "n4"))
        mesh.add_node_set("loaded", ("n2", "n3"))
        mesh.add_element_set("plate", ("element-1",))
        mesh.add_surface(Surface(name="top", facets=(SurfaceFacet(element_name="element-1", local_face="S3"),)))

        part = Part(name="part-1", mesh=mesh)

        model = ModelDB(
            name="demo",
            metadata=Metadata(description="任务二模型定义测试", tags=("task02", "modeldb")),
        )
        model.add_part(part)
        model.add_material(MaterialDef(name="mat-1", material_type="linear_elastic"))
        model.add_section(
            SectionDef(
                name="sec-1",
                section_type="plane_stress",
                material_name="mat-1",
                region_name="plate",
                scope_name="part-1",
            )
        )
        model.add_boundary(BoundaryDef(name="bc-1", target_name="fixed", dof_values={"UX": 0.0, "UY": 0.0}))
        model.add_nodal_load(NodalLoadDef(name="load-1", target_name="loaded", components={"FY": -10.0}))
        model.add_output_request(OutputRequest(name="field-u", variables=("U",), target_type="model"))
        model.add_step(
            StepDef(
                name="step-1",
                procedure_type="static",
                boundary_names=("bc-1",),
                nodal_load_names=("load-1",),
                output_request_names=("field-u",),
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-1",)))

        model.validate()
        payload = model.to_dict()

        self.assertEqual(payload["metadata"]["version"], "2.0")
        self.assertEqual(payload["parts"]["part-1"]["mesh"]["elements"]["element-1"]["type_key"], "CPS4")
        self.assertEqual(payload["parts"]["part-1"]["mesh"]["element_sets"]["plate"], ["element-1"])
        self.assertEqual(payload["steps"]["step-1"]["boundary_names"], ["bc-1"])
        self.assertEqual(payload["job"]["step_names"], ["step-1"])

    def test_modeldb_duplicate_step_name_fails_fast(self) -> None:
        model = ModelDB(name="duplicate-step")
        model.add_step(StepDef(name="step-1", procedure_type="static_linear"))

        with self.assertRaises(ModelValidationError):
            model.add_step(StepDef(name="step-1", procedure_type="modal"))

    def test_modeldb_validates_and_serializes_instance_level_assembly_aliases(self) -> None:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(1.0, 0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n3", coordinates=(1.0, 1.0, 0.0)))
        mesh.add_node(NodeRecord(name="n4", coordinates=(0.0, 1.0, 0.0)))
        mesh.add_node(NodeRecord(name="n5", coordinates=(0.0, 0.0, 1.0)))
        mesh.add_node(NodeRecord(name="n6", coordinates=(1.0, 0.0, 1.0)))
        mesh.add_node(NodeRecord(name="n7", coordinates=(1.0, 1.0, 1.0)))
        mesh.add_node(NodeRecord(name="n8", coordinates=(0.0, 1.0, 1.0)))
        mesh.add_element(
            ElementRecord(
                name="e1",
                type_key="C3D8",
                node_names=("n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8"),
            )
        )
        mesh.add_element_set("block", ("e1",))
        part = Part(name="part-1", mesh=mesh)

        assembly = Assembly(name="asm-1")
        assembly.add_instance(PartInstance(name="left", part_name="part-1"))
        assembly.add_instance_node_set("left", "fixed_alias", ("n1", "n4", "n5", "n8"))
        assembly.add_instance_element_set("left", "surface_region", ("e1",))
        assembly.add_instance_surface(
            "left",
            Surface(name="pressure_alias", facets=(SurfaceFacet(element_name="e1", local_face="S3"),)),
        )

        model = ModelDB(name="assembly-alias-model")
        model.add_part(part)
        model.set_assembly(assembly)
        model.add_material(MaterialDef(name="mat-1", material_type="linear_elastic"))
        model.add_section(
            SectionDef(
                name="sec-1",
                section_type="solid",
                material_name="mat-1",
                region_name="block",
                scope_name="left",
            )
        )
        model.add_boundary(BoundaryDef(name="bc-1", target_name="fixed_alias", scope_name="left", dof_values={"UX": 0.0}))

        model.validate()
        scope = model.resolve_compilation_scope("left")
        payload = model.to_dict()

        self.assertIsNotNone(scope)
        self.assertEqual(scope.resolve_node_names("node_set", "fixed_alias"), ("n1", "n4", "n5", "n8"))
        self.assertIsNotNone(scope.get_surface("pressure_alias"))
        self.assertEqual(payload["assembly"]["instance_node_sets"]["left"]["fixed_alias"], ["n1", "n4", "n5", "n8"])
        self.assertEqual(payload["assembly"]["instance_surfaces"]["left"]["pressure_alias"]["facets"][0]["element_name"], "e1")


if __name__ == "__main__":
    unittest.main()
