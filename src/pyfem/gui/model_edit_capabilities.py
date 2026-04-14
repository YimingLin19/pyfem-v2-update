"""定义 GUI / Exporter / JobSnapshot 共用的支持矩阵。"""

from __future__ import annotations

from dataclasses import dataclass

from pyfem.modeldb import ModelDB, OutputRequest, SectionDef, StepDef
from pyfem.procedures.nonlinear_support import StaticNonlinearParameters

EDITABLE_OBJECT_KINDS = (
    "material",
    "section",
    "boundary",
    "nodal_load",
    "distributed_load",
    "output_request",
    "step",
    "instance",
)

SUPPORTED_STEP_TYPES = ("static", "static_linear", "static_nonlinear", "modal", "dynamic", "implicit_dynamic")
SUPPORTED_MATERIAL_TYPES = ("linear_elastic", "elastic_isotropic", "j2_plastic", "j2_plasticity")
SUPPORTED_SECTION_TYPES = ("solid", "plane_stress", "plane_strain", "beam")
SUPPORTED_OUTPUT_POSITIONS = (
    "NODE",
    "ELEMENT_CENTROID",
    "INTEGRATION_POINT",
    "ELEMENT_NODAL",
    "NODE_AVERAGED",
    "GLOBAL_HISTORY",
)
SUPPORTED_RAW_BLOCK_PLACEMENTS = (
    "before_parts",
    "before_materials",
    "before_steps",
    "step_start",
    "step_end",
    "after_model",
)


@dataclass(slots=True, frozen=True)
class CapabilityIssue:
    """描述一个支持矩阵检查结果。"""

    severity: str
    code: str
    message: str
    object_kind: str
    object_name: str | None = None
    step_name: str | None = None


@dataclass(slots=True, frozen=True)
class OutputRequestSemanticSummary:
    """描述输出请求的最小语义感知结果。"""

    request_mode: str
    kinematic_regime: str
    strain_measure: str | None
    stress_measure: str | None
    message: str


def is_object_editable(kind: str) -> bool:
    """判断对象类型当前是否纳入正式参数编辑主线。"""

    return normalize_object_kind(kind) in EDITABLE_OBJECT_KINDS


def normalize_object_kind(kind: str) -> str:
    """归一化 GUI / shell 使用的对象类型名称。"""

    normalized = str(kind).strip().lower()
    aliases = {
        "load": "load",
        "material": "material",
        "section": "section",
        "boundary": "boundary",
        "nodal_load": "nodal_load",
        "distributed_load": "distributed_load",
        "output_request": "output_request",
        "step": "step",
        "instance": "instance",
    }
    return aliases.get(normalized, normalized)


def normalize_step_type(step_type: str) -> str:
    """归一化分析步骤类型。"""

    aliases = {
        "static": "static_linear",
        "static_linear": "static_linear",
        "static_nonlinear": "static_nonlinear",
        "modal": "modal",
        "dynamic": "implicit_dynamic",
        "implicit_dynamic": "implicit_dynamic",
    }
    return aliases.get(str(step_type).strip().lower(), str(step_type).strip().lower())


def normalize_material_type(material_type: str) -> str:
    """归一化材料类型。"""

    aliases = {
        "linear_elastic": "linear_elastic",
        "elastic_isotropic": "linear_elastic",
        "j2_plastic": "j2_plasticity",
        "j2_plasticity": "j2_plasticity",
    }
    return aliases.get(str(material_type).strip().lower(), str(material_type).strip().lower())


def normalize_load_type(load_type: str) -> str:
    """归一化分布载荷类型。"""

    aliases = {
        "p": "pressure",
        "pressure": "pressure",
        "follower": "follower_pressure",
        "follower_pressure": "follower_pressure",
        "follower-pressure": "follower_pressure",
    }
    return aliases.get(str(load_type).strip().lower(), str(load_type).strip().lower())


