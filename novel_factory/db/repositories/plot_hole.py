"""Plot hole (伏笔) CRUD operations."""

from __future__ import annotations

from ..connection import row_to_dict

# v6.8.3: Canonical plot hole status values and terminal set.
VALID_PLOT_STATUSES = ("planted", "resolved", "abandoned")
TERMINAL_PLOT_STATUSES = ("resolved", "abandoned")


class PlotHoleRepositoryMixin:
    """Repository mixin for plot_holes table CRUD operations."""

    def list_plot_holes(self, project_id: str, status: str | None = None) -> list[dict]:
        """List plot holes for a project.

        Args:
            project_id: Project identifier.
            status: Optional status filter (planted, resolved).

        Returns:
            List of plot hole dicts.
        """
        conn = self._conn()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM plot_holes WHERE project_id=? AND status=? ORDER BY planted_chapter, code",
                    (project_id, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM plot_holes WHERE project_id=? ORDER BY planted_chapter, code",
                    (project_id,),
                ).fetchall()
            return [row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_plot_hole(self, project_id: str, plot_id: int) -> dict | None:
        """Get a specific plot hole.

        Args:
            project_id: Project identifier.
            plot_id: Plot hole ID.

        Returns:
            Plot hole dict or None if not found.
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM plot_holes WHERE project_id=? AND id=?",
                (project_id, plot_id),
            ).fetchone()
            return row_to_dict(row)
        finally:
            conn.close()

    def create_plot_hole(
        self,
        project_id: str,
        code: str,
        type: str = "",
        title: str = "",
        description: str = "",
        planted_chapter: int | None = None,
        planned_resolve_chapter: int | None = None,
        status: str = "planted",
        notes: str = "",
    ) -> dict:
        """Create a new plot hole.

        Args:
            project_id: Project identifier.
            code: Unique plot code within project.
            type: Plot type (伏笔/线索/悬念).
            title: Plot title.
            description: Plot description.
            planted_chapter: Chapter where planted.
            planned_resolve_chapter: Chapter where planned to resolve.
            status: Status (planted/resolved).
            notes: Additional notes.

        Returns:
            Created plot hole dict with id.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "INSERT INTO plot_holes "
                "(project_id, code, type, title, description, planted_chapter, "
                "planned_resolve_chapter, status, notes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (project_id, code, type, title, description, planted_chapter,
                 planned_resolve_chapter, status, notes),
            )
            plot_id = cursor.lastrowid
            conn.commit()
            return {
                "id": plot_id,
                "project_id": project_id,
                "code": code,
                "type": type,
                "title": title,
                "description": description,
                "planted_chapter": planted_chapter,
                "planned_resolve_chapter": planned_resolve_chapter,
                "status": status,
                "notes": notes,
            }
        finally:
            conn.close()

    def update_plot_hole(
        self,
        project_id: str,
        plot_id: int,
        data: dict,
        *,
        protect_terminal: bool = True,
    ) -> dict | None:
        """Update a plot hole.

        Args:
            project_id: Project identifier.
            plot_id: Plot hole ID.
            data: Dict with fields to update.
            protect_terminal: v6.8.3 — when True (default), a plot already in a
                terminal status (resolved/abandoned) cannot have its status or
                resolved_chapter regressed by a non-terminal update. This is the
                last line of defense against same-batch ``update`` patches that
                carry a stale ``status="planted"`` and silently revert a prior
                ``resolve``. Explicit re-resolve/deprecate (a terminal incoming
                status) still passes through.

        Returns:
            Updated plot hole dict or None if not found.
        """
        conn = self._conn()
        try:
            current = row_to_dict(
                conn.execute(
                    "SELECT * FROM plot_holes WHERE project_id=? AND id=?",
                    (project_id, plot_id),
                ).fetchone()
            )
            if current is None:
                return None

            data = dict(data)
            # v6.8.3: Terminal status protection. A non-terminal update must not
            # knock a resolved/abandoned plot back to planted. Only strip fields
            # when the incoming update *explicitly* carries a regressive status;
            # an update that merely sets resolved_chapter (no status) is allowed.
            if protect_terminal and current.get("status") in TERMINAL_PLOT_STATUSES:
                incoming_status = data.get("status")
                if incoming_status is not None and incoming_status not in TERMINAL_PLOT_STATUSES:
                    # Regressive status change attempt — drop the status and any
                    # accompanying resolved_chapter so the terminal state holds.
                    data.pop("status", None)
                    data.pop("resolved_chapter", None)

            fields = []
            values = []
            for key in ("code", "type", "title", "description", "planted_chapter",
                        "planned_resolve_chapter", "resolved_chapter", "status", "notes"):
                if key in data:
                    fields.append(f"{key}=?")
                    values.append(data[key])

            if not fields:
                return current

            values.extend([project_id, plot_id])
            cursor = conn.execute(
                f"UPDATE plot_holes SET {', '.join(fields)} "
                "WHERE project_id=? AND id=?",
                values,
            )
            conn.commit()

            if cursor.rowcount == 0:
                return None

            return self.get_plot_hole(project_id, plot_id)
        finally:
            conn.close()

    def delete_plot_hole(self, project_id: str, plot_id: int) -> bool:
        """Delete a plot hole.

        Args:
            project_id: Project identifier.
            plot_id: Plot hole ID.

        Returns:
            True if deleted, False if not found.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "DELETE FROM plot_holes WHERE project_id=? AND id=?",
                (project_id, plot_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete_plot_holes_by_project(self, project_id: str) -> int:
        """Delete all plot holes for a project (used in cascade delete).

        Args:
            project_id: Project identifier.

        Returns:
            Number of rows deleted.
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "DELETE FROM plot_holes WHERE project_id=?",
                (project_id,),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()
