"""v6.4.4: Editor Advisory Quality Gates tests.

Tests that Editor uses v6.4.0-6.4.3 anti-AI skill signals as advisory
issues/suggestions without changing workflow routing.
No LLM calls for the advisory layer. No text rewriting.
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


# -- Sample texts --

SAMPLE_AI_HEAVY_TEXT = (
    "李明感到一阵愤怒涌上心头。\n\n"
    "他看着眼前的对手，这次一定要赢。\n\n"
    "\"你这个人，真是太可笑了。\"他说道。\n\n"
    "这个世界是一个充满魔法的世界，在这个世界里，人们可以通过修炼获得强大的力量。"
    "所谓修炼，是指通过吸收天地灵气来增强自身实力的过程。简单来说，修炼就是变强的途径。\n\n"
    "然而，事情并没有那么简单。\n\n"
    "张华觉得有些不安。他明白，这次的任务非常危险。他理解，如果失败，后果将不堪设想。\n\n"
    "\"我们必须小心。\"张华说道。\n\n"
    "\"我明白。\"李明回答。\n\n"
    "与此同时，王芳也感到了同样的压力。她意识到，这场战斗将决定一切。\n\n"
    "综上所述，三人都做好了准备。\n\n"
)
# Pad to meet editor word-count threshold (2250+)
SAMPLE_AI_HEAVY_TEXT = SAMPLE_AI_HEAVY_TEXT * 15

SAMPLE_GOOD_TEXT = (
    "李明攥紧拳头，指节发白。\n\n"
    "眼前的对手正咧嘴笑着逼近，每一步都像踩在鼓点上。李明没有后退，只是微微侧头，"
    "让过对方的第一拳，反手一记肘击撞在对手肋下。\n\n"
    "\"就这点本事？\"对手咧着嘴，呼吸有些急促。\n\n"
    "李明没回答，只是脚步一错，身形如鬼魅般绕到对手身后。空气中弥漫着汗水和铁锈的气味，"
    "远处传来几声喝彩，又被更大的嘘声压了下去。\n\n"
    "张华靠在石柱旁，手里把玩着一枚铜币。铜币在他指间翻转，发出细碎的摩擦声。"
    "他没有抬头，只是用余光扫着场中的两人。\n\n"
    "\"赌谁赢？\"旁边有人低声问。\n\n"
    "\"赌命。\"张华终于开口，声音轻得像叹息。\n\n"
    "王芳站在阴影里，手指无意识地摩挲着腰间的短刀。刀柄已经被汗水浸得湿滑，但她没有松手。\n\n"
    "场中的两人再次交错，拳脚相撞的闷响在空旷的大厅里回荡。\n\n"
)
# Pad to meet editor word-count threshold (2250+)
SAMPLE_GOOD_TEXT = SAMPLE_GOOD_TEXT * 15


class StubLLMProvider(LLMProvider):
    """Stub LLM that returns predetermined JSON responses."""

    def __init__(self, responses: list[dict] | None = None):
        self.responses = responses or []
        self._call_count = 0

    def invoke_json(self, messages, schema=None, temperature=None) -> dict:
        if self._call_count < len(self.responses):
            resp = self.responses[self._call_count]
            self._call_count += 1
            return resp
        return {}

    def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
        return json.dumps(self.invoke_json(messages))


@pytest.fixture
def seeded_repo():
    """Seed a project and chapter in 'polished' status."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)
    repo = Repository(db_path)
    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        ("test_proj", "Test Novel", "urban"),
    )
    conn.execute(
        "INSERT INTO chapters (project_id, chapter_number, title, status) "
        "VALUES (?, ?, ?, ?)",
        ("test_proj", 1, "第一章 测试", "polished"),
    )
    conn.execute(
        "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
        "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
        ("test_proj", 1, "测试目标", '["事件1"]', '["P001"]', '[]', "悬念", 2500),
    )
    conn.execute(
        "INSERT INTO characters (project_id, name, role, description, status) "
        "VALUES (?, ?, ?, ?, 'active')",
        ("test_proj", "林默", "protagonist", "主角"),
    )
    conn.commit()
    conn.close()
    try:
        yield repo
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


