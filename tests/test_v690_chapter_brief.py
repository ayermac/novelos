"""v6.9.0: Chapter Brief validation and filling tests.

Covers:
- validate_chapter_brief: Tier 1 field detection
- fill_missing_tier2_fields: genre profile defaults
- validate_and_fill_brief: combined flow
- ChapterBrief model creation
"""

from __future__ import annotations


from novel_factory.models.chapter_contracts import (
    ChapterBrief,
    ChapterBriefTier1,
    ChapterBriefTier2,
)
from novel_factory.models.creative_contracts import GenreProfile
from novel_factory.quality.chapter_brief_validator import (
    validate_chapter_brief,
    fill_missing_tier2_fields,
    validate_and_fill_brief,
    TIER1_FIELDS,
    TIER2_FIELDS,
)


def _full_tier1_brief() -> dict:
    return {
        "chapter_goal": "林默追查灵力来源",
        "reader_payoff": "揭露部分真相",
        "protagonist_agency": "主动出击",
        "forbidden_moves": ["不开挂"],
    }


def _sample_genre_profile() -> GenreProfile:
    return GenreProfile(
        profile_id="test_genre",
        chapter_rhythm_defaults={
            "minor_payoff_frequency": 1,
            "visible_upgrade_frequency": 5,
        },
    )


class TestTier1Fields:
    def test_tier1_field_count(self):
        assert len(TIER1_FIELDS) == 4

    def test_all_tier1_fields_present(self):
        assert "chapter_goal" in TIER1_FIELDS
        assert "reader_payoff" in TIER1_FIELDS
        assert "protagonist_agency" in TIER1_FIELDS
        assert "forbidden_moves" in TIER1_FIELDS


class TestValidateChapterBrief:
    def test_valid_brief(self):
        is_valid, missing = validate_chapter_brief(_full_tier1_brief())
        assert is_valid is True
        assert missing == []

    def test_empty_brief(self):
        is_valid, missing = validate_chapter_brief({})
        assert is_valid is False
        assert set(missing) == set(TIER1_FIELDS)

    def test_none_brief(self):
        is_valid, missing = validate_chapter_brief(None)
        assert is_valid is False
        assert set(missing) == set(TIER1_FIELDS)

    def test_missing_chapter_goal(self):
        brief = _full_tier1_brief()
        del brief["chapter_goal"]
        is_valid, missing = validate_chapter_brief(brief)
        assert is_valid is False
        assert "chapter_goal" in missing

    def test_missing_reader_payoff(self):
        brief = _full_tier1_brief()
        del brief["reader_payoff"]
        is_valid, missing = validate_chapter_brief(brief)
        assert is_valid is False
        assert "reader_payoff" in missing

    def test_missing_multiple(self):
        is_valid, missing = validate_chapter_brief({"chapter_goal": "test"})
        assert is_valid is False
        assert "reader_payoff" in missing
        assert "protagonist_agency" in missing
        assert "forbidden_moves" in missing

    def test_none_value_treated_as_missing(self):
        brief = _full_tier1_brief()
        brief["chapter_goal"] = None
        is_valid, missing = validate_chapter_brief(brief)
        assert is_valid is False
        assert "chapter_goal" in missing

    def test_empty_string_passes(self):
        """Empty string for a Tier 1 field is treated as missing (v6.9.0 stricter validation)."""
        brief = _full_tier1_brief()
        brief["chapter_goal"] = ""
        is_valid, missing = validate_chapter_brief(brief)
        # v6.9.0: empty values for required Tier 1 fields are now flagged as missing
        assert is_valid is False
        assert "chapter_goal" in missing


class TestFillMissingTier2Fields:
    def test_all_tier2_filled(self):
        brief = _full_tier1_brief()
        filled = fill_missing_tier2_fields(brief, _sample_genre_profile())
        for field in TIER2_FIELDS:
            assert field in filled

    def test_existing_tier2_preserved(self):
        brief = _full_tier1_brief()
        brief["pressure_budget"] = "heavy"
        filled = fill_missing_tier2_fields(brief, _sample_genre_profile())
        assert filled["pressure_budget"] == "heavy"

    def test_scene_count_target_default(self):
        filled = fill_missing_tier2_fields({}, _sample_genre_profile())
        assert filled["scene_count_target"] == 3

    def test_empty_brief_fills_all(self):
        filled = fill_missing_tier2_fields({}, _sample_genre_profile())
        assert "pressure_budget" in filled
        assert "opening_hook" in filled
        assert "ending_hook" in filled

    def test_does_not_modify_original(self):
        brief = _full_tier1_brief()
        original_keys = set(brief.keys())
        fill_missing_tier2_fields(brief, _sample_genre_profile())
        assert set(brief.keys()) == original_keys


