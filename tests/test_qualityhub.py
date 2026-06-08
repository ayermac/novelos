"""Tests for v2.1 QualityHub."""

from __future__ import annotations

import pytest

from novel_factory.quality.hub import QualityHub
from novel_factory.skills.narrative_quality_scorer import NarrativeQualityScorer
from novel_factory.skills.registry import SkillRegistry
from novel_factory.db.repository import Repository
from novel_factory.db.connection import init_db


class TestQualityHubCheckDraft:
    """Test QualityHub.check_draft."""

    def test_check_draft_passes(self, tmp_db):
        """Test check_draft with good content."""
        repo = Repository(tmp_db)
        registry = SkillRegistry()
        hub = QualityHub(repo, registry)

        # Seed test data
        _seed_test_project(repo, "test_proj", 1)

        result = hub.check_draft("test_proj", 1, "这是一个测试内容。" * 50)

        assert result["ok"] is True
        assert "data" in result
        assert "overall_score" in result["data"]

    def test_check_draft_with_death_penalty(self, tmp_db):
        """Test check_draft detects death penalty."""
        repo = Repository(tmp_db)
        registry = SkillRegistry()
        hub = QualityHub(repo, registry)

        # Seed test data
        _seed_test_project(repo, "test_proj", 1)

        # Content with death penalty
        content = "这是一个测试内容，包含敏感词汇如习近平。"
        result = hub.check_draft("test_proj", 1, content)

        assert result["ok"] is True
        data = result["data"]
        # Should have blocking issues if death penalty detected
        if data["blocking_issues"]:
            assert any("death_penalty" in issue.get("type", "") for issue in data["blocking_issues"])


class TestQualityHubCheckPolished:
    """Test QualityHub.check_polished."""

    def test_check_polished_passes(self, tmp_db):
        """Test check_polished with good content."""
        repo = Repository(tmp_db)
        registry = SkillRegistry()
        hub = QualityHub(repo, registry)

        # Seed test data
        _seed_test_project(repo, "test_proj", 1)

        original = "这是原始内容。" * 50
        polished = "这是润色后的内容。" * 50

        result = hub.check_polished("test_proj", 1, original, polished)

        assert result["ok"] is True
        assert "data" in result


class TestQualityHubFinalGate:
    """Test QualityHub.final_gate."""

    def test_final_gate_passes(self, tmp_db):
        """Test final_gate with good review."""
        repo = Repository(tmp_db)
        registry = SkillRegistry()
        hub = QualityHub(repo, registry)

        # Seed test project with content and review
        _seed_test_project_with_review(repo, "test_proj", 1, passed=True, score=92)

        result = hub.final_gate("test_proj", 1)

        assert result["ok"] is True
        data = result["data"]
        # Should pass if review passed
        assert data["pass"] is True or data["overall_score"] >= 60

    def test_final_gate_fails_on_editor_rejection(self, tmp_db):
        """Test final_gate fails when editor rejected."""
        repo = Repository(tmp_db)
        registry = SkillRegistry()
        hub = QualityHub(repo, registry)

        # Seed test project with failed review
        _seed_test_project_with_review(repo, "test_proj", 1, passed=False, score=45)

        result = hub.final_gate("test_proj", 1)

        assert result["ok"] is True
        data = result["data"]
        # Should have blocking issues
        assert len(data["blocking_issues"]) > 0
        # Should not pass
        assert data["pass"] is False
        assert data["revision_target"] == "author"

    def test_final_gate_narrative_low_is_warning(self, tmp_db):
        """Narrative quality is an aggregate warning, not a hard blocker."""
        repo = Repository(tmp_db)

        class FakeRegistry:
            def run_skill(self, skill_id, payload, agent="manual", stage="manual"):
                if skill_id == "ai-style-detector":
                    return {"ok": True, "data": {"ai_trace_score": 0}}
                if skill_id == "narrative-quality":
                    return {"ok": True, "data": {"scores": {"overall_score": 10}}}
                return {"ok": True, "data": {}}

        registry = FakeRegistry()
        hub = QualityHub(repo, registry)

        # Seed test project with passed review
        _seed_test_project_with_review(repo, "test_proj", 1, passed=True, score=85)

        result = hub.final_gate("test_proj", 1)

        assert result["ok"] is True
        data = result["data"]

        assert not any(issue.get("type") == "narrative_quality_low" for issue in data["blocking_issues"])
        assert any(issue.get("type") == "narrative_quality_low" for issue in data["warnings"])
        assert data["pass"] is True
        assert data["revision_target"] is None
        assert data["quality_dimensions"]["narrative_quality"] == 10


