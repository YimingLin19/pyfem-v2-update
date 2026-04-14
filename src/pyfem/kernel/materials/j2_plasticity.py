"""J2 各向同性硬化材料运行时。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy

from pyfem.foundation.errors import SolverError
from pyfem.foundation.types import Matrix, StateMap, Vector
from pyfem.kernel.materials.base import MaterialRuntime, MaterialUpdateResult

_SMALL_STRAIN_MODES = {"3d", "solid", "plane_strain"}
_FINITE_STRAIN_MODES = {"3d_total_lagrangian", "solid_total_lagrangian", "plane_strain_total_lagrangian"}
_SMALL_STRAIN_MEASURES = (
    "small_strain",
    "cauchy_small_strain",
    "d_cauchy_small_strain_d_small_strain",
)
_FINITE_STRAIN_MEASURES = (
    "green_lagrange",
    "second_piola_kirchhoff",
    "d_second_piola_kirchhoff_d_green_lagrange",
)


def _as_matrix(values: numpy.ndarray) -> Matrix:
    """将数组转换为矩阵元组。"""

    return tuple(tuple(float(item) for item in row) for row in values.tolist())


def _as_vector(values: numpy.ndarray) -> Vector:
    """将数组转换为向量元组。"""

    return tuple(float(item) for item in values.tolist())


@dataclass(slots=True)
class J2PlasticityRuntime(MaterialRuntime):
    """定义 J2 各向同性硬化材料运行时。"""

    name: str
    young_modulus: float
    poisson_ratio: float
    yield_stress: float
    hardening_modulus: float
    density: float = 0.0
    tangent_mode: str = "consistent"

    def __post_init__(self) -> None:
        """校验材料参数合法性。"""

        if self.young_modulus <= 0.0:
            raise SolverError("J2 塑性材料的 young_modulus 必须大于零。")
        if not (-1.0 < self.poisson_ratio < 0.5):
            raise SolverError("J2 塑性材料的 poisson_ratio 必须位于 (-1, 0.5)。")
        if self.yield_stress <= 0.0:
            raise SolverError("J2 塑性材料的 yield_stress 必须大于零。")
        if self.hardening_modulus < 0.0:
            raise SolverError("J2 塑性材料的 hardening_modulus 不能为负数。")
        if self.tangent_mode not in {"consistent", "numerical"}:
            raise SolverError("J2 塑性材料的 tangent_mode 仅支持 consistent 或 numerical。")

    def get_name(self) -> str:
        """返回材料运行时名称。"""

        return self.name

    def get_material_type(self) -> str:
        """返回材料运行时类型。"""

        return "j2_plasticity"

    def allocate_state(self) -> dict[str, Any]:
        """分配 J2 材料状态容器。"""

        return {
            "strain": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            "stress": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            "plastic_strain": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            "equivalent_plastic_strain": 0.0,
            "plastic_multiplier": 0.0,
            "yield_function": 0.0,
            "is_plastic": False,
            "mode": None,
            "kinematic_regime": "small_strain",
            "strain_measure": "small_strain",
            "stress_measure": "cauchy_small_strain",
            "tangent_measure": "d_cauchy_small_strain_d_small_strain",
            "tangent_mode": self.tangent_mode,
        }

    def update(self, strain: Vector, state: StateMap | None = None, mode: str = "3d") -> MaterialUpdateResult:
        """根据指定模式执行正式材料更新。"""

        normalized_mode = str(mode).strip().lower()
        if normalized_mode in {"plane_stress", "plane_stress_total_lagrangian"}:
            raise SolverError(
                "J2PlasticityRuntime 当前仅正式支持 plane_strain、3d/solid 以及对应的 total_lagrangian 模式，"
                "暂不支持 plane_stress。"
            )
        if normalized_mode in {"uniaxial", "beam_axial"}:
            return self._update_uniaxial_response(strain=strain, state=state, mode=normalized_mode)

        kinematic_regime = self._resolve_kinematic_regime(normalized_mode)
        reduced_strain = numpy.asarray(strain, dtype=float)
        reduced_stress, next_state, debug_context = self._update_reduced_response(
            reduced_strain=reduced_strain,
            state=state,
            mode=normalized_mode,
            kinematic_regime=kinematic_regime,
        )
        tangent = self._build_reduced_tangent(
            reduced_strain=reduced_strain,
            state=state,
            mode=normalized_mode,
            debug_context=debug_context,
        )
        strain_measure, stress_measure, tangent_measure = self._resolve_measure_contract(normalized_mode)
        next_state["tangent_mode"] = self.tangent_mode
        next_state["kinematic_regime"] = kinematic_regime
        next_state["strain_measure"] = strain_measure
        next_state["stress_measure"] = stress_measure
        next_state["tangent_measure"] = tangent_measure
        next_state["mode"] = normalized_mode
        return MaterialUpdateResult(
            stress=_as_vector(reduced_stress),
            tangent=_as_matrix(tangent),
            state=next_state,
            strain=_as_vector(reduced_strain),
            strain_measure=strain_measure,
            stress_measure=stress_measure,
            tangent_measure=tangent_measure,
        )

    def get_density(self) -> float:
        """返回材料密度。"""

        return self.density

    def describe(self) -> Mapping[str, Any]:
        """返回材料运行时的可序列化描述。"""

        return {
            "name": self.name,
            "material_type": self.get_material_type(),
            "young_modulus": self.young_modulus,
            "poisson_ratio": self.poisson_ratio,
            "yield_stress": self.yield_stress,
            "hardening_modulus": self.hardening_modulus,
            "density": self.density,
            "tangent_mode": self.tangent_mode,
        }

    def _update_uniaxial_response(
        self,
        *,
        strain: Vector,
        state: StateMap | None,
        mode: str,
    ) -> MaterialUpdateResult:
        """执行最小正式可用的一维弹塑性更新。"""

        if len(strain) != 1:
            raise SolverError("beam_axial/uniaxial 模式要求单一轴向应变分量。")

        total_strain = float(strain[0])
        previous_state = self.allocate_state() if state is None else dict(state)
        raw_plastic_strain = previous_state.get("plastic_strain", (0.0,))
        if isinstance(raw_plastic_strain, (tuple, list)):
            plastic_strain = float(raw_plastic_strain[0])
        else:
            plastic_strain = float(raw_plastic_strain)
        equivalent_plastic_strain = float(previous_state.get("equivalent_plastic_strain", 0.0))

        trial_stress = self.young_modulus * (total_strain - plastic_strain)
        current_yield_stress = self.yield_stress + self.hardening_modulus * equivalent_plastic_strain
        yield_function = abs(trial_stress) - current_yield_stress

        next_state = previous_state
        if yield_function <= max(1.0, self.yield_stress) * 1.0e-10:
            stress = trial_stress
            tangent_value = self.young_modulus
            plastic_multiplier = 0.0
            is_plastic = False
        else:
            plastic_multiplier = yield_function / (self.young_modulus + self.hardening_modulus)
            sign = 1.0 if trial_stress >= 0.0 else -1.0
            stress = sign * (current_yield_stress + self.hardening_modulus * plastic_multiplier)
            plastic_strain += plastic_multiplier * sign
            equivalent_plastic_strain += plastic_multiplier
            tangent_value = self._build_uniaxial_tangent()
            is_plastic = True

        next_state["strain"] = (float(total_strain),)
        next_state["stress"] = (float(stress),)
        next_state["plastic_strain"] = (float(plastic_strain),)
        next_state["equivalent_plastic_strain"] = float(equivalent_plastic_strain)
        next_state["plastic_multiplier"] = float(plastic_multiplier)
        next_state["yield_function"] = 0.0 if is_plastic else float(max(yield_function, 0.0))
        next_state["is_plastic"] = bool(is_plastic)
        next_state["mode"] = mode
        next_state["kinematic_regime"] = "small_strain"
        next_state["strain_measure"] = "small_strain"
        next_state["stress_measure"] = "cauchy_small_strain"
        next_state["tangent_measure"] = "d_cauchy_small_strain_d_small_strain"
        next_state["tangent_mode"] = self.tangent_mode

        tangent = numpy.asarray(((tangent_value,),), dtype=float)
        if self.tangent_mode == "numerical":
            tangent = self._compute_uniaxial_numerical_tangent(total_strain=total_strain, state=state, mode=mode)

        return MaterialUpdateResult(
            stress=(float(stress),),
            tangent=_as_matrix(tangent),
            state=next_state,
            strain=(float(total_strain),),
            strain_measure="small_strain",
            stress_measure="cauchy_small_strain",
            tangent_measure="d_cauchy_small_strain_d_small_strain",
        )

    def _build_uniaxial_tangent(self) -> float:
        """返回一维一致切线模量。"""

        if self.hardening_modulus == 0.0:
            return 0.0
        return self.young_modulus * self.hardening_modulus / (self.young_modulus + self.hardening_modulus)

    def _compute_uniaxial_numerical_tangent(
        self,
        *,
        total_strain: float,
        state: StateMap | None,
        mode: str,
    ) -> numpy.ndarray:
        """以中心差分构造一维调试切线。"""

        step_size = 1.0e-8 * max(1.0, abs(total_strain))
        stress_plus = self._update_uniaxial_response(strain=(total_strain + step_size,), state=state, mode=mode).stress[0]
        stress_minus = self._update_uniaxial_response(strain=(total_strain - step_size,), state=state, mode=mode).stress[0]
        return numpy.asarray((((stress_plus - stress_minus) / (2.0 * step_size),),), dtype=float)

    def _build_reduced_tangent(
        self,
        *,
        reduced_strain: numpy.ndarray,
        state: StateMap | None,
        mode: str,
        debug_context: Mapping[str, Any],
    ) -> numpy.ndarray:
        """构造当前积分点的正式切线矩阵。"""

        if not bool(debug_context["is_plastic"]):
            return self._reduce_tangent(self._build_elastic_tangent_full(), mode=mode)
        if self.tangent_mode == "numerical":
            return self._compute_numerical_tangent(reduced_strain=reduced_strain, state=state, mode=mode)
        full_tangent = self._build_consistent_tangent_full(debug_context=debug_context)
        return self._reduce_tangent(full_tangent, mode=mode)

    def _compute_numerical_tangent(
        self,
        *,
        reduced_strain: numpy.ndarray,
        state: StateMap | None,
        mode: str,
    ) -> numpy.ndarray:
        """以数值差分构造调试用切线矩阵。"""

        size = reduced_strain.size
        tangent = numpy.zeros((size, size), dtype=float)
        reference_scale = max(1.0, float(numpy.linalg.norm(reduced_strain)))
        step_size = 1.0e-8 * reference_scale
        for column in range(size):
            perturbation = numpy.zeros(size, dtype=float)
            perturbation[column] = step_size
            stress_plus, _, _ = self._update_reduced_response(
                reduced_strain=reduced_strain + perturbation,
                state=state,
                mode=mode,
                kinematic_regime=self._resolve_kinematic_regime(mode),
            )
            stress_minus, _, _ = self._update_reduced_response(
                reduced_strain=reduced_strain - perturbation,
                state=state,
                mode=mode,
                kinematic_regime=self._resolve_kinematic_regime(mode),
            )
            tangent[:, column] = (stress_plus - stress_minus) / (2.0 * step_size)
        return 0.5 * (tangent + tangent.T)

    def _build_consistent_tangent_full(self, *, debug_context: Mapping[str, Any]) -> numpy.ndarray:
        """根据返回映射结果构造算法一致切线。"""

        _, shear_modulus = self._elastic_moduli()
        bulk_modulus, _ = self._elastic_moduli()
        delta_lambda = float(debug_context["plastic_multiplier"])
        equivalent_trial_stress = float(debug_context["equivalent_trial_stress"])
        flow_direction = numpy.asarray(debug_context["flow_direction"], dtype=float)
        beta = 1.0 - 3.0 * shear_modulus * delta_lambda / equivalent_trial_stress
        direction_factor = (1.0 / (3.0 * shear_modulus + self.hardening_modulus)) - (
            delta_lambda / equivalent_trial_stress
        )

        full_tangent = numpy.zeros((6, 6), dtype=float)
        for column in range(6):
            strain_basis = numpy.zeros(6, dtype=float)
            strain_basis[column] = 1.0
            strain_tensor = self._full_vector_to_strain_tensor(tuple(float(item) for item in strain_basis.tolist()))
            deviatoric_strain_tensor = self._deviatoric_part(strain_tensor)
            directional_projection = float(numpy.tensordot(flow_direction, deviatoric_strain_tensor))
            stress_tensor = (
                bulk_modulus * numpy.trace(strain_tensor) * numpy.eye(3, dtype=float)
                + 2.0 * shear_modulus * beta * deviatoric_strain_tensor
                - 6.0 * shear_modulus**2 * direction_factor * directional_projection * flow_direction
            )
            full_tangent[:, column] = numpy.asarray(self._stress_tensor_to_full_vector(stress_tensor), dtype=float)
        return 0.5 * (full_tangent + full_tangent.T)

    def _update_reduced_response(
        self,
        *,
        reduced_strain: numpy.ndarray,
        state: StateMap | None,
        mode: str,
        kinematic_regime: str,
    ) -> tuple[numpy.ndarray, dict[str, Any], dict[str, Any]]:
        """更新指定模式下的应力响应，并返回调试上下文。"""

        total_strain_tensor = self._strain_vector_to_tensor(reduced_strain, mode=mode)
        full_stress_tensor, next_state, debug_context = self._update_full_response(
            total_strain_tensor=total_strain_tensor,
            state=state,
            kinematic_regime=kinematic_regime,
            mode=mode,
        )
        reduced_stress = self._stress_tensor_to_vector(full_stress_tensor, mode=mode)
        next_state["strain"] = self._strain_tensor_to_full_vector(total_strain_tensor)
        next_state["stress"] = self._stress_tensor_to_full_vector(full_stress_tensor)
        next_state["mode"] = mode
        return reduced_stress, next_state, debug_context

    def _update_full_response(
        self,
        *,
        total_strain_tensor: numpy.ndarray,
        state: StateMap | None,
        kinematic_regime: str,
        mode: str,
    ) -> tuple[numpy.ndarray, dict[str, Any], dict[str, Any]]:
        """在三维张量空间执行正式返回映射。"""

        previous_state = self.allocate_state() if state is None else dict(state)
        plastic_strain_tensor = self._full_vector_to_strain_tensor(previous_state.get("plastic_strain", (0.0,) * 6))
        equivalent_plastic_strain = float(previous_state.get("equivalent_plastic_strain", 0.0))
        strain_measure, stress_measure, tangent_measure = self._resolve_measure_contract(mode)

        bulk_modulus, shear_modulus = self._elastic_moduli()
        elastic_trial_strain = total_strain_tensor - plastic_strain_tensor
        trial_stress_tensor = (
            bulk_modulus * numpy.trace(elastic_trial_strain) * numpy.eye(3, dtype=float)
            + 2.0 * shear_modulus * self._deviatoric_part(elastic_trial_strain)
        )
        deviatoric_trial_stress = self._deviatoric_part(trial_stress_tensor)
        deviatoric_norm = float(numpy.sqrt(numpy.tensordot(deviatoric_trial_stress, deviatoric_trial_stress)))
        equivalent_trial_stress = float(numpy.sqrt(1.5) * deviatoric_norm)
        current_yield_stress = self.yield_stress + self.hardening_modulus * equivalent_plastic_strain
        yield_function = equivalent_trial_stress - current_yield_stress

        if yield_function <= max(1.0, self.yield_stress) * 1.0e-10 or deviatoric_norm <= 1.0e-14:
            next_state = previous_state
            next_state["yield_function"] = float(max(yield_function, 0.0))
            next_state["plastic_multiplier"] = 0.0
            next_state["is_plastic"] = False
            next_state["strain_measure"] = strain_measure
            next_state["stress_measure"] = stress_measure
            next_state["tangent_measure"] = tangent_measure
            next_state["kinematic_regime"] = kinematic_regime
            debug_context = {
                "is_plastic": False,
                "plastic_multiplier": 0.0,
                "equivalent_trial_stress": max(equivalent_trial_stress, 1.0),
                "flow_direction": numpy.zeros((3, 3), dtype=float),
            }
            return trial_stress_tensor, next_state, debug_context

        flow_direction = deviatoric_trial_stress / deviatoric_norm
        plastic_multiplier = yield_function / (3.0 * shear_modulus + self.hardening_modulus)
        corrected_deviatoric_stress = (
            deviatoric_trial_stress
            - 2.0 * shear_modulus * plastic_multiplier * numpy.sqrt(1.5) * flow_direction
        )
        corrected_stress_tensor = corrected_deviatoric_stress + numpy.trace(trial_stress_tensor) / 3.0 * numpy.eye(
            3,
            dtype=float,
        )
        updated_plastic_strain = plastic_strain_tensor + plastic_multiplier * numpy.sqrt(1.5) * flow_direction
        updated_equivalent_plastic_strain = equivalent_plastic_strain + plastic_multiplier

        next_state = previous_state
        next_state["plastic_strain"] = self._strain_tensor_to_full_vector(updated_plastic_strain)
        next_state["equivalent_plastic_strain"] = float(updated_equivalent_plastic_strain)
        next_state["plastic_multiplier"] = float(plastic_multiplier)
        next_state["yield_function"] = 0.0
        next_state["is_plastic"] = True
        next_state["strain_measure"] = strain_measure
        next_state["stress_measure"] = stress_measure
        next_state["tangent_measure"] = tangent_measure
        next_state["kinematic_regime"] = kinematic_regime
        debug_context = {
            "is_plastic": True,
            "plastic_multiplier": float(plastic_multiplier),
            "equivalent_trial_stress": float(equivalent_trial_stress),
            "flow_direction": flow_direction,
        }
        return corrected_stress_tensor, next_state, debug_context

    def _resolve_kinematic_regime(self, mode: str) -> str:
        if mode in _SMALL_STRAIN_MODES:
            return "small_strain"
        if mode in _FINITE_STRAIN_MODES:
            return "finite_strain"
        raise SolverError(f"J2PlasticityRuntime 当前不支持模式 {mode}。")

    def _resolve_measure_contract(self, mode: str) -> tuple[str, str, str]:
        if mode in _SMALL_STRAIN_MODES or mode in {"uniaxial", "beam_axial"}:
            return _SMALL_STRAIN_MEASURES
        if mode in _FINITE_STRAIN_MODES:
            return _FINITE_STRAIN_MEASURES
        raise SolverError(f"J2PlasticityRuntime 当前不支持模式 {mode}。")

    def _elastic_moduli(self) -> tuple[float, float]:
        bulk_modulus = self.young_modulus / (3.0 * (1.0 - 2.0 * self.poisson_ratio))
        shear_modulus = self.young_modulus / (2.0 * (1.0 + self.poisson_ratio))
        return bulk_modulus, shear_modulus

    def _build_elastic_tangent_full(self) -> numpy.ndarray:
        bulk_modulus, shear_modulus = self._elastic_moduli()
        lam = bulk_modulus - 2.0 * shear_modulus / 3.0
        tangent = numpy.zeros((6, 6), dtype=float)
        tangent[0:3, 0:3] = lam
        tangent[0, 0] += 2.0 * shear_modulus
        tangent[1, 1] += 2.0 * shear_modulus
        tangent[2, 2] += 2.0 * shear_modulus
        tangent[3, 3] = shear_modulus
        tangent[4, 4] = shear_modulus
        tangent[5, 5] = shear_modulus
        return tangent

    def _reduce_tangent(self, full_tangent: numpy.ndarray, *, mode: str) -> numpy.ndarray:
        if mode in {"3d", "solid", "3d_total_lagrangian", "solid_total_lagrangian"}:
            return full_tangent
        if mode in {"plane_strain", "plane_strain_total_lagrangian"}:
            reduced_indices = (0, 1, 3)
            return full_tangent[numpy.ix_(reduced_indices, reduced_indices)]
        raise SolverError(f"J2PlasticityRuntime 当前不支持模式 {mode}。")

    def _strain_vector_to_tensor(self, strain: numpy.ndarray, *, mode: str) -> numpy.ndarray:
        if mode in {"3d", "solid", "3d_total_lagrangian", "solid_total_lagrangian"}:
            if strain.size != 6:
                raise SolverError("三维 J2 更新要求 6 分量应变向量。")
            return self._full_vector_to_strain_tensor(tuple(float(item) for item in strain.tolist()))
        if mode in {"plane_strain", "plane_strain_total_lagrangian"}:
            if strain.size != 3:
                raise SolverError("平面应变 J2 更新要求 3 分量应变向量。")
            return numpy.asarray(
                (
                    (strain[0], 0.5 * strain[2], 0.0),
                    (0.5 * strain[2], strain[1], 0.0),
                    (0.0, 0.0, 0.0),
                ),
                dtype=float,
            )
        raise SolverError(f"J2PlasticityRuntime 当前不支持模式 {mode}。")

    def _stress_tensor_to_vector(self, stress_tensor: numpy.ndarray, *, mode: str) -> numpy.ndarray:
        if mode in {"3d", "solid", "3d_total_lagrangian", "solid_total_lagrangian"}:
            return numpy.asarray(self._stress_tensor_to_full_vector(stress_tensor), dtype=float)
        if mode in {"plane_strain", "plane_strain_total_lagrangian"}:
            return numpy.asarray((stress_tensor[0, 0], stress_tensor[1, 1], stress_tensor[0, 1]), dtype=float)
        raise SolverError(f"J2PlasticityRuntime 当前不支持模式 {mode}。")

    def _deviatoric_part(self, tensor: numpy.ndarray) -> numpy.ndarray:
        return tensor - numpy.trace(tensor) / 3.0 * numpy.eye(3, dtype=float)

    def _full_vector_to_strain_tensor(self, strain: Vector) -> numpy.ndarray:
        strain_array = numpy.asarray(strain, dtype=float)
        return numpy.asarray(
            (
                (strain_array[0], 0.5 * strain_array[3], 0.5 * strain_array[5]),
                (0.5 * strain_array[3], strain_array[1], 0.5 * strain_array[4]),
                (0.5 * strain_array[5], 0.5 * strain_array[4], strain_array[2]),
            ),
            dtype=float,
        )

    def _strain_tensor_to_full_vector(self, strain_tensor: numpy.ndarray) -> tuple[float, ...]:
        return (
            float(strain_tensor[0, 0]),
            float(strain_tensor[1, 1]),
            float(strain_tensor[2, 2]),
            float(2.0 * strain_tensor[0, 1]),
            float(2.0 * strain_tensor[1, 2]),
            float(2.0 * strain_tensor[0, 2]),
        )

    def _stress_tensor_to_full_vector(self, stress_tensor: numpy.ndarray) -> tuple[float, ...]:
        return (
            float(stress_tensor[0, 0]),
            float(stress_tensor[1, 1]),
            float(stress_tensor[2, 2]),
            float(stress_tensor[0, 1]),
            float(stress_tensor[1, 2]),
            float(stress_tensor[0, 2]),
        )
