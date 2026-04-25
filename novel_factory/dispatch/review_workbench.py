"""Review workbench dispatch — build pack, chapter, timeline, diff, export."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

class ReviewWorkbenchDispatchMixin:
    """Review workbench dispatch — build pack, chapter, timeline, diff, export."""

    def build_review_pack(
        self,
        run_id: str | None = None,
        serial_plan_id: str | None = None,
        project_id: str | None = None,
        from_chapter: int | None = None,
        to_chapter: int | None = None,
    ) -> dict[str, Any]:
        """Build a review pack for human review.

        Args:
            run_id: Production run ID (priority 1).
            serial_plan_id: Serial plan ID (priority 2).
            project_id: Project ID for range (priority 3).
            from_chapter: Starting chapter for range.
            to_chapter: Ending chapter for range.

        Returns:
            Dict with ok, error, data containing review pack.
        """
        # Validate scope exclusivity: must specify exactly one scope
        scopes_specified = 0
        if run_id:
            scopes_specified += 1
        if serial_plan_id:
            scopes_specified += 1
        if project_id and from_chapter is not None and to_chapter is not None:
            scopes_specified += 1

        if scopes_specified == 0:
            return {
                "ok": False,
                "error": "Must specify one of: --run-id, --serial-plan-id, or --project-id with --from-chapter and --to-chapter",
                "data": {},
            }

        if scopes_specified > 1:
            return {
                "ok": False,
                "error": "Must specify only one scope: --run-id, --serial-plan-id, or --project-id with --from-chapter and --to-chapter",
                "data": {},
            }

        # Process the single specified scope
        if run_id:
            pack_data = self.repo.get_review_pack_for_run(run_id)
            if not pack_data:
                return {
                    "ok": False,
                    "error": f"Production run '{run_id}' not found",
                    "data": {},
                }
            scope_type = "production_run"
            scope_id = run_id
            project_id = pack_data["project_id"]
            from_chapter = pack_data["from_chapter"]
            to_chapter = pack_data["to_chapter"]

        elif serial_plan_id:
            pack_data = self.repo.get_review_pack_for_serial(serial_plan_id)
            if not pack_data:
                return {
                    "ok": False,
                    "error": f"Serial plan '{serial_plan_id}' not found",
                    "data": {},
                }
            scope_type = "serial_plan"
            scope_id = serial_plan_id
            project_id = pack_data["project_id"]

            # Get current batch info
            if pack_data.get("production_run"):
                from_chapter = pack_data["production_run"].get("from_chapter", 1)
                to_chapter = pack_data["production_run"].get("to_chapter", 1)
            else:
                # No current batch, use plan defaults
                plan = pack_data["plan"]
                from_chapter = plan.get("current_chapter", 1)
                to_chapter = from_chapter

        elif project_id and from_chapter is not None and to_chapter is not None:
            # Validate range
            if from_chapter > to_chapter:
                return {
                    "ok": False,
                    "error": f"from_chapter ({from_chapter}) must be <= to_chapter ({to_chapter})",
                    "data": {},
                }

            # Check max range
            if to_chapter - from_chapter + 1 > 50:
                return {
                    "ok": False,
                    "error": f"Chapter range exceeds maximum (50 chapters)",
                    "data": {},
                }

            pack_data = self.repo.get_review_pack_for_range(
                project_id, from_chapter, to_chapter
            )
            scope_type = "chapter_range"
            scope_id = f"{project_id}:{from_chapter}-{to_chapter}"

        else:
            return {
                "ok": False,
                "error": "Must specify one of: --run-id, --serial-plan-id, or --project-id with --from-chapter and --to-chapter",
                "data": {},
            }

        # Build decision hint
        decision_hint = self._build_decision_hint(pack_data, scope_type)

        # Get timeline
        timeline = []
        if scope_type == "production_run":
            timeline = self.repo.get_timeline_events("run", scope_id)
        elif scope_type == "serial_plan":
            timeline = self.repo.get_timeline_events("serial", scope_id)

        return {
            "ok": True,
            "error": None,
            "data": {
                "scope": {
                    "type": scope_type,
                    "id": scope_id,
                    "project_id": project_id,
                    "from_chapter": from_chapter,
                    "to_chapter": to_chapter,
                },
                "decision_hint": decision_hint,
                "chapters": pack_data.get("chapters", []),
                "continuity_gate": pack_data.get("continuity_gate"),
                "queue_item": pack_data.get("queue_item"),
                "timeline": timeline,
            },
        }

    def _build_decision_hint(self, pack_data: dict, scope_type: str) -> dict:
        """Build decision hint from pack data.

        Args:
            pack_data: Pack data from repository.
            scope_type: Type of scope.

        Returns:
            Dict with can_approve, blocking_reasons, warnings.
        """
        blocking_reasons = []
        warnings = []

        # Check queue item status (for run/serial)
        if scope_type in ("production_run", "serial_plan"):
            queue_item = pack_data.get("queue_item")
            if queue_item and queue_item.get("status") != "completed":
                blocking_reasons.append("queue_item_not_completed")

        # Check production run status
        run = pack_data.get("run") or pack_data.get("production_run")
        if run:
            run_status = run.get("status")
            if run_status in ("request_changes", "failed", "blocked"):
                blocking_reasons.append(f"production_run_status_{run_status}")

        # Check continuity gate (for multi-chapter batches)
        chapters = pack_data.get("chapters", [])
        if len(chapters) > 1:
            gate = pack_data.get("continuity_gate")
            if not gate:
                blocking_reasons.append("continuity_gate_not_run")
            elif gate.get("status") in ("failed", "error"):
                blocking_reasons.append(f"continuity_gate_{gate.get('status')}")
            elif gate.get("status") == "warning":
                warnings.append("continuity_gate_warning")

        # Check chapters quality and review
        for chapter_data in chapters:
            chapter_num = chapter_data.get("chapter")

            # Check quality
            quality = chapter_data.get("quality")
            if quality and not quality.get("pass"):
                blocking_reasons.append(f"chapter_{chapter_num}_quality_blocking")

            # Check review
            review = chapter_data.get("review")
            if review and not review.get("passed"):
                blocking_reasons.append(f"chapter_{chapter_num}_review_failed")

            # Check notes
            if chapter_data.get("notes_count", 0) > 0:
                warnings.append(f"chapter_{chapter_num}_has_notes")

        can_approve = len(blocking_reasons) == 0

        return {
            "can_approve": can_approve,
            "blocking_reasons": blocking_reasons,
            "warnings": warnings,
        }

    def get_review_chapter(self, project_id: str, chapter: int) -> dict[str, Any]:
        """Get review view for a single chapter.

        Args:
            project_id: Project identifier.
            chapter: Chapter number.

        Returns:
            Dict with ok, error, data containing chapter review view.
        """
        view_data = self.repo.get_chapter_review_view(project_id, chapter)
        if not view_data:
            return {
                "ok": False,
                "error": f"Chapter {chapter} not found in project '{project_id}'",
                "data": {},
            }

        return {
            "ok": True,
            "error": None,
            "data": view_data,
        }

    def get_review_timeline(
        self,
        run_id: str | None = None,
        serial_plan_id: str | None = None,
        queue_id: str | None = None,
        project_id: str | None = None,
        chapter: int | None = None,
    ) -> dict[str, Any]:
        """Get timeline events for a scope.

        Args:
            run_id: Production run ID.
            serial_plan_id: Serial plan ID.
            queue_id: Queue item ID.
            project_id: Project ID (for chapter).
            chapter: Chapter number.

        Returns:
            Dict with ok, error, data containing timeline events.
        """
        # Determine scope
        if run_id:
            events = self.repo.get_timeline_events("run", run_id)
        elif serial_plan_id:
            events = self.repo.get_timeline_events("serial", serial_plan_id)
        elif queue_id:
            events = self.repo.get_timeline_events("queue", queue_id)
        elif project_id and chapter is not None:
            scope_id = f"{project_id}:{chapter}"
            events = self.repo.get_timeline_events("chapter", scope_id)
        else:
            return {
                "ok": False,
                "error": "Must specify one of: --run-id, --serial-plan-id, --queue-id, or --project-id with --chapter",
                "data": {},
            }

        return {
            "ok": True,
            "error": None,
            "data": {"events": events},
        }

    def get_review_diff(
        self,
        project_id: str,
        chapter: int,
        from_version: str | None = None,
        to_version: str | None = None,
    ) -> dict[str, Any]:
        """Get diff between chapter versions.

        Args:
            project_id: Project identifier.
            chapter: Chapter number.
            from_version: From version ID (or None for previous).
            to_version: To version ID (or None for latest).

        Returns:
            Dict with ok, error, data containing diff info.
        """
        diff_data = self.repo.get_chapter_version_diff(
            project_id, chapter, from_version, to_version
        )

        if "error" in diff_data:
            return {
                "ok": False,
                "error": diff_data["error"],
                "data": {},
            }

        return {
            "ok": True,
            "error": None,
            "data": diff_data,
        }

    def export_review_pack(
        self,
        run_id: str | None = None,
        serial_plan_id: str | None = None,
        project_id: str | None = None,
        from_chapter: int | None = None,
        to_chapter: int | None = None,
        format: str = "json",
        output: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Export review pack to file.

        Args:
            run_id: Production run ID.
            serial_plan_id: Serial plan ID.
            project_id: Project ID for range.
            from_chapter: Starting chapter for range.
            to_chapter: Ending chapter for range.
            format: Export format (json or markdown).
            output: Output file path.
            force: Force overwrite if file exists.

        Returns:
            Dict with ok, error, data.
        """
        # Build review pack
        pack_result = self.build_review_pack(
            run_id=run_id,
            serial_plan_id=serial_plan_id,
            project_id=project_id,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
        )

        if not pack_result.get("ok"):
            return pack_result

        # Validate format
        if format not in ("json", "markdown"):
            return {
                "ok": False,
                "error": f"Invalid format '{format}'. Must be 'json' or 'markdown'",
                "data": {},
            }

        # Check output path
        if not output:
            return {
                "ok": False,
                "error": "Must specify --output path",
                "data": {},
            }

        # Check if file exists
        from pathlib import Path
        output_path = Path(output)

        if output_path.exists() and not force:
            return {
                "ok": False,
                "error": f"File '{output}' already exists. Use --force to overwrite.",
                "data": {},
            }

        # Check parent directory exists
        if not output_path.parent.exists():
            return {
                "ok": False,
                "error": f"Parent directory '{output_path.parent}' does not exist",
                "data": {},
            }

        # Generate content
        if format == "json":
            content = json.dumps(pack_result["data"], indent=2, ensure_ascii=False)
        else:
            content = self._generate_markdown_review_pack(pack_result["data"])

        # Write file
        try:
            output_path.write_text(content, encoding="utf-8")
        except Exception as e:
            return {
                "ok": False,
                "error": f"Failed to write file: {e}",
                "data": {},
            }

        return {
            "ok": True,
            "error": None,
            "data": {"output": str(output_path), "format": format},
        }

    def _generate_markdown_review_pack(self, data: dict) -> str:
        """Generate markdown format review pack.

        Args:
            data: Review pack data.

        Returns:
            Markdown string.
        """
        lines = []

        # Title
        scope = data.get("scope", {})
        scope_type = scope.get("type", "unknown")
        project_id = scope.get("project_id", "")
        from_ch = scope.get("from_chapter", 1)
        to_ch = scope.get("to_chapter", 1)

        lines.append(f"# Review Pack: {project_id} chapters {from_ch}-{to_ch}")
        lines.append("")

        # Decision Hint
        lines.append("## Decision Hint")
        lines.append("")
        hint = data.get("decision_hint", {})
        can_approve = hint.get("can_approve", False)
        lines.append(f"- Can approve: {'yes' if can_approve else 'no'}")

        blocking = hint.get("blocking_reasons", [])
        if blocking:
            lines.append("- Blocking:")
            for reason in blocking:
                lines.append(f"  - {reason}")

        warnings = hint.get("warnings", [])
        if warnings:
            lines.append("- Warnings:")
            for warning in warnings:
                lines.append(f"  - {warning}")

        lines.append("")

        # Chapters table
        chapters = data.get("chapters", [])
        if chapters:
            lines.append("## Chapters")
            lines.append("")
            lines.append("| Chapter | Status | Words | Quality | Review | Notes |")
            lines.append("| --- | --- | ---: | --- | --- | ---: |")

            for ch in chapters:
                ch_num = ch.get("chapter", "?")
                status = ch.get("status", "?")
                words = ch.get("word_count", 0)

                quality = ch.get("quality")
                if quality:
                    q_pass = "pass" if quality.get("pass") else "fail"
                    q_score = quality.get("latest_score", 0)
                    quality_str = f"{q_pass} {q_score}"
                else:
                    quality_str = "-"

                review = ch.get("review")
                if review:
                    r_pass = "pass" if review.get("passed") else "fail"
                    r_score = review.get("latest_score", 0)
                    review_str = f"{r_pass} {r_score}"
                else:
                    review_str = "-"

                notes = ch.get("notes_count", 0)

                lines.append(f"| {ch_num} | {status} | {words} | {quality_str} | {review_str} | {notes} |")

            lines.append("")

        # Continuity Gate
        gate = data.get("continuity_gate")
        if gate:
            lines.append("## Continuity Gate")
            lines.append("")
            lines.append(f"- Status: {gate.get('status', 'unknown')}")
            lines.append(f"- Issue count: {gate.get('issue_count', 0)}")
            lines.append("")

        # Timeline
        timeline = data.get("timeline", [])
        if timeline:
            lines.append("## Timeline")
            lines.append("")
            for event in timeline:
                time = event.get("time", "?")
                source = event.get("source", "?")
                event_type = event.get("type", "?")
                message = event.get("message", "")
                lines.append(f"- {time} [{source}] {event_type}: {message}")

            lines.append("")

        return "\n".join(lines)
