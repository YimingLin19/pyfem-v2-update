"""????????"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy

from pyfem.io import (
    FIELD_KEY_S_AVG,
    FIELD_KEY_S_IP,
    FIELD_KEY_S_PRINCIPAL_AVG,
    FIELD_KEY_S_PRINCIPAL_IP,
    FIELD_KEY_S_PRINCIPAL_REC,
    FIELD_KEY_S_REC,
    FIELD_KEY_S_VM_AVG,
    FIELD_KEY_S_VM_IP,
    FIELD_KEY_S_VM_REC,
    FIELD_KEY_U,
    FIELD_KEY_U_MAG,
    RESULT_SOURCE_DERIVED,
    ResultField,
)
from pyfem.post.common import (
    FIELD_METADATA_KEY_DERIVED_FROM,
    PRINCIPAL_COMPONENT_NAMES,
    build_component_mapping,
    extract_component_vector,
)

_MAGNITUDE_COMPONENT_NAMES = ("MAGNITUDE",)
_MISES_COMPONENT_NAMES = ("MISES",)
_STRESS_DERIVED_SPECS = (
    (FIELD_KEY_S_IP, FIELD_KEY_S_VM_IP, FIELD_KEY_S_PRINCIPAL_IP),
    (FIELD_KEY_S_REC, FIELD_KEY_S_VM_REC, FIELD_KEY_S_PRINCIPAL_REC),
    (FIELD_KEY_S_AVG, FIELD_KEY_S_VM_AVG, FIELD_KEY_S_PRINCIPAL_AVG),
)


@dataclass(slots=True, frozen=True)
class DerivedFieldService:
    """????????????????"""

    def build_fields(self, field_registry: Mapping[str, ResultField]) -> tuple[ResultField, ...]:
        """?????????????????"""

        fields: list[ResultField] = []
        displacement_field = field_registry.get(FIELD_KEY_U)
        if displacement_field is not None and displacement_field.values:
            fields.append(self.build_displacement_magnitude_field(displacement_field))

        for source_field_name, mises_field_name, principal_field_name in _STRESS_DERIVED_SPECS:
            stress_field = field_registry.get(source_field_name)
            if stress_field is None or not stress_field.values:
                continue
            fields.extend(
                self.build_stress_derived_fields(
                    stress_field,
                    mises_field_name=mises_field_name,
                    principal_field_name=principal_field_name,
                )
            )
        return tuple(fields)

    def build_displacement_magnitude_field(self, displacement_field: ResultField) -> ResultField:
        """????????"""

        values = {
            str(target_key): build_component_mapping(
                (float(numpy.linalg.norm(extract_component_vector(value, displacement_field.component_names))),),
                _MAGNITUDE_COMPONENT_NAMES,
            )
            for target_key, value in displacement_field.values.items()
        }
        metadata = dict(displacement_field.metadata)
        metadata[FIELD_METADATA_KEY_DERIVED_FROM] = displacement_field.name
        return ResultField(
            name=FIELD_KEY_U_MAG,
            position=displacement_field.position,
            values=values,
            source_type=RESULT_SOURCE_DERIVED,
            component_names=_MAGNITUDE_COMPONENT_NAMES,
            metadata=metadata,
        )

    def build_stress_derived_fields(
        self,
        stress_field: ResultField,
        *,
        mises_field_name: str,
        principal_field_name: str,
    ) -> tuple[ResultField, ResultField]:
        """??????? von Mises ??????"""

        mises_values: dict[str, dict[str, float]] = {}
        principal_values: dict[str, dict[str, float]] = {}
        for target_key, value in stress_field.values.items():
            tensor = self._build_stress_tensor(value, stress_field.component_names)
            principal = tuple(float(item) for item in sorted(numpy.linalg.eigvalsh(tensor), reverse=True))
            mises = float(self._compute_von_mises(tensor))
            mises_values[str(target_key)] = build_component_mapping((mises,), _MISES_COMPONENT_NAMES)
            principal_values[str(target_key)] = build_component_mapping(principal, PRINCIPAL_COMPONENT_NAMES)

        metadata = dict(stress_field.metadata)
        metadata[FIELD_METADATA_KEY_DERIVED_FROM] = stress_field.name
        return (
            ResultField(
                name=mises_field_name,
                position=stress_field.position,
                values=mises_values,
                source_type=RESULT_SOURCE_DERIVED,
                component_names=_MISES_COMPONENT_NAMES,
                metadata=metadata,
            ),
            ResultField(
                name=principal_field_name,
                position=stress_field.position,
                values=principal_values,
                source_type=RESULT_SOURCE_DERIVED,
                component_names=PRINCIPAL_COMPONENT_NAMES,
                metadata=metadata,
            ),
        )

    def _build_stress_tensor(self, value, component_names: tuple[str, ...]) -> numpy.ndarray:
        vector = extract_component_vector(value, component_names)
        component_map = {
            component_names[index]: float(vector[index])
            for index in range(len(component_names))
        }
        s11 = component_map.get("S11", 0.0)
        s22 = component_map.get("S22", 0.0)
        s33 = component_map.get("S33", 0.0)
        s12 = component_map.get("S12", 0.0)
        s23 = component_map.get("S23", 0.0)
        s13 = component_map.get("S13", 0.0)
        return numpy.asarray(
            (
                (s11, s12, s13),
                (s12, s22, s23),
                (s13, s23, s33),
            ),
            dtype=float,
        )

    def _compute_von_mises(self, tensor: numpy.ndarray) -> float:
        s11 = float(tensor[0, 0])
        s22 = float(tensor[1, 1])
        s33 = float(tensor[2, 2])
        s12 = float(tensor[0, 1])
        s23 = float(tensor[1, 2])
        s13 = float(tensor[0, 2])
        return numpy.sqrt(
            0.5 * ((s11 - s22) ** 2 + (s22 - s33) ** 2 + (s33 - s11) ** 2)
            + 3.0 * (s12**2 + s23**2 + s13**2)
        )
