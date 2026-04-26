"""v4.2 Style Sample Repository tests.

Covers:
- save/list/show/delete style samples
- Duplicate content_hash rejection
- Soft delete behavior
- get_style_samples_by_ids
"""

from __future__ import annotations

import json

import pytest

from novel_factory.db.connection import init_db, get_connection
from novel_factory.db.repository import Repository


def _ensure_project(db_path: str, project_id: str) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO projects (project_id, name) VALUES (?, ?)",
            (project_id, "Test Project"),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def db_path(tmp_path):
    db = str(tmp_path / "test_v42_repo.db")
    init_db(db)
    return db


@pytest.fixture
def repo(db_path):
    return Repository(db_path)


class TestSaveStyleSample:
    def test_save_returns_id(self, db_path, repo):
        _ensure_project(db_path, "repo_test")
        sid = repo.save_style_sample(
            "repo_test", "Sample A", "local_text",
            "abc123hash", "preview text",
        )
        assert sid  # Non-empty ID

    def test_save_with_metrics(self, db_path, repo):
        _ensure_project(db_path, "repo_test")
        metrics = {"char_count": 100, "avg_sentence_length": 25.0}
        sid = repo.save_style_sample(
            "repo_test", "Sample B", "local_text",
            "def456hash", "preview",
            metrics_json=json.dumps(metrics),
        )
        sample = repo.get_style_sample(sid)
        assert sample["metrics"]["char_count"] == 100

    def test_duplicate_hash_rejected(self, db_path, repo):
        _ensure_project(db_path, "repo_test")
        repo.save_style_sample(
            "repo_test", "First", "local_text",
            "same_hash", "preview1",
        )
        with pytest.raises(ValueError, match="already exists"):
            repo.save_style_sample(
                "repo_test", "Second", "local_text",
                "same_hash", "preview2",
            )

    def test_same_hash_different_project_ok(self, db_path, repo):
        _ensure_project(db_path, "proj_a")
        _ensure_project(db_path, "proj_b")
        sid_a = repo.save_style_sample(
            "proj_a", "A", "local_text", "hash_x", "p1",
        )
        sid_b = repo.save_style_sample(
            "proj_b", "B", "local_text", "hash_x", "p2",
        )
        assert sid_a != sid_b


class TestGetStyleSample:
    def test_get_existing(self, db_path, repo):
        _ensure_project(db_path, "repo_test")
        sid = repo.save_style_sample(
            "repo_test", "Sample", "local_text", "hash1", "preview",
        )
        sample = repo.get_style_sample(sid)
        assert sample is not None
        assert sample["name"] == "Sample"
        assert sample["source_type"] == "local_text"

    def test_get_nonexistent(self, repo):
        assert repo.get_style_sample("nonexistent") is None

    def test_metrics_parsed(self, db_path, repo):
        _ensure_project(db_path, "repo_test")
        metrics = {"char_count": 50}
        sid = repo.save_style_sample(
            "repo_test", "Parsed", "local_text", "hp",
            "p", metrics_json=json.dumps(metrics),
        )
        sample = repo.get_style_sample(sid)
        assert sample["metrics"]["char_count"] == 50


class TestListStyleSamples:
    def test_list_by_project(self, db_path, repo):
        _ensure_project(db_path, "repo_test")
        repo.save_style_sample("repo_test", "A", "local_text", "h1", "p")
        repo.save_style_sample("repo_test", "B", "local_text", "h2", "p")
        samples = repo.list_style_samples("repo_test")
        assert len(samples) == 2

    def test_list_excludes_deleted(self, db_path, repo):
        _ensure_project(db_path, "repo_test")
        sid = repo.save_style_sample("repo_test", "A", "local_text", "h1", "p")
        repo.delete_style_sample(sid)
        samples = repo.list_style_samples("repo_test")
        assert len(samples) == 0

    def test_list_by_status(self, db_path, repo):
        _ensure_project(db_path, "repo_test")
        sid = repo.save_style_sample("repo_test", "A", "local_text", "h1", "p")
        repo.update_style_sample_analysis(sid, "{}", "{}", status="analyzed")
        analyzed = repo.list_style_samples("repo_test", status="analyzed")
        imported = repo.list_style_samples("repo_test", status="imported")
        assert len(analyzed) == 1
        assert len(imported) == 0


class TestUpdateAnalysis:
    def test_update_sets_analyzed(self, db_path, repo):
        _ensure_project(db_path, "repo_test")
        sid = repo.save_style_sample("repo_test", "A", "local_text", "h1", "p")
        ok = repo.update_style_sample_analysis(
            sid, '{"char_count": 100}', '{"rhythm": "fast"}',
        )
        assert ok is True
        sample = repo.get_style_sample(sid)
        assert sample["status"] == "analyzed"
        assert sample["metrics"]["char_count"] == 100

    def test_update_nonexistent_returns_false(self, repo):
        ok = repo.update_style_sample_analysis("nonexistent", "{}", "{}")
        assert ok is False


