"""网格容器与集合定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pyfem.foundation.errors import ModelValidationError
from pyfem.mesh.records import ElementRecord, NodeRecord


@dataclass(slots=True, frozen=True)
class SurfaceFacet:
    """定义一个表面上的局部面片。"""

    element_name: str
    local_face: str

    def to_dict(self) -> dict[str, Any]:
        """将面片定义序列化为字典。"""

        return {"element_name": self.element_name, "local_face": self.local_face}


@dataclass(slots=True)
class Surface:
    """定义网格表面。"""

    name: str
    facets: tuple[SurfaceFacet, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """将表面定义序列化为字典。"""

        return {"name": self.name, "facets": [facet.to_dict() for facet in self.facets]}


@dataclass(slots=True)
class Orientation:
    """定义单元局部方向。"""

    name: str
    system: str = "rectangular"
    axis_1: tuple[float, ...] = (1.0, 0.0, 0.0)
    axis_2: tuple[float, ...] = (0.0, 1.0, 0.0)
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将方向定义序列化为字典。"""

        return {
            "name": self.name,
            "system": self.system,
            "axis_1": list(self.axis_1),
            "axis_2": list(self.axis_2),
            "parameters": dict(self.parameters),
        }

    def validate(self, spatial_dimension: int | None = None) -> None:
        """校验方向定义的轴向量配置。"""

        axis_1 = tuple(float(value) for value in self.axis_1)
        axis_2 = tuple(float(value) for value in self.axis_2)
        if len(axis_1) != len(axis_2):
            raise ModelValidationError(f"方向 {self.name} 的 axis_1 与 axis_2 维度必须一致。")
        if len(axis_1) not in {2, 3}:
            raise ModelValidationError(f"方向 {self.name} 当前仅支持二维或三维轴向量。")
        if spatial_dimension is not None and spatial_dimension > 0:
            allowed_dimensions = {spatial_dimension}
            if spatial_dimension == 2:
                allowed_dimensions.add(3)
            if len(axis_1) not in allowed_dimensions:
                raise ModelValidationError(
                    f"方向 {self.name} 的轴向量维度 {len(axis_1)} 与部件维度 {spatial_dimension} 不兼容。"
                )

        norm_1 = sum(value * value for value in axis_1) ** 0.5
        norm_2 = sum(value * value for value in axis_2) ** 0.5
        if norm_1 <= 0.0 or norm_2 <= 0.0:
            raise ModelValidationError(f"方向 {self.name} 的轴向量长度必须大于零。")
        dot_value = sum(value_1 * value_2 for value_1, value_2 in zip(axis_1, axis_2))
        if abs(dot_value) > 1.0e-9 * norm_1 * norm_2:
            raise ModelValidationError(f"方向 {self.name} 的 axis_1 与 axis_2 必须线性独立。")


