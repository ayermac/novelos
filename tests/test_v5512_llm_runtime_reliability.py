"""v5.5.12 LLM runtime reliability and cost guardrail tests."""

from __future__ import annotations

import os
import tempfile
import json
import time

import pytest
from fastapi.testclient import TestClient

from novel_factory.config.loader import load_settings_with_cli as load_settings
from novel_factory.config.settings import LLMConfig
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
    assert provider.last_call_trace is not None
    assert provider.last_call_trace["request"]["messages"][0]["content"] == "return json"
    assert provider.last_call_trace["response"]["usage"]["total_tokens"] == 15


def test_llm_provider_ignores_malformed_proxy_environment_for_client_init(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost,::1,127.0.0.0/8,::1/128")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost,::1,127.0.0.0/8,::1/128")
    config = LLMConfig(
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        model="gpt-4",
    )

    provider = OpenAICompatibleProvider(config)

    assert provider.client is not None


def test_llm_provider_enforces_hard_timeout_when_sdk_hangs():
    class _HangingClient:
        def invoke(self, _messages, **_kwargs):
            time.sleep(2)
            return _FakeResponse()

    config = LLMConfig(
        api_key="test-key",
        request_timeout_seconds=1,
        retry_attempts=1,
        retry_min_seconds=0,
        retry_max_seconds=0,
    )
    provider = OpenAICompatibleProvider(config)
    provider._client = _HangingClient()  # type: ignore[assignment]

    with pytest.raises(Exception) as exc:
        provider.invoke_json([{"role": "user", "content": "return json"}])

    assert "超时" in str(exc.value)


def test_llm_provider_call_trace_redacts_sensitive_request_and_response():
    class _SensitiveResponse:
        content = '{"echo": "sk-response-secret"}'
        usage_metadata = {"input_tokens": 3, "output_tokens": 4}
        response_metadata = {"finish_reason": "stop"}

    class _Client:
        def invoke(self, _messages, **_kwargs):
            return _SensitiveResponse()

    config = LLMConfig(
        api_key="sk-real-secret",
        base_url="https://user:pass@example.test/v1?api_key=sk-url-secret",
        model="trace-model",
        retry_attempts=1,
    )
    provider = OpenAICompatibleProvider(config)
    provider._client = _Client()  # type: ignore[assignment]

    result = provider.invoke_json([
        {"role": "system", "content": "secret sk-system-secret"},
        {"role": "user", "content": "return json with token=abc123456789"},
    ])

    assert result == {"echo": "sk-response-secret"}
    trace = provider.last_call_trace
    assert trace is not None
    raw_trace = json.dumps(trace, ensure_ascii=False)
    assert "sk-real-secret" not in raw_trace
    assert "sk-url-secret" not in raw_trace
    assert "sk-system-secret" not in raw_trace
    assert "abc123456789" not in raw_trace
    assert trace["request"]["model"] == "trace-model"
    assert trace["request"]["message_count"] >= 2
    assert trace["response"]["content_length"] > 0


