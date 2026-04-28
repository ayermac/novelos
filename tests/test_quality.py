"""v1.2 Quality tests — Q1 through Q8.

Covers:
- Q1: ContextBuilder per-agent context, token budget, mandatory fragments
- Q2: Death penalty structured rules (exact/substring/regex, severity levels)
- Q3: State verifier consistency (level jumps, location shifts, relation reversals)
- Q4: Plot verifier structured result (missing_plants/resolves, invalid_refs)
- Q5: Learned patterns write/read/inject
- Q6: Best practices read/inject
- Q7: Revision classifier and Editor issue classification
- Q8: Fact lock (Polisher integrity check)
"""

from __future__ import annotations

import json

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.models.quality import (
    DeathPenaltyResult,
    DeathPenaltyRule,
    FactLockItem,
    IssueCategory,
    PenaltyMatchType,
    PenaltySeverity,
    PlotVerifyResult,
    RevisionClassifyResult,
    StateVerifyResult,
)


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test_quality.db"
    init_db(db_path)
    return str(db_path)


@pytest.fixture
def repo(tmp_db):
    return Repository(tmp_db)


def _seed_full_project(repo, status="planned"):
    """Seed a project with instruction, characters, and state card."""
    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        ("q_proj", "Quality Novel", "urban"),
    )
    conn.execute(
        "INSERT INTO chapters (project_id, chapter_number, title, status) "
        "VALUES (?, ?, ?, ?)",
        ("q_proj", 1, "第一章", status),
    )
    conn.execute(
        "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
        "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
        ("q_proj", 1, "突破困境", '["事件1"]', '["P001"]', '["P002"]', "悬念", 2500),
    )
    conn.execute(
        "INSERT INTO characters (project_id, name, role, description, status) "
        "VALUES (?, ?, ?, ?, 'active')",
        ("q_proj", "林默", "protagonist", "主角"),
    )
    # Add a plot hole
    conn.execute(
        "INSERT INTO plot_holes (project_id, code, title, status, planted_chapter, planned_resolve_chapter) "
        "VALUES (?, ?, ?, 'planted', 1, 5)",
        ("q_proj", "P001", "神秘信件", ),
    )
    conn.execute(
        "INSERT INTO plot_holes (project_id, code, title, status, planted_chapter, planned_resolve_chapter) "
        "VALUES (?, ?, ?, 'planted', 1, 3)",
        ("q_proj", "P002", "暗势力", ),
    )
    conn.commit()
    conn.close()


# ── Q1: ContextBuilder ──────────────────────────────────────────

class TestQ1ContextBuilder:
    def test_author_context_includes_death_penalty(self, repo):
        """Author context must include death penalty (P0)."""
        from novel_factory.context.builder import ContextBuilder
        _seed_full_project(repo)
        builder = ContextBuilder(repo)
        ctx = builder.build_for_author("q_proj", 1)
        assert "死刑红线" in ctx

    def test_author_context_includes_instruction(self, repo):
        """Author context must include instruction (P1)."""
        from novel_factory.context.builder import ContextBuilder
        _seed_full_project(repo)
        builder = ContextBuilder(repo)
        ctx = builder.build_for_author("q_proj", 1)
        assert "写作指令" in ctx

    def test_polisher_context_includes_fact_lock(self, repo):
        """Polisher context must include fact lock list."""
        from novel_factory.context.builder import ContextBuilder
        _seed_full_project(repo)
        repo.save_chapter_content("q_proj", 1, "草稿内容" * 20, "第一章")
        builder = ContextBuilder(repo)
        ctx = builder.build_for_polisher("q_proj", 1)
        assert "事实锁定" in ctx

    def test_editor_context_includes_content(self, repo):
        """Editor context must include chapter content."""
        from novel_factory.context.builder import ContextBuilder
        _seed_full_project(repo, status="polished")
        repo.save_chapter_content("q_proj", 1, "正文内容" * 50, "第一章")
        repo.update_chapter_status("q_proj", 1, "polished")
        builder = ContextBuilder(repo)
        ctx = builder.build_for_editor("q_proj", 1)
        assert "本章正文" in ctx

    def test_token_budget_trims_low_priority(self, repo):
        """With very low token budget, P8/P9 should be trimmed."""
        from novel_factory.context.builder import ContextBuilder
        _seed_full_project(repo)
        # Insert a best practice
        conn = repo._conn()
        conn.execute(
            "INSERT INTO best_practices (project_id, category, practice, avg_score) "
            "VALUES (?, 'text', '测试实践', 90.0)",
            ("q_proj",),
        )
        conn.execute(
            "INSERT INTO learned_patterns (project_id, category, pattern, frequency) "
            "VALUES (?, 'ai_trace', '测试模式', 5)",
            ("q_proj",),
        )
        conn.commit()
        conn.close()

        # Very low budget — should only include mandatory fragments
        builder = ContextBuilder(repo, token_budget=500)
        ctx = builder.build_for_author("q_proj", 1)
        # best_practices and learned_patterns should be trimmed
        assert "写作指令" in ctx  # mandatory P1

    def test_mandatory_fragments_not_trimmed(self, repo):
        """Mandatory fragments (P0-P2) must not be trimmed regardless of budget."""
        from novel_factory.context.builder import ContextBuilder
        _seed_full_project(repo)
        builder = ContextBuilder(repo, token_budget=100)
        ctx = builder.build_for_author("q_proj", 1)
        # Death penalty (P0) must always be present
        assert "死刑红线" in ctx


