"""Base LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from unittest.mock import Mock


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def invoke_json(
        self,
        messages: list[dict[str, str]],
        schema: type | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        agent_id: str = "unknown",
    ) -> dict[str, Any]:
        """Invoke the LLM and return structured JSON output.

        Args:
            messages: Chat messages in [{"role": "...", "content": "..."}] format.
            schema: Optional Pydantic model class for structured output validation.
            temperature: Override default temperature.
            max_tokens: Override default max tokens.
            agent_id: Agent name for diagnostic messages and retry prompts.

        Returns:
            Parsed JSON dict.
        """
        ...

    @abstractmethod
    def invoke_text(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_retries: int | None = None,
        request_timeout_seconds: int | None = None,
        agent_id: str = "unknown",
    ) -> str:
        """Invoke the LLM and return raw text output.

        Args:
            messages: Chat messages.
            temperature: Override default temperature.
            max_tokens: Override default max tokens.
            max_retries: Override provider retry attempts for this call.
            request_timeout_seconds: Override request timeout for this call.
            agent_id: Agent name for diagnostics.

        Returns:
            Raw text response.
        """
        ...

    def invoke_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[Any],
        tool_choice: str = "auto",
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> Any:
        """Invoke the LLM with tool/function calling support (v6.10.0).

        Args:
            messages: Chat messages.
            tools: List of ToolDefinition objects.
            tool_choice: "auto", "none", or "required".
            temperature: Override default temperature.
            max_tokens: Override default max tokens.

        Returns:
            ToolCallResponse with content and/or tool_calls.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support invoke_with_tools()"
        )

    def invoke_text_stream(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        agent_id: str = "unknown",
        on_chunk: Any = None,
        **kwargs: Any,
    ) -> str:
        """v6.10.0: Invoke LLM with streaming, calling on_chunk for each token.

        Args:
            messages: Chat messages.
            temperature: Override default temperature.
            max_tokens: Override default max tokens.
            agent_id: Agent name for diagnostics.
            on_chunk: Callback(chunk_text: str) called for each streaming chunk.

        Returns:
            Complete text response (accumulated from all chunks).
        """
        # Default fallback: call non-streaming and invoke on_chunk once
        result = self.invoke_text(
            messages, temperature=temperature, max_tokens=max_tokens, agent_id=agent_id,
            request_timeout_seconds=kwargs.get("request_timeout_seconds"),
        )
        if on_chunk:
            on_chunk(result)
        return result


def is_configured_live_provider(provider: Any) -> bool:
    """Return true for real provider instances that expose runtime config.

    ``MagicMock`` answers ``hasattr(mock, "config")`` as true for arbitrary
    attributes, so use this helper when deciding whether to take live-provider
    fast paths.
    """
    return not isinstance(provider, Mock) and getattr(provider, "config", None) is not None
