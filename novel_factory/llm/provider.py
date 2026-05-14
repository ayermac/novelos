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
    ) -> dict[str, Any]:
        """Invoke the LLM and return structured JSON output.

        Args:
            messages: Chat messages in [{"role": "...", "content": "..."}] format.
            schema: Optional Pydantic model class for structured output validation.
            temperature: Override default temperature.
            max_tokens: Override default max tokens.

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
    ) -> str:
        """Invoke the LLM and return raw text output.

        Args:
            messages: Chat messages.
            temperature: Override default temperature.
            max_tokens: Override default max tokens.

        Returns:
            Raw text response.
        """
        ...


def is_configured_live_provider(provider: Any) -> bool:
    """Return true for real provider instances that expose runtime config.

    ``MagicMock`` answers ``hasattr(mock, "config")`` as true for arbitrary
    attributes, so use this helper when deciding whether to take live-provider
    fast paths.
    """
    return not isinstance(provider, Mock) and getattr(provider, "config", None) is not None