def test_llm_provider_retries_transient_connection_errors():
    class _ConnectionClient:
        def __init__(self) -> None:
            self.calls = 0

        def invoke(self, _messages, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise Exception("connection reset by peer")
            return _FakeResponse()

    config = LLMConfig(
        api_key="test-key",
        retry_attempts=2,
        retry_min_seconds=0,
        retry_max_seconds=0,
    )
    provider = OpenAICompatibleProvider(config)
    client = _ConnectionClient()
    provider._client = client  # type: ignore[assignment]

    result = provider.invoke_json([{"role": "user", "content": "return json"}])

    assert result == {"ok": True}
    assert client.calls == 2


def test_llm_provider_falls_back_to_http_for_langchain_string_choices_error(monkeypatch):
    """Some OpenAI-compatible gateways return a shape that makes LangChain
    raise before it can build an AIMessage; provider should still normalize it.
    """
    class _BrokenLangChainClient:
        def invoke(self, _messages, **_kwargs):
            raise AttributeError("'str' object has no attribute 'choices'")

    class _FallbackResponse:
        content = '{"ok": true}'
        usage_metadata = {"input_tokens": 2, "output_tokens": 3}
        response_metadata = {
            "token_usage": {
                "prompt_tokens": 2,
                "completion_tokens": 3,
                "total_tokens": 5,
            },
            "finish_reason": "stop",
        }

    config = LLMConfig(
        api_key="test-key",
        retry_attempts=1,
        retry_min_seconds=0,
        retry_max_seconds=0,
    )
    provider = OpenAICompatibleProvider(config)
    provider._client = _BrokenLangChainClient()  # type: ignore[assignment]
    fallback_calls = []

    def fake_http_fallback(lc_messages, request_timeout_seconds=None, **kwargs):
        fallback_calls.append({
            "message_count": len(lc_messages),
            "request_timeout_seconds": request_timeout_seconds,
            "kwargs": kwargs,
        })
        return _FallbackResponse()

    monkeypatch.setattr(
        provider,
        "_invoke_http_chat_completion",
        fake_http_fallback,
        raising=False,
    )

    result = provider.invoke_json([{"role": "user", "content": "return json"}])

    assert result == {"ok": True}
    assert fallback_calls
    assert provider.last_call_trace is not None
    assert provider.last_call_trace["request"]["transport_fallback"] == "http"
    assert provider.last_call_trace["response"]["usage"]["total_tokens"] == 5


def test_llm_provider_does_not_retry_request_timeout():
    class _TimeoutClient:
        def __init__(self) -> None:
            self.calls = 0

        def invoke(self, _messages, **_kwargs):
            self.calls += 1
            raise Exception("request timed out")

    config = LLMConfig(
        api_key="test-key",
        request_timeout_seconds=60,
        retry_attempts=3,
        retry_min_seconds=0,
        retry_max_seconds=0,
    )
    provider = OpenAICompatibleProvider(config)
    client = _TimeoutClient()
    provider._client = client  # type: ignore[assignment]

    with pytest.raises(Exception, match="超时"):
        provider.invoke_json([{"role": "user", "content": "return json"}])

    assert client.calls == 1


def test_llm_provider_text_call_can_override_timeout_without_mutating_config():
    class _TextResponse:
        content = "ok"
        usage_metadata = {"input_tokens": 1, "output_tokens": 1}

    class _Client:
        def __init__(self) -> None:
            self.calls = 0

        def invoke(self, _messages, **_kwargs):
            self.calls += 1
            return _TextResponse()

    class _CapturingProvider(OpenAICompatibleProvider):
        def __init__(self, config):
            super().__init__(config)
            self.built_timeouts = []
            self.client_instances = []

        def _build_client(self, request_timeout_seconds=None):
            self.built_timeouts.append(request_timeout_seconds or self.config.request_timeout_seconds)
            client = _Client()
            self.client_instances.append(client)
            return client

    config = LLMConfig(api_key="test-key", request_timeout_seconds=60)
    provider = _CapturingProvider(config)

    text = provider.invoke_text(
        [{"role": "user", "content": "write"}],
        request_timeout_seconds=300,
        max_retries=1,
    )

    assert text == "ok"
    assert provider.built_timeouts == [300]
    assert provider.client_instances[-1].calls == 1
    assert provider.config.request_timeout_seconds == 60


def test_llm_provider_text_call_tolerates_none_response_metadata():
    class _TextResponse:
        content = "ok"
        usage_metadata = {}
        response_metadata = None

    class _Client:
        def invoke(self, _messages, **_kwargs):
            return _TextResponse()

    provider = OpenAICompatibleProvider(LLMConfig(api_key="test-key"))
    provider._client = _Client()  # type: ignore[assignment]

    text = provider.invoke_text([{"role": "user", "content": "write"}])

    assert text == "ok"
    assert provider.last_token_usage is not None
    assert provider.last_token_usage.total_tokens == 0
    assert provider.last_call_trace is not None
    assert provider.last_call_trace["response"]["response_metadata"] == {}


def test_llm_provider_text_call_tolerates_none_token_usage():
    class _TextResponse:
        content = "ok"
        usage_metadata = {}
        response_metadata = {"token_usage": None, "finish_reason": "stop"}

    class _Client:
        def invoke(self, _messages, **_kwargs):
            return _TextResponse()

    provider = OpenAICompatibleProvider(LLMConfig(api_key="test-key"))
    provider._client = _Client()  # type: ignore[assignment]

    text = provider.invoke_text([{"role": "user", "content": "write"}], agent_id="author")

    assert text == "ok"
    assert provider.last_token_usage is not None
    assert provider.last_token_usage.total_tokens == 0
    assert provider.last_call_trace is not None
    assert provider.last_call_trace["request"]["call_type"] == "text"
    assert provider.last_call_trace["request"]["agent_id"] == "author"


def test_llm_provider_stream_invalid_parameter_falls_back_to_text():
    class _TextResponse:
        content = "ok"
        usage_metadata = {"input_tokens": 2, "output_tokens": 3}
        response_metadata = {"finish_reason": "stop"}

    class _Client:
        def __init__(self) -> None:
            self.stream_calls = 0
            self.invoke_calls = 0

        def stream(self, _messages, **_kwargs):
            self.stream_calls += 1
            raise Exception(
                "Error code: 400 - {'error': {'code': 'InvalidParameter', "
                "'message': 'A parameter specified in the request is not valid', "
                "'param': '', 'type': 'BadRequest'}}"
            )

        def invoke(self, _messages, **_kwargs):
            self.invoke_calls += 1
            return _TextResponse()

    provider = OpenAICompatibleProvider(LLMConfig(api_key="test-key"))
    client = _Client()
    provider._client = client  # type: ignore[assignment]

    chunks: list[str] = []
    text = provider.invoke_text_stream(
        [{"role": "user", "content": "write"}],
        agent_id="author",
        on_chunk=chunks.append,
    )

    assert text == "ok"
    assert client.stream_calls == 1
    assert client.invoke_calls == 1
    assert provider.last_call_trace is not None
    assert provider.last_call_trace["request"]["call_type"] == "text"
    assert provider.last_call_trace["request"]["agent_id"] == "author"


def test_llm_provider_text_invalid_parameter_falls_back_to_http(monkeypatch):
    class _Client:
        def invoke(self, _messages, **_kwargs):
            raise Exception(
                "Error code: 400 - {'error': {'code': 'InvalidParameter', "
                "'message': 'A parameter specified in the request is not valid', "
                "'param': '', 'type': 'BadRequest'}}"
            )

    provider = OpenAICompatibleProvider(LLMConfig(api_key="test-key"))
    provider._client = _Client()  # type: ignore[assignment]
    fallback_calls = []

    def _fake_http_fallback(lc_messages, request_timeout_seconds=None, **kwargs):
        fallback_calls.append({
            "message_count": len(lc_messages),
            "request_timeout_seconds": request_timeout_seconds,
            "kwargs": kwargs,
        })
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        }

    monkeypatch.setattr(provider, "_invoke_http_chat_completion", _fake_http_fallback)

    text = provider.invoke_text(
        [{"role": "user", "content": "write"}],
        temperature=0.7,
        max_tokens=2048,
        agent_id="author",
    )

    assert text == "ok"
    assert fallback_calls
    assert fallback_calls[0]["kwargs"]["temperature"] == 0.7
    assert fallback_calls[0]["kwargs"]["max_tokens"] == 2048
    assert provider.last_call_trace is not None
    assert provider.last_call_trace["request"]["call_type"] == "text"
    assert provider.last_call_trace["request"]["agent_id"] == "author"
    assert provider.last_call_trace["request"]["transport_fallback"] == "http"
    assert "parameter_error" in provider.last_call_trace["request"]


