"""内置 procedure provider。"""

from __future__ import annotations

from pyfem.compiler.requests import ProcedureBuildRequest
from pyfem.foundation.errors import CompilationError
from pyfem.procedures.implicit_dynamic import ImplicitDynamicProcedure
from pyfem.procedures.modal import ModalProcedure
from pyfem.procedures.nonlinear_support import StaticNonlinearParameters
from pyfem.procedures.static_linear import StaticLinearProcedure
from pyfem.procedures.static_nonlinear import StaticNonlinearProcedure
from pyfem.solver import Assembler, DiscreteProblem, SciPyBackend

_FORMAL_NLGEOM_LOAD_SUPPORT = "当前正式支持的 nlgeom 载荷范围仅包括位移边界与 nodal load。"
_FORMAL_NLGEOM_ELEMENT_SUPPORT = "当前正式支持的 nlgeom 单元主线仅包括 B21 corotational、CPS4 total_lagrangian 与 C3D8 total_lagrangian。"
_FORMAL_NLGEOM_MATERIAL_SUPPORT = (
    "当前正式支持的 finite-strain / nlgeom 材料子集仅包括 "
    "B21 + 线弹性/J2、CPS4 + plane_strain + 线弹性/J2、C3D8 + solid + 线弹性/J2。"
)


class StaticLinearProcedureProvider:
    """构建静力线性 procedure。"""

    def build(self, request: ProcedureBuildRequest) -> StaticLinearProcedure:
        assembler = Assembler(request.compiled_model, nlgeom=False)
        problem = DiscreteProblem(request.compiled_model, assembler=assembler)
        backend = SciPyBackend()
        return StaticLinearProcedure(
            definition=request.definition,
            compiled_model=request.compiled_model,
            problem=problem,
            backend=backend,
        )


class ModalProcedureProvider:
    """构建模态分析 procedure。"""

    def build(self, request: ProcedureBuildRequest) -> ModalProcedure:
        assembler = Assembler(request.compiled_model, nlgeom=False)
        problem = DiscreteProblem(request.compiled_model, assembler=assembler)
        backend = SciPyBackend()
        return ModalProcedure(
            definition=request.definition,
            compiled_model=request.compiled_model,
            problem=problem,
            backend=backend,
        )


class ImplicitDynamicProcedureProvider:
    """构建隐式动力 procedure。"""

    def build(self, request: ProcedureBuildRequest) -> ImplicitDynamicProcedure:
        assembler = Assembler(request.compiled_model, nlgeom=False)
        problem = DiscreteProblem(request.compiled_model, assembler=assembler)
        backend = SciPyBackend()
        return ImplicitDynamicProcedure(
            definition=request.definition,
            compiled_model=request.compiled_model,
            problem=problem,
            backend=backend,
        )


class StaticNonlinearProcedureProvider:
    """构建静力非线性 procedure。"""

    def build(self, request: ProcedureBuildRequest) -> StaticNonlinearProcedure:
        parameters = StaticNonlinearParameters.from_step_parameters(request.definition.parameters)
        if parameters.nlgeom:
            self._validate_nlgeom_formal_contract(request)

        assembler = Assembler(request.compiled_model, nlgeom=parameters.nlgeom)
        problem = DiscreteProblem(request.compiled_model, assembler=assembler)
        backend = SciPyBackend()
        return StaticNonlinearProcedure(
            definition=request.definition,
            compiled_model=request.compiled_model,
            problem=problem,
            backend=backend,
        )

    def _validate_nlgeom_formal_contract(self, request: ProcedureBuildRequest) -> None:
        unsupported_element_types = _collect_unsupported_nlgeom_element_types(request)
        if unsupported_element_types:
            raise CompilationError(
                f"静力非线性步骤 {request.definition.name} 请求 nlgeom=True，"
                f"但存在未纳入正式主线的单元类型: {', '.join(unsupported_element_types)}。"
                f"{_FORMAL_NLGEOM_ELEMENT_SUPPORT}"
            )

        unsupported_material_combinations = _collect_unsupported_nlgeom_material_combinations(request)
        if unsupported_material_combinations:
            raise CompilationError(
                f"静力非线性步骤 {request.definition.name} 请求 nlgeom=True，"
                f"但存在未支持的单元/截面/材料组合: {', '.join(unsupported_material_combinations)}。"
                f"{_FORMAL_NLGEOM_MATERIAL_SUPPORT}"
            )

        unsupported_distributed_loads = _collect_unsupported_nlgeom_distributed_loads(request)
        if unsupported_distributed_loads:
            raise CompilationError(
                f"静力非线性步骤 {request.definition.name} 请求 nlgeom=True，"
                f"但以下 distributed load 当前未纳入正式主线: {', '.join(unsupported_distributed_loads)}。"
                "当前暂不支持 nlgeom=True 下的 distributed load、surface pressure 或 follower pressure 当前构形语义。"
                f"{_FORMAL_NLGEOM_LOAD_SUPPORT}"
            )


