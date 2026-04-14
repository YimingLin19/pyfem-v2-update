import unittest
from pathlib import Path
from uuid import uuid4

from pyfem.compiler import Compiler
from pyfem.io import (
    FIELD_KEY_E,
    FIELD_KEY_E_IP,
    FIELD_KEY_E_REC,
    FIELD_KEY_S,
    FIELD_KEY_S_AVG,
    FIELD_KEY_S_IP,
    FIELD_KEY_S_PRINCIPAL_AVG,
    FIELD_KEY_S_PRINCIPAL_IP,
    FIELD_KEY_S_PRINCIPAL_REC,
    FIELD_KEY_S_REC,
    FIELD_KEY_S_VM_AVG,
    FIELD_KEY_S_VM_IP,
    FIELD_KEY_S_VM_REC,
    FIELD_KEY_U,
    FIELD_KEY_U_MAG,
    JsonResultsReader,
    JsonResultsWriter,
    POSITION_ELEMENT_CENTROID,
    POSITION_ELEMENT_NODAL,
    POSITION_INTEGRATION_POINT,
    POSITION_NODE,
    POSITION_NODE_AVERAGED,
    RESULT_SOURCE_AVERAGED,
    RESULT_SOURCE_DERIVED,
    RESULT_SOURCE_RAW,
    RESULT_SOURCE_RECOVERED,
    VtkExporter,
)
from pyfem.mesh import ElementRecord, Mesh, NodeRecord, Part
from pyfem.modeldb import BoundaryDef, JobDef, MaterialDef, ModelDB, OutputRequest, SectionDef, StepDef
from pyfem.post import ResultsFacade
from pyfem.post.common import FIELD_METADATA_KEY_AVERAGING_GROUPS, FIELD_METADATA_KEY_BASE_TARGET_KEYS


