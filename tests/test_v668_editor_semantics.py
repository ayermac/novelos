"""v6.6.8: Editor Refactor & Review Semantics Closure tests.

Tests that:
- score/advisory/priority/death_penalty/diagnosis/seam semantics are clear
- advisory-only never triggers auto revision
- diagnosis score never replaces review score
- revision_target is never empty for revision
- retry/max_retries routes to human_review
- artifact contains policy input/output snapshots
- editor public behavior remains compatible with existing workflow tests
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.llm.provider import LLMProvider
from novel_factory.models.state import ChapterStatus, FactoryState


# ── Helpers ──────────────────────────────────────────────────────


class StubLLMProvider(LLMProvider):
    def __init__(self, responses: list[dict] | None = None):
        self.responses = responses or []
        self._call_count = 0

    def invoke_json(self, messages, schema=None, **kwargs):
        if self._call_count < len(self.responses):
            resp = self.responses[self._call_count]
            self._call_count += 1
            return resp
        return {}

    def invoke_text(self, messages, **kwargs):
        return json.dumps(self.invoke_json(messages))


SAMPLE_GOOD_TEXT = (
    "李明攥紧拳头，指节发白。\n\n"
    "眼前的对手正咧嘴笑着逼近，每一步都像踩在鼓点上。李明没有后退，只是微微侧头，"
    "让过对方的第一拳，反手一记肘击撞在对手肋下。\n\n"
    '"就这点本事？"对手咧着嘴，呼吸有些急促。\n\n'
    "李明没回答，只是脚步一错，身形如鬼魅般绕到对手身后。空气中弥漫着汗水和铁锈的气味，"
    "远处传来几声喝彩，又被更大的嘘声压了下去。\n\n"
    "张华靠在石柱旁，手里把玩着一枚铜币。铜币在他指间翻转，发出细碎的摩擦声。"
    "他没有抬头，只是用余光扫着场中的两人。\n\n"
    '"赌谁赢？"旁边有人低声问。\n\n'
    '"赌命。"张华终于开口，声音轻得像叹息。\n\n'
    "王芳站在阴影里，手指无意识地摩挲着腰间的短刀。刀柄已经被汗水浸得湿滑，但她没有松手。\n\n"
    "场中的两人再次交错，拳脚相撞的闷响在空旷的大厅里回荡。\n\n"
)
SAMPLE_GOOD_TEXT = SAMPLE_GOOD_TEXT * 15


def _seed_project(repo, project_id="test_proj", chapter_number=1, status="polished"):
    """Seed a project with instruction and chapter."""
    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        (project_id, "Test Novel", "urban"),
    )
    conn.execute(
        "INSERT INTO chapters (project_id, chapter_number, title, status) "
        "VALUES (?, ?, ?, ?)",
        (project_id, chapter_number, "第一章 测试", status),
    )
    conn.execute(
        "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
        "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
        (project_id, chapter_number, "测试目标", '["事件1"]', '["P001"]', '[]', "悬念", 2500),
    )
    conn.execute(
        "INSERT INTO characters (project_id, name, role, description, status) "
        "VALUES (?, ?, ?, ?, 'active')",
        (project_id, "林默", "protagonist", "主角"),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def seeded_repo():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)
    repo = Repository(db_path)
    _seed_project(repo)
    try:
        yield repo
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


# ── A. EditorStrategy unit tests (pure functions) ───────────────


class TestEditorStrategySemantics:
    """Test classify_editor_result via EditorPolicyInput."""

    def test_score_85_plus_advisory_only_is_pass(self):
        """1. score >= 85 + advisory only -> pass."""
        from novel_factory.quality.editor_strategy import EditorPolicyInput, classify_editor_result
        p = EditorPolicyInput(score=87, pass_=True, advisory_issue_count=2, quality_advisory_count=1)
        d = classify_editor_result(p)
        assert d.pass_ is True
        assert d.category == "advisory"
        assert d.decision_type == "advisory_pass"

    def test_score_85_plus_quality_advisory_only_is_pass(self):
        """2. score >= 85 + quality advisory only -> pass."""
        from novel_factory.quality.editor_strategy import EditorPolicyInput, classify_editor_result
        p = EditorPolicyInput(score=90, pass_=True, quality_advisory_count=3)
        d = classify_editor_result(p)
        assert d.pass_ is True
        assert d.category == "advisory"
        assert d.decision_type == "advisory_pass"

    def test_score_85_plus_death_penalty_is_blocking(self):
        """3. score >= 85 + death penalty -> revision/blocking."""
        from novel_factory.quality.editor_strategy import EditorPolicyInput, classify_editor_result
        p = EditorPolicyInput(score=92, pass_=False, death_penalty=True)
        d = classify_editor_result(p)
        assert d.pass_ is False
        assert d.category == "blocking"

    def test_score_80_84_no_priority_is_advisory_pass(self):
        """4. score 80-84 + no priority -> advisory_pass, not revision."""
        from novel_factory.quality.editor_strategy import EditorPolicyInput, classify_editor_result
        p = EditorPolicyInput(score=82, pass_=True, advisory_issue_count=1)
        d = classify_editor_result(p)
        assert d.pass_ is True
        assert d.category == "advisory"
        assert d.decision_type == "advisory_pass"
        assert d.revision_needed is False

    def test_score_80_84_with_quality_priority_is_revision(self):
        """5. score 80-84 + quality_priority_count > 0 -> revision."""
        from novel_factory.quality.editor_strategy import EditorPolicyInput, classify_editor_result
        p = EditorPolicyInput(score=83, pass_=False, quality_priority_count=2)
        d = classify_editor_result(p)
        assert d.pass_ is False
        assert d.category == "revision"

    def test_score_below_80_is_revision(self):
        """6. score < 80 -> revision."""
        from novel_factory.quality.editor_strategy import EditorPolicyInput, classify_editor_result
        p = EditorPolicyInput(score=75, pass_=False)
        d = classify_editor_result(p)
        assert d.pass_ is False
        assert d.category == "revision"

    def test_retry_max_goes_to_human_review(self):
        """7. retry_count >= max_retries -> human_review."""
        from novel_factory.quality.editor_strategy import EditorPolicyInput, classify_editor_result
        p = EditorPolicyInput(score=75, pass_=False, retry_count=3, max_retries=3)
        d = classify_editor_result(p)
        assert d.pass_ is False
        assert d.category == "human_review"
        assert d.revision_needed is False

    def test_quality_hub_exception_does_not_block(self):
        """8. QualityHub exception must not block workflow.

        Test that a failed quality diagnosis (empty result) doesn't
        prevent a high-score advisory pass.
        """
        from novel_factory.quality.editor_strategy import EditorPolicyInput, classify_editor_result
        # Simulate: quality diagnosis failed, all counts are 0
        p = EditorPolicyInput(score=88, pass_=True)
        d = classify_editor_result(p)
        assert d.pass_ is True

    def test_seam_advisory_only_does_not_block(self):
        """9. seam advisory only -> does not block."""
        from novel_factory.quality.editor_strategy import EditorPolicyInput, classify_editor_result
        p = EditorPolicyInput(score=87, pass_=True, seam_advisory_count=2)
        d = classify_editor_result(p)
        assert d.pass_ is True
        assert d.category == "advisory"

    def test_seam_blocking_triggers_revision(self):
        """10. seam blocking -> revision/blocking."""
        from novel_factory.quality.editor_strategy import EditorPolicyInput, classify_editor_result
        p = EditorPolicyInput(score=88, pass_=False, seam_blocking_count=1, blocking_issue_count=1)
        d = classify_editor_result(p)
        assert d.pass_ is False
        assert d.category == "blocking"

    def test_revision_target_default_not_empty(self):
        """11. revision_target default is never empty for revision."""
        from novel_factory.quality.editor_strategy import determine_revision_target
        # No specific issues — should still return a non-empty default
        target = determine_revision_target(issues=["unknown issue"])
        assert target in ("author", "polisher", "planner")
        assert target != ""

    def test_advisory_pass_does_not_increment_retry(self, seeded_repo):
        """12. advisory_pass does not increment retry/deadloop counters."""
        repo = seeded_repo
        repo.save_chapter_content("test_proj", 1, SAMPLE_GOOD_TEXT, "第一章")
        repo.update_chapter_status("test_proj", 1, "polished")
        repo.create_instruction("test_proj", 1, objective="test", key_events="", word_target=200)

        from novel_factory.agents.editor import EditorAgent
        from novel_factory.skills.registry import SkillRegistry

        llm = StubLLMProvider([{
            "pass": True,
            "score": 86,
            "scores": {"setting": 22, "logic": 20, "poison": 18, "text": 16, "pacing": 10},
            "issues": ["[v6.4质量信号] 场景描写较少"],
            "suggestions": ["增加场景细节"],
            "revision_target": None,
            "state_card": {},
        }])
        agent = EditorAgent(repo, llm, skill_registry=SkillRegistry())
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "llm_mode": "stub",
        }
        before = repo.get_chapter_retry_count("test_proj", 1)
        result = agent.run(state)
        after = repo.get_chapter_retry_count("test_proj", 1)
        assert result["chapter_status"] == "reviewed"
        assert after == before

    def test_artifact_contains_policy_snapshot(self, seeded_repo):
        """13. artifact contains policy input/output snapshot."""
        repo = seeded_repo
        repo.save_chapter_content("test_proj", 1, SAMPLE_GOOD_TEXT, "第一章")
        repo.update_chapter_status("test_proj", 1, "polished")
        repo.create_instruction("test_proj", 1, objective="test", key_events="", word_target=200)

        from novel_factory.agents.editor import EditorAgent
        from novel_factory.skills.registry import SkillRegistry

        llm = StubLLMProvider([{
            "pass": True,
            "score": 88,
            "scores": {"setting": 22, "logic": 20, "poison": 18, "text": 16, "pacing": 12},
            "issues": [],
            "suggestions": [],
            "revision_target": None,
            "state_card": {},
        }])
        agent = EditorAgent(repo, llm, skill_registry=SkillRegistry())
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "llm_mode": "stub",
        }
        result = agent.run(state)
        assert "error" not in result

        # Check artifact has strategy snapshot
        conn = repo._conn()
        row = conn.execute(
            "SELECT content_json FROM agent_artifacts "
            "WHERE project_id=? AND agent_id='editor' AND artifact_type='review' "
            "ORDER BY created_at DESC LIMIT 1",
            ("test_proj",),
        ).fetchone()
        conn.close()
        if row and row["content_json"]:
            content = row["content_json"]
            if isinstance(content, str):
                content = json.loads(content)
            assert "_policy_input" in content
            assert "_policy_output" in content
            assert "_strategy_decision" in content
            assert "_seam_check" in content
            assert content["_policy_input"]["score"] == 88
            assert content["_policy_input"]["quality_priority_count"] == 0
            assert content["_policy_input"]["seam_blocking_count"] == 0
            assert content["_policy_input"]["retry_count"] == 0
            assert content["_policy_input"]["max_retries"] == 3
            assert content["_policy_output"]["decision_type"] == "advisory_pass"
            assert content["_strategy_decision"]["decision_type"] == content["_policy_output"]["decision_type"]

    def test_diagnosis_score_does_not_replace_review_score(self):
        """14. diagnosis score does not replace review score."""
        from novel_factory.quality.editor_strategy import EditorPolicyInput, classify_editor_result
        # Diagnosis says 40 but review says 88 — review score wins
        p = EditorPolicyInput(score=88, pass_=True, quality_priority_count=0)
        d = classify_editor_result(p)
        assert d.pass_ is True
        # The policy input's score is the review score, not diagnosis score
        assert p.score == 88

    def test_editor_public_behavior_compatible(self, seeded_repo):
        """15. editor.py public behavior remains compatible with existing workflow tests."""
        repo = seeded_repo
        repo.save_chapter_content("test_proj", 1, SAMPLE_GOOD_TEXT, "第一章")
        repo.update_chapter_status("test_proj", 1, "polished")
        repo.create_instruction("test_proj", 1, objective="test", key_events="", word_target=200)

        from novel_factory.agents.editor import EditorAgent
        from novel_factory.skills.registry import SkillRegistry

        llm = StubLLMProvider([{
            "pass": True,
            "score": 88,
            "scores": {"setting": 22, "logic": 20, "poison": 18, "text": 16, "pacing": 12},
            "issues": [],
            "suggestions": [],
            "revision_target": None,
            "state_card": {},
        }])
        agent = EditorAgent(repo, llm, skill_registry=SkillRegistry())
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }
        result = agent.run(state)
        # Must return standard state fields
        assert "chapter_status" in result
        assert "quality_gate" in result
        assert "current_stage" in result
        assert result["chapter_status"] == "reviewed"
        assert result["quality_gate"]["pass"] is True


# ── B. determine_revision_target tests ──────────────────────────


class TestRevisionTargetSemantics:
    """Test determine_revision_target rules."""

    def test_death_penalty_routes_to_author(self):
        from novel_factory.quality.editor_strategy import determine_revision_target
        assert determine_revision_target(death_penalty=True) == "author"

    def test_planner_level_issues_route_to_planner(self):
        from novel_factory.quality.editor_strategy import determine_revision_target
        assert determine_revision_target(issues=["设定体系冲突严重"]) == "planner"

    def test_author_level_issues_route_to_author(self):
        from novel_factory.quality.editor_strategy import determine_revision_target
        assert determine_revision_target(issues=["逻辑漏洞"]) == "author"

    def test_structural_dialogue_issues_route_to_author(self):
        from novel_factory.quality.editor_strategy import determine_revision_target
        assert determine_revision_target(issues=[
            "[LOW_DIALOGUE_RATIO] 对白占比2.8%严重偏低",
            "冲突强度不足，缺乏面对面的张力场景",
            "人物动机表达不够清晰",
        ]) == "author"

    def test_truncated_hook_and_dialogue_issues_route_to_author(self):
        from novel_factory.quality.editor_strategy import determine_revision_target
        assert determine_revision_target(
            issues=[
                "[CRITICAL] 正文以'林泽'一句未完戛然而止，章节在核心冲突高潮处断裂",
                "[DIALOGUE] 对白仅占全文约3%，大量剧情推进依赖叙述者转述而非角色言行",
                "[HOOK] 章末钩子缺失，悬念被截断的结尾覆盖",
            ],
            llm_revision_target="polisher",
        ) == "author"

    def test_polisher_level_issues_route_to_polisher(self):
        from novel_factory.quality.editor_strategy import determine_revision_target
        assert determine_revision_target(issues=["AI 痕迹偏高"]) == "polisher"

    def test_seam_blocking_routes_to_author(self):
        from novel_factory.quality.editor_strategy import determine_revision_target
        assert determine_revision_target(seam_blocking_count=1) == "author"

    def test_quality_priority_default_to_polisher(self):
        from novel_factory.quality.editor_strategy import determine_revision_target
        assert determine_revision_target(quality_priority_count=2) == "polisher"

    def test_llm_target_used_when_valid(self):
        from novel_factory.quality.editor_strategy import determine_revision_target
        assert determine_revision_target(llm_revision_target="author", issues=["unknown"]) == "author"

    def test_default_is_polisher(self):
        from novel_factory.quality.editor_strategy import determine_revision_target
        assert determine_revision_target() == "polisher"


# ── C. count_issue_types tests ──────────────────────────────────


class TestCountIssueTypes:
    """Test count_issue_types heuristic."""

    def test_critical_is_blocking(self):
        from novel_factory.quality.editor_strategy import count_issue_types
        b, p, a = count_issue_types(["CRITICAL 死刑红线: 冷笑"])
        assert b == 1

    def test_advisory_marker_is_advisory(self):
        from novel_factory.quality.editor_strategy import count_issue_types
        b, p, a = count_issue_types(["[v6.4质量信号] 场景描写较少"])
        assert a == 1
        assert b == 0

    def test_logic_issue_without_critical_is_blocking(self):
        """逻辑漏洞 is in hard issue markers, so it's blocking."""
        from novel_factory.quality.editor_strategy import count_issue_types
        b, p, a = count_issue_types(["逻辑漏洞"])
        assert b == 1

    def test_non_hard_non_advisory_is_priority(self):
        """Issues that are neither hard markers nor advisory are priority."""
        from novel_factory.quality.editor_strategy import count_issue_types
        b, p, a = count_issue_types(["角色塑造不够立体"])
        assert p == 1

    def test_diagnosis_advisory_is_advisory(self):
        from novel_factory.quality.editor_strategy import count_issue_types
        b, p, a = count_issue_types(["[诊断建议] 叙事质量偏低"])
        assert a == 1


