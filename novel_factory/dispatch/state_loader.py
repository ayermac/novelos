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

            # Phase
            state.phase = project.get("phase", "init")

            # Load progress
            progress = self.repo.get_progress(project_id)
            if progress:
                state.flow = progress.get("flow", "writing")
                state.current_chapter = progress.get("current_chapter", 0)
                state.total_chapters = progress.get("total_chapters", 0)
                state.completed_chapters = progress.get("completed_chapters", [])
                state.pending_rewrites = progress.get("pending_rewrites", [])
                state.in_progress_chapter = progress.get("in_progress_chapter", 0)

                # Layered mode
                state.layered = progress.get("layered", False)
                state.current_volume = progress.get("current_volume", 0)
                state.current_arc = progress.get("current_arc", 0)

            # Load pending reviews
            state.pending_reviews = self._load_pending_reviews(project_id)

            # Load pending memory updates
            state.pending_memory_updates = self._load_pending_memory_updates(project_id)

            # Load pending steer
            state.pending_steer = self._load_pending_steer(project_id)

            # Load chapter status
            if state.current_chapter > 0:
                chapter = self.repo.get_chapter(project_id, state.current_chapter)
                if chapter:
                    state.chapter_status = chapter.get("status")

            # Load arc boundary info (layered mode)
            if state.layered and state.completed_chapters:
                last_ch = max(state.completed_chapters)
                self._load_arc_boundary(project_id, last_ch, state)

            # Load foundation missing
            state.foundation_missing = self._load_foundation_missing(project_id)

        except Exception as e:
            logger.warning("StateLoader: failed to load state for %s: %s", project_id, e)

        return state

    def _load_pending_reviews(self, project_id: str) -> list[dict[str, Any]]:
        """Load pending review results."""
        try:
            # Get chapters in review status
            chapters = self.repo.list_chapters(project_id)
            pending = []
            for ch in chapters:
                if ch.get("status") == "reviewed":
                    # Check if review result exists
                    review = self.repo.get_latest_review(project_id, ch["chapter_number"])
                    if review and not review.get("processed"):
                        pending.append({
                            "chapter_number": ch["chapter_number"],
                            "review": review,
                        })
            return pending
        except Exception:
            return []

    def _load_pending_memory_updates(self, project_id: str) -> list[dict[str, Any]]:
        """Load pending memory update batches."""
        try:
            batches = self.repo.list_memory_batches(project_id, status="pending")
            return batches[:5]  # Limit to 5
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

    def _load_arc_boundary(
        self, project_id: str, last_chapter: int, state: RouterState
    ) -> None:
        """Load arc boundary information for layered mode."""
        try:
            # Get outline to check arc boundaries
            outlines = self.repo.list_outlines(project_id)
            if not outlines:
                return

            # Find current arc
            for outline in outlines:
                chapters_range = outline.get("chapters_range", "")
                if not chapters_range:
                    continue

                try:
                    parts = chapters_range.split("-")
                    if len(parts) == 2:
                        start, end = int(parts[0]), int(parts[1])
                        if start <= last_chapter <= end:
                            # Check if this is the last chapter in the arc
                            if last_chapter == end:
                                state.is_arc_end = True

                                # Check if volume ends
                                # This is a simplified check; actual logic may be more complex
                                next_outline = self._find_next_outline(outlines, end)
                                if not next_outline or next_outline.get("level") == "volume":
                                    state.is_volume_end = True

                                # Check what processing has been done
                                state.has_arc_review = self._has_arc_review(
                                    project_id, state.current_volume, state.current_arc
                                )
                                state.has_arc_summary = self._has_arc_summary(
                                    project_id, state.current_volume, state.current_arc
                                )
                                state.has_volume_summary = self._has_volume_summary(
                                    project_id, state.current_volume
                                )

                                # Check if next arc needs expansion
                                if next_outline and next_outline.get("status") == "skeleton":
                                    state.needs_expansion = True
                                    state.next_arc = next_outline.get("arc_index", 0)
                                    state.next_volume = next_outline.get("volume_index", 0)
                except (ValueError, IndexError):
                    continue

        except Exception as e:
            logger.debug("StateLoader: failed to load arc boundary: %s", e)

    def _find_next_outline(
        self, outlines: list[dict], current_end: int
    ) -> Optional[dict]:
        """Find the outline that starts after current_end."""
        for outline in outlines:
            chapters_range = outline.get("chapters_range", "")
            if not chapters_range:
                continue
            try:
                parts = chapters_range.split("-")
                if len(parts) == 2:
                    start = int(parts[0])
                    if start == current_end + 1:
                        return outline
            except (ValueError, IndexError):
                continue
        return None

    def _has_arc_review(
        self, project_id: str, volume: int, arc: int
    ) -> bool:
        """Check if arc review has been completed."""
        try:
            reviews = self.repo.list_reviews(project_id, scope="arc")
            for review in reviews:
                if (
                    review.get("volume") == volume
                    and review.get("arc") == arc
                ):
                    return True
        except Exception:
            pass
        return False

    def _has_arc_summary(
        self, project_id: str, volume: int, arc: int
    ) -> bool:
        """Check if arc summary has been generated."""
        try:
            summaries = self.repo.list_arc_summaries(project_id)
            for summary in summaries:
                if (
                    summary.get("volume") == volume
                    and summary.get("arc") == arc
                ):
                    return True
        except Exception:
            pass
        return False

    def _has_volume_summary(
        self, project_id: str, volume: int
    ) -> bool:
        """Check if volume summary has been generated."""
        try:
            summaries = self.repo.list_volume_summaries(project_id)
            for summary in summaries:
                if summary.get("volume") == volume:
                    return True
        except Exception:
            pass
        return False

    def _load_foundation_missing(self, project_id: str) -> list[str]:
        """Load missing foundation items."""
        missing = []
        try:
            # Check characters
            chars = self.repo.get_characters(project_id)
            if not chars:
                missing.append("characters")

            # Check world settings
            ws = self.repo.list_world_settings(project_id)
            if not ws:
                missing.append("world_settings")

            # Check outlines
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
