"""共享测试模型构造辅助函数。"""

from __future__ import annotations

from pyfem.compiler import CompiledModel, Compiler
from pyfem.io import FIELD_KEY_FREQUENCY, FIELD_KEY_TIME, InMemoryResultsWriter
from pyfem.mesh import (
    Assembly,
    ElementRecord,
    Mesh,
    NodeRecord,
    Orientation,
    Part,
    PartInstance,
    RigidTransform,
    Surface,
    SurfaceFacet,
)
from pyfem.modeldb import (
    BoundaryDef,
    DistributedLoadDef,
    JobDef,
    MaterialDef,
    ModelDB,
    NodalLoadDef,
    OutputRequest,
    SectionDef,
    StepDef,
)


def run_step(model: ModelDB, step_name: str) -> tuple[CompiledModel, InMemoryResultsWriter]:
    """编译模型并执行单个步骤。"""

    compiled_model = Compiler().compile(model)
    writer = InMemoryResultsWriter()
    compiled_model.get_step_runtime(step_name).run(writer)
    return compiled_model, writer


def run_job(model: ModelDB) -> tuple[CompiledModel, InMemoryResultsWriter]:
    """按作业顺序编译并执行全部步骤。"""

    compiled_model = Compiler().compile(model)
    writer = InMemoryResultsWriter()
    step_names = tuple(model.steps.keys()) if model.job is None else model.job.step_names
    for step_name in step_names:
        compiled_model.get_step_runtime(step_name).run(writer)
    return compiled_model, writer


def build_static_beam_benchmark_model() -> ModelDB:
    """构造 B21 静力 benchmark 模型。"""

    model = _build_base_beam_model(model_name="beam-static-benchmark")
    model.add_boundary(BoundaryDef(name="bc-root", target_name="root", dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0}))
    model.add_nodal_load(NodalLoadDef(name="load-tip", target_name="tip", components={"FY": -12.0}))
    model.add_output_request(OutputRequest(name="field-node-static", variables=("U", "RF"), target_type="model", position="NODE"))
    model.add_output_request(
        OutputRequest(
            name="field-element-static",
            variables=("S", "E", "SECTION"),
            target_type="model",
            position="ELEMENT_CENTROID",
        )
    )
    model.add_output_request(OutputRequest(name="history-static", variables=(FIELD_KEY_TIME,), target_type="model", position="GLOBAL_HISTORY"))
    model.add_step(
        StepDef(
            name="step-static",
            procedure_type="static_linear",
            boundary_names=("bc-root",),
            nodal_load_names=("load-tip",),
            output_request_names=("field-node-static", "field-element-static", "history-static"),
        )
    )
    model.set_job(JobDef(name="job-1", step_names=("step-static",)))
    return model


def build_modal_beam_benchmark_model() -> ModelDB:
    """构造 B21 模态 benchmark 模型。"""

    model = _build_base_beam_model(model_name="beam-modal-benchmark")
    model.add_boundary(BoundaryDef(name="bc-root", target_name="root", dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0}))
    model.add_boundary(BoundaryDef(name="bc-guide", target_name="tip", dof_values={"UY": 0.0, "RZ": 0.0}))
    model.add_output_request(OutputRequest(name="field-modal", variables=("MODE_SHAPE",), target_type="model", position="NODE"))
    model.add_output_request(
        OutputRequest(name="history-modal", variables=(FIELD_KEY_FREQUENCY,), target_type="model", position="GLOBAL_HISTORY")
    )
    model.add_step(
        StepDef(
            name="step-modal",
            procedure_type="modal",
            boundary_names=("bc-root", "bc-guide"),
            output_request_names=("field-modal", "history-modal"),
            parameters={"num_modes": 1},
        )
    )
    model.set_job(JobDef(name="job-1", step_names=("step-modal",)))
    return model


