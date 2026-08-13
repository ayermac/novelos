"""v6.11.01: Stable fault-tolerance tests for OpenAICompatibleProvider.

Covers the retry / SDK→HTTP fallback / finish_reason=length truncation /
empty-stream fallback paths of ``novel_factory/llm/openai_compatible.py``
without making real network calls. A fake chat client is injected via
``provider._client`` and the HTTP fallback is monkeypatched, so these tests
are hermetic and fast.

See docs/codex/planning/novel-factory-v6.11.01-architecture-debt-optimization-plan.md (P2 M5).
"""

from __future__ import annotations

import pytest

from novel_factory.config.settings import LLMConfig
from novel_factory.llm.openai_compatible import (
    LLMConnectionError,
    LLMError,
    OpenAICompatibleProvider,
    _NormalizedChatResponse,
)


def _config() -> LLMConfig:
    """Fast, hermetic config: no waits, no real timeouts."""
    return LLMConfig(
        api_key="test-key",
        model="fake-model",
        request_timeout_seconds=0,
        retry_attempts=3,
        retry_min_seconds=0,
        retry_max_seconds=0,
        min_interval_seconds=0,
    )


class FakeResponse:
    """Minimal response object matching the fields the provider reads."""

    def __init__(self, content: str = "ok", finish_reason: str = "stop", pt: int = 1, ct: int = 2):
        self.content = content
        self.usage_metadata = {"input_tokens": pt, "output_tokens": ct, "total_tokens": pt + ct}
        self.response_metadata = {"finish_reason": finish_reason}


class FakeClient:
    """Replays a scripted sequence of results/exceptions from ``invoke``."""

    def __init__(self, behaviors):
        self._behaviors = list(behaviors)
        self.call_count = 0

    def invoke(self, messages, **kwargs):
        self.call_count += 1
        if not self._behaviors:
            return FakeResponse()
        item = self._behaviors.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _provider_with(behaviors) -> tuple[OpenAICompatibleProvider, FakeClient]:
    provider = OpenAICompatibleProvider(_config())
    fake = FakeClient(behaviors)
    provider._client = fake  # bypass lazy ChatOpenAI construction
    return provider, fake


# ── Retry ───────────────────────────────────────────────────────────


def test_retry_then_success_on_transient_connection_error():
    provider, fake = _provider_with([LLMConnectionError("temp fail"), FakeResponse("recovered")])
    text = provider.invoke_text([{"role": "user", "content": "hi"}], agent_id="test")
    assert text == "recovered"
    assert fake.call_count == 2  # first failed (retried), second succeeded


def test_retry_exhausted_reraises_after_max_attempts():
    # retry_attempts=3 → 3 attempts then reraise the last transient error
    provider, fake = _provider_with([LLMConnectionError("e1"), LLMConnectionError("e2"), LLMConnectionError("e3")])
    with pytest.raises(LLMConnectionError):
        provider.invoke_text([{"role": "user", "content": "hi"}], agent_id="test")
    assert fake.call_count == 3


# ── SDK → HTTP transport fallback ───────────────────────────────────


def test_sdk_shape_error_triggers_http_fallback(monkeypatch):
    provider, fake = _provider_with([AttributeError("object has no attribute 'choices'")])

    def fake_http(self, lc_messages, request_timeout_seconds=None, **kwargs):
        return _NormalizedChatResponse("http-fallback", response_metadata={"finish_reason": "stop"})

    monkeypatch.setattr(OpenAICompatibleProvider, "_invoke_http_chat_completion", fake_http)

    text = provider.invoke_text([{"role": "user", "content": "hi"}], agent_id="test")
    assert text == "http-fallback"
    assert provider.last_call_trace["request"].get("transport_fallback") == "http"
    assert fake.call_count == 1  # SDK attempted once, then HTTP fallback took over


# ── Truncation detection ────────────────────────────────────────────


def test_finish_reason_length_raises_truncation_error():
    provider, _ = _provider_with([FakeResponse("partial...", finish_reason="length")])
    with pytest.raises(LLMError, match="被截断"):
        provider.invoke_text([{"role": "user", "content": "hi"}], agent_id="test")


def test_normal_finish_reason_stop_returns_content():
    provider, _ = _provider_with([FakeResponse("hello world", finish_reason="stop")])
    text = provider.invoke_text([{"role": "user", "content": "hi"}], agent_id="test")
    assert text == "hello world"


# ── Empty-stream fallback ───────────────────────────────────────────


def test_empty_stream_falls_back_to_non_stream(monkeypatch):
    # Streaming yields empty content → provider must fall back to invoke_text,
    # which uses the fake client to return "recovered-text".
    provider, fake = _provider_with([FakeResponse("recovered-text", finish_reason="stop")])

    monkeypatch.setattr(
        "novel_factory.llm.openai_streaming.stream_text",
        lambda *a, **k: ("", 0, 0, 0),
    )

    text = provider.invoke_text_stream(
        [{"role": "user", "content": "hi"}],
        agent_id="test",
        on_chunk=lambda c: None,
    )
    assert text == "recovered-text"
    # The fallback invoked the (fake) non-stream client exactly once.
    assert fake.call_count == 1


def test_streaming_parameter_error_falls_back_to_text(monkeypatch):
    # A provider that rejects streaming params should fall back to invoke_text.
    provider, fake = _provider_with([FakeResponse("text-mode", finish_reason="stop")])

    def boom(*a, **k):
        raise RuntimeError("400 BadRequest: streaming unsupported parameter")

    monkeypatch.setattr("novel_factory.llm.openai_streaming.stream_text", boom)

    text = provider.invoke_text_stream(
        [{"role": "user", "content": "hi"}],
        agent_id="test",
        on_chunk=lambda c: None,
    )
    assert text == "text-mode"
    # The fallback invoked the (fake) non-stream client exactly once.
    # (last_call_trace is overwritten by invoke_text, so we cannot assert the
    # streaming_fallback flag here; the warning log + call_count prove the
    # fallback path executed.)
    assert fake.call_count == 1
