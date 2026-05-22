"""Tests for v6.6.2 Agent Context Inheritance Foundation.

Covers:
1. Planner context includes trusted memory.
2. Planner context does NOT treat state-card fallback as trusted memory.
3. Author context includes hard constraints.
4. Author plain-text fallback includes revision feedback and inheritance context.
5. Screenwriter context includes previous-chapter bridge.
6. Timeline constraints can be extracted from story_facts / plot_holes.
7. Low-confidence memory goes to advisory, NOT trusted_memory.
8. Inheritance check can detect unhandled previous-chapter suspense.
9. Polisher context does not encourage plot-level hard changes.
10. Editor context includes hard_constraints and keeps advisory-only non-blocking.
11. Existing published-chapter local polish logic does NOT regress.
12. Memory fallback / degraded no-op is NOT treated as trusted memory.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.agent_runtime.context_builder import (
    AgentContextBuilder,
    AgentContextBundle,
    ContextItem,
    extract_timeline_constraints,
    format_context_bundle_for_prompt,
    _is_trusted_memory_item,
    _is_untrusted_memory_item,
)
from novel_factory.quality.chapter_inheritance import (
    InheritanceCheckResult,
    validate_chapter_inheritance,
)
from novel_factory.models.state import FactoryState


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test_v662.db"
    init_db(db_path)
    return str(db_path)


@pytest.fixture
def repo(tmp_db):
    return Repository(tmp_db)


@pytest.fixture
def seeded_repo(repo):
    """Seed a project with two chapters and basic data."""
    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        ("test_proj", "Test Novel", "urban"),
    )
    conn.execute(
        "INSERT INTO chapters (project_id, chapter_number, title, status) VALUES (?, ?, ?, ?)",
        ("test_proj", 1, "第一章 测试", "reviewed"),
    )
    conn.execute(
        "INSERT INTO chapters (project_id, chapter_number, title, status) VALUES (?, ?, ?, ?)",
        ("test_proj", 2, "第二章 测试", "planned"),
    )
    conn.execute(
        "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
        "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
        ("test_proj", 2, "测试目标", '["事件1"]', '["P001"]', '[]', "悬念", 2500),
    )
    conn.execute(
        "INSERT INTO characters (project_id, name, role, description, status) "
        "VALUES (?, ?, ?, ?, 'active')",
        ("test_proj", "林默", "protagonist", "主角"),
    )
    conn.commit()
    conn.close()
    return repo


class TestTrustedMemoryFiltering:
    def test_high_confidence_evidence_is_trusted(self):
        item = {
            "confidence": 0.85,
            "evidence_text": "黑影再次约定三天后旧工业区",
            "rationale": "正文复核提取。",
        }
        assert _is_trusted_memory_item(item) is True
        assert _is_untrusted_memory_item(item) is False

    def test_low_confidence_is_untrusted(self):
        item = {
            "confidence": 0.30,
            "evidence_text": "",
            "rationale": "低可信",
        }
        assert _is_trusted_memory_item(item) is False
        assert _is_untrusted_memory_item(item) is True

    def test_fallback_memory_is_untrusted(self):
        item = {
            "confidence": 0.80,
            "evidence_text": "some text",
            "rationale": "状态卡兜底候选：未经过 MemoryCurator LLM 复核",
        }
        assert _is_trusted_memory_item(item) is False
        assert _is_untrusted_memory_item(item) is True

    def test_degraded_no_op_is_untrusted(self):
        item = {
            "confidence": 0.90,
            "evidence_text": "text",
            "rationale": "degraded no-op fallback",
        }
        assert _is_trusted_memory_item(item) is False
        assert _is_untrusted_memory_item(item) is True

    def test_missing_evidence_is_untrusted(self):
        item = {
            "confidence": 0.90,
            "evidence_text": "",
            "rationale": "正常提取",
        }
        assert _is_trusted_memory_item(item) is False
        assert _is_untrusted_memory_item(item) is True


class TestTimelineExtraction:
    def test_extract_from_story_facts(self, seeded_repo):
        seeded_repo.create_story_fact(
            "test_proj",
            "chapter_1.appointment",
            "time_constraint",
            json.dumps({"time": "三天后", "location": "旧工业区"}, ensure_ascii=False),
            subject="黑影邀约",
            attribute="会面时间地点",
            source_chapter=1,
            source_agent="memory_curator",
        )
        items = extract_timeline_constraints("test_proj", 2, seeded_repo)
        texts = [it.text for it in items]
        assert any("三天后" in t for t in texts)

    def test_extract_from_plot_holes(self, seeded_repo):
        seeded_repo.create_plot_hole(
            "test_proj",
            code="P001",
            title="旧址会面与72小时访客",
            description="黑影约定72小时后旧工业区见面",
            planted_chapter=1,
            status="planted",
        )
        items = extract_timeline_constraints("test_proj", 2, seeded_repo)
        texts = [it.text for it in items]
        assert any("72小时" in t for t in texts)

    def test_extract_from_prev_state_card(self, seeded_repo):
        seeded_repo.save_chapter_state(
            "test_proj",
            1,
            {"suspense_hooks": ["三天后旧工业区的约定", "林默的伤势"]},
            "第1章状态卡",
        )
        items = extract_timeline_constraints("test_proj", 2, seeded_repo)
        texts = [it.text for it in items]
        assert any("三天后" in t for t in texts)


class TestPlannerContext:
    def test_planner_context_includes_trusted_memory(self, seeded_repo):
        from novel_factory.agents.planner import PlannerAgent
        from novel_factory.llm.provider import LLMProvider

        class DummyLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {}
            def invoke_text(self, messages, temperature=None, max_tokens=None):
                return ""

        # Seed trusted memory batch for chapter 1
        batch = seeded_repo.create_memory_batch("test_proj", chapter_number=1, summary="第1章记忆提取 (1项)")
        seeded_repo.create_memory_item(
            batch_id=batch["id"],
            project_id="test_proj",
            target_table="plot_holes",
            operation="update",
            after_json=json.dumps({"code": "PH-014", "title": "旧址会面"}, ensure_ascii=False),
            confidence=0.94,
            evidence_text="黑影再次约定三天后旧工业区",
            rationale="正文复核提取。",
        )

        agent = PlannerAgent(seeded_repo, DummyLLM())
        context = agent.build_context({
            "project_id": "test_proj",
            "chapter_number": 2,
            "chapter_status": "planned",
        })

        assert "旧址会面" in context  # title from trusted memory item
        assert "可信记忆" in context or "Trusted Memory" in context

    def test_planner_context_excludes_state_card_fallback(self, seeded_repo):
        from novel_factory.agents.planner import PlannerAgent
        from novel_factory.llm.provider import LLMProvider

        class DummyLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {}
            def invoke_text(self, messages, temperature=None, max_tokens=None):
                return ""

        fallback = seeded_repo.create_memory_batch("test_proj", chapter_number=1, summary="第1章记忆提取 - 状态卡兜底 (1项)")
        seeded_repo.create_memory_item(
            batch_id=fallback["id"],
            project_id="test_proj",
            target_table="story_facts",
            operation="create",
            after_json=json.dumps({"fact_key": "fallback"}, ensure_ascii=False),
            confidence=0.45,
            evidence_text="低可信",
            rationale="状态卡兜底候选：未经过 MemoryCurator LLM 复核，请人工确认后应用。",
        )

        agent = PlannerAgent(seeded_repo, DummyLLM())
        context = agent.build_context({
            "project_id": "test_proj",
            "chapter_number": 2,
            "chapter_status": "planned",
        })

        assert "状态卡兜底" not in context
        assert "fallback" not in context.lower()

    def test_medium_confidence_memory_enters_advisory_without_trusted_batch(self, seeded_repo):
        batch = seeded_repo.create_memory_batch("test_proj", chapter_number=1, summary="第1章记忆提取 (1项)")
        seeded_repo.create_memory_item(
            batch_id=batch["id"],
            project_id="test_proj",
            target_table="story_facts",
            operation="create",
            after_json=json.dumps({"fact_key": "maybe.true", "title": "疑似线索"}, ensure_ascii=False),
            confidence=0.60,
            evidence_text="疑似出现一个低置信线索",
            rationale="正文复核但证据不足。",
        )

        builder = AgentContextBuilder(seeded_repo)
        bundle = builder.build_for_planner("test_proj", 2, None)

        assert bundle.trusted_memory == []
        assert any("疑似线索" in item.text for item in bundle.advisory_context)

    def test_planner_inheritance_check_warns_on_unhandled_suspense(self, seeded_repo):
        from novel_factory.agents.planner import PlannerAgent
        from novel_factory.llm.provider import LLMProvider

        class DummyLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {
                    "chapter_brief": {
                        "objective": "林默去新公司报到",
                        "required_events": ["报到"],
                        "plots_to_plant": [],
                        "plots_to_resolve": [],
                        "ending_hook": "悬念",
                        "constraints": [],
                    }
                }
            def invoke_text(self, messages, temperature=None, max_tokens=None):
                return ""

        seeded_repo.save_chapter_content("test_proj", 1, "黑影抬起左手：'三天后，旧工业区。'", "第一章 测试")
        seeded_repo.save_chapter_state(
            "test_proj", 1,
            {"suspense_hooks": ["三天后旧工业区的约定"]},
            "第1章状态卡",
        )

        agent = PlannerAgent(seeded_repo, DummyLLM())
        result = agent.run({
            "project_id": "test_proj",
            "chapter_number": 2,
            "chapter_status": "planned",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        })

        events = result.get("_exec_events", [])
        assert any(
            ev.get("event_type") == "planner_inheritance_check"
            for ev in events
        )


class TestAuthorContext:
    def test_author_context_includes_hard_constraints(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent
        from novel_factory.llm.provider import LLMProvider

        class DummyLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {}
            def invoke_text(self, messages, temperature=None, max_tokens=None):
                return ""

        seeded_repo.save_chapter_state(
            "test_proj", 1,
            {"suspense_hooks": ["三天后旧工业区的约定"]},
            "第1章状态卡",
        )

        agent = AuthorAgent(seeded_repo, DummyLLM())
        context = agent.build_context({
            "project_id": "test_proj",
            "chapter_number": 2,
            "chapter_status": "scripted",
        })

        assert "不可违背事实" in context or "Hard Constraints" in context
        assert "三天后" in context

    def test_author_plain_text_fallback_includes_revision_feedback(self, seeded_repo):
        from novel_factory.agents.author import AuthorAgent
        from novel_factory.llm.provider import LLMProvider

        class DummyLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {}
            def invoke_text(self, messages, temperature=None, max_tokens=None):
                return ""

        # Create a review for chapter 2
        conn = seeded_repo._conn()
        conn.execute(
            "INSERT INTO reviews (project_id, chapter_id, pass, score, setting_score, logic_score, poison_score, text_score, pacing_score, issues, suggestions, summary, revision_target) "
            "VALUES (?, ?, 0, 70, 15, 15, 12, 14, 14, ?, ?, ?, 'author')",
            ("test_proj", 2, '["字数不足"]', '["扩写到3000字"]', "issues=1, suggestions=1"),
        )
        conn.commit()
        conn.close()

        agent = AuthorAgent(seeded_repo, DummyLLM())
        state: FactoryState = {
            "project_id": "test_proj",
            "chapter_number": 2,
            "chapter_status": "revision",
            "_revision_review": {
                "review_id": "r1",
                "score": 70,
                "revision_target": "author",
                "issues": ["字数不足"],
                "suggestions": ["扩写到3000字"],
            },
        }
        context = agent._build_plain_text_context(state, "fallback")

        assert "返修" in context or "revision" in context.lower() or "退回问题" in context


class TestScreenwriterContext:
    def test_screenwriter_context_includes_prev_chapter_bridge(self, seeded_repo):
        from novel_factory.agents.screenwriter import ScreenwriterAgent
        from novel_factory.llm.provider import LLMProvider

        class DummyLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {}
            def invoke_text(self, messages, temperature=None, max_tokens=None):
                return ""

        seeded_repo.save_chapter_content("test_proj", 1, "林默站在旧工业区门口，等待黑影出现。", "第一章 测试")
        seeded_repo.save_chapter_state(
            "test_proj", 1,
            {"suspense_hooks": ["黑影身份不明"]},
            "第1章状态卡",
        )

        agent = ScreenwriterAgent(seeded_repo, DummyLLM())
        context = agent.build_context({
            "project_id": "test_proj",
            "chapter_number": 2,
            "chapter_status": "planned",
        })

        assert "上一章" in context
        assert "旧工业区" in context or "黑影" in context


class TestPolisherContext:
    def test_polisher_context_does_not_encourage_plot_changes(self, seeded_repo):
        from novel_factory.agents.polisher import PolisherAgent
        from novel_factory.llm.provider import LLMProvider

        class DummyLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {}
            def invoke_text(self, messages, temperature=None, max_tokens=None):
                return ""

        agent = PolisherAgent(seeded_repo, DummyLLM())
        context = agent.build_context({
            "project_id": "test_proj",
            "chapter_number": 2,
            "chapter_status": "drafted",
        })

        assert "不要主动大改剧情结构" in context or "不要硬改" in context


class TestEditorContext:
    def test_editor_context_includes_hard_constraints(self, seeded_repo):
        from novel_factory.agents.editor import EditorAgent
        from novel_factory.llm.provider import LLMProvider

        class DummyLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {}
            def invoke_text(self, messages, temperature=None, max_tokens=None):
                return ""

        seeded_repo.save_chapter_state(
            "test_proj", 1,
            {"suspense_hooks": ["三天后旧工业区的约定"]},
            "第1章状态卡",
        )

        agent = EditorAgent(seeded_repo, DummyLLM())
        context = agent.build_context({
            "project_id": "test_proj",
            "chapter_number": 2,
            "chapter_status": "polished",
        })

        assert "不可违背事实" in context or "Hard Constraints" in context


class TestInheritanceCheck:
    def test_detects_unhandled_suspense(self):
        prev_state = {
            "state_data": {
                "suspense_hooks": ["三天后旧工业区的约定"],
            }
        }
        bundle = AgentContextBundle()
        bundle.hard_constraints = [
            ContextItem(kind="suspense_hook", text="三天后旧工业区的约定", priority=1, trusted=True),
        ]
        result = validate_chapter_inheritance(
            prev_state,
            bundle,
            {"objective": "林默去新公司报到", "required_events": ["报到"], "content": "林默走进新公司大门。"},
        )
        assert result.passed is True  # First version is advisory-only
        assert any("三天后" in w for w in result.warnings)

    def test_advisory_when_plots_not_referenced(self):
        prev_state = None
        bundle = AgentContextBundle()
        bundle.plot_obligations = [
            ContextItem(kind="plot_obligation", text="埋设伏笔: [P001] 旧工业区", priority=1, trusted=True),
            ContextItem(kind="plot_obligation", text="埋设伏笔: [P002] 黑影身份", priority=1, trusted=True),
        ]
        result = validate_chapter_inheritance(
            prev_state,
            bundle,
            {"content": "林默走进新公司大门。"},
        )
        assert any("伏笔" in a for a in result.advisory_issues)


class TestFormatContextBundle:
    def test_priority_truncation_drops_low_priority(self):
        bundle = AgentContextBundle()
        bundle.hard_constraints = [ContextItem(kind="hard", text="H1", priority=1, trusted=True)]
        bundle.advisory_context = [ContextItem(kind="advisory", text="A1" * 5000, priority=8, trusted=False)]
        bundle.project_context = [ContextItem(kind="project", text="P1" * 5000, priority=10, trusted=True)]

        result = format_context_bundle_for_prompt(bundle, "test", max_chars=3000)
        assert "H1" in result
        assert "不可违背事实" in result
        # Low priority should be truncated or omitted
        assert len(result) <= 3200


class TestPublishedChapterPolishRegression:
    def test_published_chapter_local_polish_logic_not_regressed(self, seeded_repo):
        """Ensure that context builder does not break when chapter is already published."""
        from novel_factory.agents.polisher import PolisherAgent
        from novel_factory.llm.provider import LLMProvider

        class DummyLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {}
            def invoke_text(self, messages, temperature=None, max_tokens=None):
                return ""

        conn = seeded_repo._conn()
        conn.execute(
            "UPDATE chapters SET status = 'published' WHERE project_id = ? AND chapter_number = ?",
            ("test_proj", 1),
        )
        conn.commit()
        conn.close()

        agent = PolisherAgent(seeded_repo, DummyLLM())
        # Should not raise even for published chapter
        context = agent.build_context({
            "project_id": "test_proj",
            "chapter_number": 1,
            "chapter_status": "published",
        })
        assert isinstance(context, str)
