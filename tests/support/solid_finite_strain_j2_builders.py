"""solid finite-strain J2 测试模型构造器。"""

from __future__ import annotations

from pyfem.io import FIELD_KEY_E_IP, FIELD_KEY_E_REC, FIELD_KEY_RF, FIELD_KEY_S_IP, FIELD_KEY_S_REC, FIELD_KEY_U
from pyfem.mesh import ElementRecord, Mesh, NodeRecord, Part
from pyfem.modeldb import BoundaryDef, JobDef, MaterialDef, ModelDB, OutputRequest, SectionDef, StepDef


def build_cps4_j2_model(
    *,
    model_name: str,
    nlgeom: bool,
    right_displacement: float,
    procedure_type: str = "static_nonlinear",
    include_material_fields: bool = False,
    initial_increment: float = 0.0625,
    min_increment: float = 0.015625,
    max_increments: int = 16,
    max_iterations: int = 20,
    tangent_mode: str = "consistent",
) -> ModelDB:
    """构造 CPS4 plane_strain + J2 的单步模型。"""

    mesh = Mesh()
    mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
    mesh.add_node(NodeRecord(name="n2", coordinates=(1.0, 0.0)))
    mesh.add_node(NodeRecord(name="n3", coordinates=(1.0, 1.0)))
    mesh.add_node(NodeRecord(name="n4", coordinates=(0.0, 1.0)))
    mesh.add_element(ElementRecord(name="plate-1", type_key="CPS4", node_names=("n1", "n2", "n3", "n4")))
    mesh.add_node_set("left", ("n1", "n4"))
    mesh.add_node_set("right", ("n2", "n3"))
    mesh.add_node_set("anchor", ("n1",))
    mesh.add_element_set("plate-set", ("plate-1",))

    model = ModelDB(name=model_name)
    model.add_part(Part(name="part-1", mesh=mesh))
    model.add_material(
        MaterialDef(
            name="mat-j2",
            material_type="j2_plasticity",
            parameters={
                "young_modulus": 200000.0,
                "poisson_ratio": 0.3,
                "yield_stress": 250.0,
                "hardening_modulus": 1000.0,
                "tangent_mode": tangent_mode,
            },
        )
    )
    model.add_section(
        SectionDef(
            name="sec-1",
            section_type="plane_strain",
            material_name="mat-j2",
            region_name="plate-set",
            scope_name="part-1",
            parameters={"thickness": 1.0},
        )
    )
    model.add_boundary(BoundaryDef(name="bc-left-x", target_name="left", dof_values={"UX": 0.0}))
    model.add_boundary(BoundaryDef(name="bc-right-x", target_name="right", dof_values={"UX": right_displacement}))
    model.add_boundary(BoundaryDef(name="bc-anchor-y", target_name="anchor", dof_values={"UY": 0.0}))
    output_request_names = _add_common_output_requests(model, include_material_fields=include_material_fields)
    model.add_step(
        StepDef(
            name="step-static",
            procedure_type=procedure_type,
            boundary_names=("bc-left-x", "bc-right-x", "bc-anchor-y"),
            output_request_names=output_request_names,
            parameters=_build_step_parameters(
                procedure_type=procedure_type,
                nlgeom=nlgeom,
                initial_increment=initial_increment,
                min_increment=min_increment,
                max_increments=max_increments,
                max_iterations=max_iterations,
            ),
        )
    )
    model.set_job(JobDef(name="job-1", step_names=("step-static",)))
    return model


