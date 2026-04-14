"""B21 corotational 几何非线性验证测试。"""

from __future__ import annotations

import math
import unittest

import numpy

from pyfem.compiler import Compiler
from pyfem.foundation.types import ElementLocation
from pyfem.io import InMemoryResultsWriter
from pyfem.kernel.elements import B21Runtime
from pyfem.kernel.materials import ElasticIsotropicRuntime
from pyfem.kernel.sections import BeamSectionRuntime
from pyfem.mesh import ElementRecord, Mesh, NodeRecord, Part
from pyfem.modeldb import BoundaryDef, JobDef, MaterialDef, ModelDB, NodalLoadDef, OutputRequest, SectionDef, StepDef


class B21CorotationalVerificationTests(unittest.TestCase):
    """验证 B21 corotational 几何非线性的关键数值行为。"""

    def test_rigid_body_rotation_does_not_generate_spurious_strain_or_internal_force(self) -> None:
        element = self._build_element_runtime()
        rotation = math.pi / 2.0
        length = 2.0
        displacement = (
            0.0,
            0.0,
            rotation,
            length * (math.cos(rotation) - 1.0),
            length * math.sin(rotation),
            rotation,
        )

        contribution = element.tangent_residual(
            displacement=displacement,
            state={"analysis_flags": {"nlgeom": True}, "material": element.material_runtime.allocate_state()},
        )
        output = element.output(
            displacement=displacement,
            state={"analysis_flags": {"nlgeom": True}, "material": element.material_runtime.allocate_state()},
        )

        self.assertTrue(numpy.allclose(contribution.residual, 0.0, atol=1.0e-8, rtol=1.0e-8))
        self.assertAlmostEqual(float(output["axial_strain"]), 0.0, delta=1.0e-10)
        self.assertAlmostEqual(float(output["axial_force"]), 0.0, delta=1.0e-8)
        self.assertAlmostEqual(float(output["end_moment_i"]), 0.0, delta=1.0e-8)
        self.assertAlmostEqual(float(output["end_moment_j"]), 0.0, delta=1.0e-8)

    def test_small_displacement_limit_matches_linear_beam_response(self) -> None:
        linear_writer = self._run_step(self._build_linear_tip_force_model(load_value=-1.0e-3, num_elements=4))
        nonlinear_writer = self._run_step(self._build_nlgeom_tip_force_model(load_value=-1.0e-3, num_elements=4))

        linear_tip = linear_writer.read_step("step-static").frames[-1].get_field("U").values["part-1.n5"]
        nonlinear_tip = nonlinear_writer.read_step("step-static").frames[-1].get_field("U").values["part-1.n5"]

        self.assertAlmostEqual(float(linear_tip["UX"]), float(nonlinear_tip["UX"]), delta=1.0e-10)
        self.assertAlmostEqual(float(linear_tip["UY"]), float(nonlinear_tip["UY"]), delta=1.0e-8)
        self.assertAlmostEqual(float(linear_tip["RZ"]), float(nonlinear_tip["RZ"]), delta=1.0e-8)

    def test_tip_end_moment_benchmark_matches_large_rotation_circular_arc_solution(self) -> None:
        writer = self._run_step(self._build_nlgeom_tip_moment_model())
        tip_field = writer.read_step("step-static").frames[-1].get_field("U").values["part-1.n17"]
        summary = writer.read_summary("step-static", "static_nonlinear_summary").data

        target_rotation = math.pi / 2.0
        length = 2.0
        curvature = target_rotation / length
        expected_x = math.sin(target_rotation) / curvature
        expected_y = (1.0 - math.cos(target_rotation)) / curvature

        self.assertAlmostEqual(float(tip_field["UX"]), expected_x - length, delta=2.0e-3)
        self.assertAlmostEqual(float(tip_field["UY"]), expected_y, delta=2.0e-3)
        self.assertAlmostEqual(float(tip_field["RZ"]), target_rotation, delta=1.0e-8)
        self.assertTrue(bool(summary["nlgeom"]))
        self.assertEqual(float(summary["load_factor"]), 1.0)

    def _build_element_runtime(self) -> B21Runtime:
        material = ElasticIsotropicRuntime(
            name="beam-mat",
            young_modulus=1.0e6,
            poisson_ratio=0.3,
            density=4.0,
        )
        section = BeamSectionRuntime(
            name="beam-sec",
            material_runtime=material,
            area=0.03,
            moment_inertia_z=2.0e-4,
        )
        return B21Runtime(
            location=ElementLocation(scope_name="part-1", element_name="beam-1"),
            coordinates=((0.0, 0.0), (2.0, 0.0)),
            node_names=("n1", "n2"),
            dof_indices=tuple(range(6)),
            section_runtime=section,
            material_runtime=material,
        )

    def _run_step(self, model: ModelDB) -> InMemoryResultsWriter:
        compiled_model = Compiler().compile(model)
        writer = InMemoryResultsWriter()
        compiled_model.get_step_runtime("step-static").run(writer)
        return writer

    def _build_linear_tip_force_model(self, *, load_value: float, num_elements: int) -> ModelDB:
        model = self._build_base_beam_model(model_name="beam-linear-small", num_elements=num_elements)
        model.add_boundary(BoundaryDef(name="bc-root", target_name="root", dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0}))
        model.add_nodal_load(NodalLoadDef(name="load-tip", target_name="tip", components={"FY": load_value}))
        model.add_output_request(OutputRequest(name="field-node", variables=("U", "RF"), target_type="model", position="NODE"))
        model.add_step(
            StepDef(
                name="step-static",
                procedure_type="static_linear",
                boundary_names=("bc-root",),
                nodal_load_names=("load-tip",),
                output_request_names=("field-node",),
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-static",)))
        return model

    def _build_nlgeom_tip_force_model(self, *, load_value: float, num_elements: int) -> ModelDB:
        model = self._build_linear_tip_force_model(load_value=load_value, num_elements=num_elements)
        step = model.steps["step-static"]
        step.procedure_type = "static_nonlinear"
        step.parameters = {
            "max_increments": 8,
            "initial_increment": 0.25,
            "min_increment": 0.0625,
            "max_iterations": 30,
            "residual_tolerance": 1.0e-9,
            "displacement_tolerance": 1.0e-9,
            "allow_cutback": True,
            "line_search": False,
            "nlgeom": True,
        }
        return model

    def _build_nlgeom_tip_moment_model(self) -> ModelDB:
        model = self._build_base_beam_model(model_name="beam-nlgeom-tip-moment", num_elements=16)
        elastic_modulus = 1.0e6
        inertia = 2.0e-4
        length = 2.0
        target_rotation = math.pi / 2.0
        end_moment = elastic_modulus * inertia * target_rotation / length

        model.add_boundary(BoundaryDef(name="bc-root", target_name="root", dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0}))
        model.add_nodal_load(NodalLoadDef(name="load-tip-moment", target_name="tip", components={"MZ": end_moment}))
        model.add_output_request(OutputRequest(name="field-node", variables=("U", "RF"), target_type="model", position="NODE"))
        model.add_output_request(OutputRequest(name="history-time", variables=("TIME",), target_type="model", position="GLOBAL_HISTORY"))
        model.add_step(
            StepDef(
                name="step-static",
                procedure_type="static_nonlinear",
                boundary_names=("bc-root",),
                nodal_load_names=("load-tip-moment",),
                output_request_names=("field-node", "history-time"),
                parameters={
                    "max_increments": 12,
                    "initial_increment": 0.125,
                    "min_increment": 0.015625,
                    "max_iterations": 40,
                    "residual_tolerance": 1.0e-9,
                    "displacement_tolerance": 1.0e-9,
                    "allow_cutback": True,
                    "line_search": False,
                    "nlgeom": True,
                },
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-static",)))
        return model

    def _build_base_beam_model(self, *, model_name: str, num_elements: int) -> ModelDB:
        mesh = Mesh()
        length = 2.0
        element_length = length / float(num_elements)
        node_names: list[str] = []
        element_names: list[str] = []
        for node_index in range(num_elements + 1):
            node_name = f"n{node_index + 1}"
            node_names.append(node_name)
            mesh.add_node(NodeRecord(name=node_name, coordinates=(float(node_index) * element_length, 0.0)))
        for element_index in range(num_elements):
            element_name = f"beam-{element_index + 1}"
            element_names.append(element_name)
            mesh.add_element(
                ElementRecord(
                    name=element_name,
                    type_key="B21",
                    node_names=(node_names[element_index], node_names[element_index + 1]),
                )
            )
        mesh.add_node_set("root", (node_names[0],))
        mesh.add_node_set("tip", (node_names[-1],))
        mesh.add_element_set("beam-set", tuple(element_names))

        model = ModelDB(name=model_name)
        model.add_part(Part(name="part-1", mesh=mesh))
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
        return model


if __name__ == "__main__":
    unittest.main()
