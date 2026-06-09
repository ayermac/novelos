"""Workflow run diagnosis helpers."""

from __future__ import annotations

from typing import Any


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(needle.lower() in lowered for needle in needles)


def diagnose_run(repo: Any, run_data: dict[str, Any], chapter: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a compact diagnosis for a workflow run.

    The doctor is advisory: it classifies failures and gives next actions. It
    does not change workflow state.
    """
    status = str(run_data.get("status") or "unknown")
    current_node = str(run_data.get("current_node") or "")
    error_message = str(run_data.get("error_message") or "")
    category = "healthy" if status in {"completed"} else "unknown"
    severity = "info"
    next_action = "none"
    summary = "运行未发现明确异常。"
    evidence: dict[str, Any] = {
        "run_status": status,
        "current_node": current_node,
        "chapter_status": (chapter or {}).get("status"),
    }

    events: list[dict[str, Any]] = []
    try:
        events = repo.get_workflow_node_events(run_data.get("id")) if hasattr(repo, "get_workflow_node_events") else []
    except Exception:
        events = []
    failed_events = [
        event for event in events
        if str(event.get("status") or "").lower() in {"failed", "error"}
        or str(event.get("event_type") or "").lower() in {"failed", "error"}
    ]
    warning_events = [event for event in events if str(event.get("status") or "").lower() == "warning"]
    evidence["failed_event_count"] = len(failed_events)
    evidence["warning_event_count"] = len(warning_events)

    combined = " ".join(
        [error_message, current_node]
        + [str(event.get("message") or "") for event in failed_events[-3:]]
    )

    if current_node == "memory_curator" or _contains_any(combined, ("memory_curator", "记忆", "memory curator")):
        category = "memory_failure"
        severity = "warning" if (chapter or {}).get("status") in {"reviewed", "awaiting_publish", "published"} else "error"
        next_action = "backfill_memory"
        summary = "记忆整理失败或超时；正文已过审时可补跑记忆，不应重置整章。"
    elif current_node == "quality_gate" or _contains_any(combined, ("quality gate", "质检", "门禁", "blocking issues")):
        category = "deterministic_quality_failure"
        severity = "error"
        next_action = "revise_by_gate"
        summary = "确定性质检未通过，按门禁问题返修。"
    elif _contains_any(combined, ("json", "schema", "parse", "empty", "空内容", "输出格式", "Author 纯正文生成空内容")):
        category = "model_output_failure"
        severity = "error"
        next_action = "retry_node_or_switch_model"
        summary = "模型输出格式或内容为空，优先定点重试或切换模型。"
    elif _contains_any(combined, ("config", "配置", "api key", "base_url", "profile", "llm route")):
        category = "configuration_failure"
        severity = "error"
        next_action = "check_settings"
        summary = "配置或 LLM 路由异常，先检查设置。"
    elif _contains_any(combined, ("timeout", "超时", "stale", "疑似卡住")):
        category = "runtime_timeout"
        severity = "warning"
        next_action = "mark_stuck"
        summary = "运行超时或疑似卡住，建议标记阻塞后按节点恢复。"
    elif status in {"blocked", "failed"} and failed_events:
        category = "workflow_failure"
        severity = "error"
        next_action = "view_failed_node"
        summary = "工作流节点失败，查看失败节点事件后定点恢复。"
    elif status == "running":
        category = "running"
        severity = "info"
        next_action = "wait_or_watch"
        summary = "运行仍在进行中。"

    return {
        "category": category,
        "severity": severity,
        "summary": summary,
        "next_action": next_action,
        "evidence": evidence,
    }