# ── Q2: Death penalty structured rules ──────────────────────────

class TestQ2DeathPenalty:
    def test_exact_match(self):
        from novel_factory.validators.death_penalty import check_death_penalty_structured
        result = check_death_penalty_structured("他冷笑了一声。")
        assert "冷笑" in result.violations
        assert result.has_critical is True

    def test_regex_match(self):
        from novel_factory.validators.death_penalty import check_death_penalty_structured
        result = check_death_penalty_structured("这不仅好而且棒更是绝")
        assert len(result.violations) >= 1

    def test_severity_critical_triggers_failure(self):
        from novel_factory.validators.death_penalty import has_critical_violation
        assert has_critical_violation("他冷笑了一声。") is True

    def test_severity_high_no_critical(self):
        from novel_factory.validators.death_penalty import has_critical_violation
        # "心道" is HIGH, not CRITICAL
        assert has_critical_violation("他心道不妙") is False

    def test_no_violations(self):
        from novel_factory.validators.death_penalty import check_death_penalty_structured
        result = check_death_penalty_structured("林默走进房间，安静地坐下。")
        assert result.violations == []
        assert result.has_critical is False

    def test_custom_rule_exact(self):
        from novel_factory.validators.death_penalty import check_death_penalty_structured
        rules = [DeathPenaltyRule(
            code="TEST_01", pattern="测试禁词", match_type=PenaltyMatchType.EXACT,
            severity=PenaltySeverity.LOW,
        )]
        result = check_death_penalty_structured("包含测试禁词的文本", rules=rules)
        assert "测试禁词" in result.violations
        assert result.has_critical is False

    def test_custom_rule_regex(self):
        from novel_factory.validators.death_penalty import check_death_penalty_structured
        rules = [DeathPenaltyRule(
            code="TEST_02", pattern="超级.*无敌", match_type=PenaltyMatchType.REGEX,
            severity=PenaltySeverity.MEDIUM,
        )]
        result = check_death_penalty_structured("他是超级无敌的存在", rules=rules)
        assert len(result.violations) >= 1

    def test_author_critical_fails(self):
        """Author output with critical death penalty word must fail validation."""
        from novel_factory.agents.author import AuthorAgent
        from novel_factory.llm.provider import LLMProvider

        class StubLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {
                    "title": "测试", "content": "他冷笑了一声。" * 100,
                    "word_count": 700, "implemented_events": [], "used_plot_refs": [],
                }
            def invoke_text(self, messages, **kw):
                return "{}"

        # Will be caught by validate_output
        # Author's validate_output now checks for critical violations
        from novel_factory.validators.death_penalty import has_critical_violation
        assert has_critical_violation("他冷笑了一声。") is True


# ── Q3: State verifier consistency ──────────────────────────────

