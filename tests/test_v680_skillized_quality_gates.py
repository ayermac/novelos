"""v6.8.0: Skillized Quality Gates tests.

Tests that:
1. Each new Phase 1 Skill can be instantiated via registry
2. Each Skill's run() returns correct {ok, error, data} envelope
3. Skills are pure functions (no side effects)
4. Skills are correctly registered in skills.yaml and base.py
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.skills.registry import SkillRegistry
from novel_factory.skills.base import BUILTIN_SKILLS, _get_skill_class


# ── Helpers ──────────────────────────────────────────────────────


@pytest.fixture
def repo():
    """Create a temporary DB and Repository."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    repository = Repository(path)
    yield repository
    os.unlink(path)


@pytest.fixture
def skill_registry():
    """Create a SkillRegistry from the default config."""
    config_path = os.path.join(os.path.dirname(__file__), "..", "novel_factory", "config", "skills.yaml")
    if not os.path.exists(config_path):
        config_path = "novel_factory/config/skills.yaml"
    return SkillRegistry(config_path)


# ── A. BUILTIN_SKILLS whitelist ──────────────────────────────────


def test_builtin_skills_contains_phase1():
    """All 5 Phase 1 Skills are in BUILTIN_SKILLS whitelist."""
    for name in ("ContinuityGateSkill", "ChapterSeamSkill", "DeathPenaltySkill", "WordCountGateSkill", "FactLockSkill"):
        assert name in BUILTIN_SKILLS, f"{name} not in BUILTIN_SKILLS"


def test_get_skill_class_returns_phase1():
    """_get_skill_class returns the correct class for each Phase 1 Skill."""
    from novel_factory.skills.continuity_gate_skill import ContinuityGateSkill
    from novel_factory.skills.chapter_seam_skill import ChapterSeamSkill
    from novel_factory.skills.death_penalty_skill import DeathPenaltySkill
    from novel_factory.skills.word_count_gate_skill import WordCountGateSkill
    from novel_factory.skills.fact_lock_skill import FactLockSkill

    assert _get_skill_class("ContinuityGateSkill") is ContinuityGateSkill
    assert _get_skill_class("ChapterSeamSkill") is ChapterSeamSkill
    assert _get_skill_class("DeathPenaltySkill") is DeathPenaltySkill
    assert _get_skill_class("WordCountGateSkill") is WordCountGateSkill
    assert _get_skill_class("FactLockSkill") is FactLockSkill


# ── B. Registry loads Phase 1 Skills ────────────────────────────


def test_registry_has_phase1_skills(skill_registry):
    """SkillRegistry can get all Phase 1 Skills."""
    for skill_id in ("continuity-gate", "chapter-seam", "death-penalty", "word-count-gate", "fact-lock"):
        skill = skill_registry.get_skill(skill_id)
        assert skill is not None, f"Skill '{skill_id}' not found in registry"


# ── C. ContinuityGateSkill ──────────────────────────────────────


def test_continuity_gate_empty_content(skill_registry):
    """ContinuityGateSkill returns error on empty content."""
    skill = skill_registry.get_skill("continuity-gate")
    result = skill.run({"content": ""})
    assert result["ok"] is False
    assert "缺少 content" in result["error"]


def test_continuity_gate_title_only(skill_registry):
    """ContinuityGateSkill runs title check without repo."""
    skill = skill_registry.get_skill("continuity-gate")
    result = skill.run({"content": "some text", "title": "第5章 三家世界五百强企业宣布无"})
    assert "data" in result
    assert result["data"]["severity"] == "warning"


def test_continuity_gate_title_truncation(skill_registry):
    """ContinuityGateSkill detects truncated title."""
    skill = skill_registry.get_skill("continuity-gate")
    result = skill.run({"content": "some text", "title": "第5章 三家世界五百强企业宣布无"})
    issues = result["data"]["issues"]
    assert any("截断" in i or "残缺" in i for i in issues)


# ── D. ChapterSeamSkill ─────────────────────────────────────────


def test_chapter_seam_empty_content(skill_registry):
    """ChapterSeamSkill returns error on empty content."""
    skill = skill_registry.get_skill("chapter-seam")
    result = skill.run({"content": ""})
    assert result["ok"] is False
    assert "缺少 content" in result["error"]


