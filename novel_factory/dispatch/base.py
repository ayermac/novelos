"""Base dispatcher with shared initialization and helper methods."""

from __future__ import annotations

import json
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

# ── Routing table (v1.3 spec D3) ─────────────────────────────────

STATUS_ROUTE: dict[str, str] = {
    "planned": "screenwriter",
    "scripted": "author",
    "drafted": "polisher",
    "polished": "editor",
    "reviewed": "publisher",
    "published": "__end__",
    "blocking": "__stop__",
    # Compatibility: old Web API initial status (v5.1.1 and earlier used "pending")
    "pending": "screenwriter",
}

REVISION_ROUTE: dict[str, str] = {
    "author": "author",
    "polisher": "polisher",
    "planner": "__stop__",  # human handling required
}

# Legal target statuses for human-resume (D5)
LEGAL_RESUME_STATUSES = {"planned", "scripted", "drafted", "polished", "revision"}


class BaseDispatcher:
    """Base dispatcher with shared initialization and helper methods."""

    def __init__(
        self,
        repo: Repository,
        llm: LLMProvider | None = None,
        max_retries: int = 3,
        skill_registry: Any = None,
        create_skill_registry: bool = True,
        llm_router: Any = None,
    ) -> None:
        """Initialize Dispatcher.

        Args:
            repo: Repository instance.
            llm: LLM provider instance (for backward compatibility).
            max_retries: Maximum retry count.
            skill_registry: Optional SkillRegistry instance for v2.1 skills.
            create_skill_registry: If True and skill_registry is None, create default SkillRegistry.
            llm_router: Optional LLMRouter instance for v3.1 agent-level routing.

        Note:
            - If llm_router is provided, it takes precedence over llm.
            - If only llm is provided, all agents use the same LLM (backward compatibility).
            - If neither is provided, raises ValueError.
        """
        self.repo = repo
        self.llm = llm
        self.max_retries = max_retries
        self.skill_registry = skill_registry
        self.llm_router = llm_router

        # Validate that at least one LLM source is provided
        if llm is None and llm_router is None:
            raise ValueError("Either 'llm' or 'llm_router' must be provided")

        # Create default SkillRegistry if not provided and create_skill_registry is True
        if self.skill_registry is None and create_skill_registry:
            try:
                from ..skills.registry import SkillRegistry
                self.skill_registry = SkillRegistry()
            except Exception as e:
                logger.warning(f"Failed to create SkillRegistry: {e}")
                self.skill_registry = None

    def _llm_for_agent(self, agent_id: str) -> LLMProvider:
        """Get LLM provider for a specific agent.

        Args:
            agent_id: Agent identifier (e.g., "author", "editor").

        Returns:
            LLM provider instance for the agent.
        """
        if self.llm_router:
            return self.llm_router.for_agent(agent_id)
        if self.llm:
            return self.llm
        raise ValueError("No LLM provider available")

    def _now_iso(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    def _route(self, project_id: str, chapter_number: int, status: str) -> str:
        """Determine next agent based on status routing table.

        Safety: requires_human/error always override chapter_status.
        """
        # Check for revision status with revision_target
        if status == "revision":
            # Look up the latest review's revision_target
            chapter = self.repo.get_chapter(project_id, chapter_number)
            if chapter:
                review = self.repo.get_latest_review(project_id, chapter["id"])
                if review:
                    # First try structured revision_target field
                    revision_target = review.get("revision_target")
                    if revision_target:
                        return REVISION_ROUTE.get(revision_target, "__stop__")

                    # Fallback: parse from summary for backward compatibility
                    summary = review.get("summary") or ""
                    for part in summary.split(","):
                        if part.strip().startswith("revision_target="):
                            target = part.strip().split("=", 1)[1]
                            return REVISION_ROUTE.get(target, "__stop__")
            # Default revision route
            return "author"

        return STATUS_ROUTE.get(status, "__stop__")

    def _build_state(
        self,
        project_id: str,
        chapter_number: int,
        current_status: str,
    ) -> FactoryState:
        """Build FactoryState from DB current state."""
        retry_count = self.repo.get_chapter_retry_count(project_id, chapter_number)
        return {
            "project_id": project_id,
            "chapter_number": chapter_number,
            "chapter_status": current_status,
            "retry_count": retry_count,
            "max_retries": self.max_retries,
            "requires_human": False,
            "error": None,
        }
