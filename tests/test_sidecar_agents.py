"""Tests for v2 sidecar agents (Scout, Secretary, ContinuityChecker, Architect)."""

import json
import tempfile
from pathlib import Path

import pytest

from novel_factory.agents.architect import ArchitectAgent
from novel_factory.agents.continuity_checker import ContinuityCheckerAgent
from novel_factory.agents.scout import ScoutAgent
from novel_factory.agents.secretary import SecretaryAgent
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.llm.provider import LLMProvider


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_sidecar.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def repo(tmp_db):
    """Create a repository instance."""
    return Repository(str(tmp_db))


@pytest.fixture
def sample_project(repo):
    """Create a sample project for testing."""
    project_id = "test-project-001"
    conn = repo._conn()
    try:
        conn.execute(
            "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
            (project_id, "Test Novel", "都市异能"),
        )
        conn.commit()
    finally:
        conn.close()
    return project_id


class StubLLM(LLMProvider):
    """Stub LLM for testing."""
    
    def invoke_json(self, messages, schema=None, temperature=None):
        if schema:
            schema_name = schema.__name__
            if "ScoutOutput" in schema_name:
                return {
                    "market_report": {
                        "genre": "玄幻",
                        "platform": "起点",
                        "audience": "男性读者",
                        "trends": ["趋势1", "趋势2"],
                        "opportunities": ["机会1", "机会2"],
                        "reader_preferences": ["偏好1", "偏好2"],
                        "competitor_notes": ["竞品1", "竞品2"],
                        "summary": "市场分析摘要",
                        "recommendations": ["建议1", "建议2"]
                    },
                    "topic": "都市异能",
                    "keywords": ["关键词1", "关键词2"]
                }
            elif "DailyReport" in schema_name:
                return {
                    "daily_report": {
                        "date": "2025-01-01",
                        "workflow_summary": {"total_chapters": 1, "completed": 1},
                        "performance_metrics": {"avg_words": 100, "avg_quality": 8.5},
                        "issues": [],
                        "recommendations": ["建议1"]
                    }
                }
            elif "ContinuityCheckerOutput" in schema_name:
                return {
                    "report": {
                        "project_id": "test-project",
                        "from_chapter": 1,
                        "to_chapter": 5,
                        "issues": [{
                            "issue_type": "character",
                            "severity": "warning",
                            "chapter_range": "1-5",
                            "description": "角色不一致",
                            "recommendation": "检查角色设定"
                        }],
                        "warnings": ["警告1"],
                        "state_card_consistency": True,
                        "character_consistency": True,
                        "plot_consistency": True,
                        "summary": "连续性检查摘要"
                    },
                    "agent_messages": []
                }
            elif "ArchitectOutput" in schema_name:
                return {
                    "proposals": [{
                        "proposal_type": "quality_rule",
                        "scope": "quality",
                        "title": "改进提案",
                        "description": "描述",
                        "risk_level": "medium",
                        "affected_area": ["editor"],
                        "recommendation": "建议",
                        "rationale": "理由",
                        "implementation_notes": "实施说明"
                    }],
                    "summary": "架构改进提案摘要",
                    "total_proposals": 1
                }
        return {}
    
    def invoke_text(self, messages, temperature=None, max_tokens=None):
        return "Stub response"


class TestScoutAgent:
    """Tests for ScoutAgent."""

    def test_scout_run_generates_report(self, tmp_db, sample_project):
        """Scout agent should generate a market report."""
        repo = Repository(str(tmp_db))
        llm = StubLLM()
        agent = ScoutAgent(repo, llm)
        result = agent.run(
            project_id=sample_project,
            topic="都市异能",
            genre="玄幻",
            platform="起点",
            audience="男性读者",
        )

        assert result["ok"] is True
        assert "report_id" in result["data"]
        assert result["data"]["report_id"] > 0

    def test_scout_saves_to_database(self, repo, tmp_db, sample_project):
        """Scout report should be saved to scout_reports table."""
        llm = StubLLM()
        agent = ScoutAgent(repo, llm)
        agent.run(
            project_id=sample_project,
            topic="都市异能",
            genre="玄幻",
        )

        reports = repo.get_market_reports(sample_project, limit=1)
        assert len(reports) == 1
        assert reports[0]["topic"] == "都市异能"

    def test_scout_sends_message_to_planner(self, repo, tmp_db, sample_project):
        """Scout should send summary to Planner via agent_messages."""
        llm = StubLLM()
        agent = ScoutAgent(repo, llm)
        result = agent.run(project_id=sample_project, topic="都市异能")
        
        # send_summary_to_planner is called inside run() now
        # Just verify that messages were sent
        messages = repo.get_pending_messages(project_id=sample_project, to_agent="planner")
        assert len(messages) >= 1
        assert messages[0]["from_agent"] == "scout"


