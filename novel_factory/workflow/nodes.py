"""LangGraph node functions for the chapter production workflow.

Each node takes a FactoryState and returns a dict of updates to merge.
v1.1: Nodes now track workflow_runs lifecycle and update current_node.
v5.1.6: Added create_node_runners for LLMRouter-based dependency injection.
"""

from __future__ import annotations

import logging
import json
import time
from typing import Any, Callable

from ..db.repository import Repository
from ..llm.provider import LLMProvider
from ..models.state import ChapterStatus, FactoryState
from .conditions import hydrate_revision_state, revision_target_from_state
from ..agents.planner import PlannerAgent
from ..agents.planner import build_memory_context_audit
from ..agents.screenwriter import ScreenwriterAgent
from ..agents.author import AuthorAgent
from ..agents.polisher import PolisherAgent
from ..agents.editor import EditorAgent
from ..agents.memory_curator import MemoryCuratorAgent
from ..agent_runtime.context_builder import AgentContextBuilder
from .execution_events import (
    log_execution_event,
    CONTEXT_SUMMARIZERS,
    build_context_loaded_message,
    verify_agent_completion_evidence,
    EVENT_CONTEXT_LOADED,
    EVENT_LLM_STARTED,
    EVENT_LLM_REQUEST_DETAIL,
    EVENT_LLM_RESPONSE_DETAIL,
    EVENT_LLM_COMPLETED,
    EVENT_LLM_FAILED,
    EVENT_EVIDENCE_VERIFIED,
    EVENT_FALLBACK_USED,
    EVENT_ARTIFACT_SAVED,
    EVENT_DIFF_GENERATED,
    EVENT_SELF_CHECK_COMPLETED,
    EVENT_SKILL_COMPLETED,
    EVIDENCE_STATUS_PASS,
    EVIDENCE_STATUS_FAIL,
    EVIDENCE_STATUS_WARN,
)

logger = logging.getLogger(__name__)


# ── Helper ──────────────────────────────────────────────────────


# v5.8: Chinese-facing node messages for observability
_NODE_MESSAGES: dict[str, dict[str, str]] = {
    "health_check": {"started": "开始工作流预检", "completed": "预检通过"},
    "task_discovery": {"started": "识别章节任务状态", "completed": "任务状态识别完成"},
    "planner": {"started": "开始章节规划", "completed": "已生成章节规划", "failed": "章节规划失败", "retrying": "规划质量门未通过，准备重试"},
    "screenwriter": {"started": "开始编剧", "completed": "已生成章节场景规划", "failed": "编剧失败", "retrying": "编剧质量门未通过，准备重试"},
    "author": {"started": "开始执笔撰写", "completed": "已生成章节初稿", "failed": "执笔撰写失败", "retrying": "执笔质量门未通过，准备重试"},
    "polisher": {"started": "开始润色", "completed": "润色完成", "failed": "润色失败", "retrying": "润色质量门未通过，准备重试"},
    "editor": {"started": "开始审核", "completed": "审核完成", "failed": "审核失败", "retrying": "审核质量门未通过，准备重试"},
    "memory_curator": {"started": "开始记忆整理", "completed": "记忆更新完成", "failed": "记忆整理失败"},
    "publisher": {"started": "开始发布", "completed": "章节已发布", "failed": "发布失败"},
    "awaiting_publish": {"started": "等待人工发布", "completed": "已到达等待发布状态"},
    "revision_router": {"started": "返修路由", "completed": "返修路由完成"},
    "human_review": {"started": "进入人工审核", "completed": "人工审核处理完成", "failed": "需要人工干预"},
    "archive": {"started": "开始归档", "completed": "归档完成"},
}


def _node_message(node_name: str, event_type: str) -> str:
    """Get author-facing Chinese message for a node event."""
    msgs = _NODE_MESSAGES.get(node_name, {})
    return msgs.get(event_type, f"{node_name} {event_type}")


def _redact_trace_value(value: Any) -> Any:
    """Recursively redact sensitive strings in trace payloads."""
    if isinstance(value, str):
        from ..security.redaction import redact_sensitive_text
        return redact_sensitive_text(value)
    if isinstance(value, dict):
        return {str(k): _redact_trace_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_trace_value(item) for item in value]
    return value


def _log_llm_trace_events(state: FactoryState, repo: Repository, agent_name: str, llm: LLMProvider) -> None:
    """Best-effort log LLM request/response metadata (v6.8.0: reduced verbosity).

    Only logs compact metadata (model, tokens, duration, error) — not full
    prompt/response text. Full payloads are available in the LLM provider's
    last_call_trace for debugging but are no longer persisted to DB.
    """
    trace = getattr(llm, "last_call_trace", None)
    if not isinstance(trace, dict):
        return
    request = trace.get("request")
    if isinstance(request, dict) and request:
        try:
            compact_request = {
                "provider": request.get("provider"),
                "model": request.get("model"),
                "temperature": request.get("temperature"),
                "max_tokens": request.get("max_tokens"),
                "call_type": request.get("call_type"),
                "schema": request.get("schema"),
                "agent_id": request.get("agent_id"),
            }
            log_execution_event(
                repo, state, agent_name, EVENT_LLM_REQUEST_DETAIL,
                message=f"LLM 请求详情：{agent_name}",
                agent_id=agent_name,
                status="info",
                payload=compact_request,
            )
        except Exception:
            logger.debug("Failed to log LLM request detail for %s", agent_name, exc_info=True)
    response = trace.get("response")
    if isinstance(response, dict) and response:
        try:
            usage = response.get("usage") or response.get("usage_metadata") or {}
            compact_response = {
                "content_length": len(str(response.get("content", ""))),
                "usage": usage,
                "finish_reason": response.get("finish_reason"),
            }
            log_execution_event(
                repo, state, agent_name, EVENT_LLM_RESPONSE_DETAIL,
                message=f"LLM 响应详情：{agent_name}",
                agent_id=agent_name,
                status="info",
                payload=compact_response,
            )
        except Exception:
            logger.debug("Failed to log LLM response detail for %s", agent_name, exc_info=True)
    elif trace.get("error"):
        try:
            log_execution_event(
                repo, state, agent_name, EVENT_LLM_RESPONSE_DETAIL,
                message=f"LLM 响应详情：{agent_name} 调用失败",
                agent_id=agent_name,
                status="error",
                payload={"error": _redact_trace_value(trace.get("error"))},
            )
        except Exception:
            logger.debug("Failed to log LLM error detail for %s", agent_name, exc_info=True)


def _log_node_event(
    state: FactoryState,
    repo: Repository,
    node_name: str,
    event_type: str,
    status: str | None = None,
    error_message: str | None = None,
    artifact_refs: list[dict] | None = None,
    token_count: int | None = None,
    latency_ms: int | None = None,
) -> None:
    """Best-effort log a workflow node event. Never raises.

    v5.8: Node-level observability. Failures are logged as warnings
    but do not block the main workflow.
    """
    run_id = state.get("workflow_run_id")
    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)
    if not run_id or not project_id or not chapter_number:
        return
    try:
        import json
        message = _node_message(node_name, event_type)
        if error_message:
            message = f"{message}：{error_message}"
        artifact_refs_json = json.dumps(artifact_refs, ensure_ascii=False) if artifact_refs else None
        repo.create_workflow_node_event(
            run_id=run_id,
            project_id=project_id,
            chapter_number=chapter_number,
            node_name=node_name,
            event_type=event_type,
            status=status,
            message=message,
            error_message=error_message,
            artifact_refs_json=artifact_refs_json,
            token_count=token_count,
            latency_ms=latency_ms,
        )
    except Exception:
        logger.warning(
            "Failed to log node event for %s/%s node=%s event=%s",
            project_id, chapter_number, node_name, event_type,
            exc_info=True,
        )