class PostProcessingPipelinePhase2IntegrationTests(unittest.TestCase):
    """验证 Phase 2 后处理结果消费链。"""

    def test_json_roundtrip_exposes_full_post_pipeline_fields(self) -> None:
        target_path = Path("tests") / f"_tmp_post_phase2_{uuid4().hex}.json"
        try:
            writer = JsonResultsWriter(target_path)
            Compiler().compile(self._build_single_cps4_model()).get_step_runtime("step-static").run(writer)

            reader = JsonResultsReader(target_path)
            facade = ResultsFacade(reader)
            frame = reader.read_frame("step-static", 0)

            self.assertEqual(reader.read_field("step-static", 0, FIELD_KEY_U).position, POSITION_NODE)
            self.assertEqual(reader.read_field("step-static", 0, FIELD_KEY_U_MAG).source_type, RESULT_SOURCE_DERIVED)
            self.assertEqual(reader.read_field("step-static", 0, FIELD_KEY_S).position, POSITION_ELEMENT_CENTROID)
            self.assertEqual(reader.read_field("step-static", 0, FIELD_KEY_E).position, POSITION_ELEMENT_CENTROID)
            self.assertEqual(reader.read_field("step-static", 0, FIELD_KEY_S_IP).position, POSITION_INTEGRATION_POINT)
            self.assertEqual(reader.read_field("step-static", 0, FIELD_KEY_S_IP).source_type, RESULT_SOURCE_RAW)
            self.assertEqual(reader.read_field("step-static", 0, FIELD_KEY_E_IP).source_type, RESULT_SOURCE_RAW)
            self.assertEqual(reader.read_field("step-static", 0, FIELD_KEY_S_REC).position, POSITION_ELEMENT_NODAL)
            self.assertEqual(reader.read_field("step-static", 0, FIELD_KEY_S_REC).source_type, RESULT_SOURCE_RECOVERED)
            self.assertEqual(reader.read_field("step-static", 0, FIELD_KEY_E_REC).source_type, RESULT_SOURCE_RECOVERED)
            self.assertEqual(reader.read_field("step-static", 0, FIELD_KEY_S_AVG).position, POSITION_NODE_AVERAGED)
            self.assertEqual(reader.read_field("step-static", 0, FIELD_KEY_S_AVG).source_type, RESULT_SOURCE_AVERAGED)
            self.assertEqual(reader.read_field("step-static", 0, FIELD_KEY_S_VM_IP).source_type, RESULT_SOURCE_DERIVED)
            self.assertEqual(reader.read_field("step-static", 0, FIELD_KEY_S_VM_REC).source_type, RESULT_SOURCE_DERIVED)
            self.assertEqual(reader.read_field("step-static", 0, FIELD_KEY_S_VM_AVG).source_type, RESULT_SOURCE_DERIVED)
            self.assertEqual(reader.read_field("step-static", 0, FIELD_KEY_S_PRINCIPAL_IP).source_type, RESULT_SOURCE_DERIVED)
            self.assertEqual(reader.read_field("step-static", 0, FIELD_KEY_S_PRINCIPAL_REC).source_type, RESULT_SOURCE_DERIVED)
            self.assertEqual(reader.read_field("step-static", 0, FIELD_KEY_S_PRINCIPAL_AVG).source_type, RESULT_SOURCE_DERIVED)
            self.assertIn(POSITION_NODE, frame.field_positions)
            self.assertIn(POSITION_ELEMENT_CENTROID, frame.field_positions)
            self.assertIn(POSITION_INTEGRATION_POINT, frame.field_positions)
            self.assertIn(POSITION_ELEMENT_NODAL, frame.field_positions)
            self.assertIn(POSITION_NODE_AVERAGED, frame.field_positions)
            self.assertIn(RESULT_SOURCE_RAW, frame.field_source_types)
            self.assertIn(RESULT_SOURCE_RECOVERED, frame.field_source_types)
            self.assertIn(RESULT_SOURCE_AVERAGED, frame.field_source_types)
            self.assertIn(RESULT_SOURCE_DERIVED, frame.field_source_types)
            self.assertEqual(reader.read_field("step-static", 0, FIELD_KEY_S_IP).target_count, 4)
            self.assertEqual(reader.read_field("step-static", 0, FIELD_KEY_S_REC).target_count, 4)
            self.assertEqual(reader.read_field("step-static", 0, FIELD_KEY_S_AVG).target_count, 4)

            averaged_overview = facade.fields(
                step_name="step-static",
                frame_id=0,
                field_name=FIELD_KEY_S_AVG,
                target_key="part-1.n1",
            )[0]
            self.assertEqual(averaged_overview.target_keys, ("part-1.n1",))
            self.assertEqual(averaged_overview.source_type, RESULT_SOURCE_AVERAGED)
        finally:
            target_path.unlink(missing_ok=True)

    def test_facade_probe_csv_and_vtk_export_consume_post_pipeline_fields(self) -> None:
        results_path = Path("tests") / f"_tmp_post_phase2_consume_{uuid4().hex}.json"
        csv_path = Path("tests") / f"_tmp_post_phase2_probe_{uuid4().hex}.csv"
        vtk_path = Path("tests") / f"_tmp_post_phase2_export_{uuid4().hex}.vtk"
        model = self._build_single_cps4_model()
        try:
            Compiler().compile(model).get_step_runtime("step-static").run(JsonResultsWriter(results_path))

            reader = JsonResultsReader(results_path)
            facade = ResultsFacade(reader)
            field_overviews = {item.field_name: item for item in facade.fields(step_name="step-static", frame_id=0)}
            recovered_field_names = tuple(item.field_name for item in facade.recovered_fields(step_name="step-static", frame_id=0))
            averaged_field_names = tuple(item.field_name for item in facade.averaged_fields(step_name="step-static", frame_id=0))
            derived_field_names = tuple(item.field_name for item in facade.derived_fields(step_name="step-static", frame_id=0))

            self.assertEqual(field_overviews[FIELD_KEY_S].position, POSITION_ELEMENT_CENTROID)
            self.assertEqual(field_overviews[FIELD_KEY_S].source_type, RESULT_SOURCE_RAW)
            self.assertEqual(field_overviews[FIELD_KEY_S].component_names, ("S11", "S22", "S12"))
            self.assertEqual(field_overviews[FIELD_KEY_S_IP].component_names, ("S11", "S22", "S12"))
            self.assertIsNotNone(field_overviews[FIELD_KEY_S].min_value)
            self.assertIsNotNone(field_overviews[FIELD_KEY_S].max_value)
            self.assertIn(FIELD_KEY_S_REC, recovered_field_names)
            self.assertIn(FIELD_KEY_S_AVG, averaged_field_names)
            self.assertIn(FIELD_KEY_S_VM_AVG, derived_field_names)

            probe = facade.probe()
            node_probe = probe.node_component("step-static", "part-1.n2", "UX", field_name=FIELD_KEY_U)
            element_probe = probe.element_component("step-static", "part-1.e1", "S11", field_name=FIELD_KEY_S)
            integration_point_probe = probe.integration_point_component(
                "step-static", "part-1.e1.ip1", "S11", field_name=FIELD_KEY_S_IP
            )
            averaged_probe = probe.averaged_node_component("step-static", "part-1.n1", "S11", field_name=FIELD_KEY_S_AVG)

            self.assertEqual(len(node_probe.values), 1)
            self.assertEqual(len(element_probe.values), 1)
            self.assertEqual(len(integration_point_probe.values), 1)
            self.assertEqual(len(averaged_probe.values), 1)
            self.assertEqual(element_probe.values, (1.0,))
            self.assertEqual(node_probe.metadata["position"], POSITION_NODE)
            self.assertEqual(element_probe.metadata["position"], POSITION_ELEMENT_CENTROID)
            self.assertEqual(integration_point_probe.metadata["position"], POSITION_INTEGRATION_POINT)
            self.assertEqual(averaged_probe.metadata["position"], POSITION_NODE_AVERAGED)

            probe.export_csv(integration_point_probe, csv_path)
            csv_content = csv_path.read_text(encoding="utf-8")
            self.assertIn("step_name,source_name,axis_kind,axis_value,value,field_name", csv_content)
            self.assertIn("part-1.e1.ip1", csv_content)
            self.assertIn(FIELD_KEY_S_IP, csv_content)

            VtkExporter().export(model=model, results_reader=reader, path=vtk_path, step_name="step-static")
            vtk_content = vtk_path.read_text(encoding="utf-8")
            self.assertIn("VECTORS RAW__U float", vtk_content)
            self.assertIn("SCALARS RAW__S__S11 float 1", vtk_content)
            self.assertIn("SCALARS RAW__S_IP__IP1__S11 float 1", vtk_content)
            self.assertIn("SCALARS RECOVERED__S_REC__N1__S11 float 1", vtk_content)
            self.assertIn("SCALARS AVERAGED__S_AVG__S11 float 1", vtk_content)
            self.assertIn("SCALARS DERIVED__S_VM_AVG__MISES float 1", vtk_content)
        finally:
            results_path.unlink(missing_ok=True)
            csv_path.unlink(missing_ok=True)
            vtk_path.unlink(missing_ok=True)

    def test_node_averaged_stress_breaks_material_boundary(self) -> None:
        target_path = Path("tests") / f"_tmp_post_phase2_boundary_{uuid4().hex}.json"
        writer = JsonResultsWriter(target_path)
        try:
            Compiler().compile(self._build_dual_material_cps4_model()).get_step_runtime("step-static").run(writer)
            reader = JsonResultsReader(target_path)
            avg_field = reader.read_field("step-static", 0, FIELD_KEY_S_AVG)
            base_target_keys = avg_field.metadata[FIELD_METADATA_KEY_BASE_TARGET_KEYS]
            interface_targets = [
                target_key
                for target_key, base_target_key in base_target_keys.items()
                if base_target_key == "part-1.n2"
            ]

            self.assertEqual(len(interface_targets), 2)
            self.assertEqual(
                len(set(avg_field.metadata[FIELD_METADATA_KEY_AVERAGING_GROUPS][target_key] for target_key in interface_targets)),
                2,
            )
            self.assertTrue(all(target_key in avg_field.values for target_key in interface_targets))
        finally:
            target_path.unlink(missing_ok=True)

    def _build_single_cps4_model(self) -> ModelDB:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(1.0, 0.0)))
        mesh.add_node(NodeRecord(name="n3", coordinates=(1.0, 1.0)))
        mesh.add_node(NodeRecord(name="n4", coordinates=(0.0, 1.0)))
        mesh.add_element(ElementRecord(name="e1", type_key="CPS4", node_names=("n1", "n2", "n3", "n4")))
        mesh.add_node_set("left", ("n1", "n4"))
        mesh.add_node_set("right", ("n2", "n3"))
        mesh.add_node_set("anchor", ("n1",))
        mesh.add_element_set("plate", ("e1",))

        model = ModelDB(name="post-phase2-cps4")
        model.add_part(Part(name="part-1", mesh=mesh))
        model.add_material(
            MaterialDef(
                name="mat-1",
                material_type="linear_elastic",
                parameters={"young_modulus": 1000.0, "poisson_ratio": 0.25, "density": 1.0},
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
        model.add_boundary(BoundaryDef(name="bc-left", target_name="left", dof_values={"UX": 0.0}))
        model.add_boundary(BoundaryDef(name="bc-right", target_name="right", dof_values={"UX": 0.001}))
        model.add_boundary(BoundaryDef(name="bc-anchor", target_name="anchor", dof_values={"UY": 0.0}))
        model.add_output_request(OutputRequest(name="node-base", variables=(FIELD_KEY_U, FIELD_KEY_U_MAG), target_type="model", position="NODE"))
        model.add_output_request(OutputRequest(name="element-centroid", variables=(FIELD_KEY_S, FIELD_KEY_E), target_type="model", position="ELEMENT_CENTROID"))
        model.add_output_request(
            OutputRequest(
                name="integration-point",
                variables=(FIELD_KEY_S_IP, FIELD_KEY_E_IP, FIELD_KEY_S_VM_IP, FIELD_KEY_S_PRINCIPAL_IP),
                target_type="model",
                position="INTEGRATION_POINT",
            )
        )
        model.add_output_request(
            OutputRequest(
                name="element-nodal",
                variables=(FIELD_KEY_S_REC, FIELD_KEY_E_REC, FIELD_KEY_S_VM_REC, FIELD_KEY_S_PRINCIPAL_REC),
                target_type="model",
                position="ELEMENT_NODAL",
            )
        )
        model.add_output_request(
            OutputRequest(
                name="node-averaged",
                variables=(FIELD_KEY_S_AVG, FIELD_KEY_S_VM_AVG, FIELD_KEY_S_PRINCIPAL_AVG),
                target_type="model",
                position="NODE_AVERAGED",
            )
        )
        model.add_step(
            StepDef(
                name="step-static",
                procedure_type="static_linear",
                boundary_names=("bc-left", "bc-right", "bc-anchor"),
                output_request_names=("node-base", "element-centroid", "integration-point", "element-nodal", "node-averaged"),
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-static",)))
        return model

    def _build_dual_material_cps4_model(self) -> ModelDB:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(1.0, 0.0)))
        mesh.add_node(NodeRecord(name="n3", coordinates=(2.0, 0.0)))
        mesh.add_node(NodeRecord(name="n4", coordinates=(0.0, 1.0)))
        mesh.add_node(NodeRecord(name="n5", coordinates=(1.0, 1.0)))
        mesh.add_node(NodeRecord(name="n6", coordinates=(2.0, 1.0)))
        mesh.add_element(ElementRecord(name="e1", type_key="CPS4", node_names=("n1", "n2", "n5", "n4")))
        mesh.add_element(ElementRecord(name="e2", type_key="CPS4", node_names=("n2", "n3", "n6", "n5")))
        mesh.add_node_set("left", ("n1", "n4"))
        mesh.add_node_set("right", ("n3", "n6"))
        mesh.add_node_set("anchor", ("n1",))
        mesh.add_node_set("interface", ("n2", "n5"))
        mesh.add_element_set("left-set", ("e1",))
        mesh.add_element_set("right-set", ("e2",))

        model = ModelDB(name="post-phase2-boundary")
        model.add_part(Part(name="part-1", mesh=mesh))
        model.add_material(
            MaterialDef(
                name="mat-left",
                material_type="linear_elastic",
                parameters={"young_modulus": 1000.0, "poisson_ratio": 0.25, "density": 1.0},
            )
        )
        model.add_material(
            MaterialDef(
                name="mat-right",
                material_type="linear_elastic",
                parameters={"young_modulus": 1000.0, "poisson_ratio": 0.25, "density": 1.0},
            )
        )
        model.add_section(
            SectionDef(
                name="sec-left",
                section_type="plane_stress",
                material_name="mat-left",
                region_name="left-set",
                scope_name="part-1",
                parameters={"thickness": 1.0},
            )
        )
        model.add_section(
            SectionDef(
                name="sec-right",
                section_type="plane_stress",
                material_name="mat-right",
                region_name="right-set",
                scope_name="part-1",
                parameters={"thickness": 1.0},
            )
        )
        model.add_boundary(BoundaryDef(name="bc-left", target_name="left", dof_values={"UX": 0.0}))
        model.add_boundary(BoundaryDef(name="bc-right", target_name="right", dof_values={"UX": 0.002}))
        model.add_boundary(BoundaryDef(name="bc-anchor", target_name="anchor", dof_values={"UY": 0.0}))
        model.add_output_request(
            OutputRequest(
                name="node-averaged",
                variables=(FIELD_KEY_S_AVG,),
                target_type="node_set",
                target_name="interface",
                position="NODE_AVERAGED",
            )
        )
        model.add_step(
            StepDef(
                name="step-static",
                procedure_type="static_linear",
                boundary_names=("bc-left", "bc-right", "bc-anchor"),
                output_request_names=("node-averaged",),
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-static",)))
        return model


if __name__ == "__main__":
    unittest.main()


