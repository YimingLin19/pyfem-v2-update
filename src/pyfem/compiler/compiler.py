"""模型到运行时世界的编译器。"""

from __future__ import annotations

from pyfem.compiler.compiled_model import CompiledModel
from pyfem.compiler.registry import RuntimeRegistry
from pyfem.compiler.requests import (
    ConstraintBuildRequest,
    ElementBuildRequest,
    InteractionBuildRequest,
    MaterialBuildRequest,
    ProcedureBuildRequest,
    SectionBuildRequest,
)
from pyfem.compiler.runtime_placeholders import (
    ConstraintRuntimePlaceholder,
    ElementRuntimePlaceholder,
    InteractionRuntimePlaceholder,
    MaterialRuntimePlaceholder,
    SectionRuntimePlaceholder,
    StepRuntimePlaceholder,
)
from pyfem.foundation.errors import CompilationError
from pyfem.foundation.types import DofLocation, ElementLocation, NodeLocation
from pyfem.kernel import DofManager
from pyfem.kernel.constraints import ConstrainedDof, ConstraintRuntime
from pyfem.kernel.elements import ElementRuntime
from pyfem.kernel.interactions import InteractionRuntime
from pyfem.kernel.materials import MaterialRuntime
from pyfem.kernel.sections import SectionRuntime
from pyfem.mesh import ElementRecord
from pyfem.modeldb import ModelDB, SectionDef
from pyfem.modeldb.scopes import CompilationScope
from pyfem.procedures.base import ProcedureRuntime


