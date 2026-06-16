"""Workflow node recovery helpers.

These helpers keep run-detail and workflow-timeline recovery decisions aligned.
The persisted ``current_node`` may be ``human_review`` after an upstream node
fails, so recovery UI must derive the real failed node from node events.
"""

from __future__ import annotations

from typing import Any


HUMAN_REVIEW_NODES = frozenset({"human_review", "revision_router"})

NODE_RETRY_TARGETS: dict[str, dict[str, str]] = {
    "planner": {"node": "planner", "label": "规划", "status": "planned"},
    "screenwriter": {"node": "screenwriter", "label": "编剧", "status": "planned"},
    "author": {"node": "author", "label": "执笔", "status": "scripted"},
    "polisher": {"node": "polisher", "label": "润色", "status": "drafted"},
    "editor": {"node": "editor", "label": "审核", "status": "polished"},
    # v6.10.8: Cover nodes introduced in v6.8.5+ / v6.9.0
    "quality_gate": {"node": "quality_gate", "label": "质检门禁", "status": "polished"},
    "memory_curator": {"node": "memory_curator", "label": "记忆整理", "status": "reviewed"},
    "creative_ledger_curator": {"node": "creative_ledger_curator", "label": "创作台账", "status": "published"},
}


TERMINAL_EVENT_TYPES = frozenset({
    "completed",
    "failed",
    "skipped",
    "workflow_interrupted",
})
TERMINAL_STATUSES = frozenset({
    "completed",
    "failed",
    "skipped",
    "blocked",
    "error",
})


def node_retry_target(current_node: str | None) -> dict[str, str] | None:
    """Return the last safe DB status for retrying a failed workflow node."""
    node = (current_node or "").strip()
    return NODE_RETRY_TARGETS.get(node)


def event_indicates_failure(event: dict[str, Any]) -> bool:
    """Return whether a node/execution event represents failure or timeout."""
    status = str(event.get("status") or "").lower()
    event_type = str(event.get("event_type") or "").lower()
    message = f"{event.get('message') or ''} {event.get('error_message') or ''}".lower()
    if status in {"failed", "error"}:
        return True
    if event_type in {"failed", "error", "llm_failed", "step_error"}:
        return True
    return "执行超时" in message or "timeout" in message


def resolve_failed_node_from_events(
    events: list[dict[str, Any]] | None,
    current_node: str | None = None,
) -> str | None:
    """Resolve the real failed node, ignoring terminal human-review wrappers."""
    if events:
        for event in reversed(events):
            node_name = str(event.get("node_name") or event.get("node") or "").strip()
            if not node_name or node_name in HUMAN_REVIEW_NODES:
                continue
            if event_indicates_failure(event):
                return node_name

    node = (current_node or "").strip()
    return node or None


def active_node_started_at_from_events(
    events: list[dict[str, Any]] | None,
    current_node: str | None = None,
) -> str | None:
    """Return the started_at for the currently active node, if observable.

    Stuck-run recovery must be based on the active node age, not total run age.
    A long workflow can legitimately exceed the global stuck threshold while a
    later node has only been running for a few minutes.
    """
    if not events:
        return None

    active_started_at: dict[str, str] = {}
    active_order: list[str] = []
    for event in events:
        node_name = str(event.get("node_name") or event.get("node") or "").strip()
        if not node_name:
            continue
        event_type = str(event.get("event_type") or "").lower()
        status = str(event.get("status") or "").lower()
        timestamp = str(
            event.get("created_at")
            or event.get("timestamp")
            or event.get("started_at")
            or ""
        ).strip()

        if event_type in TERMINAL_EVENT_TYPES or status in TERMINAL_STATUSES:
            active_started_at.pop(node_name, None)
            active_order = [node for node in active_order if node != node_name]
            continue

        if event_type in {"started", "node_started"} or status == "running":
            active_started_at[node_name] = timestamp
            active_order = [node for node in active_order if node != node_name]
            active_order.append(node_name)

    node = (current_node or "").strip()
    if node and active_started_at.get(node):
        return active_started_at[node]
    for node_name in reversed(active_order):
        started_at = active_started_at.get(node_name)
        if started_at:
            return started_at
    return None