def build_dynamic_beam_benchmark_model() -> ModelDB:
    """构造 B21 隐式动力学 benchmark 模型。"""

    model = _build_base_beam_model(model_name="beam-dynamic-benchmark")
    model.add_boundary(BoundaryDef(name="bc-root", target_name="root", dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0}))
    model.add_boundary(BoundaryDef(name="bc-guide", target_name="tip", dof_values={"UY": 0.0, "RZ": 0.0}))
    model.add_output_request(OutputRequest(name="field-dynamic", variables=("U",), target_type="model", position="NODE"))
    model.add_output_request(OutputRequest(name="history-dynamic", variables=(FIELD_KEY_TIME,), target_type="model", position="GLOBAL_HISTORY"))
    model.add_step(
        StepDef(
            name="step-dynamic",
            procedure_type="implicit_dynamic",
            boundary_names=("bc-root", "bc-guide"),
            output_request_names=("field-dynamic", "history-dynamic"),
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


def build_multi_step_beam_model() -> ModelDB:
    """构造 static / modal / dynamic 多步结果主线模型。"""

    model = _build_base_beam_model(model_name="beam-multistep-regression")
    model.add_boundary(BoundaryDef(name="bc-root", target_name="root", dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0}))
    model.add_boundary(BoundaryDef(name="bc-guide", target_name="tip", dof_values={"UY": 0.0, "RZ": 0.0}))
    model.add_nodal_load(NodalLoadDef(name="load-tip", target_name="tip", components={"FY": -12.0}))

    model.add_output_request(OutputRequest(name="field-static", variables=("U", "RF"), target_type="model", position="NODE"))
    model.add_output_request(OutputRequest(name="history-static", variables=(FIELD_KEY_TIME,), target_type="model", position="GLOBAL_HISTORY"))
    model.add_output_request(OutputRequest(name="field-modal", variables=("MODE_SHAPE",), target_type="model", position="NODE"))
    model.add_output_request(
        OutputRequest(name="history-modal", variables=(FIELD_KEY_FREQUENCY,), target_type="model", position="GLOBAL_HISTORY")
    )
    model.add_output_request(OutputRequest(name="field-dynamic", variables=("U",), target_type="model", position="NODE"))
    model.add_output_request(OutputRequest(name="history-dynamic", variables=(FIELD_KEY_TIME,), target_type="model", position="GLOBAL_HISTORY"))

    model.add_step(
        StepDef(
            name="step-static",
            procedure_type="static_linear",
            boundary_names=("bc-root",),
            nodal_load_names=("load-tip",),
            output_request_names=("field-static", "history-static"),
        )
    )
    model.add_step(
        StepDef(
            name="step-modal",
            procedure_type="modal",
            boundary_names=("bc-root", "bc-guide"),
            output_request_names=("field-modal", "history-modal"),
            parameters={"num_modes": 1},
        )
    )
    model.add_step(
        StepDef(
            name="step-dynamic",
            procedure_type="implicit_dynamic",
            boundary_names=("bc-root", "bc-guide"),
            output_request_names=("field-dynamic", "history-dynamic"),
            parameters={
                "time_step": 0.0005,
                "total_time": 0.002,
                "beta": 0.25,
                "gamma": 0.5,
                "initial_displacement": {"part-1.n2.UX": 0.01},
            },
        )
    )
    model.set_job(JobDef(name="job-1", step_names=("step-static", "step-modal", "step-dynamic")))
    return model


def build_dual_instance_beam_model(*, boundary_scope_name: str = "left") -> ModelDB:
    """构造双实例 B21 作用域语义模型。"""

    mesh = Mesh()
    mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
    mesh.add_node(NodeRecord(name="n2", coordinates=(2.0, 0.0)))
    mesh.add_element(ElementRecord(name="beam-1", type_key="B21", node_names=("n1", "n2")))
    mesh.add_node_set("root", ("n1",))
    mesh.add_node_set("tip", ("n2",))
    mesh.add_element_set("beam-set", ("beam-1",))

    model = ModelDB(name="dual-instance-beam")
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
    assembly.add_instance(PartInstance(name="right", part_name="beam-part", transform=RigidTransform(translation=(5.0, 0.0))))
    model.set_assembly(assembly)

    model.add_boundary(BoundaryDef(name="bc-left-root", target_name="root", scope_name=boundary_scope_name, dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0}))
    model.add_boundary(BoundaryDef(name="bc-right-root", target_name="root", scope_name="right", dof_values={"UX": 0.0, "UY": 0.0, "RZ": 0.0}))
    model.add_nodal_load(NodalLoadDef(name="load-right-tip", target_name="tip", scope_name="right", components={"FY": -12.0}))
    model.add_output_request(OutputRequest(name="field-u", variables=("U",), target_type="model", position="NODE"))
    model.add_step(
        StepDef(
            name="step-static",
            procedure_type="static_linear",
            boundary_names=("bc-left-root", "bc-right-root"),
            nodal_load_names=("load-right-tip",),
            output_request_names=("field-u",),
        )
    )
    model.set_job(JobDef(name="job-1", step_names=("step-static",)))
    return model


