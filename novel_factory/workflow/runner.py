"""LangGraph-based chapter production runner.

v5.1.6: Provides run_with_graph() that returns the same shape as Dispatcher.run_chapter().
v5.2 Phase C: Adds run_with_graph_stream() for SSE streaming support.
v5.2 Phase D: Adds SqliteSaver-based checkpoint persistence for recovery.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Generator

from ..config.settings import Settings
from ..models.state import ChapterStatus
from ..db.repository import Repository
from ..models.state import FactoryState
from ..quality.hub import DeadloopDetector
from .graph import compile_graph
from .conditions import hydrate_revision_state
from .continuation_plan import ensure_continuation_plan_for_chapter
from .checkpoint import (
    delete_checkpoint_thread,
    derive_checkpoint_db_path,
    get_checkpoint_config,
    get_sqlite_checkpointer,
)
from ..security.redaction import redact_sensitive_text
from ..guards.budget_sentinel import BudgetSentinel

logger = logging.getLogger(__name__)

STALE_RUNNING_RUN_SECONDS = 2 * 60 * 60
STREAM_VISIBLE_NODES = frozenset(
    {
        "planner",
        "screenwriter",
        "author",
        "polisher",
        "editor",
        "memory_curator",
        "publisher",
        "awaiting_publish",
        "human_review",
    }
)
GRAPH_SUCCESS_STATUSES = frozenset(
    {
        ChapterStatus.REVIEWED.value,
        "awaiting_publish",
        ChapterStatus.PUBLISHED.value,
    }
)


def _run_current_node(repo: Repository, state: FactoryState, fallback: str | None = None) -> str:
    """Resolve the best current node label for a run outcome message."""
    run_id = state.get("workflow_run_id")
    project_id = state.get("project_id")
    chapter_number = state.get("chapter_number")
    if run_id and project_id and chapter_number:
        try:
            runs = repo.get_workflow_runs_for_project(
                str(project_id),
                chapter_number=int(chapter_number),
                limit=10,
            )
            for run in runs:
                if (run.get("id") or run.get("run_id")) == run_id:
                    return run.get("current_node") or fallback or "workflow_exit_guard"
        except Exception:
            logger.debug("Failed to resolve workflow current_node for %s", run_id, exc_info=True)
    return fallback or "workflow_exit_guard"


def _graph_exit_error_message(state: FactoryState, current_node: str) -> str:
    """Explain a graph exit that did not reach a terminal workflow outcome."""
    chapter_status = state.get("chapter_status") or "unknown"
    return (
        "WORKFLOW_INTERRUPTED_BEFORE_TERMINAL: "
        f"workflow stopped at {current_node} while chapter_status={chapter_status}. "
        "The run was not finalized by a terminal node."
    )


def _graph_exit_is_success(state: FactoryState) -> bool:
    """Return True only when graph state represents a coherent successful exit."""
    if state.get("error"):
        return False
    if state.get("requires_human") and not state.get("awaiting_publish"):
        return False
    chapter_status = state.get("chapter_status") or ""
    if chapter_status == ChapterStatus.REVIEWED.value:
        return bool(state.get("awaiting_publish"))
    return chapter_status in GRAPH_SUCCESS_STATUSES


def _block_incomplete_graph_exit(
    repo: Repository,
    state: FactoryState,
    current_node: str | None = None,
) -> str:
    """Mark a run blocked when LangGraph exits before a terminal node."""
    node = _run_current_node(repo, state, current_node)
    message = _graph_exit_error_message(state, node)
    run_id = state.get("workflow_run_id")
    if run_id:
        try:
            repo.update_workflow_run(
                run_id,
                status="blocked",
                current_node=node,
                error_message=message,
                prompt_tokens=state.get("prompt_tokens", 0),
                completion_tokens=state.get("completion_tokens", 0),
                total_tokens=state.get("total_tokens", 0),
                duration_ms=state.get("duration_ms", 0),
            )
        except Exception:
            logger.warning("Failed to block incomplete workflow run %s", run_id, exc_info=True)

        try:
            repo.create_workflow_node_event(
                run_id=run_id,
                project_id=str(state.get("project_id", "")),
                chapter_number=int(state.get("chapter_number", 0)),
                node_name=node,
                event_type="workflow_interrupted",
                status="blocked",
                message=message,
                error_code="WORKFLOW_INTERRUPTED_BEFORE_TERMINAL",
                error_message=message,
            )
        except Exception:
            logger.debug("Failed to log incomplete workflow exit for %s", run_id, exc_info=True)
    return message


def _mark_run_failed(repo: Repository, run_id: str | None, error: str) -> None:
    """Best-effort workflow run failure finalization."""
    if not run_id:
        return
    try:
        repo.update_workflow_run(run_id, status="failed", error_message=error)
    except Exception:
        logger.warning("Failed to mark workflow run %s as failed", run_id, exc_info=True)


def _parse_workflow_timestamp(value: Any) -> datetime | None:
    """Parse repository workflow timestamps stored as SQLite datetime strings."""
    if not value:
        return None
    text = str(value).strip().replace("T", " ")
    if text.endswith("Z"):
        text = text[:-1]
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _running_run_is_recent(run: dict[str, Any], max_age_seconds: int = STALE_RUNNING_RUN_SECONDS) -> bool:
    """Return True when a running workflow run still looks actively resumable."""
    started_at = _parse_workflow_timestamp(run.get("started_at"))
    if started_at is None:
        return True
    # workflow_runs.started_at is stored as local China time via SQLite
    # datetime('now','+8 hours'), so compare against the same clock.
    now_local = datetime.utcnow() + timedelta(hours=8)
    age = now_local - started_at
    return age.total_seconds() <= max_age_seconds


def _clear_stale_checkpoint_for_new_run(
    repo: Repository,
    project_id: str,
    chapter_number: int,
) -> None:
    """Clear persisted graph state before a user-initiated fresh run.

    LangGraph checkpoints are keyed by project/chapter. If a previous run left
    a checkpoint after an agent had already advanced the DB status, a later
    manual retry can resume from that stale node and fail an optimistic status
    transition such as planned->scripted. Keep checkpoints only while the latest
    run is still marked running; every other new run starts from DB truth.

    v6.6.6: Enhanced with stale checkpoint detection and explanatory logging.
    """
    from .state_integrity import _checkpoint_is_stale, STALE_CHECKPOINT_SECONDS
    from .checkpoint import inspect_checkpoint_thread

    try:
        latest_runs = repo.get_workflow_runs_for_project(
            project_id, chapter_number=chapter_number, limit=1
        )
        latest_status = latest_runs[0].get("status") if latest_runs else None

        # Check if checkpoint exists at all
        checkpoint_info = None
        try:
            checkpoint_info = inspect_checkpoint_thread(repo.db_path, project_id, chapter_number)
        except Exception:
            pass

        checkpoint_exists = bool(checkpoint_info and checkpoint_info.get("checkpoint_exists"))

        if latest_status == "running" and _running_run_is_recent(latest_runs[0]):
            # Healthy running run - do NOT clear checkpoint
            logger.debug(
                "Skipping checkpoint clear for %s/%s: healthy running run",
                project_id, chapter_number,
            )
            return

        if latest_status == "running":
            # Stale running run - mark as failed and clear checkpoint
            run_id = latest_runs[0].get("id") or latest_runs[0].get("run_id")
            _mark_run_failed(
                repo,
                run_id,
                "Stale running workflow detected; clearing checkpoint before fresh run.",
            )
            logger.info(
                "Marked stale running run %s as failed for %s/%s",
                run_id, project_id, chapter_number,
            )

        # v6.6.6: Check if checkpoint is stale before clearing
        if checkpoint_exists:
            chapter = repo.get_chapter(project_id, chapter_number)
            chapter_status = chapter.get("status", "planned") if chapter else "planned"
            checkpoint_node = checkpoint_info.get("checkpoint_node")
            checkpoint_chapter_status = None  # Not easily available from inspect
            current_node = latest_runs[0].get("current_node") if latest_runs else None

            is_stale, stale_reason = _checkpoint_is_stale(
                run_status=latest_status,
                checkpoint_exists=checkpoint_exists,
                checkpoint_node=checkpoint_node,
                checkpoint_chapter_status=checkpoint_chapter_status,
                current_chapter_status=chapter_status,
                current_node=current_node,
                checkpoint_age_seconds=None,
            )

            if is_stale:
                logger.info(
                    "Clearing stale checkpoint for %s/%s: %s",
                    project_id, chapter_number, stale_reason,
                )
                # Record explanatory event if possible
                try:
                    run_id = latest_runs[0].get("id") if latest_runs else None
                    if run_id:
                        repo.create_workflow_node_event(
                            run_id=run_id,
                            project_id=project_id,
                            chapter_number=chapter_number,
                            node_name="checkpoint_cleanup",
                            event_type="stale_checkpoint_cleared",
                            status="info",
                            message=f"清理过期检查点: {stale_reason}",
                        )
                except Exception:
                    pass  # Non-critical: logging is best-effort

        delete_checkpoint_thread(repo.db_path, project_id, chapter_number)
    except Exception:
        logger.warning(
            "Failed to clear stale checkpoint for %s/%s",
            project_id,
            chapter_number,
            exc_info=True,
        )


def _check_deadloop_for_run(
    repo: Repository,
    project_id: str,
    chapter_number: int,
    current_status: str,
) -> dict[str, Any] | None:
    """Stop repeated automatic runs when a chapter is already in a dead loop."""
    deadloop = DeadloopDetector.check_deadloop(repo, project_id, chapter_number)
    if not deadloop.get("triggered"):
        return None
    reason = deadloop.get("reason") or "章节生产疑似进入返修死循环"
    action = deadloop.get("action") or "请人工检查并考虑恢复最佳历史版本"
    return {
        "run_id": "",
        "chapter_status": current_status,
        "steps": [],
        "error": f"章节生产熔断：{reason}。{action}",
        "requires_human": True,
        "deadloop_detected": True,
        "details": deadloop,
        "actions": [
            {
                "key": "restore_best_version",
                "label": "恢复历史最佳版本",
                "description": "从已有版本中选择满足字数和评分较好的正文，恢复后再进入审核/润色路径。",
                "action_url": f"/api/projects/{project_id}/chapters/{chapter_number}/restore-best-version",
                "method": "POST",
                "requires_confirmation": True,
                "target_chapter": chapter_number,
            },
            {
                "key": "reset_chapter",
                "label": "人工确认重置后重跑",
                "description": "保留现有正文和历史版本，只清理阻塞状态与本轮失败窗口。",
                "action_url": f"/api/projects/{project_id}/chapters/{chapter_number}/reset",
                "method": "POST",
                "requires_confirmation": True,
                "target_chapter": chapter_number,
            },
        ],
    }


def _build_llm_router(settings: Settings, llm_mode: str = "stub"):
    """Build LLMRouter from settings and llm_mode.

    Extracts the logic from cli_app/common.py _build_dispatcher.

    Args:
        settings: Application settings with LLM configuration.
        llm_mode: "stub" or "real".

    Returns:
        LLMRouter instance (always returns a router in stub mode).
    """
    from ..llm.profiles import LLMProfilesConfig, LLMProfile
    from ..llm.router import LLMRouter

    if llm_mode == "stub":
        from ..llm.stub_provider import StubLLM
        stub = StubLLM()
        if settings.llm_profiles and len(settings.llm_profiles) > 0:
            config = LLMProfilesConfig(
                default_llm=settings.default_llm,
                llm_profiles=settings.llm_profiles,
                agent_llm=settings.agent_llm,
                agent_llm_fallback=settings.agent_llm_fallback,
            )
            return LLMRouter(config, stub_provider=stub, llm_mode="stub")

        # No profiles in stub mode: build a stub router with default profile
        config = LLMProfilesConfig(
            default_llm="default",
            llm_profiles={
                "default": LLMProfile(
                    provider=settings.llm.provider if settings.llm else "openai",
                    model=settings.llm.model if settings.llm else "gpt-4",
                    api_key_env="OPENAI_API_KEY",
                    base_url=settings.llm.base_url if settings.llm else None,
                )
            },
            agent_llm={},
        )
        return LLMRouter(config, stub_provider=stub, llm_mode="stub")

    # Real mode
    from ..config.env_loader import load_dotenv, create_env_getter
    dotenv_vars = load_dotenv()
    env_getter = create_env_getter(dotenv_vars)

    if settings.llm_profiles and len(settings.llm_profiles) > 0:
        config = LLMProfilesConfig(
            default_llm=settings.default_llm,
            llm_profiles=settings.llm_profiles,
            agent_llm=settings.agent_llm,
            agent_llm_fallback=settings.agent_llm_fallback,
        )
        return LLMRouter(config, llm_mode=llm_mode, env_getter=env_getter)

    # Legacy: no profiles, build single-profile router from settings.llm
    config = LLMProfilesConfig(
        default_llm="default",
        llm_profiles={
            "default": LLMProfile(
                provider=settings.llm.provider,
                model=settings.llm.model,
                api_key_env="OPENAI_API_KEY",
                base_url=settings.llm.base_url,
            )
        },
        agent_llm={},
    )
    return LLMRouter(config, llm_mode=llm_mode, env_getter=env_getter)


def _validate_llm_config(settings: Settings, llm_mode: str) -> None:
    """Validate LLM configuration before starting the workflow.

    Raises:
        ValueError: If LLM configuration is invalid for real mode.
    """
    if llm_mode == "stub":
        return  # Stub mode doesn't need API keys

    # Real mode: check if API key is available
    from ..config.env_loader import load_dotenv, create_env_getter
    dotenv_vars = load_dotenv()
    env_getter = create_env_getter(dotenv_vars)

    # Check if llm_profiles is configured
    if settings.llm_profiles and len(settings.llm_profiles) > 0:
        # Profile mode: validate each profile by attempting to create provider
        from ..llm.profiles import LLMProfilesConfig
        from ..llm.router import LLMRouter
        config = LLMProfilesConfig(
            default_llm=settings.default_llm,
            llm_profiles=settings.llm_profiles,
            agent_llm=settings.agent_llm,
            agent_llm_fallback=settings.agent_llm_fallback,
        )
        router = LLMRouter(config, llm_mode=llm_mode, env_getter=env_getter)
        # Validate by attempting to get provider for default profile
        # This will raise ValueError if API key/base_url is missing
        try:
            default_profile = config.default_llm
            if default_profile:
                router.for_agent(default_profile)
        except ValueError:
            raise
    else:
        # Legacy single-LLM mode: check OPENAI_API_KEY
        api_key_available = bool(env_getter("OPENAI_API_KEY"))
        if not api_key_available and not settings.llm.api_key:
            raise ValueError(
                "API key not configured for real mode. "
                "Set OPENAI_API_KEY environment variable or configure in .env file."
            )


def _check_context_readiness_for_run(
    repo: Repository,
    project_id: str,
    chapter_number: int,
    chapter_status: str,
) -> dict[str, Any] | None:
    """Return a context-readiness error payload, or None if generation can run."""
    from ..validators.context_readiness import check_context_readiness, format_readiness_error

    project = repo.get_project(project_id)
    if not project:
        return {
            "run_id": "",
            "chapter_status": chapter_status,
            "steps": [],
            "error": "Project not found",
            "requires_human": True,
        }

    readiness = check_context_readiness(
        project=project,
        world_settings=repo.get_world_settings(project_id),
        characters=repo.get_characters(project_id),
        outlines=repo.list_outlines(project_id),
        instruction=repo.get_instruction(project_id, chapter_number),
        chapter_number=chapter_number,
        chapter_status=chapter_status,
    )

    if readiness.ready:
        return None

    error_info = format_readiness_error(readiness)
    return {
        "run_id": "",
        "chapter_status": chapter_status,
        "steps": [],
        "error": error_info["message"],
        "requires_human": True,
        "context_incomplete": True,
        "missing": readiness.missing,
        "actions": readiness.actions,
        "details": readiness.details,
    }


def _runtime_budget_state(settings: Settings, repo: Repository, project_id: str) -> dict[str, int]:
    """Build runtime budget fields injected into FactoryState."""
    budget = getattr(settings, "runtime_budget", None)
    return {
        "chapter_token_limit": getattr(budget, "chapter_token_limit", 0) if budget else 0,
        "project_token_limit": getattr(budget, "project_token_limit", 0) if budget else 0,
        "project_tokens_before_run": repo.get_project_workflow_token_total(project_id),
    }


def _get_budget_sentinel(settings: Settings) -> BudgetSentinel:
    """Build BudgetSentinel for cost tracking (v6.10.13).

    limit_usd=0 means no hard limit; sentinel still tracks and fires events.
    """
    budget_cfg = getattr(settings, "runtime_budget", None)
    limit_usd = 0.0
    if budget_cfg and hasattr(budget_cfg, "limit_usd"):
        limit_usd = float(getattr(budget_cfg, "limit_usd", 0.0))
    return BudgetSentinel(limit_usd=limit_usd)


def run_with_graph(
    project_id: str,
    chapter_number: int,
    settings: Settings,
    repo: Repository,
    llm_mode: str = "stub",
    max_steps: int = 100,
    workflow_run_id: str | None = None,
) -> dict[str, Any]:
    """Run chapter production via LangGraph.

    This function provides a Dispatcher.run_chapter() compatible interface
    for the LangGraph-based workflow execution.

    Args:
        project_id: Project identifier.
        chapter_number: Chapter number to produce.
        settings: Application settings.
        repo: Repository instance for database access.
        llm_mode: "stub" for demo mode, "real" for actual LLM calls.
        max_steps: Maximum graph recursion limit (steps). Defaults to 100.

    Returns:
        Dict with the same shape as Dispatcher.run_chapter():
        - run_id: Workflow run identifier.
        - chapter_status: Final chapter status.
        - steps: List of step records.
        - error: Error message if any.
        - requires_human: True if human intervention needed.
        - context_incomplete: (v5.3.0) True if context readiness gate failed.
        - missing: (v5.3.0) List of missing context items.
        - actions: (v5.3.0) List of suggested actions.
    """
    # Validate LLM configuration early (v5.2 Phase D)
    _validate_llm_config(settings, llm_mode)

    # Verify chapter exists
    chapter = repo.get_chapter(project_id, chapter_number)
    if not chapter:
        return {
            "run_id": "",
            "chapter_status": None,
            "steps": [],
            "error": "Chapter not found in DB",
            "requires_human": True,
        }

    # Normalize legacy 'pending' status
    current_status = chapter.get("status", "")
    if current_status == "pending":
        repo.update_chapter_status(project_id, chapter_number, "planned")
        current_status = "planned"

    # Short-circuit: chapters already in a terminal status
    # (reviewed / awaiting_publish / published) should not be re-processed.
    # In real mode, 'reviewed' semantically means "awaiting human publish".
    _terminal_statuses = {"reviewed", "awaiting_publish", "published"}
    if current_status in _terminal_statuses:
        _is_awaiting = current_status == "awaiting_publish" or (
            current_status == "reviewed" and llm_mode == "real"
        )
        return {
            "run_id": "",
            "chapter_status": current_status,
            "steps": [],
            "error": None,
            "requires_human": _is_awaiting,
            "awaiting_publish": _is_awaiting,
        }

    deadloop_error = _check_deadloop_for_run(repo, project_id, chapter_number, current_status)
    if deadloop_error:
        if workflow_run_id:
            repo.update_workflow_run(
                workflow_run_id,
                status="blocked",
                current_node="deadloop_guard",
                error_message=deadloop_error.get("error"),
            )
            deadloop_error["run_id"] = workflow_run_id
        return deadloop_error

    if workflow_run_id:
        delete_checkpoint_thread(repo.db_path, project_id, chapter_number)
    else:
        _clear_stale_checkpoint_for_new_run(repo, project_id, chapter_number)

    # v6.7.1: Extend arc planning before the readiness gate when generation
    # reaches a chapter outside the genesis-seeded outline range.
    ensure_continuation_plan_for_chapter(repo, project_id, chapter_number)

    # v5.3.0: Context Readiness Gate
    readiness_error = _check_context_readiness_for_run(
        repo, project_id, chapter_number, current_status
    )
    if readiness_error:
        if workflow_run_id:
            repo.update_workflow_run(
                workflow_run_id,
                status="blocked",
                current_node="context_readiness",
                error_message=readiness_error.get("error"),
            )
            readiness_error["run_id"] = workflow_run_id
        return readiness_error

    # Build initial state
    state: FactoryState = {
        "project_id": project_id,
        "chapter_number": chapter_number,
        "chapter_status": current_status,
        "retry_count": repo.get_chapter_retry_count(project_id, chapter_number),
        "max_retries": settings.quality_gate.max_retries,
        "requires_human": False,
        "error": None,
        "steps": [],
        "llm_mode": llm_mode,  # v5.3.0: Pass llm_mode for publish routing
        **_runtime_budget_state(settings, repo, project_id),
    }

    # v6.10.13: Inject checkpoint_dir for step-level recovery (inactive if not configured)
    state["checkpoint_dir"] = getattr(settings, "checkpoint_dir", None)

    # v6.10.13: Budget sentinel for cost tracking (inactive if limit_usd=0)
    budget_sentinel = _get_budget_sentinel(settings)

    # v6.10.13: Budget check before starting expensive graph execution
    can_start, start_reason = budget_sentinel.can_start()
    if not can_start:
        logger.warning("Budget sentinel blocked run start: %s", start_reason)
        if workflow_run_id:
            _mark_run_failed(repo, workflow_run_id, f"Budget blocked: {start_reason}")
        return {
            "run_id": workflow_run_id or "",
            "chapter_status": current_status,
            "steps": [],
            "error": f"Budget blocked: {start_reason}",
            "requires_human": True,
            "budget_exceeded": True,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "duration_ms": 0,
        }

    # v6.1.1+: Recover revision_target/review metadata from the latest review
    # for fresh revision runs. Keep this shared with streaming execution.
    state = hydrate_revision_state(state, repo)

    # Build LLMRouter
    llm_router = _build_llm_router(settings, llm_mode)

    # Get checkpoint config for this chapter
    config = get_checkpoint_config(project_id, chapter_number, recursion_limit=max_steps)

    # Build initial state with workflow_run_id placeholder
    # (will be populated by health_check_node)
    state["workflow_run_id"] = workflow_run_id or ""

    # v6.10.0: Create event queue for real-time SSE streaming
    from .event_queue import get_event_queue_manager
    event_queue = None
    if workflow_run_id:
        event_queue = get_event_queue_manager().get_or_create(workflow_run_id)

    # Derive checkpoint DB path from the main repository DB so checkpoints
    # always follow the data they belong to — never in the repo root.
    checkpoint_db_path = derive_checkpoint_db_path(repo.db_path)

    try:
        # Use SqliteSaver for persistent checkpointing (v5.2 Phase D)
        with get_sqlite_checkpointer(db_path=checkpoint_db_path) as checkpointer:
            # Compile graph with persistent checkpointer
            graph = compile_graph(
                settings=settings,
                repo=repo,
                llm_router=llm_router,
                checkpointer=checkpointer,
            )
            result_state = graph.invoke(state, config=config)
    except Exception as e:
        logger.exception("LangGraph execution failed for project=%s chapter=%s", project_id, chapter_number)
        safe_error = redact_sensitive_text(str(e))
        _mark_run_failed(repo, state.get("workflow_run_id"), safe_error)
        # v6.10.0: Mark event queue as done
        if event_queue:
            event_queue.mark_done("failed")
        return {
            "run_id": state.get("workflow_run_id", ""),
            "chapter_status": current_status,
            "steps": state.get("steps", []),
            "error": safe_error,
            "requires_human": True,
            "prompt_tokens": state.get("prompt_tokens", 0),
            "completion_tokens": state.get("completion_tokens", 0),
            "total_tokens": state.get("total_tokens", 0),
            "duration_ms": state.get("duration_ms", 0),
        }

    if not _graph_exit_is_success(result_state):
        interrupted_error = result_state.get("error") or _block_incomplete_graph_exit(
            repo,
            result_state,
            result_state.get("current_node"),
        )
        # v6.10.0: Mark event queue as done
        if event_queue:
            event_queue.mark_done("failed")
        return {
            "run_id": result_state.get("workflow_run_id", ""),
            "chapter_status": result_state.get("chapter_status"),
            "steps": result_state.get("steps", []),
            "error": interrupted_error,
            "requires_human": True,
            "workflow_interrupted": True,
            "awaiting_publish": False,
            "prompt_tokens": result_state.get("prompt_tokens", 0),
            "completion_tokens": result_state.get("completion_tokens", 0),
            "total_tokens": result_state.get("total_tokens", 0),
            "duration_ms": result_state.get("duration_ms", 0),
        }

    # v6.10.13: Budget check after run — return warning if budget exceeded
    if budget_sentinel.should_stop():
        logger.warning("Budget sentinel triggered stop after run")
        return {
            "run_id": result_state.get("workflow_run_id", ""),
            "chapter_status": result_state.get("chapter_status"),
            "steps": result_state.get("steps", []),
            "error": "Budget exhausted after chapter run",
            "requires_human": True,
            "budget_exceeded": True,
            "prompt_tokens": result_state.get("prompt_tokens", 0),
            "completion_tokens": result_state.get("completion_tokens", 0),
            "total_tokens": result_state.get("total_tokens", 0),
            "duration_ms": result_state.get("duration_ms", 0),
        }

    # Map to Dispatcher return shape
    return {
        "run_id": result_state.get("workflow_run_id", ""),
        "chapter_status": result_state.get("chapter_status"),
        "steps": result_state.get("steps", []),
        "error": result_state.get("error"),
        "requires_human": result_state.get("requires_human", False),
        "awaiting_publish": result_state.get("awaiting_publish", False),
        "prompt_tokens": result_state.get("prompt_tokens", 0),
        "completion_tokens": result_state.get("completion_tokens", 0),
        "total_tokens": result_state.get("total_tokens", 0),
        "duration_ms": result_state.get("duration_ms", 0),
    }


def run_with_graph_stream(
    project_id: str,
    chapter_number: int,
    settings: Settings,
    repo: Repository,
    llm_mode: str = "stub",
    max_steps: int = 100,
) -> Generator[dict[str, Any], None, None]:
    """Run chapter production with streaming events (v5.2 Phase C).

    Yields SSE-compatible events for real-time progress updates.

    Args:
        project_id: Project identifier.
        chapter_number: Chapter number to produce.
        settings: Application settings.
        repo: Repository instance for database access.
        llm_mode: "stub" for demo mode, "real" for actual LLM calls.
        max_steps: Maximum graph recursion limit (steps). Defaults to 100.

    Yields:
        Event dicts with format:
        - {"type": "step_start", "agent": str, "timestamp": str}
        - {"type": "step_complete", "agent": str, "duration_ms": int, ...}
        - {"type": "run_complete", "chapter_status": str, "run_id": str}
        - {"type": "run_error", "error": str, "chapter_status": str}
    """
    # Validate LLM configuration early (v5.2 Phase D). Because this function is
    # a generator, convert setup failures into SSE error events instead of
    # letting the stream disconnect without a structured payload.
    try:
        _validate_llm_config(settings, llm_mode)
    except Exception as e:
        safe_error = redact_sensitive_text(str(e))
        logger.warning("LLM config validation failed: %s", safe_error)
        yield {
            "type": "run_error",
            "error": safe_error,
            "chapter_status": None,
        }
        return

    # Verify chapter exists
    chapter = repo.get_chapter(project_id, chapter_number)
    if not chapter:
        yield {
            "type": "run_error",
            "error": "Chapter not found in DB",
            "chapter_status": None,
        }
        return

    # Normalize legacy 'pending' status
    current_status = chapter.get("status", "")
    if current_status == "pending":
        repo.update_chapter_status(project_id, chapter_number, "planned")
        current_status = "planned"

    # Short-circuit: chapters already in a terminal status
    # (reviewed / awaiting_publish / published) should not be re-processed.
    # In real mode, 'reviewed' semantically means "awaiting human publish".
    _terminal_statuses = {"reviewed", "awaiting_publish", "published"}
    if current_status in _terminal_statuses:
        _is_awaiting = current_status == "awaiting_publish" or (
            current_status == "reviewed" and llm_mode == "real"
        )
        yield {
            "type": "run_complete",
            "chapter_status": current_status,
            "run_id": "",
            "awaiting_publish": _is_awaiting,
            "requires_human": _is_awaiting,
        }
        return

    deadloop_error = _check_deadloop_for_run(repo, project_id, chapter_number, current_status)
    if deadloop_error:
        yield {
            "type": "run_error",
            "error": deadloop_error.get("error"),
            "chapter_status": current_status,
            "deadloop_detected": True,
            "details": deadloop_error.get("details", {}),
            "actions": deadloop_error.get("actions", []),
        }
        return

    _clear_stale_checkpoint_for_new_run(repo, project_id, chapter_number)

    # v6.7.1: Keep streaming and non-streaming run entrypoints aligned.
    ensure_continuation_plan_for_chapter(repo, project_id, chapter_number)

    # v5.3.0: Context Readiness Gate must match non-streaming execution.
    readiness_error = _check_context_readiness_for_run(
        repo, project_id, chapter_number, current_status
    )
    if readiness_error:
        yield {
            "type": "run_error",
            "error": readiness_error.get("error"),
            "chapter_status": readiness_error.get("chapter_status"),
            "context_incomplete": readiness_error.get("context_incomplete", False),
            "missing": readiness_error.get("missing", []),
            "actions": readiness_error.get("actions", []),
            "details": readiness_error.get("details", {}),
        }
        return

    # Build initial state
    state: FactoryState = {
        "project_id": project_id,
        "chapter_number": chapter_number,
        "chapter_status": current_status,
        "retry_count": repo.get_chapter_retry_count(project_id, chapter_number),
        "max_retries": settings.quality_gate.max_retries,
        "requires_human": False,
        "error": None,
        "steps": [],
        "workflow_run_id": "",
        "llm_mode": llm_mode,
        **_runtime_budget_state(settings, repo, project_id),
    }

    # v6.10.13: Inject checkpoint_dir for step-level recovery (inactive if not configured)
    state["checkpoint_dir"] = getattr(settings, "checkpoint_dir", None)

    # v6.10.13: Inject budget sentinel for cost tracking (inactive if limit_usd=0)
    budget_sentinel = _get_budget_sentinel(settings)

    # v6.10.13: Budget check before starting expensive graph execution
    can_start, start_reason = budget_sentinel.can_start()
    if not can_start:
        logger.warning("Budget sentinel blocked stream start: %s", start_reason)
        yield {
            "type": "run_error",
            "error": f"Budget blocked: {start_reason}",
            "chapter_status": current_status,
            "budget_exceeded": True,
        }
        return

    # v6.1.1+: Recover revision_target/review metadata from the latest review
    # for fresh revision runs. Keep this shared with non-streaming execution.
    state = hydrate_revision_state(state, repo)

    # Build LLMRouter
    try:
        llm_router = _build_llm_router(settings, llm_mode)
    except Exception as e:
        safe_error = redact_sensitive_text(str(e))
        logger.warning("Failed to build LLM router: %s", safe_error)
        yield {
            "type": "run_error",
            "error": safe_error,
            "chapter_status": current_status,
        }
        return

    # Get checkpoint config for this chapter
    config = get_checkpoint_config(project_id, chapter_number, recursion_limit=max_steps)

    # Track timing per agent
    agent_start_times: dict[str, float] = {}
    current_agent: str | None = None
    event_queue = None  # v6.10.0: Lazy-initialized event queue

    # Derive checkpoint DB path from the main repository DB so checkpoints
    # always follow the data they belong to — never in the repo root.
    checkpoint_db_path = derive_checkpoint_db_path(repo.db_path)

    try:
        # Use SqliteSaver for persistent checkpointing (v5.2 Phase D)
        with get_sqlite_checkpointer(db_path=checkpoint_db_path) as checkpointer:
            # Compile graph with persistent checkpointer
            graph = compile_graph(
                settings=settings,
                repo=repo,
                llm_router=llm_router,
                checkpointer=checkpointer,
            )

            # Use graph.stream() for streaming execution
            for event in graph.stream(state, config=config):
                # Parse LangGraph stream event
                # Event format: {node_name: {output_state}}
                for node_name, node_output in event.items():
                    # Always merge state updates so workflow_run_id and tokens
                    # set by health_check/internal nodes are preserved.
                    if isinstance(node_output, dict):
                        state.update(node_output)

                    # v6.10.0: Create event queue when run_id becomes available
                    run_id_val = state.get("workflow_run_id", "")
                    if run_id_val and event_queue is None:
                        from .event_queue import get_event_queue_manager
                        event_queue = get_event_queue_manager().get_or_create(run_id_val)

                    # Skip internal nodes for SSE events
                    if node_name in ("health_check", "task_discovery", "revision_router", "archive"):
                        continue

                    # Detect agent transitions
                    if node_name != current_agent:
                        # Emit step_complete for previous agent
                        if current_agent and current_agent in agent_start_times:
                            duration_ms = int((time.time() - agent_start_times[current_agent]) * 1000)
                            yield {
                                "type": "step_complete",
                                "agent": current_agent,
                                "duration_ms": duration_ms,
                            }

                        # Emit step_start for new agent
                        if node_name in STREAM_VISIBLE_NODES:
                            current_agent = node_name
                            agent_start_times[node_name] = time.time()
                            yield {
                                "type": "step_start",
                                "agent": node_name,
                                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            }

                    # Update state from output
                    if isinstance(node_output, dict):
                        state.update(node_output)

        # Emit final step_complete if needed
        if current_agent and current_agent in agent_start_times:
            duration_ms = int((time.time() - agent_start_times[current_agent]) * 1000)
            yield {
                "type": "step_complete",
                "agent": current_agent,
                "duration_ms": duration_ms,
            }

        if not _graph_exit_is_success(state):
            interrupted_error = state.get("error") or _block_incomplete_graph_exit(
                repo,
                state,
                current_agent,
            )
            # v6.10.0: Mark event queue as done
            if event_queue:
                event_queue.mark_done("failed")
            yield {
                "type": "run_error",
                "run_id": state.get("workflow_run_id", ""),
                "error": interrupted_error,
                "chapter_status": state.get("chapter_status"),
                "requires_human": True,
                "workflow_interrupted": True,
                "prompt_tokens": state.get("prompt_tokens", 0),
                "completion_tokens": state.get("completion_tokens", 0),
                "total_tokens": state.get("total_tokens", 0),
                "duration_ms": state.get("duration_ms", 0),
            }
            return

        # v6.10.0: Mark event queue as done
        if event_queue:
            event_queue.mark_done("completed")

        # v6.10.13: Budget check after run — yield warning if budget exceeded
        if budget_sentinel.should_stop():
            logger.warning("Budget sentinel triggered stop after stream run")
            yield {
                "type": "run_error",
                "run_id": state.get("workflow_run_id", ""),
                "error": "Budget exhausted after chapter run",
                "chapter_status": state.get("chapter_status"),
                "requires_human": True,
                "budget_exceeded": True,
                "prompt_tokens": state.get("prompt_tokens", 0),
                "completion_tokens": state.get("completion_tokens", 0),
                "total_tokens": state.get("total_tokens", 0),
                "duration_ms": state.get("duration_ms", 0),
            }
            return

        # Emit run_complete only after a coherent terminal graph outcome.
        yield {
            "type": "run_complete",
            "chapter_status": state.get("chapter_status"),
            "run_id": state.get("workflow_run_id", ""),
            "awaiting_publish": state.get("awaiting_publish", False),
            "prompt_tokens": state.get("prompt_tokens", 0),
            "completion_tokens": state.get("completion_tokens", 0),
            "total_tokens": state.get("total_tokens", 0),
            "duration_ms": state.get("duration_ms", 0),
        }

    except Exception as e:
        logger.exception("LangGraph streaming failed for project=%s chapter=%s", project_id, chapter_number)
        safe_error = redact_sensitive_text(str(e))
        _mark_run_failed(repo, state.get("workflow_run_id"), safe_error)
        # v6.10.0: Mark event queue as done
        if event_queue:
            event_queue.mark_done("failed")
        yield {
            "type": "run_error",
            "run_id": state.get("workflow_run_id", ""),
            "error": safe_error,
            "chapter_status": state.get("chapter_status", current_status),
            "prompt_tokens": state.get("prompt_tokens", 0),
            "completion_tokens": state.get("completion_tokens", 0),
            "total_tokens": state.get("total_tokens", 0),
            "duration_ms": state.get("duration_ms", 0),
        }
