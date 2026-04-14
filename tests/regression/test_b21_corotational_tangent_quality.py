"""B21 corotational 解析切线质量回归测试。"""

from __future__ import annotations

import math
import unittest
from types import MethodType

import numpy

from pyfem.compiler import Compiler
from pyfem.foundation.types import ElementLocation
from pyfem.io import InMemoryResultsWriter
from pyfem.kernel.elements import B21Runtime
from pyfem.kernel.materials import ElasticIsotropicRuntime
from pyfem.kernel.sections import BeamSectionRuntime
from pyfem.mesh import ElementRecord, Mesh, NodeRecord, Part
from pyfem.modeldb import BoundaryDef, JobDef, MaterialDef, ModelDB, NodalLoadDef, OutputRequest, SectionDef, StepDef


class B21CorotationalTangentQualityTests(unittest.TestCase):
    """验证 B21 corotational 解析切线与收敛质量。"""

    def test_analytic_tangent_matches_high_precision_numerical_tangent(self) -> None:
        element = self._build_element_runtime()
        displacement = numpy.asarray((0.05, -0.02, 0.18, -0.12, 0.65, 1.02), dtype=float)

        kinematics = element._build_corotational_kinematics(displacement)
        section_response = element._build_section_response(
            axial_response=element._build_ephemeral_axial_response(axial_extension=kinematics.axial_extension),
            local_rotation_i=kinematics.local_rotation_i,
            local_rotation_j=kinematics.local_rotation_j,
        )
        analytic_tangent = element._build_corotational_tangent(kinematics, section_response)
        numerical_tangent = element._build_corotational_numerical_tangent(displacement, relative_step=1.0e-9)

        self.assertTrue(numpy.allclose(analytic_tangent, numerical_tangent, atol=1.0e-3, rtol=2.0e-7))

    def test_rigid_body_rotation_tangent_remains_finite_and_matches_numerical_linearization(self) -> None:
        element = self._build_element_runtime()
        rotation = math.pi / 3.0
        length = 2.0
        displacement = numpy.asarray(
            (
                0.0,
                0.0,
                rotation,
                length * (math.cos(rotation) - 1.0),
                length * math.sin(rotation),
                rotation,
            ),
            dtype=float,
        )

        kinematics = element._build_corotational_kinematics(displacement)
        section_response = element._build_section_response(
            axial_response=element._build_ephemeral_axial_response(axial_extension=kinematics.axial_extension),
            local_rotation_i=kinematics.local_rotation_i,
            local_rotation_j=kinematics.local_rotation_j,
        )
        analytic_tangent = element._build_corotational_tangent(kinematics, section_response)
        numerical_tangent = element._build_corotational_numerical_tangent(displacement, relative_step=1.0e-9)
        residual = element._assemble_corotational_internal_force(kinematics, section_response.basic_force)

        self.assertTrue(numpy.all(numpy.isfinite(analytic_tangent)))
        self.assertTrue(numpy.allclose(residual, 0.0, atol=1.0e-8, rtol=1.0e-8))
        self.assertTrue(numpy.allclose(analytic_tangent, numerical_tangent, atol=1.0e-3, rtol=2.0e-7))

    def test_analytic_tangent_newton_convergence_is_not_worse_than_numerical_tangent(self) -> None:
        analytic_writer = self._run_nlgeom_step(self._build_tip_moment_benchmark_model(), use_numerical_tangent=False)
        numerical_writer = self._run_nlgeom_step(self._build_tip_moment_benchmark_model(), use_numerical_tangent=True)

        analytic_summary = analytic_writer.read_summary("step-static", "static_nonlinear_summary").data
        numerical_summary = numerical_writer.read_summary("step-static", "static_nonlinear_summary").data
        analytic_iterations = analytic_writer.read_history("step-static", "iteration_count").get_series()
        numerical_iterations = numerical_writer.read_history("step-static", "iteration_count").get_series()

        self.assertLessEqual(int(analytic_summary["cutback_count"]), int(numerical_summary["cutback_count"]))
        self.assertLessEqual(
            float(analytic_summary["average_iteration_per_increment"]),
            float(numerical_summary["average_iteration_per_increment"]) + 1.0e-12,
        )
        self.assertEqual(analytic_iterations, numerical_iterations)
        self.assertAlmostEqual(float(analytic_summary["load_factor"]), 1.0, delta=1.0e-12)
        self.assertAlmostEqual(float(numerical_summary["load_factor"]), 1.0, delta=1.0e-12)

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

    def _run_nlgeom_step(self, model: ModelDB, *, use_numerical_tangent: bool) -> InMemoryResultsWriter:
        compiled_model = Compiler().compile(model)
        if use_numerical_tangent:
            for runtime in compiled_model.element_runtimes.values():
                if isinstance(runtime, B21Runtime):
                    runtime._build_corotational_tangent = MethodType(
                        lambda self, kinematics, section_response: self._build_corotational_numerical_tangent(
                            kinematics.displacement_vector
                        ),
                        runtime,
                    )

        writer = InMemoryResultsWriter()
        compiled_model.get_step_runtime("step-static").run(writer)
        return writer

    def _build_tip_moment_benchmark_model(self) -> ModelDB:
        mesh = Mesh()
        total_length = 2.0
        num_elements = 16
        element_length = total_length / num_elements
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

        model = ModelDB(name="b21-corotational-tangent-quality")
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
        end_moment = 1.0e6 * 2.0e-4 * (math.pi / 2.0) / total_length
        model.add_boundary(BoundaryDef(name="bc-root", target_name="root", dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0}))
        model.add_nodal_load(NodalLoadDef(name="load-tip-moment", target_name="tip", components={"MZ": end_moment}))
        model.add_output_request(OutputRequest(name="field-node", variables=("U", "RF"), target_type="model", position="NODE"))
        model.add_step(
            StepDef(
                name="step-static",
                procedure_type="static_nonlinear",
                boundary_names=("bc-root",),
                nodal_load_names=("load-tip-moment",),
                output_request_names=("field-node",),
                parameters={
                    "max_increments": 32,
                    "initial_increment": 0.03125,
                    "min_increment": 0.0078125,
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


if __name__ == "__main__":
    unittest.main()