def register_builtin_procedure_providers(registry) -> None:
    """注册内置 procedure provider。"""

    registry.register_procedure("static", StaticLinearProcedureProvider())
    registry.register_procedure("static_linear", StaticLinearProcedureProvider())
    registry.register_procedure("static_nonlinear", StaticNonlinearProcedureProvider())
    registry.register_procedure("modal", ModalProcedureProvider())
    registry.register_procedure("implicit_dynamic", ImplicitDynamicProcedureProvider())
    registry.register_procedure("dynamic", ImplicitDynamicProcedureProvider())


def _collect_unsupported_nlgeom_element_types(request: ProcedureBuildRequest) -> list[str]:
    unsupported_type_keys = sorted(
        {
            runtime.get_type_key()
            for runtime in request.compiled_model.element_runtimes.values()
            if not runtime.get_supported_geometric_nonlinearity_modes()
        }
    )
    return unsupported_type_keys


def _collect_unsupported_nlgeom_material_combinations(request: ProcedureBuildRequest) -> list[str]:
    unsupported_combinations: list[str] = []
    for runtime in request.compiled_model.element_runtimes.values():
        type_key = runtime.get_type_key()
        material_runtime = getattr(runtime, "material_runtime", None)
        if material_runtime is None:
            continue
        material_type = str(material_runtime.get_material_type())
        section_runtime = getattr(runtime, "section_runtime", None)
        section_type = _resolve_runtime_section_type(section_runtime)

        if type_key == "B21":
            if material_type in {"linear_elastic", "j2_plasticity"}:
                continue
        elif type_key == "CPS4":
            if material_type == "linear_elastic":
                continue
            if material_type == "j2_plasticity" and section_type == "plane_strain":
                continue
        elif type_key == "C3D8":
            if material_type in {"linear_elastic", "j2_plasticity"}:
                continue

        unsupported_combinations.append(
            f"{runtime.get_location().qualified_name}[element={type_key}, section={section_type}, material={material_type}]"
        )
    return sorted(unsupported_combinations)


def _collect_unsupported_nlgeom_distributed_loads(request: ProcedureBuildRequest) -> list[str]:
    load_descriptions: list[str] = []
    for load_name in request.definition.distributed_load_names:
        load_definition = request.compiled_model.model.distributed_loads[load_name]
        load_descriptions.append(_describe_distributed_load(load_definition))
    return sorted(load_descriptions)


def _resolve_runtime_section_type(section_runtime: object | None) -> str:
    if section_runtime is None:
        return "none"
    get_section_type = getattr(section_runtime, "get_section_type", None)
    if callable(get_section_type):
        return str(get_section_type())
    return type(section_runtime).__name__


def _describe_distributed_load(load_definition: object) -> str:
    load_name = str(getattr(load_definition, "name", "<unknown>"))
    target_type = str(getattr(load_definition, "target_type", "<unknown>"))
    scope_name = getattr(load_definition, "scope_name", None)
    target_name = str(getattr(load_definition, "target_name", "<unknown>"))
    load_type = _normalize_load_type(str(getattr(load_definition, "load_type", "<unknown>")))
    qualified_target = f"{scope_name}.{target_name}" if scope_name else target_name
    return f"{load_name}[type={load_type}, target_type={target_type}, target={qualified_target}]"


def _normalize_load_type(load_type: str) -> str:
    normalized_load_type = str(load_type).strip().lower()
    aliases = {
        "p": "pressure",
        "pressure": "pressure",
        "follower": "follower_pressure",
        "follower_pressure": "follower_pressure",
        "follower-pressure": "follower_pressure",
    }
    return aliases.get(normalized_load_type, normalized_load_type)