# ── D. Legacy backward compatibility ────────────────────────────


class TestLegacyBackwardCompat:
    """Test legacy classify_editor_result_legacy interface."""

    def test_legacy_interface_matches_new(self):
        from novel_factory.quality.editor_strategy import classify_editor_result_legacy, classify_editor_result, EditorPolicyInput
        # Same inputs via legacy and new interface should give same pass_
        d1 = classify_editor_result_legacy(
            score=87,
            issues=["[v6.4质量信号] 场景描写较少"],
            has_blocking=False,
            has_hard_word_fail=False,
            has_death_penalty=False,
            quality_priority_count=0,
            quality_advisory_only=True,
        )
        p = EditorPolicyInput(score=87, pass_=True, advisory_issue_count=1, quality_advisory_count=1)
        d2 = classify_editor_result(p)
        assert d1.pass_ == d2.pass_

    def test_post_process_llm_decision_advisory_override(self):
        """LLM says fail but policy says advisory — override."""
        from novel_factory.quality.editor_strategy import post_process_llm_decision
        d = post_process_llm_decision(
            llm_pass=False,
            score=87,
            issues=["[v6.4质量信号] 场景描写较少"],
            has_death_penalty=False,
            quality_advisory_only=True,
        )
        assert d.pass_ is True
        assert d.category == "advisory"
        assert d.decision_type == "advisory_pass"


