"""LangGraph node functions for the chapter production workflow.

Each node takes a FactoryState and returns a dict of updates to merge.
v1.1: Nodes now track workflow_runs lifecycle and update current_node.
"""

from __future__ import annotations

import logging
from typing import Any

from ..db.repository import Repository
from ..llm.provider import LLMProvider
from ..models.state import ChapterStatus, FactoryState
from ..agents.planner import PlannerAgent
from ..agents.screenwriter import ScreenwriterAgent
from ..agents.author import AuthorAgent
from ..agents.polisher import PolisherAgent
from ..agents.editor import EditorAgent

logger = logging.getLogger(__name__)


# ── Helper ──────────────────────────────────────────────────────


def _update_run_node(state: FactoryState, repo: Repository, node_name: str) -> None:
    """Update workflow_runs.current_node if a run_id exists in state."""
    run_id = state.get("workflow_run_id")
    if run_id:
        repo.update_workflow_run(run_id, current_node=node_name)


def _finalize_run(state: FactoryState, repo: Repository, status: str, error: str | None = None) -> None:
    """Finalize workflow run with given status."""
    run_id = state.get("workflow_run_id")
    if run_id:
        repo.update_workflow_run(run_id, status=status, error_message=error)


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

    state_status = state.get("chapter_status", "")
    if db_status != state_status:
        logger.info(
            "task_discovery: DB status '%s' overrides state status '%s'",
            db_status, state_status,
        )
        return {"chapter_status": db_status}

    return {}


def planner_node(state: FactoryState, repo: Repository, llm: LLMProvider) -> dict[str, Any]:
    """Run the Planner agent."""
    _update_run_node(state, repo, "planner")
    agent = PlannerAgent(repo, llm)
    result = agent.run(state)
    if "error" in result:
        _finalize_run(state, repo, "failed", result["error"])
    return result


def screenwriter_node(state: FactoryState, repo: Repository, llm: LLMProvider) -> dict[str, Any]:
    """Run the Screenwriter agent."""
    _update_run_node(state, repo, "screenwriter")
    agent = ScreenwriterAgent(repo, llm)
    result = agent.run(state)
    if "error" in result:
        _finalize_run(state, repo, "failed", result["error"])
    return result


def author_node(state: FactoryState, repo: Repository, llm: LLMProvider) -> dict[str, Any]:
    """Run the Author agent."""
    _update_run_node(state, repo, "author")
    agent = AuthorAgent(repo, llm)
    result = agent.run(state)
    if "error" in result:
        _finalize_run(state, repo, "failed", result["error"])
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
    result = agent.run(state)
    if "error" in result:
        _finalize_run(state, repo, "failed", result["error"])
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
    if "error" in result:
        _finalize_run(state, repo, "failed", result["error"])
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


def revision_router_node(state: FactoryState) -> dict[str, Any]:
    """Determine where to route revision based on review result."""
    # Just pass through — routing is handled by conditional edges
    return {}


def human_review_node(state: FactoryState, repo: Repository) -> dict[str, Any]:
    """Handle blocking/human intervention scenarios."""
    _update_run_node(state, repo, "human_review")
    _finalize_run(state, repo, "blocked")
    logger.warning(
        "Human intervention required: project=%s chapter=%s",
        state.get("project_id"), state.get("chapter_number"),
    )
    return {"requires_human": True, "chapter_status": "blocking"}


def archive_node(state: FactoryState, repo: Repository) -> dict[str, Any]:
    """Archive after publishing. Marks workflow run as completed."""
    _update_run_node(state, repo, "archive")
    _finalize_run(state, repo, "completed")
    logger.info(
        "Archive: project=%s chapter=%s published",
        state.get("project_id"), state.get("chapter_number"),
    )
    return {}
