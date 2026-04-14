"""?????????????"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pyfem.io import FIELD_KEY_E_IP, FIELD_KEY_S_IP, POSITION_INTEGRATION_POINT, RESULT_SOURCE_RAW, ResultField
from pyfem.post.common import (
    FIELD_METADATA_KEY_NATURAL_COORDINATES,
    FIELD_METADATA_KEY_OWNER_ELEMENT_KEYS,
    FIELD_METADATA_KEY_SAMPLE_WEIGHTS,
    FIELD_METADATA_KEY_SECTION_POINT_LABELS,
    build_measure_metadata,
    build_component_mapping,
    merge_component_names,
    resolve_strain_component_names,
    resolve_stress_component_names,
)


@dataclass(slots=True, frozen=True)
class RawFieldService:
    """???? rich output ???????????"""

    def build_fields(self, element_outputs: Mapping[str, Mapping[str, Any]]) -> tuple[ResultField, ...]:
        """?? raw integration-point strain/stress ????"""

        strain_values: dict[str, dict[str, float]] = {}
        stress_values: dict[str, dict[str, float]] = {}
        owner_element_keys: dict[str, str] = {}
        natural_coordinates: dict[str, tuple[float, ...]] = {}
        sample_weights: dict[str, float] = {}
        section_point_labels: dict[str, str] = {}
        strain_measures: dict[str, str] = {}
        stress_measures: dict[str, str] = {}
        tangent_measures: dict[str, str] = {}
        strain_component_names: tuple[str, ...] = ()
        stress_component_names: tuple[str, ...] = ()

        for element_key, output in element_outputs.items():
            integration_points = tuple(output.get("integration_points", ()))
            if not integration_points:
                continue

            type_key = str(output["type_key"])
            current_strain_components = resolve_strain_component_names(type_key)
            current_stress_components = resolve_stress_component_names(type_key)
            strain_component_names = merge_component_names(strain_component_names, current_strain_components)
            stress_component_names = merge_component_names(stress_component_names, current_stress_components)

            for integration_point in integration_points:
                target_key = str(integration_point["target_key"])
                strain_values[target_key] = build_component_mapping(
                    integration_point["strain"],
                    current_strain_components,
                )
                stress_values[target_key] = build_component_mapping(
                    integration_point["stress"],
                    current_stress_components,
                )
                owner_element_keys[target_key] = element_key
                natural_coordinates[target_key] = tuple(
                    float(value) for value in integration_point.get("natural_coordinates", ())
                )
                sample_weights[target_key] = float(integration_point.get("sample_weight", 0.0))
                strain_measures[target_key] = str(
                    integration_point.get("strain_measure", output.get("strain_measure", "unspecified"))
                )
                stress_measures[target_key] = str(
                    integration_point.get("stress_measure", output.get("stress_measure", "unspecified"))
                )
                tangent_measures[target_key] = str(
                    integration_point.get("tangent_measure", output.get("tangent_measure", "unspecified"))
                )
                section_point_label = integration_point.get("section_point_label")
                if section_point_label is not None:
                    section_point_labels[target_key] = str(section_point_label)

        fields: list[ResultField] = []
        if strain_values:
            fields.append(
                ResultField(
                    name=FIELD_KEY_E_IP,
                    position=POSITION_INTEGRATION_POINT,
                    values=strain_values,
                    source_type=RESULT_SOURCE_RAW,
                    component_names=strain_component_names,
                    metadata=self._build_metadata(
                        target_keys=tuple(strain_values.keys()),
                        owner_element_keys=owner_element_keys,
                        natural_coordinates=natural_coordinates,
                        sample_weights=sample_weights,
                        section_point_labels=section_point_labels,
                        strain_measures=strain_measures,
                        tangent_measures=tangent_measures,
                    ),
                )
            )
        if stress_values:
            fields.append(
                ResultField(
                    name=FIELD_KEY_S_IP,
                    position=POSITION_INTEGRATION_POINT,
                    values=stress_values,
                    source_type=RESULT_SOURCE_RAW,
                    component_names=stress_component_names,
                    metadata=self._build_metadata(
                        target_keys=tuple(stress_values.keys()),
                        owner_element_keys=owner_element_keys,
                        natural_coordinates=natural_coordinates,
                        sample_weights=sample_weights,
                        section_point_labels=section_point_labels,
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
        natural_coordinates: Mapping[str, tuple[float, ...]],
        sample_weights: Mapping[str, float],
        section_point_labels: Mapping[str, str],
        strain_measures: Mapping[str, str] | None = None,
        stress_measures: Mapping[str, str] | None = None,
        tangent_measures: Mapping[str, str],
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            FIELD_METADATA_KEY_OWNER_ELEMENT_KEYS: dict(owner_element_keys),
            FIELD_METADATA_KEY_NATURAL_COORDINATES: {
                str(target_key): tuple(value)
                for target_key, value in natural_coordinates.items()
            },
            FIELD_METADATA_KEY_SAMPLE_WEIGHTS: {
                str(target_key): float(value)
                for target_key, value in sample_weights.items()
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
        if section_point_labels:
            metadata[FIELD_METADATA_KEY_SECTION_POINT_LABELS] = {
                str(target_key): str(label)
                for target_key, label in section_point_labels.items()
            }
        return metadata
