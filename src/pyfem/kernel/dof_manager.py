"""全局自由度管理器。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from pyfem.foundation.errors import CompilationError
from pyfem.foundation.types import DofLocation, NodeLocation


@dataclass(slots=True, frozen=True)
class DofDescriptor:
    """描述一个自由度的位置与全局编号。"""

    location: DofLocation
    index: int


class DofManager:
    """负责全局自由度的注册、编号与查询。"""

    def __init__(self) -> None:
        """初始化空的自由度管理器。"""

        self._index_by_location: dict[DofLocation, int] = {}
        self._locations_by_index: list[DofLocation] = []
        self._dof_names_by_owner: dict[tuple[str, str, str], list[str]] = {}
        self._is_finalized = False

    def register_dof(self, location: DofLocation) -> int:
        """注册单个自由度并返回其全局编号。"""

        self._ensure_mutable()
        if location in self._index_by_location:
            return self._index_by_location[location]

        index = len(self._locations_by_index)
        self._index_by_location[location] = index
        self._locations_by_index.append(location)
        return index

    def register_node_dofs(self, node_location: NodeLocation, dof_names: Iterable[str]) -> tuple[int, ...]:
        """为一个节点批量注册自由度并返回编号序列。"""

        return self.register_owned_dofs(
            scope_name=node_location.scope_name,
            owner_kind="node",
            owner_name=node_location.node_name,
            dof_names=dof_names,
        )

    def register_owned_dofs(
        self,
        scope_name: str,
        owner_kind: str,
        owner_name: str,
        dof_names: Iterable[str],
    ) -> tuple[int, ...]:
        """为任意自由度拥有者批量注册自由度。"""

        self._ensure_mutable()
        validated_scope_name, validated_owner_kind, validated_owner_name, validated_dof_names = self._validate_registration_request(
            scope_name=scope_name,
            owner_kind=owner_kind,
            owner_name=owner_name,
            dof_names=dof_names,
        )
        owner_key = (validated_scope_name, validated_owner_kind, validated_owner_name)
        owner_dof_names = self._dof_names_by_owner.setdefault(owner_key, [])
        indices: list[int] = []
        for dof_name in validated_dof_names:
            if dof_name not in owner_dof_names:
                owner_dof_names.append(dof_name)
            location = (
                DofLocation.node(scope_name=validated_scope_name, node_name=validated_owner_name, dof_name=dof_name)
                if validated_owner_kind == "node"
                else DofLocation(
                    scope_name=validated_scope_name,
                    node_name=None,
                    dof_name=dof_name,
                    owner_kind=validated_owner_kind,
                    owner_name=validated_owner_name,
                )
            )
            indices.append(self.register_dof(location))
        return tuple(indices)

    def register_extra_dofs(self, scope_name: str, owner_name: str, dof_names: Iterable[str]) -> tuple[int, ...]:
        """为兼容旧接口的额外自由度拥有者注册辅助自由度。"""

        return self.register_owned_dofs(
            scope_name=scope_name,
            owner_kind="auxiliary",
            owner_name=owner_name,
            dof_names=dof_names,
        )

    def finalize(self) -> None:
        """冻结当前自由度布局，禁止后续继续注册。"""

        self._is_finalized = True

    def get_global_id(self, location: DofLocation) -> int:
        """查询单个自由度的全局编号。"""

        try:
            return self._index_by_location[location]
        except KeyError as error:
            raise CompilationError(f"自由度 {location.qualified_name} 尚未注册。") from error

    def get_node_dof_ids(
        self,
        node_location: NodeLocation,
        dof_names: Iterable[str] | None = None,
    ) -> tuple[int, ...]:
        """查询一个节点上一组自由度的全局编号。"""

        return self.get_owner_dof_ids(
            scope_name=node_location.scope_name,
            owner_kind="node",
            owner_name=node_location.node_name,
            dof_names=dof_names,
        )

    def get_owner_dof_ids(
        self,
        *,
        scope_name: str,
        owner_kind: str,
        owner_name: str,
        dof_names: Iterable[str] | None = None,
    ) -> tuple[int, ...]:
        """查询任意自由度拥有者上一组自由度的全局编号。"""

        owner_key = (scope_name, owner_kind, owner_name)
        if dof_names is None:
            try:
                query_dof_names = tuple(self._dof_names_by_owner[owner_key])
            except KeyError as error:
                raise CompilationError(f"拥有者 {scope_name}.{owner_kind}:{owner_name} 尚未注册自由度。") from error
        else:
            query_dof_names = tuple(dof_names)

        return tuple(
            self.get_global_id(
                DofLocation.node(scope_name=scope_name, node_name=owner_name, dof_name=dof_name)
                if owner_kind == "node"
                else DofLocation(
                    scope_name=scope_name,
                    node_name=None,
                    dof_name=dof_name,
                    owner_kind=owner_kind,
                    owner_name=owner_name,
                )
            )
            for dof_name in query_dof_names
        )

    def resolve_dof(self, location: DofLocation) -> int:
        """返回兼容旧接口的自由度查询结果。"""

        return self.get_global_id(location)

    def resolve_node_dofs(self, node_location: NodeLocation, dof_names: Iterable[str]) -> tuple[int, ...]:
        """返回兼容旧接口的节点自由度查询结果。"""

        return self.get_node_dof_ids(node_location, dof_names)

    def iter_descriptors(self) -> tuple[DofDescriptor, ...]:
        """按全局编号顺序返回所有自由度描述。"""

        return tuple(
            DofDescriptor(location=location, index=index) for index, location in enumerate(self._locations_by_index)
        )

    def num_dofs(self) -> int:
        """返回当前已分配的自由度总数。"""

        return len(self._locations_by_index)

    def count(self) -> int:
        """返回兼容旧接口的自由度总数。"""

        return self.num_dofs()

    def _validate_registration_request(
        self,
        *,
        scope_name: str,
        owner_kind: str,
        owner_name: str,
        dof_names: Iterable[str],
    ) -> tuple[str, str, str, tuple[str, ...]]:
        """校验自由度注册请求的边界条件。"""

        validated_scope_name = self._validate_non_empty_text(scope_name, "scope_name")
        validated_owner_kind = self._validate_non_empty_text(owner_kind, "owner_kind")
        validated_owner_name = self._validate_non_empty_text(owner_name, "owner_name")
        validated_dof_names = tuple(dof_names)
        if not validated_dof_names:
            raise CompilationError("注册自由度时至少需要提供一个 dof_name。")
        for dof_name in validated_dof_names:
            self._validate_non_empty_text(dof_name, "dof_name")
        return validated_scope_name, validated_owner_kind, validated_owner_name, validated_dof_names

    def _validate_non_empty_text(self, value: str, label: str) -> str:
        """校验注册参数中的文本字段非空。"""

        if not value or not value.strip():
            raise CompilationError(f"注册自由度时 {label} 不能为空。")
        return value

    def _ensure_mutable(self) -> None:
        if self._is_finalized:
            raise CompilationError("自由度管理器已冻结，不能继续注册自由度。")
