"""Checkpoint management for LangGraph workflow persistence.

v5.2 Phase D: Provides SqliteSaver-based checkpoint management for
cross-process recovery of incomplete chapter generation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_sqlite_checkpointer(db_path: str | Path | None = None) -> Any:
    """Get a SqliteSaver checkpointer instance.

    Args:
        db_path: Path to the checkpoint database. If None, uses the default
                 path alongside the main application database.

    Returns:
        SqliteSaver instance (context manager).

    Usage:
        with get_sqlite_checkpointer() as checkpointer:
            graph = compile_graph(settings, repo, checkpointer=checkpointer)
            result = graph.invoke(state, config={"configurable": {"thread_id": "..."}})
    """
    from langgraph.checkpoint.sqlite import SqliteSaver

    if db_path is None:
        # Default to checkpoints.db in the same directory as the main DB
        db_path = Path(__file__).parent.parent.parent / "checkpoints.db"

    return SqliteSaver.from_conn_string(str(db_path))


def get_checkpoint_thread_id(project_id: str, chapter_number: int) -> str:
    """Generate a consistent thread_id for chapter checkpointing.

    Args:
        project_id: Project identifier.
        chapter_number: Chapter number.

    Returns:
        Thread ID string for checkpoint identification.
    """
    return f"{project_id}-chapter-{chapter_number}"


def get_checkpoint_config(project_id: str, chapter_number: int) -> dict:
    """Get checkpoint config for a chapter.

    Args:
        project_id: Project identifier.
        chapter_number: Chapter number.

    Returns:
        Config dict for use with graph.invoke() or graph.stream().
    """
    return {
        "configurable": {
            "thread_id": get_checkpoint_thread_id(project_id, chapter_number),
        }
    }


def resume_from_checkpoint(
    graph: Any,
    project_id: str,
    chapter_number: int,
) -> dict | None:
    """Check if there's an existing checkpoint to resume from.

    Args:
        graph: Compiled LangGraph with checkpointer.
        project_id: Project identifier.
        chapter_number: Chapter number.

    Returns:
        Checkpoint state if exists, None otherwise.
    """
    config = get_checkpoint_config(project_id, chapter_number)

    try:
        # Get the latest checkpoint state
        state = graph.get_state(config)
        if state and state.values:
            logger.info(
                f"Found checkpoint for {project_id}/{chapter_number}: "
                f"status={state.values.get('chapter_status', 'unknown')}"
            )
            return state.values
    except Exception as e:
        logger.debug(f"No checkpoint found or error: {e}")

    return None
