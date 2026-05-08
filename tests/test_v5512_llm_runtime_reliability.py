"""v5.5.12 LLM runtime reliability and cost guardrail tests."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from novel_factory.config.settings import LLMConfig, load_settings
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.llm.openai_compatible import OpenAICompatibleProvider
from novel_factory.workflow.runner import run_with_graph


class _FakeResponse:
    content = '{"ok": true}'
    usage_metadata = {"input_tokens": 10, "output_tokens": 5}


class _FlakyClient:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, _messages, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            raise Exception("429 rate limit")
        return _FakeResponse()


def _seed_ready_project(repo: Repository, project_id: str = "budget_proj") -> None:
    repo.create_project(
        project_id=project_id,
        name="Budget Project",
        genre="fantasy",
        description="A budget test project",
        total_chapters_planned=10,
        target_words=30000,
    )
    repo.add_chapter(project_id, 1, title="第一章", status="planned")
    repo.create_world_setting(project_id, "世界", "城市", "城市修仙世界")
    repo.create_character(project_id, "叶玄", "protagonist", "重生仙帝")
    repo.create_outline(project_id, "arc", 1, "第一卷", "主角回归都市", "1-10")
    repo.create_instruction(
        project_id,
        1,
        objective="主角解决第一场危机",
        key_events='["危机出现", "主角出手"]',
        ending_hook="新的敌人出现",
        word_target=2500,
    )


def test_llm_provider_retries_rate_limit_with_exponential_backoff():
    config = LLMConfig(
        api_key="test-key",
        retry_attempts=2,
        retry_min_seconds=0,
        retry_max_seconds=0,
    )
    provider = OpenAICompatibleProvider(config)
    client = _FlakyClient()
    provider._client = client  # type: ignore[assignment]

    result = provider.invoke_json([{"role": "user", "content": "return json"}])

    assert result == {"ok": True}
    assert client.calls == 2
    assert provider.last_token_usage is not None
    assert provider.last_token_usage.total_tokens == 15


def test_chapter_token_budget_failure_finalizes_workflow_run(tmp_path):
    db_path = str(tmp_path / "budget.db")
    init_db(db_path)
    repo = Repository(db_path)
    _seed_ready_project(repo)

    settings = load_settings()
    settings.db_path = db_path
    settings.runtime_budget.chapter_token_limit = 100

    result = run_with_graph(
        project_id="budget_proj",
        chapter_number=1,
        settings=settings,
        repo=repo,
        llm_mode="stub",
    )

    assert result["error"]
    assert "TOKEN_BUDGET_EXCEEDED" in result["error"]
    assert result["requires_human"] is True
    assert result["total_tokens"] > 100

    runs = repo.get_workflow_runs_for_project("budget_proj")
    assert runs[0]["status"] in ("failed", "blocked")
    assert "TOKEN_BUDGET_EXCEEDED" in (runs[0]["error_message"] or "")
    assert runs[0]["total_tokens"] > 100


def test_project_token_budget_includes_previous_runs(tmp_path):
    db_path = str(tmp_path / "project_budget.db")
    init_db(db_path)
    repo = Repository(db_path)
    _seed_ready_project(repo, project_id="project-budget")

    previous_run = repo.create_workflow_run("project-budget", 0)
    repo.update_workflow_run(previous_run, status="completed", total_tokens=95)

    settings = load_settings()
    settings.db_path = db_path
    settings.runtime_budget.project_token_limit = 100

    result = run_with_graph(
        project_id="project-budget",
        chapter_number=1,
        settings=settings,
        repo=repo,
        llm_mode="stub",
    )

    assert result["error"]
    assert "TOKEN_BUDGET_EXCEEDED" in result["error"]
    assert "项目 token" in result["error"]
    assert result["requires_human"] is True


@pytest.fixture()
def client_with_project():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)
    app = __import__("novel_factory.api_app", fromlist=["create_api_app"]).create_api_app(
        db_path=db_path, llm_mode="stub"
    )
    client = TestClient(app)
    resp = client.post("/api/onboarding/projects", json={
        "project_id": "budget-auto",
        "name": "Budget Auto",
        "genre": "奇幻",
        "description": "budget auto project",
        "total_chapters_planned": 10,
        "target_words": 30000,
    })
    assert resp.status_code == 200

    gen_resp = client.post("/api/projects/budget-auto/genesis/generate", json={
        "title": "Budget Auto",
        "genre": "奇幻",
        "premise": "budget auto project",
        "target_chapters": 10,
        "target_words": 30000,
    })
    assert gen_resp.status_code == 200
    genesis_id = gen_resp.json()["data"]["id"]
    approve_resp = client.post(f"/api/projects/budget-auto/genesis/{genesis_id}/approve")
    assert approve_resp.status_code == 200

    fill_resp = client.post("/api/projects/budget-auto/production/auto-fill", json={
        "scope": "missing_context",
        "chapter_start": 1,
        "chapter_end": 10,
        "confirm": True,
    })
    assert fill_resp.status_code == 200
    assert fill_resp.json()["ok"] is True
    yield client
    if os.path.exists(db_path):
        os.unlink(db_path)


def test_run_auto_stops_when_session_token_budget_exceeded(client_with_project):
    resp = client_with_project.post("/api/projects/budget-auto/production/run-auto", json={
        "confirm": True,
        "max_steps": 3,
        "max_session_tokens": 1,
    })

    body = resp.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["stop_reason"] == "token_budget_exceeded"
    assert data["status"] == "stopped"
    assert data["session_tokens_used"] > 1
