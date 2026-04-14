"""OutputRequest 合同单元测试。"""

import unittest

from pyfem.compiler import Compiler
from pyfem.foundation import CompilationError
from pyfem.mesh import ElementRecord, Mesh, NodeRecord, Part
from pyfem.modeldb import BoundaryDef, JobDef, MaterialDef, ModelDB, OutputRequest, SectionDef, StepDef


class OutputRequestContractTests(unittest.TestCase):
    """验证 OutputRequest 的 compile-time 合同。"""

    def test_compile_fails_for_mixed_variable_position_contract(self) -> None:
        model = self._build_static_model(
            OutputRequest(
                name="bad-output",
                variables=("U", "S"),
                target_type="model",
                position="NODE",
            )
        )

        with self.assertRaises(CompilationError):
            Compiler().compile(model)

    def test_compile_fails_for_unsupported_target_type_at_node_position(self) -> None:
        model = self._build_static_model(
            OutputRequest(
                name="bad-target",
                variables=("U",),
                target_type="element_set",
                target_name="plate",
                position="NODE",
            )
        )

        with self.assertRaises(CompilationError):
            Compiler().compile(model)

    def test_compile_fails_for_non_positive_output_frequency(self) -> None:
        model = self._build_static_model(
            OutputRequest(
                name="bad-frequency",
                variables=("U",),
                target_type="model",
                position="NODE",
                frequency=0,
            )
        )

        with self.assertRaisesRegex(CompilationError, "frequency 必须大于零"):
            Compiler().compile(model)

    def test_compile_fails_when_history_output_declares_target_name(self) -> None:
        model = self._build_static_model(
            OutputRequest(
                name="bad-history-target",
                variables=("TIME",),
                target_type="model",
                target_name="tip",
                position="GLOBAL_HISTORY",
            )
        )

        with self.assertRaisesRegex(CompilationError, "历史量输出不允许声明 target_name"):
            Compiler().compile(model)

    def _build_static_model(self, output_request: OutputRequest) -> ModelDB:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(1.0, 0.0)))
        mesh.add_node(NodeRecord(name="n3", coordinates=(1.0, 1.0)))
        mesh.add_node(NodeRecord(name="n4", coordinates=(0.0, 1.0)))
        mesh.add_element(ElementRecord(name="e1", type_key="CPS4", node_names=("n1", "n2", "n3", "n4")))
        mesh.add_node_set("fixed", ("n1", "n4"))
        mesh.add_element_set("plate", ("e1",))

        part = Part(name="part-1", mesh=mesh)
        model = ModelDB(name="output-contract")
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
        model.add_boundary(BoundaryDef(name="bc-1", target_name="fixed", dof_values={"UX": 0.0, "UY": 0.0}))
        model.add_output_request(output_request)
        model.add_step(
            StepDef(
                name="step-1",
                procedure_type="static_linear",
                boundary_names=("bc-1",),
                output_request_names=(output_request.name,),
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-1",)))
        return model


if __name__ == "__main__":
    unittest.main()
