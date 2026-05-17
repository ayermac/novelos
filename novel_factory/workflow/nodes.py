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
from ..agents.planner import PlannerAgent
from ..agents.screenwriter import ScreenwriterAgent
from ..agents.author import AuthorAgent
from ..agents.polisher import PolisherAgent
from ..agents.editor import EditorAgent
from ..agents.memory_curator import MemoryCuratorAgent
from .execution_events import (
    log_execution_event,
    CONTEXT_SUMMARIZERS,
    build_context_loaded_message,
    verify_agent_completion_evidence,
    EVENT_CONTEXT_LOADED,
    EVENT_LLM_STARTED,
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
    "planner": {"started": "开始章节规划", "completed": "已生成章节规划", "failed": "章节规划失败"},
    "screenwriter": {"started": "开始编剧", "completed": "已生成章节场景规划", "failed": "编剧失败"},
    "author": {"started": "开始执笔撰写", "completed": "已生成章节初稿", "failed": "执笔撰写失败"},
    "polisher": {"started": "开始润色", "completed": "润色完成", "failed": "润色失败"},
    "editor": {"started": "开始审核", "completed": "审核完成", "failed": "审核失败"},
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


def _update_run_node(state: FactoryState, repo: Repository, node_name: str) -> None:
    """Update workflow_runs.current_node if a run_id exists in state."""
    run_id = state.get("workflow_run_id")
    if run_id:
        repo.update_workflow_run(run_id, current_node=node_name)


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


def _handle_retryable_quality_gate(
    state: FactoryState,
    repo: Repository,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Convert retryable quality gate failures into revision routing.

    Author/Polisher word-count failures and death-penalty red-line failures
    are expected recoverable defects. They should consume a revision attempt
    and route back to the responsible agent until the chapter-level retry cap
    is reached. Other errors remain blocking.
    """
    gate = result.get("quality_gate") or {}
    retryable_gate = gate.get("word_count_fail") or gate.get("death_penalty_fail")
    if not result.get("error") or not retryable_gate:
        return result

    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)
    retry_count = repo.get_chapter_retry_count(project_id, chapter_number)
    max_retries = state.get("max_retries", 3)
    if retry_count >= max_retries:
        result["requires_human"] = True
        result["retry_count"] = retry_count
        return result

    revision_target = gate.get("revision_target") or "author"
    current_status = repo.get_chapter_status(project_id, chapter_number)
    if current_status not in (
        ChapterStatus.BLOCKING.value,
        ChapterStatus.PUBLISHED.value,
        ChapterStatus.REVIEWED.value,
    ):
        repo.update_chapter_status(project_id, chapter_number, ChapterStatus.REVISION.value)

    task_id = repo.start_task(
        project_id, chapter_number, "revise", revision_target,
        workflow_run_id=state.get("workflow_run_id"),
    )
    repo.complete_task(task_id, success=True)

    updated = dict(result)
    updated.pop("error", None)
    updated["chapter_status"] = ChapterStatus.REVISION.value
    updated["current_stage"] = "revision"
    updated["retry_count"] = retry_count + 1
    updated["requires_human"] = False
    return updated


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
    except Exception as e:
        logger.warning(f"Failed to create SkillRegistry: {e}")
        return None


def _ensure_tool_registry() -> Any | None:
    """v6.0: Create a default ToolRegistry for agent tool runtime."""
    try:
        from ..tools.registry import ToolRegistry
        return ToolRegistry()
    except Exception as e:
        logger.warning(f"Failed to create ToolRegistry: {e}")
        return None


def _ensure_trace_store(repo: Repository) -> Any | None:
    """v6.0: Create a DecisionTraceStore backed by repository."""
    try:
        from ..agent_runtime.decision_trace import DecisionTraceStore
        return DecisionTraceStore(repo)
    except Exception as e:
        logger.warning(f"Failed to create DecisionTraceStore: {e}")
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
        _update_run_node(state, repo, agent_name)
        _log_node_event(state, repo, agent_name, "started", status="running")

        # Record step before running (for run_with_graph return value)
        status_before = state.get("chapter_status", "")

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
                contract_ok, contract_issues = validate_handoff(prev_agent, agent_name, artifact)
                if not contract_ok:
                    logger.warning(
                        "Handoff contract %s -> %s failed: %s",
                        prev_agent, agent_name, contract_issues,
                    )
            except Exception:
                pass  # Best-effort; never block workflow

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
        if agent_name in ("planner", "screenwriter", "author", "polisher", "editor", "memory_curator"):
            agent = agent_cls(
                repo, llm,
                skill_registry=effective_skill_registry,
                tool_registry=effective_tool_registry,
                trace_store=effective_trace_store,
            )
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
                pass  # Best-effort

        agent_started_at = time.perf_counter()
        log_execution_event(
            repo, state, agent_name, EVENT_LLM_STARTED,
            message=f"开始调用模型：{agent_name}",
            agent_id=agent_name,
            status="running",
        )
        result = _handle_retryable_quality_gate(state, repo, agent.run(state))
        agent_latency_ms = int((time.perf_counter() - agent_started_at) * 1000)

        # v6.1: Agent-specific execution events are emitted by the agent, but
        # keep the high-level LLM completion/failure event adjacent to
        # llm_started so the timeline reads naturally.
        exec_events = result.pop("_exec_events", [])
        used_fallback = any(ev.get("event_type") == EVENT_FALLBACK_USED for ev in exec_events)

        # v6.1: Log LLM completion/failure
        if "error" in result:
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
                pass  # Best-effort

        # v6.1: Verify completion evidence on success
        if "error" not in result and agent_name in ("planner", "screenwriter", "author", "polisher", "editor", "memory_curator"):
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
                    ev_msg = "完成证据校验通过"
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
                pass  # Best-effort; never block workflow

        # v5.2: Accumulate token usage from LLM provider
        token_updates = _accumulate_tokens(state, llm)
        if token_updates:
            result.update(token_updates)
            budget_error = _enforce_token_budget(state, result)
            if budget_error:
                result = budget_error

        # Handle error - set requires_human to stop downstream execution
        if "error" in result:
            _log_node_event(
                state,
                repo,
                agent_name,
                "failed",
                status="failed",
                error_message=result["error"],
                token_count=result.get("total_tokens"),
                latency_ms=agent_latency_ms,
            )
            _finalize_run(state, repo, "failed", result["error"])
            # P1 fix: Ensure requires_human is set so route_by_chapter_status
            # safety gate catches this and routes to human_review
            result["requires_human"] = True
        else:
            _log_node_event(
                state,
                repo,
                agent_name,
                "completed",
                status="completed",
                token_count=result.get("total_tokens"),
                latency_ms=agent_latency_ms,
            )

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
        _log_node_event(state, repo, "planner", "failed", status="failed", error_message=result["error"])
        _finalize_run(state, repo, "failed", result["error"])
        result["requires_human"] = True  # P1 fix
    else:
        _log_node_event(state, repo, "planner", "completed", status="completed")
    return result


def screenwriter_node(state: FactoryState, repo: Repository, llm: LLMProvider, skill_registry=None) -> dict[str, Any]:
    """Run the Screenwriter agent."""
    _update_run_node(state, repo, "screenwriter")
    _log_node_event(state, repo, "screenwriter", "started", status="running")
    agent = ScreenwriterAgent(repo, llm, **_v6_agent_kwargs(repo, skill_registry))
    result = agent.run(state)
    # v5.2: Accumulate token usage
    token_updates = _accumulate_tokens(state, llm)
    if token_updates:
        result.update(token_updates)
        budget_error = _enforce_token_budget(state, result)
        if budget_error:
            result = budget_error
    if "error" in result:
        _log_node_event(state, repo, "screenwriter", "failed", status="failed", error_message=result["error"])
        _finalize_run(state, repo, "failed", result["error"])
        result["requires_human"] = True  # P1 fix
    else:
        _log_node_event(state, repo, "screenwriter", "completed", status="completed")
    return result


def author_node(state: FactoryState, repo: Repository, llm: LLMProvider, skill_registry=None) -> dict[str, Any]:
    """Run the Author agent."""
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
        _log_node_event(state, repo, "author", "failed", status="failed", error_message=result["error"])
        _finalize_run(state, repo, "failed", result["error"])
        result["requires_human"] = True  # P1 fix
    else:
        _log_node_event(state, repo, "author", "completed", status="completed")
    return result


def polisher_node(state: FactoryState, repo: Repository, llm: LLMProvider, skill_registry=None) -> dict[str, Any]:
    """Run the Polisher agent."""
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
        _log_node_event(state, repo, "polisher", "failed", status="failed", error_message=result["error"])
        _finalize_run(state, repo, "failed", result["error"])
        result["requires_human"] = True  # P1 fix
    else:
        _log_node_event(state, repo, "polisher", "completed", status="completed")
    return result


def editor_node(state: FactoryState, repo: Repository, llm: LLMProvider, skill_registry=None) -> dict[str, Any]:
    """Run the Editor agent."""
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
        _log_node_event(state, repo, "editor", "failed", status="failed", error_message=result["error"])
        _finalize_run(state, repo, "failed", result["error"])
        result["requires_human"] = True  # P1 fix
    else:
        _log_node_event(state, repo, "editor", "completed", status="completed")
    return result


def memory_curator_node(state: FactoryState, repo: Repository, llm: LLMProvider, skill_registry=None) -> dict[str, Any]:
    """Run the Memory Curator agent to extract story facts from reviewed chapter.

    v5.3.2 closure: In real mode, failure is blocking (requires_human=True).
    In stub mode, failure is non-blocking (log and continue).
    """
    _update_run_node(state, repo, "memory_curator")
    _log_node_event(state, repo, "memory_curator", "started", status="running")
    agent = MemoryCuratorAgent(repo, llm, **_v6_agent_kwargs(repo, skill_registry))
    result = agent.run(state)
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
    """Publish a reviewed chapter."""
    _update_run_node(state, repo, "publisher")
    _log_node_event(state, repo, "publisher", "started", status="running")

    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)

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
    """Determine where to route revision based on review result."""
    if repo is not None:
        _update_run_node(state, repo, "revision_router")
        _log_node_event(state, repo, "revision_router", "started", status="running")
        _log_node_event(state, repo, "revision_router", "completed", status="completed")
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
    if not error and gate.get("pass") is False:
        score = gate.get("score")
        target = gate.get("revision_target") or "author"
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

    if not error and state.get("chapter_status") == ChapterStatus.BLOCKING.value:
        error = "章节已处于阻塞状态，请先解除阻塞后再重新执行工作流。"

    if project_id and chapter_number:
        current_status = repo.get_chapter_status(project_id, chapter_number)
        if current_status not in (ChapterStatus.PUBLISHED.value, ChapterStatus.REVIEWED.value):
            repo.update_chapter_status(project_id, chapter_number, ChapterStatus.BLOCKING.value)

    _finalize_run(state, repo, "blocked", error=error)
    _log_node_event(state, repo, "human_review", "failed", status="failed", error_message=error)
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
