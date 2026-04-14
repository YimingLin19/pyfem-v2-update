"""实例 / 作用域边界回归测试。"""

import unittest

from pyfem.compiler import Compiler
from pyfem.foundation import ModelValidationError
from pyfem.foundation.types import DofLocation
from tests.support import (
    build_dual_instance_beam_model,
    build_dual_instance_c3d8_pressure_model,
    build_rotated_beam_assembly_model,
    build_rotated_instance_c3d8_pressure_model,
    build_rotated_instance_cps4_solver_model,
    run_step,
)


class InstanceScopeRegressionTests(unittest.TestCase):
    """固化 canonical scope、变换几何与实例隔离边界。"""

    def test_rotated_instance_keeps_canonical_scope_geometry_and_orientation(self) -> None:
        model = build_rotated_beam_assembly_model()

        model.validate()
        right_scope = model.resolve_compilation_scope("right")

        self.assertIsNotNone(right_scope)
        self.assertEqual(right_scope.get_node_geometry_record("n1").coordinates, (3.0, 0.0))
        self.assertEqual(right_scope.get_node_geometry_record("n2").coordinates, (3.0, 2.0))
        orientation = right_scope.get_orientation("ori-1")
        self.assertIsNotNone(orientation)
        self.assertEqual(orientation.axis_1, (0.0, 1.0))
        self.assertEqual(orientation.axis_2, (-1.0, 0.0))

    def test_dual_instance_surface_load_output_and_dof_owners_remain_scope_separated(self) -> None:
        model = build_dual_instance_c3d8_pressure_model()
        compiled_model, writer = run_step(model, "step-static")

        left_scope = model.resolve_compilation_scope("left")
        right_scope = model.resolve_compilation_scope("right")
        frame = writer.read_frame("step-static", 0)
        displacement = frame.get_field("U").values
        reaction = frame.get_field("RF").values
        left_loaded_node_keys = ("left.1", "left.2", "left.3", "left.4")
        right_loaded_node_keys = ("right.1", "right.2", "right.3", "right.4")
        right_fixed_node_keys = ("right.5", "right.6", "right.7", "right.8")

        self.assertIsNotNone(left_scope)
        self.assertIsNotNone(right_scope)
        self.assertIsNotNone(left_scope.get_surface("PRESSURE_FACE"))
        self.assertIsNotNone(right_scope.get_surface("PRESSURE_FACE"))
        self.assertEqual(
            compiled_model.dof_manager.get_global_id(DofLocation(scope_name="left", node_name="1", dof_name="UX")),
            0,
        )
        self.assertGreater(
            compiled_model.dof_manager.get_global_id(DofLocation(scope_name="right", node_name="1", dof_name="UX")),
            compiled_model.dof_manager.get_global_id(DofLocation(scope_name="left", node_name="8", dof_name="UZ")),
        )
        self.assertTrue(all(abs(displacement[node_key]["UX"]) <= 1.0e-12 for node_key in left_loaded_node_keys))
        self.assertTrue(all(displacement[node_key]["UX"] > 0.0 for node_key in right_loaded_node_keys))
        self.assertAlmostEqual(abs(sum(reaction[node_key]["UX"] for node_key in right_fixed_node_keys)), 2.0, delta=1.0e-8)

    def test_rotated_cps4_instances_produce_scope_separated_and_geometry_sensitive_solver_results(self) -> None:
        model = build_rotated_instance_cps4_solver_model()
        _, writer = run_step(model, "step-static")

        frame = writer.read_frame("step-static", 0)
        displacement = frame.get_field("U").values
        reaction = frame.get_field("RF").values
        axial_right_nodes = ("axial.n2", "axial.n3")
        rotated_right_nodes = ("rotated.n2", "rotated.n3")
        axial_right_reaction_y = sum(reaction[node_key]["UY"] for node_key in axial_right_nodes)
        rotated_right_reaction_y = sum(reaction[node_key]["UY"] for node_key in rotated_right_nodes)

        self.assertEqual(tuple(displacement.keys()), ("axial.n1", "axial.n2", "axial.n3", "axial.n4", "rotated.n1", "rotated.n2", "rotated.n3", "rotated.n4"))
        self.assertAlmostEqual(displacement["axial.n2"]["UY"], 0.001, places=12)
        self.assertAlmostEqual(displacement["axial.n3"]["UY"], 0.001, places=12)
        self.assertAlmostEqual(displacement["rotated.n2"]["UY"], 0.001, places=12)
        self.assertAlmostEqual(displacement["rotated.n3"]["UY"], 0.001, places=12)
        self.assertAlmostEqual(abs(axial_right_reaction_y), 0.0, delta=1.0e-10)
        self.assertGreater(abs(rotated_right_reaction_y), 1.0e-1)
        self.assertGreater(abs(abs(rotated_right_reaction_y) - abs(axial_right_reaction_y)), 1.0e-1)
        self.assertAlmostEqual(displacement["axial.n4"]["UX"], -5.0e-4, delta=1.0e-8)
        self.assertAlmostEqual(displacement["rotated.n4"]["UX"], 1.25e-4, delta=1.0e-8)

    def test_rotated_c3d8_surface_pressure_is_consumed_by_solver_in_global_rotated_direction(self) -> None:
        model = build_rotated_instance_c3d8_pressure_model()
        _, writer = run_step(model, "step-static")

        frame = writer.read_frame("step-static", 0)
        displacement = frame.get_field("U").values
        reaction = frame.get_field("RF").values
        left_loaded_nodes = ("left.1", "left.2", "left.3", "left.4")
        right_loaded_nodes = ("right.1", "right.2", "right.3", "right.4")
        right_fixed_nodes = ("right.5", "right.6", "right.7", "right.8")
        right_reaction_x = sum(reaction[node_key]["UX"] for node_key in right_fixed_nodes)
        right_reaction_y = sum(reaction[node_key]["UY"] for node_key in right_fixed_nodes)

        self.assertTrue(all(abs(displacement[node_key]["UX"]) <= 1.0e-12 for node_key in left_loaded_nodes))
        self.assertTrue(all(abs(displacement[node_key]["UY"]) <= 1.0e-12 for node_key in left_loaded_nodes))
        self.assertTrue(all(displacement[node_key]["UY"] > 0.0 for node_key in right_loaded_nodes))
        self.assertAlmostEqual(abs(right_reaction_x), 0.0, delta=1.0e-8)
        self.assertAlmostEqual(abs(right_reaction_y), 2.0, delta=1.0e-8)

    def test_part_name_scope_alias_still_fails_fast_under_assembly(self) -> None:
        model = build_dual_instance_beam_model(boundary_scope_name="beam-part")

        with self.assertRaises(ModelValidationError):
            Compiler().compile(model)


if __name__ == "__main__":
    unittest.main()
