"""C3D8 实体单元运行时。"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy

from pyfem.foundation.errors import SolverError
from pyfem.foundation.types import ElementLocation, Matrix, StateMap, Vector
from pyfem.kernel.elements.base import ElementContribution, ElementRuntime
from pyfem.kernel.elements.common import as_matrix, as_vector, gauss_points_2x2, gauss_points_2x2x2
from pyfem.kernel.materials import MaterialRuntime, MaterialUpdateResult
from pyfem.kernel.sections import SolidSectionRuntime


@dataclass(slots=True, frozen=True)
class TotalLagrangianPointResponse:
    """描述 C3D8 单元在单个积分点上的 TL 评估结果。"""

    strain: numpy.ndarray
    stress: numpy.ndarray
    material_tangent: numpy.ndarray
    geometric_tangent: numpy.ndarray
    internal_force: numpy.ndarray
    deformation_gradient: numpy.ndarray
    jacobian_ratio: float
    point_state: dict[str, Any]


@dataclass(slots=True)
class C3D8Runtime(ElementRuntime):
    """定义 C3D8 实体单元运行时，支持小变形与最小正式 TL 几何非线性。"""

    location: ElementLocation
    coordinates: tuple[tuple[float, float, float], ...]
    node_names: tuple[str, ...]
    dof_indices: tuple[int, ...]
    section_runtime: SolidSectionRuntime
    material_runtime: MaterialRuntime

    def get_type_key(self) -> str:
        """返回单元运行时类型键。"""

        return "C3D8"

    def get_dof_layout(self) -> tuple[str, ...]:
        """返回单元节点自由度布局。"""

        return ("UX", "UY", "UZ")

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
        total_mass = self.material_runtime.get_density() * self._compute_reference_volume()
        nodal_mass = total_mass / 8.0
        mass = numpy.zeros((24, 24), dtype=float)
        for node_index in range(8):
            base = 3 * node_index
            mass[base, base] = nodal_mass
            mass[base + 1, base + 1] = nodal_mass
            mass[base + 2, base + 2] = nodal_mass
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
            "averaging_weight": self._compute_reference_volume(),
            "strain": strain_average,
            "stress": stress_average,
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

    def compute_surface_load(
        self,
        local_face: str,
        load_type: str,
        components: Mapping[str, float],
        state: StateMap | None = None,
    ) -> Vector:
        """计算实体表面分布载荷的等效节点力。"""

        normalized_load_type = self._normalize_surface_load_type(load_type)
        if self._is_nlgeom_enabled(state):
            raise SolverError(
                f"单元 {self.location.qualified_name} 在 nlgeom=True 下暂不支持表面分布载荷。"
                f"收到 load_type={normalized_load_type}, local_face={local_face}。"
                "当前仅正式支持小变形 C3D8 surface pressure 载荷，"
                "不支持 nlgeom=True 下的 pressure / follower pressure 当前构形语义。"
            )
        if normalized_load_type not in {"pressure", "p"}:
            raise NotImplementedError(f"C3D8 当前仅支持 pressure 类型表面载荷，收到 {load_type}。")

        pressure = self._resolve_pressure_value(components)
        equivalent_load = numpy.zeros(24, dtype=float)
        for face_coordinate_a, face_coordinate_b, weight in gauss_points_2x2():
            xi, eta, zeta = self._map_face_parent_coordinates(local_face.upper(), face_coordinate_a, face_coordinate_b)
            shape_values = self._shape_functions(xi, eta, zeta)
            face_normal = self._build_face_normal(local_face.upper(), xi, eta, zeta)
            face_jacobian = numpy.linalg.norm(face_normal)
            if face_jacobian <= 0.0:
                raise ValueError(f"单元 {self.location.qualified_name} 的面 {local_face} 出现非法 Jacobian。")
            traction = (-pressure) * face_normal / face_jacobian
            equivalent_load += self._build_surface_shape_matrix(shape_values).T @ traction * face_jacobian * weight
        return as_vector(equivalent_load)

    def _compute_small_strain_tangent_and_residual(
        self,
        *,
        displacement_array: numpy.ndarray,
        state: StateMap | None,
    ) -> ElementContribution:
        stiffness = numpy.zeros((24, 24), dtype=float)
        residual = numpy.zeros(24, dtype=float)
        for point_index, (xi, eta, zeta, weight) in enumerate(gauss_points_2x2x2(), start=1):
            b_matrix = self._build_small_strain_b_matrix(xi, eta, zeta)
            determinant = self._reference_jacobian_determinant(xi, eta, zeta)
            strain = b_matrix @ displacement_array
            point_result = self._update_small_strain_material_point(
                point_index=point_index,
                strain=strain,
                state=state,
            )
            tangent = numpy.asarray(point_result.tangent, dtype=float)
            stress = numpy.asarray(point_result.stress, dtype=float)
            factor = determinant * weight
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
        stiffness = numpy.zeros((24, 24), dtype=float)
        residual = numpy.zeros(24, dtype=float)
        for point_index, (xi, eta, zeta, weight) in enumerate(gauss_points_2x2x2(), start=1):
            response = self._evaluate_total_lagrangian_point(
                point_index=point_index,
                xi=xi,
                eta=eta,
                zeta=zeta,
                displacement_array=displacement_array,
                state=state,
                update_state=True,
            )
            factor = self._reference_jacobian_determinant(xi, eta, zeta) * weight
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
        for point_index, (xi, eta, zeta, weight) in enumerate(gauss_points_2x2x2(), start=1):
            determinant = self._reference_jacobian_determinant(xi, eta, zeta)
            point_key = self._build_point_key(point_index)
            point_state = self._resolve_cached_point_state(point_key=point_key, state=state)
            if point_state is None or "stress" not in point_state or "strain" not in point_state:
                strain = self._build_small_strain_b_matrix(xi, eta, zeta) @ displacement_array
                update_result = self.material_runtime.update(
                    strain=as_vector(strain),
                    state=None if point_state is None else point_state.get("material_state"),
                    mode="3d",
                )
                point_state = self._build_small_strain_point_state(
                    point_index=point_index,
                    update_result=update_result,
                    strain=strain,
                )
            records.append(
                {
                    "target_key": self._build_integration_point_key(point_index),
                    "natural_coordinates": (float(xi), float(eta), float(zeta)),
                    "sample_weight": float(determinant * weight),
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
        for point_index, (xi, eta, zeta, weight) in enumerate(gauss_points_2x2x2(), start=1):
            determinant = self._reference_jacobian_determinant(xi, eta, zeta)
            point_key = self._build_point_key(point_index)
            point_state = self._resolve_cached_point_state(point_key=point_key, state=state)
            if point_state is None or "stress" not in point_state or "strain" not in point_state:
                point_state = self._evaluate_total_lagrangian_point(
                    point_index=point_index,
                    xi=xi,
                    eta=eta,
                    zeta=zeta,
                    displacement_array=displacement_array,
                    state=state,
                    update_state=False,
                ).point_state
            records.append(
                {
                    "target_key": self._build_integration_point_key(point_index),
                    "natural_coordinates": (float(xi), float(eta), float(zeta)),
                    "sample_weight": float(determinant * weight),
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
            mode="3d",
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
                "mode": "3d",
            },
        }

    def _evaluate_total_lagrangian_point(
        self,
        *,
        point_index: int,
        xi: float,
        eta: float,
        zeta: float,
        displacement_array: numpy.ndarray,
        state: StateMap | Mapping[str, Any] | None,
        update_state: bool,
    ) -> TotalLagrangianPointResponse:
        reference_gradients = self._reference_shape_function_gradients(xi, eta, zeta)
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
                "mode": "3d_total_lagrangian",
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

    def _compute_reference_volume(self) -> float:
        volume = 0.0
        for xi, eta, zeta, weight in gauss_points_2x2x2():
            volume += self._reference_jacobian_determinant(xi, eta, zeta) * weight
        return float(volume)

    def _resolve_displacement(
        self,
        displacement: Vector | None,
        state: StateMap | Mapping[str, Any] | None,
    ) -> numpy.ndarray:
        if displacement is not None:
            return numpy.asarray(displacement, dtype=float)
        if state is not None and "displacement" in state:
            return numpy.asarray(state["displacement"], dtype=float)
        return numpy.zeros(24, dtype=float)

    def _build_extrapolation_matrix(self) -> numpy.ndarray:
        shape_matrix = numpy.vstack(
            [self._shape_functions(xi, eta, zeta) for xi, eta, zeta, _ in gauss_points_2x2x2()]
        )
        return numpy.linalg.inv(shape_matrix)

    def _build_node_key(self, node_name: str) -> str:
        return f"{self.location.scope_name}.{node_name}"

    def _build_point_key(self, point_index: int) -> str:
        return f"ip{int(point_index)}"

    def _build_integration_point_key(self, point_index: int) -> str:
        return f"{self.location.qualified_name}.{self._build_point_key(point_index)}"

    def _build_element_nodal_key(self, node_name: str) -> str:
        return f"{self.location.qualified_name}.{node_name}"

    def _resolve_pressure_value(self, components: Mapping[str, float]) -> float:
        if "P" not in components:
            raise ValueError("压力载荷必须提供 P 分量。")
        return float(components["P"])

    def _normalize_surface_load_type(self, load_type: str) -> str:
        normalized_load_type = str(load_type).strip().lower()
        aliases = {
            "p": "pressure",
            "pressure": "pressure",
            "follower": "follower_pressure",
            "follower_pressure": "follower_pressure",
            "follower-pressure": "follower_pressure",
        }
        return aliases.get(normalized_load_type, normalized_load_type)

    def _is_nlgeom_enabled(self, state: StateMap | Mapping[str, Any] | None) -> bool:
        if state is None:
            return False
        analysis_flags = state.get("analysis_flags")
        if not isinstance(analysis_flags, Mapping):
            return False
        return bool(analysis_flags.get("nlgeom", False))

    def _assert_total_lagrangian_material_supported(self) -> None:
        material_type = self.material_runtime.get_material_type()
        if material_type in {"linear_elastic", "j2_plasticity"}:
            return
        raise SolverError(
            f"单元 {self.location.qualified_name} 当前仅正式支持 C3D8 + nlgeom + 线弹性，"
            "以及 C3D8 + nlgeom + J2；"
            f"暂不支持材料类型 {material_type}。"
        )

    def _resolve_total_lagrangian_material_mode(self) -> str:
        return "solid_total_lagrangian"

    def _reference_jacobian_determinant(self, xi: float, eta: float, zeta: float) -> float:
        jacobian = self._build_reference_jacobian(xi, eta, zeta)
        determinant = float(numpy.linalg.det(jacobian))
        if determinant <= 0.0:
            raise SolverError(f"单元 {self.location.qualified_name} 的参考构形 Jacobian 非正。")
        return determinant

    def _build_small_strain_b_matrix(self, xi: float, eta: float, zeta: float) -> numpy.ndarray:
        gradients = self._reference_shape_function_gradients(xi, eta, zeta)
        b_matrix = numpy.zeros((6, 24), dtype=float)
        for node_index in range(8):
            base = 3 * node_index
            dndx = gradients[0, node_index]
            dndy = gradients[1, node_index]
            dndz = gradients[2, node_index]
            b_matrix[0, base] = dndx
            b_matrix[1, base + 1] = dndy
            b_matrix[2, base + 2] = dndz
            b_matrix[3, base] = dndy
            b_matrix[3, base + 1] = dndx
            b_matrix[4, base + 1] = dndz
            b_matrix[4, base + 2] = dndy
            b_matrix[5, base] = dndz
            b_matrix[5, base + 2] = dndx
        return b_matrix

    def _build_total_lagrangian_b_matrix(
        self,
        *,
        reference_gradients: numpy.ndarray,
        deformation_gradient: numpy.ndarray,
    ) -> numpy.ndarray:
        b_matrix = numpy.zeros((6, 24), dtype=float)
        f11 = float(deformation_gradient[0, 0])
        f12 = float(deformation_gradient[0, 1])
        f13 = float(deformation_gradient[0, 2])
        f21 = float(deformation_gradient[1, 0])
        f22 = float(deformation_gradient[1, 1])
        f23 = float(deformation_gradient[1, 2])
        f31 = float(deformation_gradient[2, 0])
        f32 = float(deformation_gradient[2, 1])
        f33 = float(deformation_gradient[2, 2])

        for node_index in range(8):
            base = 3 * node_index
            dndx = float(reference_gradients[0, node_index])
            dndy = float(reference_gradients[1, node_index])
            dndz = float(reference_gradients[2, node_index])

            b_matrix[0, base] = f11 * dndx
            b_matrix[0, base + 1] = f21 * dndx
            b_matrix[0, base + 2] = f31 * dndx

            b_matrix[1, base] = f12 * dndy
            b_matrix[1, base + 1] = f22 * dndy
            b_matrix[1, base + 2] = f32 * dndy

            b_matrix[2, base] = f13 * dndz
            b_matrix[2, base + 1] = f23 * dndz
            b_matrix[2, base + 2] = f33 * dndz

            b_matrix[3, base] = f12 * dndx + f11 * dndy
            b_matrix[3, base + 1] = f22 * dndx + f21 * dndy
            b_matrix[3, base + 2] = f32 * dndx + f31 * dndy

            b_matrix[4, base] = f13 * dndy + f12 * dndz
            b_matrix[4, base + 1] = f23 * dndy + f22 * dndz
            b_matrix[4, base + 2] = f33 * dndy + f32 * dndz

            b_matrix[5, base] = f13 * dndx + f11 * dndz
            b_matrix[5, base + 1] = f23 * dndx + f21 * dndz
            b_matrix[5, base + 2] = f33 * dndx + f31 * dndz
        return b_matrix

    def _build_total_lagrangian_geometric_tangent(
        self,
        *,
        reference_gradients: numpy.ndarray,
        stress: numpy.ndarray,
    ) -> numpy.ndarray:
        stress_tensor = self._stress_vector_to_tensor(stress)
        geometric = numpy.zeros((24, 24), dtype=float)
        for row_index in range(8):
            grad_row = reference_gradients[:, row_index]
            for column_index in range(8):
                grad_column = reference_gradients[:, column_index]
                scalar = float(grad_row @ stress_tensor @ grad_column)
                row_slice = slice(3 * row_index, 3 * row_index + 3)
                column_slice = slice(3 * column_index, 3 * column_index + 3)
                geometric[row_slice, column_slice] += scalar * numpy.eye(3, dtype=float)
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
        nodal_displacements = numpy.asarray(displacement_array, dtype=float).reshape(8, 3)
        return reference_coordinates + nodal_displacements

    def _build_green_lagrange_strain_vector(self, deformation_gradient: numpy.ndarray) -> numpy.ndarray:
        right_cauchy_green = deformation_gradient.T @ deformation_gradient
        return numpy.asarray(
            (
                0.5 * (right_cauchy_green[0, 0] - 1.0),
                0.5 * (right_cauchy_green[1, 1] - 1.0),
                0.5 * (right_cauchy_green[2, 2] - 1.0),
                right_cauchy_green[0, 1],
                right_cauchy_green[1, 2],
                right_cauchy_green[0, 2],
            ),
            dtype=float,
        )

    def _stress_vector_to_tensor(self, stress: numpy.ndarray) -> numpy.ndarray:
        return numpy.asarray(
            (
                (stress[0], stress[3], stress[5]),
                (stress[3], stress[1], stress[4]),
                (stress[5], stress[4], stress[2]),
            ),
            dtype=float,
        )

    def _build_reference_jacobian(self, xi: float, eta: float, zeta: float) -> numpy.ndarray:
        derivative_parent = self._shape_function_derivative_parent(xi, eta, zeta)
        coordinates = numpy.asarray(self.coordinates, dtype=float)
        return derivative_parent @ coordinates

    def _reference_shape_function_gradients(self, xi: float, eta: float, zeta: float) -> numpy.ndarray:
        derivative_parent = self._shape_function_derivative_parent(xi, eta, zeta)
        jacobian = self._build_reference_jacobian(xi, eta, zeta)
        return numpy.linalg.inv(jacobian) @ derivative_parent

    def _shape_functions(self, xi: float, eta: float, zeta: float) -> numpy.ndarray:
        signs = numpy.asarray(
            (
                (-1.0, -1.0, -1.0),
                (1.0, -1.0, -1.0),
                (1.0, 1.0, -1.0),
                (-1.0, 1.0, -1.0),
                (-1.0, -1.0, 1.0),
                (1.0, -1.0, 1.0),
                (1.0, 1.0, 1.0),
                (-1.0, 1.0, 1.0),
            ),
            dtype=float,
        )
        values = numpy.zeros(8, dtype=float)
        for node_index, (sx, sy, sz) in enumerate(signs):
            values[node_index] = 0.125 * (1.0 + sx * xi) * (1.0 + sy * eta) * (1.0 + sz * zeta)
        return values

    def _shape_function_derivative_parent(self, xi: float, eta: float, zeta: float) -> numpy.ndarray:
        signs = numpy.asarray(
            (
                (-1.0, -1.0, -1.0),
                (1.0, -1.0, -1.0),
                (1.0, 1.0, -1.0),
                (-1.0, 1.0, -1.0),
                (-1.0, -1.0, 1.0),
                (1.0, -1.0, 1.0),
                (1.0, 1.0, 1.0),
                (-1.0, 1.0, 1.0),
            ),
            dtype=float,
        )
        derivative_parent = numpy.zeros((3, 8), dtype=float)
        for node_index, (sx, sy, sz) in enumerate(signs):
            derivative_parent[0, node_index] = 0.125 * sx * (1.0 + sy * eta) * (1.0 + sz * zeta)
            derivative_parent[1, node_index] = 0.125 * sy * (1.0 + sx * xi) * (1.0 + sz * zeta)
            derivative_parent[2, node_index] = 0.125 * sz * (1.0 + sx * xi) * (1.0 + sy * eta)
        return derivative_parent

    def _build_total_lagrangian_numerical_tangent(
        self,
        displacement_array: numpy.ndarray,
        *,
        state: Mapping[str, Any] | None = None,
        relative_step: float = 1.0e-8,
    ) -> numpy.ndarray:
        """仅用于测试校验 TL 解析切线精度的数值差分辅助函数。"""

        tangent = numpy.zeros((24, 24), dtype=float)
        for column in range(24):
            perturbation = numpy.zeros(24, dtype=float)
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
        residual = numpy.zeros(24, dtype=float)
        for point_index, (xi, eta, zeta, weight) in enumerate(gauss_points_2x2x2(), start=1):
            response = self._evaluate_total_lagrangian_point(
                point_index=point_index,
                xi=xi,
                eta=eta,
                zeta=zeta,
                displacement_array=displacement_array,
                state=state,
                update_state=False,
            )
            factor = self._reference_jacobian_determinant(xi, eta, zeta) * weight
            residual += response.internal_force * factor
        return residual

    def _numerical_perturbation(self, component_value: float, *, relative_step: float = 1.0e-8) -> float:
        coordinate_scale = float(numpy.linalg.norm(numpy.asarray(self.coordinates, dtype=float)))
        scale = max(1.0, abs(component_value), coordinate_scale)
        return float(relative_step) * scale

    def _map_face_parent_coordinates(self, local_face: str, coordinate_a: float, coordinate_b: float) -> tuple[float, float, float]:
        mappings = {
            "S1": (coordinate_a, coordinate_b, -1.0),
            "S2": (coordinate_a, coordinate_b, 1.0),
            "S3": (coordinate_a, -1.0, coordinate_b),
            "S4": (1.0, coordinate_a, coordinate_b),
            "S5": (coordinate_a, 1.0, coordinate_b),
            "S6": (-1.0, coordinate_a, coordinate_b),
        }
        try:
            return mappings[local_face]
        except KeyError as error:
            raise ValueError(f"C3D8 不支持面标识 {local_face}。") from error

    def _build_face_normal(self, local_face: str, xi: float, eta: float, zeta: float) -> numpy.ndarray:
        jacobian = self._build_reference_jacobian(xi, eta, zeta)
        dxdxi = jacobian[0, :]
        dxdeta = jacobian[1, :]
        dxdzeta = jacobian[2, :]
        if local_face == "S1":
            return numpy.cross(dxdeta, dxdxi)
        if local_face == "S2":
            return numpy.cross(dxdxi, dxdeta)
        if local_face == "S3":
            return numpy.cross(dxdxi, dxdzeta)
        if local_face == "S4":
            return numpy.cross(dxdeta, dxdzeta)
        if local_face == "S5":
            return numpy.cross(dxdzeta, dxdxi)
        if local_face == "S6":
            return numpy.cross(dxdzeta, dxdeta)
        raise ValueError(f"C3D8 不支持面标识 {local_face}。")

    def _build_surface_shape_matrix(self, shape_values: numpy.ndarray) -> numpy.ndarray:
        shape_matrix = numpy.zeros((3, 24), dtype=float)
        for node_index, shape_value in enumerate(shape_values):
            base = 3 * node_index
            shape_matrix[0, base] = shape_value
            shape_matrix[1, base + 1] = shape_value
            shape_matrix[2, base + 2] = shape_value
        return shape_matrix
