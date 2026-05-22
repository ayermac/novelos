"""Tests for sidecar diagnostic commands via Dispatcher."""

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
            if "ContinuityCheckerOutput" in schema_name:
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
        return {}
    
    def invoke_text(self, messages, temperature=None, max_tokens=None):
        return "Stub response"


@pytest.fixture
def dispatcher(tmp_db):
    """Create a dispatcher with stub LLM."""
    repo = Repository(str(tmp_db))
    llm = StubLLM()
    return Dispatcher(repo, llm)


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


class TestJSONEnvelopeFormat:
    """Tests for JSON envelope format compliance."""

    def test_all_dispatcher_methods_return_envelope(self, dispatcher, sample_project, repo):
        """All v2 dispatcher methods should return {ok, error, data} envelope."""
        methods = [
            lambda: dispatcher.run_continuity_check(sample_project, 1, 5),
        ]

        for method in methods:
            result = method()
            assert "ok" in result, f"Method missing 'ok' field: {method}"
            assert "error" in result, f"Method missing 'error' field: {method}"
            assert "data" in result, f"Method missing 'data' field: {method}"

    def test_error_envelope_format(self, dispatcher):
        """Error responses should have correct format."""
        result = dispatcher.run_continuity_check("nonexistent", 1, 5)

        assert result["ok"] is False
        assert isinstance(result["error"], str)
        assert len(result["error"]) > 0
        assert result["data"] == {}