def build_cps4_j2_multistep_model(
    *,
    model_name: str,
    nlgeom: bool,
    load_displacement: float = 0.004,
    tangent_mode: str = "consistent",
) -> ModelDB:
    """构造 CPS4 plane_strain + J2 的加载/卸载多步模型。"""

    mesh = Mesh()
    mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
    mesh.add_node(NodeRecord(name="n2", coordinates=(1.0, 0.0)))
    mesh.add_node(NodeRecord(name="n3", coordinates=(1.0, 1.0)))
    mesh.add_node(NodeRecord(name="n4", coordinates=(0.0, 1.0)))
    mesh.add_element(ElementRecord(name="plate-1", type_key="CPS4", node_names=("n1", "n2", "n3", "n4")))
    mesh.add_node_set("left", ("n1", "n4"))
    mesh.add_node_set("right", ("n2", "n3"))
    mesh.add_node_set("anchor", ("n1",))
    mesh.add_element_set("plate-set", ("plate-1",))

    model = ModelDB(name=model_name)
    model.add_part(Part(name="part-1", mesh=mesh))
    model.add_material(
        MaterialDef(
            name="mat-j2",
            material_type="j2_plasticity",
            parameters={
                "young_modulus": 200000.0,
                "poisson_ratio": 0.3,
                "yield_stress": 250.0,
                "hardening_modulus": 1000.0,
                "tangent_mode": tangent_mode,
            },
        )
    )
    model.add_section(
        SectionDef(
            name="sec-1",
            section_type="plane_strain",
            material_name="mat-j2",
            region_name="plate-set",
            scope_name="part-1",
            parameters={"thickness": 1.0},
        )
    )
    model.add_boundary(BoundaryDef(name="bc-left-x", target_name="left", dof_values={"UX": 0.0}))
    model.add_boundary(BoundaryDef(name="bc-right-load", target_name="right", dof_values={"UX": load_displacement}))
    model.add_boundary(BoundaryDef(name="bc-right-unload", target_name="right", dof_values={"UX": 0.0}))
    model.add_boundary(BoundaryDef(name="bc-anchor-y", target_name="anchor", dof_values={"UY": 0.0}))
    output_request_names = _add_common_output_requests(model, include_material_fields=False)
    model.add_step(
        StepDef(
            name="step-load",
            procedure_type="static_nonlinear",
            boundary_names=("bc-left-x", "bc-right-load", "bc-anchor-y"),
            output_request_names=output_request_names,
            parameters=_build_step_parameters(
                procedure_type="static_nonlinear",
                nlgeom=nlgeom,
                initial_increment=0.0625,
                min_increment=0.015625,
                max_increments=16,
                max_iterations=20,
            ),
        )
    )
    model.add_step(
        StepDef(
            name="step-unload",
            procedure_type="static_nonlinear",
            boundary_names=("bc-left-x", "bc-right-unload", "bc-anchor-y"),
            output_request_names=output_request_names,
            parameters=_build_step_parameters(
                procedure_type="static_nonlinear",
                nlgeom=nlgeom,
                initial_increment=0.0625,
                min_increment=0.015625,
                max_increments=16,
                max_iterations=20,
            ),
        )
    )
    model.set_job(JobDef(name="job-1", step_names=("step-load", "step-unload")))
    return model


def build_c3d8_j2_model(
    *,
    model_name: str,
    nlgeom: bool,
    right_displacement: float,
    procedure_type: str = "static_nonlinear",
    include_material_fields: bool = False,
    initial_increment: float = 0.0625,
    min_increment: float = 0.03125,
    max_increments: int = 16,
    max_iterations: int = 20,
    tangent_mode: str = "consistent",
) -> ModelDB:
    """构造 C3D8 + J2 的单步模型。"""

    mesh = _build_c3d8_mesh()
    model = ModelDB(name=model_name)
    model.add_part(Part(name="part-1", mesh=mesh))
    model.add_material(
        MaterialDef(
            name="mat-j2",
            material_type="j2_plasticity",
            parameters={
                "young_modulus": 200000.0,
                "poisson_ratio": 0.3,
                "yield_stress": 250.0,
                "hardening_modulus": 1000.0,
                "tangent_mode": tangent_mode,
            },
        )
    )
    model.add_section(
        SectionDef(
            name="sec-1",
            section_type="solid",
            material_name="mat-j2",
            region_name="block-set",
            scope_name="part-1",
            parameters={},
        )
    )
    model.add_boundary(BoundaryDef(name="bc-left-fix", target_name="left", dof_values={"UX": 0.0, "UY": 0.0, "UZ": 0.0}))
    model.add_boundary(BoundaryDef(name="bc-right-ux", target_name="right", dof_values={"UX": right_displacement}))
    output_request_names = _add_common_output_requests(model, include_material_fields=include_material_fields)
    model.add_step(
        StepDef(
            name="step-static",
            procedure_type=procedure_type,
            boundary_names=("bc-left-fix", "bc-right-ux"),
            output_request_names=output_request_names,
            parameters=_build_step_parameters(
                procedure_type=procedure_type,
                nlgeom=nlgeom,
                initial_increment=initial_increment,
                min_increment=min_increment,
                max_increments=max_increments,
                max_iterations=max_iterations,
            ),
        )
    )
    model.set_job(JobDef(name="job-1", step_names=("step-static",)))
    return model


