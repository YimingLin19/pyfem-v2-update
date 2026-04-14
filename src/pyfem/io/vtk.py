"""基础 VTK 导出器。"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from numbers import Real
from pathlib import Path
from typing import Any

from pyfem.foundation.errors import PyFEMError
from pyfem.io.results import (
    FIELD_KEY_MODE_SHAPE,
    FIELD_KEY_U,
    POSITION_ELEMENT_CENTROID,
    POSITION_ELEMENT_NODAL,
    POSITION_INTEGRATION_POINT,
    POSITION_NODE,
    POSITION_NODE_AVERAGED,
    ResultField,
    ResultFrame,
    ResultsReader,
)
from pyfem.modeldb import ModelDB
from pyfem.post.common import (
    FIELD_METADATA_KEY_AVERAGING_GROUPS,
    FIELD_METADATA_KEY_BASE_TARGET_KEYS,
    FIELD_METADATA_KEY_OWNER_ELEMENT_KEYS,
)


@dataclass(slots=True, frozen=True)
class _VtkArray:
    """定义一个待写出的 VTK 数组。"""

    name: str
    kind: str
    values: tuple[Any, ...]


@dataclass(slots=True)
class VtkExporter:
    """将模型与结果帧导出为 VTK legacy 文本。"""

    def export(
        self,
        model: ModelDB,
        results_reader: ResultsReader,
        path: str | Path,
        *,
        step_name: str | None = None,
        frame_id: int | None = None,
    ) -> Path:
        """导出指定结果帧到 VTK 文件。"""

        _resolved_step_name, frame = self._select_frame(results_reader, step_name=step_name, frame_id=frame_id)
        points, point_keys, cells, cell_keys, cell_names = self._collect_mesh(model)
        point_arrays, cell_arrays = self._collect_field_arrays(frame.fields, point_keys=tuple(point_keys), cell_keys=tuple(cell_keys))

        lines: list[str] = [
            "# vtk DataFile Version 3.0",
            "pyFEM v2 results export",
            "ASCII",
            "DATASET UNSTRUCTURED_GRID",
            f"POINTS {len(points)} float",
        ]
        lines.extend(f"{x:.12g} {y:.12g} {z:.12g}" for x, y, z in points)

        cell_size = sum(len(cell) + 1 for cell in cells)
        lines.append(f"CELLS {len(cells)} {cell_size}")
        for cell in cells:
            connectivity = " ".join(str(index) for index in cell)
            lines.append(f"{len(cell)} {connectivity}")

        lines.append(f"CELL_TYPES {len(cells)}")
        for cell_name in cell_names:
            lines.append(str(self._vtk_cell_type(cell_name)))

        if point_arrays:
            lines.append(f"POINT_DATA {len(points)}")
            lines.extend(self._emit_vtk_arrays(point_arrays))
        if cell_arrays:
            lines.append(f"CELL_DATA {len(cells)}")
            lines.extend(self._emit_vtk_arrays(cell_arrays))

        target_path = Path(path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return target_path

    def _select_frame(
        self,
        results_reader: ResultsReader,
        step_name: str | None,
        frame_id: int | None,
    ) -> tuple[str, ResultFrame]:
        resolved_step_name = step_name
        if resolved_step_name is None:
            step_names = results_reader.list_steps()
            if not step_names:
                raise ValueError("当前结果数据库中没有可导出的结果步骤。")
            resolved_step_name = step_names[-1]

        if frame_id is None:
            step = results_reader.read_step(resolved_step_name)
            if not step.frames:
                raise ValueError(f"步骤 {resolved_step_name} 中没有可导出的结果帧。")
            return resolved_step_name, step.frames[-1]
        return resolved_step_name, results_reader.read_frame(resolved_step_name, frame_id)

    def _collect_mesh(
        self,
        model: ModelDB,
    ) -> tuple[list[tuple[float, float, float]], list[str], list[tuple[int, ...]], list[str], list[str]]:
        points: list[tuple[float, float, float]] = []
        point_keys: list[str] = []
        point_indices: dict[str, int] = {}
        cells: list[tuple[int, ...]] = []
        cell_keys: list[str] = []
        cell_names: list[str] = []

        for scope in model.iter_compilation_scopes():
            for node in scope.iter_node_geometry_records():
                qualified_name = scope.qualify_node_name(node.name)
                point_indices[qualified_name] = len(points)
                coordinates = tuple(node.coordinates) + (0.0,) * (3 - len(node.coordinates))
                points.append((float(coordinates[0]), float(coordinates[1]), float(coordinates[2])))
                point_keys.append(qualified_name)
            for element in scope.part.elements.values():
                cells.append(tuple(point_indices[scope.qualify_node_name(node_name)] for node_name in element.node_names))
                cell_keys.append(scope.qualify_element_name(element.name))
                cell_names.append(element.type_key)
        return points, point_keys, cells, cell_keys, cell_names

    def _collect_field_arrays(
        self,
        fields: tuple[ResultField, ...],
        *,
        point_keys: tuple[str, ...],
        cell_keys: tuple[str, ...],
    ) -> tuple[tuple[_VtkArray, ...], tuple[_VtkArray, ...]]:
        point_arrays: list[_VtkArray] = []
        cell_arrays: list[_VtkArray] = []
        for field in fields:
            if field.position == POSITION_NODE:
                point_arrays.extend(self._build_node_arrays(field, point_keys=point_keys))
                continue
            if field.position == POSITION_NODE_AVERAGED:
                point_arrays.extend(self._build_averaged_node_arrays(field, point_keys=point_keys))
                continue
            if field.position == POSITION_ELEMENT_CENTROID:
                cell_arrays.extend(self._build_cell_arrays(field, cell_keys=cell_keys))
                continue
            if field.position in {POSITION_INTEGRATION_POINT, POSITION_ELEMENT_NODAL}:
                cell_arrays.extend(self._build_cell_slot_arrays(field, cell_keys=cell_keys))
                continue
        return tuple(point_arrays), tuple(cell_arrays)

    def _build_node_arrays(self, field: ResultField, *, point_keys: tuple[str, ...]) -> tuple[_VtkArray, ...]:
        prefix = _source_prefix(field.source_type)
        if self._is_vector_field(field):
            vectors = []
            for point_key in point_keys:
                vectors.append(self._extract_vector(field.values.get(point_key)))
            return (_VtkArray(name=f"{prefix}__{field.name}", kind="vector", values=tuple(vectors)),)

        component_names = self._resolve_numeric_component_names(field)
        arrays: list[_VtkArray] = []
        for component_name in component_names:
            values = tuple(
                self._extract_scalar_component(field.values.get(point_key), component_name, field.component_names)
                for point_key in point_keys
            )
            arrays.append(
                _VtkArray(
                    name=self._build_array_name(prefix, field.name, component_name),
                    kind="scalar",
                    values=values,
                )
            )
        return tuple(arrays)

    def _build_averaged_node_arrays(self, field: ResultField, *, point_keys: tuple[str, ...]) -> tuple[_VtkArray, ...]:
        prefix = _source_prefix(field.source_type)
        component_names = self._resolve_numeric_component_names(field)
        grouped_values = self._group_averaged_targets(field)
        arrays: list[_VtkArray] = []
        for group_label, group_mapping in grouped_values.items():
            for component_name in component_names:
                values = tuple(
                    self._extract_scalar_component(group_mapping.get(point_key), component_name, field.component_names)
                    for point_key in point_keys
                )
                arrays.append(
                    _VtkArray(
                        name=self._build_array_name(prefix, field.name, group_label, component_name),
                        kind="scalar",
                        values=values,
                    )
                )
        return tuple(arrays)

    def _build_cell_arrays(self, field: ResultField, *, cell_keys: tuple[str, ...]) -> tuple[_VtkArray, ...]:
        prefix = _source_prefix(field.source_type)
        component_names = self._resolve_numeric_component_names(field)
        arrays: list[_VtkArray] = []
        for component_name in component_names:
            values = tuple(
                self._extract_scalar_component(field.values.get(cell_key), component_name, field.component_names)
                for cell_key in cell_keys
            )
            arrays.append(
                _VtkArray(
                    name=self._build_array_name(prefix, field.name, component_name),
                    kind="scalar",
                    values=values,
                )
            )
        return tuple(arrays)

    def _build_cell_slot_arrays(self, field: ResultField, *, cell_keys: tuple[str, ...]) -> tuple[_VtkArray, ...]:
        prefix = _source_prefix(field.source_type)
        component_names = self._resolve_numeric_component_names(field)
        slot_values: dict[str, dict[str, Any]] = defaultdict(dict)
        for target_key, value in field.values.items():
            owner_element_key = self._resolve_owner_element_key(field, str(target_key))
            slot_label = self._resolve_slot_label(owner_element_key, str(target_key))
            slot_values[slot_label][owner_element_key] = value

        arrays: list[_VtkArray] = []
        for slot_label in sorted(slot_values.keys()):
            owner_value_map = slot_values[slot_label]
            for component_name in component_names:
                values = tuple(
                    self._extract_scalar_component(owner_value_map.get(cell_key), component_name, field.component_names)
                    for cell_key in cell_keys
                )
                arrays.append(
                    _VtkArray(
                        name=self._build_array_name(prefix, field.name, slot_label, component_name),
                        kind="scalar",
                        values=values,
                    )
                )
        return tuple(arrays)

    def _group_averaged_targets(self, field: ResultField) -> dict[str, dict[str, Any]]:
        base_target_keys = {
            str(target_key): str(base_target_key)
            for target_key, base_target_key in field.metadata.get(FIELD_METADATA_KEY_BASE_TARGET_KEYS, {}).items()
        }
        averaging_groups = {
            str(target_key): str(group_key)
            for target_key, group_key in field.metadata.get(FIELD_METADATA_KEY_AVERAGING_GROUPS, {}).items()
        }
        duplicate_counts = Counter(base_target_keys.get(target_key, target_key) for target_key in field.values.keys())
        split_by_group = any(count > 1 for count in duplicate_counts.values())
        grouped: dict[str, dict[str, Any]] = defaultdict(dict)
        for target_key, value in field.values.items():
            base_target_key = base_target_keys.get(str(target_key), str(target_key))
            group_label = averaging_groups.get(str(target_key), "") if split_by_group else ""
            grouped[group_label][base_target_key] = value
        return grouped

    def _emit_vtk_arrays(self, arrays: tuple[_VtkArray, ...]) -> list[str]:
        lines: list[str] = []
        for array in arrays:
            if array.kind == "vector":
                lines.append(f"VECTORS {array.name} float")
                for vector in array.values:
                    x, y, z = self._extract_vector(vector)
                    lines.append(f"{self._format_scalar(x)} {self._format_scalar(y)} {self._format_scalar(z)}")
                continue
            lines.append(f"SCALARS {array.name} float 1")
            lines.append("LOOKUP_TABLE default")
            for value in array.values:
                lines.append(self._format_scalar(value))
        return lines

    def _resolve_component_names(self, field: ResultField) -> tuple[str, ...]:
        return field.component_names

    def _resolve_numeric_component_names(self, field: ResultField) -> tuple[str | None, ...]:
        component_names = self._resolve_component_names(field)
        if component_names:
            return tuple(
                component_name
                for component_name in component_names
                if self._component_is_numeric(field, component_name)
            )
        if self._component_is_numeric(field, None):
            return (None,)
        return ()

    def _component_is_numeric(self, field: ResultField, component_name: str | None) -> bool:
        is_scalar_component = component_name in {None, "", "VALUE"}
        for value in field.values.values():
            if value is None:
                continue
            if isinstance(value, dict):
                component_value = None
                if not is_scalar_component:
                    component_value = value.get(component_name)
                elif len(value) == 1:
                    component_value = next(iter(value.values()))
                if self._is_numeric_scalar(component_value):
                    return True
                continue
            if isinstance(value, (tuple, list)):
                component_value = self._extract_sequence_component(value, component_name, field.component_names)
                if self._is_numeric_scalar(component_value):
                    return True
                continue
            if is_scalar_component and self._is_numeric_scalar(value):
                return True
        return False

    def _is_numeric_scalar(self, value: Any) -> bool:
        return isinstance(value, Real) and not isinstance(value, bool | complex)

    def _resolve_owner_element_key(self, field: ResultField, target_key: str) -> str:
        owner_element_keys = field.metadata.get(FIELD_METADATA_KEY_OWNER_ELEMENT_KEYS, {})
        owner_element_key = owner_element_keys.get(target_key)
        if owner_element_key is not None:
            return str(owner_element_key)
        if "." not in target_key:
            return target_key
        return target_key.rsplit(".", maxsplit=1)[0]

    def _resolve_slot_label(self, owner_element_key: str, target_key: str) -> str:
        prefix = f"{owner_element_key}."
        if target_key.startswith(prefix):
            return target_key[len(prefix) :]
        return target_key.rsplit(".", maxsplit=1)[-1]

    def _extract_vector(self, value: Any) -> tuple[float, float, float]:
        if isinstance(value, dict):
            return (
                float(value.get("UX", float("nan"))),
                float(value.get("UY", float("nan"))),
                float(value.get("UZ", 0.0 if "UZ" not in value else value.get("UZ", float("nan")))),
            )
        if isinstance(value, (tuple, list)):
            padded = tuple(float(item) for item in value) + (0.0, 0.0, 0.0)
            return padded[0], padded[1], padded[2]
        if isinstance(value, (int, float)):
            return float(value), 0.0, 0.0
        return float("nan"), float("nan"), float("nan")

    def _extract_scalar_component(
        self,
        value: Any,
        component_name: str | None,
        component_names: tuple[str, ...] = (),
    ) -> float:
        is_scalar_component = component_name in {None, "", "VALUE"}
        if value is None:
            return float("nan")
        if isinstance(value, dict):
            component_value = None
            if not is_scalar_component:
                component_value = value.get(component_name)
            elif len(value) == 1:
                component_value = next(iter(value.values()))
            return float(component_value) if component_value is not None else float("nan")
        if isinstance(value, (tuple, list)):
            component_value = self._extract_sequence_component(value, component_name, component_names)
            return float(component_value) if component_value is not None else float("nan")
        if isinstance(value, (int, float)):
            return float(value) if is_scalar_component else float("nan")
        return float("nan")

    def _build_array_name(self, prefix: str, field_name: str, *parts: str | None) -> str:
        tokens = [prefix, field_name, *(part for part in parts if part)]
        return "__".join(_sanitize_label(token) for token in tokens)

    def _extract_sequence_component(
        self,
        value: tuple[Any, ...] | list[Any],
        component_name: str | None,
        component_names: tuple[str, ...],
    ) -> Any | None:
        if component_names:
            if component_name in {None, "", "VALUE"}:
                if len(component_names) != 1:
                    return None
                component_index = 0
            else:
                try:
                    component_index = component_names.index(str(component_name))
                except ValueError:
                    return None
            if component_index >= len(value):
                return None
            return value[component_index]
        if component_name not in {None, "", "VALUE"} or len(value) != 1:
            return None
        return value[0]

    def _format_scalar(self, value: Any) -> str:
        try:
            scalar = float(value)
        except (TypeError, ValueError):
            scalar = float("nan")
        return f"{scalar:.12g}"

    def _is_vector_field(self, field: ResultField) -> bool:
        return field.name in {FIELD_KEY_U, FIELD_KEY_MODE_SHAPE} and field.position == POSITION_NODE

    def _vtk_cell_type(self, type_key: str) -> int:
        mapping = {"B21": 3, "CPS4": 9, "C3D8": 12}
        try:
            return mapping[type_key]
        except KeyError as error:
            raise ValueError(f"当前 VTK 导出暂不支持单元类型 {type_key}。") from error


def _source_prefix(source_type: str) -> str:
    mapping = {
        "raw": "RAW",
        "recovered": "RECOVERED",
        "averaged": "AVERAGED",
        "derived": "DERIVED",
    }
    return mapping.get(str(source_type).strip().lower(), _sanitize_label(source_type))


def _sanitize_label(label: str) -> str:
    normalized = []
    for character in str(label):
        if character.isalnum():
            normalized.append(character.upper())
        else:
            normalized.append("_")
    sanitized = "".join(normalized).strip("_")
    return sanitized or "UNNAMED"