class TestEditorPromptContract:
    """Editor SYSTEM_PROMPT contains v6.4 quality dimension guidance."""

    def test_prompt_contains_ai_trace_guidance(self):
        from novel_factory.agents.editor import EDITOR_SYSTEM_PROMPT
        assert "AI 痕迹" in EDITOR_SYSTEM_PROMPT
        assert "感到" in EDITOR_SYSTEM_PROMPT
        assert "觉得" in EDITOR_SYSTEM_PROMPT

    def test_prompt_contains_show_dont_tell_guidance(self):
        from novel_factory.agents.editor import EDITOR_SYSTEM_PROMPT
        assert "直白情绪" in EDITOR_SYSTEM_PROMPT
        assert "无旁白式" in EDITOR_SYSTEM_PROMPT

    def test_prompt_contains_scene_texture_guidance(self):
        from novel_factory.agents.editor import EDITOR_SYSTEM_PROMPT
        assert "感官细节" in EDITOR_SYSTEM_PROMPT
        assert "光影" in EDITOR_SYSTEM_PROMPT

    def test_prompt_contains_dialogue_guidance(self):
        from novel_factory.agents.editor import EDITOR_SYSTEM_PROMPT
        assert "对白" in EDITOR_SYSTEM_PROMPT
        assert "潜台词" in EDITOR_SYSTEM_PROMPT

    def test_prompt_contains_pacing_guidance(self):
        from novel_factory.agents.editor import EDITOR_SYSTEM_PROMPT
        assert "节奏控制" in EDITOR_SYSTEM_PROMPT
        assert "段落长短" in EDITOR_SYSTEM_PROMPT

    def test_prompt_contains_no_rewrite_rule(self):
        from novel_factory.agents.editor import EDITOR_SYSTEM_PROMPT
        assert "不直接改写正文" in EDITOR_SYSTEM_PROMPT

    def test_prompt_revision_target_mapping(self):
        from novel_factory.agents.editor import EDITOR_SYSTEM_PROMPT
        assert "info dump" in EDITOR_SYSTEM_PROMPT
        assert "直白情绪" in EDITOR_SYSTEM_PROMPT
        assert '"author"' in EDITOR_SYSTEM_PROMPT
        assert '"polisher"' in EDITOR_SYSTEM_PROMPT


