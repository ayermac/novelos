"""Controlled Agent Tool Runtime registry.

v6.0: Internal tools are enabled by default.
External tools (search/file/http/bash) are opt-in and audited.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from .project_tools import handle_project_context_query
from .chapter_tools import handle_chapter_version_diff, handle_local_rewrite
from .memory_tools import handle_agent_memory_query, handle_agent_memory_write, handle_foreshadowing_debt_report
from .eval_tools import handle_capability_eval

logger = logging.getLogger(__name__)


@dataclass
class ToolSpec:
    tool_id: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    permissions: dict[str, Any]
    allowed_agents: list[str]
    audit_policy: str
    cost_policy: dict[str, Any]
    failure_policy: str
    handler: Callable[..., dict[str, Any]] | None = None
    enabled_by_default: bool = True


class ToolRegistry:
    """Registry for agent tools with permission controls."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        # Internal tools — enabled by default
        self.register(ToolSpec(
            tool_id="project_context.query",
            description="查询项目角色、世界观、伏笔、事实",
            input_schema={"type": "object", "properties": {"project_id": {"type": "string"}, "query": {"type": "string"}}},
            output_schema={"type": "object"},
            permissions={"read": True, "write": False},
            allowed_agents=["*"],
            audit_policy="log",
            cost_policy={"type": "free"},
            failure_policy="warn",
            enabled_by_default=True,
            handler=handle_project_context_query,
        ))
        self.register(ToolSpec(
            tool_id="chapter.version_diff",
            description="对比版本和局部变化",
            input_schema={"type": "object", "properties": {"project_id": {"type": "string"}, "chapter_number": {"type": "integer"}}},
            output_schema={"type": "object"},
            permissions={"read": True, "write": False},
            allowed_agents=["*"],
            audit_policy="log",
            cost_policy={"type": "free"},
            failure_policy="warn",
            enabled_by_default=True,
            handler=handle_chapter_version_diff,
        ))
        self.register(ToolSpec(
            tool_id="foreshadowing.debt_report",
            description="生成伏笔债务报告",
            input_schema={"type": "object", "properties": {"project_id": {"type": "string"}}},
            output_schema={"type": "object"},
            permissions={"read": True, "write": False},
            allowed_agents=["planner", "editor", "memory_curator"],
            audit_policy="log",
            cost_policy={"type": "free"},
            failure_policy="warn",
            enabled_by_default=True,
            handler=handle_foreshadowing_debt_report,
        ))
        self.register(ToolSpec(
            tool_id="agent_memory.query",
            description="查询 Agent 记忆",
            input_schema={"type": "object", "properties": {"project_id": {"type": "string"}, "agent_id": {"type": "string"}}},
            output_schema={"type": "object"},
            permissions={"read": True, "write": False},
            allowed_agents=["*"],
            audit_policy="log",
            cost_policy={"type": "free"},
            failure_policy="warn",
            enabled_by_default=True,
            handler=handle_agent_memory_query,
        ))
        self.register(ToolSpec(
            tool_id="agent_memory.write",
            description="写入 Agent 记忆",
            input_schema={"type": "object", "properties": {"project_id": {"type": "string"}, "agent_id": {"type": "string"}, "memory_type": {"type": "string"}, "key": {"type": "string"}, "value": {"type": "object"}}},
            output_schema={"type": "object"},
            permissions={"read": False, "write": True},
            allowed_agents=["*"],
            audit_policy="trace",
            cost_policy={"type": "free"},
            failure_policy="warn",
            enabled_by_default=True,
            handler=handle_agent_memory_write,
        ))
        self.register(ToolSpec(
            tool_id="local_rewrite.apply",
            description="局部修复正文",
            input_schema={"type": "object", "properties": {"project_id": {"type": "string"}, "chapter_number": {"type": "integer"}, "target": {"type": "string"}, "replacement": {"type": "string"}}},
            output_schema={"type": "object"},
            permissions={"read": True, "write": True},
            allowed_agents=["author", "polisher", "screenwriter"],
            audit_policy="trace",
            cost_policy={"type": "token", "max_tokens": 500},
            failure_policy="warn",
            enabled_by_default=True,
            handler=handle_local_rewrite,
        ))
        self.register(ToolSpec(
            tool_id="capability.eval",
            description="执行能力评估",
            input_schema={"type": "object", "properties": {"skill_id": {"type": "string"}, "payload": {"type": "object"}}},
            output_schema={"type": "object"},
            permissions={"read": True, "write": False},
            allowed_agents=["editor", "memory_curator"],
            audit_policy="log",
            cost_policy={"type": "free"},
            failure_policy="warn",
            enabled_by_default=True,
            handler=handle_capability_eval,
        ))

        # External tools — disabled by default
        self.register(ToolSpec(
            tool_id="web_search.query",
            description="查外部资料",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            output_schema={"type": "object"},
            permissions={"read": True, "write": False, "network": True},
            allowed_agents=["planner", "author"],
            audit_policy="audit",
            cost_policy={"type": "api"},
            failure_policy="warn",
            enabled_by_default=False,
        ))
        self.register(ToolSpec(
            tool_id="file.import_reference",
            description="导入本地资料",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            output_schema={"type": "object"},
            permissions={"read": True, "write": False, "filesystem": True},
            allowed_agents=["planner", "memory_curator"],
            audit_policy="audit",
            cost_policy={"type": "free"},
            failure_policy="warn",
            enabled_by_default=False,
        ))
        self.register(ToolSpec(
            tool_id="http.request",
            description="外部 API 调用",
            input_schema={"type": "object", "properties": {"url": {"type": "string"}, "method": {"type": "string"}}},
            output_schema={"type": "object"},
            permissions={"read": True, "write": False, "network": True},
            allowed_agents=[],
            audit_policy="audit",
            cost_policy={"type": "api"},
            failure_policy="block",
            enabled_by_default=False,
        ))
        self.register(ToolSpec(
            tool_id="bash.run",
            description="shell 命令",
            input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
            output_schema={"type": "object"},
            permissions={"read": False, "write": False, "exec": True},
            allowed_agents=[],
            audit_policy="audit",
            cost_policy={"type": "free"},
            failure_policy="block",
            enabled_by_default=False,
        ))

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.tool_id] = spec
        logger.info("Registered tool: %s (enabled=%s)", spec.tool_id, spec.enabled_by_default)

    def get(self, tool_id: str) -> ToolSpec | None:
        return self._tools.get(tool_id)

    def list_tools(self, agent_id: str | None = None, enabled_only: bool = True) -> list[ToolSpec]:
        results = list(self._tools.values())
        if enabled_only:
            results = [t for t in results if t.enabled_by_default]
        if agent_id:
            results = [
                t for t in results
                if "*" in t.allowed_agents or agent_id in t.allowed_agents
            ]
        return results

    def is_allowed(self, tool_id: str, agent_id: str) -> bool:
        spec = self._tools.get(tool_id)
        if not spec:
            return False
        if not spec.enabled_by_default:
            return False
        return "*" in spec.allowed_agents or agent_id in spec.allowed_agents

    def call(self, tool_id: str, payload: dict[str, Any], repo: Any | None = None) -> dict[str, Any]:
        spec = self._tools.get(tool_id)
        if not spec:
            return {"ok": False, "error": f"Tool not found: {tool_id}", "data": {}}
        if not spec.enabled_by_default:
            return {"ok": False, "error": f"Tool disabled: {tool_id}", "data": {}}
        if spec.handler is None:
            return {"ok": False, "error": f"Tool has no handler: {tool_id}", "data": {}}
        try:
            result = spec.handler(payload, repo=repo)
            return {"ok": True, "error": None, "data": result}
        except Exception as e:
            logger.warning("Tool %s call failed: %s", tool_id, e)
            return {"ok": False, "error": str(e), "data": {}}