def _retryable_quality_gate_message(result: dict[str, Any]) -> str:
    """Return the user-facing reason for a retryable quality-gate loop."""
    gate = result.get("quality_gate") or {}
    return gate.get("message") or "质量门未通过，已进入返修重试"


def _log_agent_node_outcome(
    state: FactoryState,
    repo: Repository,
    agent_name: str,
    result: dict[str, Any],
    *,
    latency_ms: int | None = None,
) -> None:
    """Log node lifecycle outcome without claiming completion during retries."""
    if "error" in result:
        _log_node_event(
            state,
            repo,
            agent_name,
            "failed",
            status="failed",
            error_message=result["error"],
            token_count=result.get("total_tokens"),
            latency_ms=latency_ms,
        )
        return

    if result.get("retryable_quality_gate"):
        _log_node_event(
            state,
            repo,
            agent_name,
            "retrying",
            status="warning",
            error_message=_retryable_quality_gate_message(result),
            token_count=result.get("total_tokens"),
            latency_ms=latency_ms,
        )
        return

    _log_node_event(
        state,
        repo,
        agent_name,
        "completed",
        status="completed",
        token_count=result.get("total_tokens"),
        latency_ms=latency_ms,
    )


def _update_run_node(state: FactoryState, repo: Repository, node_name: str) -> None:
    """Update workflow_runs.current_node if a run_id exists in state."""
    run_id = state.get("workflow_run_id")
    if run_id:
        repo.update_workflow_run(run_id, current_node=node_name)


def _guard_blocking_db_status(state: FactoryState, repo: Repository) -> dict[str, Any] | None:
    """Stop agent execution when DB truth has already entered blocking."""
    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)
    if not project_id or not chapter_number:
        return None

    try:
        db_status = repo.get_chapter_status(project_id, chapter_number)
    except Exception:
        logger.debug(
            "Failed to read chapter status before agent execution for %s/%s",
            project_id, chapter_number,
            exc_info=True,
        )
        return None

    if db_status == ChapterStatus.BLOCKING.value:
        return {
            "chapter_status": ChapterStatus.BLOCKING.value,
            "requires_human": True,
            "error": "章节已处于阻塞状态，停止下游 Agent 执行，请先解除阻塞后再继续工作流。",
        }
    return None


def _finalize_run(state: FactoryState, repo: Repository, status: str, error: str | None = None) -> None:
    """Finalize workflow run with given status and token usage."""
    run_id = state.get("workflow_run_id")
    if run_id:
        # P1 fix: When status is 'completed', clear any stale error_message
        clear_error = (status == "completed")
        repo.update_workflow_run(
            run_id,
            status=status,
            error_message=error,
            prompt_tokens=state.get("prompt_tokens", 0),
            completion_tokens=state.get("completion_tokens", 0),
            total_tokens=state.get("total_tokens", 0),
            duration_ms=state.get("duration_ms", 0),
            clear_error=clear_error,
        )


def _append_step(state: FactoryState, step_info: dict[str, Any]) -> None:
    """Append a step record to state.steps (v5.1.6)."""
    steps = state.get("steps", [])
    steps.append(step_info)
    state["steps"] = steps


def _save_memory_context_audit_if_missing(
    state: FactoryState,
    repo: Repository,
    *,
    built_at_node: str,
) -> dict[str, Any] | None:
    """Persist memory context audit even when Planner is skipped.

    Planned chapters with pre-generated instructions route directly to
    Screenwriter. Without this, chapter-to-chapter memory inheritance becomes
    invisible in run detail because the original audit was only saved by the
    Planner agent.
    """
    project_id = state.get("project_id", "")
    chapter_number = int(state.get("chapter_number") or 0)
    run_id = state.get("workflow_run_id")
    if not project_id or not chapter_number or not run_id:
        return None

    try:
        conn = repo._conn()
        try:
            existing = conn.execute(
                "SELECT id FROM agent_artifacts "
                "WHERE workflow_run_id=? AND agent_id='planner' "
                "AND artifact_type='memory_context_audit' "
                "LIMIT 1",
                (run_id,),
            ).fetchone()
            if existing:
                return None
        finally:
            conn.close()

        bundle = AgentContextBuilder(repo).build_for_planner(project_id, chapter_number, state)
        audit = build_memory_context_audit(chapter_number, bundle)
        audit["built_at_node"] = built_at_node
        repo.save_artifact(
            project_id,
            chapter_number,
            "planner",
            "memory_context_audit",
            content_json=audit,
            workflow_run_id=run_id,
        )
        return audit
    except Exception:
        logger.exception(
            "failed to save memory_context_audit project=%s chapter=%s run=%s",
            project_id,
            chapter_number,
            run_id,
        )
        return None


def _accumulate_tokens(state: FactoryState, llm: LLMProvider) -> dict[str, int]:
    """Accumulate token usage from LLM provider into state (v5.2).

    Returns the delta token usage for this call.
    """
    usage = getattr(llm, "last_token_usage", None)
    if not usage:
        return {}

    current_prompt = state.get("prompt_tokens", 0)
    current_completion = state.get("completion_tokens", 0)
    current_total = state.get("total_tokens", 0)
    current_duration = state.get("duration_ms", 0)

    return {
        "prompt_tokens": current_prompt + usage.prompt_tokens,
        "completion_tokens": current_completion + usage.completion_tokens,
        "total_tokens": current_total + usage.total_tokens,
        "duration_ms": current_duration + usage.duration_ms,
    }


def _enforce_token_budget(state: FactoryState, updates: dict[str, Any]) -> dict[str, Any] | None:
    """Return a blocking error update when runtime token budgets are exceeded."""
    total_tokens = updates.get("total_tokens", state.get("total_tokens", 0))
    chapter_limit = state.get("chapter_token_limit", 0) or 0
    project_limit = state.get("project_token_limit", 0) or 0
    project_tokens_before = state.get("project_tokens_before_run", 0) or 0

    if chapter_limit > 0 and total_tokens > chapter_limit:
        return {
            **updates,
            "error": f"TOKEN_BUDGET_EXCEEDED: 单章 token 已用 {total_tokens}，超过上限 {chapter_limit}",
            "chapter_status": updates.get("chapter_status", state.get("chapter_status")),
            "requires_human": True,
        }

    project_total = project_tokens_before + total_tokens
    if project_limit > 0 and project_total > project_limit:
        return {
            **updates,
            "error": f"TOKEN_BUDGET_EXCEEDED: 项目 token 已用 {project_total}，超过上限 {project_limit}",
            "chapter_status": updates.get("chapter_status", state.get("chapter_status")),
            "requires_human": True,
        }

    return None


