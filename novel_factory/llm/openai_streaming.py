"""Streaming and tool-calling helpers for OpenAI-compatible providers."""

from __future__ import annotations

import time
from typing import Any

from .types import ToolCall, ToolCallResponse


def stream_text(
    client,
    to_lc_messages,
    messages: list[dict[str, str]],
    temperature: float | None = None,
    max_tokens: int | None = None,
    agent_id: str = "unknown",
    on_chunk: Any = None,
) -> tuple[str, int, int, int]:
    """Stream text from LLM. Returns (full_content, prompt_tokens, completion_tokens, duration_ms)."""
    lc_messages = to_lc_messages(messages)
    call_kwargs: dict[str, Any] = {}
    if temperature is not None:
        call_kwargs["temperature"] = temperature
    if max_tokens is not None:
        call_kwargs["max_tokens"] = max_tokens

    start_ts = time.time()
    chunks: list[str] = []
    for chunk in client.stream(lc_messages, **call_kwargs):
        text = chunk.content if hasattr(chunk, "content") else str(chunk)
        if text:
            chunks.append(text)
            if on_chunk:
                try:
                    on_chunk(text)
                except Exception:
                    pass

    full_content = "".join(chunks)
    duration_ms = int((time.time() - start_ts) * 1000)
    # Chinese text ~1.5-2 tokens/char, English ~4 chars/token
    # Use 2 chars/token as rough estimate for mixed content
    prompt_text = "".join(str(m.get("content", "")) for m in messages)
    prompt_tokens = max(1, len(prompt_text) // 2)
    completion_tokens = max(1, len(full_content) // 2)
    return full_content, prompt_tokens, completion_tokens, duration_ms


def call_with_tools(
    client,
    to_lc_messages,
    messages: list[dict[str, Any]],
    tools: list[Any],
    tool_choice: str = "auto",
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> ToolCallResponse:
    """Invoke LLM with tool calling support."""
    lc_messages = to_lc_messages(messages)
    lc_tools = [
        {
            "type": "function",
            "function": {
                "name": td.name,
                "description": td.description,
                "parameters": td.parameters or {"type": "object", "properties": {}},
            },
        }
        for td in tools
    ]

    llm_with_tools = client.bind_tools(lc_tools, tool_choice=tool_choice)
    call_kwargs: dict[str, Any] = {}
    if temperature is not None:
        call_kwargs["temperature"] = temperature
    if max_tokens is not None:
        call_kwargs["max_tokens"] = max_tokens

    response = llm_with_tools.invoke(lc_messages, **call_kwargs)

    tool_calls = []
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tc in response.tool_calls:
            tool_calls.append(ToolCall(
                id=tc.get("id", f"call_{tc['name']}"),
                name=tc["name"],
                arguments=tc.get("args", {}),
            ))

    total_tokens = 0
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        total_tokens = response.usage_metadata.get("total_tokens", 0)

    return ToolCallResponse(
        content=response.content if not tool_calls else None,
        tool_calls=tool_calls,
        total_tokens=total_tokens,
        rounds_used=1,
    )
