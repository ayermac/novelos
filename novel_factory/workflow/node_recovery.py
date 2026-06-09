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
}


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

