"""Tests for v2 CLI commands via Dispatcher."""

import json
import tempfile
from pathlib import Path

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.dispatcher import Dispatcher
from novel_factory.llm.provider import LLMProvider


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_v2_cli.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def repo(tmp_db):
    """Create a repository instance."""
    return Repository(str(tmp_db))


@pytest.fixture
def sample_project(repo):
    """Create a sample project for testing."""
    project_id = "test-cli-project"
    conn = repo._conn()
    try:
        conn.execute(
            "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
            (project_id, "CLI Test Novel", "都市异能"),
        )
        conn.commit()
    finally:
        conn.close()
    return project_id


class StubLLM(LLMProvider):
    """Stub LLM for v2 testing."""
    
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


@pytest.fixture
def dispatcher(tmp_db):
    """Create a dispatcher with stub LLM."""
    repo = Repository(str(tmp_db))
    llm = StubLLM()
    return Dispatcher(repo, llm)


class TestScoutViaDispatcher:
    """Tests for scout functionality via Dispatcher."""

    def test_scout_generates_report(self, dispatcher, sample_project):
        """Scout should generate a market report."""
        result = dispatcher.run_scout(
            project_id=sample_project,
            topic="都市异能",
            genre="玄幻",
            platform="起点",
            audience="男性读者",
        )

        assert result["ok"] is True
        assert "report_id" in result["data"]

    def test_scout_missing_project(self, dispatcher):
        """Scout should fail with missing project."""
        result = dispatcher.run_scout(
            project_id="nonexistent",
            topic="都市异能",
        )

        assert result["ok"] is False
        assert "not found" in result["error"]


class TestSecretaryViaDispatcher:
    """Tests for secretary functionality via Dispatcher."""

    def test_daily_report_generation(self, dispatcher, sample_project):
        """Secretary should generate daily report."""
        result = dispatcher.run_secretary_report(
            project_id=sample_project,
            report_type="daily",
        )

        assert result["ok"] is True
        assert "report_id" in result["data"]

    def test_chapter_export(self, dispatcher, sample_project, repo):
        """Secretary should export chapter content."""
        # Create a chapter first
        repo.save_chapter(
            project_id=sample_project,
            chapter_number=1,
            title="Chapter 1",
            content="This is chapter 1 content.",
            word_count=100,
            status="published",
        )

        result = dispatcher.run_secretary_export(
            project_id=sample_project,
            chapter_number=1,
            export_format="markdown",
        )

        assert result["ok"] is True
        assert "export" in result["data"]
        assert "content" in result["data"]["export"]


class TestContinuityCheckViaDispatcher:
    """Tests for continuity check functionality via Dispatcher."""

    def test_continuity_check(self, dispatcher, sample_project):
        """Continuity check should generate report."""
        result = dispatcher.run_continuity_check(
            project_id=sample_project,
            from_chapter=1,
            to_chapter=5,
        )

        assert result["ok"] is True
        assert "report_id" in result["data"]


class TestArchitectViaDispatcher:
    """Tests for architect functionality via Dispatcher."""

    def test_architect_suggest(self, dispatcher, sample_project):
        """Architect should generate proposal."""
        result = dispatcher.run_architect_suggest(
            project_id=sample_project,
            scope="quality",
        )

        assert result["ok"] is True
        assert "proposal_ids" in result["data"]


class TestJSONEnvelopeFormat:
    """Tests for JSON envelope format compliance."""

    def test_all_dispatcher_methods_return_envelope(self, dispatcher, sample_project, repo):
        """All v2 dispatcher methods should return {ok, error, data} envelope."""
        # Create a chapter for export test
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
                ("Content", 100, chapter_id),
            )
            conn.commit()
        finally:
            conn.close()

        methods = [
            lambda: dispatcher.run_scout(sample_project, "都市异能"),
            lambda: dispatcher.run_secretary_report(sample_project, "daily"),
            lambda: dispatcher.run_secretary_export(sample_project, 1, "markdown"),
            lambda: dispatcher.run_continuity_check(sample_project, 1, 5),
            lambda: dispatcher.run_architect_suggest(sample_project, "quality"),
        ]

        for method in methods:
            result = method()
            assert "ok" in result, f"Method missing 'ok' field: {method}"
            assert "error" in result, f"Method missing 'error' field: {method}"
            assert "data" in result, f"Method missing 'data' field: {method}"

    def test_error_envelope_format(self, dispatcher):
        """Error responses should have correct format."""
        result = dispatcher.run_scout(project_id="nonexistent", topic="test")

        assert result["ok"] is False
        assert isinstance(result["error"], str)
        assert len(result["error"]) > 0
        assert result["data"] == {}
