"""Dispatcher — runtime orchestrator for chapter production.

Responsibilities:
- Task discovery based on DB status (source of truth)
- Status routing per the v1.3 routing table
- Single-step and multi-step chapter execution
- Health checks, retry/circuit-breaker awareness
- Human intervention detection
- Workflow run tracking

Prohibited:
- Does NOT generate content
- Does NOT modify Agent output
- Does NOT bypass Agent precondition checks
- Does NOT trust in-memory state over DB state
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .db.repository import Repository
from .llm.provider import LLMProvider
from .models.state import ChapterStatus, FactoryState
from .agents.planner import PlannerAgent
from .agents.screenwriter import ScreenwriterAgent
from .agents.author import AuthorAgent
from .agents.polisher import PolisherAgent
from .agents.editor import EditorAgent

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
}

REVISION_ROUTE: dict[str, str] = {
    "author": "author",
    "polisher": "polisher",
    "planner": "__stop__",  # human handling required
}

# Legal target statuses for human-resume (D5)
LEGAL_RESUME_STATUSES = {"planned", "scripted", "drafted", "polished", "revision"}


class Dispatcher:
    """Runtime dispatcher for chapter production pipeline."""

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
                from .skills.registry import SkillRegistry
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

    # ── Public API ────────────────────────────────────────────────

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

    # ── Sidecar Agent methods (v2) ────────────────────────────────

    def run_scout(
        self,
        project_id: str,
        topic: str | None = None,
        genre: str | None = None,
        platform: str | None = None,
        audience: str | None = None,
    ) -> dict[str, Any]:
        """Run Scout agent to generate market report.

        Note: This is a sidecar method that does NOT change chapter status.

        Args:
            project_id: Project identifier.
            topic: Optional topic to analyze.
            genre: Optional target genre.
            platform: Optional target platform.
            audience: Optional target audience.

        Returns:
            Dict with success, report_id, market_report, error.
        """
        from .agents.scout import ScoutAgent

        # v3.1: Use agent-specific LLM with error handling
        try:
            llm = self._llm_for_agent("scout")
        except ValueError as e:
            logger.error(f"LLM configuration error for scout: {e}")
            return {"ok": False, "error": f"LLM configuration error: {e}", "data": {}}
        
        scout = ScoutAgent(self.repo, llm)
        return scout.run(
            project_id=project_id,
            topic=topic,
            genre=genre,
            platform=platform,
            audience=audience,
        )

    def run_secretary_report(
        self,
        project_id: str,
        report_type: str = "daily",
        date: str | None = None,
    ) -> dict[str, Any]:
        """Run Secretary agent to generate report.

        Note: This is a sidecar method that does NOT change chapter status.

        Args:
            project_id: Project identifier.
            report_type: Type of report (daily, weekly, etc.).
            date: Optional date string.

        Returns:
            Dict with success, report, error.
        """
        from .agents.secretary import SecretaryAgent

        secretary = SecretaryAgent(self.repo)
        
        if report_type == "daily":
            return secretary.generate_daily_report(project_id, date)
        else:
            return {"success": False, "error": f"Unsupported report type: {report_type}"}

    def run_secretary_export(
        self,
        project_id: str,
        chapter_number: int,
        export_format: str = "markdown",
    ) -> dict[str, Any]:
        """Run Secretary agent to export chapter.

        Note: This is a sidecar method that does NOT change chapter status.

        Args:
            project_id: Project identifier.
            chapter_number: Chapter number to export.
            export_format: Export format (json, markdown).

        Returns:
            Dict with success, export, error.
        """
        from .agents.secretary import SecretaryAgent

        secretary = SecretaryAgent(self.repo)
        return secretary.export_chapter(project_id, chapter_number, export_format)

    def run_continuity_check(
        self,
        project_id: str,
        from_chapter: int,
        to_chapter: int,
    ) -> dict[str, Any]:
        """Run ContinuityChecker agent for cross-chapter consistency.

        Note: This is a sidecar method that does NOT change chapter status.

        Args:
            project_id: Project identifier.
            from_chapter: Start chapter number.
            to_chapter: End chapter number.

        Returns:
            Dict with success, report, issues, error.
        """
        from .agents.continuity_checker import ContinuityCheckerAgent

        # v3.1: Use agent-specific LLM with error handling
        try:
            llm = self._llm_for_agent("continuity_checker")
        except ValueError as e:
            logger.error(f"LLM configuration error for continuity_checker: {e}")
            return {"ok": False, "error": f"LLM configuration error: {e}", "data": {}}
        
        checker = ContinuityCheckerAgent(self.repo, llm)
        return checker.run(project_id, from_chapter, to_chapter)

    def run_architect_suggest(
        self,
        project_id: str,
        scope: str = "quality",
    ) -> dict[str, Any]:
        """Run Architect agent to generate improvement proposals.

        Note: This is a sidecar method that does NOT change chapter status
        or automatically apply any changes.

        Args:
            project_id: Project identifier.
            scope: Scope of analysis (quality, workflow, agent, system).

        Returns:
            Dict with success, proposals, error.
        """
        from .agents.architect import ArchitectAgent

        # v3.1: Use agent-specific LLM with error handling
        try:
            llm = self._llm_for_agent("architect")
        except ValueError as e:
            logger.error(f"LLM configuration error for architect: {e}")
            return {"ok": False, "error": f"LLM configuration error: {e}", "data": {}}
        
        architect = ArchitectAgent(self.repo, llm)
        return architect.run(project_id, scope)

    # ── Batch Production methods (v3.0) ─────────────────────────────

    def run_batch(
        self,
        project_id: str,
        from_chapter: int,
        to_chapter: int,
        stop_on_block: bool = True,
    ) -> dict[str, Any]:
        """Run batch production for multiple chapters.

        Args:
            project_id: Project identifier.
            from_chapter: Starting chapter number (inclusive).
            to_chapter: Ending chapter number (inclusive).
            stop_on_block: Stop batch if any chapter fails/blocks/requires_human.

        Returns:
            Dict with ok, error, data containing run_id and batch status.
        """
        # Validate chapter range
        if from_chapter > to_chapter:
            return {
                "ok": False,
                "error": f"from_chapter ({from_chapter}) must be <= to_chapter ({to_chapter})",
                "data": {},
            }

        # Create production run
        run_id = self.repo.create_production_run(project_id, from_chapter, to_chapter)
        if not run_id:
            return {
                "ok": False,
                "error": "Failed to create production run",
                "data": {},
            }

        # Create production run items for each chapter
        item_ids = {}
        for chapter_num in range(from_chapter, to_chapter + 1):
            item_id = self.repo.create_production_run_item(run_id, project_id, chapter_num)
            if not item_id:
                # Mark run as failed and return
                self.repo.update_production_run(run_id, status="failed", error="Failed to create production run items")
                return {
                    "ok": False,
                    "error": "Failed to create production run items",
                    "data": {"run_id": run_id},
                }
            item_ids[chapter_num] = item_id

        # Run each chapter sequentially
        blocked_chapter = None
        blocked_error = None
        completed_count = 0

        for chapter_num in range(from_chapter, to_chapter + 1):
            item_id = item_ids[chapter_num]

            # Mark item as running
            ok = self.repo.update_production_run_item(item_id, status="running", started_at=self._now_iso())
            if not ok:
                # Mark run as failed and return
                self.repo.update_production_run(run_id, status="failed", error=f"Failed to mark item {chapter_num} as running")
                return {
                    "ok": False,
                    "error": f"Failed to mark item {chapter_num} as running",
                    "data": {"run_id": run_id},
                }

            # Run chapter using existing run_chapter method
            result = self.run_chapter(project_id, chapter_num)

            # Determine item status based on result
            chapter_status = result.get("chapter_status")
            error = result.get("error")
            requires_human = result.get("requires_human", False)

            # Get workflow_run_id from the latest workflow run for this chapter
            workflow_run_id = None
            workflow_runs = self.repo.get_workflow_runs_for_project(project_id, chapter_number=chapter_num, limit=1)
            if workflow_runs:
                workflow_run_id = workflow_runs[0].get("id")

            # Get quality_pass from latest quality report
            quality_pass = None
            chapter = self.repo.get_chapter(project_id, chapter_num)
            if chapter:
                # Try to get the latest quality report (try final stage first, then polished, then draft)
                for stage in ["final", "polished", "draft"]:
                    latest_report = self.repo.get_latest_quality_report(project_id, chapter_num, stage)
                    if latest_report:
                        quality_pass = bool(latest_report.get("pass", 0))
                        break

            # Check if blocked
            is_blocked = bool(error) or requires_human or chapter_status == "blocking"

            if is_blocked:
                # Mark item as blocked
                ok = self.repo.update_production_run_item(
                    item_id,
                    status="blocked",
                    workflow_run_id=workflow_run_id,
                    chapter_status=chapter_status,
                    quality_pass=quality_pass,
                    error=error,
                    requires_human=requires_human,
                    completed_at=self._now_iso(),
                )
                if not ok:
                    self.repo.update_production_run(run_id, status="failed", error=f"Failed to mark item {chapter_num} as blocked")
                    return {
                        "ok": False,
                        "error": f"Failed to mark item {chapter_num} as blocked",
                        "data": {"run_id": run_id},
                    }

                # Mark run as blocked
                blocked_chapter = chapter_num
                blocked_error = error or ("requires_human" if requires_human else "blocking")
                ok = self.repo.update_production_run(
                    run_id,
                    status="blocked",
                    blocked_chapter=blocked_chapter,
                    error=blocked_error,
                )
                if not ok:
                    return {
                        "ok": False,
                        "error": "Failed to mark run as blocked",
                        "data": {"run_id": run_id},
                    }

                # Stop if stop_on_block is True
                if stop_on_block:
                    # Mark remaining items as skipped
                    for remaining_chapter in range(chapter_num + 1, to_chapter + 1):
                        remaining_item_id = item_ids[remaining_chapter]
                        ok = self.repo.update_production_run_item(remaining_item_id, status="skipped")
                        if not ok:
                            self.repo.update_production_run(run_id, status="failed", error=f"Failed to mark item {remaining_chapter} as skipped")
                            return {
                                "ok": False,
                                "error": f"Failed to mark item {remaining_chapter} as skipped",
                                "data": {"run_id": run_id},
                            }
                    break
            else:
                # Mark item as completed
                ok = self.repo.update_production_run_item(
                    item_id,
                    status="completed",
                    workflow_run_id=workflow_run_id,
                    chapter_status=chapter_status,
                    quality_pass=quality_pass,
                    error=None,
                    requires_human=False,
                    completed_at=self._now_iso(),
                )
                if not ok:
                    self.repo.update_production_run(run_id, status="failed", error=f"Failed to mark item {chapter_num} as completed")
                    return {
                        "ok": False,
                        "error": f"Failed to mark item {chapter_num} as completed",
                        "data": {"run_id": run_id},
                    }
                completed_count += 1

        # If not blocked, mark run as awaiting_review
        if not blocked_chapter:
            ok = self.repo.update_production_run(
                run_id,
                status="awaiting_review",
                completed_chapters=completed_count,
                completed_at=self._now_iso(),
            )
            if not ok:
                return {
                    "ok": False,
                    "error": "Failed to mark run as awaiting_review",
                    "data": {"run_id": run_id},
                }
        else:
            # Update completed count even if blocked
            ok = self.repo.update_production_run(run_id, completed_chapters=completed_count)
            if not ok:
                return {
                    "ok": False,
                    "error": "Failed to update completed_chapters count",
                    "data": {"run_id": run_id},
                }

        # Get final run status
        run = self.repo.get_production_run(run_id)

        # v3.1: Return error if blocked
        if blocked_chapter:
            return {
                "ok": False,
                "error": blocked_error or f"Blocked at chapter {blocked_chapter}",
                "data": {
                    "run_id": run_id,
                    "project_id": project_id,
                    "status": run.get("status") if run else "unknown",
                    "from_chapter": from_chapter,
                    "to_chapter": to_chapter,
                    "blocked_chapter": blocked_chapter,
                },
            }

        return {
            "ok": True,
            "error": None,
            "data": {
                "run_id": run_id,
                "project_id": project_id,
                "status": run.get("status") if run else "unknown",
                "from_chapter": from_chapter,
                "to_chapter": to_chapter,
                "completed_chapters": run.get("completed_chapters", 0) if run else 0,
                "blocked_chapter": run.get("blocked_chapter") if run else None,
            },
        }

    def get_batch_status(self, run_id: str) -> dict[str, Any]:
        """Get batch production run status.

        Args:
            run_id: Production run identifier.

        Returns:
            Dict with ok, error, data containing run status and items.
        """
        run = self.repo.get_production_run(run_id)
        if not run:
            return {
                "ok": False,
                "error": f"production run not found: {run_id}",
                "data": {},
            }

        items = self.repo.get_production_run_items(run_id)

        # Transform items to clean format
        items_data = []
        for item in items:
            items_data.append({
                "chapter_number": item.get("chapter_number"),
                "status": item.get("status"),
                "chapter_status": item.get("chapter_status"),
                "quality_pass": bool(item.get("quality_pass", 0)) if item.get("quality_pass") is not None else None,
                "error": item.get("error"),
                "requires_human": bool(item.get("requires_human", 0)),
            })

        return {
            "ok": True,
            "error": None,
            "data": {
                "run_id": run.get("id"),
                "project_id": run.get("project_id"),
                "status": run.get("status"),
                "from_chapter": run.get("from_chapter"),
                "to_chapter": run.get("to_chapter"),
                "completed_chapters": run.get("completed_chapters", 0),
                "blocked_chapter": run.get("blocked_chapter"),
                "items": items_data,
            },
        }

    def review_batch(
        self,
        run_id: str,
        decision: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Record human review decision for a batch production run.

        Args:
            run_id: Production run identifier.
            decision: Review decision (approve, request_changes, reject).
            notes: Optional review notes.

        Returns:
            Dict with ok, error, data.
        """
        # Validate decision
        valid_decisions = {"approve", "request_changes", "reject"}
        if decision not in valid_decisions:
            return {
                "ok": False,
                "error": f"Invalid decision '{decision}'. Must be one of: {sorted(valid_decisions)}",
                "data": {},
            }

        # Get production run
        run = self.repo.get_production_run(run_id)
        if not run:
            return {
                "ok": False,
                "error": f"production run not found: {run_id}",
                "data": {},
            }

        # v3.3: If decision is approve, check continuity gate first
        if decision == "approve":
            gate_check = self.can_approve_batch(run_id)
            if not gate_check.get("ok"):
                # Gate blocks approve — do NOT update production_run or save review_session
                gate = self.repo.get_latest_batch_continuity_gate(run_id)
                blocking_issues = []
                if gate:
                    import json as _json
                    blocking_issues = _json.loads(gate.get("blocking_issues_json", "[]"))
                return {
                    "ok": False,
                    "error": "Batch continuity gate failed; approve is blocked",
                    "data": {
                        "run_id": run_id,
                        "gate_status": gate_check["data"].get("gate_status"),
                        "blocking_issues": blocking_issues,
                    },
                }

        # Calculate new status based on decision
        status_map = {
            "approve": "approved",
            "request_changes": "request_changes",
            "reject": "rejected",
        }
        new_status = status_map[decision]
        original_status = run.get("status")

        # Update production run status FIRST (before saving review session)
        ok = self.repo.update_production_run(run_id, status=new_status)
        if not ok:
            return {
                "ok": False,
                "error": "Failed to update production run status",
                "data": {"run_id": run_id},
            }

        # Save human review session (after status update succeeds)
        project_id = run.get("project_id")
        session_id = self.repo.save_human_review_session(run_id, project_id, decision, notes)
        if not session_id:
            # Compensate: revert run status back to original
            self.repo.update_production_run(run_id, status=original_status)
            return {
                "ok": False,
                "error": "Failed to save human review session",
                "data": {"run_id": run_id},
            }

        return {
            "ok": True,
            "error": None,
            "data": {
                "run_id": run_id,
                "decision": decision,
            },
        }

    def _now_iso(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    # ── Routing logic ─────────────────────────────────────────────

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

    # ── Internal helpers ──────────────────────────────────────────

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

    # ── Batch Revision (v3.2) ─────────────────────────────────────

    def create_batch_revision_plan(
        self,
        run_id: str,
        plan_json: str,
    ) -> dict[str, Any]:
        """Create a batch revision plan from a revision plan JSON.

        Args:
            run_id: Source production run ID.
            plan_json: JSON string of the revision plan.

        Returns:
            Dict with ok, error, data containing revision_run_id and affected chapters.
        """
        import json
        from datetime import datetime

        # Parse plan JSON
        try:
            plan = json.loads(plan_json)
        except json.JSONDecodeError as e:
            return {"ok": False, "error": f"Invalid plan JSON: {e}", "data": {}}

        # Validate plan structure
        if "actions" not in plan or not plan["actions"]:
            return {"ok": False, "error": "Plan must have 'actions' array", "data": {}}

        # Get source run
        source_run = self.repo.get_production_run(run_id)
        if not source_run:
            return {"ok": False, "error": f"Production run {run_id} not found", "data": {}}

        # Check source run status
        if source_run.get("status") != "request_changes":
            return {
                "ok": False,
                "error": f"Production run status must be 'request_changes', got '{source_run.get('status')}'",
                "data": {}
            }

        # Get latest human review session
        latest_session = self.repo.get_latest_human_review_session(run_id)
        if not latest_session:
            return {"ok": False, "error": "No human review session found for this run", "data": {}}

        # Calculate affected chapters
        affected_chapters = set()
        from_chapter = source_run.get("from_chapter", 1)
        to_chapter = source_run.get("to_chapter", 0)

        for action in plan["actions"]:
            action_type = action.get("action")

            if action_type == "rerun_chapter":
                chapter = action.get("chapter")
                if chapter is None:
                    return {"ok": False, "error": "rerun_chapter requires 'chapter' field", "data": {}}
                # R2: Validate chapter is within source batch range
                if not (from_chapter <= chapter <= to_chapter):
                    return {
                        "ok": False,
                        "error": f"Chapter {chapter} is outside source batch range [{from_chapter}, {to_chapter}]",
                        "data": {}
                    }
                affected_chapters.add(chapter)

            elif action_type == "resume_to_status":
                chapter = action.get("chapter")
                status = action.get("status")
                if chapter is None:
                    return {"ok": False, "error": "resume_to_status requires 'chapter' field", "data": {}}
                if status is None:
                    return {"ok": False, "error": "resume_to_status requires 'status' field", "data": {}}
                if status not in LEGAL_RESUME_STATUSES:
                    return {
                        "ok": False,
                        "error": f"Invalid status '{status}', must be one of {LEGAL_RESUME_STATUSES}",
                        "data": {}
                    }
                # R2: Validate chapter is within source batch range
                if not (from_chapter <= chapter <= to_chapter):
                    return {
                        "ok": False,
                        "error": f"Chapter {chapter} is outside source batch range [{from_chapter}, {to_chapter}]",
                        "data": {}
                    }
                affected_chapters.add(chapter)

            elif action_type == "rerun_tail":
                from_chapter_arg = action.get("from_chapter")
                if from_chapter_arg is None:
                    return {"ok": False, "error": "rerun_tail requires 'from_chapter' field", "data": {}}
                # R2: Validate from_chapter is within source batch range
                if not (from_chapter <= from_chapter_arg <= to_chapter):
                    return {
                        "ok": False,
                        "error": f"from_chapter {from_chapter_arg} is outside source batch range [{from_chapter}, {to_chapter}]",
                        "data": {}
                    }
                # Add all chapters from from_chapter_arg to to_chapter
                for ch in range(from_chapter_arg, to_chapter + 1):
                    affected_chapters.add(ch)

            else:
                return {"ok": False, "error": f"Unknown action type: {action_type}", "data": {}}

        if not affected_chapters:
            return {"ok": False, "error": "No chapters affected by the revision plan", "data": {}}

        # Create revision run
        revision_run_id = self.repo.create_batch_revision_run(
            source_run_id=run_id,
            project_id=source_run["project_id"],
            decision_session_id=latest_session["id"],
            plan_json=plan_json,
            affected_chapters_json=json.dumps(sorted(affected_chapters)),
        )

        # Create revision items and save review notes
        for action in plan["actions"]:
            action_type = action.get("action")
            notes = action.get("notes")

            if action_type == "rerun_chapter":
                chapter = action["chapter"]
                self.repo.create_batch_revision_item(
                    revision_run_id=revision_run_id,
                    chapter_number=chapter,
                    action="rerun_chapter",
                    notes=notes,
                )
                if notes:
                    self.repo.save_chapter_review_note(
                        project_id=source_run["project_id"],
                        chapter_number=chapter,
                        source_run_id=run_id,
                        revision_run_id=revision_run_id,
                        notes=notes,
                    )

            elif action_type == "resume_to_status":
                chapter = action["chapter"]
                status = action["status"]
                self.repo.create_batch_revision_item(
                    revision_run_id=revision_run_id,
                    chapter_number=chapter,
                    action="resume_to_status",
                    target_status=status,
                    notes=notes,
                )
                if notes:
                    self.repo.save_chapter_review_note(
                        project_id=source_run["project_id"],
                        chapter_number=chapter,
                        source_run_id=run_id,
                        revision_run_id=revision_run_id,
                        notes=notes,
                    )

            elif action_type == "rerun_tail":
                from_chapter = action["from_chapter"]
                # Create items for all chapters in the tail
                for ch in range(from_chapter, to_chapter + 1):
                    # Only create if not already created by another action
                    existing_items = [
                        item for item in self.repo.get_batch_revision_items(revision_run_id)
                        if item["chapter_number"] == ch
                    ]
                    if not existing_items:
                        self.repo.create_batch_revision_item(
                            revision_run_id=revision_run_id,
                            chapter_number=ch,
                            action="rerun_tail",
                            notes=notes if ch == from_chapter else None,
                        )
                        if notes and ch == from_chapter:
                            self.repo.save_chapter_review_note(
                                project_id=source_run["project_id"],
                                chapter_number=ch,
                                source_run_id=run_id,
                                revision_run_id=revision_run_id,
                                notes=notes,
                            )

        return {
            "ok": True,
            "error": None,
            "data": {
                "revision_run_id": revision_run_id,
                "affected_chapters": sorted(affected_chapters),
                "status": "pending",
            }
        }

    def _revision_pre_run(
        self,
        revision_run: dict,
        chapter_number: int,
        action: str,
        target_status: str | None,
    ) -> tuple[bool, str | None]:
        """Prepare chapter status before running revision.

        Returns (ok, error) tuple.
        """
        project_id = revision_run["project_id"]

        if action in ("rerun_chapter", "rerun_tail"):
            chapter = self.repo.get_chapter(project_id, chapter_number)
            if chapter and chapter.get("status") == "published":
                ok = self.repo.update_chapter_status(project_id, chapter_number, "revision")
                if not ok:
                    return (False, "Failed to resume to revision status")
            return (True, None)

        elif action == "resume_to_status":
            ok = self.repo.update_chapter_status(project_id, chapter_number, target_status)
            if not ok:
                return (False, f"Failed to resume to status {target_status}")
            return (True, None)

        return (False, f"Unknown action: {action}")

    def run_batch_revision(
        self,
        revision_run_id: str,
        stop_on_error: bool = True,
    ) -> dict[str, Any]:
        """Execute a batch revision run.

        Every write to revision item/run status is checked. If any write
        fails, the method returns ``ok: False`` — never silently continues.
        """
        from datetime import datetime

        revision_run = self.repo.get_batch_revision_run(revision_run_id)
        if not revision_run:
            return {"ok": False, "error": f"Revision run {revision_run_id} not found", "data": {}}

        # Mark revision run as running — must succeed
        ok = self.repo.update_batch_revision_run(revision_run_id, status="running")
        if not ok:
            return {"ok": False, "error": "Failed to update revision run status to running", "data": {}}

        items = self.repo.get_batch_revision_items(revision_run_id)
        failed_chapter: int | None = None
        failed_error: str | None = None

        for item in items:
            chapter_number = item["chapter_number"]
            action = item["action"]
            target_status = item.get("target_status")
            item_id = item["id"]

            # ── R1: Mark item as running (must block on failure) ──
            ok = self.repo.update_batch_revision_item(item_id, status="running")
            if not ok:
                self.repo.update_batch_revision_run(
                    revision_run_id, status="failed",
                    error=f"ch{chapter_number}: item running state write failed",
                    completed_at=datetime.now().isoformat(),
                )
                return {
                    "ok": False,
                    "error": f"ch{chapter_number}: item running state write failed",
                    "data": {"revision_run_id": revision_run_id},
                }

            try:
                # Pre-run: prepare chapter status based on action type
                pre_ok, pre_error = self._revision_pre_run(
                    revision_run, chapter_number, action, target_status,
                )
                if not pre_ok:
                    # Mark item failed
                    item_ok = self.repo.update_batch_revision_item(
                        item_id, status="failed",
                        error=pre_error,
                        completed_at=datetime.now().isoformat(),
                    )
                    if not item_ok:
                        self.repo.update_batch_revision_run(
                            revision_run_id, status="failed",
                            error=f"ch{chapter_number}: {pre_error}; AND item failed state write failed",
                            completed_at=datetime.now().isoformat(),
                        )
                        return {
                            "ok": False,
                            "error": f"ch{chapter_number}: {pre_error}; AND item failed state write failed",
                            "data": {"revision_run_id": revision_run_id},
                        }
                    if stop_on_error:
                        failed_chapter = chapter_number
                        failed_error = pre_error
                        break
                    continue

                # Run chapter through pipeline
                result = self.run_chapter(revision_run["project_id"], chapter_number)

                if result.get("error") or result.get("requires_human"):
                    error_msg = result.get("error", "requires_human")
                    # Mark item failed
                    item_ok = self.repo.update_batch_revision_item(
                        item_id, status="failed",
                        error=error_msg,
                        completed_at=datetime.now().isoformat(),
                    )
                    if not item_ok:
                        self.repo.update_batch_revision_run(
                            revision_run_id, status="failed",
                            error=f"ch{chapter_number} failed; AND item failed state write failed",
                            completed_at=datetime.now().isoformat(),
                        )
                        return {
                            "ok": False,
                            "error": f"ch{chapter_number} failed; AND item failed state write failed",
                            "data": {"revision_run_id": revision_run_id},
                        }
                    if stop_on_error:
                        failed_chapter = chapter_number
                        failed_error = error_msg
                        break
                else:
                    # Mark item completed
                    item_ok = self.repo.update_batch_revision_item(
                        item_id, status="completed",
                        completed_at=datetime.now().isoformat(),
                    )
                    if not item_ok:
                        self.repo.update_batch_revision_run(
                            revision_run_id, status="failed",
                            error=f"ch{chapter_number} completed but item completed state write failed",
                            completed_at=datetime.now().isoformat(),
                        )
                        return {
                            "ok": False,
                            "error": f"ch{chapter_number} completed but item completed state write failed",
                            "data": {"revision_run_id": revision_run_id},
                        }

            except Exception as e:
                logger.error(f"Revision item {item_id} failed: {e}")
                # Mark item failed
                item_ok = self.repo.update_batch_revision_item(
                    item_id, status="failed", error=str(e),
                    completed_at=datetime.now().isoformat(),
                )
                if not item_ok:
                    self.repo.update_batch_revision_run(
                        revision_run_id, status="failed",
                        error=f"ch{chapter_number} exception; AND item failed state write failed",
                        completed_at=datetime.now().isoformat(),
                    )
                    return {
                        "ok": False,
                        "error": f"ch{chapter_number} exception; AND item failed state write failed",
                        "data": {"revision_run_id": revision_run_id},
                    }
                if stop_on_error:
                    failed_chapter = chapter_number
                    failed_error = str(e)
                    break

        # ── R2: Mark final revision run status and check return value ──
        if failed_chapter:
            ok = self.repo.update_batch_revision_run(
                revision_run_id, status="failed",
                error=f"Failed at chapter {failed_chapter}: {failed_error}",
                completed_at=datetime.now().isoformat(),
            )
            if not ok:
                return {
                    "ok": False,
                    "error": f"Failed at chapter {failed_chapter}: {failed_error}; AND revision run failed state write failed",
                    "data": {"revision_run_id": revision_run_id},
                }
            return {
                "ok": False,
                "error": f"Failed at chapter {failed_chapter}: {failed_error}",
                "data": {"revision_run_id": revision_run_id, "status": "failed", "failed_chapter": failed_chapter},
            }
        else:
            ok = self.repo.update_batch_revision_run(
                revision_run_id, status="completed",
                completed_at=datetime.now().isoformat(),
            )
            if not ok:
                return {
                    "ok": False,
                    "error": "Revision completed but revision run completed state write failed",
                    "data": {"revision_run_id": revision_run_id},
                }
            return {
                "ok": True,
                "error": None,
                "data": {"revision_run_id": revision_run_id, "status": "completed"},
            }


    def get_batch_revision_status(self, revision_run_id: str) -> dict[str, Any]:
        """Get the status of a batch revision run.

        Args:
            revision_run_id: Revision run identifier.

        Returns:
            Dict with ok, error, data containing revision status.
        """
        import json

        revision_run = self.repo.get_batch_revision_run(revision_run_id)
        if not revision_run:
            return {"ok": False, "error": f"Revision run {revision_run_id} not found", "data": {}}

        items = self.repo.get_batch_revision_items(revision_run_id)

        affected_chapters = json.loads(revision_run.get("affected_chapters_json", "[]"))

        return {
            "ok": True,
            "error": None,
            "data": {
                "revision_run_id": revision_run_id,
                "source_run_id": revision_run["source_run_id"],
                "status": revision_run["status"],
                "affected_chapters": affected_chapters,
                "items": [
                    {
                        "chapter_number": item["chapter_number"],
                        "action": item["action"],
                        "status": item["status"],
                        "error": item.get("error"),
                    }
                    for item in items
                ],
            }
        }

    # ── Batch Continuity Gate (v3.3) ─────────────────────────────

    def run_batch_continuity_gate(self, run_id: str) -> dict[str, Any]:
        """Run continuity gate for a batch production run.

        Args:
            run_id: Production run ID.

        Returns:
            Dict with ok, error, data containing gate status and summary.
        """
        import json as json_mod

        # 1. Get production run
        run = self.repo.get_production_run(run_id)
        if not run:
            return {"ok": False, "error": f"Production run {run_id} not found", "data": {}}

        project_id = run["project_id"]
        from_chapter = run["from_chapter"]
        to_chapter = run["to_chapter"]

        # 2. Run continuity check via existing sidecar method
        check_result = self.run_continuity_check(project_id, from_chapter, to_chapter)

        # 3. Calculate gate status from check result
        if not check_result.get("ok"):
            # Continuity checker execution failed
            gate_status = "error"
            issue_count = 0
            warning_count = 0
            blocking_issues = []
            report_id = None
            summary = f"Continuity check execution failed: {check_result.get('error', 'unknown')}"
        else:
            report_data = check_result.get("data", {})
            report = report_data.get("report", {})
            report_id = report_data.get("report_id")
            issues = report.get("issues", [])

            # Extract blocking (error severity) and warning issues
            blocking_issues = [
                {
                    "chapter_range": i.get("chapter_range", ""),
                    "issue_type": i.get("issue_type", ""),
                    "severity": i.get("severity", ""),
                    "description": i.get("description", ""),
                }
                for i in issues
                if i.get("severity") == "error"
            ]
            warning_issues = [
                i for i in issues if i.get("severity") == "warning"
            ]

            issue_count = len(blocking_issues) + len(warning_issues)
            warning_count = len(warning_issues)

            # Synthetic blocking issues for core consistency flags
            if report.get("state_card_consistency") is False:
                synth = {
                    "chapter_range": f"{from_chapter}-{to_chapter}",
                    "issue_type": "state_card",
                    "severity": "error",
                    "description": "状态卡连续性不一致",
                }
                if synth not in blocking_issues:
                    blocking_issues.append(synth)
                    issue_count += 1
            if report.get("character_consistency") is False:
                synth = {
                    "chapter_range": f"{from_chapter}-{to_chapter}",
                    "issue_type": "character",
                    "severity": "error",
                    "description": "角色一致性不一致",
                }
                if synth not in blocking_issues:
                    blocking_issues.append(synth)
                    issue_count += 1
            if report.get("plot_consistency") is False:
                synth = {
                    "chapter_range": f"{from_chapter}-{to_chapter}",
                    "issue_type": "plot",
                    "severity": "error",
                    "description": "伏笔一致性不一致",
                }
                if synth not in blocking_issues:
                    blocking_issues.append(synth)
                    issue_count += 1

            # Determine gate status
            if blocking_issues:
                gate_status = "failed"
            elif warning_count > 0:
                gate_status = "warning"
            else:
                gate_status = "passed"

            summary = report.get("summary", "连续性检查完成")

        # 4. Save gate result
        gate_id = self.repo.save_batch_continuity_gate(
            run_id=run_id,
            project_id=project_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
            continuity_report_id=str(report_id) if report_id else None,
            status=gate_status,
            issue_count=issue_count,
            warning_count=warning_count,
            blocking_issues_json=json_mod.dumps(blocking_issues, ensure_ascii=False),
            summary=summary,
        )

        return {
            "ok": True,
            "error": None,
            "data": {
                "run_id": run_id,
                "gate_id": gate_id,
                "status": gate_status,
                "report_id": report_id,
                "issue_count": issue_count,
                "blocking_issues": blocking_issues,
                "summary": summary,
            },
        }

    def get_batch_continuity_gate_status(self, run_id: str) -> dict[str, Any]:
        """Get the latest continuity gate status for a production run.

        Args:
            run_id: Production run ID.

        Returns:
            Dict with ok, error, data containing gate info.
        """
        import json as json_mod

        run = self.repo.get_production_run(run_id)
        if not run:
            return {"ok": False, "error": f"Production run {run_id} not found", "data": {}}

        gate = self.repo.get_latest_batch_continuity_gate(run_id)
        if not gate:
            return {
                "ok": True,
                "error": None,
                "data": {
                    "run_id": run_id,
                    "gate": None,
                    "gate_status": "not_run",
                },
            }

        blocking_issues = json_mod.loads(gate.get("blocking_issues_json", "[]"))

        return {
            "ok": True,
            "error": None,
            "data": {
                "run_id": run_id,
                "gate": {
                    "id": gate["id"],
                    "status": gate["status"],
                    "issue_count": gate.get("issue_count", 0),
                    "blocking_issues": blocking_issues,
                    "summary": gate.get("summary"),
                },
                "gate_status": gate["status"],
            },
        }

    def can_approve_batch(self, run_id: str) -> dict[str, Any]:
        """Check whether a batch production run can be approved.

        Args:
            run_id: Production run ID.

        Returns:
            Dict with ok (can approve), error, data.
        """
        run = self.repo.get_production_run(run_id)
        if not run:
            return {"ok": False, "error": f"Production run {run_id} not found", "data": {}}

        from_chapter = run.get("from_chapter", 1)
        to_chapter = run.get("to_chapter", 1)

        # Single-chapter batch: gate not required, can approve
        if from_chapter == to_chapter:
            gate = self.repo.get_latest_batch_continuity_gate(run_id)
            return {
                "ok": True,
                "error": None,
                "data": {
                    "gate_required": False,
                    "gate_status": gate["status"] if gate else "not_run",
                    "run_id": run_id,
                },
            }

        # Multi-chapter batch: gate required
        gate = self.repo.get_latest_batch_continuity_gate(run_id)
        if not gate:
            return {
                "ok": False,
                "error": "Batch continuity gate has not been run; approve is blocked",
                "data": {"gate_required": True, "gate_status": "not_run", "run_id": run_id},
            }

        gate_status = gate["status"]
        if gate_status in ("failed", "error"):
            return {
                "ok": False,
                "error": f"Batch continuity gate {gate_status}; approve is blocked",
                "data": {"gate_required": True, "gate_status": gate_status, "run_id": run_id},
            }

        # passed or warning: allow
        return {
            "ok": True,
            "error": None,
            "data": {"gate_required": True, "gate_status": gate_status, "run_id": run_id},
        }

    # ── Production Queue (v3.4) ─────────────────────────────────────

    def enqueue_batch(
        self,
        project_id: str,
        from_chapter: int,
        to_chapter: int,
        priority: int = 100,
        max_attempts: int = 3,
        timeout_minutes: int = 120,
        max_chapters: int = 50,
    ) -> dict[str, Any]:
        """Enqueue a batch production request.

        Args:
            project_id: Project identifier.
            from_chapter: Starting chapter number (inclusive).
            to_chapter: Ending chapter number (inclusive).
            priority: Queue priority (lower = higher priority).
            max_attempts: Maximum retry attempts.
            timeout_minutes: Timeout in minutes for running items.
            max_chapters: Maximum allowed chapter range (guard).

        Returns:
            Dict with ok, error, data.
        """
        # Guard: from_chapter <= to_chapter
        if from_chapter > to_chapter:
            return {
                "ok": False,
                "error": f"from_chapter ({from_chapter}) must be <= to_chapter ({to_chapter})",
                "data": {},
            }

        # Guard: max chapters
        chapter_count = to_chapter - from_chapter + 1
        if chapter_count > max_chapters:
            return {
                "ok": False,
                "error": f"Chapter range ({chapter_count}) exceeds max_chapters ({max_chapters})",
                "data": {},
            }

        # Verify project exists
        project = self.repo.get_project(project_id)
        if not project:
            return {
                "ok": False,
                "error": f"Project '{project_id}' not found",
                "data": {},
            }

        # Create queue item
        queue_id = self.repo.create_queue_item(
            project_id=project_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
            priority=priority,
            max_attempts=max_attempts,
            timeout_minutes=timeout_minutes,
        )

        if not queue_id:
            return {
                "ok": False,
                "error": "Failed to create queue item",
                "data": {},
            }

        # Record enqueued event
        event_id = self.repo.record_queue_event(
            queue_id=queue_id,
            event_type="enqueued",
            to_status="pending",
            message=f"Batch enqueued: {project_id} chapters {from_chapter}-{to_chapter}",
        )
        if event_id is None:
            # Event write failed - this is a critical error
            return {
                "ok": False,
                "error": f"Queue item created but failed to record 'enqueued' event for {queue_id}",
                "data": {"queue_id": queue_id, "status": "pending"},
            }

        return {
            "ok": True,
            "error": None,
            "data": {
                "queue_id": queue_id,
                "status": "pending",
            },
        }

    def run_queue_once(self) -> dict[str, Any]:
        """Execute the next pending queue item.

        - Marks timed out items first.
        - Claims the next pending item (priority ASC, created_at ASC).
        - Calls run_batch() for the item's chapter range.
        - Updates queue item status based on run_batch result.
        - Records queue events for every status change.

        Returns:
            Dict with ok, error, data.
        """
        # Step 1: Mark timed out items (with event recording)
        timeout_result = self.mark_queue_timeouts()
        if not timeout_result.get("ok"):
            return {
                "ok": False,
                "error": f"Failed to mark queue timeouts: {timeout_result.get('error')}",
                "data": timeout_result.get("data", {}),
            }

        # Step 2: Claim next pending item
        item = self.repo.claim_next_queue_item()
        if not item:
            return {
                "ok": True,
                "error": None,
                "data": {"status": "idle", "message": "No pending queue items"},
            }

        queue_id = item["id"]
        project_id = item["project_id"]
        from_chapter = item["from_chapter"]
        to_chapter = item["to_chapter"]

        # Record started event
        event_id = self.repo.record_queue_event(
            queue_id=queue_id,
            event_type="started",
            from_status="pending",
            to_status="running",
            message=f"Queue item started: {project_id} chapters {from_chapter}-{to_chapter}",
        )
        if event_id is None:
            # Event write failed - rollback status change
            self.repo.update_queue_item(
                queue_id,
                status="pending",
                clear_locked_at=True,
                clear_started_at=True,
            )
            return {
                "ok": False,
                "error": f"Failed to record 'started' event for queue item {queue_id}",
                "data": {"queue_id": queue_id},
            }

        # Step 3: Execute run_batch (reuse existing batch production logic)
        try:
            batch_result = self.run_batch(project_id, from_chapter, to_chapter)
        except Exception as e:
            logger.error(f"run_batch exception for queue item {queue_id}: {e}")
            batch_result = {"ok": False, "error": str(e), "data": {}}

        # Step 4: Save production_run_id
        production_run_id = batch_result.get("data", {}).get("run_id")
        if production_run_id:
            ok = self.repo.update_queue_item(queue_id, production_run_id=production_run_id)
            if not ok:
                # Critical: production_run_id write failed
                # Mark as failed to avoid orphaned state
                failed_ok = self.repo.update_queue_item(
                    queue_id,
                    status="failed",
                    last_error="Failed to save production_run_id",
                    completed_at=self._now_iso(),
                )
                if not failed_ok:
                    return {
                        "ok": False,
                        "error": f"Failed to save production_run_id and failed to mark queue item {queue_id} as failed",
                        "data": {"queue_id": queue_id, "production_run_id": production_run_id},
                    }
                # Record failed event
                event_id = self.repo.record_queue_event(
                    queue_id=queue_id,
                    event_type="failed",
                    from_status="running",
                    to_status="failed",
                    message="Failed to save production_run_id",
                )
                if event_id is None:
                    return {
                        "ok": False,
                        "error": f"Queue item {queue_id} marked failed but failed to record 'failed' event",
                        "data": {"queue_id": queue_id, "status": "failed", "production_run_id": production_run_id},
                    }
                return {
                    "ok": False,
                    "error": f"Failed to save production_run_id for queue item {queue_id}",
                    "data": {"queue_id": queue_id, "production_run_id": production_run_id},
                }

        # Step 5: Determine result and update status
        if batch_result.get("ok"):
            # Success: mark completed
            ok = self.repo.update_queue_item(
                queue_id,
                status="completed",
                completed_at=self._now_iso(),
                last_error="",
            )
            if not ok:
                return {
                    "ok": False,
                    "error": f"Failed to mark queue item {queue_id} as completed",
                    "data": {"queue_id": queue_id},
                }

            event_id = self.repo.record_queue_event(
                queue_id=queue_id,
                event_type="completed",
                from_status="running",
                to_status="completed",
                message="Queue item completed successfully",
            )
            if event_id is None:
                # Event write failed - status already committed, return error
                return {
                    "ok": False,
                    "error": f"Queue item {queue_id} completed but failed to record 'completed' event",
                    "data": {"queue_id": queue_id, "status": "completed", "production_run_id": production_run_id},
                }

            return {
                "ok": True,
                "error": None,
                "data": {
                    "queue_id": queue_id,
                    "status": "completed",
                    "production_run_id": production_run_id,
                },
            }
        else:
            # Failure: check if blocked (business error) or hard error
            error_msg = batch_result.get("error", "Unknown error")
            ok = self.repo.update_queue_item(
                queue_id,
                status="failed",
                last_error=error_msg,
                completed_at=self._now_iso(),
            )
            if not ok:
                return {
                    "ok": False,
                    "error": f"Failed to mark queue item {queue_id} as failed",
                    "data": {"queue_id": queue_id},
                }

            event_id = self.repo.record_queue_event(
                queue_id=queue_id,
                event_type="failed",
                from_status="running",
                to_status="failed",
                message=f"Queue item failed: {error_msg}",
            )
            if event_id is None:
                # Event write failed - status already committed, return error
                return {
                    "ok": False,
                    "error": f"Queue item {queue_id} failed but failed to record 'failed' event",
                    "data": {"queue_id": queue_id, "status": "failed", "production_run_id": production_run_id},
                }

            return {
                "ok": False,
                "error": error_msg,
                "data": {
                    "queue_id": queue_id,
                    "status": "failed",
                    "production_run_id": production_run_id,
                },
            }

    def get_queue_status(
        self,
        project_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Get production queue status.

        Args:
            project_id: Optional project ID filter.
            status: Optional status filter.

        Returns:
            Dict with ok, error, data containing items list.
        """
        items = self.repo.list_queue_items(project_id=project_id, status=status)

        items_data = []
        for item in items:
            items_data.append({
                "queue_id": item["id"],
                "project_id": item["project_id"],
                "from_chapter": item["from_chapter"],
                "to_chapter": item["to_chapter"],
                "status": item["status"],
                "priority": item["priority"],
                "attempt_count": item.get("attempt_count", 0),
                "max_attempts": item.get("max_attempts", 3),
                "last_error": item.get("last_error"),
                "production_run_id": item.get("production_run_id"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
            })

        return {
            "ok": True,
            "error": None,
            "data": {"items": items_data},
        }

    def pause_queue_item(self, queue_id: str) -> dict[str, Any]:
        """Pause a production queue item.

        Only pending and running items can be paused.
        Pausing a running item does not interrupt the current run_batch,
        but prevents it from being claimed again.

        Args:
            queue_id: Queue item identifier.

        Returns:
            Dict with ok, error, data.
        """
        item = self.repo.get_queue_item(queue_id)
        if not item:
            return {
                "ok": False,
                "error": f"Queue item '{queue_id}' not found",
                "data": {},
            }

        current_status = item["status"]

        # Validate allowed status transitions
        if current_status not in ("pending", "running"):
            return {
                "ok": False,
                "error": f"Cannot pause queue item in status '{current_status}'. Only 'pending' or 'running' items can be paused.",
                "data": {},
            }

        ok = self.repo.update_queue_item(queue_id, status="paused")
        if not ok:
            return {
                "ok": False,
                "error": f"Failed to pause queue item '{queue_id}'",
                "data": {},
            }

        event_id = self.repo.record_queue_event(
            queue_id=queue_id,
            event_type="paused",
            from_status=current_status,
            to_status="paused",
            message=f"Queue item paused from status '{current_status}'",
        )
        if event_id is None:
            # Event write failed - status already committed, return error
            return {
                "ok": False,
                "error": f"Queue item '{queue_id}' paused but failed to record 'paused' event",
                "data": {"queue_id": queue_id, "status": "paused"},
            }

        return {
            "ok": True,
            "error": None,
            "data": {"queue_id": queue_id, "status": "paused"},
        }

    def resume_queue_item(self, queue_id: str) -> dict[str, Any]:
        """Resume a paused queue item back to pending.

        Args:
            queue_id: Queue item identifier.

        Returns:
            Dict with ok, error, data.
        """
        item = self.repo.get_queue_item(queue_id)
        if not item:
            return {
                "ok": False,
                "error": f"Queue item '{queue_id}' not found",
                "data": {},
            }

        current_status = item["status"]

        # Validate allowed status transitions
        if current_status != "paused":
            return {
                "ok": False,
                "error": f"Cannot resume queue item in status '{current_status}'. Only 'paused' items can be resumed.",
                "data": {},
            }

        ok = self.repo.update_queue_item(queue_id, status="pending")
        if not ok:
            return {
                "ok": False,
                "error": f"Failed to resume queue item '{queue_id}'",
                "data": {},
            }

        event_id = self.repo.record_queue_event(
            queue_id=queue_id,
            event_type="resumed",
            from_status="paused",
            to_status="pending",
            message="Queue item resumed to pending",
        )
        if event_id is None:
            # Event write failed - status already committed, return error
            return {
                "ok": False,
                "error": f"Queue item '{queue_id}' resumed but failed to record 'resumed' event",
                "data": {"queue_id": queue_id, "status": "pending"},
            }

        return {
            "ok": True,
            "error": None,
            "data": {"queue_id": queue_id, "status": "pending"},
        }

    def retry_queue_item(self, queue_id: str) -> dict[str, Any]:
        """Retry a failed or timed-out queue item.

        Increments attempt_count and resets status to pending.
        Clears last_error. Preserves production_run_id for audit.

        Args:
            queue_id: Queue item identifier.

        Returns:
            Dict with ok, error, data.
        """
        item = self.repo.get_queue_item(queue_id)
        if not item:
            return {
                "ok": False,
                "error": f"Queue item '{queue_id}' not found",
                "data": {},
            }

        current_status = item["status"]

        # Validate allowed status transitions
        if current_status not in ("failed", "timeout"):
            return {
                "ok": False,
                "error": f"Cannot retry queue item in status '{current_status}'. Only 'failed' or 'timeout' items can be retried.",
                "data": {},
            }

        # Check max_attempts
        attempt_count = item.get("attempt_count", 0)
        max_attempts = item.get("max_attempts", 3)
        if attempt_count >= max_attempts:
            return {
                "ok": False,
                "error": f"Queue item '{queue_id}' has reached max attempts ({max_attempts})",
                "data": {},
            }

        # Update: increment attempt_count, reset to pending, clear error
        new_attempt = attempt_count + 1
        ok = self.repo.update_queue_item(
            queue_id,
            status="pending",
            attempt_count=new_attempt,
            last_error="",
            clear_locked_at=True,
            clear_started_at=True,
            clear_completed_at=True,
        )
        if not ok:
            return {
                "ok": False,
                "error": f"Failed to retry queue item '{queue_id}'",
                "data": {},
            }

        event_id = self.repo.record_queue_event(
            queue_id=queue_id,
            event_type="retried",
            from_status=current_status,
            to_status="pending",
            message=f"Queue item retried (attempt {new_attempt}/{max_attempts})",
        )
        if event_id is None:
            # Event write failed - status already committed, return error
            return {
                "ok": False,
                "error": f"Queue item '{queue_id}' retried but failed to record 'retried' event",
                "data": {"queue_id": queue_id, "status": "pending", "attempt_count": new_attempt},
            }

        return {
            "ok": True,
            "error": None,
            "data": {
                "queue_id": queue_id,
                "status": "pending",
                "attempt_count": new_attempt,
            },
        }

    def mark_queue_timeouts(self) -> dict[str, Any]:
        """Manually scan and mark timed-out queue items.

        Items with status 'running' whose locked_at exceeds their
        per-item timeout_minutes are marked as 'timeout'.

        For each timed-out item, a 'timeout' event is written to
        production_queue_events.

        Returns:
            Dict with ok, error, data containing count of timed-out items.
            If any event write fails, returns ok=false with error details.
        """
        timed_out_ids = self.repo.mark_timed_out_queue_items()

        # Write timeout events for each timed-out item
        event_failures = []
        for queue_id in timed_out_ids:
            event_id = self.repo.record_queue_event(
                queue_id=queue_id,
                event_type="timeout",
                from_status="running",
                to_status="timeout",
                message="Queue item timed out",
            )
            if event_id is None:
                event_failures.append(queue_id)

        if event_failures:
            return {
                "ok": False,
                "error": f"Failed to write timeout events for items: {event_failures}",
                "data": {"timed_out_count": len(timed_out_ids), "event_failures": event_failures},
            }

        return {
            "ok": True,
            "error": None,
            "data": {"timed_out_count": len(timed_out_ids)},
        }

    # ── Queue Runtime Hardening (v3.5) ───────────────────────────────

    def get_queue_events(self, queue_id: str) -> dict[str, Any]:
        """Get all events for a queue item.

        Args:
            queue_id: Queue item identifier.

        Returns:
            Dict with ok, error, data containing events list.
        """
        # Verify queue item exists
        item = self.repo.get_queue_item(queue_id)
        if not item:
            return {
                "ok": False,
                "error": f"Queue item '{queue_id}' not found",
                "data": {},
            }

        # Get events
        events = self.repo.get_queue_events(queue_id)

        events_data = []
        for event in events:
            events_data.append({
                "event_type": event.get("event_type"),
                "from_status": event.get("from_status"),
                "to_status": event.get("to_status"),
                "message": event.get("message"),
                "created_at": event.get("created_at"),
            })

        return {
            "ok": True,
            "error": None,
            "data": {
                "queue_id": queue_id,
                "events": events_data,
            },
        }

    def cancel_queue_item(self, queue_id: str, reason: str | None = None) -> dict[str, Any]:
        """Cancel a queue item.

        Allowed for: pending, paused, running, failed, timeout.
        Not allowed for: completed, cancelled.

        Args:
            queue_id: Queue item identifier.
            reason: Optional cancellation reason.

        Returns:
            Dict with ok, error, data.
        """
        item = self.repo.get_queue_item(queue_id)
        if not item:
            return {
                "ok": False,
                "error": f"Queue item '{queue_id}' not found",
                "data": {},
            }

        current_status = item["status"]

        # Validate allowed status transitions
        if current_status in ("completed", "cancelled"):
            return {
                "ok": False,
                "error": f"Cannot cancel queue item in status '{current_status}'",
                "data": {},
            }

        # Update status
        ok = self.repo.update_queue_item(
            queue_id,
            status="cancelled",
            last_error=reason,
            completed_at=self._now_iso(),
        )
        if not ok:
            return {
                "ok": False,
                "error": f"Failed to cancel queue item '{queue_id}'",
                "data": {},
            }

        # Record event
        event_id = self.repo.record_queue_event(
            queue_id=queue_id,
            event_type="cancelled",
            from_status=current_status,
            to_status="cancelled",
            message=reason or "Queue item cancelled",
        )
        if event_id is None:
            # Event write failed - status already committed, return error
            return {
                "ok": False,
                "error": f"Queue item '{queue_id}' cancelled but failed to record 'cancelled' event",
                "data": {"queue_id": queue_id, "status": "cancelled"},
            }

        return {
            "ok": True,
            "error": None,
            "data": {"queue_id": queue_id, "status": "cancelled"},
        }

    def recover_queue_item(self, queue_id: str, force: bool = False) -> dict[str, Any]:
        """Recover a stuck running queue item.

        Only allowed for 'running' status.
        Must satisfy stuck condition: locked_at exceeds timeout_minutes, or use --force.

        Args:
            queue_id: Queue item identifier.
            force: Force recovery even if not stuck.

        Returns:
            Dict with ok, error, data.
        """
        item = self.repo.get_queue_item(queue_id)
        if not item:
            return {
                "ok": False,
                "error": f"Queue item '{queue_id}' not found",
                "data": {},
            }

        current_status = item["status"]

        # Validate allowed status transitions
        if current_status != "running":
            return {
                "ok": False,
                "error": f"Cannot recover queue item in status '{current_status}'. Only 'running' items can be recovered.",
                "data": {},
            }

        # Check stuck condition
        locked_at = item.get("locked_at")
        timeout_minutes = item.get("timeout_minutes", 120)

        if not force and locked_at:
            from datetime import datetime, timezone, timedelta
            try:
                # Handle Z suffix and naive timestamps
                locked_str = locked_at.replace("Z", "+00:00")
                locked_time = datetime.fromisoformat(locked_str)
                # If naive (no timezone), compare with naive now (local time)
                # If aware, compare with aware now (UTC)
                if locked_time.tzinfo is None:
                    now = datetime.now()
                else:
                    now = datetime.now(timezone.utc)
                elapsed = (now - locked_time).total_seconds() / 60
            except (ValueError, TypeError):
                return {
                    "ok": False,
                    "error": f"Cannot parse locked_at timestamp '{locked_at}' for queue item '{queue_id}'",
                    "data": {},
                }

            if elapsed < timeout_minutes:
                return {
                    "ok": False,
                    "error": f"Queue item '{queue_id}' is not stuck (elapsed {elapsed:.1f}min < timeout {timeout_minutes}min). Use --force to override.",
                    "data": {"elapsed_minutes": elapsed, "timeout_minutes": timeout_minutes},
                }

        # Update status: running → pending, clear timestamps
        ok = self.repo.update_queue_item(
            queue_id,
            status="pending",
            clear_locked_at=True,
            clear_started_at=True,
            clear_completed_at=True,
        )
        if not ok:
            return {
                "ok": False,
                "error": f"Failed to recover queue item '{queue_id}'",
                "data": {},
            }

        # Record event
        message = "Queue item recovered"
        if force:
            message += " (forced)"

        metadata = json.dumps({"force": force})
        event_id = self.repo.record_queue_event(
            queue_id=queue_id,
            event_type="recovered",
            from_status="running",
            to_status="pending",
            message=message,
            metadata_json=metadata,
        )
        if event_id is None:
            # Event write failed - status already committed, return error
            return {
                "ok": False,
                "error": f"Queue item '{queue_id}' recovered but failed to record 'recovered' event",
                "data": {"queue_id": queue_id, "status": "pending"},
            }

        return {
            "ok": True,
            "error": None,
            "data": {"queue_id": queue_id, "status": "pending"},
        }

    def doctor_queue_item(self, queue_id: str) -> dict[str, Any]:
        """Diagnose a queue item.

        Performs various checks and reports issues without modifying state.

        Args:
            queue_id: Queue item identifier.

        Returns:
            Dict with ok, error, data containing checks and diagnostics.
        """
        import json as json_mod

        item = self.repo.get_queue_item(queue_id)
        if not item:
            return {
                "ok": False,
                "error": f"Queue item '{queue_id}' not found",
                "data": {},
            }

        checks = []
        status = item["status"]
        production_run_id = item.get("production_run_id")

        # Check 1: queue_item_exists
        checks.append({"name": "queue_item_exists", "pass": True})

        # Check 2: has_events
        events = self.repo.get_queue_events(queue_id)
        checks.append({"name": "has_events", "pass": len(events) > 0})

        # Check 3: status_has_valid_transition
        # All current statuses are valid states
        valid_statuses = {"pending", "running", "paused", "completed", "failed", "timeout", "cancelled"}
        checks.append({"name": "status_has_valid_transition", "pass": status in valid_statuses})

        # Check 4: running_has_locked_at
        if status == "running":
            checks.append({"name": "running_has_locked_at", "pass": item.get("locked_at") is not None})
        else:
            checks.append({"name": "running_has_locked_at", "pass": True, "message": "N/A (not running)"})

        # Check 5: completed_has_production_run
        if status == "completed":
            has_pr = production_run_id is not None
            checks.append({
                "name": "completed_has_production_run",
                "pass": has_pr,
                "message": None if has_pr else "Completed item missing production_run_id",
            })
        else:
            checks.append({"name": "completed_has_production_run", "pass": True, "message": "N/A (not completed)"})

        # Check 6: failed_has_error
        if status == "failed":
            has_error = item.get("last_error") is not None and item.get("last_error") != ""
            checks.append({
                "name": "failed_has_error",
                "pass": has_error,
                "message": None if has_error else "Failed item missing error message",
            })
        else:
            checks.append({"name": "failed_has_error", "pass": True, "message": "N/A (not failed)"})

        # Check 7: production_run_exists
        if production_run_id:
            production_run = self.repo.get_production_run(production_run_id)
            checks.append({
                "name": "production_run_exists",
                "pass": production_run is not None,
                "message": None if production_run else f"production_run '{production_run_id}' not found",
            })
        else:
            checks.append({"name": "production_run_exists", "pass": True, "message": "N/A (no production_run_id)"})

        # Check 8: production_run_items_exist
        if production_run_id:
            items = self.repo.get_production_run_items(production_run_id)
            checks.append({
                "name": "production_run_items_exist",
                "pass": len(items) > 0,
                "message": None if items else f"production_run '{production_run_id}' has no items",
            })
        else:
            checks.append({"name": "production_run_items_exist", "pass": True, "message": "N/A (no production_run_id)"})

        # Check 9: workflow_runs_exist
        # Get workflow runs for the project
        project_id = item.get("project_id")
        from_chapter = item.get("from_chapter")
        to_chapter = item.get("to_chapter")

        if project_id and from_chapter is not None and to_chapter is not None:
            workflow_runs = []
            for ch in range(from_chapter, to_chapter + 1):
                runs = self.repo.get_workflow_runs_for_project(project_id, chapter_number=ch, limit=1)
                workflow_runs.extend(runs)

            checks.append({
                "name": "workflow_runs_exist",
                "pass": len(workflow_runs) > 0 if status == "completed" else True,
                "message": None if workflow_runs or status != "completed" else "No workflow runs found for completed item",
            })
        else:
            checks.append({"name": "workflow_runs_exist", "pass": True, "message": "N/A"})

        return {
            "ok": True,
            "error": None,
            "data": {
                "queue_id": queue_id,
                "status": status,
                "production_run_id": production_run_id,
                "checks": checks,
                "recent_error": item.get("last_error"),
            },
        }

    def run_queue(self, limit: int = 1) -> dict[str, Any]:
        """Execute multiple queue items sequentially.

        Args:
            limit: Maximum number of items to execute (default: 1).

        Returns:
            Dict with ok, error, data containing runs list and execution summary.
        """
        if limit < 1:
            return {
                "ok": False,
                "error": "limit must be >= 1",
                "data": {},
            }

        runs = []
        executed = 0
        stopped_reason = None

        for i in range(limit):
            result = self.run_queue_once()
            runs.append(result)

            # Check for idle (no pending items)
            if result.get("ok") and result.get("data", {}).get("status") == "idle":
                stopped_reason = "idle"
                break

            # Check for failure
            if not result.get("ok"):
                stopped_reason = "failure"
                break

            executed += 1

        return {
            "ok": True,
            "error": None,
            "data": {
                "limit": limit,
                "executed": executed,
                "stopped_reason": stopped_reason,
                "runs": runs,
            },
        }
