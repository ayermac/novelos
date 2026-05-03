"""Checkpoint management for LangGraph workflow persistence.

v5.2 Phase D: Provides SqliteSaver-based checkpoint management for
cross-process recovery of incomplete chapter generation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def derive_checkpoint_db_path(repo_db_path: str | Path | None) -> Path | None:
    """Derive checkpoint DB path from the main repository DB path.

    Places ``<stem>.checkpoints.db`` alongside the main database so that
    checkpoints always follow the data they belong to — never in the repo root.

    Args:
        repo_db_path: Path to the main application database.

    Returns:
        Path to the checkpoint database, or None if repo_db_path is None
        (caller should fall back to in-memory checkpointing).
    """
    if repo_db_path is None or str(repo_db_path) == ":memory:":
        return None
    main = Path(repo_db_path)
    return main.parent / f"{main.stem}.checkpoints.db"


def get_sqlite_checkpointer(db_path: str | Path | None = None) -> Any:
    """Get a SqliteSaver checkpointer instance.

    Args:
        db_path: Path to the checkpoint database. If None, uses an in-memory
                 SQLite database (safe for tests / ephemeral runs; *never*
                 writes to the repo root).

    Returns:
        SqliteSaver instance (context manager).

    Usage:
        with get_sqlite_checkpointer(db_path=derive_checkpoint_db_path(repo.db_path)) as cp:
            graph = compile_graph(settings, repo, checkpointer=cp)
            result = graph.invoke(state, config={"configurable": {"thread_id": "..."}})
    """
    from langgraph.checkpoint.sqlite import SqliteSaver

    if db_path is None:
        # In-memory checkpointing — safe default, no files written
        return SqliteSaver.from_conn_string(":memory:")

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
        "recursion_limit": 50,
        "configurable": {
            "thread_id": get_checkpoint_thread_id(project_id, chapter_number),
        }
    }


def delete_checkpoint_thread(
    repo_db_path: str | Path | None,
    project_id: str,
    chapter_number: int,
) -> bool:
    """Delete persisted LangGraph checkpoints for a chapter.

    Manual chapter reset starts a new generation attempt. Keeping the old
    checkpoint can resume mid-graph with stale state, so reset must clear the
    thread while preserving workflow_runs/task_status history in the main DB.
    """
    checkpoint_db_path = derive_checkpoint_db_path(repo_db_path)
    if checkpoint_db_path is None or not checkpoint_db_path.exists():
        return False

    thread_id = get_checkpoint_thread_id(project_id, chapter_number)
    try:
        with get_sqlite_checkpointer(db_path=checkpoint_db_path) as checkpointer:
            checkpointer.delete_thread(thread_id)
        return True
    except Exception as e:
        logger.warning(
            "Failed to delete checkpoint thread %s from %s: %s",
            thread_id,
            checkpoint_db_path,
            e,
        )
        return False


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
