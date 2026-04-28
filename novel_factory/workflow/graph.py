"""LangGraph workflow graph for chapter production.

Builds and compiles the StateGraph that orchestrates all five agents.
v1.1: Supports custom checkpointer injection for checkpoint recovery.
v5.1.6: Supports LLMRouter-based agent routing via create_node_runners.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from ..config.settings import Settings, load_settings
from ..db.repository import Repository
from ..llm.openai_compatible import OpenAICompatibleProvider
from ..llm.provider import LLMProvider
from ..models.state import FactoryState
from .conditions import (
    route_after_agent,
    route_by_chapter_status,
    route_by_revision_type,
    route_by_review_result,
)
from . import nodes

logger = logging.getLogger(__name__)


def build_graph(
    settings: Settings | None = None,
    repo: Repository | None = None,
    llm: LLMProvider | None = None,
    llm_router: Any | None = None,
    skill_registry: Any | None = None,
) -> StateGraph:
    """Build the chapter production workflow graph.

    Args:
        settings: Application settings. Loaded from default if not provided.
        repo: Repository instance. Created from settings if not provided.
        llm: LLM provider. Created from settings if not provided.
               Used only if llm_router is None (legacy mode).
        llm_router: LLMRouter instance for agent-level routing (v5.1.6).
                    If provided, takes precedence over llm parameter.
        skill_registry: Optional SkillRegistry for polisher/editor (v5.1.6).

    Returns:
        Compiled LangGraph StateGraph ready for execution.
    """
    settings = settings or load_settings()
    repo = repo or Repository(settings.db_path)

    # v5.1.6: If llm_router provided, use create_node_runners
    use_router_mode = llm_router is not None

    if not use_router_mode:
        # Legacy mode: use single llm provider
        llm = llm or OpenAICompatibleProvider(settings.llm)

    # ── Create graph ──────────────────────────────────────────
    graph = StateGraph(FactoryState)

    # ── Add nodes ─────────────────────────────────────────────
    if use_router_mode:
        # v5.1.6: Use create_node_runners for LLMRouter-based routing
        from .nodes import create_node_runners
        runners = create_node_runners(settings, repo, llm_router, skill_registry)

        graph.add_node("health_check", lambda s: nodes.health_check_node(s, repo))
        graph.add_node("task_discovery", lambda s: nodes.task_discovery_node(s, repo))
        graph.add_node("planner", runners["planner"])
        graph.add_node("screenwriter", runners["screenwriter"])
        graph.add_node("author", runners["author"])
        graph.add_node("polisher", runners["polisher"])
        graph.add_node("editor", runners["editor"])
        graph.add_node("publisher", lambda s: nodes.publisher_node(s, repo))
        graph.add_node("awaiting_publish", lambda s: nodes.awaiting_publish_node(s, repo))  # v5.3.0
        graph.add_node("revision_router", lambda s: nodes.revision_router_node(s))
        graph.add_node("human_review", lambda s: nodes.human_review_node(s, repo))
        graph.add_node("archive", lambda s: nodes.archive_node(s, repo))
    else:
        # Legacy mode: use existing node functions with single llm
        graph.add_node(
            "health_check",
            lambda s: nodes.health_check_node(s, repo),
        )
        graph.add_node(
            "task_discovery",
            lambda s: nodes.task_discovery_node(s, repo),
        )
        graph.add_node(
            "planner",
            lambda s: nodes.planner_node(s, repo, llm),
        )
        graph.add_node(
            "screenwriter",
            lambda s: nodes.screenwriter_node(s, repo, llm),
        )
        graph.add_node(
            "author",
            lambda s: nodes.author_node(s, repo, llm),
        )
        graph.add_node(
            "polisher",
            lambda s: nodes.polisher_node(s, repo, llm),
        )
        graph.add_node(
            "editor",
            lambda s: nodes.editor_node(s, repo, llm),
        )
        graph.add_node(
            "publisher",
            lambda s: nodes.publisher_node(s, repo),
        )
        graph.add_node(
            "awaiting_publish",
            lambda s: nodes.awaiting_publish_node(s, repo),
        )  # v5.3.0
        graph.add_node("revision_router", lambda s: nodes.revision_router_node(s))
        graph.add_node(
            "human_review",
            lambda s: nodes.human_review_node(s, repo),
        )
        graph.add_node(
            "archive",
            lambda s: nodes.archive_node(s, repo),
        )

    # ── Set entry point ───────────────────────────────────────
    graph.set_entry_point("health_check")

    # ── Add edges ─────────────────────────────────────────────
    graph.add_edge("health_check", "task_discovery")

    graph.add_conditional_edges(
        "task_discovery",
        route_by_chapter_status,
        {
            "planner": "planner",
            "screenwriter": "screenwriter",
            "author": "author",
            "polisher": "polisher",
            "editor": "editor",
            "publisher": "publisher",
            "archive": "archive",          # Terminal: already published
            "human_review": "human_review",
            "revision_router": "revision_router",
        },
    )

    # Linear happy path, with a safety stop after each agent. Agent nodes set
    # requires_human on errors, so never flow into the next precondition blindly.
    graph.add_conditional_edges(
        "planner",
        route_after_agent,
        {"next": "screenwriter", "human_review": "human_review"},
    )
    graph.add_conditional_edges(
        "screenwriter",
        route_after_agent,
        {"next": "author", "human_review": "human_review"},
    )
    graph.add_conditional_edges(
        "author",
        route_after_agent,
        {"next": "polisher", "human_review": "human_review"},
    )
    graph.add_conditional_edges(
        "polisher",
        route_after_agent,
        {"next": "editor", "human_review": "human_review"},
    )

    # After editor: pass → publisher, fail → revise or human
    # v5.3.0: Real mode → awaiting_publish (no auto-publish)
    graph.add_conditional_edges(
        "editor",
        route_by_review_result,
        {
            "publish": "publisher",
            "awaiting_publish": "awaiting_publish",  # v5.3.0: Real mode stops here
            "revise": "revision_router",
            "human_review": "human_review",
        },
    )

    # Revision routing
    graph.add_conditional_edges(
        "revision_router",
        route_by_revision_type,
        {
            "author": "author",
            "polisher": "polisher",
            "planner": "planner",
        },
    )

    # Terminal nodes
    graph.add_edge("publisher", "archive")
    graph.add_edge("archive", END)
    graph.add_edge("awaiting_publish", END)  # v5.3.0: Real mode terminal
    graph.add_edge("human_review", END)

    return graph


def compile_graph(
    settings: Settings | None = None,
    repo: Repository | None = None,
    llm: LLMProvider | None = None,
    llm_router: Any | None = None,
    skill_registry: Any | None = None,
    checkpointer: Any | None = None,
    checkpoint: bool = True,
):
    """Build and compile the graph with optional checkpointing.

    Args:
        settings: Application settings.
        repo: Repository instance.
        llm: LLM provider. Used only if llm_router is None (legacy mode).
        llm_router: LLMRouter instance for agent-level routing (v5.1.6).
        skill_registry: Optional SkillRegistry for polisher/editor (v5.1.6).
        checkpointer: Custom checkpointer instance (e.g. SqliteSaver).
                       If provided, takes precedence over the checkpoint flag.
        checkpoint: If True and no custom checkpointer is given, use MemorySaver.
                    Note: v1.1 default MemorySaver does NOT guarantee cross-process
                    recovery. For persistent checkpointing, pass a durable checkpointer.

    Returns:
        Compiled graph ready for .invoke() or .stream().
    """
    graph = build_graph(settings, repo, llm, llm_router, skill_registry)
    if checkpointer is not None:
        cp = checkpointer
    elif checkpoint:
        cp = MemorySaver()
    else:
        cp = None
    return graph.compile(checkpointer=cp)