def build_rotated_beam_assembly_model(transform: RigidTransform | None = None) -> ModelDB:
    """构造带旋转实例与方向定义的装配模型。"""

    mesh = Mesh()
    mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
    mesh.add_node(NodeRecord(name="n2", coordinates=(2.0, 0.0)))
    mesh.add_element(ElementRecord(name="beam-1", type_key="B21", node_names=("n1", "n2"), orientation_name="ori-1"))
    mesh.add_node_set("root", ("n1",))
    mesh.add_node_set("tip", ("n2",))
    mesh.add_element_set("beam-set", ("beam-1",))
    mesh.add_orientation(Orientation(name="ori-1", axis_1=(1.0, 0.0), axis_2=(0.0, 1.0)))

    model = ModelDB(name="rotated-beam-assembly")
    model.add_part(Part(name="beam-part", mesh=mesh))

    assembly = Assembly(name="assembly-1")
    assembly.add_instance(PartInstance(name="left", part_name="beam-part"))
    assembly.add_instance(
        PartInstance(
            name="right",
            part_name="beam-part",
            transform=transform
            if transform is not None
            else RigidTransform(rotation=((0.0, -1.0), (1.0, 0.0)), translation=(3.0, 0.0)),
        )
    )
    model.set_assembly(assembly)
    return model


def build_rotated_instance_cps4_solver_model() -> ModelDB:
    """构造旋转实例 CPS4 solver 级回归模型。"""

    mesh = Mesh()
    mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
    mesh.add_node(NodeRecord(name="n2", coordinates=(2.0, 0.0)))
    mesh.add_node(NodeRecord(name="n3", coordinates=(2.0, 1.0)))
    mesh.add_node(NodeRecord(name="n4", coordinates=(0.0, 1.0)))
    mesh.add_element(ElementRecord(name="plate-1", type_key="CPS4", node_names=("n1", "n2", "n3", "n4")))
    mesh.add_node_set("left", ("n1", "n4"))
    mesh.add_node_set("right", ("n2", "n3"))
    mesh.add_node_set("anchor", ("n1",))
    mesh.add_element_set("plate-set", ("plate-1",))

    model = ModelDB(name="rotated-instance-cps4")
    model.add_part(Part(name="plate-part", mesh=mesh))
    model.add_material(
        MaterialDef(
            name="mat-1",
            material_type="linear_elastic",
            parameters={"young_modulus": 1000.0, "poisson_ratio": 0.25, "density": 3.0},
        )
    )
    model.add_section(
        SectionDef(
            name="sec-1",
            section_type="plane_stress",
            material_name="mat-1",
            region_name="plate-set",
            parameters={"thickness": 1.0},
        )
    )

    assembly = Assembly(name="assembly-1")
    assembly.add_instance(PartInstance(name="axial", part_name="plate-part"))
    assembly.add_instance(
        PartInstance(
            name="rotated",
            part_name="plate-part",
            transform=RigidTransform(rotation=((0.0, -1.0), (1.0, 0.0)), translation=(4.0, 0.0)),
        )
    )
    model.set_assembly(assembly)

    model.add_boundary(BoundaryDef(name="bc-axial-left", target_name="left", scope_name="axial", dof_values={"UY": 0.0}))
    model.add_boundary(BoundaryDef(name="bc-axial-right", target_name="right", scope_name="axial", dof_values={"UY": 0.001}))
    model.add_boundary(BoundaryDef(name="bc-axial-anchor", target_name="anchor", scope_name="axial", dof_values={"UX": 0.0}))
    model.add_boundary(BoundaryDef(name="bc-rot-left", target_name="left", scope_name="rotated", dof_values={"UY": 0.0}))
    model.add_boundary(BoundaryDef(name="bc-rot-right", target_name="right", scope_name="rotated", dof_values={"UY": 0.001}))
    model.add_boundary(BoundaryDef(name="bc-rot-anchor", target_name="anchor", scope_name="rotated", dof_values={"UX": 0.0}))
    model.add_output_request(OutputRequest(name="field-node", variables=("U", "RF"), target_type="model", position="NODE"))
    model.add_step(
        StepDef(
            name="step-static",
            procedure_type="static_linear",
            boundary_names=(
                "bc-axial-left",
                "bc-axial-right",
                "bc-axial-anchor",
                "bc-rot-left",
                "bc-rot-right",
                "bc-rot-anchor",
            ),
            output_request_names=("field-node",),
        )
    )
    model.set_job(JobDef(name="job-1", step_names=("step-static",)))
    return model