# v6.7.8: Cap on internal repair attempts to prevent infinite loops when
# agent auto-compression keeps failing.  Exceeding this converts the failure
# into a chapter-level retry (consumes retry_count) or requires_human.
MAX_INTERNAL_REPAIR_ATTEMPTS = 2


def _handle_retryable_quality_gate(
    state: FactoryState,
    repo: Repository,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Convert retryable quality gate failures into revision routing.

    Author/Polisher word-count failures, death-penalty red-line failures,
    scene-beat coverage gaps, and regression-guard rejections are expected
    recoverable defects. They should consume a revision attempt and route back
    to the responsible agent until the chapter-level retry cap is reached.
    Other errors remain blocking.

    v6.7.8: Quality gate results may carry ``consume_revision_retry=False``
    to signal an *internal repair* (e.g. author/polisher auto-compression).
    Internal repairs still trigger revision routing but do **not** increment
    the chapter-level retry counter and emit ``internal_repair_attempt``
    instead of ``quality_gate_retry``.  A separate cap
    (``MAX_INTERNAL_REPAIR_ATTEMPTS``) prevents infinite internal repair loops.
    """
    gate = result.get("quality_gate") or {}
    retryable_gate = (
        gate.get("word_count_fail")
        or gate.get("death_penalty_fail")
        or gate.get("scene_beat_coverage_fail")
        or gate.get("version_regression")
    )
    if not result.get("error") or not retryable_gate:
        return result

    # v6.7.8: internal repairs (e.g. auto-compression) should not consume
    # chapter-level revision retries.
    consume_retry = gate.get("consume_revision_retry", True)

    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)
    retry_count = repo.get_chapter_retry_count(project_id, chapter_number)
    max_retries = state.get("max_retries", 3)

    # v6.7.8 P1-1: Check internal repair cap before the chapter retry cap,
    # so that exhausted internal repairs are escalated properly.
    # Scope by workflow_run_id and revision target so cross-run and cross-agent
    # repairs are isolated.
    internal_repair_escalated_event: dict[str, Any] | None = None
    if not consume_retry:
        workflow_run_id = state.get("workflow_run_id")
        repair_agent_id = gate.get("revision_target") or gate.get("agent")
        internal_count = repo.get_chapter_internal_repair_count(
            project_id, chapter_number,
            workflow_run_id=workflow_run_id,
            agent_id=repair_agent_id,
        )
        if internal_count >= MAX_INTERNAL_REPAIR_ATTEMPTS:
            # Internal repair budget exhausted.  Escalate to a chapter-level
            # retry so the agent gets a fresh attempt (and retry_count advances).
            logger.info(
                "Internal repair cap (%d) reached for %s ch%d — "
                "escalating to chapter-level retry",
                MAX_INTERNAL_REPAIR_ATTEMPTS, project_id, chapter_number,
            )
            consume_retry = True  # fall through to chapter-level path
            # Patch the gate so downstream consumers see the escalation.
            gate["consume_revision_retry"] = True
            gate.pop("internal_repair", None)
            gate["message"] = (
                gate.get("message", "")
                + f" [内部修复已达上限{MAX_INTERNAL_REPAIR_ATTEMPTS}次，升级为章节重试]"
            )

            # v6.8.2: Log escalation event
            internal_repair_escalated_event = {
                "event_type": "internal_repair_escalated",
                "message": (
                    f"内部修复已达上限 {MAX_INTERNAL_REPAIR_ATTEMPTS} 次，"
                    f"升级为章节级重试（retry_count 将从 {retry_count} 增加到 {retry_count + 1}）"
                ),
                "status": "warning",
                "payload": {
                    "internal_repair_count": internal_count,
                    "internal_repair_limit": MAX_INTERNAL_REPAIR_ATTEMPTS,
                    "escalated_to": "chapter_retry",
                    "current_retry_count": retry_count,
                    "new_retry_count": retry_count + 1,
                },
            }


    if retry_count >= max_retries:
        result["requires_human"] = True
        result["retry_count"] = retry_count
        return result

    revision_target = revision_target_from_state({
        **state,
        "quality_gate": gate,
    })
    current_status = repo.get_chapter_status(project_id, chapter_number)
    if current_status not in (
        ChapterStatus.BLOCKING.value,
        ChapterStatus.PUBLISHED.value,
        ChapterStatus.REVIEWED.value,
    ):
        repo.update_chapter_status(project_id, chapter_number, ChapterStatus.REVISION.value)

    updated = dict(result)
    updated.pop("error", None)
    updated["chapter_status"] = ChapterStatus.REVISION.value
    updated["current_stage"] = "revision"
    updated["requires_human"] = False
    updated["retryable_quality_gate"] = True

    if consume_retry:
        # Chapter-level retry: create a "revise" task (counted by
        # get_chapter_retry_count) and increment the retry counter.
        task_id = repo.start_task(
            project_id, chapter_number, "revise", revision_target,
            workflow_run_id=state.get("workflow_run_id"),
        )
        repo.complete_task(task_id, success=True)
        updated["retry_count"] = retry_count + 1
        updated.setdefault("_exec_events", []).append({
            "event_type": "quality_gate_retry",
            "message": gate.get("message") or "质量门未通过，已进入返修重试",
            "status": "warning",
            "payload": {
                "revision_target": revision_target,
                "retry_count": retry_count + 1,
                "max_retries": max_retries,
                "quality_gate": gate,
            },
        })
        if internal_repair_escalated_event:
            updated.setdefault("_exec_events", []).append(internal_repair_escalated_event)
    else:
        # Internal repair: use "internal_repair" task type (not counted by
        # get_chapter_retry_count) and preserve current retry counter.
        repair_scope = gate.get("repair_scope", "internal")
        task_id = repo.start_task(
            project_id, chapter_number, "internal_repair", revision_target,
            workflow_run_id=state.get("workflow_run_id"),
        )
        repo.complete_task(task_id, success=True)
        updated["retry_count"] = retry_count
        updated.setdefault("_exec_events", []).append({
            "event_type": "internal_repair_attempt",
            "message": (
                f"内部修复({repair_scope})未通过，已重新路由但不消耗章节重试次数 "
                f"(内部修复 {internal_count + 1}/{MAX_INTERNAL_REPAIR_ATTEMPTS})"
            ),
            "status": "info",
            "payload": {
                "revision_target": revision_target,
                "retry_count": retry_count,
                "max_retries": max_retries,
                "internal_repair_count": internal_count + 1,
                "internal_repair_limit": MAX_INTERNAL_REPAIR_ATTEMPTS,
                "quality_gate": gate,
                "repair_scope": repair_scope,
                "internal_repair": True,
            },
        })
    return updated


def _memory_curator_real_mode_error(state: FactoryState, result: dict[str, Any]) -> str | None:
    """Return a blocking error when real-mode memory extraction did not truly succeed."""
    if state.get("llm_mode", "stub") != "real":
        return None
    if result.get("memory_curator_locked"):
        return None
    if result.get("memory_curator_degraded"):
        return (
            result.get("memory_curator_warning")
            or "记忆提取未成功：MemoryCurator 已降级且未创建可信记忆批次。"
        )
    if result.get("fallback_created") or result.get("extraction_success") is False:
        return (
            result.get("memory_curator_warning")
            or "记忆提取未成功：仅生成状态卡兜底候选，请补跑或人工确认记忆后再发布。"
        )
    return None


# ── v5.1.6: Node factory for LLMRouter-based injection ────────────────


def _ensure_skill_registry(skill_registry: Any | None) -> Any | None:
    """Create a default SkillRegistry when runtime hooks need one.

    The API/CLI graph path often does not pass a registry explicitly. Without
    this fallback, Agent-level Skill mounts appear in configuration but never
    execute in the real LangGraph runner.
    """
    if skill_registry is not None:
        return skill_registry
    try:
        from ..skills.registry import SkillRegistry
        return SkillRegistry()
    except Exception:
        logger.warning("Failed to create SkillRegistry", exc_info=True)
        return None


def _ensure_tool_registry() -> Any | None:
    """v6.0: Create a default ToolRegistry for agent tool runtime."""
    try:
        from ..tools.registry import ToolRegistry
        return ToolRegistry()
    except Exception:
        logger.warning("Failed to create ToolRegistry", exc_info=True)
        return None


def _ensure_trace_store(repo: Repository) -> Any | None:
    """v6.0: Create a DecisionTraceStore backed by repository."""
    try:
        from ..agent_runtime.decision_trace import DecisionTraceStore
        return DecisionTraceStore(repo)
    except Exception:
        logger.warning("Failed to create DecisionTraceStore", exc_info=True)
        return None


def _previous_agent_in_steps(state: FactoryState) -> str | None:
    """v6.0: Find the last successful agent from state.steps."""
    steps = state.get("steps", []) or []
    for step in reversed(steps):
        if step.get("agent") and not step.get("error"):
            return step.get("agent")
    return None


def _latest_artifact_content(
    repo: Repository,
    project_id: str,
    chapter_number: int,
    agent_id: str,
    artifact_type: str,
    workflow_run_id: str | None = None,
) -> dict[str, Any]:
    """Read the latest artifact content for handoff validation.

    Artifact repository metadata intentionally omits content, while v6.0
    contracts need the actual previous handoff payload. This helper keeps the
    read scoped and best-effort for workflow validation only.
    """
    conn = repo._conn()
    try:
        params: list[Any] = [project_id, chapter_number, agent_id, artifact_type]
        sql = (
            "SELECT content_json FROM agent_artifacts "
            "WHERE project_id=? AND chapter_number=? AND agent_id=? AND artifact_type=?"
        )
        if workflow_run_id:
            sql += " AND workflow_run_id=?"
            params.append(workflow_run_id)
        sql += " ORDER BY created_at DESC LIMIT 1"
        row = conn.execute(sql, params).fetchone()
        if not row or not row["content_json"]:
            return {}
        return json.loads(row["content_json"])
    except Exception:
        logger.debug(
            "Failed to read latest artifact for %s/%s agent=%s type=%s",
            project_id, chapter_number, agent_id, artifact_type,
            exc_info=True,
        )
        return {}
    finally:
        conn.close()


def create_node_runners(
    settings: Any,
    repo: Repository,
    llm_router: Any,
    skill_registry: Any | None = None,
) -> dict[str, Callable[[FactoryState], dict[str, Any]]]:
    """Create node functions with injected dependencies.

    This factory creates closures that capture LLMRouter, Repository, and
    skill_registry, aligning with Dispatcher._run_agent() logic.

    Args:
        settings: Application settings (for future use).
        repo: Repository instance for database access.
        llm_router: LLMRouter instance for agent-level LLM routing.
        skill_registry: Optional SkillRegistry for polisher/editor.

    Returns:
        Dictionary mapping agent names to node functions.
    """
    effective_skill_registry = _ensure_skill_registry(skill_registry)
    effective_tool_registry = _ensure_tool_registry()
    effective_trace_store = _ensure_trace_store(repo)

    def _run_agent_node(
        agent_name: str,
        agent_cls: type,
        state: FactoryState,
    ) -> dict[str, Any]:
        """Generic agent runner with LLMRouter + error handling.

        Equivalent to dispatch/chapter.py ChapterDispatchMixin._run_agent().
        v6.0: Injects tool_registry and trace_store; validates handoff contracts.
        """
        blocking_guard = _guard_blocking_db_status(state, repo)
        if blocking_guard:
            return blocking_guard

        _update_run_node(state, repo, agent_name)
        _log_node_event(state, repo, agent_name, "started", status="running")

        # Record step before running (for run_with_graph return value)
        status_before = state.get("chapter_status", "")
        memory_context_audit = (
            _save_memory_context_audit_if_missing(
                state,
                repo,
                built_at_node="screenwriter_node",
            )
            if agent_name == "screenwriter"
            else None
        )

        # v6.0: Best-effort handoff contract validation from previous agent
        contract_ok = True
        contract_issues: list[str] = []
        prev_agent = _previous_agent_in_steps(state)
        if prev_agent:
            try:
                from ..agent_runtime.contracts import validate_handoff
                # Build a lightweight artifact from state for contract validation
                artifact: dict[str, Any] = {"chapter_status": status_before}
                workflow_run_id = state.get("workflow_run_id")
                if status_before == ChapterStatus.PLANNED.value:
                    inst = repo.get_instruction(state.get("project_id", ""), state.get("chapter_number", 0))
                    if inst:
                        artifact.update({k: inst.get(k) for k in ("objective", "key_events", "ending_hook", "plots_to_plant", "plots_to_resolve")})
                elif status_before == ChapterStatus.SCRIPTED.value:
                    beats = repo.get_scene_beats(state.get("project_id", ""), state.get("chapter_number", 0))
                    if beats:
                        artifact["sequence"] = beats[0].get("sequence")
                        artifact["scene_goal"] = beats[0].get("scene_goal")
                        artifact["conflict"] = beats[0].get("conflict")
                        artifact["turn"] = beats[0].get("turn")
                        artifact["hook"] = beats[0].get("hook")
                        artifact["plot_refs"] = beats[0].get("plot_refs")
                elif status_before == ChapterStatus.DRAFTED.value:
                    artifact.update(_latest_artifact_content(
                        repo,
                        state.get("project_id", ""),
                        state.get("chapter_number", 0),
                        "author",
                        "draft",
                        workflow_run_id,
                    ))
                    ch = repo.get_chapter(state.get("project_id", ""), state.get("chapter_number", 0))
                    if ch:
                        artifact.setdefault("content", ch.get("content", ""))
                        artifact.setdefault("title", ch.get("title", ""))
                        artifact.setdefault("word_count", len(ch.get("content", "")))
                elif status_before == ChapterStatus.POLISHED.value:
                    artifact.update(_latest_artifact_content(
                        repo,
                        state.get("project_id", ""),
                        state.get("chapter_number", 0),
                        "polisher",
                        "polished_draft",
                        workflow_run_id,
                    ))
                    ch = repo.get_chapter(state.get("project_id", ""), state.get("chapter_number", 0))
                    if ch:
                        artifact.setdefault("content", ch.get("content", ""))
                elif status_before == ChapterStatus.REVISION.value and prev_agent == "editor":
                    revision_review = state.get("_revision_review") or {}
                    if not revision_review:
                        ch = repo.get_chapter(state.get("project_id", ""), state.get("chapter_number", 0))
                        if ch:
                            revision_review = repo.get_latest_review(
                                state.get("project_id", ""),
                                ch.get("id"),
                            ) or {}
                    artifact.update({
                        "issues": revision_review.get("issues") or [],
                        "suggestions": revision_review.get("suggestions") or [],
                        "target_paragraphs": revision_review.get("target_paragraphs") or [],
                    })
                contract_ok, contract_issues = validate_handoff(prev_agent, agent_name, artifact)
                if not contract_ok:
                    logger.warning(
                        "Handoff contract %s -> %s failed: %s",
                        prev_agent, agent_name, contract_issues,
                    )
            except Exception:
                logger.debug(
                    "Handoff contract validation %s -> %s failed (best-effort)",
                    prev_agent, agent_name,
                    exc_info=True,
                )  # Best-effort; never block workflow

        # Get LLM for this agent
        try:
            llm = llm_router.for_agent(agent_name)
        except ValueError as e:
            logger.error(f"LLM configuration error for agent '{agent_name}': {e}")
            _log_node_event(state, repo, agent_name, "failed", status="failed", error_message=str(e))
            _finalize_run(state, repo, "failed", str(e))
            return {
                "error": str(e),
                "chapter_status": status_before,
                "requires_human": True,
            }

        # v6.0: Inject skill_registry, tool_registry, and trace_store for all core agents.
        # v6.6.17: Inject fallback_llm for memory_curator
        if agent_name in ("planner", "screenwriter", "author", "polisher", "editor", "memory_curator"):
            agent_kwargs: dict[str, Any] = {
                "skill_registry": effective_skill_registry,
                "tool_registry": effective_tool_registry,
                "trace_store": effective_trace_store,
            }
            if agent_name == "memory_curator":
                fallback_llm = llm_router.for_agent_fallback(agent_name)
                agent_kwargs["fallback_llm"] = fallback_llm
            agent = agent_cls(repo, llm, **agent_kwargs)
        else:
            agent = agent_cls(repo, llm)

        # v6.1: Log context_loaded execution event
        summarizer = CONTEXT_SUMMARIZERS.get(agent_name)
        if summarizer:
            try:
                ctx_summary = summarizer(repo, state.get("project_id", ""), state.get("chapter_number", 0))
                ctx_msg = build_context_loaded_message(agent_name, ctx_summary)
                log_execution_event(
                    repo, state, agent_name, EVENT_CONTEXT_LOADED,
                    message=ctx_msg, agent_id=agent_name,
                    payload=ctx_summary,
                )
            except Exception:
                logger.debug(
                    "Context summarizer failed for %s (best-effort)",
                    agent_name,
                    exc_info=True,
                )  # Best-effort

        agent_started_at = time.perf_counter()
        log_execution_event(
            repo, state, agent_name, EVENT_LLM_STARTED,
            message=f"开始调用模型：{agent_name}",
            agent_id=agent_name,
            status="running",
        )
        result = _handle_retryable_quality_gate(state, repo, agent.run(state))
        if memory_context_audit:
            result.setdefault("memory_context_audit", memory_context_audit)
        agent_latency_ms = int((time.perf_counter() - agent_started_at) * 1000)
        memory_error = (
            _memory_curator_real_mode_error(state, result)
            if agent_name == "memory_curator" and "error" not in result
            else None
        )
        if memory_error:
            result["error"] = memory_error
            result["requires_human"] = True

        # v6.1: Agent-specific execution events are emitted by the agent, but
        # keep the high-level LLM completion/failure event adjacent to
        # llm_started so the timeline reads naturally.
        exec_events = result.pop("_exec_events", [])
        used_fallback = any(
            ev.get("event_type") == EVENT_FALLBACK_USED
            and (ev.get("payload") or {}).get("fallback_type") != "plain_text_primary"
            for ev in exec_events
        )

        # v6.1: Log LLM completion/failure
        if "error" in result:
            _log_llm_trace_events(state, repo, agent_name, llm)
            log_execution_event(
                repo, state, agent_name, EVENT_LLM_FAILED,
                message=f"Agent 执行失败：{result['error'][:200]}",
                agent_id=agent_name,
                status="error",
                payload={"error": result["error"][:500]},
                latency_ms=agent_latency_ms,
            )
        else:
            llm_usage = getattr(llm, "last_token_usage", None)
            llm_tokens = llm_usage.total_tokens if llm_usage else 0
            llm_duration = llm_usage.duration_ms if llm_usage else agent_latency_ms
            completed_message = (
                f"LLM 调用结束，已使用降级方案继续：耗时 {llm_duration/1000:.1f}s，{llm_tokens} tokens"
                if used_fallback
                else f"LLM 调用完成：耗时 {llm_duration/1000:.1f}s，{llm_tokens} tokens"
            )
            _log_llm_trace_events(state, repo, agent_name, llm)
            log_execution_event(
                repo, state, agent_name, EVENT_LLM_COMPLETED,
                message=completed_message,
                agent_id=agent_name,
                status="warning" if used_fallback else "info",
                token_count=llm_tokens,
                latency_ms=llm_duration,
            )

        # v6.1: Log agent-specific execution events from _exec_events
        for ev in exec_events:
            try:
                log_execution_event(
                    repo, state,
                    node_name=ev.get("node_name", agent_name),
                    event_type=ev.get("event_type", "info"),
                    message=ev.get("message", ""),
                    agent_id=ev.get("agent_id", agent_name),
                    status=ev.get("status", "info"),
                    payload=ev.get("payload"),
                    artifact_refs=ev.get("artifact_refs"),
                    token_count=ev.get("token_count"),
                    latency_ms=ev.get("latency_ms"),
                )
            except Exception:
                logger.debug(
                    "Execution event logging failed for %s (best-effort)",
                    agent_name,
                    exc_info=True,
                )  # Best-effort

        # v6.1: Verify completion evidence on success
        # v6.8.0: Only log evidence events on failure or warning (skip pass)
        if (
            "error" not in result
            and not result.get("retryable_quality_gate")
            and agent_name in ("planner", "screenwriter", "author", "polisher", "editor", "memory_curator")
        ):
            try:
                evidence = verify_agent_completion_evidence(repo, state, agent_name)
                severity = evidence["severity"]
                missing_str = "、".join(evidence["missing"]) if evidence["missing"] else ""
                warn_str = "、".join(evidence["warnings"]) if evidence["warnings"] else ""
                if severity == EVIDENCE_STATUS_FAIL:
                    ev_msg = f"完成证据校验失败：{missing_str}"
                elif severity == EVIDENCE_STATUS_WARN:
                    ev_msg = f"完成证据校验通过（有警告）：{warn_str}"
                else:
                    # v6.8.0: Skip logging for passing evidence (reduces noise)
                    ev_msg = None
                if ev_msg is not None:
                    log_execution_event(
                        repo, state, agent_name, EVENT_EVIDENCE_VERIFIED,
                        message=ev_msg,
                        agent_id=agent_name,
                        status=severity,
                        payload={
                            "ok": evidence["ok"],
                            "severity": severity,
                            "checks": evidence["checks"],
                            "missing": evidence["missing"],
                            "warnings": evidence["warnings"],
                        },
                    )
                # Log evidence failure as node-level warning but don't block
                if severity == EVIDENCE_STATUS_FAIL:
                    logger.warning(
                        "Agent '%s' evidence verification FAILED: %s",
                        agent_name, missing_str,
                    )
            except Exception:
                logger.debug(
                    "Completion evidence verification failed for %s (best-effort)",
                    agent_name,
                    exc_info=True,
                )  # Best-effort; never block workflow

        # v5.2: Accumulate token usage from LLM provider
        token_updates = _accumulate_tokens(state, llm)
        if token_updates:
            result.update(token_updates)
            budget_error = _enforce_token_budget(state, result)
            if budget_error:
                result = budget_error

        # Handle error - set requires_human to stop downstream execution
        if "error" in result:
            _log_agent_node_outcome(state, repo, agent_name, result, latency_ms=agent_latency_ms)
            _finalize_run(state, repo, "failed", result["error"])
            # P1 fix: Ensure requires_human is set so route_by_chapter_status
            # safety gate catches this and routes to human_review
            result["requires_human"] = True
        else:
            _log_agent_node_outcome(state, repo, agent_name, result, latency_ms=agent_latency_ms)

        # Record step after running
        step_info = {
            "agent": agent_name,
            "status_before": status_before,
            "status_after": result.get("chapter_status", status_before),
            "error": result.get("error"),
            "contract_ok": contract_ok,
            "contract_issues": contract_issues if contract_issues else None,
        }
        _append_step(state, step_info)

        return result

    # Return dict of agent name -> node function
    return {
        "planner": lambda s: _run_agent_node("planner", PlannerAgent, s),
        "screenwriter": lambda s: _run_agent_node("screenwriter", ScreenwriterAgent, s),
        "author": lambda s: _run_agent_node("author", AuthorAgent, s),
        "polisher": lambda s: _run_agent_node("polisher", PolisherAgent, s),
        "editor": lambda s: _run_agent_node("editor", EditorAgent, s),
        "memory_curator": lambda s: _run_agent_node("memory_curator", MemoryCuratorAgent, s),
    }


# ── Node implementations ───────────────────────────────────────


def health_check_node(state: FactoryState, repo: Repository) -> dict[str, Any]:
    """Check database health and ensure workflow_run_id exists.

    Creates a new workflow_run if state does not already have one.
    This is the entry point of the graph.
    """
    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)
    run_id = state.get("workflow_run_id")

    updates: dict[str, Any] = {}

    if not run_id:
        run_id = repo.create_workflow_run(project_id, chapter_number)
        updates["workflow_run_id"] = run_id
        logger.info("Created workflow_run %s for project=%s chapter=%s", run_id, project_id, chapter_number)
    else:
        updates["workflow_run_id"] = run_id

    event_state = {**state, "workflow_run_id": run_id}
    _update_run_node(event_state, repo, "health_check")
    _log_node_event(event_state, repo, "health_check", "started", status="running")
    _log_node_event(event_state, repo, "health_check", "completed", status="completed")

    return updates


def task_discovery_node(state: FactoryState, repo: Repository) -> dict[str, Any]:
    """Discover what needs to be done based on chapter status.

    Reads the current chapter status from DB (source of truth).
    If DB status differs from FactoryState, uses DB status.
    If chapter does not exist in DB, returns error with requires_human=True.

    v5.3.0: Also checks if instruction exists for Planner 必经 routing.
    """
    _update_run_node(state, repo, "task_discovery")
    _log_node_event(state, repo, "task_discovery", "started", status="running")

    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)
    if not project_id or not chapter_number:
        _log_node_event(state, repo, "task_discovery", "failed", status="failed", error_message="Missing project_id or chapter_number")
        _finalize_run(state, repo, "failed", "Missing project_id or chapter_number")
        return {"error": "Missing project_id or chapter_number"}

    db_status = repo.get_chapter_status(project_id, chapter_number)
    if not db_status:
        _log_node_event(state, repo, "task_discovery", "failed", status="failed", error_message="Chapter not found in DB")
        _finalize_run(state, repo, "blocked", "Chapter not found in DB")
        return {"error": "Chapter not found in DB", "requires_human": True, "chapter_status": "blocking"}

    # v5.3.0: Check if instruction exists for Planner 必经 routing
    instruction = repo.get_instruction(project_id, chapter_number)
    has_instruction = instruction is not None and bool(instruction.get("objective"))

    state_status = state.get("chapter_status", "")
    if db_status == ChapterStatus.REVISION.value:
        base_state = {
            **state,
            "chapter_status": db_status,
            "has_instruction": has_instruction,
        }
        hydrated = hydrate_revision_state(base_state, repo)
        hydrated_updates = {
            key: value
            for key, value in hydrated.items()
            if key not in state or state.get(key) != value
        }
        hydrated_updates["chapter_status"] = db_status
        hydrated_updates["has_instruction"] = has_instruction
        _log_node_event(state, repo, "task_discovery", "completed", status="completed")
        return hydrated_updates

    if db_status != state_status:
        logger.info(
            "task_discovery: DB status '%s' overrides state status '%s'",
            db_status, state_status,
        )
        _log_node_event(state, repo, "task_discovery", "completed", status="completed")
        return {"chapter_status": db_status, "has_instruction": has_instruction}

    _log_node_event(state, repo, "task_discovery", "completed", status="completed")
    return {"has_instruction": has_instruction}


def _v6_agent_kwargs(repo: Repository, skill_registry: Any | None = None) -> dict[str, Any]:
    """v6.0: Build shared kwargs for core agent instantiation in legacy mode."""
    return {
        "skill_registry": _ensure_skill_registry(skill_registry),
        "tool_registry": _ensure_tool_registry(),
        "trace_store": _ensure_trace_store(repo),
    }


def planner_node(state: FactoryState, repo: Repository, llm: LLMProvider, skill_registry=None) -> dict[str, Any]:
    """Run the Planner agent."""
    blocking_guard = _guard_blocking_db_status(state, repo)
    if blocking_guard:
        return blocking_guard
    _update_run_node(state, repo, "planner")
    _log_node_event(state, repo, "planner", "started", status="running")
    agent = PlannerAgent(repo, llm, **_v6_agent_kwargs(repo, skill_registry))
    result = agent.run(state)
    # v5.2: Accumulate token usage
    token_updates = _accumulate_tokens(state, llm)
    if token_updates:
        result.update(token_updates)
        budget_error = _enforce_token_budget(state, result)
        if budget_error:
            result = budget_error
    if "error" in result:
        _log_agent_node_outcome(state, repo, "planner", result)
        _finalize_run(state, repo, "failed", result["error"])
        result["requires_human"] = True  # P1 fix
    else:
        _log_agent_node_outcome(state, repo, "planner", result)
    return result


def screenwriter_node(state: FactoryState, repo: Repository, llm: LLMProvider, skill_registry=None) -> dict[str, Any]:
    """Run the Screenwriter agent."""
    blocking_guard = _guard_blocking_db_status(state, repo)
    if blocking_guard:
        return blocking_guard
    _update_run_node(state, repo, "screenwriter")
    _log_node_event(state, repo, "screenwriter", "started", status="running")
    audit = _save_memory_context_audit_if_missing(
        state,
        repo,
        built_at_node="screenwriter_node",
    )
    agent = ScreenwriterAgent(repo, llm, **_v6_agent_kwargs(repo, skill_registry))
    result = agent.run(state)
    if audit:
        result.setdefault("memory_context_audit", audit)
    # v5.2: Accumulate token usage
    token_updates = _accumulate_tokens(state, llm)
    if token_updates:
        result.update(token_updates)
        budget_error = _enforce_token_budget(state, result)
        if budget_error:
            result = budget_error
    if "error" in result:
        _log_agent_node_outcome(state, repo, "screenwriter", result)
        _finalize_run(state, repo, "failed", result["error"])
        result["requires_human"] = True  # P1 fix
    else:
        _log_agent_node_outcome(state, repo, "screenwriter", result)
    return result


def author_node(state: FactoryState, repo: Repository, llm: LLMProvider, skill_registry=None) -> dict[str, Any]:
    """Run the Author agent."""
    blocking_guard = _guard_blocking_db_status(state, repo)
    if blocking_guard:
        return blocking_guard
    _update_run_node(state, repo, "author")
    _log_node_event(state, repo, "author", "started", status="running")
    agent = AuthorAgent(repo, llm, **_v6_agent_kwargs(repo, skill_registry))
    result = _handle_retryable_quality_gate(state, repo, agent.run(state))
    # v5.2: Accumulate token usage
    token_updates = _accumulate_tokens(state, llm)
    if token_updates:
        result.update(token_updates)
        budget_error = _enforce_token_budget(state, result)
        if budget_error:
            result = budget_error
    if "error" in result:
        _log_agent_node_outcome(state, repo, "author", result)
        _finalize_run(state, repo, "failed", result["error"])
        result["requires_human"] = True  # P1 fix
    else:
        _log_agent_node_outcome(state, repo, "author", result)
    return result


def polisher_node(state: FactoryState, repo: Repository, llm: LLMProvider, skill_registry=None) -> dict[str, Any]:
    """Run the Polisher agent."""
    blocking_guard = _guard_blocking_db_status(state, repo)
    if blocking_guard:
        return blocking_guard
    _update_run_node(state, repo, "polisher")
    _log_node_event(state, repo, "polisher", "started", status="running")
    agent = PolisherAgent(repo, llm, **_v6_agent_kwargs(repo, skill_registry))
    result = _handle_retryable_quality_gate(state, repo, agent.run(state))
    # v5.2: Accumulate token usage
    token_updates = _accumulate_tokens(state, llm)
    if token_updates:
        result.update(token_updates)
        budget_error = _enforce_token_budget(state, result)
        if budget_error:
            result = budget_error
    if "error" in result:
        _log_agent_node_outcome(state, repo, "polisher", result)
        _finalize_run(state, repo, "failed", result["error"])
        result["requires_human"] = True  # P1 fix
    else:
        _log_agent_node_outcome(state, repo, "polisher", result)
    return result


def editor_node(state: FactoryState, repo: Repository, llm: LLMProvider, skill_registry=None) -> dict[str, Any]:
    """Run the Editor agent."""
    blocking_guard = _guard_blocking_db_status(state, repo)
    if blocking_guard:
        return blocking_guard
    _update_run_node(state, repo, "editor")
    _log_node_event(state, repo, "editor", "started", status="running")
    agent = EditorAgent(repo, llm, **_v6_agent_kwargs(repo, skill_registry))
    result = agent.run(state)
    # v5.2: Accumulate token usage
    token_updates = _accumulate_tokens(state, llm)
    if token_updates:
        result.update(token_updates)
        budget_error = _enforce_token_budget(state, result)
        if budget_error:
            result = budget_error
    if "error" in result:
        _log_agent_node_outcome(state, repo, "editor", result)
        _finalize_run(state, repo, "failed", result["error"])
        result["requires_human"] = True  # P1 fix
    else:
        _log_agent_node_outcome(state, repo, "editor", result)
    return result


def memory_curator_node(state: FactoryState, repo: Repository, llm: LLMProvider, skill_registry=None) -> dict[str, Any]:
    """Run the Memory Curator agent to extract story facts from reviewed chapter.

    v5.3.2 closure: In real mode, failure is blocking (requires_human=True).
    In stub mode, failure is non-blocking (log and continue).
    """
    blocking_guard = _guard_blocking_db_status(state, repo)
    if blocking_guard:
        return blocking_guard
    _update_run_node(state, repo, "memory_curator")
    _log_node_event(state, repo, "memory_curator", "started", status="running")
    agent = MemoryCuratorAgent(repo, llm, **_v6_agent_kwargs(repo, skill_registry))
    result = agent.run(state)
    memory_error = _memory_curator_real_mode_error(state, result)
    if memory_error and "error" not in result:
        result["error"] = memory_error
        result["requires_human"] = True
    # Accumulate token usage
    token_updates = _accumulate_tokens(state, llm)
    if token_updates:
        result.update(token_updates)
        budget_error = _enforce_token_budget(state, result)
        if budget_error:
            result = budget_error
    if "error" in result:
        llm_mode = state.get("llm_mode", "stub")
        if llm_mode == "real":
            # Real mode: memory extraction failure blocks publish
            logger.error("MemoryCurator failed (real mode): %s", result["error"])
            _log_node_event(state, repo, "memory_curator", "failed", status="failed", error_message=result["error"])
            _finalize_run(state, repo, "failed", result["error"])
            result["requires_human"] = True
        else:
            # Stub mode: non-blocking, log and continue
            logger.warning("MemoryCurator failed (stub mode): %s", result["error"])
            _log_node_event(state, repo, "memory_curator", "failed", status="failed", error_message=result["error"])
            result.pop("error", None)
            result["requires_human"] = False
    else:
        _log_node_event(state, repo, "memory_curator", "completed", status="completed")
    return result


def publisher_node(state: FactoryState, repo: Repository) -> dict[str, Any]:
    """Publish a reviewed chapter.

    v6.7.9: Runs narrative continuity gate before publishing.
    Blocking continuity issues prevent auto-publish.
    """
    _update_run_node(state, repo, "publisher")
    _log_node_event(state, repo, "publisher", "started", status="running")

    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)

    # v6.7.9: Continuity gate before publish
    try:
        from ..quality.continuity_gate import evaluate_publish_continuity, SEVERITY_BLOCKING

        continuity_result = evaluate_publish_continuity(repo, project_id, chapter_number)
        if continuity_result.should_block_publish or continuity_result.severity == SEVERITY_BLOCKING:
            error_msg = (
                "发布前连续性检查未通过：" + "; ".join(continuity_result.issues[:3])
            )
            _log_node_event(
                state, repo, "publisher", "failed",
                status="failed", error_message=error_msg,
            )
            _finalize_run(state, repo, "failed", error_msg)
            return {
                "error": error_msg,
                "requires_human": True,
                "continuity_gate": continuity_result.to_dict(),
            }
        if continuity_result.issues:
            # Advisory/warning: log but do not block
            _log_node_event(
                state, repo, "publisher", "completed",
                status="warning",
                error_message="发布通过，但存在连续性建议：" + "; ".join(continuity_result.issues[:2]),
            )
    except Exception:
        logger.warning("Publisher: continuity gate failed (best-effort)", exc_info=True)

    ok = repo.publish_chapter(project_id, chapter_number)
    if not ok:
        _log_node_event(state, repo, "publisher", "failed", status="failed", error_message="Failed to publish chapter")
        _finalize_run(state, repo, "failed", "Failed to publish chapter")
        return {"error": "Failed to publish chapter"}

    _log_node_event(state, repo, "publisher", "completed", status="completed")
    return {
        "chapter_status": ChapterStatus.PUBLISHED.value,
        "current_stage": "published",
    }


def awaiting_publish_node(state: FactoryState, repo: Repository) -> dict[str, Any]:
    """v5.3.0: Real mode - stop at reviewed status, await manual publish confirmation.

    This node is used when llm_mode == "real" to prevent auto-publishing.
    The chapter stays in 'reviewed' status until manually published.
    """
    _update_run_node(state, repo, "awaiting_publish")
    _log_node_event(state, repo, "awaiting_publish", "started", status="running")

    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)

    logger.info(
        "AwaitingPublish: project=%s chapter=%s reviewed, awaiting manual publish",
        project_id, chapter_number,
    )

    # Mark workflow run as completed (review done, but not published)
    _finalize_run(state, repo, "completed")
    _log_node_event(state, repo, "awaiting_publish", "completed", status="completed")

    return {
        "chapter_status": ChapterStatus.REVIEWED.value,
        "current_stage": "reviewed",
        "awaiting_publish": True,
    }


def revision_router_node(state: FactoryState, repo: Repository | None = None) -> dict[str, Any]:
    """Determine where to route revision based on review result.

    v6.2: Added mid-run hydration to protect against state corruption
    during long-running revision flows.
    v6.8.2: Enhanced hydration to include retry_count and force-load _revision_review from DB.
    """
    if repo is not None:
        _update_run_node(state, repo, "revision_router")
        _log_node_event(state, repo, "revision_router", "started", status="running")

        # Mid-run protection: re-hydrate revision state if needed. Return any
        # recovered fields so LangGraph merges them before conditional routing.
        from .conditions import hydrate_revision_state
        hydrated = hydrate_revision_state(state, repo)
        updates = {
            key: hydrated[key]
            for key in ("quality_gate", "_revision_review", "retry_count")
            if hydrated.get(key) != state.get(key)
        }

        # v6.8.2: Force-load _revision_review from DB if still missing after hydration
        if not updates.get("_revision_review"):
            project_id = state.get("project_id")
            chapter_number = state.get("chapter_number")
            if project_id and chapter_number:
                try:
                    chapter = repo.get_chapter(project_id, chapter_number)
                    if chapter:
                        review = repo.get_latest_review(project_id, chapter["id"])
                        if review:
                            updates["_revision_review"] = {
                                "review_id": review.get("id"),
                                "score": review.get("score"),
                                "revision_target": review.get("revision_target"),
                                "issues": review.get("issues") or [],
                                "suggestions": review.get("suggestions") or [],
                            }
                            logger.info(
                                "revision_router: force-loaded _revision_review from DB for %s ch%d (review_id=%s)",
                                project_id, chapter_number, review.get("id"),
                            )
                except Exception:
                    logger.warning(
                        "revision_router: failed to force-load _revision_review for %s ch%d",
                        project_id, chapter_number,
                        exc_info=True,
                    )

        _log_node_event(state, repo, "revision_router", "completed", status="completed")
        return updates
    # Pass through — routing is handled by conditional edges
    return {}


def human_review_node(state: FactoryState, repo: Repository) -> dict[str, Any]:
    """Handle blocking/human intervention scenarios."""
    _update_run_node(state, repo, "human_review")
    _log_node_event(state, repo, "human_review", "started", status="running")
    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)
    gate = state.get("quality_gate", {}) or {}
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)
    error = state.get("error")
    # v6.6.21: Distinguish human_review severity by root cause
    is_quality_gate_maxed = False
    is_preexisting_block = False
    if not error and gate.get("pass") is False:
        score = gate.get("score")
        target = revision_target_from_state(state)
        is_quality_gate_maxed = True
        # P1: Include quality gate details (word count, etc.) in blocking error
        error = (
            f"章节审核未通过，已达到最大返修次数 "
            f"({retry_count}/{max_retries})，建议人工检查。"
            f"退回目标: {target}"
        )
        if score is not None:
            error += f"，评分: {score}"
        if gate.get("word_count_fail"):
            actual_wc = gate.get("actual_word_count")
            word_target = gate.get("word_target")
            if actual_wc is not None and word_target is not None:
                error += f"，该次失败字数: {actual_wc} (目标 {word_target})"
        if gate.get("scene_beat_coverage_fail"):
            error += "，该次失败原因: 正文未覆盖完整场景 beat / 章末钩子"

    if not error and state.get("chapter_status") == ChapterStatus.BLOCKING.value:
        is_preexisting_block = True
        error = "章节已处于阻塞状态，请先解除阻塞后再重新执行工作流。"

    if project_id and chapter_number:
        current_status = repo.get_chapter_status(project_id, chapter_number)
        if current_status not in (ChapterStatus.PUBLISHED.value, ChapterStatus.REVIEWED.value):
            repo.update_chapter_status(project_id, chapter_number, ChapterStatus.BLOCKING.value)

    _finalize_run(state, repo, "blocked", error=error)
    # v6.6.21: human_review severity mapping
    # - quality gate maxed / pre-existing block -> expected, needs human intervention
    # - unexpected system error -> genuinely failed
    is_unexpected_error = error and not is_quality_gate_maxed and not is_preexisting_block
    if is_unexpected_error:
        # Unexpected system error: genuinely failed
        _log_node_event(state, repo, "human_review", "failed", status="failed", error_message=error)
        logger.error(
            "Human review triggered by unexpected error: project=%s chapter=%s error=%s",
            project_id, chapter_number, error,
        )
    else:
        # Expected human intervention (quality gate maxed / pre-existing block)
        _log_node_event(state, repo, "human_review", "completed", status="warning", error_message=error)
        logger.warning(
            "Human intervention required: project=%s chapter=%s",
            project_id, chapter_number,
        )
    return {
        "requires_human": True,
        "chapter_status": ChapterStatus.BLOCKING.value,
        "error": error,
    }


def archive_node(state: FactoryState, repo: Repository) -> dict[str, Any]:
    """Archive after publishing. Marks workflow run as completed."""
    _update_run_node(state, repo, "archive")
    _log_node_event(state, repo, "archive", "started", status="running")
    # P1 fix: Clear error_message when marking as completed
    _finalize_run(state, repo, "completed", error=None)
    _log_node_event(state, repo, "archive", "completed", status="completed")
    logger.info(
        "Archive: project=%s chapter=%s published",
        state.get("project_id"), state.get("chapter_number"),
    )
    return {}