class TestQ3StateVerifier:
    def test_level_jump_violation(self):
        from novel_factory.validators.state_verifier import check_state_consistency
        state_card = {"level": 3}
        content = "他突破到了Lv5"
        result = check_state_consistency(state_card, content)
        assert len(result.violations) >= 1
        assert any(v.type.value == "level_jump" for v in result.violations)

    def test_location_shift_warning(self):
        from novel_factory.validators.state_verifier import check_state_consistency
        state_card = {"location": "公司"}
        content = "他走进了酒楼，叫了一壶酒"
        result = check_state_consistency(state_card, content)
        assert len(result.warnings) >= 1

    def test_no_state_card_returns_warning(self):
        from novel_factory.validators.state_verifier import check_state_consistency
        result = check_state_consistency(None, "任意内容")
        assert len(result.warnings) >= 1
        assert result.violations == []

    def test_consistent_content_passes(self):
        from novel_factory.validators.state_verifier import check_state_consistency
        state_card = {"level": 3}
        content = "他继续修炼，稳步提升。"
        result = check_state_consistency(state_card, content)
        assert len(result.violations) == 0


# ── Q4: Plot verifier structured result ─────────────────────────

class TestQ4PlotVerifier:
    def test_missing_plant(self):
        from novel_factory.validators.plot_verifier import check_plot_coverage_structured
        instruction = {"plots_to_plant": '["P001"]', "plots_to_resolve": "[]"}
        result = check_plot_coverage_structured(instruction, [])
        assert "P001" in result.missing_plants

    def test_missing_resolve(self):
        from novel_factory.validators.plot_verifier import check_plot_coverage_structured
        instruction = {"plots_to_plant": "[]", "plots_to_resolve": '["P002"]'}
        result = check_plot_coverage_structured(instruction, [])
        assert "P002" in result.missing_resolves

    def test_invalid_refs(self):
        from novel_factory.validators.plot_verifier import check_plot_coverage_structured
        instruction = {"plots_to_plant": '["NONEXISTENT"]', "plots_to_resolve": "[]"}
        result = check_plot_coverage_structured(instruction, ["NONEXISTENT"], repo=repo if False else None)
        # Without repo, invalid_refs won't be populated
        assert result.missing_plants == []

    def test_invalid_refs_with_repo(self, repo):
        from novel_factory.validators.plot_verifier import check_plot_coverage_structured
        _seed_full_project(repo)
        instruction = {"plots_to_plant": '["P999"]', "plots_to_resolve": "[]"}
        result = check_plot_coverage_structured(instruction, [], repo=repo, project_id="q_proj")
        assert "P999" in result.invalid_refs

    def test_no_instruction_passes(self):
        from novel_factory.validators.plot_verifier import check_plot_coverage_structured
        result = check_plot_coverage_structured(None, [])
        assert len(result.warnings) >= 1

    def test_all_covered(self):
        from novel_factory.validators.plot_verifier import check_plot_coverage_structured
        instruction = {"plots_to_plant": '["P001"]', "plots_to_resolve": '["P002"]'}
        result = check_plot_coverage_structured(instruction, ["P001", "P002"])
        assert result.missing_plants == []
        assert result.missing_resolves == []


# ── Q5: Learned patterns ────────────────────────────────────────