def build_cps4_tension_model() -> ModelDB:
    """构造 CPS4 单元单向拉伸 benchmark 模型。"""

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

    model = ModelDB(name="cps4-tension")
    model.add_part(Part(name="plate-part", mesh=mesh))
    model.add_material(
        MaterialDef(
            name="mat-1",
            material_type="linear_elastic",
            parameters={"young_modulus": 1000.0, "poisson_ratio": 0.25, "density": 3.0},
        )
    )
    model.add_section(
        SectionDef(
            name="sec-1",
            section_type="plane_stress",
            material_name="mat-1",
            region_name="plate-set",
            scope_name="plate-part",
            parameters={"thickness": 2.0},
        )
    )
    model.add_boundary(BoundaryDef(name="bc-left-x", target_name="left", dof_values={"UX": 0.0}))
    model.add_boundary(BoundaryDef(name="bc-right-x", target_name="right", dof_values={"UX": 0.001}))
    model.add_boundary(BoundaryDef(name="bc-anchor-y", target_name="anchor", dof_values={"UY": 0.0}))
    model.add_output_request(OutputRequest(name="field-node", variables=("U", "RF"), target_type="model", position="NODE"))
    model.add_output_request(OutputRequest(name="field-element", variables=("S", "E"), target_type="model", position="ELEMENT_CENTROID"))
    model.add_step(
        StepDef(
            name="step-static",
            procedure_type="static_linear",
            boundary_names=("bc-left-x", "bc-right-x", "bc-anchor-y"),
            output_request_names=("field-node", "field-element"),
        )
    )
    model.set_job(JobDef(name="job-1", step_names=("step-static",)))
    return model


def build_c3d8_pressure_block_model() -> ModelDB:
    """构造 C3D8 表面压力 benchmark 模型。"""

    mesh = _build_block_mesh()
    model = ModelDB(name="c3d8-pressure")
    model.add_part(Part(name="block-part", mesh=mesh))
    _attach_block_material_section(model, scope_name="block-part")
    model.add_boundary(BoundaryDef(name="bc-fixed", target_name="FIXED", dof_values={"UX": 0.0, "UY": 0.0, "UZ": 0.0}))
    model.add_distributed_load(
        DistributedLoadDef(name="load-pressure", target_name="PRESSURE_FACE", scope_name="block-part", load_type="P", components={"P": -2.0})
    )
    model.add_output_request(OutputRequest(name="field-node", variables=("U", "RF"), target_type="model", position="NODE"))
    model.add_step(
        StepDef(
            name="step-static",
            procedure_type="static_linear",
            boundary_names=("bc-fixed",),
            distributed_load_names=("load-pressure",),
            output_request_names=("field-node",),
        )
    )
    model.set_job(JobDef(name="job-1", step_names=("step-static",)))
    return model


def build_dual_instance_c3d8_pressure_model() -> ModelDB:
    """构造双实例 C3D8 表面压力作用域回归模型。"""

    mesh = _build_block_mesh()
    model = ModelDB(name="dual-instance-pressure")
    model.add_part(Part(name="block-part", mesh=mesh))
    _attach_block_material_section(model, scope_name=None)

    assembly = Assembly(name="assembly-1")
    assembly.add_instance(PartInstance(name="left", part_name="block-part"))
    assembly.add_instance(PartInstance(name="right", part_name="block-part", transform=RigidTransform(translation=(3.0, 0.0, 0.0))))
    model.set_assembly(assembly)

    model.add_boundary(BoundaryDef(name="bc-left-fixed", target_name="FIXED", scope_name="left", dof_values={"UX": 0.0, "UY": 0.0, "UZ": 0.0}))
    model.add_boundary(BoundaryDef(name="bc-right-fixed", target_name="FIXED", scope_name="right", dof_values={"UX": 0.0, "UY": 0.0, "UZ": 0.0}))
    model.add_distributed_load(
        DistributedLoadDef(name="load-right-pressure", target_name="PRESSURE_FACE", scope_name="right", load_type="P", components={"P": -2.0})
    )
    model.add_output_request(OutputRequest(name="field-node", variables=("U", "RF"), target_type="model", position="NODE"))
    model.add_step(
        StepDef(
            name="step-static",
            procedure_type="static_linear",
            boundary_names=("bc-left-fixed", "bc-right-fixed"),
            distributed_load_names=("load-right-pressure",),
            output_request_names=("field-node",),
        )
    )
    model.set_job(JobDef(name="job-1", step_names=("step-static",)))
    return model


