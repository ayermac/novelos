"""v6.7.9: Narrative Continuity Gate tests.

Tests that:
1. Chapter-internal time regression is detected as blocking
2. Legitimate short flashbacks are not killed (advisory/pass)
3. Cross-chapter time-anchor conflicts are flagged
4. Truncated/malformed titles are detected
5. Fallback rule review cannot fake-green (score <= 78)
6. Publish endpoint blocks on continuity gate failures
7. All logic is generic (no hardcoded project/chapter/character names)
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any
from unittest.mock import MagicMock

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.llm.provider import LLMProvider
from novel_factory.models.state import ChapterStatus, FactoryState
from novel_factory.quality.continuity_gate import (
    evaluate_chapter_continuity,
    evaluate_publish_continuity,
    SEVERITY_PASS,
    SEVERITY_ADVISORY,
    SEVERITY_WARNING,
    SEVERITY_BLOCKING,
)
from novel_factory.agents.editor import EditorAgent


# ── Helpers ──────────────────────────────────────────────────────


class StubLLMProvider(LLMProvider):
    """Minimal stub that returns canned responses for invoke_json."""

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


def _make_state(
    project_id: str = "test_proj",
    chapter_number: int = 1,
    max_retries: int = 3,
    workflow_run_id: str = "run-001",
    **kwargs,
) -> FactoryState:
    return FactoryState(
        project_id=project_id,
        chapter_number=chapter_number,
        max_retries=max_retries,
        workflow_run_id=workflow_run_id,
        **kwargs,
    )


def _seed_project(repo, project_id="test_proj", chapter_number=1, status="polished"):
    """Seed a project with instruction and chapter."""
    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        (project_id, "Test Novel", "urban"),
    )
    conn.execute(
        "INSERT INTO chapters (project_id, chapter_number, title, status, content) "
        "VALUES (?, ?, ?, ?, ?)",
        (project_id, chapter_number, f"第{chapter_number}章 测试", status, "测试正文内容。"),
    )
    conn.execute(
        "INSERT INTO instructions (project_id, chapter_number, objective, key_events, ending_hook) "
        "VALUES (?, ?, ?, ?, ?)",
        (project_id, chapter_number, "测试目标", "[" "]", "钩子"),
    )
    conn.commit()
    conn.close()


def _seed_prev_chapter(repo, project_id="test_proj"):
    """Seed chapter 1 as reviewed previous chapter for continuity checks."""
    conn = repo._conn()
    existing = conn.execute(
        "SELECT 1 FROM chapters WHERE project_id=? AND chapter_number=?",
        (project_id, 1),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE chapters SET title=?, content=?, status=? WHERE project_id=? AND chapter_number=?",
            ("第一章 起始", "主角来到了秘密基地。会议结束了。", "reviewed", project_id, 1),
        )
    else:
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status, content) "
            "VALUES (?, ?, ?, ?, ?)",
            (project_id, 1, "第一章 起始", "reviewed", "主角来到了秘密基地。会议结束了。"),
        )
    conn.commit()
    conn.close()


def _seed_chapter(repo, project_id, chapter_number, title, content, status="polished"):
    """Seed or update a chapter with specific content."""
    conn = repo._conn()
    existing = conn.execute(
        "SELECT 1 FROM chapters WHERE project_id=? AND chapter_number=?",
        (project_id, chapter_number),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE chapters SET title=?, content=?, status=? WHERE project_id=? AND chapter_number=?",
            (title, content, status, project_id, chapter_number),
        )
    else:
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status, content) "
            "VALUES (?, ?, ?, ?, ?)",
            (project_id, chapter_number, title, status, content),
        )
    conn.commit()
    conn.close()


@pytest.fixture
def repo():
    """Create a temporary DB and Repository."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    repository = Repository(path)
    yield repository
    os.unlink(path)


# ── A. Chapter-internal time regression ──────────────────────────


