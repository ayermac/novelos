"""Base LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def invoke_json(
        self,
        messages: list[dict[str, str]],
        schema: type | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Invoke the LLM and return structured JSON output.

        Args:
            messages: Chat messages in [{"role": "...", "content": "..."}] format.
            schema: Optional Pydantic model class for structured output validation.
            temperature: Override default temperature.

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
