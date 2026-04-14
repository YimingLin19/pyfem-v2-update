"""网格基础记录对象。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class NodeRecord:
    """定义模型中的节点记录。"""

    name: str
    coordinates: tuple[float, ...]

    def spatial_dimension(self) -> int:
        """返回节点的空间维度。"""

        return len(self.coordinates)

    def to_dict(self) -> dict[str, Any]:
        """将节点记录序列化为字典。"""

        return {"name": self.name, "coordinates": list(self.coordinates)}


@dataclass(slots=True)
class ElementRecord:
    """定义模型中的单元记录。"""

    name: str
    type_key: str
    node_names: tuple[str, ...]
    section_name: str | None = None
    material_name: str | None = None
    region_name: str | None = None
    orientation_name: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def element_type(self) -> str:
        """返回兼容旧接口的单元类型名称。"""

        return self.type_key

    def connectivity_size(self) -> int:
        """返回单元连接节点数量。"""

        return len(self.node_names)

    def to_dict(self) -> dict[str, Any]:
        """将单元记录序列化为字典。"""

        return {
            "name": self.name,
            "type_key": self.type_key,
            "node_names": list(self.node_names),
            "section_name": self.section_name,
            "material_name": self.material_name,
            "region_name": self.region_name,
            "orientation_name": self.orientation_name,
            "properties": dict(self.properties),
        }