class TestDeleteStyleSample:
    def test_soft_delete(self, db_path, repo):
        _ensure_project(db_path, "repo_test")
        sid = repo.save_style_sample("repo_test", "A", "local_text", "h1", "p")
        ok = repo.delete_style_sample(sid)
        assert ok is True
        sample = repo.get_style_sample(sid)
        assert sample["status"] == "deleted"

    def test_double_delete_returns_false(self, db_path, repo):
        _ensure_project(db_path, "repo_test")
        sid = repo.save_style_sample("repo_test", "A", "local_text", "h1", "p")
        repo.delete_style_sample(sid)
        ok = repo.delete_style_sample(sid)
        assert ok is False


class TestGetStyleSamplesByIds:
    def test_get_by_ids(self, db_path, repo):
        _ensure_project(db_path, "repo_test")
        s1 = repo.save_style_sample("repo_test", "A", "local_text", "h1", "p")
        s2 = repo.save_style_sample("repo_test", "B", "local_text", "h2", "p")
        results = repo.get_style_samples_by_ids("repo_test", [s1, s2])
        assert len(results) == 2

    def test_excludes_deleted(self, db_path, repo):
        _ensure_project(db_path, "repo_test")
        s1 = repo.save_style_sample("repo_test", "A", "local_text", "h1", "p")
        s2 = repo.save_style_sample("repo_test", "B", "local_text", "h2", "p")
        repo.delete_style_sample(s1)
        results = repo.get_style_samples_by_ids("repo_test", [s1, s2])
        assert len(results) == 1

    def test_empty_ids(self, db_path, repo):
        results = repo.get_style_samples_by_ids("any", [])
        assert results == []

    def test_wrong_project_excluded(self, db_path, repo):
        _ensure_project(db_path, "proj_a")
        _ensure_project(db_path, "proj_b")
        sid = repo.save_style_sample("proj_a", "A", "local_text", "h1", "p")
        results = repo.get_style_samples_by_ids("proj_b", [sid])
        assert len(results) == 0


class TestMigration014Idempotent:
    def test_init_db_twice(self, db_path):
        init_db(db_path)
        init_db(db_path)
        conn = get_connection(db_path)
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "style_samples" in tables


class TestDBLevelUniqueHashConstraint:
    """Regression: DB-level unique index on (project_id, content_hash) for non-deleted."""

    def test_db_rejects_duplicate_hash(self, db_path, repo):
        """DB-level constraint prevents duplicate hash insertion."""
        _ensure_project(db_path, "uniq_test")
        repo.save_style_sample("uniq_test", "A", "local_text", "hash_dup", "p1")
        # Direct SQL insert bypassing app-level check should still fail
        import sqlite3
        conn = get_connection(db_path)
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO style_samples "
                    "(id, project_id, name, source_type, content_hash, "
                    "content_preview, metrics_json, analysis_json, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'imported', datetime('now'))",
                    ("dup-id", "uniq_test", "B", "local_text", "hash_dup", "p2", "{}", "{}"),
                )
        finally:
            conn.close()

    def test_deleted_allows_reimport(self, db_path, repo):
        """Deleted sample hash can be re-imported (partial unique index excludes deleted)."""
        _ensure_project(db_path, "reimport_test")
        sid = repo.save_style_sample("reimport_test", "A", "local_text", "hash_re", "p1")
        repo.delete_style_sample(sid)
        # Should not raise — deleted row is excluded by partial index
        sid2 = repo.save_style_sample("reimport_test", "B", "local_text", "hash_re", "p2")
        assert sid2 != sid

    def test_unique_index_idempotent(self, tmp_path):
        """Running migration twice does not error on the unique index."""
        db = str(tmp_path / "test_idem.db")
        init_db(db)
        init_db(db)  # Second run should not fail
        conn = get_connection(db)
        indexes = {row[1] for row in conn.execute(
            "SELECT * FROM pragma_index_list('style_samples')"
        ).fetchall()}
        conn.close()
        assert any("project_hash" in idx for idx in indexes)


class TestSaveStyleSampleWithStatus:
    """Regression: save_style_sample supports status='analyzed' for atomic import."""

    def test_save_with_analyzed_status(self, db_path, repo):
        _ensure_project(db_path, "status_test")
        sid = repo.save_style_sample(
            "status_test", "Analyzed", "local_text", "h_status",
            "p", metrics_json='{"char_count": 42}', analysis_json='{}',
            status="analyzed",
        )
        sample = repo.get_style_sample(sid)
        assert sample["status"] == "analyzed"
        assert sample["metrics"]["char_count"] == 42
        assert sample["analyzed_at"] is not None

    def test_save_default_status_is_imported(self, db_path, repo):
        _ensure_project(db_path, "status_test2")
        sid = repo.save_style_sample(
            "status_test2", "Imported", "local_text", "h_imp", "p",
        )
        sample = repo.get_style_sample(sid)
        assert sample["status"] == "imported"
        assert sample["analyzed_at"] is None
