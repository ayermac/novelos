"""v6.0 review regression tests.

These tests cover integration points that can look wired at the file level
while still being disconnected at runtime.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def _client_with_repo():
    from novel_factory.api_app import create_api_app
    from novel_factory.db.connection import init_db
    from novel_factory.db.repository import Repository

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    return TestClient(app), Repository(db_path), db_path


def test_agent_memory_api_uses_request_db_path():
    """Agent Memory API must use the app db_path, not an unset app.state.db_conn."""
    client, _repo, db_path = _client_with_repo()
    try:
        response = client.post(
            "/api/agent-memory/v60-review",
            json={
                "agent_id": "author",
                "memory_type": "user_feedback",
                "key": "style.preference",
                "value": {"note": "对白更短、更锋利"},
                "confidence": 0.9,
            },
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

        response = client.get("/api/agent-memory/v60-review?agent_id=author")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["count"] == 1
        assert data["items"][0]["value"]["note"] == "对白更短、更锋利"
    finally:
        os.remove(db_path)


def test_agent_ops_trace_api_reads_persisted_traces():
    """AgentOps trace API must read persisted DB traces, not a fresh in-memory store."""
    client, repo, db_path = _client_with_repo()
    try:
        repo.save_agent_decision_trace(
            run_id="run-v60-review",
            project_id="v60-review",
            chapter_number=1,
            agent_id="author",
            stage="execute",
            role_profile_id="author",
            input_summary="project=v60-review chapter=1",
            self_check_json='{"passed": true}',
            autonomy_decision_json='{"decision": "continue", "reason": "自检通过"}',
            repair_attempts_json="[]",
            contract_validation_json='{"passed": true}',
        )

        response = client.get("/api/agent-ops/agent-traces?project_id=v60-review&agent_id=author")
        assert response.status_code == 200
        traces = response.json()["data"]["traces"]
        assert len(traces) == 1
        assert traces[0]["run_id"] == "run-v60-review"
        assert traces[0]["self_check"]["passed"] is True
        assert traces[0]["autonomy_decision"]["decision"] == "continue"
    finally:
        os.remove(db_path)


def test_core_agents_use_v6_context_in_execute_paths():
    """Core agents must call _build_v6_context so role profile and memory reach prompts."""
    root = Path(__file__).resolve().parent.parent
    agent_files = [
        "novel_factory/agents/planner.py",
        "novel_factory/agents/screenwriter.py",
        "novel_factory/agents/author.py",
        "novel_factory/agents/polisher.py",
        "novel_factory/agents/editor.py",
        "novel_factory/agents/memory_curator.py",
    ]
    for relative_path in agent_files:
        source = (root / relative_path).read_text(encoding="utf-8")
        assert "self._build_v6_context(state)" in source, relative_path


def test_handoff_contract_accepts_empty_optional_lists():
    """Planner handoff lists can be intentionally empty and should not false-fail."""
    from novel_factory.agents.contracts import validate_handoff

    ok, issues = validate_handoff(
        "planner",
        "screenwriter",
        {
            "objective": "主角进入新地图",
            "key_events": "进入城中城，遇到对手",
            "ending_hook": "发现旧敌踪迹",
            "plots_to_plant": [],
            "plots_to_resolve": [],
        },
    )
    assert ok is True
    assert issues == []


def test_chapter_version_diff_tool_uses_existing_repository_api(tmp_path):
    """chapter.version_diff should call Repository.list_chapter_versions."""
    from novel_factory.db.connection import init_db
    from novel_factory.db.repository import Repository
    from novel_factory.tools.chapter_tools import handle_chapter_version_diff

    db_path = tmp_path / "v60-tool.db"
    init_db(db_path)
    repo = Repository(str(db_path))
    repo.create_project(
        project_id="v60-tool",
        name="Tool Test",
        genre="urban",
        description="test",
        target_words=10000,
        total_chapters_planned=3,
    )
    repo.add_chapter("v60-tool", 1, "第一章", status="drafted")
    repo.save_version("v60-tool", 1, "第一版内容", created_by="author")

    result = handle_chapter_version_diff(
        {"project_id": "v60-tool", "chapter_number": 1},
        repo=repo,
    )
    assert "error" not in result
    assert result["version_count"] == 1


def test_core_agents_block_non_continue_self_check_decisions():
    """Self-check reroute/ask_human decisions must not be trace-only."""
    root = Path(__file__).resolve().parent.parent
    expected_fragments = {
        "novel_factory/agents/author.py": 'state.get("llm_mode") == "real" and autonomy.get("decision") in {"ask_human", "reroute", "refuse"}',
        "novel_factory/agents/screenwriter.py": 'autonomy.get("decision") in {"ask_human", "reroute", "refuse"}',
        "novel_factory/agents/memory_curator.py": 'state.get("llm_mode") == "real" and autonomy.get("decision") in {"ask_human", "reroute", "refuse"}',
    }
    for relative_path, fragment in expected_fragments.items():
        source = (root / relative_path).read_text(encoding="utf-8")
        assert fragment in source, relative_path
