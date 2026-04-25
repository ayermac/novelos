"""OpenAI-compatible LLM provider.

Works with OpenAI, OpenRouter, 火山方舟 and any OpenAI-compatible API.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..config.settings import LLMConfig
from .provider import LLMProvider

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(LLMProvider):
    """LLM provider using OpenAI-compatible API via LangChain."""

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig()
        self._client: BaseChatModel | None = None

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

    def invoke_json(
        self,
        messages: list[dict[str, str]],
        schema: type | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Invoke LLM and parse JSON from the response."""
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

        try:
            response = self.client.invoke(lc_messages, **kwargs)
            text = response.content
            # Try to extract JSON from markdown code blocks
            json_str = self._extract_json(text)
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM JSON output: %s\nRaw: %s", e, text[:500])
            raise ValueError(f"LLM output is not valid JSON: {e}") from e

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

        response = self.client.invoke(lc_messages, **kwargs)
        return response.content

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON from potentially markdown-wrapped text."""
        # Try ```json ... ``` first
        import re

        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Try finding the first { ... } or [ ... ]
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            start = text.find(start_char)
            if start != -1:
                depth = 0
                for i in range(start, len(text)):
                    if text[i] == start_char:
                        depth += 1
                    elif text[i] == end_char:
                        depth -= 1
                    if depth == 0:
                        return text[start : i + 1]

        # Fallback: return as-is
        return text.strip()