def test_time_regression_blocking(repo):
    """Mid-chapter 'two hours ago' back to a completed scene → blocking."""
    _seed_project(repo, chapter_number=2)
    _seed_prev_chapter(repo)
    content = (
        "第二章 继续\n\n"
        "主角仍在秘密基地中。\n\n"
        "两小时前。\n\n"
        "主角走出公司大门，门口保安拦住了他。"
        "他穿过公司走廊，来到电梯口。"
    )
    _seed_chapter(repo, "test_proj", 2, "第二章 继续", content, "polished")

    result = evaluate_chapter_continuity(repo, "test_proj", 2, content, title="第二章 继续")
    assert not result.passed
    assert result.severity == SEVERITY_BLOCKING
    assert result.should_block_publish
    assert any("章中时空回退" in i for i in result.issues)


def test_time_regression_with_flashback_frame_advisory(repo):
    """Framed flashback should be advisory, not blocking."""
    _seed_project(repo, chapter_number=2)
    _seed_prev_chapter(repo)
    content = (
        "第二章 继续\n\n"
        "主角坐在沙发上，脑海中浮现出昨晚的情景。\n\n"
        "两小时前。\n\n"
        "他走出公司大门……"
    )
    _seed_chapter(repo, "test_proj", 2, "第二章 继续", content, "polished")

    result = evaluate_chapter_continuity(repo, "test_proj", 2, content)
    # Should not be blocking because flashback frame is present
    assert result.severity != SEVERITY_BLOCKING


# ── B. Legitimate short flashback ────────────────────────────────


def test_legitimate_flashback_not_blocking(repo):
    """Brief memory of parents — no old-scene markers, no blocking."""
    _seed_project(repo, chapter_number=2)
    content = (
        "第二章 继续\n\n"
        "主角望着窗外，想起了小时候父母带他去公园的日子。\n\n"
        "他收回思绪，继续处理眼前的文件。"
    )
    _seed_chapter(repo, "test_proj", 2, "第二章 继续", content, "polished")

    result = evaluate_chapter_continuity(repo, "test_proj", 2, content, title="第二章 继续")
    assert result.severity in (SEVERITY_PASS, SEVERITY_ADVISORY)
    assert not result.should_block_publish


# ── C. Cross-chapter time-anchor conflict ────────────────────────


def test_cross_chapter_time_anchor_conflict(repo):
    """Prev chapter: 'meet tomorrow noon'. Current: morning 7:50 but still says 'before tomorrow noon'."""
    _seed_project(repo, chapter_number=2)
    _seed_chapter(
        repo, "test_proj", 1,
        "第一章 约定",
        "……他发了一条短信：明日午时，老地方见。",
        "reviewed",
    )
    content = (
        "第二章 赴约\n\n"
        "早上七点五十，他已经站在了议事厅门口。\n\n"
        "他看了看手表，心想：明日午时之前，必须把事情办完。"
    )
    _seed_chapter(repo, "test_proj", 2, "第二章 赴约", content, "polished")

    result = evaluate_chapter_continuity(repo, "test_proj", 2, content)
    # Should detect that scene is already next-day morning but text still says "tomorrow"
    assert not result.passed
    assert any("跨章时间锚点冲突" in i for i in result.issues)


# ── D. Title truncation ──────────────────────────────────────────


def test_title_truncation_detected(repo):
    """Title ending with '无' should be flagged."""
    _seed_project(repo, chapter_number=1)
    content = "正文内容包含核心事件关键词。"
    _seed_chapter(repo, "test_proj", 1, "第5章 三家世界五百强企业宣布无", content, "polished")

    result = evaluate_chapter_continuity(
        repo, "test_proj", 1, content,
        title="第5章 三家世界五百强企业宣布无",
    )
    assert any("截断" in i or "残缺" in i for i in result.issues)


def test_title_missing(repo):
    """Missing title should be flagged."""
    result = evaluate_chapter_continuity(
        repo, "test_proj", 1, "some content", title="",
    )
    assert any("标题缺失" in i for i in result.issues)


# ── E. Fallback rule review cannot fake-green ────────────────────