class TestEditorAdvisoryUnit:
    """Direct unit tests for _run_advisory_quality_check."""

    def test_ai_heavy_text_generates_advisory_issues(self):
        """AI-heavy text should produce [v6.4质量信号] advisory issues."""
        from novel_factory.agents.editor import EditorAgent
        from novel_factory.skills.registry import SkillRegistry
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        repo = Repository(db_path)
        try:
            agent = EditorAgent(repo, StubLLMProvider(), skill_registry=SkillRegistry())
            issues, suggestions = agent._run_advisory_quality_check(SAMPLE_AI_HEAVY_TEXT)
            assert len(issues) > 0
            assert any("v6.4质量信号" in i for i in issues)
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_advisory_issues_include_expected_codes(self):
        """Advisory issues should reference anti-AI skill codes."""
        from novel_factory.agents.editor import EditorAgent
        from novel_factory.skills.registry import SkillRegistry
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        repo = Repository(db_path)
        try:
            agent = EditorAgent(repo, StubLLMProvider(), skill_registry=SkillRegistry())
            issues, _ = agent._run_advisory_quality_check(SAMPLE_AI_HEAVY_TEXT)
            codes_present = []
            for i in issues:
                if "STRAIGHT_EMOTION" in i:
                    codes_present.append("STRAIGHT_EMOTION")
                if "LORE_DUMP" in i or "INFO_DUMP" in i:
                    codes_present.append("INFO_DUMP")
                if "SCENE_TEXTURE" in i or "LOW_SENSORY" in i:
                    codes_present.append("SCENE_TEXTURE")
                if "DIALOGUE" in i:
                    codes_present.append("DIALOGUE")
            assert "STRAIGHT_EMOTION" in codes_present
            assert "INFO_DUMP" in codes_present
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_advisory_capped_at_three(self):
        """Advisory findings should be capped at 3 to avoid noise."""
        from novel_factory.agents.editor import EditorAgent
        from novel_factory.skills.registry import SkillRegistry
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        repo = Repository(db_path)
        try:
            agent = EditorAgent(repo, StubLLMProvider(), skill_registry=SkillRegistry())
            long_bad_text = SAMPLE_AI_HEAVY_TEXT * 5
            issues, _ = agent._run_advisory_quality_check(long_bad_text)
            assert len(issues) <= 3
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_advisory_suggestions_present(self):
        """Advisory findings should map to suggestions."""
        from novel_factory.agents.editor import EditorAgent
        from novel_factory.skills.registry import SkillRegistry
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        repo = Repository(db_path)
        try:
            agent = EditorAgent(repo, StubLLMProvider(), skill_registry=SkillRegistry())
            _, suggestions = agent._run_advisory_quality_check(SAMPLE_AI_HEAVY_TEXT)
            assert any(s.startswith("[") and "]" in s for s in suggestions)
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_evidence_not_huge(self):
        """Advisory issues must not contain large text payloads."""
        from novel_factory.agents.editor import EditorAgent
        from novel_factory.skills.registry import SkillRegistry
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        repo = Repository(db_path)
        try:
            agent = EditorAgent(repo, StubLLMProvider(), skill_registry=SkillRegistry())
            issues, _ = agent._run_advisory_quality_check(SAMPLE_AI_HEAVY_TEXT)
            for i in issues:
                assert len(i) < 500, f"Issue too long: {i[:50]}..."
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_no_skill_registry_returns_empty(self):
        """Without skill_registry, advisory check returns empty lists."""
        from novel_factory.agents.editor import EditorAgent
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        repo = Repository(db_path)
        try:
            agent = EditorAgent(repo, StubLLMProvider(), skill_registry=None)
            issues, suggestions = agent._run_advisory_quality_check(SAMPLE_AI_HEAVY_TEXT)
            assert issues == []
            assert suggestions == []
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_empty_text_returns_empty(self):
        """Empty text should return empty advisory lists."""
        from novel_factory.agents.editor import EditorAgent
        from novel_factory.skills.registry import SkillRegistry
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        repo = Repository(db_path)
        try:
            agent = EditorAgent(repo, StubLLMProvider(), skill_registry=SkillRegistry())
            issues, suggestions = agent._run_advisory_quality_check("")
            assert issues == []
            assert suggestions == []
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestEditorAdvisoryIntegration:
    """Integration tests: advisory signals through full Editor workflow."""

    def _run_editor(self, repo, content: str, llm_pass: bool = True, skill_registry=None):
        from novel_factory.agents.editor import EditorAgent
        from novel_factory.skills.registry import SkillRegistry

        repo.save_chapter_content("test_proj", 1, content, "第一章 测试")
        repo.update_chapter_status("test_proj", 1, "polished")

        stub = StubLLMProvider([{
            "pass": llm_pass,
            "score": 92 if llm_pass else 65,
            "scores": {"setting": 23, "logic": 20, "poison": 18, "text": 16, "pacing": 15},
            "issues": [],
            "suggestions": [],
            "revision_target": None,
            "state_card": {},
        }])

        agent = EditorAgent(repo, stub, skill_registry=skill_registry if skill_registry is not None else SkillRegistry())
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }
        return agent.run(state)

    def test_good_text_passes_with_advisory(self, seeded_repo):
        """Good text passes Editor review; advisory issues are appended non-blocking."""
        result = self._run_editor(seeded_repo, SAMPLE_GOOD_TEXT, llm_pass=True)
        assert result["chapter_status"] == ChapterStatus.REVIEWED.value
        assert result["quality_gate"]["pass"] is True

        review = seeded_repo.get_latest_review("test_proj", 1)
        assert review is not None
        issues = json.loads(review["issues"])
        # Good text may have a few advisory issues (e.g. dialogue ratio), but workflow passes
        assert any("v6.4质量信号" in i for i in issues) or len(issues) == 0

    def test_good_text_advisory_capped(self, seeded_repo):
        """Good text should not generate more than 3 advisory issues."""
        result = self._run_editor(seeded_repo, SAMPLE_GOOD_TEXT, llm_pass=True)
        review = seeded_repo.get_latest_review("test_proj", 1)
        issues = json.loads(review["issues"])
        advisory_count = sum(1 for i in issues if "v6.4质量信号" in i)
        assert advisory_count <= 3

    def test_advisory_does_not_hard_block_pass(self, seeded_repo):
        """Even with advisory issues, Editor should pass if LLM and gates pass."""
        result = self._run_editor(seeded_repo, SAMPLE_GOOD_TEXT, llm_pass=True)
        assert result["quality_gate"]["pass"] is True
        assert result["chapter_status"] == ChapterStatus.REVIEWED.value

    def test_final_gate_ignores_stale_failed_review_during_editor_run(self, seeded_repo):
        """A previous failed review must not poison the next passing Editor run."""
        chapter = seeded_repo.get_chapter("test_proj", 1)
        assert chapter is not None
        seeded_repo.save_review(
            project_id="test_proj",
            chapter_id=chapter["id"],
            passed=False,
            score=82,
            issues=["[质量诊断建议] 章末钩子强度不足（45.0 < 50）"],
            suggestions=["增加悬念"],
            revision_target="author",
        )

        result = self._run_editor(seeded_repo, SAMPLE_GOOD_TEXT, llm_pass=True)

        assert result["quality_gate"]["pass"] is True
        assert result["chapter_status"] == ChapterStatus.REVIEWED.value

    def test_no_skill_registry_graceful(self, seeded_repo):
        """Editor without skill_registry should not crash."""
        result = self._run_editor(seeded_repo, SAMPLE_GOOD_TEXT, llm_pass=True, skill_registry=None)
        assert result["chapter_status"] == ChapterStatus.REVIEWED.value
        assert result["quality_gate"]["pass"] is True

    def test_fallback_review_includes_advisory(self, seeded_repo):
        """Fallback rule review should also emit advisory quality signals."""
        from novel_factory.agents.editor import EditorAgent
        from novel_factory.llm.openai_compatible import LLMTimeoutError
        from novel_factory.skills.registry import SkillRegistry

        seeded_repo.save_chapter_content("test_proj", 1, SAMPLE_GOOD_TEXT, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "polished")

        class TimeoutLLM(LLMProvider):
            config = object()
            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None):
                raise LLMTimeoutError("timeout")
            def invoke_text(self, messages, **kw):
                return ""

        agent = EditorAgent(seeded_repo, TimeoutLLM(), skill_registry=SkillRegistry())
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "llm_mode": "real",
        }
        result = agent.run(state)
        # v6.7.9: Fallback can no longer auto-pass; check score cap and advisory inclusion
        assert result["quality_gate"]["score"] <= 78

        review = seeded_repo.get_latest_review("test_proj", 1)
        issues = json.loads(review["issues"])
        assert any("v6.4质量信号" in i for i in issues)
        assert any("规则兜底" in i for i in issues)


