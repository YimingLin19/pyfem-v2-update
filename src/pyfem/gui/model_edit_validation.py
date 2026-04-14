"""定义模型编辑弹窗使用的输入校验与对象重建逻辑。"""

from __future__ import annotations

from typing import Any

from pyfem.foundation.errors import ModelValidationError
from pyfem.mesh import PartInstance, RigidTransform
from pyfem.modeldb import BoundaryDef, DistributedLoadDef, MaterialDef, NodalLoadDef, OutputRequest, SectionDef, StepDef


def parse_required_float(text: str, *, field_name: str) -> float:
    """解析必填浮点参数。"""

    stripped = text.strip()
    if not stripped:
        raise ModelValidationError(f"{field_name} 不能为空。")
    try:
        return float(stripped)
    except ValueError as error:
        raise ModelValidationError(f"{field_name} 必须是浮点数。") from error


def parse_optional_float(text: str, *, field_name: str) -> float | None:
    """解析可选浮点参数。"""

    stripped = text.strip()
    if not stripped:
        return None
    return parse_required_float(stripped, field_name=field_name)


def parse_required_int(text: str, *, field_name: str) -> int:
    """解析必填整数参数。"""

    stripped = text.strip()
    if not stripped:
        raise ModelValidationError(f"{field_name} 不能为空。")
    try:
        return int(stripped)
    except ValueError as error:
        raise ModelValidationError(f"{field_name} 必须是整数。") from error


def parse_optional_text(text: str) -> str | None:
    """解析可选文本参数。"""

    stripped = text.strip()
    return None if not stripped else stripped


def parse_required_csv_names(text: str, *, field_name: str) -> tuple[str, ...]:
    """解析逗号分隔名称列表。"""

    values = tuple(item.strip().upper() for item in text.split(",") if item.strip())
    if not values:
        raise ModelValidationError(f"{field_name} 不能为空。")
    return values


def parse_component_value_pairs(text: str, *, field_name: str) -> dict[str, float]:
    """解析 `KEY=VALUE` 形式的分量输入。"""

    mapping: dict[str, float] = {}
    chunks = [item.strip() for item in text.split(",") if item.strip()]
    if not chunks:
        raise ModelValidationError(f"{field_name} 不能为空。")
    for chunk in chunks:
        if "=" not in chunk:
            raise ModelValidationError(f"{field_name} 必须写成 `KEY=VALUE` 形式。")
        component_name, raw_value = chunk.split("=", 1)
        normalized_component = component_name.strip().upper()
        if not normalized_component:
            raise ModelValidationError(f"{field_name} 中存在空分量名。")
        mapping[normalized_component] = parse_required_float(raw_value, field_name=f"{field_name}:{normalized_component}")
    return mapping


def parse_vector(text: str, *, field_name: str) -> tuple[float, ...]:
    """解析逗号分隔向量。"""

    items = [item.strip() for item in text.split(",") if item.strip()]
    if not items:
        return ()
    try:
        return tuple(float(item) for item in items)
    except ValueError as error:
        raise ModelValidationError(f"{field_name} 必须是逗号分隔数字。") from error


def parse_rotation_rows(rows: tuple[str, ...], *, field_name: str) -> tuple[tuple[float, ...], ...]:
    """解析旋转矩阵行。"""

    resolved_rows: list[tuple[float, ...]] = []
    for row_index, row_text in enumerate(rows, start=1):
        vector = parse_vector(row_text, field_name=f"{field_name} 第 {row_index} 行")
        if vector:
            resolved_rows.append(vector)
    return tuple(resolved_rows)


def build_material_update(
    original: MaterialDef,
    *,
    material_type: str,
    young_modulus_text: str,
    poisson_ratio_text: str,
    density_text: str,
    yield_stress_text: str,
    hardening_modulus_text: str,
    tangent_mode: str,
) -> MaterialDef:
    """构建材料更新对象。"""

    parameters: dict[str, Any] = {
        "young_modulus": parse_required_float(young_modulus_text, field_name="Young's Modulus"),
        "poisson_ratio": parse_required_float(poisson_ratio_text, field_name="Poisson Ratio"),
    }
    density = parse_optional_float(density_text, field_name="Density")
    if density is not None:
        parameters["density"] = density

    normalized_material_type = material_type.strip().lower()
    if normalized_material_type == "j2_plasticity":
        parameters["yield_stress"] = parse_required_float(yield_stress_text, field_name="Yield Stress")
        parameters["hardening_modulus"] = parse_required_float(
            hardening_modulus_text,
            field_name="Hardening Modulus",
        )
        parameters["tangent_mode"] = tangent_mode.strip().lower() or "consistent"
    return MaterialDef(name=original.name, material_type=normalized_material_type, parameters=parameters)


