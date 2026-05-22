"""Checkpoint management for LangGraph workflow persistence.

v5.2 Phase D: Provides SqliteSaver-based checkpoint management for
cross-process recovery of incomplete chapter generation.
"""

from __future__ import annotations

import logging
import sqlite3
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


def _raw_checkpoint_thread_exists(checkpoint_db_path: Path, thread_id: str) -> bool:
    """Return True when checkpoint rows exist, without deserializing payloads."""
    try:
        with sqlite3.connect(checkpoint_db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM checkpoints WHERE thread_id=? LIMIT 1",
                (thread_id,),
            ).fetchone()
            if row:
                return True
            row = conn.execute(
                "SELECT 1 FROM writes WHERE thread_id=? LIMIT 1",
                (thread_id,),
            ).fetchone()
            return row is not None
    except Exception:
        return False


def get_checkpoint_config(
    project_id: str, chapter_number: int, recursion_limit: int = 100
) -> dict:
    """Get checkpoint config for a chapter.

    Args:
        project_id: Project identifier.
        chapter_number: Chapter number.
        recursion_limit: Maximum graph recursion limit (steps).

    Returns:
        Config dict for use with graph.invoke() or graph.stream().
    """
    return {
        "recursion_limit": recursion_limit,
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


def checkpoint_thread_exists(
    repo_db_path: str | Path | None,
    project_id: str,
    chapter_number: int,
) -> bool:
    """Return whether a persisted checkpoint thread currently exists."""
    checkpoint_db_path = derive_checkpoint_db_path(repo_db_path)
    if checkpoint_db_path is None or not checkpoint_db_path.exists():
        return False

    thread_id = get_checkpoint_thread_id(project_id, chapter_number)
    try:
        with get_sqlite_checkpointer(db_path=checkpoint_db_path) as checkpointer:
            state = checkpointer.get({
                "configurable": {"thread_id": thread_id, "checkpoint_ns": ""}
            })
        return state is not None
    except Exception as e:
        logger.warning(
            "Failed to inspect checkpoint thread %s from %s: %s",
            thread_id,
            checkpoint_db_path,
            e,
        )
        return False


def inspect_checkpoint_thread(
    repo_db_path: str | Path | None,
    project_id: str,
    chapter_number: int,
) -> dict[str, Any]:
    """Return a safe, UI-facing checkpoint summary for a chapter thread."""
    summary: dict[str, Any] = {
        "checkpoint_exists": False,
        "checkpoint_node": None,
        "current_node": None,
        "checkpoint_summary": None,
        "state_keys": [],
        "recovery_available": False,
    }
    checkpoint_db_path = derive_checkpoint_db_path(repo_db_path)
    if checkpoint_db_path is None or not checkpoint_db_path.exists():
        return summary

    thread_id = get_checkpoint_thread_id(project_id, chapter_number)
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    try:
        with get_sqlite_checkpointer(db_path=checkpoint_db_path) as checkpointer:
            checkpoint_tuple = None
            if hasattr(checkpointer, "get_tuple"):
                checkpoint_tuple = checkpointer.get_tuple(config)
            checkpoint = checkpoint_tuple.checkpoint if checkpoint_tuple else checkpointer.get(config)
            metadata = getattr(checkpoint_tuple, "metadata", None) if checkpoint_tuple else None
    except Exception as e:
        raw_exists = _raw_checkpoint_thread_exists(checkpoint_db_path, thread_id)
        logger.warning(
            "Failed to summarize checkpoint thread %s from %s: %s",
            thread_id,
            checkpoint_db_path,
            e,
        )
        if raw_exists:
            summary.update({
                "checkpoint_exists": True,
                "checkpoint_corrupt": True,
                "checkpoint_error": str(e),
                "checkpoint_summary": "checkpoint payload unreadable",
                "recovery_available": True,
            })
        return summary

    if not checkpoint:
        return summary

    state_values: dict[str, Any] = {}
    if not isinstance(checkpoint, dict):
        summary.update({
            "checkpoint_exists": True,
            "checkpoint_corrupt": True,
            "checkpoint_error": f"Unexpected checkpoint payload type: {type(checkpoint).__name__}",
            "checkpoint_summary": "checkpoint payload unreadable",
            "recovery_available": True,
        })
        return summary

    channel_values = checkpoint.get("channel_values")
    if isinstance(channel_values, dict):
        state_values = channel_values

    checkpoint_node = None
    if isinstance(metadata, dict):
        writes = metadata.get("writes")
        if isinstance(writes, dict) and writes:
            checkpoint_node = next(iter(writes.keys()), None)
        checkpoint_node = checkpoint_node or metadata.get("source")
    current_node = state_values.get("current_node") or checkpoint_node
    state_keys = sorted(str(key) for key in state_values.keys())[:30]
    status = state_values.get("chapter_status") or state_values.get("current_stage")
    checkpoint_summary = None
    if status or current_node:
        parts = []
        if current_node:
            parts.append(f"node={current_node}")
        if status:
            parts.append(f"status={status}")
        checkpoint_summary = ", ".join(parts)

    summary.update({
        "checkpoint_exists": True,
        "checkpoint_node": checkpoint_node,
        "current_node": current_node,
        "checkpoint_summary": checkpoint_summary,
        "state_keys": state_keys,
        "recovery_available": True,
    })
    return summary


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
