"""LLM Function Calling 类型定义.

v6.10.0: 支持 tool calling 的数据结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolDefinition:
    """LLM Tool 定义（传给 LLM 的 function schema）."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    """LLM 返回的工具调用请求."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallResponse:
    """LLM 带 tool calling 的响应."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    total_tokens: int = 0
    rounds_used: int = 0


@dataclass
class ToolResult:
    """Tool 执行结果（知识 Skill 返回 Markdown 内容）."""

    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentToolResponse:
    """Agent 层的 tool calling 最终结果."""

    content: str | None = None
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    total_tokens: int = 0
    rounds_used: int = 0
    exceeded_rounds: bool = False
