"""Production queue dispatch — enqueue, run, pause, resume, retry, cancel, recover, doctor."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

class QueueDispatchMixin:
    """Production queue dispatch — enqueue, run, pause, resume, retry, cancel, recover, doctor."""

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
