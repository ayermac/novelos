"""LangGraph node functions for the chapter production workflow.

Each node takes a FactoryState and returns a dict of updates to merge.
v1.1: Nodes now track workflow_runs lifecycle and update current_node.
v5.1.6: Added create_node_runners for LLMRouter-based dependency injection.
"""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


# ── Helper ──────────────────────────────────────────────────────


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

    task_id = repo.start_task(project_id, chapter_number, "revise", revision_target)
    repo.complete_task(task_id, success=True)

    updated = dict(result)
    updated.pop("error", None)
    updated["chapter_status"] = ChapterStatus.REVISION.value
    updated["current_stage"] = "revision"
    updated["retry_count"] = retry_count + 1
    updated["requires_human"] = False
    return updated


# ── v5.1.6: Node factory for LLMRouter-based injection ────────────────


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

    def _run_agent_node(
        agent_name: str,
        agent_cls: type,
        state: FactoryState,
    ) -> dict[str, Any]:
        """Generic agent runner with LLMRouter + error handling.

        Equivalent to dispatch/chapter.py ChapterDispatchMixin._run_agent().
        """
        _update_run_node(state, repo, agent_name)

        # Record step before running (for run_with_graph return value)
        status_before = state.get("chapter_status", "")

        # Get LLM for this agent
        try:
            llm = llm_router.for_agent(agent_name)
        except ValueError as e:
            logger.error(f"LLM configuration error for agent '{agent_name}': {e}")
            _finalize_run(state, repo, "failed", str(e))
            return {
                "error": str(e),
                "chapter_status": status_before,
                "requires_human": True,
            }

        # Inject skill_registry for Polisher and Editor
        if agent_name in ("polisher", "editor") and skill_registry is not None:
            agent = agent_cls(repo, llm, skill_registry=skill_registry)
        else:
            agent = agent_cls(repo, llm)

        result = _handle_retryable_quality_gate(state, repo, agent.run(state))

        # v5.2: Accumulate token usage from LLM provider
        token_updates = _accumulate_tokens(state, llm)
        if token_updates:
            result.update(token_updates)

        # Handle error - set requires_human to stop downstream execution
        if "error" in result:
            _finalize_run(state, repo, "failed", result["error"])
            # P1 fix: Ensure requires_human is set so route_by_chapter_status
            # safety gate catches this and routes to human_review
            result["requires_human"] = True

        # Record step after running
        step_info = {
            "agent": agent_name,
            "status_before": status_before,
            "status_after": result.get("chapter_status", status_before),
            "error": result.get("error"),
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
        _update_run_node(state, repo, "health_check")

    return updates


def task_discovery_node(state: FactoryState, repo: Repository) -> dict[str, Any]:
    """Discover what needs to be done based on chapter status.

    Reads the current chapter status from DB (source of truth).
    If DB status differs from FactoryState, uses DB status.
    If chapter does not exist in DB, returns error with requires_human=True.

    v5.3.0: Also checks if instruction exists for Planner 必经 routing.
    """
    _update_run_node(state, repo, "task_discovery")

    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)
    if not project_id or not chapter_number:
        _finalize_run(state, repo, "failed", "Missing project_id or chapter_number")
        return {"error": "Missing project_id or chapter_number"}

    db_status = repo.get_chapter_status(project_id, chapter_number)
    if not db_status:
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
        return {"chapter_status": db_status, "has_instruction": has_instruction}

    return {"has_instruction": has_instruction}


def planner_node(state: FactoryState, repo: Repository, llm: LLMProvider) -> dict[str, Any]:
    """Run the Planner agent."""
    _update_run_node(state, repo, "planner")
    agent = PlannerAgent(repo, llm)
    result = agent.run(state)
    # v5.2: Accumulate token usage
    token_updates = _accumulate_tokens(state, llm)
    if token_updates:
        result.update(token_updates)
    if "error" in result:
        _finalize_run(state, repo, "failed", result["error"])
        result["requires_human"] = True  # P1 fix
    return result


def screenwriter_node(state: FactoryState, repo: Repository, llm: LLMProvider) -> dict[str, Any]:
    """Run the Screenwriter agent."""
    _update_run_node(state, repo, "screenwriter")
    agent = ScreenwriterAgent(repo, llm)
    result = agent.run(state)
    # v5.2: Accumulate token usage
    token_updates = _accumulate_tokens(state, llm)
    if token_updates:
        result.update(token_updates)
    if "error" in result:
        _finalize_run(state, repo, "failed", result["error"])
        result["requires_human"] = True  # P1 fix
    return result


