"""RuntimeState 与显式状态装配测试。"""

import unittest

import numpy

from pyfem.compiler import CompiledModel, Compiler
from pyfem.foundation.types import ElementLocation, NodeLocation
from pyfem.kernel import DofManager
from pyfem.kernel.elements.base import ElementContribution, ElementRuntime
from pyfem.mesh import ElementRecord, Mesh, NodeRecord, Part
from pyfem.modeldb import MaterialDef, ModelDB, SectionDef
from pyfem.solver import DiscreteProblem


class TrackingElementRuntime(ElementRuntime):
    """用于验证显式状态传递的测试单元。"""

    def __init__(self, location: ElementLocation, dof_indices: tuple[int, ...]) -> None:
        self._location = location
        self._dof_indices = dof_indices

    def get_type_key(self) -> str:
        return "TRACKING"

    def get_dof_layout(self) -> tuple[str, ...]:
        return ("UX",)

    def get_location(self) -> ElementLocation:
        return self._location

    def get_dof_indices(self) -> tuple[int, ...]:
        return self._dof_indices

    def allocate_state(self) -> dict[str, object]:
        return {"multiplier": 1.0}

    def compute_tangent_and_residual(self, displacement=None, state=None) -> ElementContribution:
        multiplier = float((state or {}).get("multiplier", 1.0))
        value = 0.0 if displacement is None else float(displacement[0])
        return ElementContribution(
            stiffness=((multiplier,),),
            residual=(multiplier * value,),
        )

    def compute_mass(self, state=None):
        return ((1.0,),)

    def compute_damping(self, state=None):
        return None

    def collect_output(self, displacement=None, state=None):
        return {"multiplier": float((state or {}).get("multiplier", 1.0))}


class RuntimeStateTests(unittest.TestCase):
    """验证 RuntimeState / StateManager 的主线行为。"""

    def test_state_manager_commits_and_rolls_back_local_states(self) -> None:
        compiled_model = Compiler().compile(self._build_minimal_plane_model())
        problem = DiscreteProblem(compiled_model)

        trial_state = problem.begin_trial()
        trial_state.material_states["mat-1"]["mode"] = "trial-material"
        trial_state.integration_point_states["part-1.e1"] = {"ip1": {"material_state": {"mode": "trial-ip"}}}
        problem.commit()

        committed_state = problem.get_committed_state()
        self.assertEqual(committed_state.material_states["mat-1"]["mode"], "trial-material")
        self.assertEqual(
            committed_state.integration_point_states["part-1.e1"]["ip1"]["material_state"]["mode"],
            "trial-ip",
        )

        trial_state = problem.begin_trial()
        trial_state.material_states["mat-1"]["mode"] = "corrupted"
        trial_state.integration_point_states["part-1.e1"]["ip1"]["material_state"]["mode"] = "corrupted"
        rolled_back_state = problem.rollback()

        self.assertEqual(rolled_back_state.material_states["mat-1"]["mode"], "trial-material")
        self.assertEqual(
            rolled_back_state.integration_point_states["part-1.e1"]["ip1"]["material_state"]["mode"],
            "trial-ip",
        )

    def test_rollback_restores_global_kinematics(self) -> None:
        compiled_model = Compiler().compile(self._build_minimal_plane_model())
        problem = DiscreteProblem(compiled_model)

        committed_trial = problem.begin_trial()
        committed_trial.displacement[:] = numpy.arange(compiled_model.dof_manager.num_dofs(), dtype=float)
        committed_trial.velocity[:] = 1.5
        committed_trial.acceleration[:] = -2.0
        committed_trial.time = 0.25
        problem.commit()

        trial_state = problem.begin_trial()
        trial_state.displacement[:] = -9.0
        trial_state.velocity[:] = 99.0
        trial_state.acceleration[:] = 123.0
        trial_state.time = 9.99
        rolled_back_state = problem.rollback()

        self.assertTrue(numpy.allclose(rolled_back_state.displacement, numpy.arange(compiled_model.dof_manager.num_dofs(), dtype=float)))
        self.assertTrue(numpy.allclose(rolled_back_state.velocity, numpy.full(compiled_model.dof_manager.num_dofs(), 1.5)))
        self.assertTrue(numpy.allclose(rolled_back_state.acceleration, numpy.full(compiled_model.dof_manager.num_dofs(), -2.0)))
        self.assertAlmostEqual(rolled_back_state.time, 0.25)

    def test_problem_assembles_with_explicit_runtime_state(self) -> None:
        manager = DofManager()
        node_location = NodeLocation(scope_name="scope-1", node_name="n1")
        dof_indices = manager.register_node_dofs(node_location, ("UX",))
        manager.finalize()

        compiled_model = CompiledModel(
            model=ModelDB(name="tracking-model"),
            dof_manager=manager,
            element_runtimes={
                "scope-1.e1": TrackingElementRuntime(
                    location=ElementLocation(scope_name="scope-1", element_name="e1"),
                    dof_indices=dof_indices,
                )
            },
        )
        problem = DiscreteProblem(compiled_model)
        state = problem.create_zero_state()
        state.displacement = numpy.asarray((3.0,), dtype=float)
        state.element_states["scope-1.e1"]["multiplier"] = 2.0

        tangent = problem.assemble_tangent(state=state)
        residual = problem.assemble_residual(state=state)

        self.assertAlmostEqual(float(tangent[0, 0]), 2.0)
        self.assertAlmostEqual(float(residual[0]), 6.0)

    def _build_minimal_plane_model(self) -> ModelDB:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(1.0, 0.0)))
        mesh.add_node(NodeRecord(name="n3", coordinates=(1.0, 1.0)))
        mesh.add_node(NodeRecord(name="n4", coordinates=(0.0, 1.0)))
        mesh.add_element(ElementRecord(name="e1", type_key="CPS4", node_names=("n1", "n2", "n3", "n4")))
        mesh.add_element_set("plate", ("e1",))

        part = Part(name="part-1", mesh=mesh)
        model = ModelDB(name="runtime-state-model")
        model.add_part(part)
        model.add_material(
            MaterialDef(
                name="mat-1",
                material_type="linear_elastic",
                parameters={"young_modulus": 1000.0, "poisson_ratio": 0.3},
            )
        )
        model.add_section(
            SectionDef(
                name="sec-1",
                section_type="plane_stress",
                material_name="mat-1",
                region_name="plate",
                scope_name="part-1",
                parameters={"thickness": 1.0},
            )
        )
        return model


if __name__ == "__main__":
    unittest.main()

