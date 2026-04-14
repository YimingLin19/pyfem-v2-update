"""VTK exporter 基础测试。"""

from pathlib import Path
import unittest
from uuid import uuid4

from pyfem.io import (
    FIELD_KEY_S,
    FIELD_KEY_S_AVG,
    FIELD_KEY_S_IP,
    FIELD_KEY_S_REC,
    FIELD_KEY_S_VM_AVG,
    FIELD_KEY_U,
    InMemoryResultsWriter,
    POSITION_ELEMENT_CENTROID,
    POSITION_ELEMENT_NODAL,
    POSITION_INTEGRATION_POINT,
    POSITION_NODE,
    POSITION_NODE_AVERAGED,
    RESULT_SOURCE_AVERAGED,
    RESULT_SOURCE_DERIVED,
    RESULT_SOURCE_RECOVERED,
    ResultField,
    ResultFrame,
    ResultsSession,
    VtkExporter,
)
from pyfem.mesh import Assembly, ElementRecord, Mesh, NodeRecord, Part, PartInstance, RigidTransform
from pyfem.modeldb import ModelDB


class VtkExporterTests(unittest.TestCase):
    """验证 VTK exporter 的基础导出能力。"""

    def test_vtk_exporter_writes_semantic_arrays_for_results(self) -> None:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(1.0, 0.0)))
        mesh.add_element(ElementRecord(name="e1", type_key="B21", node_names=("n1", "n2")))
        part = Part(name="part-1", mesh=mesh)
        model = ModelDB(name="vtk-demo")
        model.add_part(part)

        writer = InMemoryResultsWriter()
        writer.open_session(ResultsSession(model_name="vtk-demo", procedure_name="step-1", step_name="step-1"))
        writer.write_frame(
            ResultFrame(
                frame_id=0,
                step_name="step-1",
                time=0.0,
                fields=(
                    ResultField(
                        name=FIELD_KEY_U,
                        position=POSITION_NODE,
                        values={"part-1.n1": {"UX": 0.0, "UY": 0.0}, "part-1.n2": {"UX": 0.1, "UY": -0.2}},
                    ),
                    ResultField(name=FIELD_KEY_S, position=POSITION_ELEMENT_CENTROID, values={"part-1.e1": 12.5}),
                    ResultField(
                        name=FIELD_KEY_S_IP,
                        position=POSITION_INTEGRATION_POINT,
                        values={"part-1.e1.ip1": {"S11": 8.0}},
                    ),
                    ResultField(
                        name=FIELD_KEY_S_REC,
                        position=POSITION_ELEMENT_NODAL,
                        values={"part-1.e1.n1": {"S11": 7.0}, "part-1.e1.n2": {"S11": 9.0}},
                        source_type=RESULT_SOURCE_RECOVERED,
                        metadata={"owner_element_keys": {"part-1.e1.n1": "part-1.e1", "part-1.e1.n2": "part-1.e1"}},
                    ),
                    ResultField(
                        name=FIELD_KEY_S_AVG,
                        position=POSITION_NODE_AVERAGED,
                        values={"part-1.n1": {"S11": 6.0}, "part-1.n2": {"S11": 5.0}},
                        source_type=RESULT_SOURCE_AVERAGED,
                        metadata={"base_target_keys": {"part-1.n1": "part-1.n1", "part-1.n2": "part-1.n2"}},
                    ),
                    ResultField(
                        name=FIELD_KEY_S_VM_AVG,
                        position=POSITION_NODE_AVERAGED,
                        values={"part-1.n1": {"MISES": 6.5}, "part-1.n2": {"MISES": 5.5}},
                        source_type=RESULT_SOURCE_DERIVED,
                        metadata={"base_target_keys": {"part-1.n1": "part-1.n1", "part-1.n2": "part-1.n2"}},
                    ),
                ),
            )
        )
        writer.close_session()

        target_path = Path("tests") / f"_tmp_vtk_{uuid4().hex}.vtk"
        try:
            VtkExporter().export(model=model, results_reader=writer, path=target_path)
            content = target_path.read_text(encoding="utf-8")
            self.assertIn("DATASET UNSTRUCTURED_GRID", content)
            self.assertIn("VECTORS RAW__U float", content)
            self.assertIn("SCALARS RAW__S float 1", content)
            self.assertIn("SCALARS RAW__S_IP__IP1__S11 float 1", content)
            self.assertIn("SCALARS RECOVERED__S_REC__N1__S11 float 1", content)
            self.assertIn("SCALARS RECOVERED__S_REC__N2__S11 float 1", content)
            self.assertIn("SCALARS AVERAGED__S_AVG__S11 float 1", content)
            self.assertIn("SCALARS DERIVED__S_VM_AVG__MISES float 1", content)
        finally:
            target_path.unlink(missing_ok=True)

    def test_vtk_exporter_uses_canonical_scope_geometry_for_multiple_instances(self) -> None:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(2.0, 0.0)))
        mesh.add_element(ElementRecord(name="e1", type_key="B21", node_names=("n1", "n2")))
        part = Part(name="beam-part", mesh=mesh)

        assembly = Assembly(name="assembly-1")
        assembly.add_instance(PartInstance(name="left", part_name="beam-part"))
        assembly.add_instance(
            PartInstance(name="right", part_name="beam-part", transform=RigidTransform(translation=(5.0, 0.0)))
        )

        model = ModelDB(name="vtk-assembly")
        model.add_part(part)
        model.set_assembly(assembly)

        writer = InMemoryResultsWriter()
        writer.open_session(ResultsSession(model_name="vtk-assembly", procedure_name="step-1", step_name="step-1"))
        writer.write_frame(
            ResultFrame(
                frame_id=0,
                step_name="step-1",
                time=0.0,
                fields=(
                    ResultField(
                        name=FIELD_KEY_U,
                        position=POSITION_NODE,
                        values={
                            "left.n1": {"UX": 0.0, "UY": 0.0},
                            "left.n2": {"UX": 0.0, "UY": 0.0},
                            "right.n1": {"UX": 0.0, "UY": 0.0},
                            "right.n2": {"UX": 0.0, "UY": 0.0},
                        },
                    ),
                    ResultField(
                        name=FIELD_KEY_S,
                        position=POSITION_ELEMENT_CENTROID,
                        values={"left.e1": 1.0, "right.e1": 2.0},
                    ),
                ),
            )
        )
        writer.close_session()

        target_path = Path("tests") / f"_tmp_vtk_{uuid4().hex}.vtk"
        try:
            VtkExporter().export(model=model, results_reader=writer, path=target_path)
            content = target_path.read_text(encoding="utf-8")
            self.assertIn("0 0 0", content)
            self.assertIn("2 0 0", content)
            self.assertIn("5 0 0", content)
            self.assertIn("7 0 0", content)
        finally:
            target_path.unlink(missing_ok=True)

    def test_vtk_exporter_skips_non_numeric_semantic_components(self) -> None:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(1.0, 0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n3", coordinates=(1.0, 1.0, 0.0)))
        mesh.add_node(NodeRecord(name="n4", coordinates=(0.0, 1.0, 0.0)))
        mesh.add_element(ElementRecord(name="e1", type_key="CPS4", node_names=("n1", "n2", "n3", "n4")))
        part = Part(name="part-1", mesh=mesh)
        model = ModelDB(name="vtk-semantic-filter")
        model.add_part(part)

        writer = InMemoryResultsWriter()
        writer.open_session(ResultsSession(model_name="vtk-semantic-filter", procedure_name="step-1", step_name="step-1"))
        writer.write_frame(
            ResultFrame(
                frame_id=0,
                step_name="step-1",
                time=0.0,
                fields=(
                    ResultField(
                        name="SECTION",
                        position=POSITION_ELEMENT_CENTROID,
                        values={
                            "part-1.e1": {
                                "nlgeom_active": False,
                                "nlgeom_mode": "linear_small_strain",
                                "strain_measure": "small_strain",
                                "stress_measure": "cauchy_small_strain",
                            }
                        },
                    ),
                ),
            )
        )
        writer.close_session()

        target_path = Path("tests") / f"_tmp_vtk_semantic_{uuid4().hex}.vtk"
        try:
            VtkExporter().export(model=model, results_reader=writer, path=target_path)
            content = target_path.read_text(encoding="utf-8")
            self.assertNotIn("LINEAR_SMALL_STRAIN", content)
            self.assertNotIn("STRAIN_MEASURE", content)
            self.assertNotIn("STRESS_MEASURE", content)
        finally:
            target_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
