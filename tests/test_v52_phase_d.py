"""Tests for v5.2 Phase D: SqliteSaver Checkpoint Persistence."""

import pytest
import tempfile
from pathlib import Path

from novel_factory.workflow.checkpoint import (
    get_sqlite_checkpointer,
    get_checkpoint_thread_id,
    get_checkpoint_config,
    resume_from_checkpoint,
    derive_checkpoint_db_path,
)


class TestCheckpointHelpers:
    """Test checkpoint helper functions."""

    def test_get_checkpoint_thread_id(self):
        """Test thread ID generation."""
        thread_id = get_checkpoint_thread_id("project-123", 5)
        assert thread_id == "project-123-chapter-5"

    def test_get_checkpoint_config(self):
        """Test checkpoint config generation."""
        config = get_checkpoint_config("my-project", 10)
        assert config == {
            "configurable": {
                "thread_id": "my-project-chapter-10",
            }
        }

    def test_get_sqlite_checkpointer_default_path(self):
        """Test SqliteSaver creation with default (in-memory) path."""
        checkpointer = get_sqlite_checkpointer()
        assert checkpointer is not None
        # Should be a context manager
        assert hasattr(checkpointer, "__enter__")
        assert hasattr(checkpointer, "__exit__")

    def test_get_sqlite_checkpointer_custom_path(self):
        """Test SqliteSaver creation with custom path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_checkpoints.db"
            checkpointer = get_sqlite_checkpointer(db_path)
            assert checkpointer is not None


class TestCheckpointPersistence:
    """Test checkpoint persistence and recovery."""

    def test_derive_checkpoint_db_path_from_repo(self):
        """Checkpoint path should be derived from the main DB path."""
        result = derive_checkpoint_db_path("/tmp/my_novel.db")
        assert result == Path("/tmp/my_novel.checkpoints.db")

    def test_derive_checkpoint_db_path_none_returns_none(self):
        """No repo DB path means no persistent checkpoint (in-memory)."""
        result = derive_checkpoint_db_path(None)
        assert result is None

    def test_derive_checkpoint_db_path_memory_returns_none(self):
        """:memory: DB should use in-memory checkpoints, not a repo-root file."""
        result = derive_checkpoint_db_path(":memory:")
        assert result is None

    def test_derive_checkpoint_db_path_nested(self):
        """Checkpoint path works for nested directories."""
        result = derive_checkpoint_db_path("/data/projects/abc/main.db")
        assert result == Path("/data/projects/abc/main.checkpoints.db")

    def test_temp_db_does_not_write_repo_root(self, tmp_path):
        """When using a temp DB, checkpoint must NOT be written to the repo root."""
        from novel_factory.workflow.runner import run_with_graph
        from novel_factory.config.settings import load_settings
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        db_path = str(tmp_path / "temp_test.db")
        repo = Repository(db_path)
        init_db(db_path)

        # Seed minimal project + context for Context Readiness Gate
        conn = repo._conn()
        try:
            conn.execute(
                "INSERT INTO projects (project_id, name, genre, total_chapters_planned, description, target_words) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("test-no-repo-root", "Test", "fantasy", 10, "测试项目简介", 100000),
            )
            conn.execute(
                "INSERT INTO chapters (project_id, chapter_number, status, title) "
                "VALUES (?, ?, ?, ?)",
                ("test-no-repo-root", 1, "planned", "Ch1"),
            )
            conn.execute(
                "INSERT INTO world_settings (project_id, category, title, content) "
                "VALUES (?, 'world', '世界观', '修仙世界')",
                ("test-no-repo-root",),
            )
            conn.execute(
                "INSERT INTO characters (project_id, name, role, description, status) "
                "VALUES (?, '主角', 'protagonist', '主角描述', 'active')",
                ("test-no-repo-root",),
            )
            conn.execute(
                "INSERT INTO outlines (project_id, level, sequence, title, chapters_range, content) "
                "VALUES (?, 'chapter', 1, '第一卷', '1-10', '大纲摘要')",
                ("test-no-repo-root",),
            )
            conn.execute(
                "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
                "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
                "VALUES (?, ?, '测试目标', '[]', '[]', '[]', '悬念', 2500, 'active')",
                ("test-no-repo-root", 1),
            )
            conn.commit()
        finally:
            conn.close()

        settings = load_settings()
        result = run_with_graph(
            project_id="test-no-repo-root",
            chapter_number=1,
            settings=settings,
            repo=repo,
            llm_mode="stub",
        )

        # Workflow should succeed
        assert result["error"] is None

        # Checkpoint must be alongside the temp DB, NOT in repo root
        repo_root = Path(__file__).resolve().parent.parent
        assert not (repo_root / "checkpoints.db").exists(), (
            "Checkpoint DB must NOT be created in the repo root"
        )

        # Checkpoint should be next to the temp DB
        expected_cp = Path(db_path).parent / f"{Path(db_path).stem}.checkpoints.db"
        assert expected_cp.exists(), (
            f"Checkpoint DB should be at {expected_cp}"
        )

    def test_checkpointer_basic_operations(self):
        """Test basic checkpointer put/get operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            with get_sqlite_checkpointer(db_path) as checkpointer:
                # Checkpointer should have required methods
                assert hasattr(checkpointer, "put")
                assert hasattr(checkpointer, "get")
                assert hasattr(checkpointer, "get_tuple")

    def test_checkpoint_config_thread_isolation(self):
        """Test that different chapters have different thread IDs."""
        config1 = get_checkpoint_config("project-A", 1)
        config2 = get_checkpoint_config("project-A", 2)
        config3 = get_checkpoint_config("project-B", 1)

        assert config1["configurable"]["thread_id"] != config2["configurable"]["thread_id"]
        assert config1["configurable"]["thread_id"] != config3["configurable"]["thread_id"]
        assert config2["configurable"]["thread_id"] != config3["configurable"]["thread_id"]


