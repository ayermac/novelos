"""v6.8.3 Phase 3: Plot hole status migration + repository guard tests.

Covers:
- The 035 data-repair SQL (resolved_chapter set but non-terminal -> resolved;
  'validated' -> 'planted') and its idempotency.
- The migration detector _plot_hole_status_repaired.
- Repository-layer status normalization guard.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.db.migration_registry import _plot_hole_status_repaired


_MIGRATION_SQL = (
    Path(__file__).resolve().parents[1]
    / "novel_factory" / "db" / "migrations"
    / "035_v6_8_3_plot_hole_status_repair.sql"
)


def _dirty_conn(tmp_path):
    db = tmp_path / "dirty.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE plot_holes ("
        "id INTEGER PRIMARY KEY, code TEXT, status TEXT, resolved_chapter INTEGER)"
    )
    # PH-002-like contradiction + legacy validated
    conn.execute("INSERT INTO plot_holes (code,status,resolved_chapter) VALUES ('PH-002','planted',4)")
    conn.execute("INSERT INTO plot_holes (code,status,resolved_chapter) VALUES ('PH-010','validated',NULL)")
    conn.execute("INSERT INTO plot_holes (code,status,resolved_chapter) VALUES ('PH-001','planted',NULL)")
    conn.commit()
    return conn


class TestMigrationSQL:
    def test_repair_fixes_contradiction_and_validated(self, tmp_path):
        conn = _dirty_conn(tmp_path)
        conn.executescript(_MIGRATION_SQL.read_text(encoding="utf-8"))
        conn.commit()
        rows = {r[0]: (r[1], r[2]) for r in conn.execute(
            "SELECT code, status, resolved_chapter FROM plot_holes")}
        assert rows["PH-002"] == ("resolved", 4)   # contradiction repaired
        assert rows["PH-010"] == ("planted", None)  # validated normalized
        assert rows["PH-001"] == ("planted", None)  # untouched
        conn.close()

    def test_idempotent(self, tmp_path):
        conn = _dirty_conn(tmp_path)
        sql = _MIGRATION_SQL.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.commit()
        first = list(conn.execute("SELECT code, status, resolved_chapter FROM plot_holes ORDER BY code"))
        conn.executescript(sql)  # run again
        conn.commit()
        second = list(conn.execute("SELECT code, status, resolved_chapter FROM plot_holes ORDER BY code"))
        assert first == second
        conn.close()


class TestMigrationDetector:
    def test_detector_false_on_dirty(self, tmp_path):
        conn = _dirty_conn(tmp_path)
        assert _plot_hole_status_repaired(conn) is False
        conn.close()

    def test_detector_true_after_repair(self, tmp_path):
        conn = _dirty_conn(tmp_path)
        conn.executescript(_MIGRATION_SQL.read_text(encoding="utf-8"))
        conn.commit()
        assert _plot_hole_status_repaired(conn) is True
        conn.close()

    def test_detector_false_when_no_table(self, tmp_path):
        # An uninitialized DB (no plot_holes table) means the migration has NOT
        # been applied yet — detector must report False so health shows pending.
        db = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db))
        assert _plot_hole_status_repaired(conn) is False
        conn.close()


class TestRepositoryStatusGuard:
    @pytest.fixture()
    def repo(self, tmp_path):
        db_path = tmp_path / "guard.db"
        init_db(db_path)
        r = Repository(str(db_path))
        r.create_project(project_id="p", name="P", genre="f")
        return r

    def test_create_normalizes_illegal_status(self, repo):
        ph = repo.create_plot_hole("p", code="PH-X", title="t", status="validated")
        assert ph["status"] == "planted"

    def test_update_normalizes_illegal_status(self, repo):
        ph = repo.create_plot_hole("p", code="PH-Y", title="t", status="planted")
        updated = repo.update_plot_hole("p", ph["id"], {"status": "weird"})
        assert updated["status"] == "planted"

    def test_valid_statuses_pass_through(self, repo):
        for st in ("planted", "resolved", "abandoned"):
            ph = repo.create_plot_hole("p", code=f"PH-{st}", title="t", status=st)
            assert ph["status"] == st
