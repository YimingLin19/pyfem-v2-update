"""运行时构建请求对象。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pyfem.foundation.types import ElementLocation, NodeLocation

if TYPE_CHECKING:
    from pyfem.compiler.compiled_model import CompiledModel
    from pyfem.kernel import DofManager
    from pyfem.kernel.constraints import ConstrainedDof
    from pyfem.kernel.materials import MaterialRuntime
    from pyfem.kernel.sections import SectionRuntime
    from pyfem.mesh import ElementRecord, NodeRecord, Part
    from pyfem.modeldb import BoundaryDef, InteractionDef, MaterialDef, ModelDB, SectionDef, StepDef
    from pyfem.modeldb.scopes import CompilationScope


@dataclass(slots=True, frozen=True)
class MaterialBuildRequest:
    """描述构建材料运行时所需的输入。"""

    definition: MaterialDef
    model: ModelDB


@dataclass(slots=True, frozen=True)
class SectionBuildRequest:
    """描述构建截面运行时所需的输入。"""

    definition: SectionDef
    model: ModelDB
    material_runtimes: dict[str, MaterialRuntime]


@dataclass(slots=True, frozen=True)
class ElementBuildRequest:
    """描述构建单元运行时所需的输入。"""

    scope: CompilationScope
    location: ElementLocation
    part: Part
    element: ElementRecord
    node_locations: tuple[NodeLocation, ...]
    node_records: tuple[NodeRecord, ...]
    dof_indices: tuple[int, ...]
    material_runtime: MaterialRuntime
    section_runtime: SectionRuntime
    model: ModelDB
    dof_manager: DofManager


@dataclass(slots=True, frozen=True)
class ConstraintBuildRequest:
    """描述构建约束运行时所需的输入。"""

    definition: BoundaryDef
    model: ModelDB
    compiled_model: CompiledModel
    constrained_dofs: tuple[ConstrainedDof, ...]


@dataclass(slots=True, frozen=True)
class InteractionBuildRequest:
    """描述构建相互作用运行时所需的输入。"""

    definition: InteractionDef
    model: ModelDB
    compiled_model: CompiledModel


@dataclass(slots=True, frozen=True)
class ProcedureBuildRequest:
    """描述构建分析步骤运行时所需的输入。"""

    definition: StepDef
    model: ModelDB
    compiled_model: CompiledModel