def build_step_update(
    original: StepDef,
    *,
    procedure_type: str,
    nlgeom: bool,
    initial_increment_text: str,
    max_increments_text: str,
    min_increment_text: str,
    max_iterations_text: str,
    residual_tolerance_text: str,
    displacement_tolerance_text: str,
    allow_cutback: bool,
    line_search: bool,
    num_modes_text: str,
    time_step_text: str,
    total_time_text: str,
) -> StepDef:
    """构建分析步骤更新对象。"""

    normalized_procedure_type = procedure_type.strip().lower()
    parameters = dict(original.parameters)
    if normalized_procedure_type == "static_nonlinear":
        parameters = {
            "nlgeom": bool(nlgeom),
            "initial_increment": parse_required_float(initial_increment_text, field_name="Initial Increment"),
            "max_increments": parse_required_int(max_increments_text, field_name="Max Increments"),
            "min_increment": parse_required_float(min_increment_text, field_name="Min Increment"),
            "max_iterations": parse_required_int(max_iterations_text, field_name="Max Iterations"),
            "residual_tolerance": parse_required_float(residual_tolerance_text, field_name="Residual Tolerance"),
            "displacement_tolerance": parse_required_float(
                displacement_tolerance_text,
                field_name="Displacement Tolerance",
            ),
            "allow_cutback": bool(allow_cutback),
            "line_search": bool(line_search),
        }
    elif normalized_procedure_type == "modal":
        parameters = {"num_modes": parse_required_int(num_modes_text, field_name="Number of Modes")}
    elif normalized_procedure_type == "implicit_dynamic":
        parameters = {
            "time_step": parse_required_float(time_step_text, field_name="Time Step"),
            "total_time": parse_required_float(total_time_text, field_name="Total Time"),
        }
    else:
        parameters = {}

    return StepDef(
        name=original.name,
        procedure_type=normalized_procedure_type,
        boundary_names=tuple(original.boundary_names),
        nodal_load_names=tuple(original.nodal_load_names),
        distributed_load_names=tuple(original.distributed_load_names),
        output_request_names=tuple(original.output_request_names),
        parameters=parameters,
    )


def build_nodal_load_update(
    original: NodalLoadDef,
    *,
    target_name_text: str,
    target_type: str,
    scope_name_text: str,
    components_text: str,
) -> NodalLoadDef:
    """构建节点载荷更新对象。"""

    return NodalLoadDef(
        name=original.name,
        target_name=target_name_text.strip(),
        target_type=target_type.strip().lower(),
        scope_name=parse_optional_text(scope_name_text),
        components=parse_component_value_pairs(components_text, field_name="Load Components"),
        parameters=dict(original.parameters),
    )


def build_boundary_update(
    original: BoundaryDef,
    *,
    target_name_text: str,
    target_type: str,
    scope_name_text: str,
    dof_values_text: str,
) -> BoundaryDef:
    """构建边界条件更新对象。"""

    return BoundaryDef(
        name=original.name,
        target_name=target_name_text.strip(),
        target_type=target_type.strip().lower(),
        scope_name=parse_optional_text(scope_name_text),
        boundary_type=original.boundary_type,
        dof_values=parse_component_value_pairs(dof_values_text, field_name="Boundary Values"),
        parameters=dict(original.parameters),
    )


def build_distributed_load_update(
    original: DistributedLoadDef,
    *,
    target_name_text: str,
    target_type: str,
    scope_name_text: str,
    load_type: str,
    load_value_text: str,
) -> DistributedLoadDef:
    """构建分布载荷更新对象。"""

    normalized_load_type = load_type.strip().lower()
    component_name = "P" if normalized_load_type in {"pressure", "follower_pressure"} else normalized_load_type.upper()
    return DistributedLoadDef(
        name=original.name,
        target_name=target_name_text.strip(),
        target_type=target_type.strip().lower(),
        scope_name=parse_optional_text(scope_name_text),
        load_type=normalized_load_type,
        components={component_name: parse_required_float(load_value_text, field_name="Load Value")},
        parameters=dict(original.parameters),
    )


def build_output_request_update(
    original: OutputRequest,
    *,
    request_mode: str,
    variables_text: str,
    target_type: str,
    target_name_text: str,
    scope_name_text: str,
    position: str,
    frequency_text: str,
) -> OutputRequest:
    """构建输出请求更新对象。"""

    parameters = dict(original.parameters)
    parameters["request_mode"] = request_mode.strip().lower()
    return OutputRequest(
        name=original.name,
        variables=parse_required_csv_names(variables_text, field_name="Variables"),
        target_type=target_type.strip().lower(),
        target_name=parse_optional_text(target_name_text),
        scope_name=parse_optional_text(scope_name_text),
        position=position.strip().upper(),
        frequency=parse_required_int(frequency_text, field_name="Frequency"),
        parameters=parameters,
    )


def build_section_update(
    original: SectionDef,
    *,
    material_name_text: str,
    region_name_text: str,
    scope_name_text: str,
    primary_value_text: str,
    secondary_value_text: str,
    thickness_text: str,
) -> SectionDef:
    """构建截面更新对象。"""

    parameters = dict(original.parameters)
    section_type = original.section_type.strip().lower()
    if section_type == "beam":
        parameters = {
            "area": parse_required_float(primary_value_text, field_name="Area"),
            "moment_inertia_z": parse_required_float(secondary_value_text, field_name="Moment Inertia"),
        }
    elif section_type in {"plane_stress", "plane_strain"}:
        parameters = {"thickness": parse_required_float(thickness_text, field_name="Thickness")}
    else:
        parameters = dict(original.parameters)
    return SectionDef(
        name=original.name,
        section_type=original.section_type,
        material_name=parse_optional_text(material_name_text),
        region_name=parse_optional_text(region_name_text),
        scope_name=parse_optional_text(scope_name_text),
        parameters=parameters,
    )


def build_instance_transform_update(
    original: PartInstance,
    *,
    translation_text: str,
    rotation_rows: tuple[str, ...],
) -> PartInstance:
    """构建实例放置变换更新对象。"""

    transform = RigidTransform(
        rotation=parse_rotation_rows(rotation_rows, field_name="Rotation"),
        translation=parse_vector(translation_text, field_name="Translation"),
    )
    return PartInstance(
        name=original.name,
        part_name=original.part_name,
        transform=transform,
        metadata=dict(original.metadata),
    )