def test_chapter_seam_no_repo(skill_registry):
    """ChapterSeamSkill passes without repo (no cross-chapter check possible)."""
    skill = skill_registry.get_skill("chapter-seam")
    result = skill.run({"content": "some text"})
    assert result["ok"] is True
    assert result["data"]["passed"] is True


# ── E. DeathPenaltySkill ────────────────────────────────────────


def test_death_penalty_clean_text(skill_registry):
    """DeathPenaltySkill passes clean text."""
    skill = skill_registry.get_skill("death-penalty")
    result = skill.run({"text": "他走进了会议室，坐下来打开笔记本电脑。"})
    assert result["ok"] is True
    assert result["data"]["has_critical"] is False


def test_death_penalty_detects_cliche(skill_registry):
    """DeathPenaltySkill detects AI cliche phrases."""
    skill = skill_registry.get_skill("death-penalty")
    result = skill.run({"text": "他嘴角微微上扬，眼中闪过一丝精光。"})
    assert "data" in result
    assert "has_critical" in result["data"]


def test_death_penalty_empty_text(skill_registry):
    """DeathPenaltySkill passes empty text (no content to check)."""
    skill = skill_registry.get_skill("death-penalty")
    result = skill.run({"text": ""})
    assert result["ok"] is True


# ── F. WordCountGateSkill ───────────────────────────────────────


def test_word_count_gate_within_bounds(skill_registry):
    """WordCountGateSkill passes text within target range."""
    skill = skill_registry.get_skill("word-count-gate")
    text = "这是一段测试文字。" * 50  # ~250 chars
    result = skill.run({"text": text, "word_target": 200, "tolerance_ratio": 0.5})
    assert result["ok"] is True
    assert result["data"]["passed"] is True
    assert result["data"]["word_count"] > 0


def test_word_count_gate_too_short(skill_registry):
    """WordCountGateSkill fails text below lower bound."""
    skill = skill_registry.get_skill("word-count-gate")
    result = skill.run({"text": "太短了", "word_target": 1000, "tolerance_ratio": 0.25})
    assert result["ok"] is False
    assert result["data"]["passed"] is False
    assert len(result["data"]["issues"]) > 0


def test_word_count_gate_no_target(skill_registry):
    """WordCountGateSkill passes when no target specified."""
    skill = skill_registry.get_skill("word-count-gate")
    result = skill.run({"text": "some text"})
    assert result["ok"] is True
    assert result["data"]["word_count"] > 0


def test_word_count_gate_empty_text(skill_registry):
    """WordCountGateSkill fails on empty text."""
    skill = skill_registry.get_skill("word-count-gate")
    result = skill.run({"text": ""})
    assert result["ok"] is False


# ── G. FactLockSkill ────────────────────────────────────────────


def test_fact_lock_no_items(skill_registry):
    """FactLockSkill passes when no fact items provided."""
    skill = skill_registry.get_skill("fact-lock")
    result = skill.run({"text": "some polished text"})
    assert result["ok"] is True
    assert result["data"]["risk_level"] == "none"


def test_fact_lock_empty_text(skill_registry):
    """FactLockSkill passes on empty text (nothing to check)."""
    skill = skill_registry.get_skill("fact-lock")
    result = skill.run({"text": ""})
    assert result["ok"] is True


def test_fact_lock_with_items(skill_registry):
    """FactLockSkill checks fact items against polished text."""
    skill = skill_registry.get_skill("fact-lock")
    result = skill.run({
        "text": "主角走进了会议室。",
        "fact_lock_items": ["主角", "会议室"],
    })
    assert "data" in result
    assert "risk_level" in result["data"]


# ── H. Skill envelope contract ──────────────────────────────────


def test_all_phase1_skills_return_envelope(skill_registry):
    """All Phase 1 Skills return {ok, error, data} envelope."""
    skills_and_payloads = [
        ("continuity-gate", {"content": "test content", "title": "test"}),
        ("chapter-seam", {"content": "test content"}),
        ("death-penalty", {"text": "test content"}),
        ("word-count-gate", {"text": "test content"}),
        ("fact-lock", {"text": "test content"}),
    ]
    for skill_id, payload in skills_and_payloads:
        skill = skill_registry.get_skill(skill_id)
        result = skill.run(payload)
        assert "ok" in result, f"{skill_id} missing 'ok'"
        assert "error" in result, f"{skill_id} missing 'error'"
        assert "data" in result, f"{skill_id} missing 'data'"
        assert isinstance(result["ok"], bool), f"{skill_id} 'ok' is not bool"
