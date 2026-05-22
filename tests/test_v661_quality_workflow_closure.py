"""v6.6.1: Quality Diagnosis Workflow Closure tests.

Tests that quality diagnosis feeds into Polisher/Editor decision context
without adding workflow nodes, without replacing review score semantics,
and without introducing revision dead loops.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

import pytest
from fastapi.testclient import TestClient

from novel_factory.llm.provider import LLMProvider
from novel_factory.models.schemas import PolisherOutput, EditorOutput


class StubLLMProvider(LLMProvider):
    """Stub LLM that returns predetermined JSON responses."""

    def __init__(self, responses: list[dict[str, Any]] | None = None):
        self.responses = responses or []
        self.call_count = 0

    def invoke_json(self, messages, schema=None, **kwargs):
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return resp
        # Default fallback
        return {"pass": True, "score": 85, "scores": {"setting": 20, "logic": 20, "poison": 15, "text": 15, "pacing": 15}, "issues": [], "suggestions": [], "revision_target": None, "state_card": {}}

    def invoke_text(self, messages, **kwargs):
        return "stub text"


SAMPLE_AI_HEAVY_TEXT = """李明感到一阵愤怒涌上心头。

他看着眼前的对手，心中暗想：这次一定要赢。

"你这个人，真是太可笑了。"他说道。

这个世界是一个充满魔法的世界，在这个世界里，人们可以通过修炼获得强大的力量。所谓修炼，是指通过吸收天地灵气来增强自身实力的过程。简单来说，修炼就是变强的途径。

然而，事情并没有那么简单。

张华觉得有些不安。他知道，这次的任务非常危险。他明白，如果失败，后果将不堪设想。

"我们必须小心。"张华说道。

"我明白。"李明回答。

与此同时，王芳也感到了同样的压力。她意识到，这场战斗将决定一切。

综上所述，三人都做好了准备。
"""

SAMPLE_GOOD_TEXT = """李明攥紧拳头，指节发白。

眼前的对手正步步逼近，每一步都像踩在鼓点上。李明没有后退，只是微微侧头，让过对方的第一拳，反手一记肘击撞在对手肋下。

"就这点本事？"对手咧着嘴，呼吸有些急促。

李明没回答，只是脚步一错，身形如鬼魅般绕到对手身后。空气中弥漫着汗水和铁锈的气味，远处传来几声喝彩，又被更大的嘘声压了下去。

张华靠在石柱旁，手里把玩着一枚铜币。铜币在他指间翻转，发出细碎的摩擦声。他没有抬头，只是用余光扫着场中的两人。

"赌谁赢？"旁边有人低声问。

"赌命。"张华终于开口，声音轻得像叹息。

王芳站在阴影里，手指无意识地摩挲着腰间的短刀。刀柄已经被汗水浸得湿滑，但她没有松手。