class TestEditorAdvisoryDoesNotAffectRouting:
    """Advisory signals must not override LLM pass/fail or revision_target."""

    def test_llm_fail_advisory_appended_but_routing_unchanged(self, seeded_repo):
        """When LLM says fail, advisory issues are appended but revision_target stays LLM's."""
        from novel_factory.agents.editor import EditorAgent
        from novel_factory.skills.registry import SkillRegistry

        seeded_repo.save_chapter_content("test_proj", 1, SAMPLE_GOOD_TEXT, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "polished")

        stub = StubLLMProvider([{
            "pass": False,
            "score": 65,
            "scores": {"setting": 15, "logic": 12, "poison": 13, "text": 12, "pacing": 13},
            "issues": ["逻辑漏洞"],
            "suggestions": ["修复逻辑"],
            "revision_target": "author",
            "state_card": {},
        }])

        agent = EditorAgent(seeded_repo, stub, skill_registry=SkillRegistry())
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
        assert result["chapter_status"] == ChapterStatus.REVISION.value
        assert result["quality_gate"]["pass"] is False
        # Advisory issues should be present
        review = seeded_repo.get_latest_review("test_proj", 1)
        issues = json.loads(review["issues"])
        assert any("v6.4质量信号" in i for i in issues)
        # revision_target should be what LLM said (or overridden by classify_issues, but not by advisory)
        assert result["quality_gate"]["revision_target"] in ("author", "polisher")

    def test_advisory_does_not_downgrade_score(self, seeded_repo):
        """Advisory issues must not lower the LLM-reported score directly."""
        from novel_factory.agents.editor import EditorAgent
        from novel_factory.skills.registry import SkillRegistry

        seeded_repo.save_chapter_content("test_proj", 1, SAMPLE_GOOD_TEXT, "第一章 测试")
        seeded_repo.update_chapter_status("test_proj", 1, "polished")

        stub = StubLLMProvider([{
            "pass": True,
            "score": 95,
            "scores": {"setting": 24, "logic": 24, "poison": 19, "text": 15, "pacing": 13},
            "issues": [],
            "suggestions": [],
            "revision_target": None,
            "state_card": {},
        }])

        agent = EditorAgent(seeded_repo, stub, skill_registry=SkillRegistry())
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
        review = seeded_repo.get_latest_review("test_proj", 1)
        assert review is not None
        # Advisory check itself does not lower score; final_gate / before_review may,
        # but the LLM score of 95 should not be dropped by advisory alone.
        # Good text passes final_gate, so score should remain high.
        assert review["score"] >= 70
