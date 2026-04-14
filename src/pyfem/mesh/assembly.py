"""部件与装配定义。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from pyfem.foundation.errors import ModelValidationError
from pyfem.mesh.mesh import Mesh, Orientation, Surface
from pyfem.mesh.records import ElementRecord, NodeRecord


@dataclass(slots=True, frozen=True)
class RigidTransform:
    """定义实例级刚体放置变换。"""

    rotation: tuple[tuple[float, ...], ...] = ()
    translation: tuple[float, ...] = ()

    def resolve_components(self, dimension: int) -> tuple[tuple[tuple[float, ...], ...], tuple[float, ...]]:
        """按给定空间维度解析旋转矩阵与平移向量。"""

        if dimension <= 0:
            if self.rotation or self.translation:
                raise ModelValidationError("空几何对象不能绑定非恒等刚体变换。")
            return (), ()
        if dimension not in {2, 3}:
            raise ModelValidationError(f"刚体变换当前仅支持二维或三维几何，收到维度 {dimension}。")

        resolved_rotation = self._resolve_rotation(dimension)
        resolved_translation = self._resolve_translation(dimension)
        self._validate_rotation_matrix(resolved_rotation)
        return resolved_rotation, resolved_translation

    def apply(self, coordinates: tuple[float, ...]) -> tuple[float, ...]:
        """将刚体变换应用到一个坐标点上。"""

        resolved_rotation, resolved_translation = self.resolve_components(len(coordinates))
        if not resolved_rotation:
            return tuple(float(value) for value in coordinates)
        return tuple(
            sum(resolved_rotation[row_index][column_index] * float(coordinates[column_index]) for column_index in range(len(coordinates)))
            + resolved_translation[row_index]
            for row_index in range(len(coordinates))
        )

    def to_dict(self) -> dict[str, Any]:
        """将刚体变换序列化为字典。"""

        return {
            "rotation": [list(row) for row in self.rotation],
            "translation": list(self.translation),
        }

    def _resolve_rotation(self, dimension: int) -> tuple[tuple[float, ...], ...]:
        if not self.rotation:
            return tuple(
                tuple(1.0 if row_index == column_index else 0.0 for column_index in range(dimension))
                for row_index in range(dimension)
            )
        if len(self.rotation) != dimension:
            raise ModelValidationError(f"刚体变换旋转矩阵维度与几何维度 {dimension} 不一致。")

        resolved_rotation: list[tuple[float, ...]] = []
        for row in self.rotation:
            if len(row) != dimension:
                raise ModelValidationError("刚体变换旋转矩阵必须是方阵。")
            resolved_rotation.append(tuple(float(value) for value in row))
        return tuple(resolved_rotation)

    def _resolve_translation(self, dimension: int) -> tuple[float, ...]:
        if not self.translation:
            return tuple(0.0 for _ in range(dimension))
        if len(self.translation) != dimension:
            raise ModelValidationError(f"刚体变换平移向量维度与几何维度 {dimension} 不一致。")
        return tuple(float(value) for value in self.translation)

    def _validate_rotation_matrix(self, rotation: tuple[tuple[float, ...], ...]) -> None:
        tolerance = 1.0e-9
        dimension = len(rotation)
        for row_index, row in enumerate(rotation):
            norm = math.sqrt(sum(value * value for value in row))
            if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=tolerance):
                raise ModelValidationError(f"刚体变换旋转矩阵第 {row_index + 1} 行不是单位向量。")
            for other_index in range(row_index + 1, dimension):
                dot_value = sum(row[column_index] * rotation[other_index][column_index] for column_index in range(dimension))
                if not math.isclose(dot_value, 0.0, rel_tol=0.0, abs_tol=tolerance):
                    raise ModelValidationError("刚体变换旋转矩阵各行必须两两正交。")

        determinant = (
            rotation[0][0] * rotation[1][1] - rotation[0][1] * rotation[1][0]
            if dimension == 2
            else (
                rotation[0][0] * (rotation[1][1] * rotation[2][2] - rotation[1][2] * rotation[2][1])
                - rotation[0][1] * (rotation[1][0] * rotation[2][2] - rotation[1][2] * rotation[2][0])
                + rotation[0][2] * (rotation[1][0] * rotation[2][1] - rotation[1][1] * rotation[2][0])
            )
        )
        if not math.isclose(determinant, 1.0, rel_tol=0.0, abs_tol=tolerance):
            raise ModelValidationError("刚体变换旋转矩阵必须是正交右手系矩阵。")


@dataclass(slots=True)
class Part:
    """定义一个可复用的部件。"""

    name: str
    mesh: Mesh = field(default_factory=Mesh)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def nodes(self) -> dict[str, NodeRecord]:
        """返回部件中的节点字典。"""

        return self.mesh.nodes

    @property
    def elements(self) -> dict[str, ElementRecord]:
        """返回部件中的单元字典。"""

        return self.mesh.elements

    def add_node(self, node: NodeRecord) -> None:
        """向部件中添加节点定义。"""

        self.mesh.add_node(node)

    def add_element(self, element: ElementRecord) -> None:
        """向部件中添加单元定义。"""

        self.mesh.add_element(element)

    def add_node_set(self, set_name: str, node_names: tuple[str, ...]) -> None:
        """向部件中添加节点集合。"""

        self.mesh.add_node_set(set_name, node_names)

    def add_element_set(self, set_name: str, element_names: tuple[str, ...]) -> None:
        """向部件中添加单元集合。"""

        self.mesh.add_element_set(set_name, element_names)

    def add_surface(self, surface: Surface) -> None:
        """向部件中添加表面定义。"""

        self.mesh.add_surface(surface)

    def add_orientation(self, orientation: Orientation) -> None:
        """向部件中添加方向定义。"""

        self.mesh.add_orientation(orientation)

    def get_node(self, node_name: str) -> NodeRecord:
        """按名称获取节点定义。"""

        return self.mesh.get_node(node_name)

    def get_element(self, element_name: str) -> ElementRecord:
        """按名称获取单元定义。"""

        return self.mesh.get_element(element_name)

    def validate(self) -> None:
        """校验部件内部网格定义。"""

        self.mesh.validate()

    def spatial_dimension(self) -> int:
        """返回部件网格的空间维度。"""

        return self.mesh.spatial_dimension()

    def to_dict(self) -> dict[str, Any]:
        """将部件定义序列化为字典。"""

        return {"name": self.name, "mesh": self.mesh.to_dict(), "metadata": dict(self.metadata)}


@dataclass(slots=True)
class PartInstance:
    """定义装配中的部件实例。"""

    name: str
    part_name: str
    transform: RigidTransform = field(default_factory=RigidTransform)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将部件实例序列化为字典。"""

        return {
            "name": self.name,
            "part_name": self.part_name,
            "transform": self.transform.to_dict(),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class Assembly:
    """定义模型装配关系。"""

    name: str
    instances: dict[str, PartInstance] = field(default_factory=dict)
    instance_node_sets: dict[str, dict[str, tuple[str, ...]]] = field(default_factory=dict)
    instance_element_sets: dict[str, dict[str, tuple[str, ...]]] = field(default_factory=dict)
    instance_surfaces: dict[str, dict[str, Surface]] = field(default_factory=dict)

    def add_instance(self, instance: PartInstance) -> None:
        """向装配中添加部件实例。"""

        if instance.name in self.instances:
            raise ModelValidationError(f"装配 {self.name} 中已存在实例 {instance.name}。")
        self.instances[instance.name] = instance
        self.instance_node_sets[instance.name] = {}
        self.instance_element_sets[instance.name] = {}
        self.instance_surfaces[instance.name] = {}

    def add_instance_node_set(self, instance_name: str, set_name: str, node_names: tuple[str, ...]) -> None:
        """向指定实例注册装配级节点集合别名。"""

        mapping = self._instance_mapping(self.instance_node_sets, instance_name)
        if set_name in mapping:
            raise ModelValidationError(f"装配 {self.name} 的实例 {instance_name} 中已存在节点集合 {set_name}。")
        mapping[set_name] = tuple(node_names)

    def add_instance_element_set(self, instance_name: str, set_name: str, element_names: tuple[str, ...]) -> None:
        """向指定实例注册装配级单元集合别名。"""

        mapping = self._instance_mapping(self.instance_element_sets, instance_name)
        if set_name in mapping:
            raise ModelValidationError(f"装配 {self.name} 的实例 {instance_name} 中已存在单元集合 {set_name}。")
        mapping[set_name] = tuple(element_names)

    def add_instance_surface(self, instance_name: str, surface: Surface) -> None:
        """向指定实例注册装配级表面别名。"""

        mapping = self._instance_mapping(self.instance_surfaces, instance_name)
        if surface.name in mapping:
            raise ModelValidationError(f"装配 {self.name} 的实例 {instance_name} 中已存在表面 {surface.name}。")
        mapping[surface.name] = surface

    def node_sets_for_instance(self, instance_name: str) -> dict[str, tuple[str, ...]]:
        """返回指定实例的装配级节点集合映射。"""

        return dict(self._instance_mapping(self.instance_node_sets, instance_name))

    def element_sets_for_instance(self, instance_name: str) -> dict[str, tuple[str, ...]]:
        """返回指定实例的装配级单元集合映射。"""

        return dict(self._instance_mapping(self.instance_element_sets, instance_name))

    def surfaces_for_instance(self, instance_name: str) -> dict[str, Surface]:
        """返回指定实例的装配级表面映射。"""

        return dict(self._instance_mapping(self.instance_surfaces, instance_name))

    def referenced_part_names(self) -> tuple[str, ...]:
        """返回装配中引用的部件名称集合。"""

        return tuple(instance.part_name for instance in self.instances.values())

    def to_dict(self) -> dict[str, Any]:
        """将装配定义序列化为字典。"""

        return {
            "name": self.name,
            "instances": {name: item.to_dict() for name, item in self.instances.items()},
            "instance_node_sets": {
                instance_name: {set_name: list(node_names) for set_name, node_names in mapping.items()}
                for instance_name, mapping in self.instance_node_sets.items()
            },
            "instance_element_sets": {
                instance_name: {set_name: list(element_names) for set_name, element_names in mapping.items()}
                for instance_name, mapping in self.instance_element_sets.items()
            },
            "instance_surfaces": {
                instance_name: {surface_name: surface.to_dict() for surface_name, surface in mapping.items()}
                for instance_name, mapping in self.instance_surfaces.items()
            },
        }

    def _instance_mapping(self, mapping: dict[str, dict[str, Any]], instance_name: str) -> dict[str, Any]:
        if instance_name not in self.instances:
            raise ModelValidationError(f"装配 {self.name} 中不存在实例 {instance_name}。")
        return mapping[instance_name]


PartDefinition = Part
PartInstanceDefinition = PartInstance
AssemblyDefinition = Assembly