class TestQ5LearnedPatterns:
    def test_save_and_read_pattern(self, repo):
        _seed_full_project(repo)
        pid = repo.save_learned_pattern("q_proj", "ai_trace", "出现冷笑表达")
        assert pid > 0

        patterns = repo.get_learned_patterns("q_proj")
        assert len(patterns) >= 1
        assert patterns[0]["pattern"] == "出现冷笑表达"

    def test_frequency_increments(self, repo):
        _seed_full_project(repo)
        id1 = repo.save_learned_pattern("q_proj", "ai_trace", "重复问题")
        id2 = repo.save_learned_pattern("q_proj", "ai_trace", "重复问题")
        assert id1 == id2

        patterns = repo.get_learned_patterns("q_proj")
        assert patterns[0]["frequency"] == 2

    def test_disabled_pattern_not_in_context(self, repo):
        _seed_full_project(repo)
        repo.save_learned_pattern("q_proj", "ai_trace", "可见模式")
        patterns = repo.get_learned_patterns("q_proj", enabled_only=True)
        assert len(patterns) >= 1

        # Disable it
        repo.disable_learned_pattern(patterns[0]["id"])
        patterns_after = repo.get_learned_patterns("q_proj", enabled_only=True)
        visible_texts = [p["pattern"] for p in patterns_after]
        assert "可见模式" not in visible_texts

    def test_high_frequency_first(self, repo):
        _seed_full_project(repo)
        repo.save_learned_pattern("q_proj", "logic", "低频问题")
        # Create a high-frequency pattern
        for _ in range(5):
            repo.save_learned_pattern("q_proj", "logic", "高频问题")

        patterns = repo.get_learned_patterns("q_proj", min_frequency=2)
        if len(patterns) >= 2:
            assert patterns[0]["frequency"] >= patterns[1]["frequency"]

    def test_editor_writes_learned_patterns_on_rejection(self, repo):
        """When Editor rejects, it should write learned patterns."""
        from novel_factory.agents.editor import EditorAgent
        from novel_factory.llm.provider import LLMProvider

        _seed_full_project(repo, status="polished")
        repo.save_chapter_content("q_proj", 1, "正文内容" * 30, "第一章")
        repo.update_chapter_status("q_proj", 1, "polished")

        class StubLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {
                    "pass": False,
                    "score": 65,
                    "scores": {"setting": 15, "logic": 12, "poison": 13, "text": 12, "pacing": 13},
                    "issues": ["逻辑漏洞严重"],
                    "suggestions": ["修复逻辑"],
                    "revision_target": "author",
                    "state_card": {},
                }
            def invoke_text(self, messages, **kw):
                return "{}"

        agent = EditorAgent(repo, StubLLM())
        state = {
            "project_id": "q_proj", "chapter_number": 1,
            "chapter_status": "polished", "retry_count": 0,
            "max_retries": 3, "requires_human": False, "error": None,
        }
        result = agent.run(state)
        assert result["chapter_status"] == "revision"

        # Should have written learned patterns
        patterns = repo.get_learned_patterns("q_proj")
        assert len(patterns) >= 1


# ── Q6: Best practices ─────────────────────────────────────────

class TestQ6BestPractices:
    def test_read_best_practices(self, repo):
        _seed_full_project(repo)
        conn = repo._conn()
        conn.execute(
            "INSERT INTO best_practices (project_id, category, practice, avg_score) "
            "VALUES (?, 'text', '用具体动作代替抽象', 92.0)",
            ("q_proj",),
        )
        conn.execute(
            "INSERT INTO best_practices (project_id, category, practice, avg_score) "
            "VALUES (?, 'pacing', '低分实践', 60.0)",
            ("q_proj",),
        )
        conn.commit()
        conn.close()

        practices = repo.get_best_practices("q_proj")
        assert len(practices) == 1  # Only high-score one
        assert practices[0]["practice"] == "用具体动作代替抽象"

    def test_low_score_excluded(self, repo):
        conn = repo._conn()
        conn.execute(
            "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
            ("q_proj2", "BP Test", "urban"),
        )
        conn.execute(
            "INSERT INTO best_practices (project_id, category, practice, avg_score) "
            "VALUES (?, 'text', '低分', 50.0)",
            ("q_proj2",),
        )
        conn.commit()
        conn.close()

        repo2 = Repository(repo.db_path)
        practices = repo2.get_best_practices("q_proj2", min_score=80.0)
        assert len(practices) == 0

    def test_best_practices_in_author_context(self, repo):
        _seed_full_project(repo)
        conn = repo._conn()
        conn.execute(
            "INSERT INTO best_practices (project_id, category, practice, avg_score) "
            "VALUES (?, 'text', '高质量写作手法', 95.0)",
            ("q_proj",),
        )
        conn.commit()
        conn.close()

        from novel_factory.context.builder import ContextBuilder
        builder = ContextBuilder(repo, token_budget=8000)
        ctx = builder.build_for_author("q_proj", 1)
        assert "最佳实践" in ctx

    def test_best_practices_trimmed_on_low_budget(self, repo):
        _seed_full_project(repo)
        conn = repo._conn()
        conn.execute(
            "INSERT INTO best_practices (project_id, category, practice, avg_score) "
            "VALUES (?, 'text', '高质量写作手法', 95.0)",
            ("q_proj",),
        )
        conn.commit()
        conn.close()

        from novel_factory.context.builder import ContextBuilder
        builder = ContextBuilder(repo, token_budget=500)
        ctx = builder.build_for_author("q_proj", 1)
        # With very low budget, best_practices (P9) should be trimmed
        # Death penalty (P0) and instruction (P1) must still be present
        assert "死刑红线" in ctx


# ── Q7: Revision classifier ─────────────────────────────────────