def collect_export_capability_issues(model: ModelDB) -> tuple[CapabilityIssue, ...]:
    """收集当前模型在 exporter 正式子集下的 fail-fast 项。"""

    issues: list[CapabilityIssue] = []

    for material in model.materials.values():
        normalized_material_type = normalize_material_type(material.material_type)
        if normalized_material_type not in {"linear_elastic", "j2_plasticity"}:
            issues.append(
                CapabilityIssue(
                    severity="fail_fast",
                    code="unsupported_material_type",
                    message=f"材料 {material.name} 的 material_type={material.material_type} 当前未纳入 InpExporter 正式子集。",
                    object_kind="material",
                    object_name=material.name,
                )
            )

    for section in model.sections.values():
        normalized_section_type = str(section.section_type).strip().lower()
        if normalized_section_type not in SUPPORTED_SECTION_TYPES:
            issues.append(
                CapabilityIssue(
                    severity="fail_fast",
                    code="unsupported_section_type",
                    message=f"截面 {section.name} 的 section_type={section.section_type} 当前未纳入 InpExporter 正式子集。",
                    object_kind="section",
                    object_name=section.name,
                )
            )

    for step in model.steps.values():
        issues.extend(_collect_step_export_issues(step))

    for request in model.output_requests.values():
        issues.extend(_collect_output_request_export_issues(model, request))

    for block in model.raw_keyword_blocks.values():
        if block.placement not in SUPPORTED_RAW_BLOCK_PLACEMENTS:
            issues.append(
                CapabilityIssue(
                    severity="fail_fast",
                    code="unsupported_raw_block_placement",
                    message=f"raw keyword block {block.name} 的 placement={block.placement} 当前未纳入正式 exporter 子集。",
                    object_kind="raw_keyword_block",
                    object_name=block.name,
                    step_name=block.step_name,
                )
            )

    return tuple(issues)


def collect_run_capability_issues(model: ModelDB) -> tuple[CapabilityIssue, ...]:
    """收集当前模型在 Run / JobSnapshot 主线下的 fail-fast 与解释性边界。"""

    issues = list(collect_export_capability_issues(model))
    section_by_name = model.sections

    for step in model.steps.values():
        normalized_step_type = normalize_step_type(step.procedure_type)
        if normalized_step_type != "static_nonlinear":
            continue

        parameters = StaticNonlinearParameters.from_step_parameters(step.parameters)
        if not parameters.nlgeom:
            continue

        issues.extend(_collect_nlgeom_element_issues(model, step))
        issues.extend(_collect_nlgeom_material_issues(model, step, section_by_name))
        issues.extend(_collect_nlgeom_load_issues(model, step))

    return tuple(issues)


def explain_editability(model: ModelDB, kind: str, name: str | None) -> tuple[CapabilityIssue, ...]:
    """给出对象在 GUI 编辑入口中的支持说明。"""

    normalized_kind = normalize_object_kind(kind)
    if normalized_kind == "load" and name is not None:
        if name in model.nodal_loads:
            normalized_kind = "nodal_load"
        elif name in model.distributed_loads:
            normalized_kind = "distributed_load"

    if normalized_kind not in EDITABLE_OBJECT_KINDS:
        return (
            CapabilityIssue(
                severity="disabled",
                code="object_not_editable",
                message=f"对象类型 {kind} 当前未纳入第一阶段正式参数编辑主线。",
                object_kind=normalized_kind,
                object_name=name,
            ),
        )

    if normalized_kind == "distributed_load":
        referencing_steps = _steps_referencing_distributed_load(model, str(name))
        issues: list[CapabilityIssue] = []
        for step in referencing_steps:
            parameters = step.parameters if normalize_step_type(step.procedure_type) == "static_nonlinear" else {}
            nlgeom_enabled = bool(parameters.get("nlgeom", False))
            if nlgeom_enabled:
                issues.append(
                    CapabilityIssue(
                        severity="disabled",
                        code="nlgeom_distributed_load_warning",
                        message=(
                            f"分布载荷 {name} 被静力非线性步骤 {step.name} 在 nlgeom=True 下引用；"
                            "当前正式支持的 nlgeom 载荷范围仅包括位移边界与 nodal load。"
                        ),
                        object_kind=normalized_kind,
                        object_name=name,
                        step_name=step.name,
                    )
                )
        return tuple(issues)

    return ()


