"""Tests for models/schemas.py — Pydantic output validation."""

import pytest

from novel_factory.models.schemas import (
    PlannerOutput,
    ChapterBrief,
    ScreenwriterOutput,
    SceneBeat,
    AuthorOutput,
    PolisherOutput,
    EditorOutput,
    EditorScores,
)


class TestPlannerOutput:
    def test_valid_output(self):
        data = {
            "chapter_brief": {
                "objective": "测试目标",
                "required_events": ["事件1"],
                "plots_to_plant": ["P001"],
                "plots_to_resolve": [],
                "ending_hook": "悬念",
                "constraints": ["禁止冷笑"],
            }
        }
        output = PlannerOutput(**data)
        assert output.chapter_brief.objective == "测试目标"
        assert output.chapter_brief.plots_to_plant == ["P001"]

    def test_minimal_output(self):
        output = PlannerOutput(chapter_brief=ChapterBrief(objective="目标"))
        assert output.chapter_brief.required_events == []


class TestScreenwriterOutput:
    def test_valid_output(self):
        data = {
            "scene_beats": [
                {"sequence": 1, "scene_goal": "开场", "conflict": "冲突", "plot_refs": ["P001"]},
            ]
        }
        output = ScreenwriterOutput(**data)
        assert len(output.scene_beats) == 1
        assert output.scene_beats[0].sequence == 1


class TestAuthorOutput:
    def test_valid_output(self):
        data = {
            "title": "第一章 测试",
            "content": "正文内容...",
            "word_count": 2800,
            "implemented_events": ["事件1"],
            "used_plot_refs": ["P001"],
        }
        output = AuthorOutput(**data)
        assert output.word_count == 2800


class TestPolisherOutput:
    def test_valid_output(self):
        data = {
            "content": "润色后正文",
            "fact_change_risk": "none",
            "changed_scope": ["sentence", "dialogue"],
            "summary": "润色完成",
        }
        output = PolisherOutput(**data)
        assert output.fact_change_risk == "none"

    def test_fact_change_risk_not_none_raises(self):
        """Polisher must not change facts — but schema allows it for logging.
        The strict check is in PolisherAgent.validate_output."""
        data = {"content": "正文", "fact_change_risk": "high", "changed_scope": []}
        # Schema itself allows "high" — the agent-level validation enforces "none"
        output = PolisherOutput(**data)
        assert output.fact_change_risk == "high"


class TestEditorOutput:
    def test_valid_pass_output(self):
        data = {
            "pass": True,
            "score": 92,
            "scores": {"setting": 23, "logic": 20, "poison": 18, "text": 16, "pacing": 15},
            "issues": [],
            "suggestions": [],
            "revision_target": None,
            "state_card": {"assets": {"credits": 100}},
        }
        output = EditorOutput(**data)
        assert output.pass_ is True
        assert output.score == 92

    def test_valid_fail_output(self):
        data = {
            "pass": False,
            "score": 65,
            "scores": {"setting": 15, "logic": 12, "poison": 13, "text": 12, "pacing": 13},
            "issues": ["逻辑漏洞"],
            "suggestions": ["修复逻辑"],
            "revision_target": "author",
            "state_card": {},
        }
        output = EditorOutput(**data)
        assert output.pass_ is False
        assert output.revision_target == "author"

    def test_invalid_revision_target(self):
        """revision_target must be author/polisher/planner/null."""
        data = {
            "pass": False, "score": 50,
            "scores": {}, "issues": [], "suggestions": [],
            "revision_target": "invalid_agent",
            "state_card": {},
        }
        output = EditorOutput(**data)
        # Schema accepts any string — validation is in EditorAgent.validate_output
        assert output.revision_target == "invalid_agent"
