"""v6.10.0 Function Calling and types tests."""

from __future__ import annotations

import pytest

from novel_factory.llm.types import (
    ToolDefinition,
    ToolCall,
    ToolCallResponse,
    ToolResult,
    AgentToolResponse,
)
from novel_factory.llm.stub_provider import StubLLM
from novel_factory.llm.provider import LLMProvider


def test_tool_definition_creation():
    """ToolDefinition dataclass works correctly."""
    td = ToolDefinition(name="test", description="A test tool", parameters={"type": "object"})
    assert td.name == "test"
    assert td.description == "A test tool"
    assert td.parameters == {"type": "object"}


def test_tool_definition_defaults():
    """ToolDefinition has sensible defaults."""
    td = ToolDefinition(name="test", description="desc")
    assert td.parameters == {}


def test_tool_call_creation():
    """ToolCall dataclass works correctly."""
    tc = ToolCall(id="call_123", name="test", arguments={"x": 1})
    assert tc.id == "call_123"
    assert tc.name == "test"
    assert tc.arguments == {"x": 1}


def test_tool_call_response_creation():
    """ToolCallResponse dataclass works correctly."""
    resp = ToolCallResponse(
        content=None,
        tool_calls=[ToolCall(id="c1", name="t1", arguments={})],
        total_tokens=100,
        rounds_used=1,
    )
    assert resp.content is None
    assert len(resp.tool_calls) == 1
    assert resp.total_tokens == 100


def test_tool_call_response_defaults():
    """ToolCallResponse has sensible defaults."""
    resp = ToolCallResponse()
    assert resp.content is None
    assert resp.tool_calls == []
    assert resp.total_tokens == 0


def test_tool_result_creation():
    """ToolResult dataclass works correctly."""
    result = ToolResult(content="markdown content", metadata={"skill_id": "test"})
    assert result.content == "markdown content"
    assert result.metadata["skill_id"] == "test"


def test_agent_tool_response_creation():
    """AgentToolResponse dataclass works correctly."""
    resp = AgentToolResponse(
        content="final output",
        tool_results=[{"skill": "test"}],
        total_tokens=500,
        rounds_used=2,
    )
    assert resp.content == "final output"
    assert resp.rounds_used == 2
    assert resp.exceeded_rounds is False


def test_agent_tool_response_exceeded():
    """AgentToolResponse exceeded_rounds flag."""
    resp = AgentToolResponse(exceeded_rounds=True)
    assert resp.exceeded_rounds is True


def test_llm_provider_has_invoke_with_tools():
    """LLMProvider base class has invoke_with_tools method."""
    assert hasattr(LLMProvider, "invoke_with_tools")


def test_stub_llm_invoke_with_tools():
    """StubLLM.invoke_with_tools() returns tool_calls for all tools."""
    stub = StubLLM()
    tools = [
        ToolDefinition(name="tool-a", description="Tool A", parameters={}),
        ToolDefinition(name="tool-b", description="Tool B", parameters={}),
    ]
    response = stub.invoke_with_tools(messages=[], tools=tools)
    assert isinstance(response, ToolCallResponse)
    assert len(response.tool_calls) == 2
    assert response.tool_calls[0].name == "tool-a"
    assert response.tool_calls[1].name == "tool-b"
    assert response.total_tokens > 0


def test_stub_llm_invoke_with_tools_single_tool():
    """StubLLM.invoke_with_tools() works with a single tool."""
    stub = StubLLM()
    tools = [ToolDefinition(name="knowledge-skill", description="A knowledge skill")]
    response = stub.invoke_with_tools(messages=[], tools=tools)
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].id.startswith("stub_")


def test_stub_llm_invoke_with_tools_empty():
    """StubLLM.invoke_with_tools() works with no tools."""
    stub = StubLLM()
    response = stub.invoke_with_tools(messages=[], tools=[])
    assert len(response.tool_calls) == 0


def test_stub_llm_invoke_with_tools_preserves_existing_methods():
    """invoke_with_tools() does not break existing invoke_json/invoke_text."""
    stub = StubLLM()
    json_result = stub.invoke_json(messages=[])
    assert isinstance(json_result, dict)

    text_result = stub.invoke_text(messages=[])
    assert isinstance(text_result, str)
