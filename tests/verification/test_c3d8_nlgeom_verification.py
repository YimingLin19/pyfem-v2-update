"""C3D8 solid nlgeom 数值验证测试。"""

from __future__ import annotations

import unittest

import numpy

from pyfem.compiler import Compiler
from pyfem.foundation.types import ElementLocation
from pyfem.io import InMemoryResultsWriter
from pyfem.kernel.elements import C3D8Runtime
from pyfem.kernel.materials import ElasticIsotropicRuntime
from pyfem.kernel.sections import SolidSectionRuntime
from pyfem.mesh import ElementRecord, Mesh, NodeRecord, Part
from pyfem.modeldb import BoundaryDef, JobDef, MaterialDef, ModelDB, OutputRequest, SectionDef, StepDef


class C3D8NlgeomVerificationTests(unittest.TestCase):
    """验证 C3D8 total_lagrangian 的基本数值正确性。"""

    def test_uniform_extension_matches_closed_form_nominal_reaction(self) -> None:
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
        total_right_reaction = float(
            reaction_field["part-1.n2"]["UX"]
            + reaction_field["part-1.n3"]["UX"]
            + reaction_field["part-1.n6"]["UX"]
            + reaction_field["part-1.n7"]["UX"]
        )
        lame_lambda = elastic_modulus * poisson_ratio / ((1.0 + poisson_ratio) * (1.0 - 2.0 * poisson_ratio))
        shear_modulus = elastic_modulus / (2.0 * (1.0 + poisson_ratio))
        green_lagrange_strain = applied_extension + 0.5 * applied_extension**2
        second_piola_stress = (lame_lambda + 2.0 * shear_modulus) * green_lagrange_strain
        expected_nominal_reaction = (1.0 + applied_extension) * second_piola_stress

        self.assertAlmostEqual(total_right_reaction, expected_nominal_reaction, delta=1.0e-10)

    def test_rigid_translation_patch_under_nlgeom_keeps_zero_stress_and_zero_internal_force(self) -> None:
        material = ElasticIsotropicRuntime(name="solid-mat", young_modulus=1000.0, poisson_ratio=0.25, density=2.5)
        section = SolidSectionRuntime(name="solid-sec", material_runtime=material)
        element = C3D8Runtime(
            location=ElementLocation(scope_name="part-1", element_name="e1"),
            coordinates=(
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (1.0, 1.0, 0.0),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0),
                (1.0, 0.0, 1.0),
                (1.0, 1.0, 1.0),
                (0.0, 1.0, 1.0),
            ),
            node_names=("n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8"),
            dof_indices=tuple(range(24)),
            section_runtime=section,
            material_runtime=material,
        )
        rigid_translation = (
            0.1,
            -0.2,
            0.05,
            0.1,
            -0.2,
            0.05,
            0.1,
            -0.2,
            0.05,
            0.1,
            -0.2,
            0.05,
            0.1,
            -0.2,
            0.05,
            0.1,
            -0.2,
            0.05,
            0.1,
            -0.2,
            0.05,
            0.1,
            -0.2,
            0.05,
        )
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
        for node_name, coordinates in (
            ("n1", (0.0, 0.0, 0.0)),
            ("n2", (1.0, 0.0, 0.0)),
            ("n3", (1.0, 1.0, 0.0)),
            ("n4", (0.0, 1.0, 0.0)),
            ("n5", (0.0, 0.0, 1.0)),
            ("n6", (1.0, 0.0, 1.0)),
            ("n7", (1.0, 1.0, 1.0)),
            ("n8", (0.0, 1.0, 1.0)),
        ):
            mesh.add_node(NodeRecord(name=node_name, coordinates=coordinates))
        mesh.add_element(
            ElementRecord(
                name="block-1",
                type_key="C3D8",
                node_names=("n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8"),
            )
        )
        mesh.add_node_set("left", ("n1", "n4", "n5", "n8"))
        mesh.add_node_set("right", ("n2", "n3", "n6", "n7"))
        mesh.add_node_set("all", ("n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8"))
        mesh.add_element_set("block-set", ("block-1",))

        model = ModelDB(name="c3d8-uniform-extension")
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
                section_type="solid",
                material_name="mat-1",
                region_name="block-set",
                scope_name="part-1",
                parameters={},
            )
        )
        model.add_boundary(BoundaryDef(name="bc-left-x", target_name="left", dof_values={"UX": 0.0}))
        model.add_boundary(BoundaryDef(name="bc-right-x", target_name="right", dof_values={"UX": right_displacement}))
        model.add_boundary(BoundaryDef(name="bc-all-yz", target_name="all", dof_values={"UY": 0.0, "UZ": 0.0}))
        model.add_output_request(OutputRequest(name="field-node", variables=("U", "RF"), target_type="model", position="NODE"))
        model.add_step(
            StepDef(
                name="step-static",
                procedure_type="static_nonlinear",
                boundary_names=("bc-left-x", "bc-right-x", "bc-all-yz"),
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
