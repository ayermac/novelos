"""Chapter production dispatch — run, discover, resume, agent/publisher routing."""

from __future__ import annotations

import logging
from typing import Any

from ..models.state import ChapterStatus, FactoryState
from ..agents.planner import PlannerAgent
from ..agents.screenwriter import ScreenwriterAgent
from ..agents.author import AuthorAgent
from ..agents.polisher import PolisherAgent
from ..agents.editor import EditorAgent
from .base import LEGAL_RESUME_STATUSES

logger = logging.getLogger(__name__)

class ChapterDispatchMixin:
    """Chapter production dispatch — run, discover, resume, agent/publisher routing."""

    def run_chapter(
        self,
        project_id: str,
        chapter_number: int,
        max_steps: int = 20,
    ) -> dict[str, Any]:
        """Drive a chapter through the production pipeline.

        Args:
            project_id: Project identifier.
            chapter_number: Chapter number.
            max_steps: Maximum dispatch steps to prevent infinite loops.

        Returns:
            Dict with final status, steps taken, error, requires_human.
        """
        # Verify chapter exists in DB
        chapter = self.repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return {
                "chapter_status": None,
                "steps": [],
                "error": "Chapter not found in DB",
                "requires_human": True,
            }

        steps: list[dict[str, Any]] = []
        step_count = 0
        current_status = chapter["status"]
        last_error: str | None = None
        requires_human = False

        # Create one workflow run for the entire run_chapter invocation
        run_id = self.repo.create_workflow_run(project_id, chapter_number)

        while step_count < max_steps:
            # Always read DB as source of truth
            db_status = self.repo.get_chapter_status(project_id, chapter_number)
            if db_status:
                current_status = db_status

            # Check stop conditions
            if current_status in ("published",):
                break
            if current_status == "blocking":
                steps.append({"step": step_count, "action": "stop", "reason": "blocking"})
                requires_human = True
                break

            # Determine next agent
            next_agent = self._route(project_id, chapter_number, current_status)

            if next_agent in ("__end__", "__stop__"):
                steps.append({
                    "step": step_count,
                    "action": "stop" if next_agent == "__stop__" else "end",
                    "status": current_status,
                })
                if next_agent == "__stop__":
                    requires_human = True
                break

            # Build state and run agent
            state = self._build_state(project_id, chapter_number, current_status)
            state["workflow_run_id"] = run_id

            # Update current_node before running agent
            self.repo.update_workflow_run(run_id, current_node=next_agent)

            result = self._run_agent(next_agent, state)

            step_info = {
                "step": step_count,
                "agent": next_agent,
                "status_before": current_status,
                "status_after": result.get("chapter_status", current_status),
                "error": result.get("error"),
            }
            steps.append(step_info)

            # Handle error / requires_human — propagate to caller
            if result.get("error") or result.get("requires_human"):
                last_error = result.get("error")
                requires_human = result.get("requires_human", False) or bool(result.get("error"))
                # If agent returned requires_human, advance to blocking
                if result.get("requires_human") and not result.get("error"):
                    self.repo.update_chapter_status(project_id, chapter_number, "blocking")
                    current_status = "blocking"
                break

            current_status = result.get("chapter_status", current_status)
            step_count += 1

        # Finalize workflow run
        # Check if we reached a terminal state (published) before checking max_steps
        if current_status == "published":
            # Successfully completed, even if we hit max_steps
            self.repo.update_workflow_run(run_id, status="completed")
        elif step_count >= max_steps:
            # Only mark as blocked if not in terminal state
            requires_human = True
            last_error = last_error or "max_steps exceeded"
            if current_status != "blocking":
                self.repo.update_chapter_status(project_id, chapter_number, "blocking")
                current_status = "blocking"
            self.repo.update_workflow_run(run_id, status="blocked", error_message=last_error)
        elif requires_human or last_error:
            self.repo.update_workflow_run(
                run_id,
                status="blocked" if requires_human and not last_error else "failed",
                error_message=last_error,
            )
        else:
            # Successful completion
            self.repo.update_workflow_run(run_id, status="completed")

        return {
            "run_id": run_id,
            "chapter_status": current_status,
            "steps": steps,
            "error": last_error,
            "requires_human": requires_human,
        }

    def discover_next(self, project_id: str | None = None) -> list[dict]:
        """Discover chapters that need attention.

        Args:
            project_id: If provided, limit to this project. Otherwise all projects.

        Returns:
            List of dicts with project_id, chapter_number, status, next_agent.
        """
        results: list[dict] = []

        if project_id:
            projects = [project_id]
        else:
            # Get all active projects
            conn = self.repo._conn()
            try:
                rows = conn.execute(
                    "SELECT project_id FROM projects WHERE is_current=1 OR status='active'"
                ).fetchall()
                projects = [r["project_id"] for r in rows]
            finally:
                conn.close()

        for pid in projects:
            conn = self.repo._conn()
            try:
                rows = conn.execute(
                    "SELECT chapter_number, status FROM chapters WHERE project_id=?",
                    (pid,),
                ).fetchall()
            finally:
                conn.close()

            for row in rows:
                status = row["status"]
                next_agent = self._route(pid, row["chapter_number"], status)
                if next_agent not in ("__end__", "__stop__"):
                    results.append({
                        "project_id": pid,
                        "chapter_number": row["chapter_number"],
                        "status": status,
                        "next_agent": next_agent,
                    })

        return results

    def resume_blocked(
        self,
        project_id: str,
        chapter_number: int,
        status: str,
    ) -> dict[str, Any]:
        """Resume a blocked chapter to a new legal status.

        Args:
            project_id: Project identifier.
            chapter_number: Chapter number.
            status: Target status to resume to. Must be in LEGAL_RESUME_STATUSES.

        Returns:
            Dict with ok, error, data.
        """
        if status not in LEGAL_RESUME_STATUSES:
            return {
                "ok": False,
                "error": f"Cannot resume to '{status}'. Legal targets: {sorted(LEGAL_RESUME_STATUSES)}",
                "data": {},
            }

        chapter = self.repo.get_chapter(project_id, chapter_number)
        if not chapter:
            return {"ok": False, "error": "Chapter not found in DB", "data": {}}

        # Update status without expected_status (human override)
        ok = self.repo.update_chapter_status(project_id, chapter_number, status)
        if not ok:
            return {"ok": False, "error": "Failed to update chapter status", "data": {}}

        # Log the human resume action as a workflow run entry
        run_id = self.repo.create_workflow_run(project_id, chapter_number)
        self.repo.update_workflow_run(
            run_id,
            status="completed",
            current_node="human_resume",
            error_message=f"Human resume: {chapter['status']} → {status}",
        )

        return {"ok": True, "error": None, "data": {"new_status": status}}

    def _run_agent(self, agent_name: str, state: FactoryState) -> dict[str, Any]:
        """Instantiate and run an agent by name.

        v3.1: Catches LLMRouter errors and returns error dict instead of raising.
        """
        agent_map = {
            "planner": PlannerAgent,
            "screenwriter": ScreenwriterAgent,
            "author": AuthorAgent,
            "polisher": PolisherAgent,
            "editor": EditorAgent,
        }

        if agent_name == "publisher":
            return self._run_publisher(state)

        agent_cls = agent_map.get(agent_name)
        if not agent_cls:
            return {"error": f"Unknown agent: {agent_name}", "chapter_status": state.get("chapter_status")}

        # Get LLM for this agent (v3.1: agent-level routing)
        try:
            llm = self._llm_for_agent(agent_name)
        except ValueError as e:
            # LLMRouter error (missing API key, base_url, etc.)
            logger.error(f"LLM configuration error for agent '{agent_name}': {e}")
            return {
                "error": f"LLM configuration error: {e}",
                "chapter_status": state.get("chapter_status"),
                "requires_human": True,
            }

        # Inject skill_registry for Polisher and Editor (v2.1)
        if agent_name in ("polisher", "editor"):
            # Only pass skill_registry if it's not None
            agent = agent_cls(self.repo, llm, skill_registry=self.skill_registry if self.skill_registry is not None else None)
        else:
            agent = agent_cls(self.repo, llm)

        return agent.run(state)

    def _run_publisher(self, state: FactoryState) -> dict[str, Any]:
        """Publish a reviewed chapter."""
        project_id = state["project_id"]
        chapter_number = state["chapter_number"]
        ok = self.repo.publish_chapter(project_id, chapter_number)
        if not ok:
            return {"error": "Failed to publish chapter", "chapter_status": state.get("chapter_status")}
        return {
            "chapter_status": ChapterStatus.PUBLISHED.value,
            "current_stage": "published",
        }
