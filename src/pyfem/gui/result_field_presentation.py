"""GUI 结果字段展示策略。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from pyfem.io import (
    FIELD_KEY_E,
    FIELD_KEY_E_IP,
    FIELD_KEY_E_REC,
    FIELD_KEY_MODE_SHAPE,
    FIELD_KEY_RF,
    FIELD_KEY_S,
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
)
from pyfem.post import ResultFieldOverview

COMMON_VARIANT_KEY = "__common__"
FIELD_KEY_E_AVG = "E_AVG"
FIELD_KEY_S_VM = "S_VM"
FIELD_KEY_S_PRINCIPAL = "S_PRINCIPAL"


@dataclass(slots=True, frozen=True)
class FieldVariant:
    """描述 GUI 中某一物理量族下的一个结果变体。"""

    variant_key: str
    display_name: str
    field_name: str
    source_type: str
    position: str
    component_names: tuple[str, ...]
    target_count: int
    tooltip_text: str
    detail_text: str

    @property
    def is_common(self) -> bool:
        """返回当前变体是否为“常用”别名。"""

        return self.variant_key == COMMON_VARIANT_KEY


@dataclass(slots=True, frozen=True)
class FieldFamily:
    """描述 GUI 中一个按物理意义组织的结果字段族。"""

    family_key: str
    display_name: str
    default_field_name: str
    variants: tuple[FieldVariant, ...]
    tooltip_text: str


@dataclass(slots=True, frozen=True)
class FieldSelectionPresentation:
    """描述当前正式字段在 GUI 中的展示形态。"""

    family_key: str
    family_display_name: str
    variant_key: str
    variant_display_name: str
    field_name: str
    tooltip_text: str
    detail_text: str


@dataclass(slots=True, frozen=True)
class _FieldFamilySpec:
    """定义一个 GUI 物理量族的正式字段映射与默认优先级。"""

    family_key: str
    display_name: str
    formal_field_names: tuple[str, ...]


_FAMILY_SPECS: tuple[_FieldFamilySpec, ...] = (
    _FieldFamilySpec("displacement", "位移", (FIELD_KEY_U,)),
    _FieldFamilySpec("reaction_force", "反力", (FIELD_KEY_RF,)),
    _FieldFamilySpec("stress", "应力", (FIELD_KEY_S_AVG, FIELD_KEY_S_REC, FIELD_KEY_S, FIELD_KEY_S_IP)),
    _FieldFamilySpec("strain", "应变", (FIELD_KEY_E_AVG, FIELD_KEY_E_REC, FIELD_KEY_E, FIELD_KEY_E_IP)),
    _FieldFamilySpec("displacement_magnitude", "位移模", (FIELD_KEY_U_MAG,)),
    _FieldFamilySpec("von_mises_stress", "等效应力", (FIELD_KEY_S_VM_AVG, FIELD_KEY_S_VM_REC, FIELD_KEY_S_VM, FIELD_KEY_S_VM_IP)),
    _FieldFamilySpec(
        "principal_stress",
        "主应力",
        (FIELD_KEY_S_PRINCIPAL_AVG, FIELD_KEY_S_PRINCIPAL_REC, FIELD_KEY_S_PRINCIPAL, FIELD_KEY_S_PRINCIPAL_IP),
    ),
    _FieldFamilySpec("mode_shape", "模态振型", (FIELD_KEY_MODE_SHAPE,)),
)

_FIELD_VARIANT_LABELS: dict[str, str] = {
    FIELD_KEY_U: "节点",
    FIELD_KEY_RF: "节点",
    FIELD_KEY_U_MAG: "节点",
    FIELD_KEY_S_AVG: "节点平均",
    FIELD_KEY_S_REC: "恢复",
    FIELD_KEY_S: "单元中心",
    FIELD_KEY_S_IP: "积分点",
    FIELD_KEY_E_AVG: "节点平均",
    FIELD_KEY_E_REC: "恢复",
    FIELD_KEY_E: "单元中心",
    FIELD_KEY_E_IP: "积分点",
    FIELD_KEY_S_VM_AVG: "节点平均",
    FIELD_KEY_S_VM_REC: "恢复",
    FIELD_KEY_S_VM: "单元中心",
    FIELD_KEY_S_VM_IP: "积分点",
    FIELD_KEY_S_PRINCIPAL_AVG: "节点平均",
    FIELD_KEY_S_PRINCIPAL_REC: "恢复",
    FIELD_KEY_S_PRINCIPAL: "单元中心",
    FIELD_KEY_S_PRINCIPAL_IP: "积分点",
    FIELD_KEY_MODE_SHAPE: "节点",
}

_GENERIC_VARIANT_LABELS: dict[tuple[str, str], str] = {
    ("averaged", "NODE_AVERAGED"): "节点平均",
    ("recovered", "ELEMENT_NODAL"): "恢复",
    ("raw", "ELEMENT_CENTROID"): "单元中心",
    ("raw", "INTEGRATION_POINT"): "积分点",
    ("raw", "NODE"): "节点",
    ("derived", "NODE"): "节点派生",
    ("derived", "INTEGRATION_POINT"): "积分点派生",
    ("derived", "NODE_AVERAGED"): "节点平均派生",
    ("derived", "ELEMENT_CENTROID"): "单元中心派生",
    ("derived", "ELEMENT_NODAL"): "恢复派生",
}


@dataclass(slots=True)
class FieldPresentationPolicy:
    """负责将正式结果字段组织为 GUI 可消费的 family / variant 结构。"""

    families: tuple[FieldFamily, ...]
    _family_by_key: dict[str, FieldFamily] = field(init=False, repr=False)
    _field_to_family_key: dict[str, str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """建立 family 与正式字段的快速索引。"""

        family_by_key: dict[str, FieldFamily] = {}
        field_to_family_key: dict[str, str] = {}
        for family in self.families:
            family_by_key[family.family_key] = family
            for variant in family.variants:
                if variant.is_common:
                    continue
                field_to_family_key[variant.field_name] = family.family_key
        self._family_by_key = family_by_key
        self._field_to_family_key = field_to_family_key

    @classmethod
    def from_field_overviews(cls, field_overviews: Iterable[ResultFieldOverview]) -> FieldPresentationPolicy:
        """从当前帧的正式字段概览构建展示策略。"""

        overview_by_field_name = {
            overview.field_name: overview
            for overview in field_overviews
        }
        families: list[FieldFamily] = []
        consumed_field_names: set[str] = set()
        for spec in _FAMILY_SPECS:
            available_overviews = tuple(
                overview_by_field_name[field_name]
                for field_name in spec.formal_field_names
                if field_name in overview_by_field_name
            )
            if not available_overviews:
                continue
            families.append(_build_family(spec, available_overviews))
            consumed_field_names.update(overview.field_name for overview in available_overviews)

        for overview in overview_by_field_name.values():
            if overview.field_name in consumed_field_names:
                continue
            families.append(_build_generic_family(overview))

        return cls(families=tuple(families))

    def family(self, family_key: str) -> FieldFamily | None:
        """按 key 返回一个 family。"""

        return self._family_by_key.get(family_key)

    def family_for_field_name(self, field_name: str | None) -> FieldFamily | None:
        """按正式字段名查找其所属的 family。"""

        if field_name is None:
            return None
        family_key = self._field_to_family_key.get(field_name)
        if family_key is None:
            return None
        return self._family_by_key.get(family_key)

    def default_field_name(self, preferred_field_name: str | None = None) -> str | None:
        """返回当前帧最适合默认选中的正式字段。"""

        if preferred_field_name is not None and preferred_field_name in self._field_to_family_key:
            return preferred_field_name
        if FIELD_KEY_U in self._field_to_family_key:
            return FIELD_KEY_U
        return self.families[0].default_field_name if self.families else None

    def default_family_key(self, preferred_field_name: str | None = None) -> str | None:
        """返回当前帧默认 family 的 key。"""

        default_field_name = self.default_field_name(preferred_field_name)
        family = self.family_for_field_name(default_field_name)
        return None if family is None else family.family_key

    def resolve_field_name(self, family_key: str | None, variant_key: str | None) -> str | None:
        """将 GUI family / variant 解析回正式字段名。"""

        if family_key is None:
            return None
        family = self.family(family_key)
        if family is None:
            return None
        resolved_variant_key = COMMON_VARIANT_KEY if variant_key in {None, ""} else str(variant_key)
        for variant in family.variants:
            if variant.variant_key == resolved_variant_key:
                return variant.field_name
        return family.default_field_name

    def variant(self, family_key: str | None, variant_key: str | None) -> FieldVariant | None:
        """返回 family 下指定的变体对象。"""

        if family_key is None:
            return None
        family = self.family(family_key)
        if family is None:
            return None
        resolved_variant_key = COMMON_VARIANT_KEY if variant_key in {None, ""} else str(variant_key)
        for variant in family.variants:
            if variant.variant_key == resolved_variant_key:
                return variant
        return family.variants[0] if family.variants else None

    def variant_key_for_field_name(
        self,
        family_key: str | None,
        field_name: str | None,
        *,
        prefer_common: bool = False,
    ) -> str | None:
        """根据正式字段反推出 variant key。"""

        if family_key is None or field_name is None:
            return None
        family = self.family(family_key)
        if family is None:
            return None
        if prefer_common and family.default_field_name == field_name:
            return COMMON_VARIANT_KEY
        for variant in family.variants:
            if variant.is_common:
                continue
            if variant.field_name == field_name:
                return variant.variant_key
        if family.default_field_name == field_name:
            return COMMON_VARIANT_KEY
        return None

    def describe_selection(
        self,
        field_name: str | None,
        *,
        variant_key: str | None = None,
        prefer_common: bool = False,
    ) -> FieldSelectionPresentation | None:
        """生成当前正式字段对应的 GUI 展示描述。"""

        family = self.family_for_field_name(field_name)
        if family is None or field_name is None:
            return None
        resolved_variant_key = variant_key
        if resolved_variant_key is None:
            resolved_variant_key = self.variant_key_for_field_name(
                family.family_key,
                field_name,
                prefer_common=prefer_common,
            )
        variant = self.variant(family.family_key, resolved_variant_key)
        if variant is None:
            return None
        variant_display_name = variant.display_name
        if variant.is_common:
            explicit_variant = self.variant(
                family.family_key,
                self.variant_key_for_field_name(family.family_key, variant.field_name, prefer_common=False),
            )
            explicit_name = variant.display_name if explicit_variant is None else explicit_variant.display_name
            variant_display_name = f"常用（{explicit_name}）"
        return FieldSelectionPresentation(
            family_key=family.family_key,
            family_display_name=family.display_name,
            variant_key=variant.variant_key,
            variant_display_name=variant_display_name,
            field_name=variant.field_name,
            tooltip_text=variant.tooltip_text,
            detail_text=variant.detail_text,
        )


def format_variant_display_name(field_name: str, source_type: str, position: str) -> str:
    """为正式字段生成简洁的 GUI 变体名称。"""

    if field_name in _FIELD_VARIANT_LABELS:
        return _FIELD_VARIANT_LABELS[field_name]
    return _GENERIC_VARIANT_LABELS.get((source_type, position), field_name)


def _build_family(spec: _FieldFamilySpec, overviews: tuple[ResultFieldOverview, ...]) -> FieldFamily:
    default_overview = overviews[0]
    variants = (
        _build_variant(
            spec.display_name,
            default_overview,
            variant_key=COMMON_VARIANT_KEY,
            display_name="常用",
            prefix_note="当前 family 的默认变体。",
        ),
        *(
            _build_variant(
                spec.display_name,
                overview,
                variant_key=overview.field_name,
                display_name=format_variant_display_name(overview.field_name, overview.source_type, overview.position),
            )
            for overview in overviews
        ),
    )
    family_tooltip = "\n".join(
        (
            spec.display_name,
            f"默认正式字段: {default_overview.field_name}",
            f"可用变体: {', '.join(variant.display_name for variant in variants)}",
        )
    )
    return FieldFamily(
        family_key=spec.family_key,
        display_name=spec.display_name,
        default_field_name=default_overview.field_name,
        variants=tuple(variants),
        tooltip_text=family_tooltip,
    )


def _build_generic_family(overview: ResultFieldOverview) -> FieldFamily:
    family_display_name = _generic_family_display_name(overview.field_name)
    explicit_variant_name = format_variant_display_name(overview.field_name, overview.source_type, overview.position)
    common_variant = _build_variant(
        family_display_name,
        overview,
        variant_key=COMMON_VARIANT_KEY,
        display_name="常用",
        prefix_note="当前字段未命中预设物理量族，按单字段回退展示。",
    )
    explicit_variant = _build_variant(
        family_display_name,
        overview,
        variant_key=overview.field_name,
        display_name=explicit_variant_name,
    )
    return FieldFamily(
        family_key=f"generic:{overview.field_name}",
        display_name=family_display_name,
        default_field_name=overview.field_name,
        variants=(common_variant, explicit_variant),
        tooltip_text="\n".join(
            (
                family_display_name,
                f"正式字段: {overview.field_name}",
                "说明: 当前字段未配置专门的 GUI 物理量族映射。",
            )
        ),
    )


def _build_variant(
    family_display_name: str,
    overview: ResultFieldOverview,
    *,
    variant_key: str,
    display_name: str,
    prefix_note: str | None = None,
) -> FieldVariant:
    detail_lines = [
        family_display_name,
        f"变体: {display_name}",
        f"正式字段: {overview.field_name}",
        f"来源: {overview.source_type}",
        f"位置: {overview.position}",
        f"分量: {', '.join(overview.component_names) or '-'}",
        f"目标数: {overview.target_count}",
    ]
    if prefix_note:
        detail_lines.insert(0, prefix_note)
    detail_text = "\n".join(detail_lines)
    return FieldVariant(
        variant_key=variant_key,
        display_name=display_name,
        field_name=overview.field_name,
        source_type=overview.source_type,
        position=overview.position,
        component_names=overview.component_names,
        target_count=overview.target_count,
        tooltip_text=detail_text,
        detail_text=detail_text,
    )


def _generic_family_display_name(field_name: str) -> str:
    if field_name == FIELD_KEY_MODE_SHAPE:
        return "模态振型"
    return field_name
