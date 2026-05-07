"""OpenAI-compatible LLM provider.

Works with OpenAI, OpenRouter, 火山方舟 and any OpenAI-compatible API.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..config.settings import LLMConfig
from .provider import LLMProvider

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


class OpenAICompatibleProvider(LLMProvider):
    """LLM provider using OpenAI-compatible API via LangChain."""

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig()
        self._client: BaseChatModel | None = None
        self.last_token_usage: TokenUsage | None = None

    @property
    def client(self) -> BaseChatModel:
        """Lazy-init the LangChain ChatOpenAI client."""
        if self._client is None:
            self._client = ChatOpenAI(
                base_url=self.config.base_url,
                api_key=self.config.api_key or "sk-placeholder",
                model=self.config.model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                request_timeout=60,  # 60 second timeout
            )
        return self._client

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

    def _handle_api_error(self, error: Exception) -> None:
        """Convert API errors to Chinese error messages."""
        error_str = str(error).lower()

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
            raise LLMTimeoutError("LLM 响应超时（>60秒），请稍后重试") from error
        else:
            raise LLMError(f"LLM 调用失败: {error}") from error

    def _invoke_with_retry(
        self,
        lc_messages: list,
        max_retries: int = 1,
        **kwargs,
    ) -> Any:
        """Invoke with automatic retry on rate limit or validation errors."""
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                start_time = time.time()
                response = self.client.invoke(lc_messages, **kwargs)
                duration_ms = int((time.time() - start_time) * 1000)

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

                return response

            except RateLimitError:
                # Retry rate limit errors
                last_error = RateLimitError("API 请求频率超限，请稍后重试")
                if attempt < max_retries:
                    logger.warning("Rate limit hit, retrying... (attempt %d/%d)", attempt + 1, max_retries)
                    time.sleep(2)  # Wait 2 seconds before retry
                    continue
                raise
            except Exception as e:
                self._handle_api_error(e)

        raise last_error or LLMError("未知错误")

    def invoke_json(
        self,
        messages: list[dict[str, str]],
        schema: type | None = None,
        temperature: float | None = None,
        max_retries: int = 1,
    ) -> dict[str, Any]:
        """Invoke LLM and parse JSON from the response.

        On JSON parse failure, retries up to *max_retries* times with an
        explicit correction prompt appended.
        """
        lc_messages = self._to_lc_messages(messages)

        kwargs: dict[str, Any] = {}
        if temperature is not None:
            kwargs["temperature"] = temperature

        # Add JSON instruction to the last user message if schema is given
        if schema:
            lc_messages.append(
                HumanMessage(
                    content="请严格按照 JSON 格式输出，不要包含任何其他文字。"
                )
            )

        last_json_error: json.JSONDecodeError | None = None
        for attempt in range(max_retries + 1):
            try:
                response = self._invoke_with_retry(lc_messages, max_retries=1, **kwargs)
                text = response.content
                json_str = self._extract_json(text)
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                last_json_error = e
                logger.warning(
                    "JSON parse failed (attempt %d/%d): %s | near: ...%s...",
                    attempt + 1, max_retries + 1, e,
                    text[max(0, e.pos - 40):e.pos + 40] if hasattr(e, "pos") and e.pos else text[:80],
                )
                if attempt < max_retries:
                    # Append a correction prompt and retry
                    lc_messages.append(HumanMessage(
                        content=(
                            f"你上一次输出的 JSON 解析失败，错误为: {e}\n"
                            "请重新输出完整、合法的 JSON，不要包含注释、尾逗号或 Markdown 标记。"
                        )
                    ))
                else:
                    logger.error(
                        "Failed to parse LLM JSON after %d attempts: %s\nRaw (first 800 chars): %s",
                        max_retries + 1, e, text[:800],
                    )
                    raise OutputValidationError(f"LLM 输出不是有效的 JSON 格式: {e}") from e
            except (InvalidAPIKeyError, InsufficientBalanceError, LLMTimeoutError, RateLimitError):
                raise
            except LLMError:
                raise
            except Exception as e:
                self._handle_api_error(e)

        raise OutputValidationError(f"LLM 输出不是有效的 JSON 格式: {last_json_error}")

    def invoke_text(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Invoke LLM and return raw text."""
        lc_messages = self._to_lc_messages(messages)

        kwargs: dict[str, Any] = {}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        try:
            response = self._invoke_with_retry(lc_messages, max_retries=1, **kwargs)
            return response.content
        except (InvalidAPIKeyError, InsufficientBalanceError, LLMTimeoutError, RateLimitError):
            raise
        except LLMError:
            raise
        except Exception as e:
            self._handle_api_error(e)

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON from potentially markdown-wrapped text."""
        import re

        # Strip BOM and leading/trailing whitespace
        text = text.lstrip("\ufeff").strip()

        # Try ```json ... ``` first
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if match:
            candidate = match.group(1).strip()
            return OpenAICompatibleProvider._sanitize_json(candidate)

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

        return text
