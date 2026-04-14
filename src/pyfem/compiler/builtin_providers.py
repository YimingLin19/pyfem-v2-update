"""Phase 1 内置运行时提供者。"""

from __future__ import annotations

from pyfem.compiler.requests import (
    ConstraintBuildRequest,
    ElementBuildRequest,
    InteractionBuildRequest,
    MaterialBuildRequest,
    SectionBuildRequest,
)
from pyfem.foundation.errors import CompilationError
from pyfem.kernel.constraints import ConstraintRuntime, DisplacementConstraintRuntime
from pyfem.kernel.elements import B21Runtime, C3D8Runtime, CPS4Runtime, ElementRuntime
from pyfem.kernel.interactions import InteractionRuntime, NoOpInteractionRuntime
from pyfem.kernel.materials import ElasticIsotropicRuntime, J2PlasticityRuntime, MaterialRuntime
from pyfem.kernel.sections import (
    BeamSectionRuntime,
    PlaneStrainSectionRuntime,
    PlaneStressSectionRuntime,
    SectionRuntime,
    SolidSectionRuntime,
)


class ElasticIsotropicProvider:
    """构建各向同性线弹性材料运行时。"""

    def build(self, request: MaterialBuildRequest) -> MaterialRuntime:
        parameters = request.definition.parameters
        young_modulus = float(parameters.get("young_modulus", parameters.get("elastic_modulus", parameters.get("e"))))
        poisson_ratio = float(parameters.get("poisson_ratio", parameters.get("nu")))
        density = float(parameters.get("density", 0.0))
        return ElasticIsotropicRuntime(
            name=request.definition.name,
            young_modulus=young_modulus,
            poisson_ratio=poisson_ratio,
            density=density,
        )


class J2PlasticityProvider:
    """构建小变形 J2 各向同性硬化材料运行时。"""

    def build(self, request: MaterialBuildRequest) -> MaterialRuntime:
        parameters = request.definition.parameters
        return J2PlasticityRuntime(
            name=request.definition.name,
            young_modulus=float(parameters.get("young_modulus", parameters.get("elastic_modulus", parameters.get("e")))),
            poisson_ratio=float(parameters.get("poisson_ratio", parameters.get("nu"))),
            yield_stress=float(parameters.get("yield_stress")),
            hardening_modulus=float(parameters.get("hardening_modulus", 0.0)),
            density=float(parameters.get("density", 0.0)),
            tangent_mode=str(parameters.get("tangent_mode", "consistent")).strip().lower(),
        )


class SolidSectionProvider:
    """构建实体截面运行时。"""

    def build(self, request: SectionBuildRequest) -> SectionRuntime:
        material_runtime = _resolve_material_runtime(request)
        return SolidSectionRuntime(
            name=request.definition.name,
            material_runtime=material_runtime,
            parameters=dict(request.definition.parameters),
        )


class PlaneStressSectionProvider:
    """构建平面应力截面运行时。"""

    def build(self, request: SectionBuildRequest) -> SectionRuntime:
        material_runtime = _resolve_material_runtime(request)
        return PlaneStressSectionRuntime(
            name=request.definition.name,
            material_runtime=material_runtime,
            thickness=float(request.definition.parameters.get("thickness", 1.0)),
            parameters=dict(request.definition.parameters),
        )


class PlaneStrainSectionProvider:
    """构建平面应变截面运行时。"""

    def build(self, request: SectionBuildRequest) -> SectionRuntime:
        material_runtime = _resolve_material_runtime(request)
        return PlaneStrainSectionRuntime(
            name=request.definition.name,
            material_runtime=material_runtime,
            thickness=float(request.definition.parameters.get("thickness", 1.0)),
            parameters=dict(request.definition.parameters),
        )


class BeamSectionProvider:
    """构建梁截面运行时。"""

    def build(self, request: SectionBuildRequest) -> SectionRuntime:
        material_runtime = _resolve_material_runtime(request)
        parameters = request.definition.parameters
        area = float(parameters.get("area"))
        moment_inertia_z = float(parameters.get("moment_inertia_z", parameters.get("iz")))
        shear_factor = float(parameters.get("shear_factor", 1.0))
        return BeamSectionRuntime(
            name=request.definition.name,
            material_runtime=material_runtime,
            area=area,
            moment_inertia_z=moment_inertia_z,
            shear_factor=shear_factor,
            parameters=dict(parameters),
        )


