"""CPS4 solid nlgeom 数值验证测试。"""

from __future__ import annotations

import unittest

import numpy

from pyfem.compiler import Compiler
from pyfem.foundation.types import ElementLocation
from pyfem.io import InMemoryResultsWriter
from pyfem.kernel.elements import CPS4Runtime
from pyfem.kernel.materials import ElasticIsotropicRuntime
from pyfem.kernel.sections import PlaneStrainSectionRuntime, PlaneStressSectionRuntime
from pyfem.mesh import ElementRecord, Mesh, NodeRecord, Part
from pyfem.modeldb import BoundaryDef, JobDef, MaterialDef, ModelDB, OutputRequest, SectionDef, StepDef


class CPS4NlgeomVerificationTests(unittest.TestCase):
    """验证 CPS4 total_lagrangian 的基本数值正确性。"""

    def test_uniform_plane_strain_extension_matches_closed_form_nominal_reaction(self) -> None:
        applied_extension = 0.2
        elastic_modulus = 1000.0
        poisson_ratio = 0.25
        writer = self._run_uniform_extension_step(
            right_displacement=applied_extension,
            young_modulus=elastic_modulus,
            poisson_ratio=poisson_ratio,
        )

        frame = writer.read_step("step-static").frames[-1]
        reaction_field = frame.get_field("RF").values
        total_right_reaction = float(reaction_field["part-1.n2"]["UX"] + reaction_field["part-1.n3"]["UX"])
        green_lagrange_strain = applied_extension + 0.5 * applied_extension**2
        second_piola_stress = (
            elastic_modulus
            * (1.0 - poisson_ratio)
            / ((1.0 + poisson_ratio) * (1.0 - 2.0 * poisson_ratio))
            * green_lagrange_strain
        )
        expected_nominal_reaction = (1.0 + applied_extension) * second_piola_stress

        self.assertAlmostEqual(total_right_reaction, expected_nominal_reaction, delta=1.0e-10)

    def test_rigid_translation_patch_under_nlgeom_keeps_zero_stress_and_zero_internal_force(self) -> None:
        material = ElasticIsotropicRuntime(name="plane-mat", young_modulus=1200.0, poisson_ratio=0.25, density=3.0)
        section = PlaneStressSectionRuntime(name="plane-sec", material_runtime=material, thickness=2.0)
        element = CPS4Runtime(
            location=ElementLocation(scope_name="part-1", element_name="e2"),
            coordinates=((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
            node_names=("n1", "n2", "n3", "n4"),
            dof_indices=tuple(range(8)),
            section_runtime=section,
            material_runtime=material,
        )
        rigid_translation = (0.3, -0.2, 0.3, -0.2, 0.3, -0.2, 0.3, -0.2)
        state = {"analysis_flags": {"nlgeom": True}, "integration_points": {}, "time": 1.0}

        contribution = element.tangent_residual(displacement=rigid_translation, state=state)
        residual = numpy.asarray(contribution.residual, dtype=float)
        output = element.output(displacement=rigid_translation, state=state)

        self.assertTrue(numpy.allclose(residual, 0.0, atol=1.0e-10, rtol=1.0e-10))
        self.assertTrue(numpy.allclose(output["strain"], 0.0, atol=1.0e-12, rtol=1.0e-12))
        self.assertTrue(numpy.allclose(output["stress"], 0.0, atol=1.0e-10, rtol=1.0e-10))
        self.assertEqual(output["nlgeom_mode"], "total_lagrangian")

    def _run_uniform_extension_step(
        self,
        *,
        right_displacement: float,
        young_modulus: float,
        poisson_ratio: float,
    ) -> InMemoryResultsWriter:
        mesh = Mesh()
        mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
        mesh.add_node(NodeRecord(name="n2", coordinates=(1.0, 0.0)))
        mesh.add_node(NodeRecord(name="n3", coordinates=(1.0, 1.0)))
        mesh.add_node(NodeRecord(name="n4", coordinates=(0.0, 1.0)))
        mesh.add_element(ElementRecord(name="plate-1", type_key="CPS4", node_names=("n1", "n2", "n3", "n4")))
        mesh.add_node_set("left", ("n1", "n4"))
        mesh.add_node_set("right", ("n2", "n3"))
        mesh.add_node_set("bottom", ("n1", "n2"))
        mesh.add_node_set("top", ("n3", "n4"))
        mesh.add_element_set("plate-set", ("plate-1",))

        model = ModelDB(name="cps4-uniform-extension")
        model.add_part(Part(name="part-1", mesh=mesh))
        model.add_material(
            MaterialDef(
                name="mat-1",
                material_type="linear_elastic",
                parameters={"young_modulus": young_modulus, "poisson_ratio": poisson_ratio},
            )
        )
        model.add_section(
            SectionDef(
                name="sec-1",
                section_type="plane_strain",
                material_name="mat-1",
                region_name="plate-set",
                scope_name="part-1",
                parameters={"thickness": 1.0},
            )
        )
        model.add_boundary(BoundaryDef(name="bc-left-x", target_name="left", dof_values={"UX": 0.0}))
        model.add_boundary(BoundaryDef(name="bc-right-x", target_name="right", dof_values={"UX": right_displacement}))
        model.add_boundary(BoundaryDef(name="bc-bottom-y", target_name="bottom", dof_values={"UY": 0.0}))
        model.add_boundary(BoundaryDef(name="bc-top-y", target_name="top", dof_values={"UY": 0.0}))
        model.add_output_request(OutputRequest(name="field-node", variables=("U", "RF"), target_type="model", position="NODE"))
        model.add_step(
            StepDef(
                name="step-static",
                procedure_type="static_nonlinear",
                boundary_names=("bc-left-x", "bc-right-x", "bc-bottom-y", "bc-top-y"),
                output_request_names=("field-node",),
                parameters={
                    "max_increments": 8,
                    "initial_increment": 0.125,
                    "min_increment": 0.125,
                    "max_iterations": 20,
                    "residual_tolerance": 1.0e-10,
                    "displacement_tolerance": 1.0e-10,
                    "allow_cutback": True,
                    "line_search": False,
                    "nlgeom": True,
                },
            )
        )
        model.set_job(JobDef(name="job-1", step_names=("step-static",)))

        compiled_model = Compiler().compile(model)
        writer = InMemoryResultsWriter()
        compiled_model.get_step_runtime("step-static").run(writer)
        return writer


if __name__ == "__main__":
    unittest.main()
