"""结果字段展示策略单元测试。"""

from __future__ import annotations

import unittest

from pyfem.gui.result_field_presentation import COMMON_VARIANT_KEY, FieldPresentationPolicy
from pyfem.io import (
    FIELD_KEY_S,
    FIELD_KEY_S_AVG,
    FIELD_KEY_S_IP,
    FIELD_KEY_S_REC,
    FIELD_KEY_U,
    POSITION_ELEMENT_CENTROID,
    POSITION_INTEGRATION_POINT,
    POSITION_NODE,
    POSITION_NODE_AVERAGED,
    RESULT_SOURCE_AVERAGED,
    RESULT_SOURCE_RAW,
    RESULT_SOURCE_RECOVERED,
)
from pyfem.post import ResultFieldOverview
from tests.gui_test_support import build_semantic_results_view_context


class ResultFieldPresentationPolicyTests(unittest.TestCase):
    """验证 GUI 结果字段展示策略的分组与解析行为。"""

    def test_groups_frame_fields_into_expected_families(self) -> None:
        overviews = build_semantic_results_view_context().results_facade.fields(step_name="STEP-1", frame_id=0)

        policy = FieldPresentationPolicy.from_field_overviews(overviews)

        self.assertEqual(
            tuple(family.family_key for family in policy.families),
            ("displacement", "stress", "displacement_magnitude", "von_mises_stress", "principal_stress"),
        )
        self.assertEqual(policy.default_field_name(), FIELD_KEY_U)

        stress_family = policy.family("stress")
        self.assertIsNotNone(stress_family)
        assert stress_family is not None
        self.assertEqual(stress_family.default_field_name, FIELD_KEY_S_AVG)
        self.assertEqual(
            tuple(variant.display_name for variant in stress_family.variants),
            ("常用", "节点平均", "恢复", "单元中心", "积分点"),
        )

    def test_falls_back_to_next_available_variant_when_preferred_field_is_missing(self) -> None:
        policy = FieldPresentationPolicy.from_field_overviews(
            (
                self._build_overview(
                    field_name=FIELD_KEY_S,
                    position=POSITION_ELEMENT_CENTROID,
                    source_type=RESULT_SOURCE_RAW,
                    component_names=("S11", "S22"),
                    target_count=1,
                ),
                self._build_overview(
                    field_name=FIELD_KEY_S_IP,
                    position=POSITION_INTEGRATION_POINT,
                    source_type=RESULT_SOURCE_RAW,
                    component_names=("S11", "S22"),
                    target_count=4,
                ),
            )
        )

        stress_family = policy.family("stress")
        self.assertIsNotNone(stress_family)
        assert stress_family is not None
        self.assertEqual(stress_family.default_field_name, FIELD_KEY_S)
        self.assertEqual(policy.default_field_name(), FIELD_KEY_S)
        self.assertEqual(policy.resolve_field_name("stress", COMMON_VARIANT_KEY), FIELD_KEY_S)

    def test_describe_selection_prefers_common_alias_when_requested(self) -> None:
        overviews = build_semantic_results_view_context().results_facade.fields(step_name="STEP-1", frame_id=0)
        policy = FieldPresentationPolicy.from_field_overviews(overviews)

        selection = policy.describe_selection(
            FIELD_KEY_S_AVG,
            variant_key=COMMON_VARIANT_KEY,
            prefer_common=True,
        )

        self.assertIsNotNone(selection)
        assert selection is not None
        self.assertEqual(selection.family_display_name, "应力")
        self.assertEqual(selection.variant_display_name, "常用（节点平均）")
        self.assertIn("正式字段: S_AVG", selection.tooltip_text)
        self.assertIn("来源: averaged", selection.tooltip_text)
        self.assertIn("位置: NODE_AVERAGED", selection.detail_text)

    def test_unknown_field_uses_generic_fallback_without_raising(self) -> None:
        policy = FieldPresentationPolicy.from_field_overviews(
            (
                self._build_overview(
                    field_name="CUSTOM_FIELD",
                    position=POSITION_NODE,
                    source_type=RESULT_SOURCE_RAW,
                    component_names=("VALUE",),
                    target_count=2,
                ),
            )
        )

        self.assertEqual(policy.default_field_name(), "CUSTOM_FIELD")
        self.assertEqual(policy.default_family_key(), "generic:CUSTOM_FIELD")
        family = policy.family("generic:CUSTOM_FIELD")
        self.assertIsNotNone(family)
        assert family is not None
        self.assertEqual(family.display_name, "CUSTOM_FIELD")
        self.assertEqual(policy.resolve_field_name(family.family_key, COMMON_VARIANT_KEY), "CUSTOM_FIELD")

    def _build_overview(
        self,
        *,
        field_name: str,
        position: str,
        source_type: str,
        component_names: tuple[str, ...],
        target_count: int,
    ) -> ResultFieldOverview:
        return ResultFieldOverview(
            step_name="step-1",
            frame_id=0,
            field_name=field_name,
            position=position,
            source_type=source_type,
            component_names=component_names,
            target_count=target_count,
        )


if __name__ == "__main__":
    unittest.main()