def summarize_output_request_semantics(model: ModelDB, request: OutputRequest) -> OutputRequestSemanticSummary:
    """推断输出请求当前涉及的最小结果语义。"""

    request_mode = str(request.parameters.get("request_mode", _infer_request_mode_from_position(request.position))).strip().lower()
    related_steps = tuple(
        step
        for step in model.steps.values()
        if request.name in step.output_request_names
    )
    nlgeom_states = {
        bool(step.parameters.get("nlgeom", False))
        for step in related_steps
        if normalize_step_type(step.procedure_type) == "static_nonlinear"
    }

    if not related_steps:
        kinematic_regime = "unknown"
    elif nlgeom_states == {True}:
        kinematic_regime = "finite_strain"
    elif nlgeom_states == {False} or not nlgeom_states:
        kinematic_regime = "small_strain"
    else:
        kinematic_regime = "mixed"

    variables = {str(variable).upper() for variable in request.variables}
    strain_measure = None
    stress_measure = None
    if {"E", "E_IP", "E_REC"} & variables:
        strain_measure = "green_lagrange" if kinematic_regime == "finite_strain" else "small_strain"
    if {"S", "S_IP", "S_REC", "S_AVG", "S_VM_IP", "S_VM_REC", "S_VM_AVG"} & variables:
        stress_measure = (
            "second_piola_kirchhoff"
            if kinematic_regime == "finite_strain"
            else "cauchy_small_strain"
        )

    message = (
        f"mode={request_mode}, regime={kinematic_regime}, "
        f"strain_measure={strain_measure or '-'}, stress_measure={stress_measure or '-'}"
    )
    return OutputRequestSemanticSummary(
        request_mode=request_mode,
        kinematic_regime=kinematic_regime,
        strain_measure=strain_measure,
        stress_measure=stress_measure,
        message=message,
    )


def _collect_step_export_issues(step: StepDef) -> tuple[CapabilityIssue, ...]:
    issues: list[CapabilityIssue] = []
    normalized_step_type = normalize_step_type(step.procedure_type)
    if normalized_step_type not in {"static_linear", "static_nonlinear", "modal", "implicit_dynamic"}:
        issues.append(
            CapabilityIssue(
                severity="fail_fast",
                code="unsupported_step_type",
                message=f"分析步骤 {step.name} 的 procedure_type={step.procedure_type} 当前未纳入 InpExporter 正式子集。",
                object_kind="step",
                object_name=step.name,
                step_name=step.name,
            )
        )
    if normalized_step_type == "static_nonlinear":
        try:
            StaticNonlinearParameters.from_step_parameters(step.parameters)
        except Exception as error:  # noqa: BLE001
            issues.append(
                CapabilityIssue(
                    severity="fail_fast",
                    code="invalid_static_nonlinear_parameters",
                    message=f"分析步骤 {step.name} 的 static_nonlinear 参数不合法: {error}",
                    object_kind="step",
                    object_name=step.name,
                    step_name=step.name,
                )
            )
    return tuple(issues)


def _collect_output_request_export_issues(model: ModelDB, request: OutputRequest) -> tuple[CapabilityIssue, ...]:
    issues: list[CapabilityIssue] = []
    normalized_position = str(request.position).strip().upper()
    if normalized_position not in SUPPORTED_OUTPUT_POSITIONS:
        issues.append(
            CapabilityIssue(
                severity="fail_fast",
                code="unsupported_output_position",
                message=f"输出请求 {request.name} 的 position={request.position} 当前未纳入 InpExporter 正式子集。",
                object_kind="output_request",
                object_name=request.name,
            )
        )
    if request.frequency <= 0:
        issues.append(
            CapabilityIssue(
                severity="fail_fast",
                code="invalid_output_frequency",
                message=f"输出请求 {request.name} 的 frequency 必须大于零。",
                object_kind="output_request",
                object_name=request.name,
            )
        )
    if not request.variables:
        issues.append(
            CapabilityIssue(
                severity="fail_fast",
                code="empty_output_variables",
                message=f"输出请求 {request.name} 至少需要一个变量。",
                object_kind="output_request",
                object_name=request.name,
            )
        )
    if request.target_type != "model" and request.target_name is None:
        issues.append(
            CapabilityIssue(
                severity="fail_fast",
                code="missing_output_target",
                message=f"输出请求 {request.name} 缺少 target_name。",
                object_kind="output_request",
                object_name=request.name,
            )
        )
    if request.scope_name is not None and not model.iter_target_scopes(request.scope_name):
        issues.append(
            CapabilityIssue(
                severity="fail_fast",
                code="missing_output_scope",
                message=f"输出请求 {request.name} 引用了不存在的 scope {request.scope_name}。",
                object_kind="output_request",
                object_name=request.name,
            )
        )
    return tuple(issues)


