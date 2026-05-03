"""LangGraph-based chapter production runner.

v5.1.6: Provides run_with_graph() that returns the same shape as Dispatcher.run_chapter().
v5.2 Phase C: Adds run_with_graph_stream() for SSE streaming support.
v5.2 Phase D: Adds SqliteSaver-based checkpoint persistence for recovery.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Generator

from ..config.settings import Settings
from ..db.repository import Repository
from ..models.state import FactoryState
from .graph import compile_graph
from .checkpoint import get_sqlite_checkpointer, get_checkpoint_config, derive_checkpoint_db_path

logger = logging.getLogger(__name__)


def _mark_run_failed(repo: Repository, run_id: str | None, error: str) -> None:
    """Best-effort workflow run failure finalization."""
    if not run_id:
        return
    try:
        repo.update_workflow_run(run_id, status="failed", error_message=error)
    except Exception:
        logger.warning("Failed to mark workflow run %s as failed", run_id, exc_info=True)


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


def run_with_graph(
    project_id: str,
    chapter_number: int,
    settings: Settings,
    repo: Repository,
    llm_mode: str = "stub",
    max_steps: int = 20,
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
        max_steps: Maximum workflow steps (not currently enforced by LangGraph).

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

    # Short-circuit: already-published chapters need no processing
    if current_status == "published":
        return {
            "run_id": "",
            "chapter_status": "published",
            "steps": [],
            "error": None,
            "requires_human": False,
        }

    # v5.3.0: Context Readiness Gate
    readiness_error = _check_context_readiness_for_run(
        repo, project_id, chapter_number, current_status
    )
    if readiness_error:
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
    }

    # Build LLMRouter
    llm_router = _build_llm_router(settings, llm_mode)

    # Get checkpoint config for this chapter
    config = get_checkpoint_config(project_id, chapter_number)

    # Build initial state with workflow_run_id placeholder
    # (will be populated by health_check_node)
    state["workflow_run_id"] = ""

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
        logger.exception("LangGraph execution failed")
        _mark_run_failed(repo, state.get("workflow_run_id"), str(e))
        return {
            "run_id": state.get("workflow_run_id", ""),
            "chapter_status": current_status,
            "steps": state.get("steps", []),
            "error": str(e),
            "requires_human": True,
        }

    # Map to Dispatcher return shape
    return {
        "run_id": result_state.get("workflow_run_id", ""),
        "chapter_status": result_state.get("chapter_status"),
        "steps": result_state.get("steps", []),
        "error": result_state.get("error"),
        "requires_human": result_state.get("requires_human", False),
        "awaiting_publish": result_state.get("awaiting_publish", False),
    }


def run_with_graph_stream(
    project_id: str,
    chapter_number: int,
    settings: Settings,
    repo: Repository,
    llm_mode: str = "stub",
    max_steps: int = 20,
) -> Generator[dict[str, Any], None, None]:
    """Run chapter production with streaming events (v5.2 Phase C).

    Yields SSE-compatible events for real-time progress updates.

    Args:
        project_id: Project identifier.
        chapter_number: Chapter number to produce.
        settings: Application settings.
        repo: Repository instance for database access.
        llm_mode: "stub" for demo mode, "real" for actual LLM calls.
        max_steps: Maximum workflow steps (not currently enforced).

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
        yield {
            "type": "run_error",
            "error": str(e),
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

    # Short-circuit: already-published chapters
    if current_status == "published":
        yield {
            "type": "run_complete",
            "chapter_status": "published",
            "run_id": "",
            "awaiting_publish": False,
        }
        return

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
    }

    # Build LLMRouter
    try:
        llm_router = _build_llm_router(settings, llm_mode)
    except Exception as e:
        yield {
            "type": "run_error",
            "error": str(e),
            "chapter_status": current_status,
        }
        return

    # Get checkpoint config for this chapter
    config = get_checkpoint_config(project_id, chapter_number)

    # Track timing per agent
    agent_start_times: dict[str, float] = {}
    current_agent: str | None = None

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
                    # Skip internal nodes
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
                        if node_name in ("planner", "screenwriter", "author", "polisher", "editor", "publisher", "human_review"):
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

        # Emit run_complete
        yield {
            "type": "run_complete",
            "chapter_status": state.get("chapter_status"),
            "run_id": state.get("workflow_run_id", ""),
            "awaiting_publish": state.get("awaiting_publish", False),
        }

    except Exception as e:
        logger.exception("LangGraph streaming failed")
        _mark_run_failed(repo, state.get("workflow_run_id"), str(e))
        yield {
            "type": "run_error",
            "run_id": state.get("workflow_run_id", ""),
            "error": str(e),
            "chapter_status": state.get("chapter_status", current_status),
        }
