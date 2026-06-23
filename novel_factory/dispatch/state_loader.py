"""StateLoader — load RouterState from Store for FlowRouter.

v6.10.13: Non-pure loader that reads facts from Store and constructs RouterState.
This is the only place where FlowRouter touches the database.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..db.repository import Repository
from .flow_router import RouterState

logger = logging.getLogger(__name__)


class StateLoader:
    """Load RouterState from Repository."""

    def __init__(self, repo: Repository):
        self.repo = repo

    def load(self, project_id: str) -> RouterState:
        """Load complete RouterState for routing decisions."""
        state = RouterState(phase="init", flow="writing")

        try:
            # Load project
            project = self.repo.get_project(project_id)
            if not project:
                return state

            # Phase - determine from project state
            state.phase = self._determine_phase(project_id)

            # Load chapters to determine progress
            chapters = self.repo.list_chapters(project_id)
            if chapters:
                completed = [c for c in chapters if c.get("status") == "published"]
                state.completed_chapters = [c["chapter_number"] for c in completed]
                state.total_chapters = len(chapters)

                # Find current chapter (first non-published)
                for ch in sorted(chapters, key=lambda x: x.get("chapter_number", 0)):
                    if ch.get("status") not in ("published", "archived"):
                        state.current_chapter = ch["chapter_number"]
                        state.chapter_status = ch.get("status")
                        break

            # Determine flow state from chapter statuses
            state.flow = self._determine_flow(project_id, chapters)

            # Check for pending reviews
            state.pending_reviews = self._load_pending_reviews(project_id, chapters)

            # Check for pending memory updates
            state.pending_memory_updates = self._load_pending_memory_updates(project_id)

            # Check for pending steer
            state.pending_steer = self._load_pending_steer(project_id)

            # Foundation check
            state.foundation_missing = self._load_foundation_missing(project_id)

        except Exception as e:
            logger.warning("StateLoader: failed to load state for %s: %s", project_id, e)

        return state

    def _determine_phase(self, project_id: str) -> str:
        """Determine project phase from database state."""
        try:
            characters = self.repo.get_characters(project_id)
            outlines = self.repo.list_outlines(project_id)
            chapters = self.repo.list_chapters(project_id)

            if not characters or not outlines:
                return "genesis"

            published = [c for c in (chapters or []) if c.get("status") == "published"]
            if not published:
                return "writing"

            # Check if all chapters are published
            total = len(chapters or [])
            if len(published) >= total and total > 0:
                return "complete"

            return "writing"
        except Exception:
            return "init"

    def _determine_flow(self, project_id: str, current_chapter: int) -> str:
        """Determine current flow state."""
        try:
            if current_chapter <= 0:
                return "writing"

            status = self.repo.get_chapter_status(project_id, current_chapter)
            if not status:
                return "writing"

            # Map chapter status to flow state
            status_flow_map = {
                "idea": "writing",
                "outlined": "writing",
                "planned": "writing",
                "scripted": "writing",
                "drafted": "writing",
                "polished": "reviewing",
                "review": "reviewing",
                "reviewed": "writing",
                "revision": "rewriting",
                "blocking": "steering",
            }
            return status_flow_map.get(status, "writing")
        except Exception:
            return "writing"

    def _load_pending_rewrites(self, project_id: str) -> list[int]:
        """Load chapters pending rewrite."""
        try:
            chapters = self.repo.list_chapters(project_id)
            if not chapters:
                return []

            pending = []
            for ch in chapters:
                if ch.get("status") == "revision":
                    pending.append(ch["chapter_number"])
            return sorted(pending)
        except Exception:
            return []

    def _load_pending_reviews(self, project_id: str) -> list[dict[str, Any]]:
        """Load pending review results."""
        try:
            chapters = self.repo.list_chapters(project_id)
            if not chapters:
                return []

            pending = []
            for ch in chapters:
                if ch.get("status") == "reviewed":
                    # Check if review exists
                    reviews = self.repo.get_reviews(project_id, ch["chapter_number"])
                    if reviews:
                        pending.append({
                            "chapter_number": ch["chapter_number"],
                            "review": reviews[0] if reviews else None,
                        })
            return pending
        except Exception:
            return []

    def _load_pending_memory_updates(self, project_id: str) -> list[dict[str, Any]]:
        """Load pending memory update batches."""
        try:
            batches = self.repo.list_memory_batches(project_id, status="pending")
            return batches[:5] if batches else []
        except Exception:
            return []

    def _load_pending_steer(self, project_id: str) -> Optional[str]:
        """Load pending user intervention."""
        try:
            project = self.repo.get_project(project_id)
            if project:
                return project.get("pending_steer")
        except Exception:
            pass
        return None

    def _load_foundation_missing(self, project_id: str) -> list[str]:
        """Load missing foundation items."""
        missing = []
        try:
            chars = self.repo.get_characters(project_id)
            if not chars:
                missing.append("characters")

            ws = self.repo.list_world_settings(project_id)
            if not ws:
                missing.append("world_settings")

            outlines = self.repo.list_outlines(project_id)
            if not outlines:
                missing.append("outlines")

            # Check protagonist
            protagonist = None
            for char in (chars or []):
                if char.get("role") == "protagonist":
                    protagonist = char
                    break
            if not protagonist:
                missing.append("protagonist")

        except Exception:
            pass

        return missing
