"""Review workbench read-only queries."""

from __future__ import annotations

import difflib

from ..connection import row_to_dict

class ReviewWorkbenchRepositoryMixin:
    def get_review_pack_for_run(self, run_id: str) -> dict | None:
        """Get review pack data for a production run.

        Args:
            run_id: Production run identifier.

        Returns:
            Dict with run info, chapters, quality, continuity, or None if not found.
        """
        conn = self._conn()
        try:
            # Get production run
            run_row = conn.execute(
                "SELECT * FROM production_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if not run_row:
                return None

            run = row_to_dict(run_row)
            project_id = run["project_id"]
            from_chapter = run.get("from_chapter", 1)
            to_chapter = run.get("to_chapter", 1)

            # Get queue item by production_run_id (not queue_id)
            # production_queue has production_run_id field, not production_runs.queue_id
            queue_item = None
            queue_row = conn.execute(
                "SELECT * FROM production_queue WHERE production_run_id = ?",
                (run_id,),
            ).fetchone()
            if queue_row:
                queue_item = row_to_dict(queue_row)

            # Get continuity gate
            gate_row = conn.execute(
                "SELECT * FROM batch_continuity_gates WHERE run_id = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            continuity_gate = row_to_dict(gate_row) if gate_row else None

            # Get chapters info
            chapters = self._get_chapters_review_data(
                conn, project_id, from_chapter, to_chapter
            )

            return {
                "run": run,
                "queue_item": queue_item,
                "chapters": chapters,
                "continuity_gate": continuity_gate,
                "project_id": project_id,
                "from_chapter": from_chapter,
                "to_chapter": to_chapter,
            }
        finally:
            conn.close()

    def get_review_pack_for_serial(self, serial_plan_id: str) -> dict | None:
        """Get review pack data for a serial plan.

        Args:
            serial_plan_id: Serial plan identifier.

        Returns:
            Dict with plan info, current run/chapters, or None if not found.
        """
        conn = self._conn()
        try:
            # Get serial plan
            plan_row = conn.execute(
                "SELECT * FROM serial_plans WHERE id = ?",
                (serial_plan_id,),
            ).fetchone()
            if not plan_row:
                return None

            plan = row_to_dict(plan_row)
            project_id = plan["project_id"]

            # Get current queue item and production run
            queue_item = None
            production_run = None
            continuity_gate = None
            chapters = []

            if plan.get("current_queue_id"):
                queue_row = conn.execute(
                    "SELECT * FROM production_queue WHERE id = ?",
                    (plan["current_queue_id"],),
                ).fetchone()
                if queue_row:
                    queue_item = row_to_dict(queue_row)

                    if queue_item.get("production_run_id"):
                        run_row = conn.execute(
                            "SELECT * FROM production_runs WHERE id = ?",
                            (queue_item["production_run_id"],),
                        ).fetchone()
                        if run_row:
                            production_run = row_to_dict(run_row)

                            # Get continuity gate
                            gate_row = conn.execute(
                                "SELECT * FROM batch_continuity_gates WHERE run_id = ? "
                                "ORDER BY created_at DESC LIMIT 1",
                                (production_run["id"],),
                            ).fetchone()
                            continuity_gate = row_to_dict(gate_row) if gate_row else None

                            # Get chapters
                            from_chapter = production_run.get("from_chapter", 1)
                            to_chapter = production_run.get("to_chapter", 1)
                            chapters = self._get_chapters_review_data(
                                conn, project_id, from_chapter, to_chapter
                            )

            return {
                "plan": plan,
                "queue_item": queue_item,
                "production_run": production_run,
                "chapters": chapters,
                "continuity_gate": continuity_gate,
                "project_id": project_id,
            }
        finally:
            conn.close()

    def get_review_pack_for_range(
        self, project_id: str, from_chapter: int, to_chapter: int
    ) -> dict:
        """Get review pack data for a chapter range.

        Args:
            project_id: Project identifier.
            from_chapter: Starting chapter number.
            to_chapter: Ending chapter number.

        Returns:
            Dict with chapters info.
        """
        conn = self._conn()
        try:
            chapters = self._get_chapters_review_data(
                conn, project_id, from_chapter, to_chapter
            )

            return {
                "project_id": project_id,
                "from_chapter": from_chapter,
                "to_chapter": to_chapter,
                "chapters": chapters,
            }
        finally:
            conn.close()

    def get_chapter_review_view(self, project_id: str, chapter: int) -> dict | None:
        """Get detailed review view for a single chapter.

        Args:
            project_id: Project identifier.
            chapter: Chapter number.

        Returns:
            Dict with chapter details, versions, reviews, quality, notes, or None if not found.
        """
        conn = self._conn()
        try:
            # Get chapter
            chapter_row = conn.execute(
                "SELECT * FROM chapters WHERE project_id = ? AND chapter_number = ?",
                (project_id, chapter),
            ).fetchone()
            if not chapter_row:
                return None

            chapter_data = row_to_dict(chapter_row)
            chapter_id = chapter_data["id"]
            
            # Remove content from chapter_data to prevent leaking full text
            chapter_data.pop("content", None)

            # Get latest version
            latest_version = None
            content_for_preview = None
            version_row = conn.execute(
                "SELECT * FROM chapter_versions WHERE project_id = ? AND chapter = ? "
                "ORDER BY version DESC LIMIT 1",
                (project_id, chapter),
            ).fetchone()
            if version_row:
                latest_version = row_to_dict(version_row)
                # Extract content for preview before removing it
                content_for_preview = latest_version.get("content", "")
                # Remove content from latest_version to prevent leaking full text
                latest_version.pop("content", None)

            # Get recent versions (last 5)
            version_rows = conn.execute(
                "SELECT id, version, word_count, created_at FROM chapter_versions "
                "WHERE project_id = ? AND chapter = ? ORDER BY version DESC LIMIT 5",
                (project_id, chapter),
            ).fetchall()
            recent_versions = [row_to_dict(row) for row in version_rows]

            # Get latest review
            latest_review = None
            review_row = conn.execute(
                "SELECT * FROM reviews WHERE project_id = ? AND chapter_id = ? "
                "ORDER BY reviewed_at DESC LIMIT 1",
                (project_id, chapter_id),
            ).fetchone()
            if review_row:
                latest_review = row_to_dict(review_row)

            # Get latest quality report
            latest_quality = None
            quality_row = conn.execute(
                "SELECT * FROM quality_reports WHERE project_id = ? AND chapter_number = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (project_id, chapter),
            ).fetchone()
            if quality_row:
                latest_quality = row_to_dict(quality_row)

            # Get review notes count
            notes_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM chapter_review_notes "
                "WHERE project_id = ? AND chapter_number = ?",
                (project_id, chapter),
            ).fetchone()["cnt"]

            # Get content preview (max 800 chars)
            content_preview = None
            word_count = 0
            if latest_version:
                word_count = latest_version.get("word_count", 0)
                if content_for_preview:
                    content_preview = content_for_preview[:800]

            return {
                "chapter": chapter_data,
                "latest_version": latest_version,
                "recent_versions": recent_versions,
                "latest_review": latest_review,
                "latest_quality": latest_quality,
                "notes_count": notes_count,
                "content_preview": content_preview,
                "word_count": word_count,
            }
        finally:
            conn.close()

    def get_chapter_version_diff(
        self,
        project_id: str,
        chapter: int,
        from_version: str | None,
        to_version: str | None,
    ) -> dict:
        """Get diff between two chapter versions.

        Args:
            project_id: Project identifier.
            chapter: Chapter number.
            from_version: From version ID (or None for previous).
            to_version: To version ID (or None for latest).

        Returns:
            Dict with diff info.
        """
        conn = self._conn()
        try:
            # Get chapter
            chapter_row = conn.execute(
                "SELECT * FROM chapters WHERE project_id = ? AND chapter_number = ?",
                (project_id, chapter),
            ).fetchone()
            if not chapter_row:
                return {"error": "Chapter not found"}

            chapter_id = row_to_dict(chapter_row)["id"]

            # Get versions
            if to_version:
                to_row = conn.execute(
                    "SELECT * FROM chapter_versions WHERE id = ?",
                    (to_version,),
                ).fetchone()
            else:
                to_row = conn.execute(
                    "SELECT * FROM chapter_versions WHERE project_id = ? AND chapter = ? "
                    "ORDER BY version DESC LIMIT 1",
                    (project_id, chapter),
                ).fetchone()

            if not to_row:
                return {"error": "To version not found"}

            to_data = row_to_dict(to_row)

            if from_version:
                from_row = conn.execute(
                    "SELECT * FROM chapter_versions WHERE id = ?",
                    (from_version,),
                ).fetchone()
            else:
                # Get previous version
                from_row = conn.execute(
                    "SELECT * FROM chapter_versions WHERE project_id = ? AND chapter = ? "
                    "AND version < ? ORDER BY version DESC LIMIT 1",
                    (project_id, chapter, to_data["version"]),
                ).fetchone()

            if not from_row:
                return {"error": "From version not found"}

            from_data = row_to_dict(from_row)

            # Calculate diff summary
            from_content = from_data.get("content", "")
            to_content = to_data.get("content", "")

            from_words = from_data.get("word_count", len(from_content.split()))
            to_words = to_data.get("word_count", len(to_content.split()))

            word_count_delta = to_words - from_words

            # Simple diff using difflib
            import difflib
            from_lines = from_content.splitlines()
            to_lines = to_content.splitlines()

            diff = list(difflib.unified_diff(from_lines, to_lines, lineterm=""))

            # Extract additions and deletions preview
            added_lines = [line[1:] for line in diff if line.startswith("+") and not line.startswith("+++")]
            removed_lines = [line[1:] for line in diff if line.startswith("-") and not line.startswith("---")]

            added_preview = "\n".join(added_lines[:10])[:400]
            removed_preview = "\n".join(removed_lines[:10])[:400]

            # Calculate changed ratio
            total_lines = max(len(from_lines), len(to_lines), 1)
            changed_lines = len(added_lines) + len(removed_lines)
            changed_ratio = changed_lines / (total_lines * 2) if total_lines > 0 else 0

            return {
                "from_version_id": from_data["id"],
                "to_version_id": to_data["id"],
                "from_version_number": from_data["version"],
                "to_version_number": to_data["version"],
                "word_count_delta": word_count_delta,
                "changed_ratio": round(changed_ratio, 3),
                "added_preview": added_preview,
                "removed_preview": removed_preview,
            }
        finally:
            conn.close()

    def get_timeline_events(self, scope_type: str, scope_id: str) -> list[dict]:
        """Get timeline events for a scope.

        Args:
            scope_type: Type of scope (run, serial, queue, chapter).
            scope_id: Scope identifier.

        Returns:
            List of timeline events sorted by time ASC.
        """
        conn = self._conn()
        try:
            events = []

            if scope_type == "run":
                # Get production run events
                run_row = conn.execute(
                    "SELECT * FROM production_runs WHERE id = ?",
                    (scope_id,),
                ).fetchone()
                if run_row:
                    run = row_to_dict(run_row)
                    events.append({
                        "time": run.get("created_at"),
                        "source": "production_runs",
                        "type": "created",
                        "status": run.get("status"),
                        "message": f"Production run created: {run.get('from_chapter')}-{run.get('to_chapter')}",
                        "ref_id": run["id"],
                    })

                    # Get continuity gate events
                    gate_rows = conn.execute(
                        "SELECT * FROM batch_continuity_gates WHERE run_id = ? "
                        "ORDER BY created_at ASC",
                        (scope_id,),
                    ).fetchall()
                    for gate_row in gate_rows:
                        gate = row_to_dict(gate_row)
                        events.append({
                            "time": gate.get("created_at"),
                            "source": "batch_continuity_gates",
                            "type": "gate_run",
                            "status": gate.get("status"),
                            "message": f"Continuity gate: {gate.get('status')}",
                            "ref_id": gate["id"],
                        })

                    # Get human review sessions
                    session_rows = conn.execute(
                        "SELECT * FROM human_review_sessions WHERE run_id = ? "
                        "ORDER BY created_at ASC",
                        (scope_id,),
                    ).fetchall()
                    for session_row in session_rows:
                        session = row_to_dict(session_row)
                        events.append({
                            "time": session.get("created_at"),
                            "source": "human_review_sessions",
                            "type": session.get("decision", "reviewed"),
                            "status": None,
                            "message": f"Human review: {session.get('decision', 'unknown')}",
                            "ref_id": session["id"],
                        })

                    # Get queue item and its events
                    queue_row = conn.execute(
                        "SELECT * FROM production_queue WHERE production_run_id = ?",
                        (scope_id,),
                    ).fetchone()
                    if queue_row:
                        queue = row_to_dict(queue_row)
                        queue_id = queue["id"]
                        
                        # Get queue events
                        queue_event_rows = conn.execute(
                            "SELECT * FROM production_queue_events WHERE queue_id = ? "
                            "ORDER BY created_at ASC",
                            (queue_id,),
                        ).fetchall()
                        for event_row in queue_event_rows:
                            event = row_to_dict(event_row)
                            events.append({
                                "time": event.get("created_at"),
                                "source": "production_queue_events",
                                "type": event.get("event_type", "unknown"),
                                "status": event.get("status"),
                                "message": event.get("message", ""),
                                "ref_id": event["id"],
                            })

            elif scope_type == "serial":
                # Get serial plan events
                event_rows = conn.execute(
                    "SELECT * FROM serial_plan_events WHERE serial_plan_id = ? "
                    "ORDER BY created_at ASC",
                    (scope_id,),
                ).fetchall()
                for event_row in event_rows:
                    event = row_to_dict(event_row)
                    events.append({
                        "time": event.get("created_at"),
                        "source": "serial_plan_events",
                        "type": event.get("event_type"),
                        "status": event.get("to_status"),
                        "message": event.get("message", ""),
                        "ref_id": event["id"],
                    })

            elif scope_type == "queue":
                # Get queue events
                event_rows = conn.execute(
                    "SELECT * FROM production_queue_events WHERE queue_id = ? "
                    "ORDER BY created_at ASC",
                    (scope_id,),
                ).fetchall()
                for event_row in event_rows:
                    event = row_to_dict(event_row)
                    events.append({
                        "time": event.get("created_at"),
                        "source": "production_queue_events",
                        "type": event.get("event_type"),
                        "status": event.get("to_status"),
                        "message": event.get("message", ""),
                        "ref_id": event["id"],
                    })

            elif scope_type == "chapter":
                # Get chapter workflow runs
                # scope_id format: "project_id:chapter_number"
                if ":" in scope_id:
                    project_id, chapter_str = scope_id.split(":", 1)
                    chapter_number = int(chapter_str)

                    # Get chapter
                    chapter_row = conn.execute(
                        "SELECT * FROM chapters WHERE project_id = ? AND chapter_number = ?",
                        (project_id, chapter_number),
                    ).fetchone()
                    if chapter_row:
                        chapter = row_to_dict(chapter_row)
                        chapter_id = chapter["id"]

                        # Get workflow runs
                        workflow_rows = conn.execute(
                            "SELECT * FROM workflow_runs WHERE project_id = ? AND chapter_number = ? "
                            "ORDER BY started_at ASC",
                            (project_id, chapter_number),
                        ).fetchall()
                        for workflow_row in workflow_rows:
                            workflow = row_to_dict(workflow_row)
                            events.append({
                                "time": workflow.get("started_at"),
                                "source": "workflow_runs",
                                "type": workflow.get("current_node", "run"),
                                "status": workflow.get("status"),
                                "message": f"Workflow: {workflow.get('current_node', 'unknown')}",
                                "ref_id": workflow["id"],
                            })

                        # Get quality reports
                        quality_rows = conn.execute(
                            "SELECT * FROM quality_reports WHERE project_id = ? AND chapter_number = ? "
                            "ORDER BY created_at ASC",
                            (project_id, chapter_number),
                        ).fetchall()
                        for quality_row in quality_rows:
                            quality = row_to_dict(quality_row)
                            events.append({
                                "time": quality.get("created_at"),
                                "source": "quality_reports",
                                "type": "quality_check",
                                "status": "pass" if quality.get("pass") else "fail",
                                "message": f"Quality report: score {quality.get('overall_score', 0)}",
                                "ref_id": quality["id"],
                            })

            # Sort by time
            events.sort(key=lambda e: e.get("time", ""))

            return events
        finally:
            conn.close()

    def _get_chapters_review_data(
        self, conn, project_id: str, from_chapter: int, to_chapter: int
    ) -> list[dict]:
        """Helper to get review data for a range of chapters.

        Args:
            conn: Database connection.
            project_id: Project identifier.
            from_chapter: Starting chapter number.
            to_chapter: Ending chapter number.

        Returns:
            List of chapter review data.
        """
        chapters = []

        for chapter_num in range(from_chapter, to_chapter + 1):
            # Get chapter
            chapter_row = conn.execute(
                "SELECT * FROM chapters WHERE project_id = ? AND chapter_number = ?",
                (project_id, chapter_num),
            ).fetchone()

            if not chapter_row:
                continue

            chapter = row_to_dict(chapter_row)
            chapter_id = chapter["id"]

            # Get latest version
            version_row = conn.execute(
                "SELECT id, word_count FROM chapter_versions WHERE project_id = ? AND chapter = ? "
                "ORDER BY version DESC LIMIT 1",
                (project_id, chapter_num),
            ).fetchone()
            latest_version_id = version_row["id"] if version_row else None
            word_count = version_row["word_count"] if version_row else 0

            # Get latest quality report
            quality_row = conn.execute(
                "SELECT overall_score, pass FROM quality_reports WHERE project_id = ? AND chapter_number = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (project_id, chapter_num),
            ).fetchone()

            quality_data = None
            if quality_row:
                quality_data = {
                    "latest_score": quality_row["overall_score"],
                    "pass": bool(quality_row["pass"]),
                }

            # Get latest review
            review_row = conn.execute(
                "SELECT score, pass FROM reviews WHERE project_id = ? AND chapter_id = ? "
                "ORDER BY reviewed_at DESC LIMIT 1",
                (project_id, chapter_id),
            ).fetchone()

            review_data = None
            if review_row:
                review_data = {
                    "latest_score": review_row["score"],
                    "passed": bool(review_row["pass"]),
                }

            # Get notes count
            notes_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM chapter_review_notes "
                "WHERE project_id = ? AND chapter_number = ?",
                (project_id, chapter_num),
            ).fetchone()["cnt"]

            chapters.append({
                "chapter": chapter_num,
                "status": chapter.get("status"),
                "word_count": word_count,
                "latest_version_id": latest_version_id,
                "quality": quality_data,
                "review": review_data,
                "notes_count": notes_count,
            })

        return chapters