def author_node(state: FactoryState, repo: Repository, llm: LLMProvider) -> dict[str, Any]:
    """Run the Author agent."""
    _update_run_node(state, repo, "author")
    agent = AuthorAgent(repo, llm)
    result = _handle_retryable_quality_gate(state, repo, agent.run(state))
    # v5.2: Accumulate token usage
    token_updates = _accumulate_tokens(state, llm)
    if token_updates:
        result.update(token_updates)
    if "error" in result:
        _finalize_run(state, repo, "failed", result["error"])
        result["requires_human"] = True  # P1 fix
    return result


def polisher_node(state: FactoryState, repo: Repository, llm: LLMProvider, skill_registry=None) -> dict[str, Any]:
    """Run the Polisher agent."""
    _update_run_node(state, repo, "polisher")
    # R4: Support skill_registry injection
    if skill_registry is None:
        try:
            from ..skills.registry import SkillRegistry
            skill_registry = SkillRegistry()
        except Exception as e:
            logger.warning(f"Failed to create SkillRegistry: {e}")
    agent = PolisherAgent(repo, llm, skill_registry=skill_registry)
    result = _handle_retryable_quality_gate(state, repo, agent.run(state))
    # v5.2: Accumulate token usage
    token_updates = _accumulate_tokens(state, llm)
    if token_updates:
        result.update(token_updates)
    if "error" in result:
        _finalize_run(state, repo, "failed", result["error"])
        result["requires_human"] = True  # P1 fix
    return result


def editor_node(state: FactoryState, repo: Repository, llm: LLMProvider, skill_registry=None) -> dict[str, Any]:
    """Run the Editor agent."""
    _update_run_node(state, repo, "editor")
    # R4: Support skill_registry injection
    if skill_registry is None:
        try:
            from ..skills.registry import SkillRegistry
            skill_registry = SkillRegistry()
        except Exception as e:
            logger.warning(f"Failed to create SkillRegistry: {e}")
    agent = EditorAgent(repo, llm, skill_registry=skill_registry)
    result = agent.run(state)
    # v5.2: Accumulate token usage
    token_updates = _accumulate_tokens(state, llm)
    if token_updates:
        result.update(token_updates)
    if "error" in result:
        _finalize_run(state, repo, "failed", result["error"])
        result["requires_human"] = True  # P1 fix
    return result


def memory_curator_node(state: FactoryState, repo: Repository, llm: LLMProvider) -> dict[str, Any]:
    """Run the Memory Curator agent to extract story facts from reviewed chapter.

    v5.3.2 closure: In real mode, failure is blocking (requires_human=True).
    In stub mode, failure is non-blocking (log and continue).
    """
    _update_run_node(state, repo, "memory_curator")
    agent = MemoryCuratorAgent(repo, llm)
    result = agent.run(state)
    # Accumulate token usage
    token_updates = _accumulate_tokens(state, llm)
    if token_updates:
        result.update(token_updates)
    if "error" in result:
        llm_mode = state.get("llm_mode", "stub")
        if llm_mode == "real":
            # Real mode: memory extraction failure blocks publish
            logger.error("MemoryCurator failed (real mode): %s", result["error"])
            _finalize_run(state, repo, "failed", result["error"])
            result["requires_human"] = True
        else:
            # Stub mode: non-blocking, log and continue
            logger.warning("MemoryCurator failed (stub mode): %s", result["error"])
            result.pop("error", None)
            result["requires_human"] = False
    return result


def publisher_node(state: FactoryState, repo: Repository) -> dict[str, Any]:
    """Publish a reviewed chapter."""
    _update_run_node(state, repo, "publisher")

    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)

    ok = repo.publish_chapter(project_id, chapter_number)
    if not ok:
        _finalize_run(state, repo, "failed", "Failed to publish chapter")
        return {"error": "Failed to publish chapter"}

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

    project_id = state.get("project_id", "")
    chapter_number = state.get("chapter_number", 0)

    logger.info(
        "AwaitingPublish: project=%s chapter=%s reviewed, awaiting manual publish",
        project_id, chapter_number,
    )

    # Mark workflow run as completed (review done, but not published)
    _finalize_run(state, repo, "completed")

    return {
        "chapter_status": ChapterStatus.REVIEWED.value,
        "current_stage": "reviewed",
        "awaiting_publish": True,
    }


def revision_router_node(state: FactoryState) -> dict[str, Any]:
    """Determine where to route revision based on review result."""
    # Just pass through — routing is handled by conditional edges
    return {}


def human_review_node(state: FactoryState, repo: Repository) -> dict[str, Any]:
    """Handle blocking/human intervention scenarios."""
    _update_run_node(state, repo, "human_review")
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
    # P1 fix: Clear error_message when marking as completed
    _finalize_run(state, repo, "completed", error=None)
    logger.info(
        "Archive: project=%s chapter=%s published",
        state.get("project_id"), state.get("chapter_number"),
    )
    return {}