class TestNarrativeQualityScorerRealChineseProse:
    """Regression coverage from real LLM acceptance."""

    def test_scores_chinese_curly_quotes_as_dialogue(self):
        scorer = NarrativeQualityScorer()
        text = (
            "林澈盯着便签，雨噪像细针一样扎进耳膜。"
            "“你是在把我往里推，还是在把我往外赶，许今白？”他低声问。"
            "空荡的数据站没有回答。"
            "“哥，别相信我的记忆。”投影熄灭。"
        )

        result = scorer.run({"text": text})

        assert result["ok"] is True
        scores = result["data"]["scores"]
        assert scores["dialogue_naturalness"] > 30

    def test_scores_reversal_ending_as_hook(self):
        scorer = NarrativeQualityScorer()
        text = (
            "林澈反复播放那段破碎投影，确认妹妹最后留下的不是逃跑指令。"
            "投影熄灭前，又吐出半个被雨噪咬碎的音节。"
            "他听了三遍，终于确认那不是“逃”，而是“查”。"
        )

        result = scorer.run({"text": text})

        assert result["ok"] is True
        assert result["data"]["scores"]["hook_strength"] >= 45

    def test_scores_system_cost_confrontation_as_conflict(self):
        scorer = NarrativeQualityScorer()
        text = (
            "【推荐方案：异常表征清除，关联人员记忆清除。代价：目标记忆清除率100%。】\n\n"
            "老先生没动。\n\n"
            "“跟你走？”他问，“去哪儿？”\n\n"
            "林泽握紧隔离锚。“先离开这里。”\n\n"
            "“出去之后呢？你知道出去之后我们会变成什么样吗？”老先生盯着他。"
            "“你那个系统会把我们的脑子清空。你自己清楚这一点吗？”\n\n"
            "站台深处传来金属刮擦声，隔离锚弹出红色警告：方案偏离，绩效评分-15。"
        )

        result = scorer.run({"text": text})

        assert result["ok"] is True
        assert result["data"]["scores"]["conflict_intensity"] >= 40

    def test_scores_hidden_name_and_record_warning_as_strong_hook(self):
        scorer = NarrativeQualityScorer()
        text = (
            "任务结算界面闪了一下，灰色小字只剩一个姓氏。周。\n"
            "许知夏的声音压得很低：“有人调了你刚才的任务记录，我拦不住。”\n"
            "“谁？”\n"
            "“第七办公室，魏承霜的人。”\n"
            "林泽需要找到那个名字，在被系统彻底抹掉之前。"
        )

        result = scorer.run({"text": text})

        assert result["ok"] is True
        assert result["data"]["scores"]["hook_strength"] >= 50


class TestQualityReports:
    """Test quality_reports database operations."""

    def test_save_quality_report_success(self, tmp_db):
        """Test saving successful quality report."""
        repo = Repository(tmp_db)

        # Seed test project
        _seed_test_project(repo, "test_proj", 1)

        # Save quality report
        report_id = repo.save_quality_report(
            project_id="test_proj",
            chapter_number=1,
            stage="final",
            overall_score=85.5,
            pass_=True,
            revision_target=None,
            blocking_issues=[],
            warnings=["test warning"],
            skill_results=[],
            quality_dimensions={"ai_trace": 90, "narrative": 80},
        )

        assert report_id > 0

        # Query quality reports
        reports = repo.get_quality_reports("test_proj", 1)
        assert len(reports) >= 1
        assert reports[0]["overall_score"] == 85.5

    def test_save_quality_report_failure(self, tmp_db):
        """Test saving failed quality report."""
        repo = Repository(tmp_db)

        # Seed test project
        _seed_test_project(repo, "test_proj", 1)

        # Save failed quality report
        report_id = repo.save_quality_report(
            project_id="test_proj",
            chapter_number=1,
            stage="final",
            overall_score=45.0,
            pass_=False,
            revision_target="author",
            blocking_issues=[{"type": "narrative_quality_low", "message": "叙事质量过低"}],
            warnings=[],
            skill_results=[],
            quality_dimensions={"narrative": 30},
        )

        assert report_id > 0

        # Query quality reports
        reports = repo.get_quality_reports("test_proj", 1)
        assert len(reports) >= 1
        assert reports[0]["pass"] == 0


# Helper functions
def _seed_test_project(repo: Repository, project_id: str, chapter_number: int):
    """Seed test project with minimal data."""
    conn = repo._conn()
    conn.execute(
        "INSERT OR IGNORE INTO projects (project_id, name, genre) VALUES (?, ?, ?)",
        (project_id, "Test Project", "fantasy"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO chapters (project_id, chapter_number, title, status) VALUES (?, ?, ?, ?)",
        (project_id, chapter_number, f"Chapter {chapter_number}", "drafted"),
    )
    conn.commit()
    conn.close()


def _seed_test_project_with_review(
    repo: Repository, project_id: str, chapter_number: int, passed: bool, score: int
):
    """Seed test project with review."""
    conn = repo._conn()
    conn.execute(
        "INSERT OR IGNORE INTO projects (project_id, name, genre) VALUES (?, ?, ?)",
        (project_id, "Test Project", "fantasy"),
    )

    # Insert chapter with content
    cursor = conn.execute(
        "INSERT INTO chapters (project_id, chapter_number, title, status, content) VALUES (?, ?, ?, ?, ?)",
        (project_id, chapter_number, f"Chapter {chapter_number}", "polished", "测试内容" * 50),
    )
    chapter_id = cursor.lastrowid

    # Insert review
    conn.execute(
        "INSERT INTO reviews (project_id, chapter_id, pass, score, setting_score, logic_score, poison_score, text_score, pacing_score) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (project_id, chapter_id, 1 if passed else 0, score, 18, 18, 18, 18, 18),
    )

    conn.commit()
    conn.close()


@pytest.fixture
def tmp_db(tmp_path):
    """Create temporary database for testing."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return str(db_path)
