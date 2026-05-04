"""Base Agent class for Novel Factory.

All agents inherit from BaseAgent and implement build_context, run, validate_output.
"""

from __future__ import annotations

import logging
from typing import Any

from ..db.repository import Repository
from ..llm.provider import LLMProvider
from ..models.state import FactoryState
from ..validators.state_verifier import check_status_precondition

logger = logging.getLogger(__name__)


class BaseAgent:
    """Abstract base for all Novel Factory agents.

    Subclasses must define:
    - agent_id: unique identifier
    - build_context(): assemble LLM context from FactoryState
    - _execute(): execute the agent's task (called by run template method)
    - validate_output(): validate structured output before writing to DB
    """

    agent_id: str = "base"

    def __init__(
        self,
        repo: Repository,
        llm: LLMProvider,
    ) -> None:
        self.repo = repo
        self.llm = llm

    def build_context(self, state: FactoryState) -> str:
        """Build the LLM prompt context from the current workflow state.

        Override in subclasses to customize context per agent.
        """
        return ""

    def validate_output(self, output: dict) -> None:
        """Validate agent output against its schema.

        Raises ValueError if output is invalid.
        Override in subclasses.
        """
        pass

    def check_precondition(self, state: FactoryState) -> None:
        """Check chapter status precondition before writing.

        Reads DB current status as source of truth. If DB status differs
        from FactoryState, raises ValueError to prevent stale writes.

        Raises ValueError if the current chapter status does not allow
        this agent to write.
        """
        project_id = state.get("project_id", "")
        chapter_number = state.get("chapter_number", 0)

        # Read DB status as source of truth
        db_status = self.repo.get_chapter_status(project_id, chapter_number)
        if not db_status:
            raise ValueError(
                f"Agent '{self.agent_id}' precondition failed: chapter not found in DB"
            )

        state_status = state.get("chapter_status", "")
        if db_status != state_status:
            raise ValueError(
                f"Agent '{self.agent_id}' precondition failed: "
                f"DB status '{db_status}' != state status '{state_status}'. "
                f"Stale state, refusing to write."
            )

        violations = check_status_precondition(self.agent_id, db_status)
        if violations:
            raise ValueError(
                f"Agent '{self.agent_id}' precondition failed: {'; '.join(violations)}"
            )

    def run(self, state: FactoryState) -> dict[str, Any]:
        """Execute the agent's core logic with precondition and validation guards.

        Returns a dict of updates to merge into FactoryState.
        Must NOT mutate state directly.

        Subclasses should override _execute() instead of this method.
        """
        try:
            self.check_precondition(state)
            return self._execute(state)
        except ValueError as e:
            message = str(e)
            logger.error("Agent '%s' validation failed: %s", self.agent_id, message)
            if "死刑红线" in message:
                return {
                    "error": message,
                    "chapter_status": state.get("chapter_status"),
                    "quality_gate": {
                        "pass": False,
                        "revision_target": self.agent_id if self.agent_id in ("author", "polisher") else "author",
                        "death_penalty_fail": True,
                        "message": message,
                        "agent": self.agent_id,
                        "workflow_run_id": state.get("workflow_run_id"),
                    },
                }
            return {"error": message, "chapter_status": state.get("chapter_status")}
        except Exception as e:
            logger.exception("Agent '%s' execution failed", self.agent_id)
            return {"error": str(e), "chapter_status": state.get("chapter_status")}

    def _execute(self, state: FactoryState) -> dict[str, Any]:
        """Internal execution method. Subclasses must implement this."""
        raise NotImplementedError

    def _compensate_status(
        self, project_id: str, chapter_number: int,
        current_status: str, target_status: str,
    ) -> None:
        """Roll back chapter status after a write failure.

        Best-effort: uses expected_status guard so it only rolls back if
        the status is still ``current_status``.  Logs a warning if the
        compensation itself fails.
        """
        try:
            self.repo.update_chapter_status(
                project_id, chapter_number, target_status,
                expected_status=current_status,
            )
        except Exception:
            logger.warning(
                "Failed to compensate status %s→%s for %s/%s",
                current_status, target_status, project_id, chapter_number,
            )

    def _get_chapter_info(self, state: FactoryState) -> dict | None:
        """Helper: get current chapter from DB."""
        return self.repo.get_chapter(state["project_id"], state["chapter_number"])

    def _get_instruction(self, state: FactoryState) -> dict | None:
        """Helper: get instruction for current chapter."""
        return self.repo.get_instruction(state["project_id"], state["chapter_number"])

    def _get_scene_beats(self, state: FactoryState) -> list[dict]:
        """Helper: get scene beats for current chapter."""
        return self.repo.get_scene_beats(state["project_id"], state["chapter_number"])

    def _get_prev_state_card(self, state: FactoryState) -> dict | None:
        """Helper: get previous chapter's state card."""
        prev_ch = state["chapter_number"] - 1
        if prev_ch < 1:
            return None
        return self.repo.get_chapter_state(state["project_id"], prev_ch)

    def _get_style_bible_context(self, project_id: str, agent_id: str) -> str:
        """Helper: get Style Bible context for a specific agent (v4.0).

        Returns an empty string if no Style Bible exists for the project.
        Silently returns "" on any error (never blocks the main flow).
        """
        try:
            from ..style_bible.loader import get_style_context_for_agent
            return get_style_context_for_agent(project_id, agent_id, self.repo)
        except Exception:
            return ""
