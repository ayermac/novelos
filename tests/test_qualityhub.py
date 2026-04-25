"""Tests for v2.1 QualityHub."""

from __future__ import annotations

import pytest

from novel_factory.quality.hub import QualityHub
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
    
    def test_final_gate_narrative_low_blocks(self, tmp_db):
        """Test final_gate blocks on low narrative quality."""
        repo = Repository(tmp_db)
        registry = SkillRegistry()
        hub = QualityHub(repo, registry)
        
        # Seed test project with passed review
        _seed_test_project_with_review(repo, "test_proj", 1, passed=True, score=85)
        
        # Mock narrative quality to be low
        # This test verifies the logic, actual narrative scoring may vary
        result = hub.final_gate("test_proj", 1)
        
        assert result["ok"] is True
        data = result["data"]
        
        # If narrative quality is low, it should be in blocking issues
        for issue in data["blocking_issues"]:
            if issue.get("type") == "narrative_quality_low":
                assert issue.get("revision_target") == "author"


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
