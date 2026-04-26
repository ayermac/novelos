"""v4.0 Style Bible repository tests.

Covers:
- save/get/update/delete/list repository methods
- Migration 012 idempotent
- rowcount checks
- Duplicate save raises error
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from novel_factory.db.connection import init_db, get_connection
from novel_factory.db.repository import Repository
from novel_factory.models.style_bible import StyleBible, ForbiddenExpression


def _ensure_project(db_path: str, project_id: str, name: str = "Test Project") -> None:
    """Insert a project row so FK constraint on style_bibles is satisfied."""
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO projects (project_id, name) VALUES (?, ?)",
            (project_id, name),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary database with schema."""
    db = str(tmp_path / "test_v40.db")
    init_db(db)
    return db


@pytest.fixture
def repo(db_path):
    """Create a Repository instance."""
    return Repository(db_path)


@pytest.fixture
def sample_bible_dict():
    """Create a sample Style Bible dict."""
    bible = StyleBible(
        project_id="test_project",
        name="Test Style Bible",
        genre="玄幻",
        target_platform="web_serial",
        pacing="fast",
        tone_keywords=["热血", "爽感"],
        forbidden_expressions=[
            ForbiddenExpression(pattern="嘴角勾起", reason="AI味", severity="blocking"),
        ],
    )
    return bible.to_storage_dict()


class TestSaveStyleBible:
    """Test save_style_bible."""

    def test_save_success(self, repo, db_path, sample_bible_dict):
        """Save a Style Bible successfully."""
        _ensure_project(db_path, "test_project")
        bible_id = repo.save_style_bible("test_project", sample_bible_dict)
        assert bible_id  # Returns non-empty ID

    def test_save_duplicate_raises(self, repo, db_path, sample_bible_dict):
        """Saving twice for the same project raises ValueError."""
        _ensure_project(db_path, "test_project")
        repo.save_style_bible("test_project", sample_bible_dict)
        with pytest.raises(ValueError, match="already exists"):
            repo.save_style_bible("test_project", sample_bible_dict)


class TestGetStyleBible:
    """Test get_style_bible."""

    def test_get_existing(self, repo, db_path, sample_bible_dict):
        """Get an existing Style Bible."""
        _ensure_project(db_path, "test_project")
        repo.save_style_bible("test_project", sample_bible_dict)
        result = repo.get_style_bible("test_project")
        assert result is not None
        assert result["project_id"] == "test_project"
        assert result["name"] == "Test Style Bible"
        assert "bible" in result
        assert result["bible"]["name"] == "Test Style Bible"

    def test_get_nonexistent(self, repo):
        """Get a nonexistent Style Bible returns None."""
        result = repo.get_style_bible("nonexistent")
        assert result is None

    def test_get_bible_has_parsed_json(self, repo, db_path, sample_bible_dict):
        """Get Style Bible has parsed bible JSON."""
        _ensure_project(db_path, "test_project")
        repo.save_style_bible("test_project", sample_bible_dict)
        result = repo.get_style_bible("test_project")
        bible = result["bible"]
        assert bible["genre"] == "玄幻"
        assert bible["pacing"] == "fast"


class TestUpdateStyleBible:
    """Test update_style_bible."""

    def test_update_success(self, repo, db_path, sample_bible_dict):
        """Update an existing Style Bible."""
        _ensure_project(db_path, "test_project")
        repo.save_style_bible("test_project", sample_bible_dict)
        sample_bible_dict["name"] = "Updated Name"
        ok = repo.update_style_bible("test_project", sample_bible_dict)
        assert ok is True

        result = repo.get_style_bible("test_project")
        assert result["name"] == "Updated Name"

    def test_update_nonexistent(self, repo, sample_bible_dict):
        """Update a nonexistent Style Bible returns False."""
        ok = repo.update_style_bible("nonexistent", sample_bible_dict)
        assert ok is False


class TestDeleteStyleBible:
    """Test delete_style_bible."""

    def test_delete_success(self, repo, db_path, sample_bible_dict):
        """Delete an existing Style Bible."""
        _ensure_project(db_path, "test_project")
        repo.save_style_bible("test_project", sample_bible_dict)
        ok = repo.delete_style_bible("test_project")
        assert ok is True

        result = repo.get_style_bible("test_project")
        assert result is None

    def test_delete_nonexistent(self, repo):
        """Delete a nonexistent Style Bible returns False."""
        ok = repo.delete_style_bible("nonexistent")
        assert ok is False


class TestListStyleBibles:
    """Test list_style_bibles."""

    def test_list_empty(self, repo):
        """List returns empty when no bibles exist."""
        result = repo.list_style_bibles()
        assert result == []

    def test_list_with_data(self, repo, db_path, sample_bible_dict):
        """List returns created bibles."""
        _ensure_project(db_path, "project1", "Project 1")
        _ensure_project(db_path, "project2", "Project 2")
        repo.save_style_bible("project1", {**sample_bible_dict, "project_id": "project1"})
        repo.save_style_bible("project2", {**sample_bible_dict, "project_id": "project2", "name": "Bible 2"})

        result = repo.list_style_bibles()
        assert len(result) == 2
        names = {r["name"] for r in result}
        assert "Test Style Bible" in names
        assert "Bible 2" in names


class TestMigrationIdempotent:
    """Test that migration 012 is idempotent."""

    def test_init_db_twice(self, db_path):
        """Running init_db twice does not fail."""
        init_db(db_path)  # First run
        init_db(db_path)  # Second run (idempotent)

        _ensure_project(db_path, "idem_test")
        repo = Repository(db_path)
        # Should still work
        bible_dict = StyleBible(project_id="idem_test", name="Idempotent Test").to_storage_dict()
        bible_id = repo.save_style_bible("idem_test", bible_dict)
        assert bible_id
