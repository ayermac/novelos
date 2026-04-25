"""Serial plan dispatch — create, enqueue, advance, pause, resume, cancel."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

class SerialDispatchMixin:
    """Serial plan dispatch — create, enqueue, advance, pause, resume, cancel."""

    def create_serial_plan(
        self,
        project_id: str,
        name: str,
        start_chapter: int,
        target_chapter: int,
        batch_size: int,
    ) -> dict[str, Any]:
        """Create a new serial plan.

        Args:
            project_id: Project identifier.
            name: Human-readable name for the plan.
            start_chapter: Starting chapter number.
            target_chapter: Target chapter number to reach.
            batch_size: Number of chapters per batch.

        Returns:
            Dict with ok, error, data containing serial_plan_id and status.
        """
        # Validate parameters
        if start_chapter > target_chapter:
            return {
                "ok": False,
                "error": f"start_chapter ({start_chapter}) cannot be greater than target_chapter ({target_chapter})",
                "data": {},
            }

        if batch_size < 1:
            return {
                "ok": False,
                "error": "batch_size must be at least 1",
                "data": {},
            }

        # Check project exists
        project = self.repo.get_project(project_id)
        if not project:
            return {
                "ok": False,
                "error": f"Project '{project_id}' not found",
                "data": {},
            }

        # Create serial plan
        serial_plan_id = self.repo.create_serial_plan(
            project_id=project_id,
            name=name,
            start_chapter=start_chapter,
            target_chapter=target_chapter,
            batch_size=batch_size,
        )

        # Record event - MUST succeed for auditability
        event_id = self.repo.record_serial_plan_event(
            serial_plan_id=serial_plan_id,
            event_type="created",
            to_status="active",
            message=f"Serial plan created: {name}",
        )
        if event_id is None:
            # Rollback: delete the created plan
            rollback_ok = self.repo.update_serial_plan(serial_plan_id, status="cancelled")
            if not rollback_ok:
                return {
                    "ok": False,
                    "error": "Failed to record serial plan creation event; AND plan cancellation failed",
                    "data": {"serial_plan_id": serial_plan_id, "compensation_failed": True},
                }
            return {
                "ok": False,
                "error": "Failed to record serial plan creation event",
                "data": {"serial_plan_id": serial_plan_id},
            }

        return {
            "ok": True,
            "error": None,
            "data": {
                "serial_plan_id": serial_plan_id,
                "status": "active",
                "current_chapter": start_chapter,
            },
        }

    def get_serial_status(self, serial_plan_id: str) -> dict[str, Any]:
        """Get serial plan status.

        Args:
            serial_plan_id: Serial plan identifier.

        Returns:
            Dict with ok, error, data containing plan details and events.
        """
        plan = self.repo.get_serial_plan(serial_plan_id)
        if not plan:
            return {
                "ok": False,
                "error": f"Serial plan '{serial_plan_id}' not found",
                "data": {},
            }

        events = self.repo.get_serial_plan_events(serial_plan_id)

        return {
            "ok": True,
            "error": None,
            "data": {
                "serial_plan_id": plan["id"],
                "project_id": plan["project_id"],
                "name": plan["name"],
                "status": plan["status"],
                "current_chapter": plan["current_chapter"],
                "target_chapter": plan["target_chapter"],
                "batch_size": plan["batch_size"],
                "completed_chapters": plan["completed_chapters"],
                "current_queue_id": plan.get("current_queue_id"),
                "current_production_run_id": plan.get("current_production_run_id"),
                "events": events,
            },
        }

    def enqueue_serial_next(self, serial_plan_id: str) -> dict[str, Any]:
        """Enqueue the next batch for a serial plan.

        Only allowed for 'active' status.

        Args:
            serial_plan_id: Serial plan identifier.

        Returns:
            Dict with ok, error, data containing queue_id and range.
        """
        plan = self.repo.get_serial_plan(serial_plan_id)
        if not plan:
            return {
                "ok": False,
                "error": f"Serial plan '{serial_plan_id}' not found",
                "data": {},
            }

        if plan["status"] != "active":
            return {
                "ok": False,
                "error": f"Cannot enqueue-next for serial plan in status '{plan['status']}'. Only 'active' is allowed.",
                "data": {},
            }

        # Calculate next batch range
        current = plan["current_chapter"]
        target = plan["target_chapter"]
        batch_size = plan["batch_size"]

        from_chapter = current
        to_chapter = min(current + batch_size - 1, target)

        # Enqueue batch using v3.4 enqueue_batch
        result = self.enqueue_batch(
            project_id=plan["project_id"],
            from_chapter=from_chapter,
            to_chapter=to_chapter,
        )

        if not result.get("ok"):
            return result

        queue_id = result["data"]["queue_id"]

        # Update serial plan
        ok = self.repo.update_serial_plan(
            serial_plan_id,
            status="waiting_review",
            current_queue_id=queue_id,
        )

        if not ok:
            # R3: Compensate - cancel the orphan queue item
            cancel_ok = self.repo.update_queue_item(queue_id, status="cancelled")
            if not cancel_ok:
                return {
                    "ok": False,
                    "error": "Failed to update serial plan after enqueue; AND queue compensation failed",
                    "data": {"queue_id": queue_id, "compensation_failed": True},
                }

            event_id = self.repo.record_queue_event(
                queue_id=queue_id,
                event_type="cancelled",
                to_status="cancelled",
                message="Serial plan update failed, queue item cancelled",
            )
            if event_id is None:
                return {
                    "ok": False,
                    "error": "Failed to update serial plan after enqueue; AND queue compensation event failed",
                    "data": {"queue_id": queue_id, "compensation_failed": True},
                }

            return {
                "ok": False,
                "error": "Failed to update serial plan after enqueue",
                "data": {"queue_id": queue_id},
            }

        # Record event - MUST succeed for auditability
        event_id = self.repo.record_serial_plan_event(
            serial_plan_id=serial_plan_id,
            event_type="enqueued",
            from_status="active",
            to_status="waiting_review",
            message=f"Enqueued chapters {from_chapter}-{to_chapter}",
            metadata_json=json.dumps({"queue_id": queue_id, "from_chapter": from_chapter, "to_chapter": to_chapter}),
        )
        if event_id is None:
            # Rollback: revert serial plan status and cancel queue item
            rollback_ok = self.repo.update_serial_plan(serial_plan_id, status="active", current_queue_id=None)
            cancel_ok = self.repo.update_queue_item(queue_id, status="cancelled")

            # Check compensation results
            compensation_errors = []
            if not rollback_ok:
                compensation_errors.append("serial plan rollback failed")
            if not cancel_ok:
                compensation_errors.append("queue cancel failed")

            # Record queue event if cancel succeeded
            if cancel_ok:
                queue_event_id = self.repo.record_queue_event(
                    queue_id=queue_id,
                    event_type="cancelled",
                    to_status="cancelled",
                    message="Serial plan event recording failed, queue item cancelled",
                )
                if queue_event_id is None:
                    compensation_errors.append("queue event failed")

            if compensation_errors:
                return {
                    "ok": False,
                    "error": f"Failed to record serial plan enqueue event; AND compensation failed: {', '.join(compensation_errors)}",
                    "data": {"queue_id": queue_id, "compensation_failed": True},
                }

            return {
                "ok": False,
                "error": "Failed to record serial plan enqueue event",
                "data": {"queue_id": queue_id},
            }

        return {
            "ok": True,
            "error": None,
            "data": {
                "queue_id": queue_id,
                "from_chapter": from_chapter,
                "to_chapter": to_chapter,
                "status": "waiting_review",
            },
        }

    def advance_serial_plan(
        self,
        serial_plan_id: str,
        decision: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Advance a serial plan based on human decision.

        Only allowed for 'waiting_review' status.

        Args:
            serial_plan_id: Serial plan identifier.
            decision: One of 'approve', 'request_changes', 'pause', 'cancel'.
            notes: Optional notes for the decision.

        Returns:
            Dict with ok, error, data containing new status.
        """
        plan = self.repo.get_serial_plan(serial_plan_id)
        if not plan:
            return {
                "ok": False,
                "error": f"Serial plan '{serial_plan_id}' not found",
                "data": {},
            }

        if plan["status"] != "waiting_review":
            return {
                "ok": False,
                "error": f"Cannot advance serial plan in status '{plan['status']}'. Only 'waiting_review' is allowed.",
                "data": {},
            }

        valid_decisions = {"approve", "request_changes", "pause", "cancel"}
        if decision not in valid_decisions:
            return {
                "ok": False,
                "error": f"Invalid decision '{decision}'. Must be one of: {', '.join(valid_decisions)}",
                "data": {},
            }

        # Handle non-approve decisions
        if decision == "request_changes":
            event_id = self.repo.record_serial_plan_event(
                serial_plan_id=serial_plan_id,
                event_type="request_changes",
                from_status="waiting_review",
                to_status="waiting_review",
                message=f"Changes requested: {notes or 'no notes'}",
            )
            if event_id is None:
                return {
                    "ok": False,
                    "error": "Failed to record request_changes event",
                    "data": {},
                }
            return {
                "ok": True,
                "error": None,
                "data": {"status": "waiting_review"},
            }

        if decision == "pause":
            ok = self.repo.update_serial_plan(serial_plan_id, status="paused")
            if not ok:
                return {
                    "ok": False,
                    "error": "Failed to pause serial plan",
                    "data": {},
                }
            event_id = self.repo.record_serial_plan_event(
                serial_plan_id=serial_plan_id,
                event_type="paused",
                from_status="waiting_review",
                to_status="paused",
                message=notes or "Serial plan paused",
            )
            if event_id is None:
                # Rollback: revert to waiting_review
                self.repo.update_serial_plan(serial_plan_id, status="waiting_review")
                return {
                    "ok": False,
                    "error": "Failed to record pause event",
                    "data": {},
                }
            return {
                "ok": True,
                "error": None,
                "data": {"status": "paused"},
            }

        if decision == "cancel":
            ok = self.repo.update_serial_plan(serial_plan_id, status="cancelled")
            if not ok:
                return {
                    "ok": False,
                    "error": "Failed to cancel serial plan",
                    "data": {},
                }
            event_id = self.repo.record_serial_plan_event(
                serial_plan_id=serial_plan_id,
                event_type="cancelled",
                from_status="waiting_review",
                to_status="cancelled",
                message=notes or "Serial plan cancelled",
            )
            if event_id is None:
                # Rollback: revert to waiting_review
                rollback_ok = self.repo.update_serial_plan(serial_plan_id, status="waiting_review")
                if not rollback_ok:
                    return {
                        "ok": False,
                        "error": "Failed to record cancel event; AND rollback failed",
                        "data": {"serial_plan_id": serial_plan_id, "compensation_failed": True},
                    }
                return {
                    "ok": False,
                    "error": "Failed to record cancel event",
                    "data": {"serial_plan_id": serial_plan_id},
                }
            return {
                "ok": True,
                "error": None,
                "data": {"status": "cancelled"},
            }

        # Handle approve decision
        # Check queue item exists and is completed
        queue_id = plan.get("current_queue_id")
        if not queue_id:
            return {
                "ok": False,
                "error": "No current queue item found for serial plan",
                "data": {},
            }

        queue_item = self.repo.get_queue_item(queue_id)
        if not queue_item:
            return {
                "ok": False,
                "error": f"Queue item '{queue_id}' not found",
                "data": {},
            }

        if queue_item.get("status") != "completed":
            return {
                "ok": False,
                "error": f"Queue item is not completed (status: {queue_item.get('status')})",
                "data": {},
            }

        # Check production_run_id exists
        production_run_id = queue_item.get("production_run_id")
        if not production_run_id:
            return {
                "ok": False,
                "error": "Queue item has no production_run_id",
                "data": {},
            }

        # Check production run status
        production_run = self.repo.get_production_run(production_run_id)
        if not production_run:
            return {
                "ok": False,
                "error": f"Production run '{production_run_id}' not found",
                "data": {},
            }

        run_status = production_run.get("status")
        # Allow approve for awaiting_review, completed, or approved statuses
        if run_status not in ("awaiting_review", "completed", "approved"):
            return {
                "ok": False,
                "error": f"Production run status '{run_status}' is not ready for approval",
                "data": {},
            }

        # Check continuity gate for multi-chapter batches
        from_chapter = queue_item.get("from_chapter")
        to_chapter = queue_item.get("to_chapter")
        if from_chapter and to_chapter and to_chapter > from_chapter:
            # Multi-chapter batch - continuity gate is REQUIRED
            gate = self.repo.get_latest_batch_continuity_gate(production_run_id)
            if not gate:
                return {
                    "ok": False,
                    "error": "Continuity gate not run for multi-chapter batch. Cannot approve without continuity check.",
                    "data": {"gate_status": "not_run"},
                }
            gate_status = gate.get("status")
            if gate_status not in ("passed", "warning"):
                return {
                    "ok": False,
                    "error": f"Continuity gate status '{gate_status}' does not allow approval. Must be 'passed' or 'warning'.",
                    "data": {"gate_status": gate_status},
                }

        # Calculate chapters completed in this batch
        chapters_in_batch = to_chapter - from_chapter + 1 if from_chapter and to_chapter else 1

        # Calculate new current_chapter
        new_current = plan["current_chapter"] + plan["batch_size"]
        if new_current > plan["target_chapter"]:
            new_current = plan["target_chapter"] + 1  # Exceeds target means completed

        new_completed = plan["completed_chapters"] + chapters_in_batch

        # Determine new status
        if new_current > plan["target_chapter"]:
            new_status = "completed"
        else:
            new_status = "active"

        # Update serial plan
        update_data = {
            "status": new_status,
            "current_chapter": new_current,
            "completed_chapters": new_completed,
            "current_queue_id": None,
            "current_production_run_id": production_run_id,
        }

        if new_status == "completed":
            from datetime import datetime
            update_data["completed_at"] = datetime.now().isoformat()

        ok = self.repo.update_serial_plan(serial_plan_id, **update_data)
        if not ok:
            return {
                "ok": False,
                "error": "Failed to update serial plan after approval",
                "data": {},
            }

        # Record event - MUST succeed for auditability
        event_id = self.repo.record_serial_plan_event(
            serial_plan_id=serial_plan_id,
            event_type="approved",
            from_status="waiting_review",
            to_status=new_status,
            message=f"Batch approved: chapters {from_chapter}-{to_chapter}",
            metadata_json=json.dumps({
                "production_run_id": production_run_id,
                "chapters_completed": chapters_in_batch,
                "notes": notes,
            }),
        )
        if event_id is None:
            # Rollback: revert serial plan to waiting_review
            rollback_ok = self.repo.update_serial_plan(
                serial_plan_id,
                status="waiting_review",
                current_chapter=plan["current_chapter"],
                completed_chapters=plan["completed_chapters"],
                current_queue_id=queue_id,
                current_production_run_id=None,
            )
            if not rollback_ok:
                return {
                    "ok": False,
                    "error": "Failed to record serial plan approval event; AND rollback failed",
                    "data": {"serial_plan_id": serial_plan_id, "compensation_failed": True},
                }
            return {
                "ok": False,
                "error": "Failed to record serial plan approval event",
                "data": {"serial_plan_id": serial_plan_id},
            }

        return {
            "ok": True,
            "error": None,
            "data": {
                "status": new_status,
                "current_chapter": new_current,
                "completed_chapters": new_completed,
            },
        }

    def pause_serial_plan(self, serial_plan_id: str) -> dict[str, Any]:
        """Pause a serial plan.

        Allowed for 'active' or 'waiting_review' status.

        Args:
            serial_plan_id: Serial plan identifier.

        Returns:
            Dict with ok, error, data containing new status.
        """
        plan = self.repo.get_serial_plan(serial_plan_id)
        if not plan:
            return {
                "ok": False,
                "error": f"Serial plan '{serial_plan_id}' not found",
                "data": {},
            }

        if plan["status"] not in ("active", "waiting_review"):
            return {
                "ok": False,
                "error": f"Cannot pause serial plan in status '{plan['status']}'. Only 'active' or 'waiting_review' are allowed.",
                "data": {},
            }

        old_status = plan["status"]
        ok = self.repo.update_serial_plan(serial_plan_id, status="paused")
        if not ok:
            return {
                "ok": False,
                "error": "Failed to pause serial plan",
                "data": {},
            }

        event_id = self.repo.record_serial_plan_event(
            serial_plan_id=serial_plan_id,
            event_type="paused",
            from_status=old_status,
            to_status="paused",
            message="Serial plan paused",
        )
        if event_id is None:
            # Rollback: revert to old status
            rollback_ok = self.repo.update_serial_plan(serial_plan_id, status=old_status)
            if not rollback_ok:
                return {
                    "ok": False,
                    "error": "Failed to record pause event; AND rollback failed",
                    "data": {"serial_plan_id": serial_plan_id, "compensation_failed": True},
                }
            return {
                "ok": False,
                "error": "Failed to record pause event",
                "data": {"serial_plan_id": serial_plan_id},
            }

        return {
            "ok": True,
            "error": None,
            "data": {"status": "paused"},
        }

    def resume_serial_plan(self, serial_plan_id: str) -> dict[str, Any]:
        """Resume a paused serial plan.

        Only allowed for 'paused' status.
        v3.6 simplification: resume always goes to 'active'.

        Args:
            serial_plan_id: Serial plan identifier.

        Returns:
            Dict with ok, error, data containing new status.
        """
        plan = self.repo.get_serial_plan(serial_plan_id)
        if not plan:
            return {
                "ok": False,
                "error": f"Serial plan '{serial_plan_id}' not found",
                "data": {},
            }

        if plan["status"] != "paused":
            return {
                "ok": False,
                "error": f"Cannot resume serial plan in status '{plan['status']}'. Only 'paused' is allowed.",
                "data": {},
            }

        ok = self.repo.update_serial_plan(serial_plan_id, status="active")
        if not ok:
            return {
                "ok": False,
                "error": "Failed to resume serial plan",
                "data": {},
            }

        event_id = self.repo.record_serial_plan_event(
            serial_plan_id=serial_plan_id,
            event_type="resumed",
            from_status="paused",
            to_status="active",
            message="Serial plan resumed",
        )
        if event_id is None:
            # Rollback: revert to paused
            rollback_ok = self.repo.update_serial_plan(serial_plan_id, status="paused")
            if not rollback_ok:
                return {
                    "ok": False,
                    "error": "Failed to record resume event; AND rollback failed",
                    "data": {"serial_plan_id": serial_plan_id, "compensation_failed": True},
                }
            return {
                "ok": False,
                "error": "Failed to record resume event",
                "data": {"serial_plan_id": serial_plan_id},
            }

        return {
            "ok": True,
            "error": None,
            "data": {"status": "active"},
        }

    def cancel_serial_plan(self, serial_plan_id: str, reason: str | None = None) -> dict[str, Any]:
        """Cancel a serial plan.

        Allowed for any non-terminal status.

        Args:
            serial_plan_id: Serial plan identifier.
            reason: Optional cancellation reason.

        Returns:
            Dict with ok, error, data containing new status.
        """
        plan = self.repo.get_serial_plan(serial_plan_id)
        if not plan:
            return {
                "ok": False,
                "error": f"Serial plan '{serial_plan_id}' not found",
                "data": {},
            }

        if plan["status"] in ("completed", "cancelled"):
            return {
                "ok": False,
                "error": f"Cannot cancel serial plan in terminal status '{plan['status']}'",
                "data": {},
            }

        old_status = plan["status"]
        ok = self.repo.update_serial_plan(serial_plan_id, status="cancelled")
        if not ok:
            return {
                "ok": False,
                "error": "Failed to cancel serial plan",
                "data": {},
            }

        event_id = self.repo.record_serial_plan_event(
            serial_plan_id=serial_plan_id,
            event_type="cancelled",
            from_status=old_status,
            to_status="cancelled",
            message=reason or "Serial plan cancelled",
        )
        if event_id is None:
            # Rollback: revert to old status
            rollback_ok = self.repo.update_serial_plan(serial_plan_id, status=old_status)
            if not rollback_ok:
                return {
                    "ok": False,
                    "error": "Failed to record cancel event; AND rollback failed",
                    "data": {"serial_plan_id": serial_plan_id, "compensation_failed": True},
                }
            return {
                "ok": False,
                "error": "Failed to record cancel event",
                "data": {"serial_plan_id": serial_plan_id},
            }

        return {
            "ok": True,
            "error": None,
            "data": {"status": "cancelled"},
        }