def build_rotated_instance_c3d8_pressure_model() -> ModelDB:
    """构造旋转实例 C3D8 solver 级表面压力回归模型。"""

    mesh = _build_block_mesh()
    model = ModelDB(name="rotated-instance-c3d8")
    model.add_part(Part(name="block-part", mesh=mesh))
    _attach_block_material_section(model, scope_name=None)

    assembly = Assembly(name="assembly-1")
    assembly.add_instance(PartInstance(name="left", part_name="block-part"))
    assembly.add_instance(
        PartInstance(
            name="right",
            part_name="block-part",
            transform=RigidTransform(
                rotation=((0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
                translation=(0.0, 3.0, 0.0),
            ),
        )
    )
    model.set_assembly(assembly)

    model.add_boundary(BoundaryDef(name="bc-left-fixed", target_name="FIXED", scope_name="left", dof_values={"UX": 0.0, "UY": 0.0, "UZ": 0.0}))
    model.add_boundary(BoundaryDef(name="bc-right-fixed", target_name="FIXED", scope_name="right", dof_values={"UX": 0.0, "UY": 0.0, "UZ": 0.0}))
    model.add_distributed_load(
        DistributedLoadDef(name="load-right-pressure", target_name="PRESSURE_FACE", scope_name="right", load_type="P", components={"P": -2.0})
    )
    model.add_output_request(OutputRequest(name="field-node", variables=("U", "RF"), target_type="model", position="NODE"))
    model.add_step(
        StepDef(
            name="step-static",
            procedure_type="static_linear",
            boundary_names=("bc-left-fixed", "bc-right-fixed"),
            distributed_load_names=("load-right-pressure",),
            output_request_names=("field-node",),
        )
    )
    model.set_job(JobDef(name="job-1", step_names=("step-static",)))
    return model


def _build_base_beam_model(model_name: str) -> ModelDB:
    mesh = Mesh()
    mesh.add_node(NodeRecord(name="n1", coordinates=(0.0, 0.0)))
    mesh.add_node(NodeRecord(name="n2", coordinates=(2.0, 0.0)))
    mesh.add_element(ElementRecord(name="beam-1", type_key="B21", node_names=("n1", "n2")))
    mesh.add_node_set("root", ("n1",))
    mesh.add_node_set("tip", ("n2",))
    mesh.add_element_set("beam-set", ("beam-1",))

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


def _build_block_mesh() -> Mesh:
    mesh = Mesh()
    mesh.add_node(NodeRecord(name="1", coordinates=(1.0, 0.0, 1.0)))
    mesh.add_node(NodeRecord(name="2", coordinates=(1.0, 1.0, 1.0)))
    mesh.add_node(NodeRecord(name="3", coordinates=(1.0, 1.0, 0.0)))
    mesh.add_node(NodeRecord(name="4", coordinates=(1.0, 0.0, 0.0)))
    mesh.add_node(NodeRecord(name="5", coordinates=(0.0, 0.0, 1.0)))
    mesh.add_node(NodeRecord(name="6", coordinates=(0.0, 1.0, 1.0)))
    mesh.add_node(NodeRecord(name="7", coordinates=(0.0, 1.0, 0.0)))
    mesh.add_node(NodeRecord(name="8", coordinates=(0.0, 0.0, 0.0)))
    mesh.add_element(ElementRecord(name="block-1", type_key="C3D8", node_names=("1", "2", "3", "4", "5", "6", "7", "8")))
    mesh.add_node_set("FIXED", ("5", "6", "7", "8"))
    mesh.add_node_set("LOADED", ("1", "2", "3", "4"))
    mesh.add_element_set("BLOCK", ("block-1",))
    mesh.add_surface(Surface(name="PRESSURE_FACE", facets=(SurfaceFacet(element_name="block-1", local_face="S1"),)))
    return mesh


def _attach_block_material_section(model: ModelDB, scope_name: str | None) -> None:
    model.add_material(
        MaterialDef(
            name="mat-1",
            material_type="linear_elastic",
            parameters={"young_modulus": 1000.0, "poisson_ratio": 0.3, "density": 1.0},
        )
    )
    model.add_section(
        SectionDef(
            name="sec-1",
            section_type="solid",
            material_name="mat-1",
            region_name="BLOCK",
            scope_name=scope_name,
            parameters={},
        )
    )
