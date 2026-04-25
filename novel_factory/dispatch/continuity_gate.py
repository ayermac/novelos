"""Continuity gate dispatch — run, status, approval."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

class ContinuityGateDispatchMixin:
    """Continuity gate dispatch — run, status, approval."""

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
