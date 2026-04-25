"""Batch revision dispatch — plan, run, status."""

from __future__ import annotations

import json
import logging
from typing import Any

from .base import LEGAL_RESUME_STATUSES

logger = logging.getLogger(__name__)

class RevisionDispatchMixin:
    """Batch revision dispatch — plan, run, status."""

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