def build_c3d8_j2_multistep_model(
    *,
    model_name: str,
    nlgeom: bool,
    load_displacement: float = 0.004,
    tangent_mode: str = "consistent",
) -> ModelDB:
    """构造 C3D8 + J2 的加载/卸载多步模型。"""

    mesh = _build_c3d8_mesh()
    model = ModelDB(name=model_name)
    model.add_part(Part(name="part-1", mesh=mesh))
    model.add_material(
        MaterialDef(
            name="mat-j2",
            material_type="j2_plasticity",
            parameters={
                "young_modulus": 200000.0,
                "poisson_ratio": 0.3,
                "yield_stress": 250.0,
                "hardening_modulus": 1000.0,
                "tangent_mode": tangent_mode,
            },
        )
    )
    model.add_section(
        SectionDef(
            name="sec-1",
            section_type="solid",
            material_name="mat-j2",
            region_name="block-set",
            scope_name="part-1",
            parameters={},
        )
    )
    model.add_boundary(BoundaryDef(name="bc-left-fix", target_name="left", dof_values={"UX": 0.0, "UY": 0.0, "UZ": 0.0}))
    model.add_boundary(BoundaryDef(name="bc-right-load", target_name="right", dof_values={"UX": load_displacement}))
    model.add_boundary(BoundaryDef(name="bc-right-unload", target_name="right", dof_values={"UX": 0.0}))
    output_request_names = _add_common_output_requests(model, include_material_fields=False)
    model.add_step(
        StepDef(
            name="step-load",
            procedure_type="static_nonlinear",
            boundary_names=("bc-left-fix", "bc-right-load"),
            output_request_names=output_request_names,
            parameters=_build_step_parameters(
                procedure_type="static_nonlinear",
                nlgeom=nlgeom,
                initial_increment=0.0625,
                min_increment=0.03125,
                max_increments=16,
                max_iterations=20,
            ),
        )
    )
    model.add_step(
        StepDef(
            name="step-unload",
            procedure_type="static_nonlinear",
            boundary_names=("bc-left-fix", "bc-right-unload"),
            output_request_names=output_request_names,
            parameters=_build_step_parameters(
                procedure_type="static_nonlinear",
                nlgeom=nlgeom,
                initial_increment=0.0625,
                min_increment=0.03125,
                max_increments=16,
                max_iterations=20,
            ),
        )
    )
    model.set_job(JobDef(name="job-1", step_names=("step-load", "step-unload")))
    return model


def _add_common_output_requests(model: ModelDB, *, include_material_fields: bool) -> tuple[str, ...]:
    model.add_output_request(OutputRequest(name="field-node", variables=(FIELD_KEY_U, FIELD_KEY_RF), target_type="model", position="NODE"))
    output_request_names = ["field-node"]
    if include_material_fields:
        model.add_output_request(
            OutputRequest(
                name="field-ip",
                variables=(FIELD_KEY_E_IP, FIELD_KEY_S_IP),
                target_type="model",
                position="INTEGRATION_POINT",
            )
        )
        model.add_output_request(
            OutputRequest(
                name="field-rec",
                variables=(FIELD_KEY_E_REC, FIELD_KEY_S_REC),
                target_type="model",
                position="ELEMENT_NODAL",
            )
        )
        output_request_names.extend(("field-ip", "field-rec"))
    return tuple(output_request_names)


def _build_step_parameters(
    *,
    procedure_type: str,
    nlgeom: bool,
    initial_increment: float,
    min_increment: float,
    max_increments: int,
    max_iterations: int,
) -> dict[str, object]:
    if procedure_type != "static_nonlinear":
        return {}
    return {
        "max_increments": max_increments,
        "initial_increment": initial_increment,
        "min_increment": min_increment,
        "max_iterations": max_iterations,
        "residual_tolerance": 1.0e-8,
        "displacement_tolerance": 1.0e-8,
        "allow_cutback": True,
        "line_search": False,
        "nlgeom": nlgeom,
    }


def _build_c3d8_mesh() -> Mesh:
    mesh = Mesh()
    mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0, 0.0)))
    mesh.add_node(NodeRecord(name="n2", coordinates=(1.0, 0.0, 0.0)))
    mesh.add_node(NodeRecord(name="n3", coordinates=(1.0, 1.0, 0.0)))
    mesh.add_node(NodeRecord(name="n4", coordinates=(0.0, 1.0, 0.0)))
    mesh.add_node(NodeRecord(name="n5", coordinates=(0.0, 0.0, 1.0)))
    mesh.add_node(NodeRecord(name="n6", coordinates=(1.0, 0.0, 1.0)))
    mesh.add_node(NodeRecord(name="n7", coordinates=(1.0, 1.0, 1.0)))
    mesh.add_node(NodeRecord(name="n8", coordinates=(0.0, 1.0, 1.0)))
    mesh.add_element(
        ElementRecord(name="block-1", type_key="C3D8", node_names=("n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8"))
    )
    mesh.add_node_set("left", ("n1", "n4", "n5", "n8"))
    mesh.add_node_set("right", ("n2", "n3", "n6", "n7"))
    mesh.add_element_set("block-set", ("block-1",))
    return mesh
