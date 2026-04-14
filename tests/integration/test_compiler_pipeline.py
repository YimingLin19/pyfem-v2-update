"""编译主线集成测试。"""

import unittest

from pyfem.compiler import Compiler, RuntimeRegistry
from pyfem.foundation.types import DofLocation
from pyfem.kernel.constraints import DisplacementConstraintRuntime
from pyfem.kernel.elements import B21Runtime, CPS4Runtime
from pyfem.kernel.interactions import NoOpInteractionRuntime
from pyfem.kernel.materials import ElasticIsotropicRuntime
from pyfem.kernel.sections import BeamSectionRuntime, PlaneStressSectionRuntime
from pyfem.mesh import Assembly, ElementRecord, Mesh, NodeRecord, Part, PartInstance, RigidTransform
from pyfem.modeldb import BoundaryDef, InteractionDef, JobDef, MaterialDef, ModelDB, OutputRequest, SectionDef, StepDef
from pyfem.procedures import StaticLinearProcedure
from pyfem.io import InpImporter


class CompilerPipelineTests(unittest.TestCase):
    """验证 ModelDB 到 CompiledModel 的主线闭环。"""

    def test_modeldb_compiler_compiled_model_pipeline(self) -> None:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(1.0, 0.0)))
        mesh.add_node(NodeRecord(name="n3", coordinates=(1.0, 1.0)))
        mesh.add_node(NodeRecord(name="n4", coordinates=(0.0, 1.0)))
        mesh.add_element(
            ElementRecord(
                name="element-1",
                type_key="CPS4",
                node_names=("n1", "n2", "n3", "n4"),
            )
        )
        mesh.add_node_set("fixed", ("n1", "n4"))
        mesh.add_element_set("plate", ("element-1",))

        part = Part(name="part-1", mesh=mesh)

        model = ModelDB(name="demo")
        model.add_part(part)
        model.add_material(
            MaterialDef(
                name="mat-1",
                material_type="linear_elastic",
                parameters={"young_modulus": 210000.0, "poisson_ratio": 0.3, "density": 7.85},
            )
        )
        model.add_section(
            SectionDef(
                name="sec-1",
                section_type="plane_stress",
                material_name="mat-1",
                region_name="plate",
                scope_name="part-1",
                parameters={"thickness": 2.0},
            )
        )
        model.add_boundary(
            BoundaryDef(
                name="bc-1",
                target_name="fixed",
                target_type="node_set",
                scope_name="part-1",
                dof_values={"UX": 0.0, "UY": 0.0},
            )
        )
        model.add_interaction(
            InteractionDef(
                name="contact-placeholder-ready",
                interaction_type="noop",
                scope_name="part-1",
                parameters={"reason": "phase1-extension-point"},
            )
        )
        model.add_output_request(OutputRequest(name="field-u", variables=("U",), target_type="model"))
        model.add_step(
            StepDef(
                name="step-1",
                procedure_type="static",
                boundary_names=("bc-1",),
                output_request_names=("field-u",),
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-1",)))

        compiled_model = Compiler(registry=RuntimeRegistry()).compile(model)

        element_runtime = compiled_model.get_element_runtime("part-1.element-1")
        boundary_runtime = compiled_model.constraint_runtimes["bc-1"]
        interaction_runtime = compiled_model.interaction_runtimes["contact-placeholder-ready"]
        step_runtime = compiled_model.get_step_runtime("step-1")
        material_runtime = compiled_model.material_runtimes["mat-1"]
        section_runtime = compiled_model.section_runtimes["sec-1"]

        self.assertIs(compiled_model.model, model)
        self.assertEqual(compiled_model.dof_manager.num_dofs(), 8)
        self.assertEqual(element_runtime.get_dof_indices(), tuple(range(8)))
        self.assertIsInstance(material_runtime, ElasticIsotropicRuntime)
        self.assertIsInstance(section_runtime, PlaneStressSectionRuntime)
        self.assertIsInstance(element_runtime, CPS4Runtime)
        self.assertIsInstance(boundary_runtime, DisplacementConstraintRuntime)
        self.assertIsInstance(interaction_runtime, NoOpInteractionRuntime)
        self.assertIsInstance(step_runtime, StaticLinearProcedure)
        self.assertEqual(section_runtime.describe()["material_name"], "mat-1")
        self.assertEqual(section_runtime.describe()["thickness"], 2.0)
        self.assertEqual(interaction_runtime.describe()["interaction_type"], "noop")
        self.assertEqual(
            tuple(item.dof_index for item in boundary_runtime.collect_constrained_dofs()),
            (0, 1, 6, 7),
        )
        self.assertEqual(step_runtime.describe()["boundary_names"], ("bc-1",))

    def test_compiler_distinguishes_two_instances_of_same_part(self) -> None:
        model = self._build_dual_instance_beam_model()

        compiled_model = Compiler(registry=RuntimeRegistry()).compile(model)

        left_runtime = compiled_model.get_element_runtime("left.beam-1")
        right_runtime = compiled_model.get_element_runtime("right.beam-1")
        left_boundary = compiled_model.constraint_runtimes["bc-left-root"]
        right_boundary = compiled_model.constraint_runtimes["bc-right-root"]
        section_runtime = compiled_model.section_runtimes["sec-1"]

        self.assertIsInstance(left_runtime, B21Runtime)
        self.assertIsInstance(right_runtime, B21Runtime)
        self.assertIsInstance(section_runtime, BeamSectionRuntime)
        self.assertEqual(compiled_model.dof_manager.num_dofs(), 12)
        self.assertEqual(left_runtime.coordinates, ((0.0, 0.0), (2.0, 0.0)))
        self.assertEqual(right_runtime.coordinates, ((5.0, 0.0), (7.0, 0.0)))
        self.assertEqual(left_runtime.get_dof_indices(), (0, 1, 2, 3, 4, 5))
        self.assertEqual(right_runtime.get_dof_indices(), (6, 7, 8, 9, 10, 11))
        self.assertEqual(
            compiled_model.dof_manager.get_global_id(DofLocation(scope_name="right", node_name="n2", dof_name="UY")),
            10,
        )
        self.assertEqual(
            tuple(item.dof_index for item in left_boundary.collect_constrained_dofs()),
            (0, 1, 2),
        )
        self.assertEqual(
            tuple(item.dof_index for item in right_boundary.collect_constrained_dofs()),
            (6, 7, 8),
        )

    def test_compiler_keeps_part_section_region_when_assembly_alias_uses_same_set_name(self) -> None:
        model = InpImporter().import_text(
            """
*Part, name=BEAM
*Node
1, 0.0, 0.0
2, 1.0, 0.0
3, 2.0, 0.0
4, 3.0, 0.0
*Element, type=B21, elset=Set-1
1, 1, 2
2, 2, 3
3, 3, 4
*Nset, nset=ROOT
1
*Beam Section, elset=Set-1, material=STEEL
0.03, 0.0002
*End Part
*Material, name=STEEL
*Elastic
1000000.0, 0.3
*Assembly, name=ASM
*Instance, name=Part-1-1, part=BEAM
*End Instance
*Nset, nset=_PickedSet7, instance=Part-1-1
1
*Elset, elset=Set-1, instance=Part-1-1
1
*End Assembly
*Boundary
_PickedSet7, 1, 2, 0.0
*Step, name=STEP-1
*Static
*End Step
""",
            model_name="assembly-set-shadowing",
            source_name="assembly-set-shadowing.inp",
        )

        compiled_model = Compiler(registry=RuntimeRegistry()).compile(model)

        self.assertIsNotNone(compiled_model.get_element_runtime("Part-1-1.1"))
        self.assertIsNotNone(compiled_model.get_element_runtime("Part-1-1.2"))
        self.assertIsNotNone(compiled_model.get_element_runtime("Part-1-1.3"))

    def _build_dual_instance_beam_model(self) -> ModelDB:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(2.0, 0.0)))
        mesh.add_element(ElementRecord(name="beam-1", type_key="B21", node_names=("n1", "n2")))
        mesh.add_node_set("root", ("n1",))
        mesh.add_node_set("tip", ("n2",))
        mesh.add_element_set("beam-set", ("beam-1",))

        model = ModelDB(name="dual-instance-compile")
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

        model.add_boundary(BoundaryDef(name="bc-left-root", target_name="root", scope_name="left", dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0}))
        model.add_boundary(BoundaryDef(name="bc-right-root", target_name="root", scope_name="right", dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0}))
        model.add_output_request(OutputRequest(name="field-u", variables=("U",), target_type="model"))
        model.add_step(
            StepDef(
                name="step-1",
                procedure_type="static_linear",
                boundary_names=("bc-left-root", "bc-right-root"),
                output_request_names=("field-u",),
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-1",)))
        return model


if __name__ == "__main__":
    unittest.main()