class TestValidateAndFillBrief:
    def test_valid_and_filled(self):
        brief = _full_tier1_brief()
        is_valid, filled, missing = validate_and_fill_brief(brief, _sample_genre_profile())
        assert is_valid is True
        assert missing == []
        assert "scene_count_target" in filled

    def test_invalid_and_filled(self):
        is_valid, filled, missing = validate_and_fill_brief({}, _sample_genre_profile())
        assert is_valid is False
        assert len(missing) == 4
        assert "scene_count_target" in filled  # Tier 2 still filled


class TestChapterBriefModel:
    def test_model_creation(self):
        brief = ChapterBrief(
            tier1=ChapterBriefTier1(chapter_goal="test"),
            tier2=ChapterBriefTier2(scene_count_target=3),
        )
        assert brief.tier1.chapter_goal == "test"
        assert brief.tier2.scene_count_target == 3

    def test_default_tier1(self):
        tier1 = ChapterBriefTier1()
        assert tier1.chapter_goal == ""
        assert tier1.forbidden_moves == []

    def test_default_tier2(self):
        tier2 = ChapterBriefTier2()
        assert tier2.scene_count_target == 0
        assert tier2.character_arc_moves == []

    def test_serialization(self):
        brief = ChapterBrief()
        data = brief.model_dump()
        assert "tier1" in data
        assert "tier2" in data
        restored = ChapterBrief(**data)
        assert restored.tier1.chapter_goal == brief.tier1.chapter_goal


class TestNestedShapeSupport:
    """v6.9.0: validator must handle nested {tier1, tier2} dicts from ChapterBrief.model_dump()."""

    def test_validate_nested_brief_passes(self):
        brief_model = ChapterBrief(
            tier1=ChapterBriefTier1(
                chapter_goal="追查灵力",
                reader_payoff="揭真相",
                protagonist_agency="主动",
                forbidden_moves=["不开挂"],
            ),
        )
        is_valid, missing = validate_chapter_brief(brief_model.model_dump())
        assert is_valid is True
        assert missing == []

    def test_validate_nested_brief_missing_tier1_field(self):
        brief_model = ChapterBrief(
            tier1=ChapterBriefTier1(
                chapter_goal="目标",
                # reader_payoff missing (defaults to "")
                protagonist_agency="主动",
                forbidden_moves=["x"],
            ),
        )
        is_valid, missing = validate_chapter_brief(brief_model.model_dump())
        assert is_valid is False
        assert "reader_payoff" in missing

    def test_fill_tier2_preserves_nested_shape(self):
        brief_model = ChapterBrief(
            tier1=ChapterBriefTier1(chapter_goal="g", reader_payoff="p",
                                     protagonist_agency="a", forbidden_moves=["x"]),
        )
        filled = fill_missing_tier2_fields(brief_model.model_dump(), _sample_genre_profile())
        # Should remain nested
        assert "tier1" in filled and "tier2" in filled
        assert "scene_count_target" in filled["tier2"]

    def test_fill_tier2_flat_shape_unchanged(self):
        brief = _full_tier1_brief()
        filled = fill_missing_tier2_fields(brief, _sample_genre_profile())
        # Should remain flat
        assert "tier1" not in filled
        assert "scene_count_target" in filled

    def test_validate_and_fill_round_trip_nested(self):
        brief_dict = ChapterBrief(
            tier1=ChapterBriefTier1(chapter_goal="g", reader_payoff="p",
                                     protagonist_agency="a", forbidden_moves=["x"]),
        ).model_dump()
        is_valid, filled, missing = validate_and_fill_brief(brief_dict, _sample_genre_profile())
        assert is_valid is True
        assert missing == []
        assert "tier1" in filled and "tier2" in filled
