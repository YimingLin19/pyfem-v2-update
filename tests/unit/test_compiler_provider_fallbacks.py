"""compiler provider fallback 与 fail-fast 测试。"""

import unittest

from pyfem.compiler import Compiler
from pyfem.compiler.runtime_placeholders import ConstraintRuntimePlaceholder, InteractionRuntimePlaceholder
from pyfem.foundation import PyFEMError
from pyfem.io import InMemoryResultsWriter
from pyfem.mesh import ElementRecord, Mesh, NodeRecord, Part
from pyfem.modeldb import BoundaryDef, InteractionDef, JobDef, MaterialDef, ModelDB, SectionDef, StepDef


class CompilerProviderFallbackTests(unittest.TestCase):
    """验证 compiler 对 provider 缺失时的受控回退与显式报错。"""

    def test_constraint_runtime_falls_back_to_placeholder_when_provider_missing(self) -> None:
        model = self._build_minimal_model()
        model.add_boundary(
            BoundaryDef(
                name="bc-custom",
                target_name="fixed",
                target_type="node_set",
                scope_name="part-1",
                boundary_type="custom_displacement_like",
                dof_values={"UX": 0.0, "UY": 0.0},
            )
        )

        compiled_model = Compiler().compile(model)
        runtime = compiled_model.constraint_runtimes["bc-custom"]

        self.assertIsInstance(runtime, ConstraintRuntimePlaceholder)
        self.assertEqual(runtime.describe()["boundary_type"], "custom_displacement_like")
        self.assertEqual(runtime.describe()["constrained_dof_count"], 4)

    def test_interaction_runtime_falls_back_to_placeholder_when_provider_missing(self) -> None:
        model = self._build_minimal_model()
        model.add_interaction(
            InteractionDef(
                name="interaction-custom",
                interaction_type="future_contact",
                scope_name="part-1",
                parameters={"mode": "fail-fast-extension-point"},
            )
        )

        compiled_model = Compiler().compile(model)
        runtime = compiled_model.interaction_runtimes["interaction-custom"]

        self.assertIsInstance(runtime, InteractionRuntimePlaceholder)
        self.assertEqual(runtime.describe()["interaction_type"], "future_contact")

    def test_missing_procedure_provider_raises_clear_error_when_running_step(self) -> None:
        model = self._build_minimal_model()
        model.add_step(StepDef(name="step-future", procedure_type="future_custom_procedure"))
        model.set_job(JobDef(name="job-1", step_names=("step-future",)))

        compiled_model = Compiler().compile(model)

        with self.assertRaisesRegex(PyFEMError, "尚未绑定正式 ProcedureRuntimeProvider"):
            compiled_model.get_step_runtime("step-future").run(InMemoryResultsWriter())

    def _build_minimal_model(self) -> ModelDB:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(1.0, 0.0)))
        mesh.add_node(NodeRecord(name="n3", coordinates=(1.0, 1.0)))
        mesh.add_node(NodeRecord(name="n4", coordinates=(0.0, 1.0)))
        mesh.add_element(ElementRecord(name="e1", type_key="CPS4", node_names=("n1", "n2", "n3", "n4")))
        mesh.add_node_set("fixed", ("n1", "n4"))
        mesh.add_element_set("plate", ("e1",))

        part = Part(name="part-1", mesh=mesh)
        model = ModelDB(name="provider-fallback")
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
