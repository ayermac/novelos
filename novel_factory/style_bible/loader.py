"""Style Bible loader for v4.0.

Loads Style Bible from database and provides convenience functions.
"""

from __future__ import annotations

from typing import Any

from ..db.repository import Repository
from ..models.style_bible import StyleBible


def load_style_bible_for_project(
    project_id: str,
    repo: Repository,
) -> StyleBible | None:
    """Load Style Bible for a project from the database.

    Args:
        project_id: Project identifier.
        repo: Repository instance.

    Returns:
        StyleBible instance, or None if not found.
    """
    record = repo.get_style_bible(project_id)
    if not record:
        return None

    bible_data = record.get("bible", {})
    if not bible_data:
        return None

    return StyleBible.from_storage_dict(bible_data)


def get_style_context_for_agent(
    project_id: str,
    agent_id: str,
    repo: Repository,
    token_budget: int = 800,
) -> str:
    """Get style context string for a specific agent.

    Returns an empty string if no Style Bible exists for the project.

    Args:
        project_id: Project identifier.
        agent_id: Agent identifier (e.g., "author", "editor").
        repo: Repository instance.
        token_budget: Maximum estimated tokens for the context.

    Returns:
        Style context string, or "" if no Style Bible.
    """
    bible = load_style_bible_for_project(project_id, repo)
    if not bible:
        return ""

    return bible.rules_for_agent(agent_id)


def get_style_bible_summary(
    project_id: str,
    repo: Repository,
    token_budget: int = 800,
) -> str:
    """Get a concise Style Bible summary for context injection.

    Returns an empty string if no Style Bible exists.

    Args:
        project_id: Project identifier.
        repo: Repository instance.
        token_budget: Maximum estimated tokens.

    Returns:
        Summary string, or "" if no Style Bible.
    """
    bible = load_style_bible_for_project(project_id, repo)
    if not bible:
        return ""

    return bible.summary_for_context(token_budget=token_budget)