class TestSecretaryAgent:
    """Tests for SecretaryAgent."""

    def test_secretary_generates_daily_report(self, tmp_db, sample_project):
        """Secretary should generate a daily report."""
        repo = Repository(str(tmp_db))
        llm = StubLLM()
        agent = SecretaryAgent(repo, llm)
        result = agent.generate_daily_report(project_id=sample_project)

        assert result["ok"] is True
        assert "report_id" in result["data"]

    def test_secretary_saves_report_to_database(self, repo, tmp_db, sample_project):
        """Secretary report should be saved to reports table."""
        llm = StubLLM()
        agent = SecretaryAgent(repo, llm)
        agent.generate_daily_report(project_id=sample_project)

        reports = repo.get_reports(sample_project, report_type="daily")
        assert len(reports) >= 1

    def test_secretary_exports_chapter(self, repo, tmp_db, sample_project):
        """Secretary should export chapter content."""
        # Create a chapter first
        chapter_id = repo.add_chapter(
            project_id=sample_project,
            chapter_number=1,
            title="Chapter 1",
            status="published",
        )
        # Save content
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE chapters SET content=?, word_count=? WHERE id=?",
                ("This is chapter 1 content.", 100, chapter_id),
            )
            conn.commit()
        finally:
            conn.close()

        llm = StubLLM()
        agent = SecretaryAgent(repo, llm)
        result = agent.export_chapter(
            project_id=sample_project, chapter_number=1, export_format="markdown"
        )

        assert result["ok"] is True
        assert "export" in result["data"]
        assert "content" in result["data"]["export"]
        assert "chapter 1 content" in result["data"]["export"]["content"]


class TestContinuityCheckerAgent:
    """Tests for ContinuityCheckerAgent."""

    def test_continuity_check_generates_report(self, tmp_db, sample_project):
        """ContinuityChecker should generate a continuity report."""
        repo = Repository(str(tmp_db))
        llm = StubLLM()
        agent = ContinuityCheckerAgent(repo, llm)
        result = agent.run(
            project_id=sample_project, from_chapter=1, to_chapter=5
        )

        assert result["ok"] is True
        assert "report_id" in result["data"]

    def test_continuity_check_saves_to_database(self, repo, tmp_db, sample_project):
        """Continuity report should be saved to continuity_reports table."""
        llm = StubLLM()
        agent = ContinuityCheckerAgent(repo, llm)
        agent.run(project_id=sample_project, from_chapter=1, to_chapter=5)

        reports = repo.get_continuity_reports(sample_project)
        assert len(reports) >= 1

    def test_continuity_check_sends_warnings(self, repo, tmp_db, sample_project):
        """ContinuityChecker should send warnings to Editor/Planner."""
        llm = StubLLM()
        agent = ContinuityCheckerAgent(repo, llm)
        result = agent.run(project_id=sample_project, from_chapter=1, to_chapter=5)
        
        # Check that the agent sent messages (should be done in run method)
        messages = repo.get_pending_messages(project_id=sample_project)
        # Should have messages to editor or planner
        recipients = {msg["to_agent"] for msg in messages}
        # The agent should have sent messages during run()
        assert len(recipients) > 0


class TestArchitectAgent:
    """Tests for ArchitectAgent."""

    def test_architect_generates_proposal(self, tmp_db, sample_project):
        """Architect should generate an improvement proposal."""
        repo = Repository(str(tmp_db))
        llm = StubLLM()
        agent = ArchitectAgent(repo, llm)
        result = agent.run(project_id=sample_project, scope="quality")

        assert result["ok"] is True
        assert "proposal_ids" in result["data"]

    def test_architect_saves_to_database(self, repo, tmp_db, sample_project):
        """Architect proposal should be saved to architecture_proposals table."""
        llm = StubLLM()
        agent = ArchitectAgent(repo, llm)
        agent.run(project_id=sample_project, scope="quality")

        proposals = repo.get_architecture_proposals(sample_project)
        assert len(proposals) >= 1
        assert proposals[0]["status"] == "pending"

    def test_architect_proposal_has_required_fields(self, tmp_db, sample_project):
        """Architect proposal should have all required fields."""
        repo = Repository(str(tmp_db))
        llm = StubLLM()
        agent = ArchitectAgent(repo, llm)
        agent.run(project_id=sample_project, scope="quality")

        proposals = repo.get_architecture_proposals(sample_project)
        proposal = proposals[0]

        assert "title" in proposal
        assert "description" in proposal
        assert "risk_level" in proposal
        assert "recommendation" in proposal


class TestSidecarIntegration:
    """Integration tests for sidecar agents."""

    def test_all_agents_can_run_concurrently(self, tmp_db, sample_project):
        """All sidecar agents should run without conflicts."""
        repo = Repository(str(tmp_db))
        llm = StubLLM()
        
        scout = ScoutAgent(repo, llm)
        secretary = SecretaryAgent(repo, llm)
        continuity = ContinuityCheckerAgent(repo, llm)
        architect = ArchitectAgent(repo, llm)

        # Run all agents
        r1 = scout.run(project_id=sample_project, topic="都市异能")
        r2 = secretary.generate_daily_report(project_id=sample_project)
        r3 = continuity.run(project_id=sample_project, from_chapter=1, to_chapter=5)
        r4 = architect.run(project_id=sample_project, scope="quality")

        assert r1["ok"] is True
        assert r2["ok"] is True
        assert r3["ok"] is True
        assert r4["ok"] is True

    def test_sidecar_does_not_change_chapter_status(self, repo, tmp_db, sample_project):
        """Sidecar agents should NOT change chapter status."""
        # Create a chapter
        chapter_id = repo.add_chapter(
            project_id=sample_project,
            chapter_number=1,
            title="Chapter 1",
            status="draft",
        )
        # Save content
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE chapters SET content=?, word_count=? WHERE id=?",
                ("Content", 100, chapter_id),
            )
            conn.commit()
        finally:
            conn.close()

        # Run sidecar agents
        llm = StubLLM()
        scout = ScoutAgent(repo, llm)
        scout.run(project_id=sample_project, topic="都市异能")

        # Check chapter status unchanged
        chapter = repo.get_chapter(sample_project, 1)
        assert chapter["status"] == "draft"
