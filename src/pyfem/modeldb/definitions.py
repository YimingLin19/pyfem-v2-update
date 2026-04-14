"""模型定义层的基础对象。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Metadata:
    """定义模型级元数据。"""

    version: str = "2.0"
    description: str = ""
    unit_system: str | None = None
    author: str | None = None
    tags: tuple[str, ...] = ()
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将元数据序列化为字典。"""

        return {
            "version": self.version,
            "description": self.description,
            "unit_system": self.unit_system,
            "author": self.author,
            "tags": list(self.tags),
            "extras": dict(self.extras),
        }


@dataclass(slots=True)
class MaterialDef:
    """定义材料输入对象。"""

    name: str
    material_type: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将材料定义序列化为字典。"""

        return {"name": self.name, "material_type": self.material_type, "parameters": dict(self.parameters)}


@dataclass(slots=True)
class SectionDef:
    """定义截面输入对象。"""

    name: str
    section_type: str
    material_name: str | None = None
    region_name: str | None = None
    scope_name: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将截面定义序列化为字典。"""

        return {
            "name": self.name,
            "section_type": self.section_type,
            "material_name": self.material_name,
            "region_name": self.region_name,
            "scope_name": self.scope_name,
            "parameters": dict(self.parameters),
        }


@dataclass(slots=True)
class BoundaryDef:
    """定义位移边界条件输入对象。"""

    name: str
    target_name: str
    dof_values: dict[str, float]
    target_type: str = "node_set"
    scope_name: str | None = None
    boundary_type: str = "displacement"
    parameters: dict[str, Any] = field(default_factory=dict)

    @property
    def constraint_type(self) -> str:
        """返回兼容旧接口的约束类型名称。"""

        return self.boundary_type

    def to_dict(self) -> dict[str, Any]:
        """将边界条件定义序列化为字典。"""

        return {
            "name": self.name,
            "target_name": self.target_name,
            "target_type": self.target_type,
            "scope_name": self.scope_name,
            "boundary_type": self.boundary_type,
            "dof_values": dict(self.dof_values),
            "parameters": dict(self.parameters),
        }


@dataclass(slots=True)
class NodalLoadDef:
    """定义节点载荷输入对象。"""

    name: str
    target_name: str
    components: dict[str, float]
    target_type: str = "node_set"
    scope_name: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将节点载荷定义序列化为字典。"""

        return {
            "name": self.name,
            "target_name": self.target_name,
            "target_type": self.target_type,
            "scope_name": self.scope_name,
            "components": dict(self.components),
            "parameters": dict(self.parameters),
        }


@dataclass(slots=True)
class DistributedLoadDef:
    """定义分布载荷输入对象。"""

    name: str
    target_name: str
    load_type: str
    components: dict[str, float]
    target_type: str = "surface"
    scope_name: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将分布载荷定义序列化为字典。"""

        return {
            "name": self.name,
            "target_name": self.target_name,
            "target_type": self.target_type,
            "scope_name": self.scope_name,
            "load_type": self.load_type,
            "components": dict(self.components),
            "parameters": dict(self.parameters),
        }


@dataclass(slots=True)
class InteractionDef:
    """定义相互作用输入对象。"""

    name: str
    interaction_type: str
    scope_name: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将相互作用定义序列化为字典。"""

        return {
            "name": self.name,
            "interaction_type": self.interaction_type,
            "scope_name": self.scope_name,
            "parameters": dict(self.parameters),
        }


@dataclass(slots=True)
class OutputRequest:
    """定义结果输出请求。"""

    name: str
    variables: tuple[str, ...]
    target_type: str = "model"
    target_name: str | None = None
    scope_name: str | None = None
    position: str = "node"
    frequency: int = 1
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将输出请求序列化为字典。"""

        return {
            "name": self.name,
            "variables": list(self.variables),
            "target_type": self.target_type,
            "target_name": self.target_name,
            "scope_name": self.scope_name,
            "position": self.position,
            "frequency": self.frequency,
            "parameters": dict(self.parameters),
        }


@dataclass(slots=True)
class StepDef:
    """定义分析步骤输入对象。"""

    name: str
    procedure_type: str = ""
    boundary_names: tuple[str, ...] = ()
    nodal_load_names: tuple[str, ...] = ()
    distributed_load_names: tuple[str, ...] = ()
    output_request_names: tuple[str, ...] = ()
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将步骤定义序列化为字典。"""

        return {
            "name": self.name,
            "procedure_type": self.procedure_type,
            "boundary_names": list(self.boundary_names),
            "nodal_load_names": list(self.nodal_load_names),
            "distributed_load_names": list(self.distributed_load_names),
            "output_request_names": list(self.output_request_names),
            "parameters": dict(self.parameters),
        }


@dataclass(slots=True)
class RawKeywordBlockDef:
    """定义受控 raw keyword / extension block。"""

    name: str
    keyword: str
    placement: str = "before_steps"
    step_name: str | None = None
    options: dict[str, str] = field(default_factory=dict)
    data_lines: tuple[str, ...] = ()
    order: int = 0
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """将 raw keyword block 序列化为字典。"""

        return {
            "name": self.name,
            "keyword": self.keyword,
            "placement": self.placement,
            "step_name": self.step_name,
            "options": dict(self.options),
            "data_lines": list(self.data_lines),
            "order": self.order,
            "description": self.description,
        }


@dataclass(slots=True)
class JobDef:
    """定义作业输入对象。"""

    name: str
    step_names: tuple[str, ...]
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将作业定义序列化为字典。"""

        return {"name": self.name, "step_names": list(self.step_names), "parameters": dict(self.parameters)}


@dataclass(slots=True)
class ProcedureDefinition:
    """定义兼容旧接口的过程容器。"""

    name: str
    procedure_type: str
    steps: list[StepDef] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)

    def add_step(self, step: StepDef) -> None:
        """向兼容过程容器中添加步骤定义。"""

        self.steps.append(step)

    def to_step_definitions(self) -> tuple[StepDef, ...]:
        """将兼容过程容器转换为正式步骤定义集合。"""

        if not self.steps:
            return (
                StepDef(
                    name=self.name,
                    procedure_type=self.procedure_type,
                    parameters=dict(self.parameters),
                ),
            )

        compiled_steps: list[StepDef] = []
        for step in self.steps:
            compiled_steps.append(
                StepDef(
                    name=step.name,
                    procedure_type=step.procedure_type or self.procedure_type,
                    boundary_names=tuple(step.boundary_names),
                    nodal_load_names=tuple(step.nodal_load_names),
                    distributed_load_names=tuple(step.distributed_load_names),
                    output_request_names=tuple(step.output_request_names),
                    parameters={**self.parameters, **step.parameters},
                )
            )
        return tuple(compiled_steps)

    def to_dict(self) -> dict[str, Any]:
        """将兼容过程容器序列化为字典。"""

        return {
            "name": self.name,
            "procedure_type": self.procedure_type,
            "steps": [step.to_dict() for step in self.steps],
            "parameters": dict(self.parameters),
        }


MaterialDefinition = MaterialDef
SectionDefinition = SectionDef
ConstraintDefinition = BoundaryDef
InteractionDefinition = InteractionDef
StepDefinition = StepDef
