"""Batch production dispatch — run, status, review."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

class BatchDispatchMixin:
    """Batch production dispatch — run, status, review."""

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
