"""模型数据库对象。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pyfem.foundation.errors import ModelValidationError
from pyfem.mesh import Assembly, Part, RigidTransform
from pyfem.modeldb.definitions import (
    BoundaryDef,
    DistributedLoadDef,
    InteractionDef,
    JobDef,
    MaterialDef,
    Metadata,
    NodalLoadDef,
    OutputRequest,
    ProcedureDefinition,
    RawKeywordBlockDef,
    SectionDef,
    StepDef,
)
from pyfem.modeldb.scopes import CompilationScope


@dataclass(slots=True)
class ModelDB:
    """作为问题定义唯一来源的模型数据库。"""

    name: str
    metadata: Metadata = field(default_factory=Metadata)
    parts: dict[str, Part] = field(default_factory=dict)
    assembly: Assembly | None = None
    materials: dict[str, MaterialDef] = field(default_factory=dict)
    sections: dict[str, SectionDef] = field(default_factory=dict)
    boundaries: dict[str, BoundaryDef] = field(default_factory=dict)
    nodal_loads: dict[str, NodalLoadDef] = field(default_factory=dict)
    distributed_loads: dict[str, DistributedLoadDef] = field(default_factory=dict)
    interactions: dict[str, InteractionDef] = field(default_factory=dict)
    output_requests: dict[str, OutputRequest] = field(default_factory=dict)
    steps: dict[str, StepDef] = field(default_factory=dict)
    raw_keyword_blocks: dict[str, RawKeywordBlockDef] = field(default_factory=dict)
    job: JobDef | None = None

    @property
    def version(self) -> str:
        """返回模型版本号。"""

        return self.metadata.version

    @property
    def constraints(self) -> dict[str, BoundaryDef]:
        """返回兼容旧接口的约束字典。"""

        return self.boundaries

    @property
    def procedures(self) -> dict[str, StepDef]:
        """返回兼容旧接口的过程字典。"""

        return self.steps

    def add_part(self, part: Part) -> None:
        """向模型数据库中注册部件定义。"""

        self._ensure_absent(self.parts, part.name, "部件")
        self.parts[part.name] = part

    def get_part(self, part_name: str) -> Part:
        """按名称获取部件定义。"""

        try:
            return self.parts[part_name]
        except KeyError as error:
            raise ModelValidationError(f"模型 {self.name} 中不存在部件 {part_name}。") from error

    def set_assembly(self, assembly: Assembly) -> None:
        """设置模型装配定义。"""

        self.assembly = assembly

    def add_material(self, definition: MaterialDef) -> None:
        """向模型数据库中注册材料定义。"""

        self._ensure_absent(self.materials, definition.name, "材料")
        self.materials[definition.name] = definition

    def add_section(self, definition: SectionDef) -> None:
        """向模型数据库中注册截面定义。"""

        self._ensure_absent(self.sections, definition.name, "截面")
        self.sections[definition.name] = definition

    def add_boundary(self, definition: BoundaryDef) -> None:
        """向模型数据库中注册边界条件定义。"""

        self._ensure_absent(self.boundaries, definition.name, "边界条件")
        self.boundaries[definition.name] = definition

    def add_constraint(self, definition: BoundaryDef) -> None:
        """向模型数据库中注册兼容旧接口的约束定义。"""

        self.add_boundary(definition)

    def add_nodal_load(self, definition: NodalLoadDef) -> None:
        """向模型数据库中注册节点载荷定义。"""

        self._ensure_absent(self.nodal_loads, definition.name, "节点载荷")
        self.nodal_loads[definition.name] = definition

    def add_distributed_load(self, definition: DistributedLoadDef) -> None:
        """向模型数据库中注册分布载荷定义。"""

        self._ensure_absent(self.distributed_loads, definition.name, "分布载荷")
        self.distributed_loads[definition.name] = definition

    def add_interaction(self, definition: InteractionDef) -> None:
        """向模型数据库中注册相互作用定义。"""

        self._ensure_absent(self.interactions, definition.name, "相互作用")
        self.interactions[definition.name] = definition

    def add_output_request(self, definition: OutputRequest) -> None:
        """向模型数据库中注册输出请求定义。"""

        self._ensure_absent(self.output_requests, definition.name, "输出请求")
        self.output_requests[definition.name] = definition

    def add_step(self, definition: StepDef) -> None:
        """向模型数据库中注册分析步骤定义。"""

        self._ensure_absent(self.steps, definition.name, "分析步骤")
        self.steps[definition.name] = definition

    def add_raw_keyword_block(self, definition: RawKeywordBlockDef) -> None:
        """向模型数据库中注册受控 raw keyword block。"""

        self._ensure_absent(self.raw_keyword_blocks, definition.name, "raw keyword block")
        self.raw_keyword_blocks[definition.name] = definition

    def add_procedure(self, definition: ProcedureDefinition) -> None:
        """向模型数据库中注册兼容旧接口的过程定义。"""

        for step in definition.to_step_definitions():
            self.add_step(step)

    def set_job(self, definition: JobDef) -> None:
        """设置当前模型的作业定义。"""

        self.job = definition

    def iter_compilation_scopes(self) -> tuple[CompilationScope, ...]:
        """返回 canonical compilation scope 集合。"""

        if self.assembly is not None and self.assembly.instances:
            return tuple(
                CompilationScope(
                    scope_name=instance.name,
                    part_name=instance.part_name,
                    part=self.get_part(instance.part_name),
                    transform=instance.transform,
                    instance_name=instance.name,
                    node_sets=self.assembly.node_sets_for_instance(instance.name),
                    element_sets=self.assembly.element_sets_for_instance(instance.name),
                    surfaces=self.assembly.surfaces_for_instance(instance.name),
                )
                for instance in self.assembly.instances.values()
            )
        return tuple(
            CompilationScope(
                scope_name=part.name,
                part_name=part.name,
                part=part,
                transform=RigidTransform(),
                instance_name=None,
            )
            for part in self.parts.values()
        )

    def iter_target_scopes(self, scope_name: str | None = None) -> tuple[CompilationScope, ...]:
        """按 canonical scope 名称解析目标作用域集合。"""

        scopes = self.iter_compilation_scopes()
        if scope_name is None:
            return scopes
        return tuple(scope for scope in scopes if scope.scope_name == scope_name)

    def resolve_compilation_scope(self, scope_name: str) -> CompilationScope | None:
        """按 canonical scope 名称解析单个作用域。"""

        scopes = self.iter_target_scopes(scope_name)
        return scopes[0] if scopes else None

    def validate(self) -> None:
        """校验模型数据库中的定义关系是否完整。"""

        if not self.parts:
            raise ModelValidationError(f"模型 {self.name} 至少需要一个部件定义。")

        for part in self.parts.values():
            part.validate()
            for element in part.elements.values():
                if element.section_name is not None and element.section_name not in self.sections:
                    raise ModelValidationError(
                        f"部件 {part.name} 中单元 {element.name} 引用了不存在的截面 {element.section_name}。"
                    )
                if element.material_name is not None and element.material_name not in self.materials:
                    raise ModelValidationError(
                        f"部件 {part.name} 中单元 {element.name} 引用了不存在的材料 {element.material_name}。"
                    )

        if self.assembly is not None:
            for instance in self.assembly.instances.values():
                if instance.part_name not in self.parts:
                    raise ModelValidationError(f"装配 {self.assembly.name} 引用了不存在的部件 {instance.part_name}。")
                part = self.get_part(instance.part_name)
                instance.transform.resolve_components(part.spatial_dimension())
                self._validate_instance_overlays(instance.name, part)

        for section in self.sections.values():
            if section.scope_name is not None and not self.iter_target_scopes(section.scope_name):
                raise ModelValidationError(f"截面 {section.name} 引用了不存在的作用域 {section.scope_name}。")
            if section.material_name is not None and section.material_name not in self.materials:
                raise ModelValidationError(
                    f"截面 {section.name} 引用了不存在的材料 {section.material_name}。"
                )
            if section.region_name is not None and not self._element_region_exists(section.region_name, section.scope_name):
                raise ModelValidationError(
                    f"截面 {section.name} 引用了不存在的区域 {section.region_name}。"
                )

        for boundary in self.boundaries.values():
            self._validate_target(boundary.name, boundary.target_type, boundary.target_name, boundary.scope_name)

        for load in self.nodal_loads.values():
            self._validate_target(load.name, load.target_type, load.target_name, load.scope_name)

        for load in self.distributed_loads.values():
            self._validate_target(load.name, load.target_type, load.target_name, load.scope_name)

        for interaction in self.interactions.values():
            if interaction.scope_name is not None and not self.iter_target_scopes(interaction.scope_name):
                raise ModelValidationError(f"相互作用 {interaction.name} 引用了不存在的作用域 {interaction.scope_name}。")

        for request in self.output_requests.values():
            if request.target_type != "model":
                if request.target_name is None:
                    raise ModelValidationError(f"输出请求 {request.name} 缺少目标名称。")
                self._validate_target(request.name, request.target_type, request.target_name, request.scope_name)
            elif request.scope_name is not None and not self.iter_target_scopes(request.scope_name):
                raise ModelValidationError(f"输出请求 {request.name} 引用了不存在的作用域 {request.scope_name}。")

        for step in self.steps.values():
            if not step.procedure_type:
                raise ModelValidationError(f"分析步骤 {step.name} 必须给出 procedure_type。")
            for boundary_name in step.boundary_names:
                if boundary_name not in self.boundaries:
                    raise ModelValidationError(f"分析步骤 {step.name} 引用了不存在的边界条件 {boundary_name}。")
            for load_name in step.nodal_load_names:
                if load_name not in self.nodal_loads:
                    raise ModelValidationError(f"分析步骤 {step.name} 引用了不存在的节点载荷 {load_name}。")
            for load_name in step.distributed_load_names:
                if load_name not in self.distributed_loads:
                    raise ModelValidationError(f"分析步骤 {step.name} 引用了不存在的分布载荷 {load_name}。")
            for request_name in step.output_request_names:
                if request_name not in self.output_requests:
                    raise ModelValidationError(f"分析步骤 {step.name} 引用了不存在的输出请求 {request_name}。")

        for block in self.raw_keyword_blocks.values():
            if block.step_name is not None and block.step_name not in self.steps:
                raise ModelValidationError(
                    f"raw keyword block {block.name} 引用了不存在的分析步骤 {block.step_name}。"
                )

        if self.job is not None:
            if not self.job.step_names:
                raise ModelValidationError(f"作业 {self.job.name} 至少需要引用一个分析步骤。")
            for step_name in self.job.step_names:
                if step_name not in self.steps:
                    raise ModelValidationError(f"作业 {self.job.name} 引用了不存在的分析步骤 {step_name}。")

    def to_dict(self) -> dict[str, Any]:
        """将模型数据库序列化为字典。"""

        return {
            "name": self.name,
            "metadata": self.metadata.to_dict(),
            "parts": {name: part.to_dict() for name, part in self.parts.items()},
            "assembly": self.assembly.to_dict() if self.assembly is not None else None,
            "materials": {name: item.to_dict() for name, item in self.materials.items()},
            "sections": {name: item.to_dict() for name, item in self.sections.items()},
            "boundaries": {name: item.to_dict() for name, item in self.boundaries.items()},
            "nodal_loads": {name: item.to_dict() for name, item in self.nodal_loads.items()},
            "distributed_loads": {name: item.to_dict() for name, item in self.distributed_loads.items()},
            "interactions": {name: item.to_dict() for name, item in self.interactions.items()},
            "output_requests": {name: item.to_dict() for name, item in self.output_requests.items()},
            "steps": {name: item.to_dict() for name, item in self.steps.items()},
            "raw_keyword_blocks": {name: item.to_dict() for name, item in self.raw_keyword_blocks.items()},
            "job": self.job.to_dict() if self.job is not None else None,
        }

    def _ensure_absent(self, mapping: dict[str, object], item_name: str, label: str) -> None:
        if item_name in mapping:
            raise ModelValidationError(f"模型 {self.name} 中已存在{label} {item_name}。")

    def _validate_target(
        self,
        definition_name: str,
        target_type: str,
        target_name: str | None,
        scope_name: str | None,
    ) -> None:
        if not self._target_exists(target_type, target_name, scope_name):
            raise ModelValidationError(
                f"定义 {definition_name} 引用了不存在的目标 {target_type}:{target_name}。"
            )

    def _target_exists(self, target_type: str, target_name: str | None, scope_name: str | None) -> bool:
        if target_type == "model":
            return bool(self.iter_target_scopes(scope_name)) if scope_name is not None else bool(self.iter_compilation_scopes())

        for scope in self.iter_target_scopes(scope_name):
            if target_type in {"node", "node_set"} and scope.resolve_node_names(target_type, target_name):
                return True
            if target_type in {"element", "element_set"} and scope.resolve_element_names(target_type, target_name):
                return True
            if target_type == "surface" and target_name is not None and scope.get_surface(target_name) is not None:
                return True

        return False

    def _element_region_exists(self, region_name: str, scope_name: str | None) -> bool:
        for scope in self.iter_target_scopes(scope_name):
            if scope.has_part_element_region(region_name):
                return True
        return False

    def _validate_instance_overlays(self, instance_name: str, part: Part) -> None:
        if self.assembly is None:
            return

        for set_name, node_names in self.assembly.node_sets_for_instance(instance_name).items():
            missing_nodes = [node_name for node_name in node_names if node_name not in part.nodes]
            if missing_nodes:
                joined = ", ".join(missing_nodes[:5])
                raise ModelValidationError(
                    f"装配实例 {instance_name} 的节点集合 {set_name} 引用了不存在的节点: {joined}。"
                )

        for set_name, element_names in self.assembly.element_sets_for_instance(instance_name).items():
            missing_elements = [element_name for element_name in element_names if element_name not in part.elements]
            if missing_elements:
                joined = ", ".join(missing_elements[:5])
                raise ModelValidationError(
                    f"装配实例 {instance_name} 的单元集合 {set_name} 引用了不存在的单元: {joined}。"
                )

        for surface_name, surface in self.assembly.surfaces_for_instance(instance_name).items():
            missing_elements = [facet.element_name for facet in surface.facets if facet.element_name not in part.elements]
            if missing_elements:
                joined = ", ".join(missing_elements[:5])
                raise ModelValidationError(
                    f"装配实例 {instance_name} 的表面 {surface_name} 引用了不存在的单元: {joined}。"
                )
