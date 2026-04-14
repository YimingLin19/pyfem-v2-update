"""OutputRequest 执行集成测试。"""

import unittest

from pyfem.compiler import Compiler
from pyfem.io import FIELD_KEY_TIME, InMemoryResultsWriter
from pyfem.mesh import Assembly, ElementRecord, Mesh, NodeRecord, Part, PartInstance, RigidTransform
from pyfem.modeldb import BoundaryDef, JobDef, MaterialDef, ModelDB, NodalLoadDef, OutputRequest, SectionDef, StepDef


class OutputRequestExecutionTests(unittest.TestCase):
    """验证 frequency / target / position 进入正式运行时路径。"""

    def test_dynamic_output_request_frequency_and_target_filter_take_effect(self) -> None:
        compiled_model = Compiler().compile(self._build_dynamic_model())
        writer = InMemoryResultsWriter()

        report = compiled_model.get_step_runtime("step-dynamic").run(writer)
        first_frame = writer.frames[0]
        displacement_field = first_frame.get_field("U")
        time_history = writer.read_history("step-dynamic", FIELD_KEY_TIME)

        self.assertEqual(report.frame_count, 6)
        self.assertEqual(report.history_count, 2)
        self.assertEqual(tuple(frame.frame_id for frame in writer.frames), (0, 2, 4, 6, 8, 10))
        self.assertEqual(tuple(time_history.get_series()), (0.0, 0.001, 0.002, 0.003, 0.004, 0.005))
        self.assertEqual(tuple(displacement_field.values.keys()), ("part-1.n2",))

    def test_output_request_scope_filters_dual_instance_targets(self) -> None:
        compiled_model = Compiler().compile(self._build_dual_instance_static_model())
        writer = InMemoryResultsWriter()

        compiled_model.get_step_runtime("step-static").run(writer)
        displacement_field = writer.frames[0].get_field("U")

        self.assertEqual(tuple(displacement_field.values.keys()), ("right.n2",))
        self.assertLess(displacement_field.values["right.n2"]["UY"], 0.0)

    def _build_dynamic_model(self) -> ModelDB:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(2.0, 0.0)))
        mesh.add_element(ElementRecord(name="beam-1", type_key="B21", node_names=("n1", "n2")))
        mesh.add_node_set("root", ("n1",))
        mesh.add_node_set("tip", ("n2",))
        mesh.add_element_set("beam-set", ("beam-1",))

        part = Part(name="part-1", mesh=mesh)
        model = ModelDB(name="dynamic-output")
        model.add_part(part)
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
                scope_name="part-1",
                parameters={"area": 0.03, "moment_inertia_z": 2.0e-4},
            )
        )
        model.add_boundary(BoundaryDef(name="bc-root", target_name="root", dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0}))
        model.add_boundary(BoundaryDef(name="bc-guide", target_name="tip", dof_values={"UY": 0.0, "RZ": 0.0}))
        model.add_output_request(
            OutputRequest(
                name="field-tip",
                variables=("U",),
                target_type="node_set",
                target_name="tip",
                position="NODE",
                frequency=2,
            )
        )
        model.add_output_request(
            OutputRequest(
                name="history-time",
                variables=("TIME",),
                target_type="model",
                position="GLOBAL_HISTORY",
                frequency=2,
            )
        )
        model.add_step(
            StepDef(
                name="step-dynamic",
                procedure_type="implicit_dynamic",
                boundary_names=("bc-root", "bc-guide"),
                output_request_names=("field-tip", "history-time"),
                parameters={
                    "time_step": 0.0005,
                    "total_time": 0.005,
                    "beta": 0.25,
                    "gamma": 0.5,
                    "initial_displacement": {"part-1.n2.UX": 0.01},
                },
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-dynamic",)))
        return model

    def _build_dual_instance_static_model(self) -> ModelDB:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(2.0, 0.0)))
        mesh.add_element(ElementRecord(name="beam-1", type_key="B21", node_names=("n1", "n2")))
        mesh.add_node_set("root", ("n1",))
        mesh.add_node_set("tip", ("n2",))
        mesh.add_element_set("beam-set", ("beam-1",))

        model = ModelDB(name="dual-instance-output")
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
        model.add_nodal_load(NodalLoadDef(name="load-right-tip", target_name="tip", scope_name="right", components={"FY": -12.0}))
        model.add_output_request(
            OutputRequest(
                name="field-right-tip",
                variables=("U",),
                target_type="node_set",
                target_name="tip",
                scope_name="right",
                position="NODE",
            )
        )
        model.add_step(
            StepDef(
                name="step-static",
                procedure_type="static_linear",
                boundary_names=("bc-left-root", "bc-right-root"),
                nodal_load_names=("load-right-tip",),
                output_request_names=("field-right-tip",),
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-static",)))
        return model


if __name__ == "__main__":
    unittest.main()