@dataclass(slots=True)
class Mesh:
    """定义部件级网格与集合容器。"""

    nodes: dict[str, NodeRecord] = field(default_factory=dict)
    elements: dict[str, ElementRecord] = field(default_factory=dict)
    node_sets: dict[str, tuple[str, ...]] = field(default_factory=dict)
    element_sets: dict[str, tuple[str, ...]] = field(default_factory=dict)
    surfaces: dict[str, Surface] = field(default_factory=dict)
    orientations: dict[str, Orientation] = field(default_factory=dict)

    def add_node(self, node: NodeRecord) -> None:
        """向网格中添加节点定义。"""

        if node.name in self.nodes:
            raise ModelValidationError(f"网格中已存在节点 {node.name}。")
        self.nodes[node.name] = node

    def add_element(self, element: ElementRecord) -> None:
        """向网格中添加单元定义。"""

        if element.name in self.elements:
            raise ModelValidationError(f"网格中已存在单元 {element.name}。")
        self.elements[element.name] = element

    def add_node_set(self, set_name: str, node_names: tuple[str, ...]) -> None:
        """向网格中添加节点集合。"""

        if set_name in self.node_sets:
            raise ModelValidationError(f"网格中已存在节点集合 {set_name}。")
        self.node_sets[set_name] = tuple(node_names)

    def add_element_set(self, set_name: str, element_names: tuple[str, ...]) -> None:
        """向网格中添加单元集合。"""

        if set_name in self.element_sets:
            raise ModelValidationError(f"网格中已存在单元集合 {set_name}。")
        self.element_sets[set_name] = tuple(element_names)

    def add_surface(self, surface: Surface) -> None:
        """向网格中添加表面定义。"""

        if surface.name in self.surfaces:
            raise ModelValidationError(f"网格中已存在表面 {surface.name}。")
        self.surfaces[surface.name] = surface

    def add_orientation(self, orientation: Orientation) -> None:
        """向网格中添加方向定义。"""

        if orientation.name in self.orientations:
            raise ModelValidationError(f"网格中已存在方向 {orientation.name}。")
        self.orientations[orientation.name] = orientation

    def get_node(self, node_name: str) -> NodeRecord:
        """按名称获取节点记录。"""

        try:
            return self.nodes[node_name]
        except KeyError as error:
            raise ModelValidationError(f"网格中不存在节点 {node_name}。") from error

    def get_element(self, element_name: str) -> ElementRecord:
        """按名称获取单元记录。"""

        try:
            return self.elements[element_name]
        except KeyError as error:
            raise ModelValidationError(f"网格中不存在单元 {element_name}。") from error

    def has_node_set(self, set_name: str) -> bool:
        """判断网格中是否存在指定节点集合。"""

        return set_name in self.node_sets

    def has_element_set(self, set_name: str) -> bool:
        """判断网格中是否存在指定单元集合。"""

        return set_name in self.element_sets

    def has_surface(self, surface_name: str) -> bool:
        """判断网格中是否存在指定表面。"""

        return surface_name in self.surfaces

    def spatial_dimension(self) -> int:
        """返回网格节点的空间维度。"""

        if not self.nodes:
            return 0
        first_node = next(iter(self.nodes.values()))
        return first_node.spatial_dimension()

    def validate(self) -> None:
        """校验网格中的连接与集合引用关系。"""

        spatial_dimension = self.spatial_dimension()
        for node in self.nodes.values():
            if node.spatial_dimension() != spatial_dimension:
                raise ModelValidationError("同一网格中的节点空间维度必须一致。")

        for orientation in self.orientations.values():
            orientation.validate(spatial_dimension=spatial_dimension)

        for element in self.elements.values():
            missing_nodes = [node_name for node_name in element.node_names if node_name not in self.nodes]
            if missing_nodes:
                joined = ", ".join(missing_nodes)
                raise ModelValidationError(f"单元 {element.name} 引用了不存在的节点: {joined}。")
            if element.orientation_name is not None and element.orientation_name not in self.orientations:
                raise ModelValidationError(
                    f"单元 {element.name} 引用了不存在的方向 {element.orientation_name}。"
                )

        for set_name, node_names in self.node_sets.items():
            missing_nodes = [node_name for node_name in node_names if node_name not in self.nodes]
            if missing_nodes:
                joined = ", ".join(missing_nodes)
                raise ModelValidationError(f"节点集合 {set_name} 引用了不存在的节点: {joined}。")

        for set_name, element_names in self.element_sets.items():
            missing_elements = [element_name for element_name in element_names if element_name not in self.elements]
            if missing_elements:
                joined = ", ".join(missing_elements)
                raise ModelValidationError(f"单元集合 {set_name} 引用了不存在的单元: {joined}。")

        for surface in self.surfaces.values():
            missing_elements = [facet.element_name for facet in surface.facets if facet.element_name not in self.elements]
            if missing_elements:
                joined = ", ".join(missing_elements)
                raise ModelValidationError(f"表面 {surface.name} 引用了不存在的单元: {joined}。")

    def to_dict(self) -> dict[str, Any]:
        """将网格定义序列化为字典。"""

        return {
            "nodes": {name: node.to_dict() for name, node in self.nodes.items()},
            "elements": {name: element.to_dict() for name, element in self.elements.items()},
            "node_sets": {name: list(item) for name, item in self.node_sets.items()},
            "element_sets": {name: list(item) for name, item in self.element_sets.items()},
            "surfaces": {name: surface.to_dict() for name, surface in self.surfaces.items()},
            "orientations": {name: orientation.to_dict() for name, orientation in self.orientations.items()},
        }