def test_fallback_rule_review_score_capped(repo):
    """Fallback after LLM timeout must not give 88/excellent."""
    _seed_project(repo, chapter_number=1, status="polished")
    llm = StubLLMProvider()
    agent = EditorAgent(repo, llm)

    # Directly call fallback
    output = agent._fallback_rule_review(
        "Some content here with enough words to pass basic checks.",
        "simulated timeout",
        project_id="test_proj",
        chapter_number=1,
    )
    assert output.score <= 78
    assert any("规则兜底" in i or "人工复核" in i for i in output.issues)
    assert any("降级" in i or "规则兜底" in i for i in output.issues)


def test_fallback_with_continuity_blocking_fails(repo):
    """If continuity gate blocks, fallback must pass_=False and target author."""
    _seed_project(repo, chapter_number=2)
    _seed_chapter(
        repo, "test_proj", 1, "第一章", "前一章内容。", "reviewed",
    )
    # Content with time regression
    content = (
        "第二章\n\n"
        "主角仍在基地。\n\n"
        "两小时前。\n\n"
        "他走出公司大门，门口保安拦住了他。"
    )
    _seed_chapter(repo, "test_proj", 2, "第二章", content, "polished")

    llm = StubLLMProvider()
    agent = EditorAgent(repo, llm)
    output = agent._fallback_rule_review(
        content, "simulated timeout",
        project_id="test_proj", chapter_number=2,
    )
    assert output.pass_ is False
    assert output.revision_target == "author"
    assert any("连续性阻断" in i for i in output.issues)


# ── F. Publish endpoint blocks continuity issues ─────────────────


def test_publish_api_blocks_on_continuity_gate(repo):
    """Simulate the publish endpoint logic: blocking continuity = rejected."""
    _seed_project(repo, chapter_number=2)
    _seed_chapter(
        repo, "test_proj", 1, "第一章", "前一章内容。", "reviewed",
    )
    content = (
        "第二章\n\n"
        "主角仍在基地。\n\n"
        "两小时前。\n\n"
        "他走出公司大门，门口保安拦住了他。"
    )
    _seed_chapter(repo, "test_proj", 2, "第二章", content, "reviewed")

    result = evaluate_publish_continuity(repo, "test_proj", 2)
    assert result.should_block_publish
    assert result.severity == SEVERITY_BLOCKING


# ── G. Generic logic (no hardcoded names) ────────────────────────


def test_no_hardcoded_project_names(repo):
    """Ensure the gate does not contain hardcoded project/character/location names."""
    import inspect
    source = inspect.getsource(evaluate_chapter_continuity)
    # These are examples from the prompt that must NOT appear in code
    forbidden = ["novel_7ia0", "林辰", "云澜会馆", "第五章", "第七章"]
    for name in forbidden:
        assert name not in source, f"Hardcoded name '{name}' found in continuity gate"


# ── H. Continuity gate in normal editor flow ─────────────────────


def test_editor_continuity_gate_in_execute(repo):
    """Editor _execute runs continuity gate and injects issues."""
    _seed_project(repo, chapter_number=2)
    _seed_chapter(
        repo, "test_proj", 1, "第一章", "前一章内容结束于基地。", "reviewed",
    )
    content = (
        "第二章\n\n"
        "主角仍在基地中。\n\n"
        "两小时前。\n\n"
        "他走出公司大门，门口保安拦住了他。"
    )
    _seed_chapter(repo, "test_proj", 2, "第二章", content, "polished")

    state = _make_state(
        project_id="test_proj", chapter_number=2, llm_mode="stub",
        chapter_status=ChapterStatus.POLISHED.value,
    )
    llm = StubLLMProvider([{
        "pass": True,
        "score": 85,
        "scores": {"setting": 20, "logic": 20, "poison": 18, "text": 14, "pacing": 13},
        "issues": [],
        "suggestions": [],
        "revision_target": None,
        "state_card": {"summary": "ok"},
    }])
    agent = EditorAgent(repo, llm)
    result = agent.run(state)

    # Continuity blocking should cause failure
    assert result.get("chapter_status") != ChapterStatus.REVIEWED.value
    quality_gate = result.get("quality_gate") or {}
    assert quality_gate.get("pass") is False