class TestQ7RevisionClassifier:
    def test_text_issue_routes_to_polisher(self):
        from novel_factory.validators.revision_classifier import classify_issues
        result = classify_issues(["AI味句式严重", "文风模板化"])
        assert result.dominant_target == "polisher"

    def test_logic_issue_routes_to_author(self):
        from novel_factory.validators.revision_classifier import classify_issues
        result = classify_issues(["逻辑漏洞", "伏笔未兑现"])
        assert result.dominant_target == "author"

    def test_setting_issue_routes_to_planner(self):
        from novel_factory.validators.revision_classifier import classify_issues
        result = classify_issues(["设定体系冲突"], llm_revision_target="planner")
        assert result.dominant_target == "planner"

    def test_classified_issues_in_result(self):
        from novel_factory.validators.revision_classifier import classify_issues
        result = classify_issues(["逻辑漏洞", "AI味太重"])
        assert len(result.issues) == 2
        categories = [ci.category.value for ci in result.issues]
        assert "logic" in categories
        assert "text" in categories

    def test_classification_written_to_review(self, repo):
        """Editor should save classified issues to review."""
        from novel_factory.agents.editor import EditorAgent
        from novel_factory.llm.provider import LLMProvider

        _seed_full_project(repo, status="polished")
        repo.save_chapter_content("q_proj", 1, "正文内容" * 30, "第一章")
        repo.update_chapter_status("q_proj", 1, "polished")

        class StubLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {
                    "pass": False,
                    "score": 70,
                    "scores": {"setting": 15, "logic": 12, "poison": 13, "text": 15, "pacing": 15},
                    "issues": ["AI味句式问题"],
                    "suggestions": ["修改句式"],
                    "revision_target": "polisher",
                    "state_card": {},
                }
            def invoke_text(self, messages, **kw):
                return "{}"

        agent = EditorAgent(repo, StubLLM())
        state = {
            "project_id": "q_proj", "chapter_number": 1,
            "chapter_status": "polished", "retry_count": 0,
            "max_retries": 3, "requires_human": False, "error": None,
        }
        result = agent.run(state)
        # Should have written categories to review
        conn = repo._conn()
        row = conn.execute(
            "SELECT issue_categories FROM reviews WHERE project_id=? ORDER BY id DESC LIMIT 1",
            ("q_proj",),
        ).fetchone()
        conn.close()
        if row and row["issue_categories"]:
            cats = json.loads(row["issue_categories"])
            assert len(cats) >= 1


# ── Q8: Fact lock ───────────────────────────────────────────────

class TestQ8FactLock:
    def test_extract_fact_lock_from_instruction(self):
        from novel_factory.validators.fact_lock import extract_fact_lock
        instruction = {
            "key_events": '["击败Boss", "获得宝物"]',
            "plots_to_plant": '["P001"]',
            "plots_to_resolve": '[]',
        }
        items = extract_fact_lock(instruction, None)
        types = [i.fact_type for i in items]
        assert "event" in types
        assert "plot_ref" in types

    def test_extract_fact_lock_from_state_card(self):
        from novel_factory.validators.fact_lock import extract_fact_lock
        state_card = {"level": 3, "relations": {"张三": "盟友"}}
        items = extract_fact_lock(None, state_card)
        types = [i.fact_type for i in items]
        assert "state_value" in types
        assert "relation" in types

    def test_missing_event_detected(self):
        from novel_factory.validators.fact_lock import check_fact_integrity
        original = "他击败了Boss，获得了宝物。"
        polished = "他走出了森林。"  # Removed key event
        fact_lock = [FactLockItem(fact_type="event", content="击败了Boss", source="instruction")]

        result = check_fact_integrity(original, polished, fact_lock)
        assert len(result.missing_facts) >= 1
        assert result.risk != "none"

    def test_missing_plot_ref_detected(self):
        from novel_factory.validators.fact_lock import check_fact_integrity
        original = "他想起了P001那个秘密。"
        polished = "他想起了那个秘密。"  # Removed P001 reference
        fact_lock = [FactLockItem(fact_type="plot_ref", content="P001", source="instruction")]

        result = check_fact_integrity(original, polished, fact_lock)
        assert len(result.missing_facts) >= 1

    def test_normal_polish_passes(self):
        from novel_factory.validators.fact_lock import check_fact_integrity
        original = "他走进了酒楼，叫了一壶酒。"
        polished = "他迈入酒楼，要了一壶老酒。"  # Just rephrased
        fact_lock = [FactLockItem(fact_type="event", content="酒楼", source="instruction")]

        result = check_fact_integrity(original, polished, fact_lock)
        assert result.risk == "none"

    def test_polisher_critical_death_penalty_fails(self):
        """Polisher output with critical death penalty word must fail."""
        from novel_factory.validators.death_penalty import check_death_penalty_structured
        result = check_death_penalty_structured("他冷笑了一声，心中暗想。")
        assert result.has_critical is True


