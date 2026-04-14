"""编译阶段使用的占位运行时对象。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pyfem.foundation.errors import PyFEMError
from pyfem.foundation.types import ElementLocation, Matrix, StateMap, Vector
from pyfem.io.results import ResultsWriter
from pyfem.kernel.constraints import ConstrainedDof, ConstraintRuntime
from pyfem.kernel.elements import ElementContribution, ElementRuntime
from pyfem.kernel.interactions import InteractionRuntime
from pyfem.kernel.materials import MaterialRuntime, MaterialUpdateResult
from pyfem.kernel.sections import SectionRuntime
from pyfem.procedures.base import ProcedureReport, ProcedureRuntime


def _build_zero_matrix(size: int) -> Matrix:
    """构造指定阶数的零矩阵。"""

    return tuple(tuple(0.0 for _ in range(size)) for _ in range(size))


def _build_zero_vector(size: int) -> Vector:
    """构造指定长度的零向量。"""

    return tuple(0.0 for _ in range(size))


@dataclass(slots=True)
class MaterialRuntimePlaceholder(MaterialRuntime):
    """定义材料运行时占位对象。"""

    name: str
    material_type: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def get_name(self) -> str:
        """返回材料运行时名称。"""

        return self.name

    def get_material_type(self) -> str:
        """返回材料运行时类型。"""

        return self.material_type

    def allocate_state(self) -> dict[str, Any]:
        """分配占位材料状态容器。"""

        return {
            "strain": (),
            "stress": (),
            "mode": None,
            "strain_measure": "unspecified",
            "stress_measure": "unspecified",
            "tangent_measure": "unspecified",
        }

    def update(self, strain: Vector, state: StateMap | None = None, mode: str = "3d") -> MaterialUpdateResult:
        """返回占位材料的零应力与零切线。"""

        size = len(strain)
        next_state = dict(state) if state is not None else self.allocate_state()
        next_state["strain"] = tuple(strain)
        next_state["stress"] = _build_zero_vector(size)
        next_state["mode"] = mode
        return MaterialUpdateResult(
            stress=_build_zero_vector(size),
            tangent=_build_zero_matrix(size),
            state=next_state,
            strain=tuple(strain),
        )

    def get_density(self) -> float:
        """返回占位材料密度。"""

        return float(self.parameters.get("density", 0.0))

    def describe(self) -> Mapping[str, Any]:
        """返回材料运行时的可序列化描述。"""

        return {"name": self.name, "material_type": self.material_type, "parameters": dict(self.parameters)}


@dataclass(slots=True)
class SectionRuntimePlaceholder(SectionRuntime):
    """定义截面运行时占位对象。"""

    name: str
    section_type: str
    material_name: str | None = None
    region_name: str | None = None
    scope_name: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)

    def get_name(self) -> str:
        """返回截面运行时名称。"""

        return self.name

    def get_section_type(self) -> str:
        """返回截面运行时类型。"""

        return self.section_type

    def describe(self) -> Mapping[str, Any]:
        """返回截面运行时的可序列化描述。"""

        return {
            "name": self.name,
            "section_type": self.section_type,
            "material_name": self.material_name,
            "region_name": self.region_name,
            "scope_name": self.scope_name,
            "parameters": dict(self.parameters),
        }


@dataclass(slots=True)
class ElementRuntimePlaceholder(ElementRuntime):
    """定义单元运行时占位对象。"""

    location: ElementLocation
    type_key: str
    dof_layout: tuple[str, ...]
    node_names: tuple[str, ...]
    dof_indices: tuple[int, ...]
    material_name: str
    section_name: str

    def get_type_key(self) -> str:
        """返回单元运行时类型键。"""

        return self.type_key

    def get_dof_layout(self) -> tuple[str, ...]:
        """返回单元节点自由度布局。"""

        return self.dof_layout

    def get_location(self) -> ElementLocation:
        """返回单元在编译作用域中的位置。"""

        return self.location

    def get_dof_indices(self) -> tuple[int, ...]:
        """返回单元关联的全局自由度编号。"""

        return self.dof_indices

    def allocate_state(self) -> dict[str, Any]:
        """分配单元级状态容器。"""

        return {}

    def compute_tangent_and_residual(
        self,
        displacement: Vector | None = None,
        state: StateMap | None = None,
    ) -> ElementContribution:
        """计算占位单元的零切线矩阵与零残量向量。"""

        size = len(self.dof_indices)
        return ElementContribution(stiffness=_build_zero_matrix(size), residual=_build_zero_vector(size))

    def compute_mass(self, state: StateMap | None = None) -> Matrix:
        """计算占位单元的零质量矩阵。"""

        return _build_zero_matrix(len(self.dof_indices))

    def compute_damping(self, state: StateMap | None = None) -> Matrix | None:
        """返回占位单元的阻尼矩阵。"""

        return None

    def collect_output(
        self,
        displacement: Vector | None = None,
        state: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """收集占位单元的输出摘要。"""

        return {
            "location": self.location.qualified_name,
            "type_key": self.type_key,
            "node_names": self.node_names,
            "dof_count": len(self.dof_indices),
            "material_name": self.material_name,
            "section_name": self.section_name,
        }


@dataclass(slots=True)
class ConstraintRuntimePlaceholder(ConstraintRuntime):
    """定义边界条件运行时占位对象。"""

    name: str
    boundary_type: str
    target_name: str
    target_type: str
    constrained_dofs: tuple[ConstrainedDof, ...]
    dof_values: dict[str, float] = field(default_factory=dict)

    def get_name(self) -> str:
        """返回约束运行时名称。"""

        return self.name

    def get_constraint_type(self) -> str:
        """返回约束运行时类型。"""

        return self.boundary_type

    def collect_constrained_dofs(self) -> tuple[ConstrainedDof, ...]:
        """返回该约束涉及的自由度集合。"""

        return self.constrained_dofs

    def describe(self) -> Mapping[str, Any]:
        """返回约束运行时的可序列化描述。"""

        return {
            "name": self.name,
            "boundary_type": self.boundary_type,
            "target_name": self.target_name,
            "target_type": self.target_type,
            "constrained_dof_count": len(self.constrained_dofs),
            "dof_values": dict(self.dof_values),
        }


@dataclass(slots=True)
class InteractionRuntimePlaceholder(InteractionRuntime):
    """定义相互作用运行时占位对象。"""

    name: str
    interaction_type: str
    scope_name: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)

    def get_name(self) -> str:
        """返回相互作用运行时名称。"""

        return self.name

    def get_interaction_type(self) -> str:
        """返回相互作用运行时类型。"""

        return self.interaction_type

    def describe(self) -> Mapping[str, Any]:
        """返回相互作用运行时的可序列化描述。"""

        return {
            "name": self.name,
            "interaction_type": self.interaction_type,
            "scope_name": self.scope_name,
            "parameters": dict(self.parameters),
        }


@dataclass(slots=True)
class StepRuntimePlaceholder(ProcedureRuntime):
    """定义分析步骤运行时占位对象。"""

    name: str
    procedure_type: str
    boundary_names: tuple[str, ...] = ()
    nodal_load_names: tuple[str, ...] = ()
    distributed_load_names: tuple[str, ...] = ()
    output_request_names: tuple[str, ...] = ()
    parameters: dict[str, Any] = field(default_factory=dict)

    def get_name(self) -> str:
        """返回步骤名称。"""

        return self.name

    def get_procedure_type(self) -> str:
        """返回步骤过程类型。"""

        return self.procedure_type

    def describe(self) -> Mapping[str, Any]:
        """返回分析步骤运行时的可序列化描述。"""

        return {
            "name": self.name,
            "procedure_type": self.procedure_type,
            "boundary_names": self.boundary_names,
            "nodal_load_names": self.nodal_load_names,
            "distributed_load_names": self.distributed_load_names,
            "output_request_names": self.output_request_names,
            "parameters": dict(self.parameters),
        }

    def run(self, results_writer: ResultsWriter) -> ProcedureReport:
        """提示当前步骤尚未绑定正式 procedure provider。"""

        del results_writer
        raise PyFEMError(f"分析步骤 {self.name} 尚未绑定正式 ProcedureRuntimeProvider。")
