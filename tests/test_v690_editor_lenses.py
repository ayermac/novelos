"""v6.9.0: Editor Lenses deterministic tests.

Covers:
- Each of the 7 editor lenses: basic PASS scenarios
- ChiefEditor aggregation and decision logic
- BaseEditorLens score computation
"""

from __future__ import annotations

import pytest

from novel_factory.models.chapter_contracts import EditorLensReport, EditorLensFinding
from novel_factory.agents.editor_lenses.base_lens import BaseEditorLens
from novel_factory.agents.editor_lenses.type_editor import TypeEditorLens
from novel_factory.agents.editor_lenses.commercial_editor import CommercialEditorLens
from novel_factory.agents.editor_lenses.pacing_editor import PacingEditorLens
from novel_factory.agents.editor_lenses.character_editor import CharacterEditorLens
from novel_factory.agents.editor_lenses.mystery_editor import MysteryEditorLens
from novel_factory.agents.editor_lenses.style_editor import StyleEditorLens
from novel_factory.agents.editor_lenses.continuity_editor import ContinuityEditorLens
from novel_factory.agents.editor_lenses.chief_editor import ChiefEditor


def _good_content(length: int = 1000) -> str:
    base = (
        "林默推开房门，夜风裹挟着淡淡的血腥味扑面而来。"
        "他握紧手中的短刀，目光扫过走廊尽头的暗影。"
        "灯光闪烁，墙壁上浮现出奇异的符文图案。"
        "他深吸一口气，脚步无声地向前移动。"
        "突然，一道寒光从侧面袭来——"
    )
    return (base * (length // len(base) + 1))[:length]


def _minimal_context(**overrides) -> dict:
    ctx = {
        "project_id": "test", "chapter_number": 1,
        "genre_contract": {}, "launch_profile": {},
        "chapter_brief": {}, "protagonist_name": "林默",
    }
    ctx.update(overrides)
    return ctx


class TestBaseEditorLensScore:
    def test_no_findings_returns_max(self):
        assert BaseEditorLens._compute_score([]) == 100.0

    def test_blocking_deducts_20(self):
        assert BaseEditorLens._compute_score([EditorLensFinding(severity="blocking")]) == 80.0

    def test_warning_deducts_10(self):
        assert BaseEditorLens._compute_score([EditorLensFinding(severity="warning")]) == 90.0

    def test_info_deducts_3(self):
        assert BaseEditorLens._compute_score([EditorLensFinding(severity="info")]) == 97.0

    def test_floor_at_zero(self):
        findings = [EditorLensFinding(severity="blocking") for _ in range(10)]
        assert BaseEditorLens._compute_score(findings) == 0.0


class TestTypeEditorLens:
    def test_no_genre_contract_passes(self):
        report = TypeEditorLens().evaluate(_good_content(), _minimal_context(genre_contract={}))
        assert report.passed is True
        assert report.lens_type == "type"

    def test_forbidden_drift_blocking(self):
        ctx = _minimal_context(genre_contract={"forbidden_drift": ["穿越"]})
        report = TypeEditorLens().evaluate("主角突然穿越到了异世界", ctx)
        assert report.passed is False
        assert any(f.code == "FORBIDDEN_DRIFT" for f in report.findings)

    def test_no_drift_passes(self):
        ctx = _minimal_context(genre_contract={"forbidden_drift": ["穿越"]})
        report = TypeEditorLens().evaluate("林默走入密室发现了机关", ctx)
        assert report.passed is True


class TestCommercialEditorLens:
    def test_short_content_passes(self):
        report = CommercialEditorLens().evaluate("短", _minimal_context())
        assert report.passed is True
        assert report.lens_type == "commercial"

    def test_engagement_killer_warning(self):
        content = _good_content(600) + "简单来说，这个世界是一个修仙大陆。"
        report = CommercialEditorLens().evaluate(content, _minimal_context())
        assert any(f.code == "ENGAGEMENT_KILLER" for f in report.findings)

    def test_missing_hook_warning(self):
        content = ("林默走在路上看到了山。风景很美。天色渐暗。" * 50)[:1000]
        report = CommercialEditorLens().evaluate(content, _minimal_context())
        assert any(f.code == "MISSING_HOOK" for f in report.findings)

    def test_brief_forbidden_move_blocking(self):
        ctx = _minimal_context(chapter_brief={"tier1": {"forbidden_moves": ["开挂逆袭"]}})
        content = _good_content(600) + "林默突然开挂逆袭般获得了神力。"
        report = CommercialEditorLens().evaluate(content, ctx)
        assert report.passed is False


class TestPacingEditorLens:
    def test_short_content_passes(self):
        report = PacingEditorLens().evaluate("短", _minimal_context())
        assert report.passed is True
        assert report.lens_type == "pacing"

    def test_normal_content(self):
        report = PacingEditorLens().evaluate(_good_content(), _minimal_context())
        assert isinstance(report, EditorLensReport)


class TestCharacterEditorLens:
    def test_short_content_passes(self):
        report = CharacterEditorLens().evaluate("短", _minimal_context())
        assert report.passed is True
        assert report.lens_type == "character"


class TestMysteryEditorLens:
    def test_short_content_passes(self):
        report = MysteryEditorLens().evaluate("短", _minimal_context())
        assert report.passed is True
        assert report.lens_type == "mystery"


class TestStyleEditorLens:
    def test_short_content_passes(self):
        report = StyleEditorLens().evaluate("短", _minimal_context())
        assert report.passed is True
        assert report.lens_type == "style"


class TestContinuityEditorLens:
    def test_short_content_passes(self):
        report = ContinuityEditorLens().evaluate("短", _minimal_context())
        assert report.passed is True
        assert report.lens_type == "continuity"


class TestChiefEditor:
    def test_all_passing(self):
        chief = ChiefEditor()
        reports = [
            EditorLensReport(lens_type="type", passed=True, score=90.0),
            EditorLensReport(lens_type="commercial", passed=True, score=85.0),
            EditorLensReport(lens_type="pacing", passed=True, score=80.0),
            EditorLensReport(lens_type="character", passed=True, score=88.0),
            EditorLensReport(lens_type="mystery", passed=True, score=92.0),
            EditorLensReport(lens_type="style", passed=True, score=78.0),
            EditorLensReport(lens_type="continuity", passed=True, score=95.0),
        ]
        result = chief.aggregate(reports)
        assert result["passed"] is True
        assert result["score"] >= 70.0

    def test_blocking_fails(self):
        chief = ChiefEditor()
        reports = [
            EditorLensReport(lens_type="type", passed=True, score=90.0),
            EditorLensReport(lens_type="commercial", passed=False, score=40.0,
                             findings=[EditorLensFinding(severity="blocking", code="B1")]),
        ]
        result = chief.aggregate(reports)
        assert result["passed"] is False
        assert result["blocking_count"] == 1

    def test_low_score_fails(self):
        chief = ChiefEditor()
        reports = [
            EditorLensReport(lens_type="type", passed=True, score=30.0),
            EditorLensReport(lens_type="commercial", passed=True, score=30.0),
        ]
        result = chief.aggregate(reports)
        assert result["passed"] is False  # weighted avg < 70

    def test_revision_target_planner(self):
        chief = ChiefEditor()
        reports = [
            EditorLensReport(lens_type="type", passed=False, score=40.0),
            EditorLensReport(lens_type="commercial", passed=True, score=90.0),
        ]
        result = chief.aggregate(reports)
        assert result["revision_target"] == "planner"

    def test_revision_target_author(self):
        chief = ChiefEditor()
        reports = [
            EditorLensReport(lens_type="type", passed=True, score=90.0),
            EditorLensReport(lens_type="character", passed=False, score=40.0),
        ]
        result = chief.aggregate(reports)
        assert result["revision_target"] == "author"

    def test_revision_target_polisher(self):
        chief = ChiefEditor()
        reports = [
            EditorLensReport(lens_type="type", passed=True, score=90.0),
            EditorLensReport(lens_type="style", passed=False, score=40.0),
        ]
        result = chief.aggregate(reports)
        assert result["revision_target"] == "polisher"

    def test_custom_weights(self):
        chief = ChiefEditor()
        reports = [
            EditorLensReport(lens_type="type", passed=True, score=100.0),
            EditorLensReport(lens_type="commercial", passed=True, score=50.0),
        ]
        # Commercial has high weight, so avg should be lower
        result = chief.aggregate(reports, genre_weights={"commercial": 5.0})
        assert result["score"] < 80.0