def test_llm_provider_text_call_falls_back_on_none_shape_error(monkeypatch):
    class _Client:
        def invoke(self, _messages, **_kwargs):
            raise AttributeError("'NoneType' object has no attribute 'get'")

    provider = OpenAICompatibleProvider(LLMConfig(api_key="test-key"))
    provider._client = _Client()  # type: ignore[assignment]

    def _fake_http_fallback(_messages, **_kwargs):
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": None,
        }

    monkeypatch.setattr(provider, "_invoke_http_chat_completion", _fake_http_fallback)

    text = provider.invoke_text([{"role": "user", "content": "write"}], agent_id="author")

    assert text == "ok"
    assert provider.last_call_trace is not None
    assert provider.last_call_trace["request"]["call_type"] == "text"
    assert provider.last_call_trace["request"]["agent_id"] == "author"
    assert provider.last_call_trace["request"]["transport_fallback"] == "http"


def test_llm_provider_respects_configured_min_interval(monkeypatch):
    class _TextResponse:
        content = "ok"
        usage_metadata = {"input_tokens": 1, "output_tokens": 1}

    class _Client:
        def invoke(self, _messages, **_kwargs):
            return _TextResponse()

    clock = {"now": 100.0, "slept": []}

    def fake_time():
        return clock["now"]

    def fake_sleep(seconds):
        clock["slept"].append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr("novel_factory.llm.openai_compatible.time.time", fake_time)
    monkeypatch.setattr("novel_factory.llm.openai_compatible.time.sleep", fake_sleep)

    config = LLMConfig(api_key="test-key", min_interval_seconds=0.5)
    provider = OpenAICompatibleProvider(config)
    provider._client = _Client()  # type: ignore[assignment]

    assert provider.invoke_text([{"role": "user", "content": "one"}]) == "ok"
    assert provider.invoke_text([{"role": "user", "content": "two"}]) == "ok"

    assert clock["slept"] == [0.5]


def test_llm_json_sanitizer_quotes_unquoted_prose_values():
    raw = '''
    {
      "scene_beats": [
        {
          "sequence": 1,
          "scene_goal": "建立雾港",
          "turn": 林澈在广播中听见失踪者声音,
          "hook": "电话响起"
        }
      ]
    }
    '''
    sanitized = OpenAICompatibleProvider._sanitize_json(raw)

    assert '"turn": "林澈在广播中听见失踪者声音"' in sanitized
    assert json.loads(sanitized)["scene_beats"][0]["turn"] == "林澈在广播中听见失踪者声音"


def test_llm_json_extractor_accepts_markdown_fenced_json_variants():
    fenced = '''``` json
    {
      "patches": [
        {"target_table": "characters", "operation": "create"}
      ]
    }
    ```'''
    unclosed = '''```JSON
    {
      "patches": [
        {"target_table": "story_facts", "operation": "create"}
      ]
    }'''

    fenced_data = json.loads(OpenAICompatibleProvider._extract_json(fenced))
    unclosed_data = json.loads(OpenAICompatibleProvider._extract_json(unclosed))

    assert fenced_data["patches"][0]["target_table"] == "characters"
    assert unclosed_data["patches"][0]["target_table"] == "story_facts"


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
    approve_resp = client.post(f"/api/projects/budget-auto/genesis/{genesis_id}/approve", json={
        "force_apply": True,
        "confirm_quality_risk": True,
    })
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