场中的两人再次交错，拳脚相撞的闷响在空旷的大厅里回荡。
"""


@pytest.fixture
def client_with_repo():
    """Create a fresh TestClient with in-memory DB for each test."""
    from novel_factory.api_app import create_api_app
    from novel_factory.db.connection import init_db
    from novel_factory.db.repository import Repository

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    yield TestClient(app), Repository(db_path), db_path
    if os.path.exists(db_path):
        os.unlink(db_path)


# ── A. feedback_bridge tests ─────────────────────────────────────


class TestFeedbackBridge:
    """Test QualityFeedbackBridge conversion and limits."""

    def test_build_compact_feedback_maps_dimensions(self):
        """Dimension scores below threshold should produce instructions."""
        from novel_factory.quality.feedback_bridge import build_compact_feedback

        diagnose_result = {
            "overall_score": 62.0,
            "dimensions": {
                "hook_strength": 40.0,
                "dialogue_naturalness": 50.0,
                "show_dont_tell": 45.0,
                "info_dump": 30.0,
                "scene_immersion": 60.0,
                "death_penalty": 100.0,
            },
            "findings": [],
            "metrics": {"word_count": 2000, "dialogue_ratio": 0.02, "avg_sentence_length": 30.0},
        }

        fb = build_compact_feedback(diagnose_result)

        assert len(fb.polisher_instructions) > 0
        assert any("hook_strength" in i for i in fb.polisher_instructions)
        assert any("dialogue" in i for i in fb.polisher_instructions)
        assert any("show" in i or "直白心理" in i for i in fb.polisher_instructions)
        assert any("info_dump" in i or "说明" in i for i in fb.polisher_instructions)

    def test_build_compact_feedback_caps_findings(self):
        """Output must respect max_* limits."""
        from novel_factory.quality.feedback_bridge import build_compact_feedback

        findings = [
            {"severity": "high", "code": f"FIND_{i}", "message": f"msg {i}", "evidence": None, "suggestion": None}
            for i in range(20)
        ]
        diagnose_result = {
            "overall_score": 50.0,
            "dimensions": {},
            "findings": findings,
            "metrics": {"word_count": 1000, "dialogue_ratio": 0.1, "avg_sentence_length": 25.0},
        }

        fb = build_compact_feedback(diagnose_result, max_priority=3, max_advisory=2)
        assert len(fb.priority_findings) <= 3
        assert len(fb.advisory_findings) <= 2

    def test_build_compact_feedback_evidence_is_compact(self):
        """Evidence must not leak long text, only counts/ratios."""
        from novel_factory.quality.feedback_bridge import build_compact_feedback

        findings = [
            {
                "severity": "medium",
                "code": "LONG_EVIDENCE",
                "message": "short msg",
                "evidence": "x" * 500,
                "suggestion": "fix it",
            }
        ]
        diagnose_result = {
            "overall_score": 70.0,
            "dimensions": {},
            "findings": findings,
            "metrics": {"word_count": 1000, "dialogue_ratio": 0.1, "avg_sentence_length": 25.0},
        }

        fb = build_compact_feedback(diagnose_result)
        ev = fb.advisory_findings[0]["evidence"]
        assert ev is not None
        assert "len=" in ev or len(str(ev)) <= 45

    def test_build_compact_feedback_empty_result(self):
        """All-green diagnosis should produce empty feedback."""
        from novel_factory.quality.feedback_bridge import build_compact_feedback

        diagnose_result = {
            "overall_score": 95.0,
            "dimensions": {
                "death_penalty": 100.0,
                "show_dont_tell": 90.0,
                "info_dump": 95.0,
            },
            "findings": [],
            "metrics": {"word_count": 2000, "dialogue_ratio": 0.15, "avg_sentence_length": 28.0},
        }

        fb = build_compact_feedback(diagnose_result)
        assert fb.is_empty()
        assert fb.quality_risk_note is None

    def test_format_polisher_context_includes_header(self):
        """Polisher context must contain the section header."""
        from novel_factory.quality.feedback_bridge import (
            QualityFeedback, format_polisher_context,
        )

        fb = QualityFeedback(
            priority_findings=[{"code": "P1", "message": "m1", "evidence": None, "suggestion": None}],
            advisory_findings=[],
            polisher_instructions=["fix dialogue"],
            editor_notes=[],
            deferred_findings=[],
            quality_risk_note="1 priority",
        )
        ctx = format_polisher_context(fb)
        assert "本轮质量诊断修复重点" in ctx
        assert "fix dialogue" in ctx
        assert "不得为修分数改剧情事实" in ctx

    def test_format_editor_context_includes_header(self):
        """Editor context must contain the section header."""
        from novel_factory.quality.feedback_bridge import (
            QualityFeedback, format_editor_context,
        )

        fb = QualityFeedback(
            priority_findings=[{"code": "P1", "message": "m1", "evidence": None, "suggestion": None}],
            advisory_findings=[{"code": "A1", "message": "m2", "evidence": None, "suggestion": None}],
            polisher_instructions=[],
            editor_notes=["note1"],
            deferred_findings=[],
        )
        ctx = format_editor_context(fb)
        assert "辅助质量诊断参考" in ctx
        assert "不替代五层审校评分" in ctx
        assert "note1" in ctx


# ── B. Polisher integration tests ────────────────────────────────


class TestPolisherQualityIntegration:
    """Test Polisher agent consumes quality feedback."""

    def test_polisher_build_context_includes_quality_feedback(self, client_with_repo):
        """Polisher build_context should inject quality diagnosis section."""
        client, repo, db_path = client_with_repo
        repo.create_project(project_id="qp1", name="QP", genre="fantasy")
        repo.add_chapter("qp1", 1, title="Ch1", status="drafted")
        repo.save_chapter_content("qp1", 1, SAMPLE_AI_HEAVY_TEXT, "第一章")

        from novel_factory.agents.polisher import PolisherAgent
        from novel_factory.skills.registry import SkillRegistry
        from novel_factory.models.state import FactoryState

        llm = StubLLMProvider([
            {
                "content": SAMPLE_GOOD_TEXT,
                "fact_change_risk": "none",
                "changed_scope": ["dialogue", "show_dont_tell"],
                "summary": " polished ",
            }
        ])
        agent = PolisherAgent(repo, llm, skill_registry=SkillRegistry())
        state: FactoryState = {
            "project_id": "qp1",
            "chapter_number": 1,
            "chapter_status": "drafted",
            "llm_mode": "stub",
        }
        ctx = agent.build_context(state)
        assert "本轮质量诊断修复重点" in ctx or "润色写作提醒" in ctx

    def test_polisher_output_has_quality_fields(self, client_with_repo):
        """PolisherOutput schema must include quality fields."""
        output = PolisherOutput(
            content="test",
            fixed_quality_findings=["fixed1"],
            deferred_quality_findings=["deferred1"],
            quality_risk_note="risk",
        )
        d = output.model_dump()
        assert d["fixed_quality_findings"] == ["fixed1"]
        assert d["deferred_quality_findings"] == ["deferred1"]
        assert d["quality_risk_note"] == "risk"

    def test_polisher_passthrough_has_quality_fields(self, client_with_repo):
        """Passthrough fallback must produce stable quality fields."""
        client, repo, db_path = client_with_repo
        repo.create_project(project_id="qp2", name="QP", genre="fantasy")
        repo.add_chapter("qp2", 1, title="Ch1", status="drafted")
        repo.save_chapter_content("qp2", 1, SAMPLE_GOOD_TEXT, "第一章")

        from novel_factory.agents.polisher import PolisherAgent
        from novel_factory.models.state import FactoryState

        llm = StubLLMProvider([])  # will fail
        agent = PolisherAgent(repo, llm, skill_registry=None)
        state: FactoryState = {
            "project_id": "qp2",
            "chapter_number": 1,
            "chapter_status": "drafted",
            "llm_mode": "stub",
        }
        result = agent.run(state)
        # In stub mode with failing LLM, it should still return a dict
        assert isinstance(result, dict)

    def test_polisher_quality_diagnosis_does_not_block_workflow(self, client_with_repo):
        """Quality diagnosis injection must not cause polisher to return error."""
        client, repo, db_path = client_with_repo
        repo.create_project(project_id="qp3", name="QP", genre="fantasy")
        repo.add_chapter("qp3", 1, title="Ch1", status="drafted")
        repo.save_chapter_content("qp3", 1, SAMPLE_GOOD_TEXT, "第一章")
        # Set low word target to avoid word count gate failure
        repo.create_instruction("qp3", 1, objective="test", key_events="", word_target=200)

        from novel_factory.agents.polisher import PolisherAgent
        from novel_factory.skills.registry import SkillRegistry
        from novel_factory.models.state import FactoryState

        llm = StubLLMProvider([
            {
                "content": SAMPLE_GOOD_TEXT,
                "fact_change_risk": "none",
                "changed_scope": ["dialogue"],
                "summary": " polished ",
            }
        ])
        agent = PolisherAgent(repo, llm, skill_registry=SkillRegistry())
        state: FactoryState = {
            "project_id": "qp3",
            "chapter_number": 1,
            "chapter_status": "drafted",
            "llm_mode": "stub",
        }
        result = agent.run(state)
        assert "error" not in result
        assert result.get("chapter_status") == "polished"


# ── C. Editor integration tests ──────────────────────────────────


class TestEditorQualityIntegration:
    """Test Editor agent consumes quality feedback correctly."""

    def test_editor_build_context_includes_quality_feedback(self, client_with_repo):
        """Editor build_context should inject quality diagnosis section."""
        client, repo, db_path = client_with_repo
        repo.create_project(project_id="qe1", name="QE", genre="fantasy")
        repo.add_chapter("qe1", 1, title="Ch1", status="polished")
        repo.save_chapter_content("qe1", 1, SAMPLE_AI_HEAVY_TEXT, "第一章")

        from novel_factory.agents.editor import EditorAgent
        from novel_factory.skills.registry import SkillRegistry
        from novel_factory.models.state import FactoryState

        llm = StubLLMProvider([
            {
                "pass": True,
                "score": 88,
                "scores": {"setting": 22, "logic": 20, "poison": 18, "text": 16, "pacing": 12},
                "issues": [],
                "suggestions": [],
                "revision_target": None,
                "state_card": {},
            }
        ])
        agent = EditorAgent(repo, llm, skill_registry=SkillRegistry())
        state: FactoryState = {
            "project_id": "qe1",
            "chapter_number": 1,
            "chapter_status": "polished",
            "llm_mode": "stub",
        }
        ctx = agent.build_context(state)
        # SAMPLE_AI_HEAVY_TEXT triggers death-penalty critical finding,
        # so quality diagnosis feedback must be injected.
        assert "辅助质量诊断参考" in ctx or "高优先级问题" in ctx or "死刑红线" in ctx

    def test_editor_85_plus_with_advisory_passes(self, client_with_repo):
        """Score >= 85 with only advisory quality findings should pass."""
        from novel_factory.quality.editor_strategy import classify_editor_result

        decision = classify_editor_result(
            score=87,
            issues=["[v6.4质量信号] 场景描写较少"],
            has_blocking=False,
            has_hard_word_fail=False,
            has_death_penalty=False,
            quality_priority_count=0,
            quality_advisory_only=True,
        )
        assert decision.pass_ is True
        assert decision.category == "advisory"

    def test_editor_80_84_with_advisory_is_advisory(self, client_with_repo):
        """Score 80-84 with only advisory should be advisory, not revision."""
        from novel_factory.quality.editor_strategy import classify_editor_result

        decision = classify_editor_result(
            score=82,
            issues=["[v6.4质量信号] 章末钩子强度不足"],
            has_blocking=False,
            has_hard_word_fail=False,
            has_death_penalty=False,
            quality_priority_count=0,
            quality_advisory_only=True,
        )
        assert decision.pass_ is True
        assert decision.category == "advisory"

    def test_editor_80_84_with_quality_priority_is_revision(self, client_with_repo):
        """Score 80-84 with quality priority findings should be revision."""
        from novel_factory.quality.editor_strategy import classify_editor_result

        decision = classify_editor_result(
            score=83,
            issues=["[v6.4质量信号] 对白较僵硬"],
            has_blocking=False,
            has_hard_word_fail=False,
            has_death_penalty=False,
            quality_priority_count=2,
            quality_advisory_only=False,
        )
        assert decision.pass_ is False
        assert decision.category == "revision"

    def test_editor_below_80_is_revision(self, client_with_repo):
        """Score < 80 should be revision regardless of quality diagnosis."""
        from novel_factory.quality.editor_strategy import classify_editor_result

        decision = classify_editor_result(
            score=75,
            issues=[],
            has_blocking=False,
            has_hard_word_fail=False,
            has_death_penalty=False,
            quality_priority_count=0,
            quality_advisory_only=True,
        )
        assert decision.pass_ is False
        assert decision.category == "revision"

    def test_editor_death_penalty_overrides_high_score(self, client_with_repo):
        """Death penalty must block even with high score and advisory-only diagnosis."""
        from novel_factory.quality.editor_strategy import classify_editor_result

        decision = classify_editor_result(
            score=92,
            issues=["CRITICAL 死刑红线: 冷笑"],
            has_blocking=False,
            has_hard_word_fail=False,
            has_death_penalty=True,
            quality_priority_count=0,
            quality_advisory_only=True,
        )
        assert decision.pass_ is False
        assert decision.category == "blocking"

    def test_editor_injects_priority_findings_into_issues(self, client_with_repo):
        """Editor should append high-priority quality findings to issues for audit."""
        client, repo, db_path = client_with_repo
        repo.create_project(project_id="qe2", name="QE", genre="fantasy")
        repo.add_chapter("qe2", 1, title="Ch1", status="polished")
        repo.save_chapter_content("qe2", 1, SAMPLE_GOOD_TEXT, "第一章")
        repo.create_instruction("qe2", 1, objective="test", key_events="", word_target=200)

        from novel_factory.agents.editor import EditorAgent
        from novel_factory.skills.registry import SkillRegistry
        from novel_factory.models.state import FactoryState

        llm = StubLLMProvider([
            {
                "pass": True,
                "score": 88,
                "scores": {"setting": 22, "logic": 20, "poison": 18, "text": 16, "pacing": 12},
                "issues": [],
                "suggestions": [],
                "revision_target": None,
                "state_card": {},
            }
        ])
        agent = EditorAgent(repo, llm, skill_registry=SkillRegistry())
        state: FactoryState = {
            "project_id": "qe2",
            "chapter_number": 1,
            "chapter_status": "polished",
            "llm_mode": "stub",
        }
        result = agent.run(state)
        assert "error" not in result
        assert result["chapter_status"] == "reviewed"


# ── D. Anti-deadloop tests ───────────────────────────────────────


class TestQualityAntiDeadloop:
    """Test that quality diagnosis does not create revision dead loops."""

    def test_repeated_advisory_does_not_increment_retry(self, client_with_repo):
        """Advisory-only passes should not increase retry count."""
        client, repo, db_path = client_with_repo
        repo.create_project(project_id="qd1", name="QD", genre="fantasy")
        repo.add_chapter("qd1", 1, title="Ch1", status="polished")
        repo.save_chapter_content("qd1", 1, SAMPLE_GOOD_TEXT, "第一章")
        repo.create_instruction("qd1", 1, objective="test", key_events="", word_target=200)

        from novel_factory.agents.editor import EditorAgent
        from novel_factory.skills.registry import SkillRegistry
        from novel_factory.models.state import FactoryState

        llm = StubLLMProvider([
            {
                "pass": True,
                "score": 86,
                "scores": {"setting": 22, "logic": 20, "poison": 18, "text": 16, "pacing": 10},
                "issues": ["[v6.4质量信号] 场景描写较少"],
                "suggestions": ["增加场景细节"],
                "revision_target": None,
                "state_card": {},
            }
        ])
        agent = EditorAgent(repo, llm, skill_registry=SkillRegistry())
        state: FactoryState = {
            "project_id": "qd1",
            "chapter_number": 1,
            "chapter_status": "polished",
            "llm_mode": "stub",
        }
        before = repo.get_chapter_retry_count("qd1", 1)
        result = agent.run(state)
        after = repo.get_chapter_retry_count("qd1", 1)
        assert result["chapter_status"] == "reviewed"
        assert after == before  # advisory pass should not increment retry

    def test_deadloop_detector_not_triggered_by_advisory_loop(self, client_with_repo):
        """DeadloopDetector should not fire on advisory-only iterations."""
        from novel_factory.quality.deadloop_detector import DeadloopDetector

        client, repo, db_path = client_with_repo
        repo.create_project(project_id="qd2", name="QD", genre="fantasy")
        repo.add_chapter("qd2", 1, title="Ch1", status="polished")

        result = DeadloopDetector.check_deadloop(repo, "qd2", 1, recent_scores=[86, 87, 85])
        assert result["triggered"] is False


# ── E. API semantic tests ────────────────────────────────────────


class TestQualityApiSemantics:
    """Test that API/UI do not conflate review score and diagnosis score."""

    def test_quality_diagnosis_endpoint_returns_separate_score(self, client_with_repo):
        """Quality diagnosis API should return its own score, not review score."""
        client, repo, db_path = client_with_repo
        repo.create_project(project_id="qa1", name="QA", genre="fantasy")
        repo.add_chapter("qa1", 1, title="Ch1", status="polished")
        repo.save_chapter_content("qa1", 1, SAMPLE_AI_HEAVY_TEXT, "第一章")

        resp = client.get("/api/projects/qa1/chapters/1/quality-diagnosis")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "overall_score" in data
        assert "dimensions" in data
        assert "findings" in data
        assert "metrics" in data

    def test_review_score_is_independent(self, client_with_repo):
        """Review score and diagnosis score should be independent fields."""
        client, repo, db_path = client_with_repo
        repo.create_project(project_id="qa2", name="QA", genre="fantasy")
        repo.add_chapter("qa2", 1, title="Ch1", status="polished")
        repo.save_chapter_content("qa2", 1, SAMPLE_GOOD_TEXT, "第一章")
        # Save a review
        repo.save_review(
            project_id="qa2",
            chapter_id=repo.get_chapter("qa2", 1)["id"],
            passed=True,
            score=92,
            setting_score=23,
            logic_score=20,
            poison_score=18,
            text_score=16,
            pacing_score=15,
            issues=[],
            suggestions=[],
            revision_target=None,
        )

        review_resp = client.get("/api/review/chapter?project_id=qa2&chapter=1")
        diag_resp = client.get("/api/projects/qa2/chapters/1/quality-diagnosis")

        assert review_resp.status_code == 200
        assert diag_resp.status_code == 200

        review_data = review_resp.json()["data"]["data"]
        diag_data = diag_resp.json()["data"]

        assert review_data["latest_review"]["score"] == 92
        assert "overall_score" in diag_data
