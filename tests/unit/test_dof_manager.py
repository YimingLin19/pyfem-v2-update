"""自由度管理器基础测试。"""

import unittest

from pyfem.compiler import RuntimeRegistry
from pyfem.foundation import CompilationError, DofLocation, NodeLocation
from pyfem.kernel import DofManager


class DofManagerTests(unittest.TestCase):
    """验证自由度管理器和默认自由度布局。"""

    def test_dof_manager_registers_node_and_auxiliary_owners(self) -> None:
        manager = DofManager()
        node_a = NodeLocation(scope_name="scope-a", node_name="n1")

        self.assertEqual(manager.register_node_dofs(node_a, ("UX", "UY")), (0, 1))
        self.assertEqual(manager.register_extra_dofs("scope-a", "constraint-1", ("LM",)), (2,))
        self.assertEqual(manager.get_global_id(DofLocation("scope-a", "n1", "UX")), 0)
        self.assertEqual(manager.get_node_dof_ids(node_a), (0, 1))
        self.assertEqual(
            manager.get_owner_dof_ids(
                scope_name="scope-a",
                owner_kind="auxiliary",
                owner_name="constraint-1",
            ),
            (2,),
        )

        descriptors = manager.iter_descriptors()
        self.assertEqual(descriptors[2].location.owner_kind, "auxiliary")
        self.assertEqual(descriptors[2].location.owner_name, "constraint-1")
        self.assertEqual(descriptors[2].location.node_name, None)
        self.assertEqual(descriptors[2].location.qualified_name, "scope-a.auxiliary:constraint-1.LM")
        self.assertEqual(descriptors[2].location.get_result_key(), None)

        manager.finalize()

        self.assertEqual(manager.num_dofs(), 3)
        with self.assertRaises(CompilationError):
            manager.register_node_dofs(NodeLocation(scope_name="scope-a", node_name="n2"), ("UX",))

    def test_register_extra_dofs_rejects_blank_owner_name(self) -> None:
        manager = DofManager()

        with self.assertRaisesRegex(CompilationError, "owner_name 不能为空"):
            manager.register_extra_dofs("scope-a", "", ("LM",))

    def test_register_extra_dofs_rejects_blank_dof_name(self) -> None:
        manager = DofManager()

        with self.assertRaisesRegex(CompilationError, "dof_name 不能为空"):
            manager.register_extra_dofs("scope-a", "constraint-1", ("",))

    def test_auxiliary_dof_location_rejects_blank_owner_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "owner_name 不能为空"):
            DofLocation.auxiliary(scope_name="scope-a", owner_name="", dof_name="LM")

    def test_default_dof_layouts_cover_phase1_elements(self) -> None:
        registry = RuntimeRegistry()

        self.assertEqual(registry.get_dof_layout("C3D8").node_dof_names, ("UX", "UY", "UZ"))
        self.assertEqual(registry.get_dof_layout("CPS4").node_dof_names, ("UX", "UY"))
        self.assertEqual(registry.get_dof_layout("B21").node_dof_names, ("UX", "UY", "RZ"))


if __name__ == "__main__":
    unittest.main()
