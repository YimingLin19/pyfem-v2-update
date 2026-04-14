"""定义模型编辑弹窗与 Property 管理器使用的 presenter。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from pyfem.foundation.errors import ModelValidationError
from pyfem.gui.model_edit_capabilities import (
    CapabilityIssue,
    collect_run_capability_issues,
    explain_editability,
    normalize_material_type,
    normalize_object_kind,
    summarize_output_request_semantics,
)
from pyfem.gui.model_edit_validation import (
    build_boundary_update,
    build_distributed_load_update,
    build_instance_transform_update,
    build_material_update,
    build_nodal_load_update,
    build_output_request_update,
    build_section_update,
    build_step_update,
)
from pyfem.gui.shell import GuiModelSummary, GuiShell
from pyfem.mesh import PartInstance
from pyfem.modeldb import BoundaryDef, DistributedLoadDef, MaterialDef, ModelDB, NodalLoadDef, OutputRequest, SectionDef, StepDef


@dataclass(slots=True, frozen=True)
class ModelEditContext:
    """描述一个模型编辑对象的上下文。"""

    resolved_kind: str
    object_name: str
    object_type_label: str
    owner_label: str
    support_messages: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class SectionAssignmentCandidate:
    """描述一个可用于截面分配的候选区域。"""

    scope_name: str
    part_name: str
    region_name: str


@dataclass(slots=True, frozen=True)
class SectionAssignmentScope:
    """描述一个可用于截面分配的作用域入口。"""

    scope_name: str
    part_name: str


@dataclass(slots=True, frozen=True)
class SectionAssignmentContext:
    """描述打开截面分配弹窗时可复用的默认上下文。"""

    preferred_section_name: str | None = None
    preferred_scope_name: str | None = None
    preferred_region_name: str | None = None
    preferred_part_name: str | None = None


@dataclass(slots=True, frozen=True)
class LoadManagerEntry:
    """描述一个载荷管理器列表项。"""

    name: str
    resolved_kind: str
    display_label: str
    step_names: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class BoundaryManagerEntry:
    """描述一个边界管理器列表项。"""

    name: str
    display_label: str
    step_names: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class StepManagerEntry:
    """描述一个分析步管理器列表项。"""

    name: str
    display_label: str
    procedure_type: str
    job_names: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class EditScopeCandidate:
    """描述一个可供编辑对话框选择的作用域。"""

    scope_name: str
    part_name: str


@dataclass(slots=True, frozen=True)
class EditTargetCandidate:
    """描述一个可供编辑对话框选择的目标。"""

    target_name: str
    target_type: str
    display_label: str


@dataclass(slots=True, frozen=True)
class LoadEditContext:
    """描述载荷编辑对话框可复用的默认上下文。"""

    preferred_load_name: str | None = None
    preferred_step_name: str | None = None
    preferred_scope_name: str | None = None
    preferred_target_name: str | None = None
    preferred_target_type: str | None = None
    preferred_load_kind: str | None = None


@dataclass(slots=True, frozen=True)
class BoundaryEditContext:
    """描述边界编辑对话框可复用的默认上下文。"""

    preferred_boundary_name: str | None = None
    preferred_step_name: str | None = None
    preferred_scope_name: str | None = None
    preferred_target_name: str | None = None
    preferred_target_type: str | None = None


class ModelEditPresenter:
    """负责从活 ModelDB 读取对象并安全回写。"""

    def __init__(self, shell: GuiShell) -> None:
        self._shell = shell

    def material(self, name: str) -> MaterialDef:
        """返回当前材料定义。"""

        return self._copy_model().materials[name]

    def step(self, name: str) -> StepDef:
        """返回当前步骤定义。"""

        return self._copy_model().steps[name]

    def nodal_load(self, name: str) -> NodalLoadDef:
        """返回当前节点载荷定义。"""

        return self._copy_model().nodal_loads[name]

    def boundary(self, name: str) -> BoundaryDef:
        """返回当前边界条件定义。"""

        return self._copy_model().boundaries[name]

    def distributed_load(self, name: str) -> DistributedLoadDef:
        """返回当前分布载荷定义。"""

        return self._copy_model().distributed_loads[name]

    def output_request(self, name: str) -> OutputRequest:
        """返回当前输出请求定义。"""

        return self._copy_model().output_requests[name]

    def section(self, name: str) -> SectionDef:
        """返回当前截面定义。"""

        return self._copy_model().sections[name]

    def instance(self, name: str) -> PartInstance:
        """返回当前实例定义。"""

        model = self._copy_model()
        if model.assembly is None:
            raise ModelValidationError("当前模型不包含装配实例。")
        return model.assembly.instances[name]

    def list_material_names(self) -> tuple[str, ...]:
        """返回当前所有材料名称。"""

        return tuple(sorted(self._copy_model().materials.keys()))

    def list_section_names(self) -> tuple[str, ...]:
        """返回当前所有截面名称。"""

        return tuple(sorted(self._copy_model().sections.keys()))

    def list_step_names(self) -> tuple[str, ...]:
        """返回当前所有步骤名称。"""

        return tuple(sorted(self._copy_model().steps.keys()))

    def list_step_manager_entries(self) -> tuple[StepManagerEntry, ...]:
        """返回步骤管理器需要展示的列表项。"""

        model = self._copy_model()
        entries: list[StepManagerEntry] = []
        for name in sorted(model.steps.keys()):
            step = model.steps[name]
            job_names = self.step_reference_jobs(name)
            entries.append(
                StepManagerEntry(
                    name=name,
                    display_label=self._build_step_manager_label(name, step.procedure_type, job_names),
                    procedure_type=step.procedure_type,
                    job_names=job_names,
                )
            )
        return tuple(entries)

    def list_load_manager_entries(self) -> tuple[LoadManagerEntry, ...]:
        """返回载荷管理器需要展示的列表项。"""

        model = self._copy_model()
        entries: list[LoadManagerEntry] = []
        for name in sorted(model.nodal_loads.keys()):
            step_names = self.load_reference_steps(name, resolved_kind="nodal_load")
            entries.append(
                LoadManagerEntry(
                    name=name,
                    resolved_kind="nodal_load",
                    display_label=self._build_load_manager_label(name, "nodal_load", step_names),
                    step_names=step_names,
                )
            )
        for name in sorted(model.distributed_loads.keys()):
            step_names = self.load_reference_steps(name, resolved_kind="distributed_load")
            entries.append(
                LoadManagerEntry(
                    name=name,
                    resolved_kind="distributed_load",
                    display_label=self._build_load_manager_label(name, "distributed_load", step_names),
                    step_names=step_names,
                )
            )
        return tuple(entries)

    def list_boundary_manager_entries(self) -> tuple[BoundaryManagerEntry, ...]:
        """返回边界管理器需要展示的列表项。"""

        entries: list[BoundaryManagerEntry] = []
        for name in sorted(self._copy_model().boundaries.keys()):
            step_names = self.boundary_reference_steps(name)
            entries.append(
                BoundaryManagerEntry(
                    name=name,
                    display_label=self._build_boundary_manager_label(name, step_names),
                    step_names=step_names,
                )
            )
        return tuple(entries)

    def list_edit_scope_candidates(self) -> tuple[EditScopeCandidate, ...]:
        """返回可供载荷与边界编辑复用的作用域列表。"""

        model = self._copy_model()
        return tuple(
            EditScopeCandidate(scope_name=scope.scope_name, part_name=scope.part_name)
            for scope in sorted(model.iter_target_scopes(), key=lambda item: (item.scope_name, item.part_name))
        )

    def list_target_candidates(
        self,
        *,
        scope_name: str | None,
        target_type: str,
    ) -> tuple[EditTargetCandidate, ...]:
        """按作用域与目标类型返回可选目标。"""

        normalized_scope_name = self._normalize_optional_text(scope_name)
        if normalized_scope_name is None:
            return ()
        scope = self._copy_model().resolve_compilation_scope(normalized_scope_name)
        if scope is None:
            return ()
        normalized_target_type = str(target_type).strip().lower()
        if normalized_target_type == "node":
            return tuple(
                EditTargetCandidate(target_name=node_name, target_type="node", display_label=f"{node_name} [Node]")
                for node_name in sorted(scope.part.nodes.keys())
            )
        if normalized_target_type == "node_set":
            names = sorted(set(scope.part.mesh.node_sets.keys()) | set(scope.node_sets.keys()))
            return tuple(
                EditTargetCandidate(target_name=name, target_type="node_set", display_label=f"{name} [Node Set]")
                for name in names
            )
        if normalized_target_type == "surface":
            names = sorted(set(scope.part.mesh.surfaces.keys()) | set(scope.surfaces.keys()))
            return tuple(
                EditTargetCandidate(target_name=name, target_type="surface", display_label=f"{name} [Surface]")
                for name in names
            )
        if normalized_target_type == "element_set":
            names = sorted(set(scope.part.mesh.element_sets.keys()) | set(scope.element_sets.keys()))
            return tuple(
                EditTargetCandidate(target_name=name, target_type="element_set", display_label=f"{name} [Element Set]")
                for name in names
            )
        return ()

    def list_section_assignment_scopes(self) -> tuple[SectionAssignmentScope, ...]:
        """返回当前模型中的全部可选作用域。"""

        model = self._copy_model()
        return tuple(
            SectionAssignmentScope(scope_name=scope.scope_name, part_name=scope.part_name)
            for scope in sorted(model.iter_target_scopes(), key=lambda item: (item.scope_name, item.part_name))
        )

    def list_section_assignment_candidates(self) -> tuple[SectionAssignmentCandidate, ...]:
        """返回当前所有可分配的截面区域候选。"""

        model = self._copy_model()
        candidates: list[SectionAssignmentCandidate] = []
        for scope in model.iter_target_scopes():
            for region_name in sorted(scope.part.mesh.element_sets.keys()):
                candidates.append(
                    SectionAssignmentCandidate(
                        scope_name=scope.scope_name,
                        part_name=scope.part_name,
                        region_name=region_name,
                    )
                )
        return tuple(candidates)

    def snapshot_model(self) -> ModelDB:
        """返回当前模型快照，用于管理器内部回滚。"""

        return self._copy_model()

    def model_dirty(self) -> bool:
        """返回当前模型 dirty 状态。"""

        return bool(self._shell.state.model_dirty)

    def restore_model(self, model: ModelDB, *, mark_dirty: bool) -> GuiModelSummary:
        """按指定 dirty 状态恢复模型快照。"""

        return self._shell.replace_loaded_model(model, mark_dirty=mark_dirty)

    def material_reference_sections(self, material_name: str) -> tuple[str, ...]:
        """返回引用指定材料的截面名称。"""

        model = self._copy_model()
        return tuple(sorted(section.name for section in model.sections.values() if section.material_name == material_name))

    def section_direct_reference_elements(self, section_name: str) -> tuple[str, ...]:
        """返回直接引用指定截面的单元名称。"""

        model = self._copy_model()
        element_names: list[str] = []
        for part in model.parts.values():
            for element in part.elements.values():
                if element.section_name == section_name:
                    element_names.append(f"{part.name}.{element.name}")
        return tuple(sorted(element_names))

    def load_reference_steps(self, name: str, *, resolved_kind: str | None = None) -> tuple[str, ...]:
        """返回引用指定载荷的步骤名称。"""

        model = self._copy_model()
        normalized_kind = resolved_kind or self.resolve_kind("load", name)
        step_names: list[str] = []
        for step in model.steps.values():
            if normalized_kind == "nodal_load" and name in step.nodal_load_names:
                step_names.append(step.name)
            if normalized_kind == "distributed_load" and name in step.distributed_load_names:
                step_names.append(step.name)
        return tuple(sorted(step_names))

    def boundary_reference_steps(self, name: str) -> tuple[str, ...]:
        """返回引用指定边界的步骤名称。"""

        model = self._copy_model()
        return tuple(sorted(step.name for step in model.steps.values() if name in step.boundary_names))

    def step_reference_jobs(self, name: str) -> tuple[str, ...]:
        """返回引用指定步骤的作业名称。"""

        model = self._copy_model()
        if model.job is None or name not in model.job.step_names:
            return ()
        return (model.job.name,)

    def suggest_new_load_name(self) -> str:
        """返回默认的新载荷名称。"""

        model = self._copy_model()
        existing_names = tuple(sorted(set(model.nodal_loads.keys()) | set(model.distributed_loads.keys())))
        return self._suggest_unique_name("load", existing_names)

    def suggest_new_boundary_name(self) -> str:
        """返回默认的新边界名称。"""

        return self._suggest_unique_name("bc", tuple(sorted(self._copy_model().boundaries.keys())))

    def suggest_new_step_name(self) -> str:
        """返回默认的新步骤名称。"""

        return self._suggest_unique_name("step", self.list_step_names())

    def create_load(
        self,
        name: str,
        *,
        load_kind: str,
        step_name: str | None = None,
        scope_name: str | None = None,
        target_type: str | None = None,
        target_name: str | None = None,
    ) -> GuiModelSummary:
        """创建一个默认载荷，并按需挂接到步骤。"""

        model = self._copy_model()
        existing_names = tuple(sorted(set(model.nodal_loads.keys()) | set(model.distributed_loads.keys())))
        normalized_name = self._validate_new_name(name, existing_names, label="载荷")
        normalized_kind = self._normalize_load_kind(load_kind)
        normalized_scope_name = self._normalize_optional_text(scope_name)
        normalized_target_name = self._normalize_optional_text(target_name)
        normalized_target_type = self._default_target_type_for_load(normalized_kind, target_type=target_type)
        if normalized_kind == "nodal_load":
            model.nodal_loads[normalized_name] = NodalLoadDef(
                name=normalized_name,
                target_name=normalized_target_name or "",
                target_type=normalized_target_type,
                scope_name=normalized_scope_name,
                components={"FX": 0.0},
            )
        else:
            model.distributed_loads[normalized_name] = DistributedLoadDef(
                name=normalized_name,
                target_name=normalized_target_name or "",
                target_type=normalized_target_type,
                scope_name=normalized_scope_name,
                load_type="pressure",
                components={"P": 0.0},
            )
        self._assign_object_to_step(model, normalized_name, normalized_kind, self._normalize_optional_text(step_name))
        return self._commit(model)

    def copy_load(self, source_name: str, target_name: str) -> GuiModelSummary:
        """复制指定载荷，并同步步骤引用。"""

        model = self._copy_model()
        resolved_kind = self.resolve_kind("load", source_name)
        existing_names = tuple(sorted(set(model.nodal_loads.keys()) | set(model.distributed_loads.keys())))
        normalized_name = self._validate_new_name(target_name, existing_names, label="载荷")
        if resolved_kind == "nodal_load":
            copied = deepcopy(model.nodal_loads[source_name])
            copied.name = normalized_name
            copied.parameters = dict(copied.parameters)
            copied.components = dict(copied.components)
            model.nodal_loads[normalized_name] = copied
        else:
            copied = deepcopy(model.distributed_loads[source_name])
            copied.name = normalized_name
            copied.parameters = dict(copied.parameters)
            copied.components = dict(copied.components)
            model.distributed_loads[normalized_name] = copied
        for step_name in self.load_reference_steps(source_name, resolved_kind=resolved_kind):
            self._assign_object_to_step(model, normalized_name, resolved_kind, step_name)
        return self._commit(model)

    def rename_load(self, source_name: str, target_name: str) -> GuiModelSummary:
        """重命名指定载荷，并同步步骤引用。"""

        model = self._copy_model()
        resolved_kind = self.resolve_kind("load", source_name)
        existing_names = tuple(sorted(set(model.nodal_loads.keys()) | set(model.distributed_loads.keys())))
        normalized_name = self._validate_renamed_name(source_name, target_name, existing_names, label="载荷")
        if normalized_name is None:
            return self._shell.build_model_summary()
        if resolved_kind == "nodal_load":
            load = model.nodal_loads.pop(source_name)
            load.name = normalized_name
            model.nodal_loads[normalized_name] = load
        else:
            load = model.distributed_loads.pop(source_name)
            load.name = normalized_name
            model.distributed_loads[normalized_name] = load
        for step in model.steps.values():
            if source_name in step.nodal_load_names:
                step.nodal_load_names = tuple(normalized_name if item == source_name else item for item in step.nodal_load_names)
            if source_name in step.distributed_load_names:
                step.distributed_load_names = tuple(normalized_name if item == source_name else item for item in step.distributed_load_names)
        return self._commit(model)

    def delete_load(self, name: str) -> GuiModelSummary:
        """删除指定载荷；若仍被步骤引用则拒绝。"""

        resolved_kind = self.resolve_kind("load", name)
        referenced_steps = self.load_reference_steps(name, resolved_kind=resolved_kind)
        if referenced_steps:
            joined = ", ".join(referenced_steps)
            raise ModelValidationError(f"载荷 {name} 仍被步骤引用，无法删除: {joined}。")
        model = self._copy_model()
        if resolved_kind == "nodal_load":
            del model.nodal_loads[name]
        else:
            del model.distributed_loads[name]
        return self._commit(model)

    def create_boundary(
        self,
        name: str,
        *,
        step_name: str | None = None,
        scope_name: str | None = None,
        target_type: str | None = None,
        target_name: str | None = None,
    ) -> GuiModelSummary:
        """创建一个默认边界，并按需挂接到步骤。"""

        model = self._copy_model()
        normalized_name = self._validate_new_name(name, tuple(sorted(model.boundaries.keys())), label="边界")
        model.boundaries[normalized_name] = BoundaryDef(
            name=normalized_name,
            target_name=self._normalize_optional_text(target_name) or "",
            target_type=str(target_type or "node_set").strip().lower() or "node_set",
            scope_name=self._normalize_optional_text(scope_name),
            dof_values={"UX": 0.0},
        )
        self._assign_object_to_step(model, normalized_name, "boundary", self._normalize_optional_text(step_name))
        return self._commit(model)

    def copy_boundary(self, source_name: str, target_name: str) -> GuiModelSummary:
        """复制指定边界，并同步步骤引用。"""

        model = self._copy_model()
        normalized_name = self._validate_new_name(target_name, tuple(sorted(model.boundaries.keys())), label="边界")
        boundary = deepcopy(model.boundaries[source_name])
        boundary.name = normalized_name
        boundary.parameters = dict(boundary.parameters)
        boundary.dof_values = dict(boundary.dof_values)
        model.boundaries[normalized_name] = boundary
        for step_name in self.boundary_reference_steps(source_name):
            self._assign_object_to_step(model, normalized_name, "boundary", step_name)
        return self._commit(model)

    def rename_boundary(self, source_name: str, target_name: str) -> GuiModelSummary:
        """重命名指定边界，并同步步骤引用。"""

        model = self._copy_model()
        normalized_name = self._validate_renamed_name(
            source_name,
            target_name,
            tuple(sorted(model.boundaries.keys())),
            label="边界",
        )
        if normalized_name is None:
            return self._shell.build_model_summary()
        boundary = model.boundaries.pop(source_name)
        boundary.name = normalized_name
        model.boundaries[normalized_name] = boundary
        for step in model.steps.values():
            if source_name in step.boundary_names:
                step.boundary_names = tuple(normalized_name if item == source_name else item for item in step.boundary_names)
        return self._commit(model)

    def delete_boundary(self, name: str) -> GuiModelSummary:
        """删除指定边界；若仍被步骤引用则拒绝。"""

        referenced_steps = self.boundary_reference_steps(name)
        if referenced_steps:
            joined = ", ".join(referenced_steps)
            raise ModelValidationError(f"边界 {name} 仍被步骤引用，无法删除: {joined}。")
        model = self._copy_model()
        del model.boundaries[name]
        return self._commit(model)

    def copy_step(self, source_name: str, target_name: str) -> GuiModelSummary:
        """复制指定步骤。"""

        model = self._copy_model()
        normalized_name = self._validate_new_name(target_name, tuple(sorted(model.steps.keys())), label="分析步骤")
        step = deepcopy(model.steps[source_name])
        step.name = normalized_name
        step.parameters = dict(step.parameters)
        model.steps[normalized_name] = step
        return self._commit(model)

    def rename_step(self, source_name: str, target_name: str) -> GuiModelSummary:
        """重命名指定步骤，并同步作业与引用字段。"""

        model = self._copy_model()
        normalized_name = self._validate_renamed_name(
            source_name,
            target_name,
            tuple(sorted(model.steps.keys())),
            label="分析步骤",
        )
        if normalized_name is None:
            return self._shell.build_model_summary()
        step = model.steps.pop(source_name)
        step.name = normalized_name
        model.steps[normalized_name] = step
        if model.job is not None and source_name in model.job.step_names:
            model.job.step_names = tuple(normalized_name if item == source_name else item for item in model.job.step_names)
        for block in model.raw_keyword_blocks.values():
            if block.step_name == source_name:
                block.step_name = normalized_name
        return self._commit(model)

    def delete_step(self, name: str) -> GuiModelSummary:
        """删除指定步骤，并执行引用保护。"""

        referenced_jobs = self.step_reference_jobs(name)
        if referenced_jobs:
            joined = ", ".join(referenced_jobs)
            raise ModelValidationError(f"分析步骤 {name} 仍被作业引用，无法删除: {joined}。")
        model = self._copy_model()
        if len(model.steps) <= 1:
            raise ModelValidationError("当前模型至少需要保留一个分析步骤；最后一个步骤不能删除。")
        referencing_blocks = tuple(
            sorted(block.name for block in model.raw_keyword_blocks.values() if block.step_name == name)
        )
        if referencing_blocks:
            joined = ", ".join(referencing_blocks)
            raise ModelValidationError(f"分析步骤 {name} 仍被 raw keyword block 引用，无法删除: {joined}。")
        del model.steps[name]
        return self._commit(model)

    def suggest_new_material_name(self) -> str:
        """返回默认的新材料名称。"""

        return self._suggest_unique_name("mat", self.list_material_names())

    def suggest_new_section_name(self) -> str:
        """返回默认的新截面名称。"""

        return self._suggest_unique_name("sec", self.list_section_names())

    def suggest_copy_name(self, original_name: str, existing_names: tuple[str, ...]) -> str:
        """为复制操作生成默认名称。"""

        base_name = f"{original_name}-copy"
        candidate_name = base_name
        index = 2
        while candidate_name in existing_names:
            candidate_name = f"{base_name}-{index}"
            index += 1
        return candidate_name

    def create_material(
        self,
        name: str,
        *,
        material_type: str = "linear_elastic",
    ) -> GuiModelSummary:
        """创建一个默认材料定义。"""

        normalized_name = self._validate_new_name(name, self.list_material_names(), label="材料")
        normalized_material_type = normalize_material_type(material_type)
        parameters = {
            "young_modulus": 210000.0,
            "poisson_ratio": 0.3,
        }
        if normalized_material_type == "j2_plasticity":
            parameters.update(
                {
                    "yield_stress": 250.0,
                    "hardening_modulus": 1000.0,
                    "tangent_mode": "consistent",
                }
            )
        model = self._copy_model()
        model.materials[normalized_name] = MaterialDef(
            name=normalized_name,
            material_type=normalized_material_type,
            parameters=parameters,
        )
        return self._commit(model)

    def copy_material(self, source_name: str, target_name: str) -> GuiModelSummary:
        """复制指定材料。"""

        normalized_name = self._validate_new_name(target_name, self.list_material_names(), label="材料")
        model = self._copy_model()
        material = deepcopy(model.materials[source_name])
        material.name = normalized_name
        material.parameters = dict(material.parameters)
        model.materials[normalized_name] = material
        return self._commit(model)

    def rename_material(self, source_name: str, target_name: str) -> GuiModelSummary:
        """重命名材料并同步截面引用。"""

        normalized_name = self._validate_renamed_name(
            source_name,
            target_name,
            self.list_material_names(),
            label="材料",
        )
        if normalized_name is None:
            return self._shell.build_model_summary()
        model = self._copy_model()
        material = model.materials.pop(source_name)
        material.name = normalized_name
        for section in model.sections.values():
            if section.material_name == source_name:
                section.material_name = normalized_name
        model.materials[normalized_name] = material
        return self._commit(model)

    def delete_material(self, name: str) -> GuiModelSummary:
        """删除材料；若仍被截面引用则拒绝删除。"""

        referenced_sections = self.material_reference_sections(name)
        if referenced_sections:
            joined = ", ".join(referenced_sections)
            raise ModelValidationError(f"材料 {name} 仍被截面引用，无法删除: {joined}。")
        model = self._copy_model()
        del model.materials[name]
        return self._commit(model)

    def create_section(
        self,
        name: str,
        *,
        section_type: str,
        material_name: str | None = None,
        region_name: str | None = None,
        scope_name: str | None = None,
    ) -> GuiModelSummary:
        """创建一个默认截面定义。"""

        normalized_name = self._validate_new_name(name, self.list_section_names(), label="截面")
        normalized_section_type = str(section_type).strip().lower()
        model = self._copy_model()
        model.sections[normalized_name] = SectionDef(
            name=normalized_name,
            section_type=normalized_section_type,
            material_name=self._normalize_optional_text(material_name),
            region_name=self._normalize_optional_text(region_name),
            scope_name=self._normalize_optional_text(scope_name),
            parameters=self._default_section_parameters(normalized_section_type),
        )
        return self._commit(model)

    def copy_section(self, source_name: str, target_name: str) -> GuiModelSummary:
        """复制指定截面。"""

        normalized_name = self._validate_new_name(target_name, self.list_section_names(), label="截面")
        model = self._copy_model()
        section = deepcopy(model.sections[source_name])
        section.name = normalized_name
        section.parameters = dict(section.parameters)
        model.sections[normalized_name] = section
        return self._commit(model)

    def rename_section(self, source_name: str, target_name: str) -> GuiModelSummary:
        """重命名截面并同步单元直接引用。"""

        normalized_name = self._validate_renamed_name(
            source_name,
            target_name,
            self.list_section_names(),
            label="截面",
        )
        if normalized_name is None:
            return self._shell.build_model_summary()
        model = self._copy_model()
        section = model.sections.pop(source_name)
        section.name = normalized_name
        for part in model.parts.values():
            for element in part.elements.values():
                if element.section_name == source_name:
                    element.section_name = normalized_name
        model.sections[normalized_name] = section
        return self._commit(model)

    def delete_section(self, name: str) -> GuiModelSummary:
        """删除截面；若仍被单元直接引用则拒绝删除。"""

        direct_references = self.section_direct_reference_elements(name)
        if direct_references:
            joined = ", ".join(direct_references)
            raise ModelValidationError(f"截面 {name} 仍被单元直接引用，无法删除: {joined}。")
        model = self._copy_model()
        del model.sections[name]
        return self._commit(model)

    def assign_section(
        self,
        name: str,
        *,
        scope_name: str,
        region_name: str,
    ) -> GuiModelSummary:
        """将指定截面分配到目标作用域与区域。"""

        normalized_scope_name = self._require_non_empty_text(scope_name, field_name="Scope")
        normalized_region_name = self._require_non_empty_text(region_name, field_name="Region")
        model = self._copy_model()
        section = model.sections[name]
        section.scope_name = normalized_scope_name
        section.region_name = normalized_region_name
        return self._commit(model)

    def build_section_assignment_context(self, kind: str | None, name: str | None) -> SectionAssignmentContext:
        """根据当前模型对象推断截面分配弹窗的默认选择。"""

        if kind in {None, ""} or name in {None, ""}:
            return SectionAssignmentContext()

        object_name = str(name)
        resolved_kind = self.resolve_kind(str(kind), object_name)
        model = self._copy_model()

        if resolved_kind == "section":
            section = model.sections[object_name]
            return SectionAssignmentContext(
                preferred_section_name=object_name,
                preferred_scope_name=section.scope_name,
                preferred_region_name=section.region_name,
            )

        if resolved_kind == "instance" and model.assembly is not None:
            instance = model.assembly.instances[object_name]
            return SectionAssignmentContext(
                preferred_scope_name=object_name,
                preferred_part_name=instance.part_name,
            )

        if resolved_kind == "part":
            matching_scope_names = sorted(
                scope.scope_name
                for scope in model.iter_target_scopes()
                if scope.part_name == object_name
            )
            preferred_scope_name = matching_scope_names[0] if len(matching_scope_names) == 1 else None
            return SectionAssignmentContext(
                preferred_scope_name=preferred_scope_name,
                preferred_part_name=object_name,
            )

        if resolved_kind == "boundary":
            return SectionAssignmentContext(preferred_scope_name=model.boundaries[object_name].scope_name)

        if resolved_kind == "nodal_load":
            return SectionAssignmentContext(preferred_scope_name=model.nodal_loads[object_name].scope_name)

        if resolved_kind == "distributed_load":
            return SectionAssignmentContext(preferred_scope_name=model.distributed_loads[object_name].scope_name)

        if resolved_kind == "output_request":
            return SectionAssignmentContext(preferred_scope_name=model.output_requests[object_name].scope_name)

        return SectionAssignmentContext()

    def build_load_edit_context(self, kind: str | None, name: str | None) -> LoadEditContext:
        """根据当前模型对象推断载荷编辑与管理器的默认上下文。"""

        if kind in {None, ""} or name in {None, ""}:
            return LoadEditContext()

        object_name = str(name)
        resolved_kind = self.resolve_kind(str(kind), object_name)
        model = self._copy_model()

        if resolved_kind in {"nodal_load", "distributed_load"}:
            step_names = self.load_reference_steps(object_name, resolved_kind=resolved_kind)
            load = model.nodal_loads[object_name] if resolved_kind == "nodal_load" else model.distributed_loads[object_name]
            return LoadEditContext(
                preferred_load_name=object_name,
                preferred_step_name=step_names[0] if step_names else None,
                preferred_scope_name=load.scope_name,
                preferred_target_name=load.target_name,
                preferred_target_type=load.target_type,
                preferred_load_kind=resolved_kind,
            )

        if resolved_kind == "step":
            return LoadEditContext(preferred_step_name=object_name)

        if resolved_kind == "instance" and model.assembly is not None:
            return LoadEditContext(preferred_scope_name=object_name)

        if resolved_kind == "part":
            matching_scope_names = sorted(scope.scope_name for scope in model.iter_target_scopes() if scope.part_name == object_name)
            return LoadEditContext(preferred_scope_name=matching_scope_names[0] if len(matching_scope_names) == 1 else None)

        if resolved_kind == "boundary":
            boundary = model.boundaries[object_name]
            step_names = self.boundary_reference_steps(object_name)
            return LoadEditContext(
                preferred_step_name=step_names[0] if step_names else None,
                preferred_scope_name=boundary.scope_name,
                preferred_target_name=boundary.target_name,
                preferred_target_type=boundary.target_type,
            )

        return LoadEditContext()

    def build_boundary_edit_context(self, kind: str | None, name: str | None) -> BoundaryEditContext:
        """根据当前模型对象推断边界编辑与管理器的默认上下文。"""

        if kind in {None, ""} or name in {None, ""}:
            return BoundaryEditContext()

        object_name = str(name)
        resolved_kind = self.resolve_kind(str(kind), object_name)
        model = self._copy_model()

        if resolved_kind == "boundary":
            boundary = model.boundaries[object_name]
            step_names = self.boundary_reference_steps(object_name)
            return BoundaryEditContext(
                preferred_boundary_name=object_name,
                preferred_step_name=step_names[0] if step_names else None,
                preferred_scope_name=boundary.scope_name,
                preferred_target_name=boundary.target_name,
                preferred_target_type=boundary.target_type,
            )

        if resolved_kind == "step":
            return BoundaryEditContext(preferred_step_name=object_name)

        if resolved_kind == "instance" and model.assembly is not None:
            return BoundaryEditContext(preferred_scope_name=object_name)

        if resolved_kind == "part":
            matching_scope_names = sorted(scope.scope_name for scope in model.iter_target_scopes() if scope.part_name == object_name)
            return BoundaryEditContext(preferred_scope_name=matching_scope_names[0] if len(matching_scope_names) == 1 else None)

        if resolved_kind in {"nodal_load", "distributed_load"}:
            load = model.nodal_loads[object_name] if resolved_kind == "nodal_load" else model.distributed_loads[object_name]
            step_names = self.load_reference_steps(object_name, resolved_kind=resolved_kind)
            return BoundaryEditContext(
                preferred_step_name=step_names[0] if step_names else None,
                preferred_scope_name=load.scope_name,
            )

        return BoundaryEditContext()

    def build_context(self, kind: str, name: str) -> ModelEditContext:
        """构建对象编辑上下文。"""

        model = self._copy_model()
        resolved_kind = self.resolve_kind(kind, name)
        support_issues = list(explain_editability(model, resolved_kind, name))
        support_issues.extend(self._collect_related_run_issues(model, resolved_kind, name))

        object_type_label = {
            "material": "Material",
            "step": "Step",
            "boundary": "Boundary",
            "nodal_load": "Nodal Load",
            "distributed_load": "Distributed Load",
            "output_request": "Output Request",
            "section": "Section",
            "instance": "Instance",
        }.get(resolved_kind, resolved_kind)

        owner_label = self._build_owner_label(model, resolved_kind, name)
        support_messages = tuple(dict.fromkeys(issue.message for issue in support_issues))
        return ModelEditContext(
            resolved_kind=resolved_kind,
            object_name=name,
            object_type_label=object_type_label,
            owner_label=owner_label,
            support_messages=support_messages,
        )

    def resolve_kind(self, kind: str, name: str) -> str:
        """将导航树中的对象类型映射到正式编辑对象类型。"""

        model = self._copy_model()
        normalized_kind = normalize_object_kind(kind)
        if normalized_kind == "load":
            if name in model.nodal_loads:
                return "nodal_load"
            if name in model.distributed_loads:
                return "distributed_load"
        return normalized_kind

    def apply_material_update(
        self,
        name: str,
        *,
        material_type: str,
        young_modulus_text: str,
        poisson_ratio_text: str,
        density_text: str,
        yield_stress_text: str,
        hardening_modulus_text: str,
        tangent_mode: str,
    ) -> GuiModelSummary:
        """写回材料更新。"""

        model = self._copy_model()
        model.materials[name] = build_material_update(
            model.materials[name],
            material_type=material_type,
            young_modulus_text=young_modulus_text,
            poisson_ratio_text=poisson_ratio_text,
            density_text=density_text,
            yield_stress_text=yield_stress_text,
            hardening_modulus_text=hardening_modulus_text,
            tangent_mode=tangent_mode,
        )
        return self._commit(model)

    def apply_step_update(
        self,
        name: str,
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
    ) -> GuiModelSummary:
        """写回步骤更新。"""

        model = self._copy_model()
        model.steps[name] = build_step_update(
            model.steps[name],
            procedure_type=self._normalize_step_procedure_type(procedure_type),
            nlgeom=nlgeom,
            initial_increment_text=initial_increment_text,
            max_increments_text=max_increments_text,
            min_increment_text=min_increment_text,
            max_iterations_text=max_iterations_text,
            residual_tolerance_text=residual_tolerance_text,
            displacement_tolerance_text=displacement_tolerance_text,
            allow_cutback=allow_cutback,
            line_search=line_search,
            num_modes_text=num_modes_text,
            time_step_text=time_step_text,
            total_time_text=total_time_text,
        )
        return self._commit(model)

    def apply_step_editor_update(
        self,
        name: str,
        *,
        creating: bool = False,
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
    ) -> GuiModelSummary:
        """写回步骤编辑弹窗的正式更新。"""

        model = self._copy_model()
        normalized_procedure_type = self._normalize_step_procedure_type(procedure_type)
        if creating and name not in model.steps:
            original = StepDef(name=name, procedure_type=normalized_procedure_type)
        else:
            original = model.steps[name]
        model.steps[name] = build_step_update(
            original,
            procedure_type=normalized_procedure_type,
            nlgeom=nlgeom,
            initial_increment_text=initial_increment_text,
            max_increments_text=max_increments_text,
            min_increment_text=min_increment_text,
            max_iterations_text=max_iterations_text,
            residual_tolerance_text=residual_tolerance_text,
            displacement_tolerance_text=displacement_tolerance_text,
            allow_cutback=allow_cutback,
            line_search=line_search,
            num_modes_text=num_modes_text,
            time_step_text=time_step_text,
            total_time_text=total_time_text,
        )
        return self._commit(model)

    def apply_nodal_load_update(
        self,
        name: str,
        *,
        target_name_text: str,
        target_type: str,
        scope_name_text: str,
        components_text: str,
    ) -> GuiModelSummary:
        """写回节点载荷更新。"""

        model = self._copy_model()
        model.nodal_loads[name] = build_nodal_load_update(
            model.nodal_loads[name],
            target_name_text=target_name_text,
            target_type=target_type,
            scope_name_text=scope_name_text,
            components_text=components_text,
        )
        return self._commit(model)

    def apply_boundary_update(
        self,
        name: str,
        *,
        target_name_text: str,
        target_type: str,
        scope_name_text: str,
        dof_values_text: str,
    ) -> GuiModelSummary:
        """写回边界条件更新。"""

        model = self._copy_model()
        model.boundaries[name] = build_boundary_update(
            model.boundaries[name],
            target_name_text=target_name_text,
            target_type=target_type,
            scope_name_text=scope_name_text,
            dof_values_text=dof_values_text,
        )
        return self._commit(model)

    def apply_distributed_load_update(
        self,
        name: str,
        *,
        target_name_text: str,
        target_type: str,
        scope_name_text: str,
        load_type: str,
        load_value_text: str,
    ) -> GuiModelSummary:
        """写回分布载荷更新。"""

        model = self._copy_model()
        model.distributed_loads[name] = build_distributed_load_update(
            model.distributed_loads[name],
            target_name_text=target_name_text,
            target_type=target_type,
            scope_name_text=scope_name_text,
            load_type=load_type,
            load_value_text=load_value_text,
        )
        return self._commit(model)

    def apply_load_editor_update(
        self,
        name: str,
        *,
        creating: bool = False,
        original_kind: str,
        load_kind: str,
        step_name: str | None,
        target_name_text: str,
        target_type: str,
        scope_name_text: str,
        components_text: str,
        load_type: str,
        load_value_text: str,
    ) -> GuiModelSummary:
        """写回载荷编辑弹窗的正式更新。"""

        model = self._copy_model()
        normalized_original_kind = self._normalize_load_kind(original_kind)
        normalized_load_kind = self._normalize_load_kind(load_kind)
        if creating:
            original = (
                NodalLoadDef(name=name, target_name="", target_type="node_set", scope_name=None, components={"FX": 0.0})
                if normalized_load_kind == "nodal_load"
                else DistributedLoadDef(
                    name=name,
                    target_name="",
                    target_type="surface",
                    scope_name=None,
                    load_type="pressure",
                    components={"P": 0.0},
                )
            )
        elif normalized_original_kind == "nodal_load":
            original = model.nodal_loads.pop(name)
        else:
            original = model.distributed_loads.pop(name)

        if normalized_load_kind == "nodal_load":
            updated = build_nodal_load_update(
                NodalLoadDef(
                    name=original.name,
                    target_name=getattr(original, "target_name", ""),
                    target_type=getattr(original, "target_type", "node_set"),
                    scope_name=getattr(original, "scope_name", None),
                    components=dict(getattr(original, "components", {"FX": 0.0})),
                    parameters=dict(getattr(original, "parameters", {})),
                ),
                target_name_text=target_name_text,
                target_type=target_type,
                scope_name_text=scope_name_text,
                components_text=components_text,
            )
            model.nodal_loads[name] = updated
        else:
            updated = build_distributed_load_update(
                DistributedLoadDef(
                    name=original.name,
                    target_name=getattr(original, "target_name", ""),
                    target_type=self._default_target_type_for_load("distributed_load", target_type=getattr(original, "target_type", None)),
                    scope_name=getattr(original, "scope_name", None),
                    load_type=getattr(original, "load_type", "pressure"),
                    components=dict(getattr(original, "components", {"P": 0.0})),
                    parameters=dict(getattr(original, "parameters", {})),
                ),
                target_name_text=target_name_text,
                target_type=target_type,
                scope_name_text=scope_name_text,
                load_type=load_type,
                load_value_text=load_value_text,
            )
            model.distributed_loads[name] = updated

        self._assign_object_to_step(model, name, normalized_load_kind, self._normalize_optional_text(step_name))
        return self._commit(model)

    def apply_boundary_editor_update(
        self,
        name: str,
        *,
        creating: bool = False,
        step_name: str | None,
        target_name_text: str,
        target_type: str,
        scope_name_text: str,
        dof_values_text: str,
    ) -> GuiModelSummary:
        """写回边界编辑弹窗的正式更新。"""

        model = self._copy_model()
        if creating and name not in model.boundaries:
            model.boundaries[name] = BoundaryDef(name=name, target_name="", target_type="node_set", dof_values={"UX": 0.0})
        model.boundaries[name] = build_boundary_update(
            model.boundaries[name],
            target_name_text=target_name_text,
            target_type=target_type,
            scope_name_text=scope_name_text,
            dof_values_text=dof_values_text,
        )
        self._assign_object_to_step(model, name, "boundary", self._normalize_optional_text(step_name))
        return self._commit(model)

    def apply_output_request_update(
        self,
        name: str,
        *,
        request_mode: str,
        variables_text: str,
        target_type: str,
        target_name_text: str,
        scope_name_text: str,
        position: str,
        frequency_text: str,
    ) -> GuiModelSummary:
        """写回输出请求更新。"""

        model = self._copy_model()
        model.output_requests[name] = build_output_request_update(
            model.output_requests[name],
            request_mode=request_mode,
            variables_text=variables_text,
            target_type=target_type,
            target_name_text=target_name_text,
            scope_name_text=scope_name_text,
            position=position,
            frequency_text=frequency_text,
        )
        return self._commit(model)

    def apply_section_update(
        self,
        name: str,
        *,
        material_name_text: str,
        region_name_text: str,
        scope_name_text: str,
        primary_value_text: str,
        secondary_value_text: str,
        thickness_text: str,
    ) -> GuiModelSummary:
        """写回截面更新。"""

        model = self._copy_model()
        model.sections[name] = build_section_update(
            model.sections[name],
            material_name_text=material_name_text,
            region_name_text=region_name_text,
            scope_name_text=scope_name_text,
            primary_value_text=primary_value_text,
            secondary_value_text=secondary_value_text,
            thickness_text=thickness_text,
        )
        return self._commit(model)

    def apply_instance_transform_update(
        self,
        name: str,
        *,
        translation_text: str,
        rotation_rows: tuple[str, ...],
    ) -> GuiModelSummary:
        """写回实例放置变换。"""

        model = self._copy_model()
        if model.assembly is None:
            raise ModelValidationError("当前模型不包含装配实例。")
        model.assembly.instances[name] = build_instance_transform_update(
            model.assembly.instances[name],
            translation_text=translation_text,
            rotation_rows=rotation_rows,
        )
        return self._commit(model)

    def output_semantics_message(self, name: str) -> str:
        """返回输出请求的最小语义说明。"""

        model = self._copy_model()
        return summarize_output_request_semantics(model, model.output_requests[name]).message

    def _commit(self, model: ModelDB) -> GuiModelSummary:
        model.validate()
        return self._shell.replace_loaded_model(model, mark_dirty=True)

    def _copy_model(self) -> ModelDB:
        return self._shell.clone_loaded_model()

    def _build_owner_label(self, model: ModelDB, resolved_kind: str, name: str) -> str:
        if resolved_kind == "step":
            return f"job={', '.join(self.step_reference_jobs(name)) or '-'}"
        if resolved_kind == "instance":
            if model.assembly is None:
                return "assembly=(none)"
            instance = model.assembly.instances[name]
            return f"assembly={model.assembly.name}, part={instance.part_name}"
        if resolved_kind == "material":
            section_names = tuple(
                section.name
                for section in model.sections.values()
                if section.material_name == name
            )
            return f"sections={', '.join(section_names) or '-'}"
        if resolved_kind == "section":
            section = model.sections[name]
            return f"material={section.material_name or '-'}, scope={section.scope_name or '-'}"
        if resolved_kind == "boundary":
            boundary = model.boundaries[name]
            return f"target={boundary.target_name}, scope={boundary.scope_name or '-'}"
        if resolved_kind == "nodal_load":
            load = model.nodal_loads[name]
            return f"target={load.target_name}, scope={load.scope_name or '-'}"
        if resolved_kind == "distributed_load":
            load = model.distributed_loads[name]
            return f"target={load.target_name}, scope={load.scope_name or '-'}"
        if resolved_kind == "output_request":
            request = model.output_requests[name]
            return f"target={request.target_type}:{request.target_name or '-'}, scope={request.scope_name or '-'}"
        return "-"

    def _collect_related_run_issues(
        self,
        model: ModelDB,
        resolved_kind: str,
        name: str,
    ) -> tuple[CapabilityIssue, ...]:
        related_issues: list[CapabilityIssue] = []
        for issue in collect_run_capability_issues(model):
            if issue.object_name == name:
                related_issues.append(issue)
                continue
            if resolved_kind == "step" and issue.step_name == name:
                related_issues.append(issue)
                continue
            if resolved_kind == "distributed_load" and name in issue.message:
                related_issues.append(issue)
                continue
        return tuple(related_issues)

    def _assign_object_to_step(
        self,
        model: ModelDB,
        name: str,
        resolved_kind: str,
        step_name: str | None,
    ) -> None:
        """将对象重新绑定到指定步骤，并清理旧引用。"""

        for step in model.steps.values():
            if resolved_kind == "boundary":
                step.boundary_names = tuple(item for item in step.boundary_names if item != name)
                continue
            if resolved_kind == "nodal_load":
                step.nodal_load_names = tuple(item for item in step.nodal_load_names if item != name)
                step.distributed_load_names = tuple(item for item in step.distributed_load_names if item != name)
                continue
            if resolved_kind == "distributed_load":
                step.nodal_load_names = tuple(item for item in step.nodal_load_names if item != name)
                step.distributed_load_names = tuple(item for item in step.distributed_load_names if item != name)

        if step_name is None:
            return
        if step_name not in model.steps:
            raise ModelValidationError(f"步骤 {step_name} 不存在。")
        step = model.steps[step_name]
        if resolved_kind == "boundary":
            step.boundary_names = tuple(dict.fromkeys((*step.boundary_names, name)))
        elif resolved_kind == "nodal_load":
            step.nodal_load_names = tuple(dict.fromkeys((*step.nodal_load_names, name)))
        elif resolved_kind == "distributed_load":
            step.distributed_load_names = tuple(dict.fromkeys((*step.distributed_load_names, name)))

    def _normalize_load_kind(self, load_kind: str) -> str:
        """归一化载荷类型键。"""

        normalized_kind = str(load_kind).strip().lower()
        if normalized_kind not in {"nodal_load", "distributed_load"}:
            raise ModelValidationError(f"Unsupported load kind: {load_kind}")
        return normalized_kind

    def _default_target_type_for_load(self, load_kind: str, *, target_type: str | None) -> str:
        """返回载荷类型对应的默认目标类型。"""

        normalized_target_type = str(target_type or "").strip().lower()
        if load_kind == "distributed_load":
            return normalized_target_type or "surface"
        return normalized_target_type or "node_set"

    def _build_load_manager_label(self, name: str, resolved_kind: str, step_names: tuple[str, ...]) -> str:
        """构建载荷管理器列表显示标签。"""

        type_label = "Nodal" if resolved_kind == "nodal_load" else "Distributed"
        return f"{name} [{type_label}]  step={', '.join(step_names) or '-'}"

    def _build_boundary_manager_label(self, name: str, step_names: tuple[str, ...]) -> str:
        """构建边界管理器列表显示标签。"""

        return f"{name} [Boundary]  step={', '.join(step_names) or '-'}"

    def _build_step_manager_label(self, name: str, procedure_type: str, job_names: tuple[str, ...]) -> str:
        """构建步骤管理器列表显示标签。"""

        return f"{name} [{self._format_step_type_label(procedure_type)}]  job={', '.join(job_names) or '-'}"

    def _default_section_parameters(self, section_type: str) -> dict[str, float]:
        """返回新截面的默认参数。"""

        if section_type == "beam":
            return {"area": 1.0, "moment_inertia_z": 1.0}
        if section_type in {"plane_stress", "plane_strain"}:
            return {"thickness": 1.0}
        return {}

    def _suggest_unique_name(self, prefix: str, existing_names: tuple[str, ...]) -> str:
        """按统一规则生成唯一名称。"""

        index = 1
        candidate_name = f"{prefix}-{index}"
        existing_name_set = set(existing_names)
        while candidate_name in existing_name_set:
            index += 1
            candidate_name = f"{prefix}-{index}"
        return candidate_name

    def _validate_new_name(self, name: str, existing_names: tuple[str, ...], *, label: str) -> str:
        """校验新建对象名称。"""

        normalized_name = self._require_non_empty_text(name, field_name=f"{label}名称")
        if normalized_name in existing_names:
            raise ModelValidationError(f"{label} {normalized_name} 已存在。")
        return normalized_name

    def _validate_renamed_name(
        self,
        source_name: str,
        target_name: str,
        existing_names: tuple[str, ...],
        *,
        label: str,
    ) -> str | None:
        """校验重命名目标名称。"""

        normalized_name = self._require_non_empty_text(target_name, field_name=f"{label}名称")
        if normalized_name == source_name:
            return None
        if normalized_name in existing_names:
            raise ModelValidationError(f"{label} {normalized_name} 已存在。")
        return normalized_name

    def _require_non_empty_text(self, text: str | None, *, field_name: str) -> str:
        """校验必填文本。"""

        normalized_text = str(text or "").strip()
        if not normalized_text:
            raise ModelValidationError(f"{field_name} 不能为空。")
        return normalized_text

    def _normalize_optional_text(self, text: str | None) -> str | None:
        """归一化可选文本。"""

        normalized_text = str(text or "").strip()
        return normalized_text or None

    def _normalize_step_procedure_type(self, procedure_type: str) -> str:
        """归一化步骤类型关键字。"""

        normalized_type = str(procedure_type).strip().lower()
        aliases = {
            "static": "static_linear",
            "static_linear": "static_linear",
            "static_nonlinear": "static_nonlinear",
            "modal": "modal",
            "dynamic": "implicit_dynamic",
            "implicit_dynamic": "implicit_dynamic",
        }
        try:
            return aliases[normalized_type]
        except KeyError as error:
            raise ModelValidationError(f"Unsupported step procedure type: {procedure_type}") from error

    def _format_step_type_label(self, procedure_type: str) -> str:
        """返回步骤类型的人类可读标签。"""

        normalized_type = self._normalize_step_procedure_type(procedure_type)
        labels = {
            "static_linear": "Static Linear",
            "static_nonlinear": "Static Nonlinear",
            "modal": "Modal",
            "implicit_dynamic": "Implicit Dynamic",
        }
        return labels[normalized_type]
