"""Example: How to integrate AgentGuardMixin into existing agents.

v6.10.13: This file shows the pattern for integrating StepCheckpoint
and StopGuard into existing agents like Author, Editor, etc.

This is a reference implementation - actual integration should be done
in the real agent files.

DEPRECATED (v6.11.01): Reference/example code should not live in the
production ``agents/`` package. Scheduled for relocation to an examples
directory (v6.11.01 P3). Not imported by any production code.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..agent_runtime.base import BaseAgent
from ..agent_runtime.guard_integration import AgentGuardMixin
from ..guards.stop_guard import StopDecision
from ..models.state import FactoryState

logger = logging.getLogger(__name__)


class GuardedAuthorAgent(BaseAgent, AgentGuardMixin):
    """Example Author agent with checkpoint and stop guard integration.

    This shows how to:
    1. Initialize guard components
    2. Save checkpoints at each step
    3. Check if agent can finish via StopGuard
    4. Recover from checkpoints on restart
    """

    agent_id = "author"

    def __init__(
        self,
        repo,
        llm,
        skill_registry=None,
        base_dir: str | Path = ".novelos",
        **kwargs,
    ):
        super().__init__(repo, llm, skill_registry=skill_registry, **kwargs)

        # Initialize guard components
        self.__init_guard__(
            agent_id=self.agent_id,
            base_dir=base_dir,
            required_checkpoints=["plan", "draft", "commit"],
        )

    def _execute(self, state: FactoryState) -> dict[str, Any]:
        """Execute author with checkpoint recovery."""
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]

        # Step 1: Plan chapter
        if not self._has_checkpoint(project_id, chapter_number, "plan"):
            plan = self._plan_chapter(state)
            self._save_checkpoint(project_id, chapter_number, "plan", plan)
        else:
            plan = self._load_checkpoint(project_id, chapter_number, "plan")
            logger.info("Author: recovered plan from checkpoint")

        # Step 2: Write draft
        if not self._has_checkpoint(project_id, chapter_number, "draft"):
            draft = self._write_draft(state, plan)
            self._save_checkpoint(project_id, chapter_number, "draft", draft)
        else:
            draft = self._load_checkpoint(project_id, chapter_number, "draft")
            logger.info("Author: recovered draft from checkpoint")

        # Step 3: Commit chapter
        if not self._has_checkpoint(project_id, chapter_number, "commit"):
            commit_result = self._commit_chapter(state, draft)
            self._save_checkpoint(project_id, chapter_number, "commit", commit_result)
        else:
            commit_result = self._load_checkpoint(project_id, chapter_number, "commit")
            logger.info("Author: recovered commit from checkpoint")

        # Check if we can finish
        checkpoints = self._checkpoint.list_steps(project_id, chapter_number)
        checkpoint_list = [{"step": s, "seq": i} for i, s in enumerate(checkpoints)]
        guard_result = self._check_can_finish(checkpoint_list)

        if guard_result.decision == StopDecision.BLOCK:
            logger.warning("Author: blocked, missing: %s", guard_result.missing_checkpoints)
            # Return error to trigger retry
            return {"error": f"Missing checkpoints: {guard_result.missing_checkpoints}"}

        if guard_result.decision == StopDecision.ESCALATE:
            logger.error("Author: escalated after %d blocks", guard_result.consecutive_blocks)
            return {"error": "Too many failed attempts", "requires_human": True}

        # Success - cleanup checkpoints
        self._clear_chapter_checkpoints(project_id, chapter_number)

        return {
            "content": draft.get("content", ""),
            "chapter_status": "drafted",
            "total_tokens": commit_result.get("total_tokens", 0),
        }

    def _plan_chapter(self, state: FactoryState) -> dict[str, Any]:
        """Plan chapter content."""
        # Implementation here
        return {"plan": "..."}

    def _write_draft(self, state: FactoryState, plan: dict) -> dict[str, Any]:
        """Write chapter draft."""
        # Implementation here
        return {"content": "..."}

    def _commit_chapter(self, state: FactoryState, draft: dict) -> dict[str, Any]:
        """Commit chapter to database."""
        # Implementation here
        return {"committed": True, "total_tokens": 0}


class GuardedEditorAgent(BaseAgent, AgentGuardMixin):
    """Example Editor agent with checkpoint and stop guard integration."""

    agent_id = "editor"

    def __init__(
        self,
        repo,
        llm,
        skill_registry=None,
        base_dir: str | Path = ".novelos",
        **kwargs,
    ):
        super().__init__(repo, llm, skill_registry=skill_registry, **kwargs)

        # Initialize guard components
        self.__init_guard__(
            agent_id=self.agent_id,
            base_dir=base_dir,
            required_checkpoints=["review", "save_summary"],
        )

    def _execute(self, state: FactoryState) -> dict[str, Any]:
        """Execute editor with checkpoint recovery."""
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]

        # Step 1: Review chapter
        if not self._has_checkpoint(project_id, chapter_number, "review"):
            review = self._review_chapter(state)
            self._save_checkpoint(project_id, chapter_number, "review", review)
        else:
            review = self._load_checkpoint(project_id, chapter_number, "review")
            logger.info("Editor: recovered review from checkpoint")

        # Step 2: Save summary
        if not self._has_checkpoint(project_id, chapter_number, "save_summary"):
            summary = self._save_summary(state, review)
            self._save_checkpoint(project_id, chapter_number, "save_summary", summary)
        else:
            summary = self._load_checkpoint(project_id, chapter_number, "save_summary")
            logger.info("Editor: recovered summary from checkpoint")

        # Check if we can finish
        checkpoints = self._checkpoint.list_steps(project_id, chapter_number)
        checkpoint_list = [{"step": s, "seq": i} for i, s in enumerate(checkpoints)]
        guard_result = self._check_can_finish(checkpoint_list)

        if guard_result.decision == StopDecision.BLOCK:
            logger.warning("Editor: blocked, missing: %s", guard_result.missing_checkpoints)
            return {"error": f"Missing checkpoints: {guard_result.missing_checkpoints}"}

        if guard_result.decision == StopDecision.ESCALATE:
            logger.error("Editor: escalated after %d blocks", guard_result.consecutive_blocks)
            return {"error": "Too many failed attempts", "requires_human": True}

        # Success - cleanup checkpoints
        self._clear_chapter_checkpoints(project_id, chapter_number)

        return {
            "review": review,
            "summary": summary,
            "chapter_status": "reviewed",
        }

    def _review_chapter(self, state: FactoryState) -> dict[str, Any]:
        """Review chapter content."""
        # Implementation here
        return {"verdict": "pass", "score": 85}

    def _save_summary(self, state: FactoryState, review: dict) -> dict[str, Any]:
        """Save chapter summary."""
        # Implementation here
        return {"summary": "..."}
