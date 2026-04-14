"""B21 二节点 Euler-Bernoulli 梁单元运行时。"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy

from pyfem.foundation.errors import SolverError
from pyfem.foundation.types import ElementLocation, Matrix, StateMap, Vector
from pyfem.kernel.elements.base import ElementContribution, ElementRuntime
from pyfem.kernel.elements.common import as_matrix, as_vector, gauss_points_2
from pyfem.kernel.materials import MaterialRuntime, MaterialUpdateResult
from pyfem.kernel.sections import BeamSectionRuntime


@dataclass(slots=True, frozen=True)
class CorotationalKinematics:
    """描述 corotational 梁单元当前构形下的核心运动学量。"""

    displacement_vector: numpy.ndarray
    reference_length: float
    current_length: float
    reference_rotation: float
    current_rotation: float
    rigid_rotation: float
    axial_extension: float
    local_rotation_i: float
    local_rotation_j: float
    tangent_vector: numpy.ndarray
    normal_vector: numpy.ndarray
    basic_deformation: numpy.ndarray


@dataclass(slots=True, frozen=True)
class BeamAxialResponse:
    """描述梁单元轴向响应点的材料更新结果。"""

    axial_strain: float
    axial_stress: float
    axial_force: float
    axial_basic_tangent: float
    material_update: MaterialUpdateResult
    point_state: dict[str, Any]


@dataclass(slots=True, frozen=True)
class BeamSectionResponse:
    """描述梁单元 basic deformation 对应的 generalized response。"""

    axial_response: BeamAxialResponse
    basic_force: numpy.ndarray
    basic_tangent: numpy.ndarray


@dataclass(slots=True)
class B21Runtime(ElementRuntime):
    """定义 B21 梁单元运行时，支持 corotational 几何非线性与最小轴向材料耦合。"""

    location: ElementLocation
    coordinates: tuple[tuple[float, float], ...]
    node_names: tuple[str, ...]
    dof_indices: tuple[int, ...]
    section_runtime: BeamSectionRuntime
    material_runtime: MaterialRuntime

    def get_type_key(self) -> str:
        """返回单元运行时类型键。"""

        return "B21"

    def get_dof_layout(self) -> tuple[str, ...]:
        """返回单元节点自由度布局。"""

        return ("UX", "UY", "RZ")

    def get_location(self) -> ElementLocation:
        """返回单元在编译作用域中的位置。"""

        return self.location

    def get_dof_indices(self) -> tuple[int, ...]:
        """返回单元关联的全局自由度编号。"""

        return self.dof_indices

    def get_supported_geometric_nonlinearity_modes(self) -> tuple[str, ...]:
        """返回当前单元支持的几何非线性模式。"""

        return ("corotational",)

    def allocate_state(self) -> dict[str, Any]:
        """分配单元级状态容器。"""

        return {}

    def compute_tangent_and_residual(
        self,
        displacement: Vector | None = None,
        state: StateMap | None = None,
    ) -> ElementContribution:
        """计算单元切线矩阵与内力残量。"""

        displacement_array = self._resolve_displacement(displacement=displacement, state=state)
        if not self._is_nlgeom_enabled(state):
            transformation = self._build_transformation_matrix(self._reference_rotation())
            local_displacement = transformation @ displacement_array
            section_response = self._evaluate_section_response(
                axial_extension=float(local_displacement[3] - local_displacement[0]),
                local_rotation_i=float(local_displacement[2]),
                local_rotation_j=float(local_displacement[5]),
                state=state,
            )
            local_force = self._build_linear_local_internal_force(
                local_displacement=local_displacement,
                section_response=section_response,
            )
            local_tangent = self._build_linear_local_tangent(section_response=section_response)
            return ElementContribution(
                stiffness=as_matrix(transformation.T @ local_tangent @ transformation),
                residual=as_vector(transformation.T @ local_force),
            )

        kinematics = self._build_corotational_kinematics(displacement_array)
        section_response = self._evaluate_section_response(
            axial_extension=kinematics.axial_extension,
            local_rotation_i=kinematics.local_rotation_i,
            local_rotation_j=kinematics.local_rotation_j,
            state=state,
        )
        residual = self._assemble_corotational_internal_force(kinematics, section_response.basic_force)
        tangent = self._build_corotational_tangent(kinematics, section_response)
        return ElementContribution(stiffness=as_matrix(tangent), residual=as_vector(residual))

    def compute_mass(self, state: StateMap | None = None) -> Matrix:
        """计算单元一致质量矩阵。"""

        del state
        length = self._reference_length()
        density = self.material_runtime.get_density()
        area = self.section_runtime.get_area()
        local_mass = density * area * length / 420.0 * numpy.asarray(
            (
                (140.0, 0.0, 0.0, 70.0, 0.0, 0.0),
                (0.0, 156.0, 22.0 * length, 0.0, 54.0, -13.0 * length),
                (0.0, 22.0 * length, 4.0 * length**2, 0.0, 13.0 * length, -3.0 * length**2),
                (70.0, 0.0, 0.0, 140.0, 0.0, 0.0),
                (0.0, 54.0, 13.0 * length, 0.0, 156.0, -22.0 * length),
                (0.0, -13.0 * length, -3.0 * length**2, 0.0, -22.0 * length, 4.0 * length**2),
            ),
            dtype=float,
        )
        transformation = self._build_transformation_matrix(self._reference_rotation())
        return as_matrix(transformation.T @ local_mass @ transformation)

    def compute_damping(self, state: StateMap | None = None) -> Matrix | None:
        """返回阻尼矩阵占位。"""

        del state
        return None

    def collect_output(
        self,
        displacement: Vector | None = None,
        state: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """收集单元输出字段。"""

        displacement_array = self._resolve_displacement(displacement=displacement, state=state)
        if self._is_nlgeom_enabled(state):
            kinematics = self._build_corotational_kinematics(displacement_array)
            section_response = self._resolve_output_section_response(
                axial_extension=kinematics.axial_extension,
                local_rotation_i=kinematics.local_rotation_i,
                local_rotation_j=kinematics.local_rotation_j,
                state=state,
            )
            current_length = kinematics.current_length
            rigid_rotation = kinematics.rigid_rotation
            local_rotation_i = kinematics.local_rotation_i
            local_rotation_j = kinematics.local_rotation_j
            nlgeom_mode = "corotational"
        else:
            transformation = self._build_transformation_matrix(self._reference_rotation())
            local_displacement = transformation @ displacement_array
            section_response = self._resolve_output_section_response(
                axial_extension=float(local_displacement[3] - local_displacement[0]),
                local_rotation_i=float(local_displacement[2]),
                local_rotation_j=float(local_displacement[5]),
                state=state,
            )
            current_length = self._reference_length()
            rigid_rotation = 0.0
            local_rotation_i = float(local_displacement[2])
            local_rotation_j = float(local_displacement[5])
            nlgeom_mode = "linear_small_strain"

        reference_length = self._reference_length()
        section_point_label = self._section_point_label()
        point_state = section_response.axial_response.point_state
        material_state = point_state.get("material_state", {})
        equivalent_plastic_strain = float(material_state.get("equivalent_plastic_strain", 0.0))
        integration_points = []
        for point_index, (xi, weight) in enumerate(gauss_points_2(), start=1):
            integration_points.append(
                {
                    "target_key": self._build_integration_point_key(point_index, section_point_label=section_point_label),
                    "natural_coordinates": (float(xi),),
                    "sample_weight": float(0.5 * reference_length * self.section_runtime.get_area() * weight),
                    "section_point_label": section_point_label,
                    "strain": point_state["strain"],
                    "stress": point_state["stress"],
                    "equivalent_plastic_strain": equivalent_plastic_strain,
                }
            )

        recovery_target_keys = tuple(
            self._build_element_nodal_key(node_name, section_point_label=section_point_label)
            for node_name in self.node_names
        )
        recovery_base_target_keys = {
            target_key: self._build_node_key(node_name)
            for target_key, node_name in zip(recovery_target_keys, self.node_names, strict=True)
        }
        return {
            "type_key": self.get_type_key(),
            "location": self.location.qualified_name,
            "scope_name": self.location.scope_name,
            "node_names": self.node_names,
            "node_keys": tuple(self._build_node_key(node_name) for node_name in self.node_names),
            "section_name": self.section_runtime.get_name(),
            "section_type": self.section_runtime.get_section_type(),
            "material_name": self.material_runtime.get_name(),
            "averaging_weight": float(reference_length * self.section_runtime.get_area()),
            "strain": point_state["strain"],
            "stress": point_state["stress"],
            "axial_strain": float(section_response.axial_response.axial_strain),
            "axial_stress": float(section_response.axial_response.axial_stress),
            "axial_force": float(section_response.axial_response.axial_force),
            "end_moment_i": float(section_response.basic_force[1]),
            "end_moment_j": float(section_response.basic_force[2]),
            "reference_length": float(reference_length),
            "current_length": float(current_length),
            "axial_extension": float(current_length - reference_length),
            "rigid_rotation": float(rigid_rotation),
            "local_rotation_i": float(local_rotation_i),
            "local_rotation_j": float(local_rotation_j),
            "equivalent_plastic_strain": equivalent_plastic_strain,
            "nlgeom_active": self._is_nlgeom_enabled(state),
            "nlgeom_mode": nlgeom_mode,
            "integration_points": tuple(integration_points),
            "recovery": {
                "target_keys": recovery_target_keys,
                "base_target_keys": recovery_base_target_keys,
                "extrapolation_matrix": as_matrix(self._build_extrapolation_matrix()),
                "section_nodal_semantics": "reference_section",
            },
        }

    def _resolve_displacement(self, displacement: Vector | None, state: StateMap | Mapping[str, Any] | None) -> numpy.ndarray:
        if displacement is not None:
            return numpy.asarray(displacement, dtype=float)
        if state is not None and "displacement" in state:
            return numpy.asarray(state["displacement"], dtype=float)
        return numpy.zeros(6, dtype=float)

    def _is_nlgeom_enabled(self, state: StateMap | Mapping[str, Any] | None) -> bool:
        if state is None:
            return False
        analysis_flags = state.get("analysis_flags")
        if not isinstance(analysis_flags, Mapping):
            return False
        return bool(analysis_flags.get("nlgeom", False))

    def _build_corotational_kinematics(self, displacement_array: numpy.ndarray) -> CorotationalKinematics:
        reference_i = numpy.asarray(self.coordinates[0], dtype=float)
        reference_j = numpy.asarray(self.coordinates[1], dtype=float)
        current_i = reference_i + displacement_array[0:2]
        current_j = reference_j + displacement_array[3:5]
        current_vector = current_j - current_i
        current_length = float(numpy.linalg.norm(current_vector))
        if current_length <= 1.0e-12:
            raise SolverError(
                f"单元 {self.location.qualified_name} 的当前长度退化到零附近，无法执行 corotational 更新。"
            )

        tangent_vector = current_vector / current_length
        normal_vector = numpy.asarray((-tangent_vector[1], tangent_vector[0]), dtype=float)
        reference_length = self._reference_length()
        reference_rotation = self._reference_rotation()
        current_rotation = math.atan2(float(current_vector[1]), float(current_vector[0]))
        rigid_rotation = self._normalize_angle(current_rotation - reference_rotation)
        local_rotation_i = self._normalize_angle(float(displacement_array[2]) - rigid_rotation)
        local_rotation_j = self._normalize_angle(float(displacement_array[5]) - rigid_rotation)
        axial_extension = current_length - reference_length
        return CorotationalKinematics(
            displacement_vector=numpy.asarray(displacement_array, dtype=float).copy(),
            reference_length=reference_length,
            current_length=current_length,
            reference_rotation=reference_rotation,
            current_rotation=current_rotation,
            rigid_rotation=rigid_rotation,
            axial_extension=axial_extension,
            local_rotation_i=local_rotation_i,
            local_rotation_j=local_rotation_j,
            tangent_vector=tangent_vector,
            normal_vector=normal_vector,
            basic_deformation=numpy.asarray((axial_extension, local_rotation_i, local_rotation_j), dtype=float),
        )

    def _evaluate_section_response(
        self,
        *,
        axial_extension: float,
        local_rotation_i: float,
        local_rotation_j: float,
        state: StateMap | None,
    ) -> BeamSectionResponse:
        """计算并写回本轮 trial 的 generalized response。"""

        axial_response = self._update_axial_material_point(
            axial_extension=axial_extension,
            local_rotation_i=local_rotation_i,
            local_rotation_j=local_rotation_j,
            state=state,
        )
        return self._build_section_response(
            axial_response=axial_response,
            local_rotation_i=local_rotation_i,
            local_rotation_j=local_rotation_j,
        )

    def _resolve_output_section_response(
        self,
        *,
        axial_extension: float,
        local_rotation_i: float,
        local_rotation_j: float,
        state: Mapping[str, Any] | None,
    ) -> BeamSectionResponse:
        point_key = self._build_axial_point_key()
        cached_point_state = self._resolve_cached_point_state(point_key=point_key, state=state)
        if cached_point_state is None:
            return self._build_section_response(
                axial_response=self._build_ephemeral_axial_response(axial_extension=axial_extension),
                local_rotation_i=local_rotation_i,
                local_rotation_j=local_rotation_j,
            )

        return self._build_section_response(
            axial_response=self._build_axial_response_from_point_state(cached_point_state),
            local_rotation_i=local_rotation_i,
            local_rotation_j=local_rotation_j,
        )

    def _build_section_response(
        self,
        *,
        axial_response: BeamAxialResponse,
        local_rotation_i: float,
        local_rotation_j: float,
    ) -> BeamSectionResponse:
        basic_force = self._build_basic_force(
            axial_force=axial_response.axial_force,
            local_rotation_i=local_rotation_i,
            local_rotation_j=local_rotation_j,
        )
        basic_tangent = self._build_basic_tangent(
            axial_basic_tangent=axial_response.axial_basic_tangent,
        )
        return BeamSectionResponse(
            axial_response=axial_response,
            basic_force=basic_force,
            basic_tangent=basic_tangent,
        )

    def _build_ephemeral_axial_response(self, *, axial_extension: float) -> BeamAxialResponse:
        material_update = self.material_runtime.update(
            strain=(float(axial_extension / self._reference_length()),),
            state=None,
            mode="beam_axial",
        )
        point_state = self._build_axial_point_state(
            material_update=material_update,
            axial_extension=axial_extension,
            local_rotation_i=0.0,
            local_rotation_j=0.0,
            current_time=0.0,
            base_material_state=None,
        )
        return self._build_axial_response_from_point_state(point_state)

    def _build_axial_response_from_point_state(self, point_state: Mapping[str, Any]) -> BeamAxialResponse:
        axial_strain = float(point_state["strain"][0])
        axial_stress = float(point_state["stress"][0])
        axial_force = float(point_state["axial_force"])
        axial_basic_tangent = float(point_state["axial_basic_tangent"])
        material_state = dict(point_state.get("material_state", {}))
        axial_modulus = axial_basic_tangent * self._reference_length() / self.section_runtime.get_area()
        material_update = MaterialUpdateResult(
            stress=(axial_stress,),
            tangent=((float(axial_modulus),),),
            state=material_state,
            strain=(axial_strain,),
            strain_measure="small_strain",
            stress_measure="cauchy_small_strain",
            tangent_measure="d_cauchy_small_strain_d_small_strain",
        )
        return BeamAxialResponse(
            axial_strain=axial_strain,
            axial_stress=axial_stress,
            axial_force=axial_force,
            axial_basic_tangent=axial_basic_tangent,
            material_update=material_update,
            point_state=dict(point_state),
        )

    def _update_axial_material_point(
        self,
        *,
        axial_extension: float,
        local_rotation_i: float,
        local_rotation_j: float,
        state: StateMap | None,
    ) -> BeamAxialResponse:
        point_key = self._build_axial_point_key()
        integration_points = self._resolve_integration_points(state)
        previous_point_state = integration_points.get(point_key)
        current_time = self._resolve_trial_time(state)
        base_material_state = self._resolve_material_base_state(
            previous_point_state=previous_point_state,
            current_time=current_time,
        )
        material_update = self.material_runtime.update(
            strain=(float(axial_extension / self._reference_length()),),
            state=base_material_state,
            mode="beam_axial",
        )
        point_state = self._build_axial_point_state(
            material_update=material_update,
            axial_extension=axial_extension,
            local_rotation_i=local_rotation_i,
            local_rotation_j=local_rotation_j,
            current_time=current_time,
            base_material_state=base_material_state,
        )
        integration_points[point_key] = point_state
        return self._build_axial_response_from_point_state(point_state)

    def _build_axial_point_state(
        self,
        *,
        material_update: MaterialUpdateResult,
        axial_extension: float,
        local_rotation_i: float,
        local_rotation_j: float,
        current_time: float,
        base_material_state: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        axial_strain = float(axial_extension / self._reference_length())
        axial_stress = float(material_update.stress[0])
        axial_modulus = float(material_update.tangent[0][0])
        axial_force = float(self.section_runtime.get_area() * axial_stress)
        axial_basic_tangent = float(self.section_runtime.get_area() * axial_modulus / self._reference_length())
        generalized_stress = self._build_basic_force(
            axial_force=axial_force,
            local_rotation_i=local_rotation_i,
            local_rotation_j=local_rotation_j,
        )
        return {
            "material_state": dict(material_update.state),
            "base_material_state": None if base_material_state is None else dict(base_material_state),
            "strain": (axial_strain,),
            "stress": (axial_stress,),
            "axial_force": axial_force,
            "axial_basic_tangent": axial_basic_tangent,
            "generalized_strain": (float(axial_extension), float(local_rotation_i), float(local_rotation_j)),
            "generalized_stress": tuple(float(item) for item in generalized_stress.tolist()),
            "source_time": float(current_time),
            "debug_metadata": {
                "owner": self.location.qualified_name,
                "point_key": self._build_axial_point_key(),
                "qualified_point_key": f"{self.location.qualified_name}.{self._build_axial_point_key()}",
                "mode": "beam_axial",
            },
        }

    def _resolve_integration_points(self, state: StateMap | None) -> dict[str, dict[str, Any]]:
        if state is None:
            return {}
        raw_points = state.setdefault("integration_points", {})
        return raw_points

    def _resolve_cached_point_state(
        self,
        *,
        point_key: str,
        state: Mapping[str, Any] | None,
    ) -> Mapping[str, Any] | None:
        if state is None:
            return None
        integration_points = state.get("integration_points")
        if not isinstance(integration_points, Mapping):
            return None
        raw_point_state = integration_points.get(point_key)
        if not isinstance(raw_point_state, Mapping):
            return None
        return raw_point_state

    def _resolve_trial_time(self, state: StateMap | Mapping[str, Any] | None) -> float:
        if state is None:
            return 0.0
        return float(state.get("time", 0.0))

    def _resolve_material_base_state(
        self,
        *,
        previous_point_state: Mapping[str, Any] | None,
        current_time: float,
    ) -> Mapping[str, Any] | None:
        if previous_point_state is None:
            return None
        source_time = float(previous_point_state.get("source_time", float("nan")))
        if math.isfinite(source_time) and abs(source_time - current_time) <= 1.0e-15:
            base_material_state = previous_point_state.get("base_material_state")
            if isinstance(base_material_state, Mapping):
                return base_material_state
        material_state = previous_point_state.get("material_state")
        if isinstance(material_state, Mapping):
            return material_state
        return None

    def _build_linear_local_internal_force(
        self,
        *,
        local_displacement: numpy.ndarray,
        section_response: BeamSectionResponse,
    ) -> numpy.ndarray:
        force = self._build_linear_bending_stiffness() @ local_displacement
        force[0] -= section_response.axial_response.axial_force
        force[3] += section_response.axial_response.axial_force
        return force

    def _build_linear_local_tangent(self, *, section_response: BeamSectionResponse) -> numpy.ndarray:
        tangent = self._build_linear_bending_stiffness()
        axial_basic_tangent = section_response.axial_response.axial_basic_tangent
        tangent[0, 0] += axial_basic_tangent
        tangent[0, 3] -= axial_basic_tangent
        tangent[3, 0] -= axial_basic_tangent
        tangent[3, 3] += axial_basic_tangent
        return tangent

    def _build_corotational_tangent(
        self,
        kinematics: CorotationalKinematics,
        section_response: BeamSectionResponse,
    ) -> numpy.ndarray:
        b_matrix = self._build_corotational_b_matrix(kinematics)
        material_tangent = b_matrix.T @ section_response.basic_tangent @ b_matrix
        geometric_tangent = self._build_corotational_geometric_tangent(
            kinematics=kinematics,
            basic_force=section_response.basic_force,
        )
        total_tangent = material_tangent + geometric_tangent
        return 0.5 * (total_tangent + total_tangent.T)

    def _build_corotational_numerical_tangent(
        self,
        displacement_array: numpy.ndarray,
        *,
        relative_step: float = 1.0e-8,
    ) -> numpy.ndarray:
        """仅用于测试校验解析切线精度的高精度数值差分辅助函数。"""

        tangent = numpy.zeros((6, 6), dtype=float)
        for column in range(6):
            perturbation = numpy.zeros(6, dtype=float)
            perturbation[column] = self._numerical_perturbation(
                displacement_array[column],
                relative_step=relative_step,
            )
            kinematics_plus = self._build_corotational_kinematics(displacement_array + perturbation)
            response_plus = self._build_section_response(
                axial_response=self._build_ephemeral_axial_response(axial_extension=kinematics_plus.axial_extension),
                local_rotation_i=kinematics_plus.local_rotation_i,
                local_rotation_j=kinematics_plus.local_rotation_j,
            )
            residual_plus = self._assemble_corotational_internal_force(kinematics_plus, response_plus.basic_force)

            kinematics_minus = self._build_corotational_kinematics(displacement_array - perturbation)
            response_minus = self._build_section_response(
                axial_response=self._build_ephemeral_axial_response(axial_extension=kinematics_minus.axial_extension),
                local_rotation_i=kinematics_minus.local_rotation_i,
                local_rotation_j=kinematics_minus.local_rotation_j,
            )
            residual_minus = self._assemble_corotational_internal_force(kinematics_minus, response_minus.basic_force)
            tangent[:, column] = (residual_plus - residual_minus) / (2.0 * perturbation[column])
        return 0.5 * (tangent + tangent.T)

    def _assemble_corotational_internal_force(
        self,
        kinematics: CorotationalKinematics,
        basic_force: numpy.ndarray,
    ) -> numpy.ndarray:
        return self._build_corotational_b_matrix(kinematics).T @ basic_force

    def _build_basic_force(
        self,
        *,
        axial_force: float,
        local_rotation_i: float,
        local_rotation_j: float,
    ) -> numpy.ndarray:
        bending_force = self._build_bending_basic_stiffness() @ numpy.asarray(
            (local_rotation_i, local_rotation_j),
            dtype=float,
        )
        return numpy.asarray((float(axial_force), bending_force[0], bending_force[1]), dtype=float)

    def _build_basic_tangent(self, *, axial_basic_tangent: float) -> numpy.ndarray:
        bending_stiffness = self._build_bending_basic_stiffness()
        return numpy.asarray(
            (
                (float(axial_basic_tangent), 0.0, 0.0),
                (0.0, bending_stiffness[0, 0], bending_stiffness[0, 1]),
                (0.0, bending_stiffness[1, 0], bending_stiffness[1, 1]),
            ),
            dtype=float,
        )

    def _build_bending_basic_stiffness(self) -> numpy.ndarray:
        length = self._reference_length()
        elastic_modulus = self._resolve_bending_elastic_modulus()
        inertia = self.section_runtime.get_moment_inertia_z()
        factor = elastic_modulus * inertia / length
        return factor * numpy.asarray(((4.0, 2.0), (2.0, 4.0)), dtype=float)

    def _resolve_bending_elastic_modulus(self) -> float:
        material_runtime = self.section_runtime.get_material_runtime()
        get_young_modulus = getattr(material_runtime, "get_young_modulus", None)
        if callable(get_young_modulus):
            return float(get_young_modulus())
        young_modulus = getattr(material_runtime, "young_modulus", None)
        if young_modulus is not None:
            return float(young_modulus)
        raise SolverError(
            f"梁单元 {self.location.qualified_name} 的最小材料耦合方案要求材料运行时提供 young_modulus。"
        )

    def _build_linear_bending_stiffness(self) -> numpy.ndarray:
        tangent = self._build_local_stiffness().copy()
        tangent[0, :] = 0.0
        tangent[3, :] = 0.0
        tangent[:, 0] = 0.0
        tangent[:, 3] = 0.0
        return tangent

    def _build_local_stiffness(self) -> numpy.ndarray:
        length = self._reference_length()
        elastic_modulus = self._resolve_bending_elastic_modulus()
        area = self.section_runtime.get_area()
        inertia = self.section_runtime.get_moment_inertia_z()
        axial = elastic_modulus * area / length
        bending = elastic_modulus * inertia / length**3
        return numpy.asarray(
            (
                (axial, 0.0, 0.0, -axial, 0.0, 0.0),
                (0.0, 12.0 * bending, 6.0 * length * bending, 0.0, -12.0 * bending, 6.0 * length * bending),
                (
                    0.0,
                    6.0 * length * bending,
                    4.0 * length**2 * bending,
                    0.0,
                    -6.0 * length * bending,
                    2.0 * length**2 * bending,
                ),
                (-axial, 0.0, 0.0, axial, 0.0, 0.0),
                (0.0, -12.0 * bending, -6.0 * length * bending, 0.0, 12.0 * bending, -6.0 * length * bending),
                (
                    0.0,
                    6.0 * length * bending,
                    2.0 * length**2 * bending,
                    0.0,
                    -6.0 * length * bending,
                    4.0 * length**2 * bending,
                ),
            ),
            dtype=float,
        )

    def _build_corotational_b_matrix(self, kinematics: CorotationalKinematics) -> numpy.ndarray:
        tangent_x, tangent_y = kinematics.tangent_vector
        normal_x, normal_y = kinematics.normal_vector
        inverse_length = 1.0 / kinematics.current_length
        return numpy.asarray(
            (
                (-tangent_x, -tangent_y, 0.0, tangent_x, tangent_y, 0.0),
                (
                    normal_x * inverse_length,
                    normal_y * inverse_length,
                    1.0,
                    -normal_x * inverse_length,
                    -normal_y * inverse_length,
                    0.0,
                ),
                (
                    normal_x * inverse_length,
                    normal_y * inverse_length,
                    0.0,
                    -normal_x * inverse_length,
                    -normal_y * inverse_length,
                    1.0,
                ),
            ),
            dtype=float,
        )

    def _build_corotational_geometric_tangent(
        self,
        *,
        kinematics: CorotationalKinematics,
        basic_force: numpy.ndarray,
    ) -> numpy.ndarray:
        """构造与当前 basic force 一致的几何切线贡献。"""

        axial_force = float(basic_force[0])
        bending_resultant = float(basic_force[1] + basic_force[2])
        tangent_vector = kinematics.tangent_vector
        normal_vector = kinematics.normal_vector
        current_length = kinematics.current_length

        translational_operator = (
            axial_force / current_length * numpy.outer(normal_vector, normal_vector)
            + bending_resultant / current_length**2
            * (numpy.outer(tangent_vector, normal_vector) + numpy.outer(normal_vector, tangent_vector))
        )

        geometric_tangent = numpy.zeros((6, 6), dtype=float)
        geometric_tangent[numpy.ix_((0, 1), (0, 1))] += translational_operator
        geometric_tangent[numpy.ix_((0, 1), (3, 4))] -= translational_operator
        geometric_tangent[numpy.ix_((3, 4), (0, 1))] -= translational_operator
        geometric_tangent[numpy.ix_((3, 4), (3, 4))] += translational_operator
        return geometric_tangent

    def _build_transformation_matrix(self, rotation: float) -> numpy.ndarray:
        cosine = math.cos(rotation)
        sine = math.sin(rotation)
        return numpy.asarray(
            (
                (cosine, sine, 0.0, 0.0, 0.0, 0.0),
                (-sine, cosine, 0.0, 0.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0, cosine, sine, 0.0),
                (0.0, 0.0, 0.0, -sine, cosine, 0.0),
                (0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
            ),
            dtype=float,
        )

    def _reference_length(self) -> float:
        coordinates = numpy.asarray(self.coordinates, dtype=float)
        return float(numpy.linalg.norm(coordinates[1] - coordinates[0]))

    def _reference_rotation(self) -> float:
        x1, y1 = self.coordinates[0]
        x2, y2 = self.coordinates[1]
        return math.atan2(y2 - y1, x2 - x1)

    def _build_extrapolation_matrix(self) -> numpy.ndarray:
        shape_matrix = numpy.vstack([self._shape_functions(xi) for xi, _ in gauss_points_2()])
        return numpy.linalg.inv(shape_matrix)

    def _shape_functions(self, xi: float) -> numpy.ndarray:
        return numpy.asarray((0.5 * (1.0 - xi), 0.5 * (1.0 + xi)), dtype=float)

    def _section_point_label(self) -> str:
        return "sp1"

    def _build_axial_point_key(self) -> str:
        return "ip1"

    def _build_node_key(self, node_name: str) -> str:
        return f"{self.location.scope_name}.{node_name}"

    def _build_integration_point_key(self, point_index: int, *, section_point_label: str) -> str:
        return f"{self.location.qualified_name}.ip{int(point_index)}.{section_point_label}"

    def _build_element_nodal_key(self, node_name: str, *, section_point_label: str) -> str:
        return f"{self.location.qualified_name}.{node_name}.{section_point_label}"

    def _numerical_perturbation(self, component_value: float, *, relative_step: float = 1.0e-8) -> float:
        scale = max(1.0, abs(float(component_value)), self._reference_length())
        return float(relative_step) * scale

    def _normalize_angle(self, value: float) -> float:
        return math.atan2(math.sin(value), math.cos(value))
