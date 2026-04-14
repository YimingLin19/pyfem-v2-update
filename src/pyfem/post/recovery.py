"""????????"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy

from pyfem.foundation.errors import PyFEMError
from pyfem.io import (
    FIELD_KEY_E_IP,
    FIELD_KEY_E_REC,
    FIELD_KEY_S_IP,
    FIELD_KEY_S_REC,
    POSITION_ELEMENT_NODAL,
    RECOVERY_METHOD_DIRECT_EXTRAPOLATION,
    RECOVERY_METHOD_LEAST_SQUARES,
    RECOVERY_METHOD_PATCH,
    RESULT_SOURCE_RECOVERED,
    ResultField,
)
from pyfem.post.common import (
    FIELD_METADATA_KEY_AVERAGING_DOMAINS,
    FIELD_METADATA_KEY_AVERAGING_WEIGHTS,
    FIELD_METADATA_KEY_BASE_TARGET_KEYS,
    FIELD_METADATA_KEY_OWNER_ELEMENT_KEYS,
    FIELD_METADATA_KEY_RECOVERY_METHOD,
    FIELD_METADATA_KEY_RECOVERY_SOURCE_FIELD,
    FIELD_METADATA_KEY_SECTION_NODAL_SEMANTICS,
    build_measure_metadata,
    build_component_mapping,
    extract_component_vector,
    merge_component_names,
    resolve_strain_component_names,
    resolve_stress_component_names,
)


@dataclass(slots=True, frozen=True)
class RecoveryService:
    """??????????????????"""

    def available_strategies(self) -> tuple[str, ...]:
        """???????????????"""

        return (
            RECOVERY_METHOD_DIRECT_EXTRAPOLATION,
            RECOVERY_METHOD_LEAST_SQUARES,
            RECOVERY_METHOD_PATCH,
        )

    def build_fields(
        self,
        element_outputs: Mapping[str, Mapping[str, Any]],
        *,
        strategy: str = RECOVERY_METHOD_DIRECT_EXTRAPOLATION,
    ) -> tuple[ResultField, ...]:
        """?? recovered element-nodal strain/stress ????"""

        if strategy != RECOVERY_METHOD_DIRECT_EXTRAPOLATION:
            raise NotImplementedError(f"????? {RECOVERY_METHOD_DIRECT_EXTRAPOLATION}??? {strategy}?")

        strain_values: dict[str, dict[str, float]] = {}
        stress_values: dict[str, dict[str, float]] = {}
        owner_element_keys: dict[str, str] = {}
        base_target_keys: dict[str, str] = {}
        averaging_domains: dict[str, dict[str, str]] = {}
        averaging_weights: dict[str, float] = {}
        section_nodal_semantics: dict[str, str] = {}
        strain_measures: dict[str, str] = {}
        stress_measures: dict[str, str] = {}
        tangent_measures: dict[str, str] = {}
        strain_component_names: tuple[str, ...] = ()
        stress_component_names: tuple[str, ...] = ()

        for element_key, output in element_outputs.items():
            recovery = output.get("recovery")
            integration_points = tuple(output.get("integration_points", ()))
            if not isinstance(recovery, Mapping) or not integration_points:
                continue

            extrapolation_matrix = numpy.asarray(recovery.get("extrapolation_matrix", ()), dtype=float)
            if extrapolation_matrix.size == 0:
                continue

            type_key = str(output["type_key"])
            current_strain_components = resolve_strain_component_names(type_key)
            current_stress_components = resolve_stress_component_names(type_key)
            strain_component_names = merge_component_names(strain_component_names, current_strain_components)
            stress_component_names = merge_component_names(stress_component_names, current_stress_components)

            target_keys = tuple(str(item) for item in recovery.get("target_keys", ()))
            if extrapolation_matrix.shape[0] != len(target_keys):
                raise PyFEMError(f"?? {element_key} ???????? target_keys ??????")
            if extrapolation_matrix.shape[1] != len(integration_points):
                raise PyFEMError(f"?? {element_key} ?????????????????")

            strain_samples = numpy.vstack(
                [extract_component_vector(item["strain"], current_strain_components) for item in integration_points]
            )
            stress_samples = numpy.vstack(
                [extract_component_vector(item["stress"], current_stress_components) for item in integration_points]
            )
            recovered_strain = extrapolation_matrix @ strain_samples
            recovered_stress = extrapolation_matrix @ stress_samples

            element_base_target_keys = {
                str(target_key): str(base_key)
                for target_key, base_key in recovery.get("base_target_keys", {}).items()
            }
            averaging_domain = {
                "scope_name": str(output.get("scope_name", "")),
                "section_name": str(output.get("section_name", "")),
                "material_name": str(output.get("material_name", "")),
            }
            averaging_weight = float(output.get("averaging_weight", 0.0))
            section_nodal_semantic = str(recovery.get("section_nodal_semantics", ""))
            strain_measure = str(output.get("strain_measure", "unspecified"))
            stress_measure = str(output.get("stress_measure", "unspecified"))
            tangent_measure = str(output.get("tangent_measure", "unspecified"))

            for row_index, target_key in enumerate(target_keys):
                strain_values[target_key] = build_component_mapping(
                    recovered_strain[row_index],
                    current_strain_components,
                )
                stress_values[target_key] = build_component_mapping(
                    recovered_stress[row_index],
                    current_stress_components,
                )
                owner_element_keys[target_key] = element_key
                base_target_keys[target_key] = element_base_target_keys.get(target_key, target_key)
                averaging_domains[target_key] = dict(averaging_domain)
                averaging_weights[target_key] = averaging_weight
                strain_measures[target_key] = strain_measure
                stress_measures[target_key] = stress_measure
                tangent_measures[target_key] = tangent_measure
                if section_nodal_semantic:
                    section_nodal_semantics[target_key] = section_nodal_semantic

        fields: list[ResultField] = []
        if strain_values:
            fields.append(
                ResultField(
                    name=FIELD_KEY_E_REC,
                    position=POSITION_ELEMENT_NODAL,
                    values=strain_values,
                    source_type=RESULT_SOURCE_RECOVERED,
                    component_names=strain_component_names,
                    metadata=self._build_metadata(
                        target_keys=tuple(strain_values.keys()),
                        owner_element_keys=owner_element_keys,
                        base_target_keys=base_target_keys,
                        averaging_domains=averaging_domains,
                        averaging_weights=averaging_weights,
                        section_nodal_semantics=section_nodal_semantics,
                        recovered_from=FIELD_KEY_E_IP,
                        strategy=strategy,
                        strain_measures=strain_measures,
                        tangent_measures=tangent_measures,
                    ),
                )
            )
        if stress_values:
            fields.append(
                ResultField(
                    name=FIELD_KEY_S_REC,
                    position=POSITION_ELEMENT_NODAL,
                    values=stress_values,
                    source_type=RESULT_SOURCE_RECOVERED,
                    component_names=stress_component_names,
                    metadata=self._build_metadata(
                        target_keys=tuple(stress_values.keys()),
                        owner_element_keys=owner_element_keys,
                        base_target_keys=base_target_keys,
                        averaging_domains=averaging_domains,
                        averaging_weights=averaging_weights,
                        section_nodal_semantics=section_nodal_semantics,
                        recovered_from=FIELD_KEY_S_IP,
                        strategy=strategy,
                        stress_measures=stress_measures,
                        tangent_measures=tangent_measures,
                    ),
                )
            )
        return tuple(fields)

    def _build_metadata(
        self,
        *,
        target_keys: tuple[str, ...],
        owner_element_keys: Mapping[str, str],
        base_target_keys: Mapping[str, str],
        averaging_domains: Mapping[str, Mapping[str, str]],
        averaging_weights: Mapping[str, float],
        section_nodal_semantics: Mapping[str, str],
        recovered_from: str,
        strategy: str,
        strain_measures: Mapping[str, str] | None = None,
        stress_measures: Mapping[str, str] | None = None,
        tangent_measures: Mapping[str, str],
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            FIELD_METADATA_KEY_RECOVERY_METHOD: strategy,
            FIELD_METADATA_KEY_RECOVERY_SOURCE_FIELD: recovered_from,
            FIELD_METADATA_KEY_OWNER_ELEMENT_KEYS: dict(owner_element_keys),
            FIELD_METADATA_KEY_BASE_TARGET_KEYS: dict(base_target_keys),
            FIELD_METADATA_KEY_AVERAGING_DOMAINS: {
                str(target_key): dict(domain)
                for target_key, domain in averaging_domains.items()
            },
            FIELD_METADATA_KEY_AVERAGING_WEIGHTS: {
                str(target_key): float(weight)
                for target_key, weight in averaging_weights.items()
            },
        }
        metadata.update(
            build_measure_metadata(
                target_keys=target_keys,
                strain_measures=strain_measures,
                stress_measures=stress_measures,
                tangent_measures=tangent_measures,
            )
        )
        if section_nodal_semantics:
            metadata[FIELD_METADATA_KEY_SECTION_NODAL_SEMANTICS] = {
                str(target_key): str(semantic)
                for target_key, semantic in section_nodal_semantics.items()
            }
        return metadata