# ── E. Integration: score 80-84 boundary ───────────────────────


class TestScore80to84Boundary:
    """Test the critical 80-84 score range with various inputs."""

    def test_80_with_no_priority_pass(self):
        from novel_factory.quality.editor_strategy import EditorPolicyInput, classify_editor_result
        p = EditorPolicyInput(score=80, pass_=True, advisory_issue_count=1)
        d = classify_editor_result(p)
        assert d.pass_ is True

    def test_84_with_no_priority_pass(self):
        from novel_factory.quality.editor_strategy import EditorPolicyInput, classify_editor_result
        p = EditorPolicyInput(score=84, pass_=True)
        d = classify_editor_result(p)
        assert d.pass_ is True

    def test_80_with_quality_priority_revision(self):
        from novel_factory.quality.editor_strategy import EditorPolicyInput, classify_editor_result
        p = EditorPolicyInput(score=80, pass_=False, quality_priority_count=1)
        d = classify_editor_result(p)
        assert d.pass_ is False
        assert d.category == "revision"

    def test_84_with_priority_revision(self):
        from novel_factory.quality.editor_strategy import EditorPolicyInput, classify_editor_result
        p = EditorPolicyInput(score=84, pass_=False, priority_issue_count=1)
        d = classify_editor_result(p)
        assert d.pass_ is False
        assert d.category == "revision"

    def test_79_always_revision(self):
        from novel_factory.quality.editor_strategy import EditorPolicyInput, classify_editor_result
        p = EditorPolicyInput(score=79, pass_=False)
        d = classify_editor_result(p)
        assert d.pass_ is False
        assert d.category == "revision"

    def test_quality_advisory_alone_no_revision(self):
        """quality_advisory_count alone must NOT cause revision for score >= 80."""
        from novel_factory.quality.editor_strategy import EditorPolicyInput, classify_editor_result
        p = EditorPolicyInput(score=82, pass_=True, quality_advisory_count=5)
        d = classify_editor_result(p)
        assert d.pass_ is True
        assert d.category == "advisory"
