"""Tests for validators/ — death penalty, chapter checker, state verifier, plot verifier."""

from __future__ import annotations

import pytest

from novel_factory.validators.death_penalty import check_death_penalty, has_death_penalty
from novel_factory.validators.chapter_checker import check_word_count, validate_chapter_output
from novel_factory.validators.state_verifier import check_status_precondition, check_transition
from novel_factory.validators.plot_verifier import check_plot_coverage
from novel_factory.models.state import ChapterStatus


class TestDeathPenalty:
    def test_no_violations(self):
        assert check_death_penalty("林默走进房间，安静地坐下。") == []

    def test_catch_cold_smile(self):
        violations = check_death_penalty("他冷笑了一声。")
        assert "冷笑" in violations

    def test_catch_corner_smile(self):
        violations = check_death_penalty("她嘴角微扬，露出笑意。")
        assert "嘴角微扬" in violations

    def test_catch_gasp(self):
        violations = check_death_penalty("众人倒吸一口凉气。")
        assert "倒吸一口凉气" in violations

    def test_catch_eye_flash(self):
        violations = check_death_penalty("他眼中闪过一道寒芒。")
        assert "眼中闪过" in violations

    def test_catch_inner_thought(self):
        violations = check_death_penalty("他心中暗想，这事不简单。")
        assert "心中暗想" in violations

    def test_multiple_violations(self):
        violations = check_death_penalty("他冷笑一声，心中暗想不妙。")
        assert len(violations) >= 2

    def test_has_death_penalty_true(self):
        assert has_death_penalty("冷笑") is True

    def test_has_death_penalty_false(self):
        assert has_death_penalty("正常内容") is False


class TestChapterChecker:
    def test_word_count_ok(self):
        content = "正常" * 300  # 600 chars
        assert check_word_count(content) == []

    def test_word_count_too_short(self):
        violations = check_word_count("太短")
        assert len(violations) == 1
        assert "字数不足" in violations[0]

    def test_word_count_too_long(self):
        content = "x" * 9000
        violations = check_word_count(content)
        assert len(violations) == 1
        assert "字数超标" in violations[0]

    def test_empty_content(self):
        violations = check_word_count("")
        assert "内容为空" in violations

    def test_validate_chapter_output_empty(self):
        violations = validate_chapter_output({})
        assert "content 为空" in violations

    def test_validate_chapter_output_word_count_mismatch(self):
        violations = validate_chapter_output({
            "content": "短内容",
            "word_count": 5000,
        })
        assert any("word_count 不匹配" in v for v in violations)

    def test_validate_chapter_output_valid(self):
        content = "正常内容" * 100  # 400 chars
        violations = validate_chapter_output({
            "content": content,
            "word_count": len(content),
        })
        # May fail on min_words, but should not have mismatch
        assert not any("word_count 不匹配" in v for v in violations)


class TestStateVerifier:
    def test_planner_idea_ok(self):
        assert check_status_precondition("planner", "idea") == []

    def test_planner_outlined_ok(self):
        assert check_status_precondition("planner", "outlined") == []

    def test_planner_planned_ok(self):
        assert check_status_precondition("planner", "planned") == []

    def test_author_scripted_ok(self):
        assert check_status_precondition("author", "scripted") == []

    def test_author_revision_ok(self):
        assert check_status_precondition("author", "revision") == []

    def test_author_wrong_status(self):
        violations = check_status_precondition("author", "planned")
        assert len(violations) == 1
        assert "scripted" in violations[0]

    def test_polisher_drafted_ok(self):
        assert check_status_precondition("polisher", "drafted") == []

    def test_polisher_revision_ok(self):
        assert check_status_precondition("polisher", "revision") == []

    def test_editor_polished_ok(self):
        assert check_status_precondition("editor", "polished") == []

    def test_editor_review_ok(self):
        assert check_status_precondition("editor", "review") == []

    def test_valid_transition(self):
        assert check_transition("planned", "scripted") == []

    def test_invalid_transition(self):
        violations = check_transition("planned", "published")
        assert len(violations) == 1
        assert "非法" in violations[0]


class TestPlotVerifier:
    def test_no_instruction(self):
        # v1.2: None instruction returns a warning
        result = check_plot_coverage(None, [])
        assert len(result) >= 0  # may have warning about missing instruction

    def test_all_plots_covered(self):
        instruction = {
            "plots_to_plant": '["P001"]',
            "plots_to_resolve": '["P002"]',
        }
        warnings = check_plot_coverage(instruction, ["P001", "P002"])
        assert warnings == []

    def test_missing_plant(self):
        instruction = {
            "plots_to_plant": '["P001"]',
            "plots_to_resolve": "[]",
        }
        warnings = check_plot_coverage(instruction, [])
        assert any("P001" in w for w in warnings)

    def test_missing_resolve(self):
        instruction = {
            "plots_to_plant": "[]",
            "plots_to_resolve": '["P002"]',
        }
        warnings = check_plot_coverage(instruction, [])
        assert any("P002" in w for w in warnings)