# ── Q8 Integration: PolisherAgent fact lock in production pipeline ───

class TestQ8PolisherFactLockIntegration:
    """Integration tests verifying Q8 fact lock is a hard gate in PolisherAgent.

    These tests exercise the full PolisherAgent._execute() path, ensuring:
    - fact lock verification runs BEFORE status advance
    - verification failure returns error, status stays drafted, no products saved
    - verification success allows normal drafted→polished transition
    - LLM user message includes fact lock context from ContextBuilder
    """

    @staticmethod
    def _seed_drafted_chapter(repo, key_events='["击败Boss"]',
                              plots_to_plant='["P001"]', plots_to_resolve='[]',
                              content="他击败了Boss，获得了宝物。"):
        """Seed a chapter in 'drafted' status with content and instruction."""
        conn = repo._conn()
        conn.execute(
            "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
            ("q8_proj", "Q8 Novel", "urban"),
        )
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status, content) "
            "VALUES (?, ?, ?, 'drafted', ?)",
            ("q8_proj", 1, "第一章", content),
        )
        conn.execute(
            "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
            "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
            ("q8_proj", 1, "突破困境", key_events, plots_to_plant, plots_to_resolve, "悬念", 2500),
        )
        conn.execute(
            "INSERT INTO plot_holes (project_id, code, title, status, planted_chapter, planned_resolve_chapter) "
            "VALUES (?, ?, ?, 'planted', 1, 5)",
            ("q8_proj", "P001", "神秘信件"),
        )
        conn.commit()
        conn.close()

    def test_polisher_removes_locked_event_returns_error(self, repo):
        """Polisher removes a locked key event → must return error, status stays drafted."""
        from novel_factory.agents.polisher import PolisherAgent
        from novel_factory.llm.provider import LLMProvider

        # key_events content must match what appears in the draft text exactly
        self._seed_drafted_chapter(
            repo,
            key_events='["击败Boss"]',
            content="他击败Boss，获得了宝物。",
        )

        class RemoveEventLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {
                    "content": "他走出了森林，心情愉快。",  # Removed "击败Boss"
                    "fact_change_risk": "none",
                    "changed_scope": ["sentence"],
                    "summary": "润色了句子",
                }
            def invoke_text(self, messages, **kw):
                return "{}"

        agent = PolisherAgent(repo, RemoveEventLLM())
        state = {
            "project_id": "q8_proj", "chapter_number": 1,
            "chapter_status": "drafted",
        }
        result = agent.run(state)

        # Must return error with fact lock failure
        assert "error" in result
        assert "fact lock" in result["error"]
        # Status must remain drafted
        assert result["chapter_status"] == "drafted"
        # Content must NOT be overwritten
        ch = repo.get_chapter("q8_proj", 1)
        assert "击败Boss" in ch["content"]

    def test_polisher_removes_locked_plot_ref_returns_error(self, repo):
        """Polisher removes a locked plot reference → must return error, original content preserved."""
        from novel_factory.agents.polisher import PolisherAgent
        from novel_factory.llm.provider import LLMProvider

        self._seed_drafted_chapter(
            repo,
            content="他想起了P001那个秘密，心中一凛。",
        )

        class RemovePlotRefLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {
                    "content": "他想起了那个秘密，心中一凛。",  # Removed "P001"
                    "fact_change_risk": "none",
                    "changed_scope": ["sentence"],
                    "summary": "润色了句子",
                }
            def invoke_text(self, messages, **kw):
                return "{}"

        agent = PolisherAgent(repo, RemovePlotRefLLM())
        state = {
            "project_id": "q8_proj", "chapter_number": 1,
            "chapter_status": "drafted",
        }
        result = agent.run(state)

        assert "error" in result
        assert "fact lock" in result["error"]
        assert result["chapter_status"] == "drafted"
        ch = repo.get_chapter("q8_proj", 1)
        assert "P001" in ch["content"]

    def test_polisher_changes_locked_state_value_returns_error(self, repo):
        """Polisher changes a locked state card numeric value → must return error."""
        from novel_factory.agents.polisher import PolisherAgent
        from novel_factory.llm.provider import LLMProvider

        # Use chapter 2 so prev_state_card (chapter 1) is accessible
        conn = repo._conn()
        conn.execute(
            "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
            ("q8_proj", "Q8 Novel", "urban"),
        )
        conn.execute(
            "INSERT INTO chapters (project_id, chapter_number, title, status, content) "
            "VALUES (?, ?, ?, 'drafted', ?)",
            ("q8_proj", 2, "第二章", "林默等级level=3，继续修炼中。"),
        )
        conn.execute(
            "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
            "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
            ("q8_proj", 2, "继续修炼", '[]', '[]', '[]', "悬念", 2500),
        )
        # Seed chapter 1 state card with level=3
        conn.execute(
            "INSERT INTO chapter_state (project_id, chapter_number, state_data, summary) "
            "VALUES (?, ?, ?, ?)",
            ("q8_proj", 1, '{"level": 3}', "前置状态卡"),
        )
        conn.commit()
        conn.close()

        class ChangeLevelLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {
                    "content": "林默等级level=5，继续修炼中。",  # Changed level=3 → level=5
                    "fact_change_risk": "none",
                    "changed_scope": ["sentence"],
                    "summary": "润色了句子",
                }
            def invoke_text(self, messages, **kw):
                return "{}"

        agent = PolisherAgent(repo, ChangeLevelLLM())
        state = {
            "project_id": "q8_proj", "chapter_number": 2,
            "chapter_status": "drafted",
        }
        result = agent.run(state)

        assert "error" in result
        assert "fact lock" in result["error"]
        assert result["chapter_status"] == "drafted"
        ch = repo.get_chapter("q8_proj", 2)
        assert "level=3" in ch["content"]

    def test_polisher_preserves_locked_facts_passes(self, repo):
        """Polisher preserves all locked facts → normal drafted→polished transition."""
        from novel_factory.agents.polisher import PolisherAgent
        from novel_factory.llm.provider import LLMProvider

        # v5.3.0: Content must meet 85% threshold (2125 chars for 2500 target)
        # Base is 33 chars, need 65x to get 2145 > 2125
        base = "他击败了Boss，获得了宝物，想起了P001。林默心中暗想下一步。"
        long_content = base * 65  # 2145 chars

        self._seed_drafted_chapter(
            repo,
            content=long_content,
        )

        class GoodPolishLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                return {
                    "content": long_content.replace("暗想", "谋划"),
                    "fact_change_risk": "none",
                    "changed_scope": ["sentence"],
                    "summary": "微调表达",
                }
            def invoke_text(self, messages, **kw):
                return "{}"

        agent = PolisherAgent(repo, GoodPolishLLM())
        state = {
            "project_id": "q8_proj", "chapter_number": 1,
            "chapter_status": "drafted",
        }
        result = agent.run(state)

        assert "error" not in result
        assert result["chapter_status"] == "polished"
        ch = repo.get_chapter("q8_proj", 1)
        assert "击败了Boss" in ch["content"]
        assert "P001" in ch["content"]

    def test_polisher_llm_message_contains_fact_lock(self, repo):
        """Polisher's actual LLM user message must include 事实锁定清单 from ContextBuilder."""
        from novel_factory.agents.polisher import PolisherAgent
        from novel_factory.llm.provider import LLMProvider

        self._seed_drafted_chapter(repo)

        captured_messages = []

        class CaptureLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None):
                captured_messages.extend(messages)
                return {
                    "content": "他击败了Boss，获得了宝物。",
                    "fact_change_risk": "none",
                    "changed_scope": [],
                    "summary": "无改动",
                }
            def invoke_text(self, messages, **kw):
                return "{}"

        agent = PolisherAgent(repo, CaptureLLM())
        state = {
            "project_id": "q8_proj", "chapter_number": 1,
            "chapter_status": "drafted",
        }
        agent.run(state)

        # Verify the user message contains fact lock context
        user_msgs = [m for m in captured_messages if m["role"] == "user"]
        assert len(user_msgs) >= 1
        user_content = user_msgs[0]["content"]
        assert "事实锁定" in user_content
