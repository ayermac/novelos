"""v4.1 Style Bible Version tests.

Covers:
- save/list/show style_bible_versions
- update_style_bible auto-creates version record
- Version record contains correct data
"""

from __future__ import annotations

import json

import pytest

from novel_factory.db.connection import init_db, get_connection
from novel_factory.db.repository import Repository
from novel_factory.models.style_bible import StyleBible


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
    db = str(tmp_path / "test_v41_versions.db")
    init_db(db)
    return db


@pytest.fixture
def repo(db_path):
    return Repository(db_path)


class TestStyleBibleVersions:
    def test_save_version(self, db_path, repo):
        _ensure_project(db_path, "ver_test")
        bible = StyleBible(project_id="ver_test", name="V1")
        bible_id = repo.save_style_bible("ver_test", bible.to_storage_dict())

        vid = repo.save_style_bible_version(
            "ver_test", bible_id, bible.to_storage_dict(),
            change_summary="Initial version",
            created_by="test",
        )
        assert vid  # Returns non-empty ID

    def test_list_versions(self, db_path, repo):
        _ensure_project(db_path, "ver_test")
        bible = StyleBible(project_id="ver_test", name="V1")
        bible_id = repo.save_style_bible("ver_test", bible.to_storage_dict())

        repo.save_style_bible_version("ver_test", bible_id, bible.to_storage_dict(), "v1")
        repo.save_style_bible_version("ver_test", bible_id, bible.to_storage_dict(), "v2")

        versions = repo.get_style_bible_versions("ver_test")
        assert len(versions) == 2

    def test_get_version(self, db_path, repo):
        _ensure_project(db_path, "ver_test")
        bible = StyleBible(project_id="ver_test", name="V1")
        bible_id = repo.save_style_bible("ver_test", bible.to_storage_dict())

        vid = repo.save_style_bible_version(
            "ver_test", bible_id, bible.to_storage_dict(), "Initial"
        )
        version = repo.get_style_bible_version(vid)
        assert version is not None
        assert version["change_summary"] == "Initial"
        assert "bible" in version  # Parsed JSON

    def test_get_nonexistent_version(self, repo):
        version = repo.get_style_bible_version("nonexistent")
        assert version is None

    def test_update_creates_version(self, db_path, repo):
        """update_style_bible auto-creates a version snapshot."""
        _ensure_project(db_path, "ver_test")
        bible = StyleBible(project_id="ver_test", name="V1", genre="玄幻")
        repo.save_style_bible("ver_test", bible.to_storage_dict())

        # No versions yet
        versions = repo.get_style_bible_versions("ver_test")
        assert len(versions) == 0

        # Update
        bible.genre = "仙侠"
        ok = repo.update_style_bible("ver_test", bible.to_storage_dict(), change_summary="Changed genre")
        assert ok is True

        # Version should be auto-created
        versions = repo.get_style_bible_versions("ver_test")
        assert len(versions) == 1
        assert versions[0]["change_summary"] == "Changed genre"

    def test_multiple_updates_multiple_versions(self, db_path, repo):
        _ensure_project(db_path, "ver_test")
        bible = StyleBible(project_id="ver_test", name="V1")
        repo.save_style_bible("ver_test", bible.to_storage_dict())

        bible.genre = "仙侠"
        repo.update_style_bible("ver_test", bible.to_storage_dict(), "Change 1")
        bible.target_platform = "起点"
        repo.update_style_bible("ver_test", bible.to_storage_dict(), "Change 2")

        versions = repo.get_style_bible_versions("ver_test")
        assert len(versions) == 2

    def test_version_contains_old_bible_data(self, db_path, repo):
        """Version snapshot contains the OLD bible data, not the new one."""
        _ensure_project(db_path, "ver_test")
        bible = StyleBible(project_id="ver_test", name="V1", genre="玄幻")
        repo.save_style_bible("ver_test", bible.to_storage_dict())

        # Update genre
        bible.genre = "仙侠"
        repo.update_style_bible("ver_test", bible.to_storage_dict(), "Changed genre")

        # Version should have OLD genre
        versions = repo.get_style_bible_versions("ver_test")
        version_data = repo.get_style_bible_version(versions[0]["id"])
        assert version_data["bible"]["genre"] == "玄幻"

        # Current bible should have NEW genre
        current = repo.get_style_bible("ver_test")
        assert current["bible"]["genre"] == "仙侠"

    def test_update_fails_if_version_snapshot_fails(self, db_path, repo):
        """update_style_bible raises error if version snapshot insert fails,
        and the Style Bible itself is NOT updated (atomic rollback)."""
        _ensure_project(db_path, "ver_test")
        bible = StyleBible(project_id="ver_test", name="V1", genre="玄幻")
        repo.save_style_bible("ver_test", bible.to_storage_dict())

        # Drop the style_bible_versions table to force snapshot failure
        conn = get_connection(db_path)
        conn.execute("DROP TABLE style_bible_versions")
        conn.commit()
        conn.close()

        # update_style_bible should raise (OperationalError from missing table)
        bible.genre = "仙侠"
        with pytest.raises(Exception):
            repo.update_style_bible("ver_test", bible.to_storage_dict(), change_summary="Should fail")

        # Verify the Style Bible was NOT updated (atomic rollback)
        current = repo.get_style_bible("ver_test")
        assert current["bible"]["genre"] == "玄幻"
