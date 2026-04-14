"""CompilationScope 与实例变换单元测试。"""

import unittest

from pyfem.foundation import ModelValidationError
from pyfem.mesh import Assembly, ElementRecord, Mesh, NodeRecord, Orientation, Part, PartInstance, RigidTransform
from pyfem.modeldb import ModelDB


class CompilationScopeTests(unittest.TestCase):
    """验证 canonical scope、实例变换与 fail-fast 语义。"""

    def test_assembly_instances_define_canonical_scopes_and_transformed_geometry(self) -> None:
        model = self._build_rotated_assembly_model()

        model.validate()
        scopes = model.iter_compilation_scopes()
        right_scope = model.resolve_compilation_scope("right")

        self.assertEqual(tuple(scope.scope_name for scope in scopes), ("left", "right"))
        self.assertIsNone(model.resolve_compilation_scope("beam-part"))
        self.assertEqual(model.iter_target_scopes("beam-part"), ())
        self.assertIsNotNone(right_scope)
        self.assertEqual(right_scope.get_node_geometry_record("n1").coordinates, (3.0, 0.0))
        self.assertEqual(right_scope.get_node_geometry_record("n2").coordinates, (3.0, 2.0))

        orientation = right_scope.get_orientation("ori-1")
        self.assertIsNotNone(orientation)
        self.assertEqual(orientation.axis_1, (0.0, 1.0))
        self.assertEqual(orientation.axis_2, (-1.0, 0.0))

    def test_validate_rejects_non_right_handed_instance_rotation(self) -> None:
        model = self._build_rotated_assembly_model(
            transform=RigidTransform(rotation=((1.0, 0.0), (0.0, -1.0)), translation=(3.0, 0.0))
        )

        with self.assertRaisesRegex(ModelValidationError, "右手系"):
            model.validate()

    def _build_rotated_assembly_model(self, transform: RigidTransform | None = None) -> ModelDB:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(2.0, 0.0)))
        mesh.add_element(ElementRecord(name="beam-1", type_key="B21", node_names=("n1", "n2"), orientation_name="ori-1"))
        mesh.add_node_set("root", ("n1",))
        mesh.add_node_set("tip", ("n2",))
        mesh.add_element_set("beam-set", ("beam-1",))
        mesh.add_orientation(Orientation(name="ori-1", axis_1=(1.0, 0.0), axis_2=(0.0, 1.0)))

        model = ModelDB(name="scope-model")
        model.add_part(Part(name="beam-part", mesh=mesh))

        assembly = Assembly(name="assembly-1")
        assembly.add_instance(PartInstance(name="left", part_name="beam-part"))
        assembly.add_instance(
            PartInstance(
                name="right",
                part_name="beam-part",
                transform=transform
                if transform is not None
                else RigidTransform(rotation=((0.0, -1.0), (1.0, 0.0)), translation=(3.0, 0.0)),
            )
        )
        model.set_assembly(assembly)
        return model


if __name__ == "__main__":
    unittest.main()
