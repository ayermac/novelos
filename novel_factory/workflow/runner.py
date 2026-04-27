"""LangGraph-based chapter production runner.

v5.1.6: Provides run_with_graph() that returns the same shape as Dispatcher.run_chapter().
"""

from __future__ import annotations

import logging
from typing import Any

from ..config.settings import Settings
from ..db.repository import Repository
from ..models.state import FactoryState
from .graph import compile_graph

logger = logging.getLogger(__name__)


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
    """
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
    }

    # Build LLMRouter
    llm_router = _build_llm_router(settings, llm_mode)

    # Compile and execute graph
    graph = compile_graph(
        settings=settings,
        repo=repo,
        llm_router=llm_router,
        checkpoint=True,
    )

    # Build initial state with workflow_run_id placeholder
    # (will be populated by health_check_node)
    state["workflow_run_id"] = ""

    try:
        # LangGraph requires thread_id when using checkpointer
        config = {"configurable": {"thread_id": f"{project_id}-{chapter_number}"}}
        result_state = graph.invoke(state, config=config)
    except Exception as e:
        logger.exception("LangGraph execution failed")
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
    }