class Compiler:
    """负责将模型数据库编译为运行时对象图。"""

    def __init__(self, registry: RuntimeRegistry | None = None) -> None:
        """使用给定的运行时注册表初始化编译器。"""

        self._registry = registry if registry is not None else RuntimeRegistry()

    def compile(self, model: ModelDB) -> CompiledModel:
        """将模型数据库编译为正式的运行时模型。"""

        model.validate()

        material_runtimes = self._build_material_runtimes(model)
        section_runtimes = self._build_section_runtimes(model, material_runtimes)
        dof_manager = DofManager()
        element_runtimes = self._build_element_runtimes(model, dof_manager, material_runtimes, section_runtimes)

        compiled_model = CompiledModel(
            model=model,
            dof_manager=dof_manager,
            element_runtimes=element_runtimes,
            material_runtimes=material_runtimes,
            section_runtimes=section_runtimes,
            constraint_runtimes={},
            interaction_runtimes={},
            step_runtimes={},
        )

        compiled_model.constraint_runtimes = self._build_constraint_runtimes(model, compiled_model)
        compiled_model.interaction_runtimes = self._build_interaction_runtimes(model, compiled_model)
        compiled_model.step_runtimes = self._build_step_runtimes(model, compiled_model)
        dof_manager.finalize()
        return compiled_model

    def _build_material_runtimes(self, model: ModelDB) -> dict[str, MaterialRuntime]:
        material_runtimes: dict[str, MaterialRuntime] = {}
        for definition in model.materials.values():
            provider = self._registry.find_material_provider(definition.material_type)
            if provider is None:
                material_runtimes[definition.name] = MaterialRuntimePlaceholder(
                    name=definition.name,
                    material_type=definition.material_type,
                    parameters=dict(definition.parameters),
                )
            else:
                material_runtimes[definition.name] = provider.build(
                    MaterialBuildRequest(definition=definition, model=model)
                )
        return material_runtimes

    def _build_section_runtimes(
        self,
        model: ModelDB,
        material_runtimes: dict[str, MaterialRuntime],
    ) -> dict[str, SectionRuntime]:
        section_runtimes: dict[str, SectionRuntime] = {}
        for definition in model.sections.values():
            provider = self._registry.find_section_provider(definition.section_type)
            if provider is None:
                section_runtimes[definition.name] = SectionRuntimePlaceholder(
                    name=definition.name,
                    section_type=definition.section_type,
                    material_name=definition.material_name,
                    region_name=definition.region_name,
                    scope_name=definition.scope_name,
                    parameters=dict(definition.parameters),
                )
            else:
                section_runtimes[definition.name] = provider.build(
                    SectionBuildRequest(
                        definition=definition,
                        model=model,
                        material_runtimes=material_runtimes,
                    )
                )
        return section_runtimes

    def _build_element_runtimes(
        self,
        model: ModelDB,
        dof_manager: DofManager,
        material_runtimes: dict[str, MaterialRuntime],
        section_runtimes: dict[str, SectionRuntime],
    ) -> dict[str, ElementRuntime]:
        element_runtimes: dict[str, ElementRuntime] = {}

        for scope in model.iter_compilation_scopes():
            for element in scope.part.elements.values():
                section_definition = self._resolve_section_definition(model, scope, element)
                section_runtime = section_runtimes[section_definition.name]
                material_name = self._resolve_material_name(element, section_definition)
                material_runtime = material_runtimes[material_name]
                node_records = tuple(scope.get_node_geometry_record(node_name) for node_name in element.node_names)
                node_locations = tuple(
                    NodeLocation(scope_name=scope.scope_name, node_name=node_record.name) for node_record in node_records
                )
                dof_layout = self._registry.get_dof_layout(element.type_key)
                dof_indices = tuple(
                    index
                    for node_location in node_locations
                    for index in dof_manager.register_node_dofs(node_location, dof_layout.node_dof_names)
                )
                location = ElementLocation(scope_name=scope.scope_name, element_name=element.name)
                provider = self._registry.find_element_provider(element.type_key)
                if provider is None:
                    element_runtimes[location.qualified_name] = ElementRuntimePlaceholder(
                        location=location,
                        type_key=element.type_key,
                        dof_layout=dof_layout.node_dof_names,
                        node_names=element.node_names,
                        dof_indices=dof_indices,
                        material_name=material_name,
                        section_name=section_definition.name,
                    )
                else:
                    element_runtimes[location.qualified_name] = provider.build(
                        ElementBuildRequest(
                            scope=scope,
                            location=location,
                            part=scope.part,
                            element=element,
                            node_locations=node_locations,
                            node_records=node_records,
                            dof_indices=dof_indices,
                            material_runtime=material_runtime,
                            section_runtime=section_runtime,
                            model=model,
                            dof_manager=dof_manager,
                        )
                    )
        return element_runtimes

    def _build_constraint_runtimes(self, model: ModelDB, compiled_model: CompiledModel) -> dict[str, ConstraintRuntime]:
        constraint_runtimes: dict[str, ConstraintRuntime] = {}
        for definition in model.boundaries.values():
            constrained_dofs = self._resolve_boundary_constrained_dofs(model, compiled_model.dof_manager, definition)
            provider = self._registry.find_constraint_provider(definition.constraint_type)
            if provider is None:
                constraint_runtimes[definition.name] = ConstraintRuntimePlaceholder(
                    name=definition.name,
                    boundary_type=definition.boundary_type,
                    target_name=definition.target_name,
                    target_type=definition.target_type,
                    constrained_dofs=constrained_dofs,
                    dof_values=dict(definition.dof_values),
                )
                continue
            constraint_runtimes[definition.name] = provider.build(
                ConstraintBuildRequest(
                    definition=definition,
                    model=model,
                    compiled_model=compiled_model,
                    constrained_dofs=constrained_dofs,
                )
            )
        return constraint_runtimes

    def _build_interaction_runtimes(
        self,
        model: ModelDB,
        compiled_model: CompiledModel,
    ) -> dict[str, InteractionRuntime]:
        interaction_runtimes: dict[str, InteractionRuntime] = {}
        for definition in model.interactions.values():
            provider = self._registry.find_interaction_provider(definition.interaction_type)
            if provider is None:
                interaction_runtimes[definition.name] = InteractionRuntimePlaceholder(
                    name=definition.name,
                    interaction_type=definition.interaction_type,
                    scope_name=definition.scope_name,
                    parameters=dict(definition.parameters),
                )
                continue
            interaction_runtimes[definition.name] = provider.build(
                InteractionBuildRequest(
                    definition=definition,
                    model=model,
                    compiled_model=compiled_model,
                )
            )
        return interaction_runtimes

    def _build_step_runtimes(self, model: ModelDB, compiled_model: CompiledModel) -> dict[str, ProcedureRuntime]:
        step_runtimes: dict[str, ProcedureRuntime] = {}
        step_names = model.job.step_names if model.job is not None else tuple(model.steps.keys())
        for step_name in step_names:
            definition = model.steps[step_name]
            provider = self._registry.find_procedure_provider(definition.procedure_type)
            if provider is None:
                step_runtimes[definition.name] = StepRuntimePlaceholder(
                    name=definition.name,
                    procedure_type=definition.procedure_type,
                    boundary_names=tuple(definition.boundary_names),
                    nodal_load_names=tuple(definition.nodal_load_names),
                    distributed_load_names=tuple(definition.distributed_load_names),
                    output_request_names=tuple(definition.output_request_names),
                    parameters=dict(definition.parameters),
                )
            else:
                step_runtimes[definition.name] = provider.build(
                    ProcedureBuildRequest(
                        definition=definition,
                        model=model,
                        compiled_model=compiled_model,
                    )
                )
        return step_runtimes

    def _resolve_section_definition(
        self,
        model: ModelDB,
        scope: CompilationScope,
        element: ElementRecord,
    ) -> SectionDef:
        direct_section = model.sections[element.section_name] if element.section_name is not None else None
        if direct_section is not None and direct_section.scope_name is not None and direct_section.scope_name != scope.scope_name:
            raise CompilationError(
                f"单元 {scope.scope_name}.{element.name} 引用了作用域不匹配的直接截面 {direct_section.name}。"
            )
        region_section = self._resolve_region_section(model, scope, element.name)

        if direct_section is not None and region_section is not None and direct_section.name != region_section.name:
            raise CompilationError(
                f"单元 {scope.scope_name}.{element.name} 的直接截面与区域截面绑定冲突。"
            )

        selected_section = direct_section or region_section
        if selected_section is None:
            raise CompilationError(f"单元 {scope.scope_name}.{element.name} 未能绑定到任何截面定义。")
        return selected_section

    def _resolve_region_section(
        self,
        model: ModelDB,
        scope: CompilationScope,
        element_name: str,
    ) -> SectionDef | None:
        candidates: list[SectionDef] = []
        for section in model.sections.values():
            if section.region_name is None:
                continue
            if section.scope_name is not None and section.scope_name != scope.scope_name:
                continue
            if not scope.has_part_element_region(section.region_name):
                continue
            if element_name in scope.resolve_part_element_region(section.region_name):
                candidates.append(section)

        if len(candidates) > 1:
            joined = ", ".join(section.name for section in candidates)
            raise CompilationError(f"单元 {scope.scope_name}.{element_name} 命中了多个区域截面: {joined}。")
        return candidates[0] if candidates else None

    def _resolve_material_name(self, element: ElementRecord, section_definition: SectionDef) -> str:
        if (
            element.material_name is not None
            and section_definition.material_name is not None
            and element.material_name != section_definition.material_name
        ):
            raise CompilationError(f"单元 {element.name} 的材料绑定与截面材料绑定冲突。")

        material_name = element.material_name or section_definition.material_name
        if material_name is None:
            raise CompilationError(f"单元 {element.name} 未能绑定到任何材料定义。")
        return material_name

    def _resolve_boundary_constrained_dofs(
        self,
        model: ModelDB,
        dof_manager: DofManager,
        definition,
    ) -> tuple[ConstrainedDof, ...]:
        constrained_dofs: list[ConstrainedDof] = []
        matched_target = False
        scopes = model.iter_target_scopes(definition.scope_name)
        if definition.scope_name is not None and not scopes:
            raise CompilationError(f"未找到作用域 {definition.scope_name}。")

        for scope in scopes:
            node_names = self._resolve_boundary_target_nodes(scope, definition.target_type, definition.target_name)
            if not node_names:
                continue
            matched_target = True
            for node_name in node_names:
                for dof_name, value in definition.dof_values.items():
                    constrained_dofs.append(
                        ConstrainedDof(
                            dof_index=dof_manager.get_global_id(
                                DofLocation(
                                    scope_name=scope.scope_name,
                                    node_name=node_name,
                                    dof_name=dof_name.upper(),
                                )
                            ),
                            value=value,
                        )
                    )

        if not matched_target:
            raise CompilationError(f"边界条件 {definition.name} 未匹配到任何目标节点。")

        return tuple(constrained_dofs)

    def _resolve_boundary_target_nodes(
        self,
        scope: CompilationScope,
        target_type: str,
        target_name: str,
    ) -> tuple[str, ...]:
        if target_type not in {"node", "node_set"}:
            raise CompilationError(f"当前边界条件暂不支持目标类型 {target_type}。")
        return scope.resolve_node_names(target_type, target_name)
