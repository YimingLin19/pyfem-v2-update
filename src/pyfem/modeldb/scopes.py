"""编译作用域与实例几何视图。"""

from __future__ import annotations

from dataclasses import dataclass, field

from pyfem.mesh import Orientation, Part, RigidTransform, Surface
from pyfem.mesh.records import NodeRecord


@dataclass(slots=True, frozen=True)
class CompilationScope:
    """描述一个 canonical compilation scope。"""

    scope_name: str
    part_name: str
    part: Part
    transform: RigidTransform
    instance_name: str | None = None
    node_sets: dict[str, tuple[str, ...]] = field(default_factory=dict)
    element_sets: dict[str, tuple[str, ...]] = field(default_factory=dict)
    surfaces: dict[str, Surface] = field(default_factory=dict)

    def qualify_node_name(self, node_name: str) -> str:
        """返回作用域内节点的 canonical 名称。"""

        return f"{self.scope_name}.{node_name}"

    def qualify_element_name(self, element_name: str) -> str:
        """返回作用域内单元的 canonical 名称。"""

        return f"{self.scope_name}.{element_name}"

    def get_node_geometry_record(self, node_name: str) -> NodeRecord:
        """返回当前作用域下经过实例变换后的节点记录。"""

        local_record = self.part.get_node(node_name)
        return NodeRecord(name=local_record.name, coordinates=self.transform.apply(local_record.coordinates))

    def iter_node_geometry_records(self) -> tuple[NodeRecord, ...]:
        """返回当前作用域下全部经过实例变换的节点记录。"""

        return tuple(self.get_node_geometry_record(node_name) for node_name in self.part.nodes)

    def resolve_node_names(self, target_type: str, target_name: str | None = None) -> tuple[str, ...]:
        """在当前作用域内解析节点目标。"""

        if target_type == "model":
            return tuple(self.part.nodes.keys())
        if target_type == "node":
            if target_name is None:
                return ()
            return (target_name,) if target_name in self.part.nodes else ()
        if target_type == "node_set":
            if target_name is None:
                return ()
            if target_name in self.node_sets:
                return tuple(self.node_sets[target_name])
            return tuple(self.part.mesh.node_sets.get(target_name, ()))
        return ()

    def resolve_element_names(self, target_type: str, target_name: str | None = None) -> tuple[str, ...]:
        """在当前作用域内解析单元目标。"""

        if target_type == "model":
            return tuple(self.part.elements.keys())
        if target_type == "element":
            if target_name is None:
                return ()
            return (target_name,) if target_name in self.part.elements else ()
        if target_type == "element_set":
            if target_name is None:
                return ()
            if target_name in self.element_sets:
                return tuple(self.element_sets[target_name])
            return tuple(self.part.mesh.element_sets.get(target_name, ()))
        return ()

    def get_surface(self, surface_name: str) -> Surface | None:
        """返回当前作用域内的局部表面定义。"""

        if surface_name in self.surfaces:
            return self.surfaces[surface_name]
        return self.part.mesh.surfaces.get(surface_name)

    def get_orientation(self, orientation_name: str) -> Orientation | None:
        """返回当前作用域内经过实例旋转映射的方向定义。"""

        local_orientation = self.part.mesh.orientations.get(orientation_name)
        if local_orientation is None:
            return None

        axis_dimension = len(local_orientation.axis_1)
        part_dimension = self.part.spatial_dimension()
        if axis_dimension != part_dimension or part_dimension not in {2, 3}:
            return Orientation(
                name=local_orientation.name,
                system=local_orientation.system,
                axis_1=tuple(float(value) for value in local_orientation.axis_1),
                axis_2=tuple(float(value) for value in local_orientation.axis_2),
                parameters=dict(local_orientation.parameters),
            )

        rotation, _ = self.transform.resolve_components(part_dimension)

        def rotate_axis(axis: tuple[float, ...]) -> tuple[float, ...]:
            return tuple(
                sum(rotation[row_index][column_index] * float(axis[column_index]) for column_index in range(part_dimension))
                for row_index in range(part_dimension)
            )

        return Orientation(
            name=local_orientation.name,
            system=local_orientation.system,
            axis_1=rotate_axis(local_orientation.axis_1),
            axis_2=rotate_axis(local_orientation.axis_2),
            parameters=dict(local_orientation.parameters),
        )

    def has_element_region(self, region_name: str) -> bool:
        """判断当前作用域内是否存在指定单元区域。"""

        return region_name in self.element_sets or region_name in self.part.mesh.element_sets

    def has_part_element_region(self, region_name: str) -> bool:
        """判断当前作用域对应部件内是否存在指定单元区域。"""

        return region_name in self.part.mesh.element_sets

    def resolve_part_element_region(self, region_name: str) -> tuple[str, ...]:
        """仅按部件本地网格解析单元区域，不受装配 alias 遮蔽影响。"""

        return tuple(self.part.mesh.element_sets.get(region_name, ()))
