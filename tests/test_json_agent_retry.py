"""Tests for JSON agent retry logic in OpenAI-compatible provider (v6.6.21)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from novel_factory.llm.openai_compatible import (
    InvalidAPIKeyError,
    LLMConnectionError,
    LLMError,
    LLMTimeoutError,
    OpenAICompatibleProvider,
    OutputValidationError,
    RateLimitError,
)
from novel_factory.llm.provider import LLMProvider
from novel_factory.config.settings import LLMConfig


class _MockResponse:
    """Mock LangChain response with content."""

    def __init__(self, content: str):
        self.content = content
        self.usage_metadata = None
        self.response_metadata = {}


class TestInvokeJsonRetry:
    """Test 3-tier JSON retry strategy in invoke_json."""

    def _make_provider(self) -> OpenAICompatibleProvider:
        provider = OpenAICompatibleProvider(
            config=LLMConfig(
                provider="openai",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                model="gpt-4",
            )
        )
        return provider

    def test_first_attempt_success(self):
        """Valid JSON on first attempt returns immediately."""
        provider = self._make_provider()
        mock_response = _MockResponse('{"ok": true, "data": "first"}')

        with patch.object(provider, "_invoke_with_retry", return_value=mock_response):
            result = provider.invoke_json(
                [{"role": "user", "content": "test"}],
                agent_id="test_agent",
            )

        assert result == {"ok": True, "data": "first"}

    def test_second_attempt_after_first_parse_fail(self):
        """First bad JSON, second good JSON -> success with 2 LLM calls."""
        provider = self._make_provider()
        responses = [
            _MockResponse('not json at all'),
            _MockResponse('{"ok": true, "data": "second"}'),
        ]
        call_count = 0

        def _mock_invoke(*args, **kwargs):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            return resp

        with patch.object(provider, "_invoke_with_retry", side_effect=_mock_invoke):
            result = provider.invoke_json(
                [{"role": "user", "content": "test"}],
                max_retries=2,
                agent_id="test_agent",
            )

        assert result == {"ok": True, "data": "second"}
        assert call_count == 2

    def test_third_attempt_repair_only(self):
        """First two bad, third good -> success with 3 LLM calls."""
        provider = self._make_provider()
        responses = [
            _MockResponse('bad json 1'),
            _MockResponse('bad json 2'),
            _MockResponse('{"ok": true, "data": "third"}'),
        ]
        call_count = 0

        def _mock_invoke(*args, **kwargs):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            return resp

        with patch.object(provider, "_invoke_with_retry", side_effect=_mock_invoke):
            result = provider.invoke_json(
                [{"role": "user", "content": "test"}],
                max_retries=2,
                agent_id="test_agent",
            )

        assert result == {"ok": True, "data": "third"}
        assert call_count == 3

    def test_all_attempts_fail_raises_with_diagnostics(self):
        """All JSON parse attempts fail -> OutputValidationError with agent info."""
        provider = self._make_provider()

        with patch.object(
            provider, "_invoke_with_retry", return_value=_MockResponse('always broken')
        ):
            with pytest.raises(OutputValidationError) as exc_info:
                provider.invoke_json(
                    [{"role": "user", "content": "test"}],
                    max_retries=2,
                    agent_id="screenwriter",
                    schema=type("ScreenwriterOutput", (), {}),
                )

        error_str = str(exc_info.value)
        assert "screenwriter" in error_str
        assert "ScreenwriterOutput" in error_str
        assert "attempt 3/3" in error_str

    def test_temperature_zero_on_final_attempt(self):
        """Final repair attempt forces temperature=0."""
        provider = self._make_provider()
        captured_kwargs: list[dict] = []

        def _mock_invoke(*args, **kwargs):
            captured_kwargs.append(kwargs)
            return _MockResponse('{"ok": true}')

        with patch.object(provider, "_invoke_with_retry", side_effect=_mock_invoke):
            provider.invoke_json(
                [{"role": "user", "content": "test"}],
                max_retries=2,
                temperature=0.5,
            )

        # Only 1 call since first attempt succeeds
        assert len(captured_kwargs) == 1
        assert captured_kwargs[0]["temperature"] == 0.5

        # Now force 3 calls
        captured_kwargs.clear()
        responses = [
            _MockResponse('bad'),
            _MockResponse('bad'),
            _MockResponse('{"ok": true}'),
        ]
        call_idx = 0

        def _mock_invoke2(*args, **kwargs):
            nonlocal call_idx
            captured_kwargs.append(kwargs)
            resp = responses[call_idx]
            call_idx += 1
            return resp

        with patch.object(provider, "_invoke_with_retry", side_effect=_mock_invoke2):
            provider.invoke_json(
                [{"role": "user", "content": "test"}],
                max_retries=2,
                temperature=None,
            )

        # Third call (index 2) should have temperature=0
        assert len(captured_kwargs) == 3
        assert captured_kwargs[2].get("temperature") == 0.0


class TestInvokeJsonResponseFormat:
    """Test structured output hint passing."""

    def _make_provider(self) -> OpenAICompatibleProvider:
        return OpenAICompatibleProvider(
            config=LLMConfig(
                provider="openai",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                model="gpt-4",
            )
        )

    def test_response_format_passed_when_schema_given(self):
        """response_format should be in kwargs when schema is provided."""
        provider = self._make_provider()
        captured_kwargs: dict = {}

        def _mock_invoke(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return _MockResponse('{"ok": true}')

        with patch.object(provider, "_invoke_with_retry", side_effect=_mock_invoke):
            provider.invoke_json(
                [{"role": "user", "content": "test"}],
                schema=type("TestSchema", (), {}),
            )

        assert captured_kwargs.get("response_format") == {"type": "json_object"}

    def test_no_response_format_without_schema(self):
        """response_format should not be added when no schema."""
        provider = self._make_provider()
        captured_kwargs: dict = {}

        def _mock_invoke(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return _MockResponse('{"ok": true}')

        with patch.object(provider, "_invoke_with_retry", side_effect=_mock_invoke):
            provider.invoke_json([{"role": "user", "content": "test"}])

        # response_format should not be set (or at least not the json_object hint)
        # because the schema-based extra message is also skipped
        assert "response_format" not in captured_kwargs or captured_kwargs.get("response_format") is None


class TestResponseFormatFallback:
    """v6.6.21-review: Test response_format fallback when provider doesn't support it."""

    def _make_provider(self) -> OpenAICompatibleProvider:
        return OpenAICompatibleProvider(
            config=LLMConfig(
                provider="openai",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                model="gpt-4",
            )
        )

    def test_fallback_on_unsupported_response_format(self):
        """When provider rejects response_format, fallback to plain JSON call succeeds."""
        provider = self._make_provider()
        captured_kwargs_list: list[dict] = []

        def _mock_invoke(*args, **kwargs):
            captured_kwargs_list.append(dict(kwargs))
            if "response_format" in kwargs:
                # Simulate provider rejecting response_format
                raise LLMError("unsupported parameter: response_format")
            return _MockResponse('{"ok": true, "data": "fallback_success"}')

        with patch.object(provider, "_invoke_with_retry", side_effect=_mock_invoke):
            result = provider.invoke_json(
                [{"role": "user", "content": "test"}],
                schema=type("TestSchema", (), {}),
                agent_id="test_fallback",
            )

        # Should succeed after fallback
        assert result == {"ok": True, "data": "fallback_success"}
        # Two calls: first with response_format, second without
        assert len(captured_kwargs_list) == 2
        assert "response_format" in captured_kwargs_list[0]
        assert "response_format" not in captured_kwargs_list[1]

    def test_fallback_on_raw_exception_unsupported_parameter(self):
        """Raw exception (not LLMError) with unsupported parameter also triggers fallback."""
        provider = self._make_provider()
        call_count = 0

        def _mock_invoke(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TypeError("got an unexpected keyword argument 'response_format'")
            return _MockResponse('{"ok": true}')

        with patch.object(provider, "_invoke_with_retry", side_effect=_mock_invoke):
            result = provider.invoke_json(
                [{"role": "user", "content": "test"}],
                schema=type("TestSchema", (), {}),
            )

        assert result == {"ok": True}
        assert call_count == 2

    def test_no_fallback_on_auth_error(self):
        """Auth/balance/timeout/rate-limit errors must NOT be treated as response_format fallback."""
        provider = self._make_provider()

        with patch.object(
            provider, "_invoke_with_retry",
            side_effect=InvalidAPIKeyError("API Key 无效"),
        ):
            with pytest.raises(InvalidAPIKeyError):
                provider.invoke_json(
                    [{"role": "user", "content": "test"}],
                    schema=type("TestSchema", (), {}),
                )

    def test_no_fallback_on_timeout_error(self):
        """Timeout errors must NOT be treated as response_format fallback."""
        provider = self._make_provider()

        with patch.object(
            provider, "_invoke_with_retry",
            side_effect=LLMTimeoutError("LLM 响应超时"),
        ):
            with pytest.raises(LLMTimeoutError):
                provider.invoke_json(
                    [{"role": "user", "content": "test"}],
                    schema=type("TestSchema", (), {}),
                )

    def test_no_fallback_on_rate_limit_error(self):
        """Rate limit errors must NOT be treated as response_format fallback."""
        provider = self._make_provider()

        with patch.object(
            provider, "_invoke_with_retry",
            side_effect=RateLimitError("API 请求频率超限"),
        ):
            with pytest.raises(RateLimitError):
                provider.invoke_json(
                    [{"role": "user", "content": "test"}],
                    schema=type("TestSchema", (), {}),
                )

    def test_no_fallback_on_connection_error(self):
        """Connection errors must NOT be treated as response_format fallback."""
        provider = self._make_provider()

        with patch.object(
            provider, "_invoke_with_retry",
            side_effect=LLMConnectionError("LLM 网络连接失败"),
        ):
            with pytest.raises(LLMConnectionError):
                provider.invoke_json(
                    [{"role": "user", "content": "test"}],
                    schema=type("TestSchema", (), {}),
                )

    def test_fallback_does_not_consume_json_retry(self):
        """response_format fallback should NOT consume a JSON parse retry attempt."""
        provider = self._make_provider()
        call_count = 0

        def _mock_invoke(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise LLMError("unsupported parameter: response_format")
            return _MockResponse('{"ok": true}')

        with patch.object(provider, "_invoke_with_retry", side_effect=_mock_invoke):
            result = provider.invoke_json(
                [{"role": "user", "content": "test"}],
                schema=type("TestSchema", (), {}),
                max_retries=2,
            )

        assert result == {"ok": True}
        # Only 2 calls total (1 failed + 1 success), NOT 3 — fallback didn't consume a JSON retry
        assert call_count == 2


class TestAgentIdInDiagnostics:
    """v6.6.21-review: Test agent_id propagation in invoke_json diagnostics."""

    def _make_provider(self) -> OpenAICompatibleProvider:
        return OpenAICompatibleProvider(
            config=LLMConfig(
                provider="openai",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                model="gpt-4",
            )
        )

    def test_agent_id_in_trace(self):
        """agent_id should appear in last_call_trace when set by invoke_json."""
        provider = self._make_provider()

        def _mock_invoke(*args, **kwargs):
            # Simulate what _invoke_with_retry does: set last_call_trace
            provider.last_call_trace = {"request": kwargs, "response": None, "error": None}
            return _MockResponse('{"ok": true}')

        with patch.object(provider, "_invoke_with_retry", side_effect=_mock_invoke):
            provider.invoke_json(
                [{"role": "user", "content": "test"}],
                agent_id="screenwriter",
            )

        # invoke_json updates last_call_trace with agent_id after _invoke_with_retry
        assert provider.last_call_trace is not None
        assert provider.last_call_trace.get("request", {}).get("agent_id") == "screenwriter"

    def test_agent_id_in_parse_failure(self):
        """JSON parse failure error message must contain agent_id and schema_name."""
        provider = self._make_provider()

        with patch.object(provider, "_invoke_with_retry", return_value=_MockResponse('not json')):
            with pytest.raises(OutputValidationError) as exc_info:
                provider.invoke_json(
                    [{"role": "user", "content": "test"}],
                    schema=type("ScreenwriterOutput", (), {}),
                    max_retries=2,
                    agent_id="screenwriter",
                )

        error_str = str(exc_info.value)
        assert "screenwriter" in error_str
        assert "ScreenwriterOutput" in error_str
