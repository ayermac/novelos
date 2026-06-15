"""Project integrity checking utilities.

v6.10.7: Provides a unified, internal data-integrity validation layer so the
system can detect and refuse operations when critical project assets (protagonist,
project name, required settings) are missing or corrupted — without relying on
external agent intervention.
"""

from __future__ import annotations

from typing import Any


class IntegrityViolation(Exception):
    """Raised when a project fails an integrity check."""

    def __init__(self, check_name: str, message: str, details: dict | None = None):
        self.check_name = check_name
        self.details = details or {}
        super().__init__(f"[{check_name}] {message}")


class ProjectIntegrityChecker:
    """Validate project data integrity before critical operations.

    Checks are intentionally strict: if the project lacks a protagonist with a
    valid name, chapter generation must not proceed. This prevents the downstream
    cascade of garbage data that occurs when the planner/author operate without a
    known protagonist.
    """

    def __init__(self, repo):
        self.repo = repo

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def check_protagonist_exists(self, project_id: str) -> dict:
        """Return status dict; raise IntegrityViolation if protagonist is missing."""
        protagonist = None
        try:
            protagonist = self.repo.get_protagonist(project_id)
        except Exception as exc:
            raise IntegrityViolation(
                "protagonist_exists",
                f"无法查询 protagonist: {exc}",
                {"project_id": project_id},
            ) from exc

        if not protagonist:
            raise IntegrityViolation(
                "protagonist_exists",
                "项目缺少主角（protagonist）。",
                {"project_id": project_id, "remediation": "请先创建主角角色并设置 role='protagonist'。"},
            )

        name = str(protagonist.get("name") or "").strip()
        if not name:
            raise IntegrityViolation(
                "protagonist_name",
                "主角记录存在但名字为空。",
                {
                    "project_id": project_id,
                    "character_id": protagonist.get("id"),
                    "remediation": "请修复主角名字。",
                },
            )

        if len(name) > 16:
            raise IntegrityViolation(
                "protagonist_name",
                f"主角名字过长 ({len(name)} 字符)。",
                {"project_id": project_id, "name": name},
            )

        return {
            "check": "protagonist_exists",
            "ok": True,
            "character_id": protagonist.get("id"),
            "name": name,
        }

    def check_protagonist_unique(self, project_id: str) -> dict:
        """Ensure there is exactly one active protagonist."""
        try:
            chars = self.repo.list_characters(project_id, include_inactive=True)
        except Exception as exc:
            raise IntegrityViolation(
                "protagonist_unique",
                f"无法查询角色列表: {exc}",
                {"project_id": project_id},
            ) from exc

        protagonists = [c for c in chars if c.get("role") == "protagonist"]
        if len(protagonists) > 1:
            raise IntegrityViolation(
                "protagonist_unique",
                f"项目存在 {len(protagonists)} 个 protagonist，只能有一个。",
                {
                    "project_id": project_id,
                    "protagonists": [
                        {"id": c["id"], "name": c.get("name")} for c in protagonists
                    ],
                    "remediation": "请删除或降级多余 protagonist。",
                },
            )

        return {
            "check": "protagonist_unique",
            "ok": True,
            "count": len(protagonists),
        }

    def check_project_exists(self, project_id: str) -> dict:
        """Ensure the project record itself exists."""
        project = self.repo.get_project(project_id)
        if not project:
            raise IntegrityViolation(
                "project_exists",
                f"项目 '{project_id}' 不存在。",
                {"project_id": project_id},
            )
        return {"check": "project_exists", "ok": True, "project_id": project_id}

    # ------------------------------------------------------------------
    # Batch checks
    # ------------------------------------------------------------------

    def run_all_checks(self, project_id: str) -> dict[str, Any]:
        """Run the full integrity suite and return a summary.

        Returns:
            {
                "ok": bool,
                "checks": {"check_name": {"ok": bool, ...}, ...},
                "violations": [IntegrityViolation, ...],
            }
        """
        checks = {}
        violations: list[IntegrityViolation] = []

        for check_fn in (
            self.check_project_exists,
            self.check_protagonist_exists,
            self.check_protagonist_unique,
        ):
            try:
                checks[check_fn.__name__] = check_fn(project_id)
            except IntegrityViolation as exc:
                checks[check_fn.__name__] = {
                    "ok": False,
                    "check": exc.check_name,
                    "error": str(exc),
                    "details": exc.details,
                }
                violations.append(exc)

        return {
            "ok": not violations,
            "checks": checks,
            "violations": [
                {
                    "check": v.check_name,
                    "error": str(v),
                    "details": v.details,
                }
                for v in violations
            ],
        }

    # ------------------------------------------------------------------
    # Convenience gating helpers
    # ------------------------------------------------------------------

    def gate_before_plan(self, project_id: str) -> None:
        """Raise if planning cannot safely proceed."""
        self.check_protagonist_exists(project_id)
        self.check_protagonist_unique(project_id)

    def gate_before_author(self, project_id: str) -> None:
        """Raise if authoring cannot safely proceed."""
        self.check_protagonist_exists(project_id)
        self.check_protagonist_unique(project_id)
