"""CPS4 平面连续体单元运行时。"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy

from pyfem.foundation.errors import SolverError
from pyfem.foundation.types import ElementLocation, Matrix, StateMap, Vector
from pyfem.kernel.elements.base import ElementContribution, ElementRuntime
from pyfem.kernel.elements.common import as_matrix, as_vector, gauss_points_2x2
from pyfem.kernel.materials import MaterialRuntime, MaterialUpdateResult
from pyfem.kernel.sections import PlaneStrainSectionRuntime, PlaneStressSectionRuntime


@dataclass(slots=True, frozen=True)
class TotalLagrangianPointResponse:
    """描述 CPS4 单元在单个积分点上的 TL 评估结果。"""

    strain: numpy.ndarray
    stress: numpy.ndarray
    material_tangent: numpy.ndarray
    geometric_tangent: numpy.ndarray
    internal_force: numpy.ndarray
    deformation_gradient: numpy.ndarray
    jacobian_ratio: float
    point_state: dict[str, Any]


@dataclass(slots=True)
class CPS4Runtime(ElementRuntime):
    """定义 CPS4 平面单元运行时，支持小变形与最小正式 TL 几何非线性。"""

    location: ElementLocation
    coordinates: tuple[tuple[float, float], ...]
    node_names: tuple[str, ...]
    dof_indices: tuple[int, ...]
    section_runtime: PlaneStressSectionRuntime | PlaneStrainSectionRuntime
    material_runtime: MaterialRuntime

    def get_type_key(self) -> str:
        """返回单元运行时类型键。"""

        return "CPS4"

    def get_dof_layout(self) -> tuple[str, ...]:
        """返回单元节点自由度布局。"""

        return ("UX", "UY")

    def get_location(self) -> ElementLocation:
        """返回单元在编译作用域中的位置。"""

        return self.location

    def get_dof_indices(self) -> tuple[int, ...]:
        """返回单元关联的全局自由度编号。"""

        return self.dof_indices

    def get_supported_geometric_nonlinearity_modes(self) -> tuple[str, ...]:
        """返回当前单元支持的几何非线性模式。"""

        return ("total_lagrangian",)

    def allocate_state(self) -> dict[str, Any]:
        """分配单元级状态容器。"""

        return {}

    def compute_tangent_and_residual(
        self,
        displacement: Vector | None = None,
        state: StateMap | None = None,
    ) -> ElementContribution:
        """计算单元切线矩阵与内力向量。"""

        displacement_array = self._resolve_displacement(displacement=displacement, state=state)
        if not self._is_nlgeom_enabled(state):
            return self._compute_small_strain_tangent_and_residual(displacement_array=displacement_array, state=state)
        return self._compute_total_lagrangian_tangent_and_residual(displacement_array=displacement_array, state=state)

    def compute_mass(self, state: StateMap | None = None) -> Matrix:
        """计算单元质量矩阵。"""

        del state
        area = self._compute_reference_area()
        total_mass = self.material_runtime.get_density() * self.section_runtime.get_thickness() * area
        nodal_mass = total_mass / 4.0
        mass = numpy.zeros((8, 8), dtype=float)
        for node_index in range(4):
            base = 2 * node_index
            mass[base, base] = nodal_mass
            mass[base + 1, base + 1] = nodal_mass
        return as_matrix(mass)

    def compute_damping(self, state: StateMap | None = None) -> Matrix | None:
        """返回阻尼矩阵占位。"""

        del state
        return None

    def collect_output(
        self,
        displacement: Vector | None = None,
        state: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """收集单元输出与积分点结果。"""

        displacement_array = self._resolve_displacement(displacement=displacement, state=state)
        if self._is_nlgeom_enabled(state):
            point_records = self._collect_total_lagrangian_point_records(
                displacement_array=displacement_array,
                state=state,
            )
            nlgeom_mode = "total_lagrangian"
        else:
            point_records = self._collect_small_strain_point_records(
                displacement_array=displacement_array,
                state=state,
            )
            nlgeom_mode = "linear_small_strain"
        strain_measure = self._resolve_uniform_measure(point_records, measure_key="strain_measure", default="unspecified")
        stress_measure = self._resolve_uniform_measure(point_records, measure_key="stress_measure", default="unspecified")
        tangent_measure = self._resolve_uniform_measure(point_records, measure_key="tangent_measure", default="unspecified")

        area = self._compute_reference_area()
        thickness = self.section_runtime.get_thickness()
        strain_average = self._average_vectors(point_records, key="strain")
        stress_average = self._average_vectors(point_records, key="stress")

        recovery_target_keys = tuple(self._build_element_nodal_key(node_name) for node_name in self.node_names)
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
            "averaging_weight": float(area * thickness),
            "strain": strain_average,
            "stress": stress_average,
            "thickness": thickness,
            "integration_points": tuple(point_records),
            "nlgeom_active": self._is_nlgeom_enabled(state),
            "nlgeom_mode": nlgeom_mode,
            "strain_measure": strain_measure,
            "stress_measure": stress_measure,
            "tangent_measure": tangent_measure,
            "recovery": {
                "target_keys": recovery_target_keys,
                "base_target_keys": recovery_base_target_keys,
                "extrapolation_matrix": as_matrix(self._build_extrapolation_matrix()),
            },
        }

    def _compute_small_strain_tangent_and_residual(
        self,
        *,
        displacement_array: numpy.ndarray,
        state: StateMap | None,
    ) -> ElementContribution:
        stiffness = numpy.zeros((8, 8), dtype=float)
        residual = numpy.zeros(8, dtype=float)
        thickness = self.section_runtime.get_thickness()
        for point_index, (xi, eta, weight) in enumerate(gauss_points_2x2(), start=1):
            b_matrix = self._build_small_strain_b_matrix(xi, eta)
            determinant = self._reference_jacobian_determinant(xi, eta)
            strain = b_matrix @ displacement_array
            point_result = self._update_small_strain_material_point(
                point_index=point_index,
                strain=strain,
                state=state,
            )
            tangent = numpy.asarray(point_result.tangent, dtype=float)
            stress = numpy.asarray(point_result.stress, dtype=float)
            factor = thickness * determinant * weight
            stiffness += b_matrix.T @ tangent @ b_matrix * factor
            residual += b_matrix.T @ stress * factor
        return ElementContribution(stiffness=as_matrix(stiffness), residual=as_vector(residual))

    def _compute_total_lagrangian_tangent_and_residual(
        self,
        *,
        displacement_array: numpy.ndarray,
        state: StateMap | None,
    ) -> ElementContribution:
        self._assert_total_lagrangian_material_supported()
        stiffness = numpy.zeros((8, 8), dtype=float)
        residual = numpy.zeros(8, dtype=float)
        thickness = self.section_runtime.get_thickness()
        for point_index, (xi, eta, weight) in enumerate(gauss_points_2x2(), start=1):
            response = self._evaluate_total_lagrangian_point(
                point_index=point_index,
                xi=xi,
                eta=eta,
                displacement_array=displacement_array,
                state=state,
                update_state=True,
            )
            factor = thickness * self._reference_jacobian_determinant(xi, eta) * weight
            stiffness += (response.material_tangent + response.geometric_tangent) * factor
            residual += response.internal_force * factor
        stiffness = 0.5 * (stiffness + stiffness.T)
        return ElementContribution(stiffness=as_matrix(stiffness), residual=as_vector(residual))

    def _collect_small_strain_point_records(
        self,
        *,
        displacement_array: numpy.ndarray,
        state: Mapping[str, Any] | None,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        thickness = self.section_runtime.get_thickness()
        for point_index, (xi, eta, weight) in enumerate(gauss_points_2x2(), start=1):
            point_key = self._build_point_key(point_index)
            point_state = self._resolve_cached_point_state(point_key=point_key, state=state)
            if point_state is None or "stress" not in point_state or "strain" not in point_state:
                strain = self._build_small_strain_b_matrix(xi, eta) @ displacement_array
                update_result = self.material_runtime.update(
                    strain=as_vector(strain),
                    state=None if point_state is None else point_state.get("material_state"),
                    mode=self.section_runtime.get_section_type(),
                )
                point_state = self._build_small_strain_point_state(
                    point_index=point_index,
                    update_result=update_result,
                    strain=strain,
                )
            records.append(
                {
                    "target_key": self._build_integration_point_key(point_index),
                    "natural_coordinates": (float(xi), float(eta)),
                    "sample_weight": float(self._reference_jacobian_determinant(xi, eta) * weight * thickness),
                    "strain": point_state["strain"],
                    "stress": point_state["stress"],
                    "strain_measure": str(point_state.get("strain_measure", "unspecified")),
                    "stress_measure": str(point_state.get("stress_measure", "unspecified")),
                    "tangent_measure": str(point_state.get("tangent_measure", "unspecified")),
                    "equivalent_plastic_strain": float(
                        point_state["material_state"].get("equivalent_plastic_strain", 0.0)
                    ),
                }
            )
        return records

    def _collect_total_lagrangian_point_records(
        self,
        *,
        displacement_array: numpy.ndarray,
        state: Mapping[str, Any] | None,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        thickness = self.section_runtime.get_thickness()
        for point_index, (xi, eta, weight) in enumerate(gauss_points_2x2(), start=1):
            point_key = self._build_point_key(point_index)
            point_state = self._resolve_cached_point_state(point_key=point_key, state=state)
            if point_state is None or "stress" not in point_state or "strain" not in point_state:
                point_state = self._evaluate_total_lagrangian_point(
                    point_index=point_index,
                    xi=xi,
                    eta=eta,
                    displacement_array=displacement_array,
                    state=state,
                    update_state=False,
                ).point_state
            records.append(
                {
                    "target_key": self._build_integration_point_key(point_index),
                    "natural_coordinates": (float(xi), float(eta)),
                    "sample_weight": float(self._reference_jacobian_determinant(xi, eta) * weight * thickness),
                    "strain": point_state["strain"],
                    "stress": point_state["stress"],
                    "strain_measure": str(point_state.get("strain_measure", "unspecified")),
                    "stress_measure": str(point_state.get("stress_measure", "unspecified")),
                    "tangent_measure": str(point_state.get("tangent_measure", "unspecified")),
                    "equivalent_plastic_strain": float(
                        point_state["material_state"].get("equivalent_plastic_strain", 0.0)
                    ),
                    "jacobian_ratio": float(point_state.get("jacobian_ratio", 1.0)),
                }
            )
        return records

    def _update_small_strain_material_point(
        self,
        *,
        point_index: int,
        strain: numpy.ndarray,
        state: StateMap | None,
    ) -> MaterialUpdateResult:
        point_key = self._build_point_key(point_index)
        integration_points = self._resolve_integration_points(state)
        previous_point_state = integration_points.get(point_key)
        material_state = None if previous_point_state is None else previous_point_state.get("material_state")
        update_result = self.material_runtime.update(
            strain=as_vector(strain),
            state=material_state,
            mode=self.section_runtime.get_section_type(),
        )
        integration_points[point_key] = self._build_small_strain_point_state(
            point_index=point_index,
            update_result=update_result,
            strain=strain,
        )
        return update_result

    def _build_small_strain_point_state(
        self,
        *,
        point_index: int,
        update_result: MaterialUpdateResult,
        strain: numpy.ndarray,
    ) -> dict[str, Any]:
        return {
            "material_state": dict(update_result.state),
            "strain": tuple(float(item) for item in (update_result.strain or tuple(float(item) for item in strain.tolist()))),
            "stress": tuple(float(item) for item in update_result.stress),
            "strain_measure": update_result.strain_measure,
            "stress_measure": update_result.stress_measure,
            "tangent_measure": update_result.tangent_measure,
            "debug_metadata": {
                "owner": self.location.qualified_name,
                "point_key": self._build_point_key(point_index),
                "qualified_point_key": self._build_integration_point_key(point_index),
                "mode": self.section_runtime.get_section_type(),
            },
        }

    def _evaluate_total_lagrangian_point(
        self,
        *,
        point_index: int,
        xi: float,
        eta: float,
        displacement_array: numpy.ndarray,
        state: StateMap | Mapping[str, Any] | None,
        update_state: bool,
    ) -> TotalLagrangianPointResponse:
        reference_gradients = self._reference_shape_function_gradients(xi, eta)
        deformation_gradient = self._build_deformation_gradient(
            reference_gradients=reference_gradients,
            displacement_array=displacement_array,
        )
        jacobian_ratio = float(numpy.linalg.det(deformation_gradient))
        if jacobian_ratio <= 1.0e-12:
            raise SolverError(
                f"单元 {self.location.qualified_name} 在积分点 {self._build_point_key(point_index)} 出现非正 Jacobian，"
                "当前构形已退化或翻转。"
            )

        strain = self._build_green_lagrange_strain_vector(deformation_gradient)
        point_key = self._build_point_key(point_index)
        previous_point_state = self._resolve_previous_point_state(point_key=point_key, state=state)
        current_time = self._resolve_trial_time(state)
        base_material_state = self._resolve_material_base_state(
            previous_point_state=previous_point_state,
            current_time=current_time,
        )
        update_result = self.material_runtime.update(
            strain=as_vector(strain),
            state=base_material_state,
            mode=self._resolve_total_lagrangian_material_mode(),
        )
        strain = numpy.asarray(update_result.strain, dtype=float)
        stress = numpy.asarray(update_result.stress, dtype=float)
        material_constitutive = numpy.asarray(update_result.tangent, dtype=float)
        b_matrix = self._build_total_lagrangian_b_matrix(
            reference_gradients=reference_gradients,
            deformation_gradient=deformation_gradient,
        )
        internal_force = b_matrix.T @ stress
        material_tangent = b_matrix.T @ material_constitutive @ b_matrix
        geometric_tangent = self._build_total_lagrangian_geometric_tangent(
            reference_gradients=reference_gradients,
            stress=stress,
        )
        point_state = self._build_total_lagrangian_point_state(
            point_index=point_index,
            update_result=update_result,
            strain=strain,
            stress=stress,
            deformation_gradient=deformation_gradient,
            jacobian_ratio=jacobian_ratio,
            current_time=current_time,
            base_material_state=base_material_state,
        )
        if update_state:
            self._resolve_integration_points(state)[point_key] = point_state
        return TotalLagrangianPointResponse(
            strain=strain,
            stress=stress,
            material_tangent=material_tangent,
            geometric_tangent=geometric_tangent,
            internal_force=internal_force,
            deformation_gradient=deformation_gradient,
            jacobian_ratio=jacobian_ratio,
            point_state=point_state,
        )

    def _build_total_lagrangian_point_state(
        self,
        *,
        point_index: int,
        update_result: MaterialUpdateResult,
        strain: numpy.ndarray,
        stress: numpy.ndarray,
        deformation_gradient: numpy.ndarray,
        jacobian_ratio: float,
        current_time: float,
        base_material_state: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "material_state": dict(update_result.state),
            "base_material_state": None if base_material_state is None else dict(base_material_state),
            "strain": tuple(float(item) for item in (update_result.strain or tuple(float(item) for item in strain.tolist()))),
            "stress": tuple(float(item) for item in stress.tolist()),
            "strain_measure": update_result.strain_measure,
            "stress_measure": update_result.stress_measure,
            "tangent_measure": update_result.tangent_measure,
            "deformation_gradient": as_matrix(deformation_gradient),
            "jacobian_ratio": float(jacobian_ratio),
            "source_time": float(current_time),
            "debug_metadata": {
                "owner": self.location.qualified_name,
                "point_key": self._build_point_key(point_index),
                "qualified_point_key": self._build_integration_point_key(point_index),
                "mode": f"{self.section_runtime.get_section_type()}_total_lagrangian",
            },
        }

    def _resolve_previous_point_state(
        self,
        *,
        point_key: str,
        state: StateMap | Mapping[str, Any] | None,
    ) -> Mapping[str, Any] | None:
        if state is None:
            return None
        integration_points = state.get("integration_points")
        if not isinstance(integration_points, Mapping):
            return None
        point_state = integration_points.get(point_key)
        if not isinstance(point_state, Mapping):
            return None
        return point_state

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

    def _average_vectors(self, point_records: list[Mapping[str, Any]], *, key: str) -> tuple[float, ...]:
        if not point_records:
            return ()
        stacked = numpy.asarray([record[key] for record in point_records], dtype=float)
        return tuple(float(item) for item in numpy.mean(stacked, axis=0).tolist())

    def _resolve_uniform_measure(
        self,
        point_records: list[Mapping[str, Any]],
        *,
        measure_key: str,
        default: str,
    ) -> str:
        measures = tuple(
            dict.fromkeys(
                str(record.get(measure_key, default))
                for record in point_records
                if str(record.get(measure_key, default)).strip()
            )
        )
        if not measures:
            return default
        if len(measures) == 1:
            return measures[0]
        return "mixed"

    def _compute_reference_area(self) -> float:
        area = 0.0
        for xi, eta, weight in gauss_points_2x2():
            area += self._reference_jacobian_determinant(xi, eta) * weight
        return float(area)

    def _resolve_displacement(
        self,
        displacement: Vector | None,
        state: StateMap | Mapping[str, Any] | None,
    ) -> numpy.ndarray:
        if displacement is not None:
            return numpy.asarray(displacement, dtype=float)
        if state is not None and "displacement" in state:
            return numpy.asarray(state["displacement"], dtype=float)
        return numpy.zeros(8, dtype=float)

    def _build_extrapolation_matrix(self) -> numpy.ndarray:
        shape_matrix = numpy.vstack([self._shape_functions(xi, eta) for xi, eta, _ in gauss_points_2x2()])
        return numpy.linalg.inv(shape_matrix)

    def _build_node_key(self, node_name: str) -> str:
        return f"{self.location.scope_name}.{node_name}"

    def _build_point_key(self, point_index: int) -> str:
        return f"ip{int(point_index)}"

    def _build_integration_point_key(self, point_index: int) -> str:
        return f"{self.location.qualified_name}.{self._build_point_key(point_index)}"

    def _build_element_nodal_key(self, node_name: str) -> str:
        return f"{self.location.qualified_name}.{node_name}"

    def _is_nlgeom_enabled(self, state: StateMap | Mapping[str, Any] | None) -> bool:
        if state is None:
            return False
        analysis_flags = state.get("analysis_flags")
        if not isinstance(analysis_flags, Mapping):
            return False
        return bool(analysis_flags.get("nlgeom", False))

    def _assert_total_lagrangian_material_supported(self) -> None:
        material_type = self.material_runtime.get_material_type()
        section_type = self.section_runtime.get_section_type()
        if material_type == "linear_elastic":
            return
        if material_type == "j2_plasticity" and section_type == "plane_strain":
            return
        if material_type == "j2_plasticity" and section_type == "plane_stress":
            raise SolverError(
                f"单元 {self.location.qualified_name} 当前仅正式支持 CPS4 + nlgeom + plane_strain + J2，"
                "暂不支持 CPS4 + nlgeom + plane_stress + J2。"
            )
        raise SolverError(
            f"单元 {self.location.qualified_name} 当前仅正式支持 CPS4 + nlgeom + 线弹性，"
            "以及 CPS4 + nlgeom + plane_strain + J2；"
            f"暂不支持材料类型 {material_type}。"
        )

    def _resolve_total_lagrangian_material_mode(self) -> str:
        section_type = self.section_runtime.get_section_type()
        if section_type == "plane_strain":
            return "plane_strain_total_lagrangian"
        if section_type == "plane_stress":
            return "plane_stress_total_lagrangian"
        raise SolverError(f"单元 {self.location.qualified_name} 不支持截面类型 {section_type} 的 TL 材料更新。")

    def _reference_jacobian_determinant(self, xi: float, eta: float) -> float:
        jacobian = self._build_reference_jacobian(xi, eta)
        determinant = float(numpy.linalg.det(jacobian))
        if determinant <= 0.0:
            raise SolverError(f"单元 {self.location.qualified_name} 的参考构形 Jacobian 非正。")
        return determinant

    def _build_small_strain_b_matrix(self, xi: float, eta: float) -> numpy.ndarray:
        gradients = self._reference_shape_function_gradients(xi, eta)
        b_matrix = numpy.zeros((3, 8), dtype=float)
        for node_index in range(4):
            base = 2 * node_index
            dndx = gradients[0, node_index]
            dndy = gradients[1, node_index]
            b_matrix[0, base] = dndx
            b_matrix[1, base + 1] = dndy
            b_matrix[2, base] = dndy
            b_matrix[2, base + 1] = dndx
        return b_matrix

    def _build_total_lagrangian_b_matrix(
        self,
        *,
        reference_gradients: numpy.ndarray,
        deformation_gradient: numpy.ndarray,
    ) -> numpy.ndarray:
        b_matrix = numpy.zeros((3, 8), dtype=float)
        f11 = float(deformation_gradient[0, 0])
        f12 = float(deformation_gradient[0, 1])
        f21 = float(deformation_gradient[1, 0])
        f22 = float(deformation_gradient[1, 1])
        for node_index in range(4):
            base = 2 * node_index
            dndx = float(reference_gradients[0, node_index])
            dndy = float(reference_gradients[1, node_index])
            b_matrix[0, base] = f11 * dndx
            b_matrix[0, base + 1] = f21 * dndx
            b_matrix[1, base] = f12 * dndy
            b_matrix[1, base + 1] = f22 * dndy
            b_matrix[2, base] = f12 * dndx + f11 * dndy
            b_matrix[2, base + 1] = f22 * dndx + f21 * dndy
        return b_matrix

    def _build_total_lagrangian_geometric_tangent(
        self,
        *,
        reference_gradients: numpy.ndarray,
        stress: numpy.ndarray,
    ) -> numpy.ndarray:
        stress_tensor = numpy.asarray(
            (
                (stress[0], stress[2]),
                (stress[2], stress[1]),
            ),
            dtype=float,
        )
        geometric = numpy.zeros((8, 8), dtype=float)
        for row_index in range(4):
            grad_row = reference_gradients[:, row_index]
            for column_index in range(4):
                grad_column = reference_gradients[:, column_index]
                scalar = float(grad_row @ stress_tensor @ grad_column)
                row_slice = slice(2 * row_index, 2 * row_index + 2)
                column_slice = slice(2 * column_index, 2 * column_index + 2)
                geometric[row_slice, column_slice] += scalar * numpy.eye(2, dtype=float)
        return geometric

    def _build_deformation_gradient(
        self,
        *,
        reference_gradients: numpy.ndarray,
        displacement_array: numpy.ndarray,
    ) -> numpy.ndarray:
        current_coordinates = self._build_current_coordinates(displacement_array)
        deformation_gradient = current_coordinates.T @ reference_gradients.T
        return numpy.asarray(deformation_gradient, dtype=float)

    def _build_current_coordinates(self, displacement_array: numpy.ndarray) -> numpy.ndarray:
        reference_coordinates = numpy.asarray(self.coordinates, dtype=float)
        nodal_displacements = numpy.asarray(displacement_array, dtype=float).reshape(4, 2)
        return reference_coordinates + nodal_displacements

    def _build_green_lagrange_strain_vector(self, deformation_gradient: numpy.ndarray) -> numpy.ndarray:
        right_cauchy_green = deformation_gradient.T @ deformation_gradient
        return numpy.asarray(
            (
                0.5 * (right_cauchy_green[0, 0] - 1.0),
                0.5 * (right_cauchy_green[1, 1] - 1.0),
                right_cauchy_green[0, 1],
            ),
            dtype=float,
        )

    def _build_reference_jacobian(self, xi: float, eta: float) -> numpy.ndarray:
        derivative_parent = self._shape_function_derivative_parent(xi, eta)
        coordinates = numpy.asarray(self.coordinates, dtype=float)
        return derivative_parent @ coordinates

    def _reference_shape_function_gradients(self, xi: float, eta: float) -> numpy.ndarray:
        derivative_parent = self._shape_function_derivative_parent(xi, eta)
        jacobian = self._build_reference_jacobian(xi, eta)
        return numpy.linalg.inv(jacobian) @ derivative_parent

    def _shape_functions(self, xi: float, eta: float) -> numpy.ndarray:
        return 0.25 * numpy.asarray(
            (
                (1.0 - xi) * (1.0 - eta),
                (1.0 + xi) * (1.0 - eta),
                (1.0 + xi) * (1.0 + eta),
                (1.0 - xi) * (1.0 + eta),
            ),
            dtype=float,
        )

    def _shape_function_derivative_parent(self, xi: float, eta: float) -> numpy.ndarray:
        return 0.25 * numpy.asarray(
            (
                (-(1.0 - eta), 1.0 - eta, 1.0 + eta, -(1.0 + eta)),
                (-(1.0 - xi), -(1.0 + xi), 1.0 + xi, 1.0 - xi),
            ),
            dtype=float,
        )

    def _build_total_lagrangian_numerical_tangent(
        self,
        displacement_array: numpy.ndarray,
        *,
        state: Mapping[str, Any] | None = None,
        relative_step: float = 1.0e-8,
    ) -> numpy.ndarray:
        """仅用于测试校验 TL 解析切线精度的数值差分辅助函数。"""

        tangent = numpy.zeros((8, 8), dtype=float)
        for column in range(8):
            perturbation = numpy.zeros(8, dtype=float)
            perturbation[column] = self._numerical_perturbation(
                float(displacement_array[column]),
                relative_step=relative_step,
            )
            residual_plus = self._compute_total_lagrangian_internal_force(
                displacement_array=displacement_array + perturbation,
                state=state,
            )
            residual_minus = self._compute_total_lagrangian_internal_force(
                displacement_array=displacement_array - perturbation,
                state=state,
            )
            tangent[:, column] = (residual_plus - residual_minus) / (2.0 * perturbation[column])
        return 0.5 * (tangent + tangent.T)

    def _compute_total_lagrangian_internal_force(
        self,
        *,
        displacement_array: numpy.ndarray,
        state: Mapping[str, Any] | None,
    ) -> numpy.ndarray:
        residual = numpy.zeros(8, dtype=float)
        thickness = self.section_runtime.get_thickness()
        for point_index, (xi, eta, weight) in enumerate(gauss_points_2x2(), start=1):
            response = self._evaluate_total_lagrangian_point(
                point_index=point_index,
                xi=xi,
                eta=eta,
                displacement_array=displacement_array,
                state=state,
                update_state=False,
            )
            factor = thickness * self._reference_jacobian_determinant(xi, eta) * weight
            residual += response.internal_force * factor
        return residual

    def _numerical_perturbation(self, component_value: float, *, relative_step: float = 1.0e-8) -> float:
        coordinate_scale = float(numpy.linalg.norm(numpy.asarray(self.coordinates, dtype=float)))
        scale = max(1.0, abs(component_value), coordinate_scale)
        return float(relative_step) * scale