def _collect_nlgeom_element_issues(model: ModelDB, step: StepDef) -> tuple[CapabilityIssue, ...]:
    unsupported_type_keys = sorted(
        {
            element.type_key
            for part in model.parts.values()
            for element in part.elements.values()
            if element.type_key not in {"B21", "CPS4", "C3D8"}
        }
    )
    if not unsupported_type_keys:
        return ()
    return (
        CapabilityIssue(
            severity="fail_fast",
            code="unsupported_nlgeom_element_type",
            message=(
                f"静力非线性步骤 {step.name} 请求 nlgeom=True，"
                f"但存在未纳入正式主线的单元类型: {', '.join(unsupported_type_keys)}。"
            ),
            object_kind="step",
            object_name=step.name,
            step_name=step.name,
        ),
    )


def _collect_nlgeom_material_issues(
    model: ModelDB,
    step: StepDef,
    section_by_name: dict[str, SectionDef],
) -> tuple[CapabilityIssue, ...]:
    unsupported_combinations: list[str] = []
    for part in model.parts.values():
        for element in part.elements.values():
            section = _resolve_element_section(part, element.name, element.section_name, section_by_name)
            if section is None or section.material_name is None:
                continue
            material = model.materials.get(section.material_name)
            if material is None:
                continue
            material_type = normalize_material_type(material.material_type)
            section_type = str(section.section_type).strip().lower()
            if _is_nlgeom_material_combination_supported(element.type_key, section_type, material_type):
                continue
            unsupported_combinations.append(
                f"{part.name}.{element.name}[element={element.type_key}, section={section_type}, material={material_type}]"
            )
    if not unsupported_combinations:
        return ()
    return (
        CapabilityIssue(
            severity="fail_fast",
            code="unsupported_nlgeom_material_combo",
            message=(
                f"静力非线性步骤 {step.name} 请求 nlgeom=True，"
                f"但存在未支持的单元/截面/材料组合: {', '.join(sorted(unsupported_combinations))}。"
            ),
            object_kind="step",
            object_name=step.name,
            step_name=step.name,
        ),
    )


def _collect_nlgeom_load_issues(model: ModelDB, step: StepDef) -> tuple[CapabilityIssue, ...]:
    if not step.distributed_load_names:
        return ()
    descriptions = [
        _describe_distributed_load(model, load_name)
        for load_name in step.distributed_load_names
    ]
    return (
        CapabilityIssue(
            severity="fail_fast",
            code="unsupported_nlgeom_distributed_load",
            message=(
                f"静力非线性步骤 {step.name} 请求 nlgeom=True，"
                f"但以下 distributed load 当前未纳入正式主线: {', '.join(descriptions)}。"
                "当前正式支持的 nlgeom 载荷范围仅包括位移边界与 nodal load。"
            ),
            object_kind="step",
            object_name=step.name,
            step_name=step.name,
        ),
    )


def _resolve_element_section(
    part,
    element_name: str,
    direct_section_name: str | None,
    section_by_name: dict[str, SectionDef],
) -> SectionDef | None:
    if direct_section_name is not None:
        return section_by_name.get(direct_section_name)
    for section in section_by_name.values():
        if section.region_name is None:
            continue
        if section.scope_name not in {None, part.name}:
            continue
        element_names = part.mesh.element_sets.get(section.region_name, ())
        if element_name in element_names:
            return section
    return None


def _is_nlgeom_material_combination_supported(type_key: str, section_type: str, material_type: str) -> bool:
    if type_key == "B21":
        return material_type in {"linear_elastic", "j2_plasticity"}
    if type_key == "CPS4":
        if material_type == "linear_elastic":
            return True
        return material_type == "j2_plasticity" and section_type == "plane_strain"
    if type_key == "C3D8":
        return material_type in {"linear_elastic", "j2_plasticity"}
    return False


def _describe_distributed_load(model: ModelDB, load_name: str) -> str:
    load = model.distributed_loads[load_name]
    normalized_load_type = normalize_load_type(load.load_type)
    qualified_target = f"{load.scope_name}.{load.target_name}" if load.scope_name else load.target_name
    return f"{load.name}[type={normalized_load_type}, target_type={load.target_type}, target={qualified_target}]"


def _steps_referencing_distributed_load(model: ModelDB, load_name: str) -> tuple[StepDef, ...]:
    return tuple(step for step in model.steps.values() if load_name in step.distributed_load_names)


def _infer_request_mode_from_position(position: str) -> str:
    return "history" if str(position).strip().upper() == "GLOBAL_HISTORY" else "field"