class C3D8Provider:
    """构建 C3D8 单元运行时。"""

    def build(self, request: ElementBuildRequest) -> ElementRuntime:
        if not isinstance(request.section_runtime, SolidSectionRuntime):
            raise CompilationError(f"单元 {request.location.qualified_name} 需要 SolidSectionRuntime。")
        return C3D8Runtime(
            location=request.location,
            coordinates=tuple(tuple(record.coordinates) for record in request.node_records),
            node_names=request.element.node_names,
            dof_indices=request.dof_indices,
            section_runtime=request.section_runtime,
            material_runtime=request.material_runtime,
        )


class CPS4Provider:
    """构建 CPS4 单元运行时。"""

    def build(self, request: ElementBuildRequest) -> ElementRuntime:
        if not isinstance(request.section_runtime, (PlaneStressSectionRuntime, PlaneStrainSectionRuntime)):
            raise CompilationError(f"单元 {request.location.qualified_name} 需要平面截面运行时。")
        if isinstance(request.section_runtime, PlaneStressSectionRuntime) and isinstance(request.material_runtime, J2PlasticityRuntime):
            raise CompilationError(
                f"单元 {request.location.qualified_name} 当前仅支持 PlaneStrainSection + J2 或 SolidSection + J2，"
                "暂不支持 PlaneStressSection + J2。"
            )
        return CPS4Runtime(
            location=request.location,
            coordinates=tuple(tuple(record.coordinates[:2]) for record in request.node_records),
            node_names=request.element.node_names,
            dof_indices=request.dof_indices,
            section_runtime=request.section_runtime,
            material_runtime=request.material_runtime,
        )


class B21Provider:
    """构建 B21 单元运行时。"""

    def build(self, request: ElementBuildRequest) -> ElementRuntime:
        if not isinstance(request.section_runtime, BeamSectionRuntime):
            raise CompilationError(f"单元 {request.location.qualified_name} 需要 BeamSectionRuntime。")
        return B21Runtime(
            location=request.location,
            coordinates=tuple(tuple(record.coordinates[:2]) for record in request.node_records),
            node_names=request.element.node_names,
            dof_indices=request.dof_indices,
            section_runtime=request.section_runtime,
            material_runtime=request.material_runtime,
        )


class DisplacementConstraintProvider:
    """构建位移边界条件运行时。"""

    def build(self, request: ConstraintBuildRequest) -> ConstraintRuntime:
        return DisplacementConstraintRuntime(
            name=request.definition.name,
            boundary_type=request.definition.boundary_type,
            target_name=request.definition.target_name,
            target_type=request.definition.target_type,
            scope_name=request.definition.scope_name,
            constrained_dofs=request.constrained_dofs,
            dof_values=dict(request.definition.dof_values),
            parameters=dict(request.definition.parameters),
        )


class NoOpInteractionProvider:
    """构建最小 no-op 相互作用运行时。"""

    def build(self, request: InteractionBuildRequest) -> InteractionRuntime:
        return NoOpInteractionRuntime(
            name=request.definition.name,
            interaction_type=request.definition.interaction_type,
            scope_name=request.definition.scope_name,
            parameters=dict(request.definition.parameters),
        )


def register_builtin_runtime_providers(registry) -> None:
    """向注册表中写入 Phase 1 内置 provider。"""

    registry.register_material("linear_elastic", ElasticIsotropicProvider())
    registry.register_material("elastic_isotropic", ElasticIsotropicProvider())
    registry.register_material("j2_plastic", J2PlasticityProvider())
    registry.register_material("j2_plasticity", J2PlasticityProvider())
    registry.register_section("solid", SolidSectionProvider())
    registry.register_section("plane_stress", PlaneStressSectionProvider())
    registry.register_section("plane_strain", PlaneStrainSectionProvider())
    registry.register_section("beam", BeamSectionProvider())
    registry.register_element("C3D8", C3D8Provider())
    registry.register_element("CPS4", CPS4Provider())
    registry.register_element("B21", B21Provider())
    registry.register_constraint("displacement", DisplacementConstraintProvider())
    registry.register_interaction("noop", NoOpInteractionProvider())
    registry.register_interaction("none", NoOpInteractionProvider())


def _resolve_material_runtime(request: SectionBuildRequest) -> MaterialRuntime:
    material_name = request.definition.material_name
    if material_name is None:
        raise CompilationError(f"截面 {request.definition.name} 缺少材料名称。")
    try:
        return request.material_runtimes[material_name]
    except KeyError as error:
        raise CompilationError(f"截面 {request.definition.name} 未找到材料运行时 {material_name}。") from error
