"""????????"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy

from pyfem.io import FIELD_KEY_S_AVG, POSITION_NODE_AVERAGED, RESULT_SOURCE_AVERAGED, ResultField
from pyfem.post.common import (
    FIELD_METADATA_KEY_AVERAGING_DOMAINS,
    FIELD_METADATA_KEY_AVERAGING_GROUPS,
    FIELD_METADATA_KEY_AVERAGING_WEIGHTS,
    FIELD_METADATA_KEY_BASE_TARGET_KEYS,
    FIELD_METADATA_KEY_STRESS_MEASURES,
    FIELD_METADATA_KEY_TANGENT_MEASURES,
    build_measure_metadata,
    build_averaging_group_key,
    build_component_mapping,
    extract_component_vector,
)


@dataclass(slots=True, frozen=True)
class AveragingService:
    """? recovered stress ??????????????"""

    def build_fields(self, recovered_stress_field: ResultField | None) -> tuple[ResultField, ...]:
        """?? averaged stress ????"""

        if recovered_stress_field is None or not recovered_stress_field.values:
            return ()

        base_target_keys = {
            str(target_key): str(base_key)
            for target_key, base_key in recovered_stress_field.metadata.get(FIELD_METADATA_KEY_BASE_TARGET_KEYS, {}).items()
        }
        averaging_domains = {
            str(target_key): dict(domain)
            for target_key, domain in recovered_stress_field.metadata.get(FIELD_METADATA_KEY_AVERAGING_DOMAINS, {}).items()
        }
        averaging_weights = {
            str(target_key): float(weight)
            for target_key, weight in recovered_stress_field.metadata.get(FIELD_METADATA_KEY_AVERAGING_WEIGHTS, {}).items()
        }
        recovered_stress_measures = {
            str(target_key): str(value)
            for target_key, value in recovered_stress_field.metadata.get(FIELD_METADATA_KEY_STRESS_MEASURES, {}).items()
        }
        recovered_tangent_measures = {
            str(target_key): str(value)
            for target_key, value in recovered_stress_field.metadata.get(FIELD_METADATA_KEY_TANGENT_MEASURES, {}).items()
        }
        component_names = recovered_stress_field.component_names

        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for target_key, value in recovered_stress_field.values.items():
            normalized_target_key = str(target_key)
            base_target_key = base_target_keys.get(normalized_target_key, normalized_target_key)
            domain = averaging_domains.get(
                normalized_target_key,
                {"scope_name": "", "section_name": "", "material_name": ""},
            )
            group_key = build_averaging_group_key(
                str(domain.get("scope_name", "")),
                str(domain.get("section_name", "")),
                str(domain.get("material_name", "")),
            )
            weight = float(averaging_weights.get(normalized_target_key, 0.0))
            entry = grouped.setdefault(
                (group_key, base_target_key),
                {
                    "weighted_sum": numpy.zeros(len(component_names), dtype=float),
                    "weight_total": 0.0,
                    "fallback_count": 0,
                    "domain": dict(domain),
                    "stress_measures": [],
                    "tangent_measures": [],
                },
            )
            vector = extract_component_vector(value, component_names)
            if weight > 0.0:
                entry["weighted_sum"] += weight * vector
                entry["weight_total"] += weight
            else:
                entry["weighted_sum"] += vector
                entry["fallback_count"] += 1
            entry["stress_measures"].append(recovered_stress_measures.get(normalized_target_key, "unspecified"))
            entry["tangent_measures"].append(recovered_tangent_measures.get(normalized_target_key, "unspecified"))

        duplicate_counts = Counter(base_target_key for _, base_target_key in grouped.keys())
        averaged_values: dict[str, dict[str, float]] = {}
        averaged_base_target_keys: dict[str, str] = {}
        averaged_groups: dict[str, str] = {}
        averaged_domains: dict[str, dict[str, str]] = {}
        averaged_weights: dict[str, float] = {}
        averaged_stress_measures: dict[str, str] = {}
        averaged_tangent_measures: dict[str, str] = {}

        for (group_key, base_target_key), payload in grouped.items():
            weight_total = float(payload["weight_total"])
            fallback_count = int(payload["fallback_count"])
            if weight_total > 0.0:
                averaged_vector = payload["weighted_sum"] / weight_total
                effective_weight = weight_total
            else:
                divisor = max(fallback_count, 1)
                averaged_vector = payload["weighted_sum"] / divisor
                effective_weight = float(divisor)

            if duplicate_counts[base_target_key] == 1:
                target_key = base_target_key
            else:
                target_key = f"{base_target_key}.avg[{group_key}]"

            averaged_values[target_key] = build_component_mapping(averaged_vector, component_names)
            averaged_base_target_keys[target_key] = base_target_key
            averaged_groups[target_key] = group_key
            averaged_domains[target_key] = dict(payload["domain"])
            averaged_weights[target_key] = effective_weight
            stress_measure_options = tuple(dict.fromkeys(str(value) for value in payload["stress_measures"]))
            tangent_measure_options = tuple(dict.fromkeys(str(value) for value in payload["tangent_measures"]))
            averaged_stress_measures[target_key] = stress_measure_options[0] if len(stress_measure_options) == 1 else "mixed"
            averaged_tangent_measures[target_key] = tangent_measure_options[0] if len(tangent_measure_options) == 1 else "mixed"

        if not averaged_values:
            return ()

        return (
            ResultField(
                name=FIELD_KEY_S_AVG,
                position=POSITION_NODE_AVERAGED,
                values=averaged_values,
                source_type=RESULT_SOURCE_AVERAGED,
                component_names=component_names,
                metadata=self._build_metadata(
                    target_keys=tuple(averaged_values.keys()),
                    averaged_base_target_keys=averaged_base_target_keys,
                    averaged_groups=averaged_groups,
                    averaged_domains=averaged_domains,
                    averaged_weights=averaged_weights,
                    averaged_stress_measures=averaged_stress_measures,
                    averaged_tangent_measures=averaged_tangent_measures,
                ),
            ),
        )

    def _build_metadata(
        self,
        *,
        target_keys: tuple[str, ...],
        averaged_base_target_keys: Mapping[str, str],
        averaged_groups: Mapping[str, str],
        averaged_domains: Mapping[str, Mapping[str, str]],
        averaged_weights: Mapping[str, float],
        averaged_stress_measures: Mapping[str, str],
        averaged_tangent_measures: Mapping[str, str],
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            FIELD_METADATA_KEY_BASE_TARGET_KEYS: dict(averaged_base_target_keys),
            FIELD_METADATA_KEY_AVERAGING_GROUPS: dict(averaged_groups),
            FIELD_METADATA_KEY_AVERAGING_DOMAINS: {
                str(target_key): dict(domain)
                for target_key, domain in averaged_domains.items()
            },
            FIELD_METADATA_KEY_AVERAGING_WEIGHTS: {
                str(target_key): float(weight)
                for target_key, weight in averaged_weights.items()
            },
        }
        metadata.update(
            build_measure_metadata(
                target_keys=target_keys,
                stress_measures=averaged_stress_measures,
                tangent_measures=averaged_tangent_measures,
            )
        )
        return metadata
