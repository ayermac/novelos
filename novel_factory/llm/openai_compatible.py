"""OpenAI-compatible LLM provider.

Works with OpenAI, OpenRouter, 火山方舟 and any OpenAI-compatible API.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import time
from typing import Any

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from tenacity import (
    Retrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config.settings import LLMConfig
from .provider import LLMProvider
from ..security.redaction import redact_sensitive_text

logger = logging.getLogger(__name__)


# Custom exceptions with Chinese messages
class LLMError(Exception):
    """Base LLM error with Chinese message."""
    pass


class InvalidAPIKeyError(LLMError):
    """API Key 无效或已过期."""
    pass


class InsufficientBalanceError(LLMError):
    """API 余额不足."""
    pass


class LLMTimeoutError(LLMError):
    """LLM 响应超时."""
    pass


class RateLimitError(LLMError):
    """API 请求频率超限."""
    pass


class LLMConnectionError(LLMError):
    """LLM 网络连接暂时失败."""
    pass


class OutputValidationError(LLMError):
    """LLM 输出校验失败."""
    pass


class TokenUsage:
    """Token usage statistics."""

    def __init__(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        duration_ms: int = 0,
    ):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
        self.duration_ms = duration_ms

    def to_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "duration_ms": self.duration_ms,
        }


class _NormalizedChatResponse:
    """Small response adapter matching the fields used by this provider."""

    def __init__(
        self,
        content: str,
        usage_metadata: dict[str, int] | None = None,
        response_metadata: dict[str, Any] | None = None,
    ) -> None:
        self.content = content
        self.usage_metadata = usage_metadata or {}
        self.response_metadata = response_metadata or {}


def _message_to_dict(message: Any) -> dict[str, Any]:
    """Convert LangChain or plain message objects to loggable dicts."""
    if isinstance(message, dict):
        return {
            "role": str(message.get("role", "user")),
            "content": redact_sensitive_text(str(message.get("content", ""))),
        }
    role = getattr(message, "type", None) or getattr(message, "role", None) or message.__class__.__name__
    content = getattr(message, "content", "")
    return {"role": str(role), "content": redact_sensitive_text(str(content))}


class OpenAICompatibleProvider(LLMProvider):
    """LLM provider using OpenAI-compatible API via LangChain."""

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig()
        self._client: BaseChatModel | None = None
        self.last_token_usage: TokenUsage | None = None
        self.last_call_trace: dict[str, Any] | None = None
        self._last_call_started_at: float | None = None

    @property
    def client(self) -> BaseChatModel:
        """Lazy-init the LangChain ChatOpenAI client."""
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _build_client(self, request_timeout_seconds: int | None = None) -> BaseChatModel:
        """Build a ChatOpenAI client, optionally using a per-call timeout."""
        timeout = request_timeout_seconds or self.config.request_timeout_seconds
        return ChatOpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key or "sk-placeholder",
            model=self.config.model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            request_timeout=timeout,
            http_client=httpx.Client(timeout=timeout, trust_env=False),
            http_async_client=httpx.AsyncClient(timeout=timeout, trust_env=False),
            # Keep retry policy centralized in _invoke_with_retry so provider
            # behavior is predictable across OpenAI-compatible backends.
            max_retries=0,
        )

    def _to_lc_messages(self, messages: list[dict[str, str]]) -> list:
        """Convert dict messages to LangChain message objects."""
        result = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                result.append(SystemMessage(content=content))
            else:
                result.append(HumanMessage(content=content))
        return result

    def _normalize_chat_response(self, response: Any) -> Any:
        """Normalize raw string/dict responses into the minimal AIMessage shape.

        Some OpenAI-compatible gateways work over direct HTTP but trip
        LangChain/OpenAI SDK response parsing. Keep the rest of the provider on
        one response contract: content + optional usage/metadata.
        """
        if response is None:
            return _NormalizedChatResponse("")
        if hasattr(response, "content"):
            return response
        if isinstance(response, (str, dict)):
            return self._response_from_http_payload(response)
        return _NormalizedChatResponse(str(response))

    @staticmethod
    def _is_langchain_response_shape_error(error: Exception) -> bool:
        """Return true for SDK/LangChain parser crashes on malformed choices."""
        error_str = str(error).lower()
        return any(
            pattern in error_str
            for pattern in (
                "object has no attribute 'choices'",
                'object has no attribute "choices"',
                "object has no attribute 'model_dump'",
                'object has no attribute "model_dump"',
                "response missing `choices` key",
                "'nonetype' object has no attribute",
                "none has no attribute",
            )
        )

    @staticmethod
    def _lc_message_to_openai_payload(message: Any) -> dict[str, Any]:
        if isinstance(message, dict):
            role = str(message.get("role", "user"))
            content = message.get("content", "")
        else:
            raw_role = getattr(message, "type", None) or getattr(message, "role", None) or "user"
            role = str(raw_role)
            content = getattr(message, "content", "")
        role_map = {"human": "user", "ai": "assistant", "system": "system"}
        return {"role": role_map.get(role, role), "content": content}

    @staticmethod
    def _content_to_text(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if text:
                        parts.append(str(text))
                elif item is not None:
                    parts.append(str(item))
            return "".join(parts)
        if isinstance(content, dict):
            text = content.get("text") or content.get("content")
            if text is not None:
                return str(text)
            return json.dumps(content, ensure_ascii=False)
        return str(content)

    def _response_from_http_payload(self, payload: Any) -> _NormalizedChatResponse:
        if payload is None:
            return _NormalizedChatResponse("")
        if isinstance(payload, str):
            return _NormalizedChatResponse(payload)

        choices = payload.get("choices") if isinstance(payload, dict) else None
        first_choice = choices[0] if isinstance(choices, list) and choices else {}
        message = first_choice.get("message", {}) if isinstance(first_choice, dict) else {}
        content = self._content_to_text(
            message.get("content") if isinstance(message, dict) else None
        )
        if not content and isinstance(first_choice, dict):
            content = self._content_to_text(first_choice.get("text"))

        usage = payload.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion_tokens = int(
            usage.get("completion_tokens") or usage.get("output_tokens") or 0
        )
        total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
        finish_reason = first_choice.get("finish_reason") if isinstance(first_choice, dict) else None

        return _NormalizedChatResponse(
            content=content,
            usage_metadata={
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            response_metadata={
                "token_usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                },
                "model_name": payload.get("model"),
                "id": payload.get("id"),
                "finish_reason": finish_reason,
            },
        )

    def _invoke_http_chat_completion(
        self,
        lc_messages: list,
        request_timeout_seconds: int | None = None,
        **kwargs,
    ) -> _NormalizedChatResponse:
        """Direct HTTP fallback for OpenAI-compatible chat completions."""
        import urllib.error
        import urllib.request

        base_url = self.config.base_url.rstrip("/")
        url = (
            base_url
            if base_url.endswith("/chat/completions")
            else f"{base_url}/chat/completions"
        )
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [self._lc_message_to_openai_payload(msg) for msg in lc_messages],
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
        }
        for key, value in kwargs.items():
            if key not in {"temperature", "max_tokens"}:
                payload[key] = value

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.config.api_key or 'sk-placeholder'}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        timeout = request_timeout_seconds or self.config.request_timeout_seconds
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {error.code}: {raw}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"connection error: {error.reason}") from error

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        if parsed is None:
            parsed = {}
        return self._response_from_http_payload(parsed)

    def _handle_api_error(self, error: Exception, timeout_seconds: int | None = None) -> None:
        """Convert API errors to Chinese error messages.

        Original error messages are redacted before inclusion in raised
        exceptions to prevent API keys or tokens from leaking.
        """
        error_str = str(error).lower()
        safe_error = redact_sensitive_text(str(error))

        # Check for common error patterns
        if "invalid" in error_str and "api" in error_str:
            raise InvalidAPIKeyError("API Key 无效或已过期，请检查配置") from error
        elif "unauthorized" in error_str or "401" in error_str:
            raise InvalidAPIKeyError("API Key 无效或已过期，请检查配置") from error
        elif "insufficient" in error_str or "quota" in error_str or "balance" in error_str:
            raise InsufficientBalanceError("API 余额不足，请充值后重试") from error
        elif "rate" in error_str or "limit" in error_str or "429" in error_str:
            raise RateLimitError("API 请求频率超限，请稍后重试") from error
        elif "timeout" in error_str or "timed out" in error_str:
            timeout = timeout_seconds or self.config.request_timeout_seconds
            raise LLMTimeoutError(
                f"LLM 响应超时（>{timeout}秒），请稍后重试"
            ) from error
        elif any(
            marker in error_str
            for marker in (
                "connection",
                "connect",
                "network",
                "temporarily",
                "reset by peer",
                "remote protocol",
                "decompress",
                "incorrect header check",
                "ssl",
                "tls",
                "read error",
                "write error",
            )
        ):
            raise LLMConnectionError(f"LLM 网络连接失败，请稍后重试: {safe_error}") from error
        else:
            raise LLMError(f"LLM 调用失败: {safe_error}") from error

    def _invoke_client_with_hard_timeout(
        self,
        client: BaseChatModel,
        lc_messages: list,
        timeout_seconds: int,
        **kwargs,
    ) -> Any:
        """Invoke the SDK client with a wall-clock timeout guard.

        Some OpenAI-compatible SDK paths can outlive their configured HTTPX
        timeout in desktop environments. Keep workflow runs bounded even when
        the underlying transport fails to return.
        """
        if timeout_seconds <= 0:
            return client.invoke(lc_messages, **kwargs)

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(client.invoke, lc_messages, **kwargs)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError as error:
            future.cancel()
            raise LLMTimeoutError(
                f"LLM 响应超时（>{timeout_seconds}秒），请稍后重试"
            ) from error
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _invoke_with_retry(
        self,
        lc_messages: list,
        max_retries: int | None = None,
        request_timeout_seconds: int | None = None,
        **kwargs,
    ) -> Any:
        """Invoke with exponential backoff for transient provider failures."""
        attempts = max(1, max_retries if max_retries is not None else self.config.retry_attempts)
        client = (
            self.client
            if request_timeout_seconds is None
            or request_timeout_seconds == self.config.request_timeout_seconds
            else self._build_client(request_timeout_seconds=request_timeout_seconds)
        )
        retryer = Retrying(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(
                multiplier=self.config.retry_min_seconds,
                min=self.config.retry_min_seconds,
                max=self.config.retry_max_seconds,
            ),
            retry=retry_if_exception_type((RateLimitError, LLMConnectionError)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )

        for attempt in retryer:
            with attempt:
                attempt_number = attempt.retry_state.attempt_number
                request_payload = {
                    "provider": self.config.provider,
                    "base_url": redact_sensitive_text(self.config.base_url),
                    "model": self.config.model,
                    "temperature": kwargs.get("temperature", self.config.temperature),
                    "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
                    "request_timeout_seconds": request_timeout_seconds or self.config.request_timeout_seconds,
                    "retry_attempts_configured": attempts,
                    "attempt_number": attempt_number,
                    "message_count": len(lc_messages),
                    "messages": [_message_to_dict(msg) for msg in lc_messages],
                    "kwargs": {
                        key: redact_sensitive_text(str(value))
                        for key, value in kwargs.items()
                    },
                }
                self.last_call_trace = {
                    "request": request_payload,
                    "response": None,
                    "error": None,
                }
                try:
                    interval = max(0.0, float(getattr(self.config, "min_interval_seconds", 0.0) or 0.0))
                    if interval > 0 and self._last_call_started_at is not None:
                        elapsed = time.time() - self._last_call_started_at
                        if elapsed < interval:
                            time.sleep(interval - elapsed)
                    start_time = time.time()
                    self._last_call_started_at = start_time
                    response = self._invoke_client_with_hard_timeout(
                        client,
                        lc_messages,
                        request_timeout_seconds or self.config.request_timeout_seconds,
                        **kwargs,
                    )
                    response = self._normalize_chat_response(response)
                    duration_ms = int((time.time() - start_time) * 1000)
                except (InvalidAPIKeyError, InsufficientBalanceError, LLMTimeoutError, RateLimitError, LLMConnectionError) as e:
                    if self.last_call_trace is not None:
                        self.last_call_trace["error"] = redact_sensitive_text(str(e))
                    raise
                except Exception as e:
                    if self._is_langchain_response_shape_error(e):
                        safe_error = redact_sensitive_text(str(e))
                        request_payload["transport_fallback"] = "http"
                        request_payload["langchain_error"] = safe_error
                        logger.warning(
                            "LangChain response parser failed; retrying via direct HTTP fallback model=%s attempt=%s error=%s",
                            self.config.model,
                            attempt_number,
                            safe_error,
                        )
                        try:
                            response = self._invoke_http_chat_completion(
                                lc_messages,
                                request_timeout_seconds=request_timeout_seconds,
                                **kwargs,
                            )
                            response = self._normalize_chat_response(response)
                            duration_ms = int((time.time() - start_time) * 1000)
                        except (InvalidAPIKeyError, InsufficientBalanceError, LLMTimeoutError, RateLimitError, LLMConnectionError) as fallback_error:
                            if self.last_call_trace is not None:
                                self.last_call_trace["error"] = redact_sensitive_text(str(fallback_error))
                            raise
                        except Exception as fallback_error:
                            if self.last_call_trace is not None:
                                self.last_call_trace["error"] = redact_sensitive_text(str(fallback_error))
                            self._handle_api_error(fallback_error, timeout_seconds=request_timeout_seconds)
                    else:
                        if self.last_call_trace is not None:
                            self.last_call_trace["error"] = redact_sensitive_text(str(e))
                        self._handle_api_error(e, timeout_seconds=request_timeout_seconds)

                # Extract token usage if available
                prompt_tokens = 0
                completion_tokens = 0
                total_tokens = 0

                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    prompt_tokens = response.usage_metadata.get("input_tokens", 0)
                    completion_tokens = response.usage_metadata.get("output_tokens", 0)
                    total_tokens = prompt_tokens + completion_tokens
                elif hasattr(response, "response_metadata"):
                    usage = response.response_metadata.get("token_usage", {})
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    total_tokens = usage.get("total_tokens", 0)

                self.last_token_usage = TokenUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    duration_ms=duration_ms,
                )
                response_text = redact_sensitive_text(str(getattr(response, "content", "")))
                response_payload = {
                    "content": response_text,
                    "content_preview": response_text[:2000],
                    "content_length": len(response_text),
                    "usage": self.last_token_usage.to_dict(),
                    "response_metadata": getattr(response, "response_metadata", None) or {},
                    "finish_reason": (
                        (getattr(response, "response_metadata", None) or {}).get("finish_reason")
                        or (getattr(response, "response_metadata", None) or {}).get("stop_reason")
                    ),
                    "attempt_number": attempt_number,
                    "duration_ms": duration_ms,
                }
                self.last_call_trace = {
                    "request": request_payload,
                    "response": response_payload,
                    "error": None,
                }
                logger.info(
                    "LLM call completed model=%s attempt=%s prompt_tokens=%s completion_tokens=%s total_tokens=%s duration_ms=%s",
                    self.config.model,
                    attempt_number,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    duration_ms,
                )

                return response

        raise LLMError("未知错误")

    # Patterns that indicate a provider does not support response_format
    _RESPONSE_FORMAT_UNSUPPORTED_PATTERNS: tuple[str, ...] = (
        "unsupported parameter",
        "unknown parameter",
        "extra fields not permitted",
        "response_format not supported",
        "response_format is not supported",
        "json_object` is not supported by this model",
        "json_object is not supported by this model",
        "unrecognized arguments",
        "got an unexpected keyword argument",
        "unexpected keyword argument",
    )

    def _is_response_format_unsupported_error(self, error: Exception) -> bool:
        """Check if an error indicates response_format is not supported by the provider.

        Only matches explicit parameter-incompatibility errors — never matches
        auth, balance, timeout, rate-limit, or network errors.
        """
        error_str = str(error).lower()
        return any(pat in error_str for pat in self._RESPONSE_FORMAT_UNSUPPORTED_PATTERNS)

    def invoke_json(
        self,
        messages: list[dict[str, str]],
        schema: type | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_retries: int = 2,
        agent_id: str = "unknown",
    ) -> dict[str, Any]:
        """Invoke LLM and parse JSON from the response with resilient retry.

        v6.6.21: 3-tier retry strategy:
        - Attempt 1: Normal JSON output with optional response_format hint.
        - Attempt 2: Append error details and ask model to re-emit full valid JSON.
        - Attempt 3: Provide raw previous output + schema, ask to repair JSON only.

        v6.6.21-review: response_format fallback — if a provider rejects
        response_format as an unsupported parameter, the error is caught and
        the call is retried without response_format. This fallback does NOT
        consume a JSON parse retry slot.

        Args:
            messages: Chat messages.
            schema: Optional Pydantic model for validation.
            temperature: Override temperature (attempt 3 forces 0).
            max_tokens: Override max tokens.
            max_retries: Max JSON parse retries (default 2 for 3 attempts total).
            agent_id: Agent name for diagnostics.
        """
        from .json_resilience import parse_json

        lc_messages = self._to_lc_messages(messages)

        kwargs: dict[str, Any] = {}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        schema_name = getattr(schema, "__name__", None) if schema else None

        # Attempt 1: Use structured output hint if supported
        if schema:
            kwargs["response_format"] = {"type": "json_object"}
            lc_messages.append(
                HumanMessage(
                    content="请严格按照 JSON 格式输出，不要包含任何其他文字。"
                )
            )

        last_raw_text: str = ""
        last_json_error: Exception | None = None
        max_attempts = max_retries + 1

        for attempt in range(max_attempts):
            try:
                # Force temperature=0 on final repair attempt
                call_kwargs = dict(kwargs)
                if attempt == max_attempts - 1 and temperature is None:
                    call_kwargs["temperature"] = 0.0

                response = self._invoke_with_retry(lc_messages, **call_kwargs)
                if self.last_call_trace is not None:
                    self.last_call_trace.setdefault("request", {})
                    self.last_call_trace["request"].update({
                        "call_type": "json",
                        "schema": schema_name,
                        "json_parse_attempt": attempt + 1,
                        "json_parse_max_attempts": max_attempts,
                        "agent_id": agent_id,
                    })
                text = response.content
                last_raw_text = text

                return parse_json(
                    text,
                    agent_id=agent_id,
                    schema_name=schema_name,
                    attempt=attempt + 1,
                    max_attempts=max_attempts,
                )
            except json.JSONDecodeError as e:
                last_json_error = e
                logger.warning(
                    "JSON parse failed (attempt %d/%d) agent=%s: %s",
                    attempt + 1, max_attempts, agent_id, e,
                )
                if attempt < max_attempts - 1:
                    if attempt == 0:
                        # Attempt 2: Ask model to re-emit with error context
                        lc_messages.append(HumanMessage(
                            content=(
                                f"你上一次输出的 JSON 解析失败，错误为: {e}\n"
                                "请重新输出完整、合法的 JSON，不要包含注释、尾逗号或 Markdown 标记。"
                            )
                        ))
                    else:
                        # Attempt 3+: Provide raw output and schema, ask to repair
                        raw_preview = last_raw_text[:1200]
                        lc_messages.append(HumanMessage(
                            content=(
                                f"你上一次输出仍无法解析。原始输出如下（请只修复 JSON 语法，"
                                f"不要修改内容含义）：\n\n{raw_preview}\n\n"
                                f"请输出修复后的完整合法 JSON。"
                            )
                        ))
                else:
                    logger.error(
                        "Failed to parse LLM JSON after %d attempts agent=%s: %s\nRaw (first 800 chars): %s",
                        max_attempts, agent_id, e, last_raw_text[:800],
                    )
                    raise OutputValidationError(
                        f"[{agent_id}] LLM 输出不是有效的 JSON 格式 (attempt {max_attempts}/{max_attempts}): {e}"
                    ) from e
            except (InvalidAPIKeyError, InsufficientBalanceError, LLMTimeoutError, RateLimitError, LLMConnectionError):
                raise
            except LLMError as e:
                # v6.6.21-review: response_format fallback
                # If provider rejects response_format as an unsupported parameter,
                # remove it and retry the SAME attempt (not consuming a JSON parse slot).
                if (
                    "response_format" in kwargs
                    and self._is_response_format_unsupported_error(e)
                ):
                    logger.warning(
                        "Provider does not support response_format, falling back to plain JSON call agent=%s: %s",
                        agent_id, e,
                    )
                    kwargs.pop("response_format")
                    if self.last_call_trace is not None:
                        self.last_call_trace.setdefault("request", {})
                        self.last_call_trace["request"]["response_format_fallback"] = True
                    # Retry same attempt without response_format — do NOT increment attempt
                    continue
                raise
            except Exception as e:
                # v6.6.21-review: Also check raw exceptions for response_format incompatibility
                # before routing through _handle_api_error which would wrap them as generic LLMError
                if (
                    "response_format" in kwargs
                    and self._is_response_format_unsupported_error(e)
                ):
                    logger.warning(
                        "Provider does not support response_format (raw exception), falling back agent=%s: %s",
                        agent_id, e,
                    )
                    kwargs.pop("response_format")
                    if self.last_call_trace is not None:
                        self.last_call_trace.setdefault("request", {})
                        self.last_call_trace["request"]["response_format_fallback"] = True
                    continue
                self._handle_api_error(e)

        raise OutputValidationError(
            f"[{agent_id}] LLM 输出不是有效的 JSON 格式: {last_json_error}"
        )

    def invoke_text(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_retries: int | None = None,
        request_timeout_seconds: int | None = None,
    ) -> str:
        """Invoke LLM and return raw text."""
        lc_messages = self._to_lc_messages(messages)

        kwargs: dict[str, Any] = {}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        try:
            response = self._invoke_with_retry(
                lc_messages,
                max_retries=max_retries,
                request_timeout_seconds=request_timeout_seconds,
                **kwargs,
            )
            if self.last_call_trace is not None:
                self.last_call_trace.setdefault("request", {})
                self.last_call_trace["request"].update({
                    "call_type": "text",
                })
            return response.content
        except (InvalidAPIKeyError, InsufficientBalanceError, LLMTimeoutError, RateLimitError, LLMConnectionError):
            raise
        except LLMError:
            raise
        except Exception as e:
            self._handle_api_error(e, timeout_seconds=request_timeout_seconds)

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON from potentially markdown-wrapped text."""
        import re

        # Strip BOM and leading/trailing whitespace
        text = text.lstrip("\ufeff").strip()

        # Try fenced blocks first. Models often return variants such as
        # ```json, ``` json, ```JSON, or even an unclosed fence.
        match = re.match(
            r"^\s*(```|~~~)[^\r\n]*[\r\n]+(.*?)(?:[\r\n]+\1\s*)?\s*$",
            text,
            re.DOTALL,
        )
        if match:
            text = match.group(2).strip()

        # If a fence appears later in explanatory text, prefer its body.
        match = re.search(
            r"(```|~~~)[^\r\n]*[\r\n]+(.*?)(?:[\r\n]+\1)",
            text,
            re.DOTALL,
        )
        if match:
            text = match.group(2).strip()

        # Try finding the first { ... } or [ ... ], respecting strings
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            start = text.find(start_char)
            if start != -1:
                depth = 0
                in_string = False
                escape_next = False
                for i in range(start, len(text)):
                    c = text[i]
                    if escape_next:
                        escape_next = False
                        continue
                    if c == "\\":
                        escape_next = True
                        continue
                    if c == '"':
                        in_string = not in_string
                        continue
                    if in_string:
                        continue
                    if c == start_char:
                        depth += 1
                    elif c == end_char:
                        depth -= 1
                    if depth == 0:
                        candidate = text[start : i + 1]
                        return OpenAICompatibleProvider._sanitize_json(candidate)

        # Fallback: return sanitized text
        return OpenAICompatibleProvider._sanitize_json(text.strip())

    @staticmethod
    def _sanitize_json(text: str) -> str:
        """Attempt to fix common LLM JSON output issues before parsing.

        Handles: trailing commas, single-quoted strings, JS-style comments,
        and unescaped newlines in strings.
        """
        import re

        # Remove JS-style single-line comments (// ...) outside of strings
        result_lines = []
        in_string = False
        for line in text.split("\n"):
            new_line = []
            escape_next = False
            i = 0
            while i < len(line):
                c = line[i]
                if escape_next:
                    new_line.append(c)
                    escape_next = False
                    i += 1
                    continue
                if c == "\\":
                    new_line.append(c)
                    escape_next = True
                    i += 1
                    continue
                if c == '"':
                    in_string = not in_string
                    new_line.append(c)
                    i += 1
                    continue
                if not in_string and c == "/" and i + 1 < len(line) and line[i + 1] == "/":
                    break
                new_line.append(c)
                i += 1
            result_lines.append("".join(new_line))
        text = "\n".join(result_lines)

        # Remove trailing commas before } or ]
        text = re.sub(r",\s*([}\]])", r"\1", text)

        # Replace single-quoted keys/values with double-quoted (simple heuristic)
        text = re.sub(r"(?<=[\[{,:\s])'([^']*)'(?=[\]},:\s])", r'"\1"', text)

        def quote_unquoted_value(match: re.Match) -> str:
            prefix = match.group(1)
            value = match.group(2).strip()
            if not value:
                return match.group(0)
            if value[0] in '"{[0123456789-tfn':
                return match.group(0)
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return f'{prefix}"{escaped}"'

        # Some models emit prose scalar values without quotes, for example:
        # {"turn": 林澈发现线索}. Wrap those values before json.loads().
        text = re.sub(
            r'(:[^\S\r\n]*)([^,\n\r}\]]+)(?=,|\n|\r|}|\])',
            quote_unquoted_value,
            text,
        )

        return text