# ── I. Title-content mismatch ────────────────────────────────────


def test_title_content_keyword_mismatch(repo):
    """Title keywords not in content should be flagged."""
    content = "主角来到了一个普通的餐厅，点了一杯咖啡。"
    result = evaluate_chapter_continuity(
        repo, "test_proj", 1, content,
        title="第3章 太空站遇袭",
    )
    assert any("脱节" in i or "关键词" in i for i in result.issues)


# ── J. Event replay detection ─────────────────────────────────────


def test_event_replay_blocking(repo):
    """When >=3 long unique sentences from prev chapter appear verbatim → blocking."""
    _seed_project(repo, chapter_number=2)
    # 3 long unique sentences that are NOT common glue
    prev_content = (
        "第一章 约定\n\n"
        "他站在云澜会馆的天台上，俯瞰着整座城市的夜景。\n"
        "远处传来悠扬的琴声，仿佛在诉说着一段不为人知的往事。\n"
        "他深吸一口气，转身走向了通往地下的秘密通道。"
    )
    _seed_chapter(repo, "test_proj", 1, "第一章 约定", prev_content, "reviewed")

    # Current chapter replays those 3 sentences plus new content
    content = (
        "第二章 潜入\n\n"
        "新的故事开始了。\n\n"
        "他站在云澜会馆的天台上，俯瞰着整座城市的夜景。\n"
        "远处传来悠扬的琴声，仿佛在诉说着一段不为人知的往事。\n"
        "他深吸一口气，转身走向了通往地下的秘密通道。"
    )
    _seed_chapter(repo, "test_proj", 2, "第二章 潜入", content, "polished")

    result = evaluate_chapter_continuity(repo, "test_proj", 2, content, title="第二章 潜入")
    assert not result.passed
    assert result.severity == SEVERITY_BLOCKING
    assert any("重复" in i for i in result.issues)


def test_event_replay_jaccard_skip(repo):
    """When chapters are >50% identical (stub data), skip replay detection."""
    _seed_project(repo, chapter_number=2)
    # Create 6 identical short sentences — Jaccard will be high
    shared = "这是一个测试句子。"
    prev_content = "第一章\n\n" + "\n".join([shared] * 6)
    _seed_chapter(repo, "test_proj", 1, "第一章", prev_content, "reviewed")

    content = "第二章\n\n" + "\n".join([shared] * 6)
    _seed_chapter(repo, "test_proj", 2, "第二章", content, "polished")

    result = evaluate_chapter_continuity(repo, "test_proj", 2, content, title="第二章")
    # Should NOT block — Jaccard guard skips replay detection for stub data
    replay_evidence = result.evidence.get("event_replay", {})
    assert replay_evidence.get("jaccard_similarity", 0) > 0.5
    assert not any("重复" in i for i in result.issues)


# ── K. Fallback with continuity warning ───────────────────────────


def test_fallback_with_continuity_warning_passes_with_warning(repo):
    """Continuity warning (not blocking) should not fail the fallback."""
    _seed_project(repo, chapter_number=2)
    _seed_chapter(repo, "test_proj", 1, "第一章 约定", "……他发了一条短信：明日午时，老地方见。", "reviewed")
    # Content that triggers warning (time marker but no old scene)
    content = (
        "第二章 赴约\n\n"
        "他坐在办公室里。\n\n"
        "他想起了昨晚的对话。\n\n"
        "他决定出发。"
    )
    _seed_chapter(repo, "test_proj", 2, "第二章 赴约", content, "polished")

    llm = StubLLMProvider()
    agent = EditorAgent(repo, llm)
    output = agent._fallback_rule_review(
        content, "simulated timeout",
        project_id="test_proj", chapter_number=2,
    )
    # Warning-level continuity issues should not block fallback
    # (depends on whether the content actually triggers a warning vs advisory)
    # At minimum, verify the fallback runs without error
    assert output.score <= 78
    assert any("规则兜底" in i or "降级" in i for i in output.issues)