class TestCheckpointIntegration:
    """Test checkpoint integration with workflow runner."""

    def test_run_with_graph_creates_checkpoint(self, tmp_path):
        """Test that run_with_graph creates a checkpoint file."""
        from novel_factory.workflow.runner import run_with_graph
        from novel_factory.config.settings import load_settings
        from novel_factory.db.repository import Repository

        # Create test database
        db_path = str(tmp_path / "test.db")
        repo = Repository(db_path)

        # Initialize database schema
        from novel_factory.db.connection import init_db
        init_db(db_path)

        # Create test project, chapter, and context for readiness gate
        conn = repo._conn()
        try:
            conn.execute(
                "INSERT INTO projects (project_id, name, genre, total_chapters_planned, description, target_words) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("test-checkpoint-project", "Test Project", "fantasy", 10, "测试简介", 100000),
            )
            conn.execute(
                "INSERT INTO chapters (project_id, chapter_number, status, title) "
                "VALUES (?, ?, ?, ?)",
                ("test-checkpoint-project", 1, "planned", "Chapter 1"),
            )
            conn.execute(
                "INSERT INTO world_settings (project_id, category, title, content) "
                "VALUES (?, 'world', '世界观', '修仙世界')",
                ("test-checkpoint-project",),
            )
            conn.execute(
                "INSERT INTO characters (project_id, name, role, description, status) "
                "VALUES (?, '主角', 'protagonist', '主角描述', 'active')",
                ("test-checkpoint-project",),
            )
            conn.execute(
                "INSERT INTO outlines (project_id, level, sequence, title, chapters_range, content) "
                "VALUES (?, 'chapter', 1, '第一卷', '1-10', '大纲摘要')",
                ("test-checkpoint-project",),
            )
            conn.execute(
                "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
                "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
                "VALUES (?, ?, '测试目标', '[]', '[]', '[]', '悬念', 2500, 'active')",
                ("test-checkpoint-project", 1),
            )
            conn.commit()
        finally:
            conn.close()

        # Run workflow
        settings = load_settings()
        result = run_with_graph(
            project_id="test-checkpoint-project",
            chapter_number=1,
            settings=settings,
            repo=repo,
            llm_mode="stub",
        )

        # Verify result
        assert result["run_id"] != ""
        assert result["chapter_status"] == "published"
        assert result["error"] is None

        # Note: checkpoint database is created alongside the main DB
        # (derived via derive_checkpoint_db_path), not in the repo root.
        # Verify the checkpoint file exists next to the main DB.
        checkpoint_path = Path(db_path).parent / f"{Path(db_path).stem}.checkpoints.db"
        assert checkpoint_path.exists(), (
            f"Checkpoint DB should be created at {checkpoint_path}, not in repo root"
        )
