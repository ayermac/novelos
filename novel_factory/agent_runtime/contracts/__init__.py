"""Agent Collaboration Contracts for v6.0.

Defines handoff contracts between agents with quality bars and escalation rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class HandoffContract:
    from_agent: str
    to_agent: str
    handoff_artifact: str
    required_fields: list[str]
    quality_bar: str
    feedback_channel: str
    failure_escalation: str

    def validate(self, artifact: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate artifact against required fields."""
        missing = [
            f for f in self.required_fields
            if f not in artifact or artifact[f] is None or artifact[f] == ""
        ]
        if missing:
            return False, [f"Missing required field: {f}" for f in missing]
        return True, []


# v6.0: Canonical collaboration contracts
CANONICAL_CONTRACTS: list[HandoffContract] = [
    HandoffContract(
        from_agent="planner",
        to_agent="screenwriter",
        handoff_artifact="chapter_brief",
        required_fields=["objective", "key_events", "ending_hook", "plots_to_plant", "plots_to_resolve"],
        quality_bar="章节指令必须能拆成场景，事件可落地",
        feedback_channel="planner 接收 screenwriter 的「事件不可写」反馈",
        failure_escalation="如果 screenwriter 反馈 2 次以上无法执行，重新规划",
    ),
    HandoffContract(
        from_agent="screenwriter",
        to_agent="author",
        handoff_artifact="scene_beats",
        required_fields=["sequence", "scene_goal", "conflict", "turn", "hook", "plot_refs"],
        quality_bar="scene beats 必须可写正文，每个 beat 有明确功能",
        feedback_channel="author 向 screenwriter 反馈「beat 无法展开」",
        failure_escalation="2 次以上反馈则返回 planner 重新规划",
    ),
    HandoffContract(
        from_agent="author",
        to_agent="polisher",
        handoff_artifact="draft",
        required_fields=["content", "title", "word_count", "implemented_events", "used_plot_refs"],
        quality_bar="正文结构完整且事件覆盖，语言可润色",
        feedback_channel="polisher 向 author 反馈「事实被改」时通知",
        failure_escalation="事实锁失败则退回 author",
    ),
    HandoffContract(
        from_agent="polisher",
        to_agent="editor",
        handoff_artifact="polished_draft",
        required_fields=["content", "fact_change_risk", "changed_scope", "summary"],
        quality_bar="润色不能改变事实，必须通过事实锁",
        feedback_channel="editor 发现问题时归因到 polisher",
        failure_escalation="事实锁失败则退回 polisher",
    ),
    HandoffContract(
        from_agent="editor",
        to_agent="author",
        handoff_artifact="revision_brief",
        required_fields=["issues", "suggestions", "target_paragraphs"],
        quality_bar="返修单必须明确归因，给出具体段落/场景目标",
        feedback_channel="author 向 editor 反馈「返修单不可执行」",
        failure_escalation="连续 2 次不可执行则退回 planner",
    ),
    HandoffContract(
        from_agent="memory_curator",
        to_agent="planner",
        handoff_artifact="context_warnings",
        required_fields=["warning_type", "affected_entities", "reason"],
        quality_bar="记忆变化影响后续规划时必须提醒",
        feedback_channel="planner 接收 memory_curator 的设定变化提醒",
        failure_escalation="设定冲突时暂停规划，请求人工确认",
    ),
]


def get_contract(from_agent: str, to_agent: str) -> HandoffContract | None:
    for c in CANONICAL_CONTRACTS:
        if c.from_agent == from_agent and c.to_agent == to_agent:
            return c
    return None


def validate_handoff(from_agent: str, to_agent: str, artifact: dict[str, Any]) -> tuple[bool, list[str]]:
    contract = get_contract(from_agent, to_agent)
    if not contract:
        return True, []  # No contract defined = pass
    return contract.validate(artifact)
