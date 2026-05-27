"""
v6.7.2 Memory Dedup & Preflight Hardening

Tests for:
1. Lightweight preflight checks (duplicate detection, memory pressure warnings)
2. Run guard integration with preflight diagnostics

Note: Memory write dedup guards (characters.create → update, world_settings.create → update)
are tested in tests/test_v532_memory_loop.py via API route tests.
"""

import os
import sqlite3
import tempfile

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository


@pytest.fixture
def repo():
    """Create a temporary database and repository for testing."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = temp_file.name
    temp_file.close()
    init_db(db_path)
    repo_obj = Repository(db_path)
    yield repo_obj, db_path
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestPreflightDiagnostics:
    """Test lightweight preflight checks before chapter generation."""

    def test_preflight_detects_duplicate_characters(self, repo):
        """Preflight should detect duplicate character names."""
        repo_obj, db_path = repo
        project_id = "v672-preflight-dup-chars"
        repo_obj.create_project(
            project_id=project_id,
            name="Preflight Dup Chars",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )

        # Create two characters with same name (simulating edge case)
        repo_obj.create_character(
            project_id=project_id,
            name="陆澈",
            role="protagonist",
            description="调查局人员",
            traits="",
            first_appearance=1,
        )
        # Directly insert duplicate via raw SQL to simulate edge case
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO characters (project_id, name, role, description, traits, first_appearance)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, "陆澈", "secondary", "另一个陆澈", "", 2),
        )
        conn.commit()
        conn.close()

        from novel_factory.ops.preflight import check_preflight_diagnostics

        result = check_preflight_diagnostics(repo_obj, project_id)

        # Should have duplicate character warning
        dup_char_warnings = [w for w in result.warnings if w.code == "duplicate_characters"]
        assert len(dup_char_warnings) == 1
        assert "陆澈" in dup_char_warnings[0].details["examples"]

    def test_preflight_detects_duplicate_world_settings(self, repo):
        """Preflight should detect duplicate world_setting titles."""
        repo_obj, db_path = repo
        project_id = "v672-preflight-dup-world"
        repo_obj.create_project(
            project_id=project_id,
            name="Preflight Dup World",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )

        # Create two world settings with same title
        repo_obj.create_world_setting(
            project_id=project_id,
            category="城市系统",
            title="潮汐能源城邦",
            content="城市依赖潮汐能源系统运行。",
        )
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO world_settings (project_id, category, title, content)
               VALUES (?, ?, ?, ?)""",
            (project_id, "城市系统", "潮汐能源城邦", "重复的世界观设定"),
        )
        conn.commit()
        conn.close()

        from novel_factory.ops.preflight import check_preflight_diagnostics

        result = check_preflight_diagnostics(repo_obj, project_id)

        # Should have duplicate world_setting warning
        dup_world_warnings = [w for w in result.warnings if w.code == "duplicate_world_settings"]
        assert len(dup_world_warnings) == 1
        assert "潮汐能源城邦" in dup_world_warnings[0].details["examples"]

    def test_preflight_detects_story_facts_pressure(self, repo):
        """Preflight should detect story facts pressure warnings."""
        repo_obj, db_path = repo
        project_id = "v672-preflight-pressure"
        repo_obj.create_project(
            project_id=project_id,
            name="Preflight Pressure",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )

        # Add many story facts to trigger pressure warning
        import json
        for i in range(150):
            repo_obj.create_story_fact(
                project_id=project_id,
                fact_key=f"fact_{i}",
                fact_type="plot",
                value_json=json.dumps({"content": f"故事事实 {i}"}),
                source_chapter=1,
            )

        from novel_factory.ops.preflight import check_preflight_diagnostics

        result = check_preflight_diagnostics(repo_obj, project_id, limits={"story_facts": 100})

        # Should have story facts pressure warning
        pressure_warnings = [w for w in result.warnings if w.code == "story_facts_pressure"]
        assert len(pressure_warnings) == 1
        assert pressure_warnings[0].details["count"] == 150
        assert pressure_warnings[0].details["limit"] == 100

    def test_preflight_detects_memory_items_pressure(self, repo):
        """Preflight should detect memory items pressure warnings."""
        repo_obj, db_path = repo
        project_id = "v672-preflight-memory-pressure"
        repo_obj.create_project(
            project_id=project_id,
            name="Preflight Memory Pressure",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )

        # Add many memory update items to trigger pressure warning
        import json
        batch = repo_obj.create_memory_batch(project_id)
        batch_id = batch["id"]
        for i in range(300):
            repo_obj.create_memory_item(
                batch_id=batch_id,
                project_id=project_id,
                target_table="characters",
                operation="create",
                after_json=json.dumps({"name": f"角色{i}"}),
            )

        from novel_factory.ops.preflight import check_preflight_diagnostics

        result = check_preflight_diagnostics(repo_obj, project_id, limits={"memory_items": 200})

        # Should have memory items pressure warning
        pressure_warnings = [w for w in result.warnings if w.code == "memory_items_pressure"]
        assert len(pressure_warnings) == 1
        assert pressure_warnings[0].details["count"] == 300
        assert pressure_warnings[0].details["limit"] == 200

    def test_preflight_detects_context_pressure(self, repo):
        """Preflight should detect context character pressure warnings."""
        repo_obj, db_path = repo
        project_id = "v672-preflight-context-pressure"
        repo_obj.create_project(
            project_id=project_id,
            name="Preflight Context Pressure",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )

        # Add many characters with long descriptions to trigger context pressure
        for i in range(100):
            repo_obj.create_character(
                project_id=project_id,
                name=f"角色{i}",
                role="secondary",
                description="这是一个很长的角色描述，用于测试上下文字符压力检测功能。" * 10,
                traits="",
                first_appearance=1,
            )

        from novel_factory.ops.preflight import check_preflight_diagnostics

        result = check_preflight_diagnostics(repo_obj, project_id, limits={"context_chars": 10000})

        # Should have context pressure warning
        pressure_warnings = [w for w in result.warnings if w.code == "context_pressure"]
        assert len(pressure_warnings) == 1
        assert pressure_warnings[0].details["count"] > 10000
        assert pressure_warnings[0].details["limit"] == 10000

    def test_preflight_returns_empty_when_no_issues(self, repo):
        """Preflight should return no warnings when there are no issues."""
        repo_obj, db_path = repo
        project_id = "v672-preflight-clean"
        repo_obj.create_project(
            project_id=project_id,
            name="Preflight Clean",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )

        # Add a few items, well under limits
        repo_obj.create_character(
            project_id=project_id,
            name="陆澈",
            role="protagonist",
            description="调查局人员",
            traits="",
            first_appearance=1,
        )
        repo_obj.create_world_setting(
            project_id=project_id,
            category="城市系统",
            title="潮汐能源城邦",
            content="城市依赖潮汐能源系统运行。",
        )
        import json
        repo_obj.create_story_fact(
            project_id=project_id,
            fact_key="fact_1",
            fact_type="plot",
            value_json=json.dumps({"content": "故事事实"}),
            source_chapter=1,
        )

        from novel_factory.ops.preflight import check_preflight_diagnostics

        result = check_preflight_diagnostics(repo_obj, project_id)

        # Should have no warnings
        assert len(result.warnings) == 0


class TestRunGuardPreflightIntegration:
    """Test integration of preflight diagnostics with run guards."""

    def test_run_guard_returns_preflight_warnings(self, repo):
        """Run guard should return preflight warnings alongside guard errors."""
        repo_obj, db_path = repo
        project_id = "v672-guard-preflight"
        repo_obj.create_project(
            project_id=project_id,
            name="Guard Preflight",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        repo_obj.add_chapter(project_id, 1, "第 1 章", status="planned")

        # Create duplicate characters to trigger preflight warning
        repo_obj.create_character(
            project_id=project_id,
            name="陆澈",
            role="protagonist",
            description="调查局人员",
            traits="",
            first_appearance=1,
        )
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO characters (project_id, name, role, description, traits, first_appearance)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, "陆澈", "secondary", "另一个陆澈", "", 2),
        )
        conn.commit()
        conn.close()

        from novel_factory.api.routes._run_guards import check_chapter_run_guard

        # Guard should fail due to missing context, but also return preflight warnings
        guard_error, preflight_warnings = check_chapter_run_guard(repo_obj, project_id, 1)

        # Guard error should exist (missing context)
        assert guard_error is not None
        assert guard_error.code == "CONTEXT_INCOMPLETE"

        # Preflight warnings should also be returned
        assert len(preflight_warnings) > 0
        dup_char_warnings = [w for w in preflight_warnings if w["code"] == "duplicate_characters"]
        assert len(dup_char_warnings) == 1

    def test_run_guard_returns_preflight_warnings_on_success(self, repo):
        """Run guard should return preflight warnings even when guard passes."""
        repo_obj, db_path = repo
        project_id = "v672-guard-preflight-success"
        repo_obj.create_project(
            project_id=project_id,
            name="Guard Preflight Success",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        repo_obj.add_chapter(project_id, 1, "第 1 章", status="planned")

        # Set up complete context
        repo_obj.create_genesis_run(project_id, input_json='{"title":"test"}', status="approved")
        repo_obj.create_world_setting(project_id, category="世界观", title="背景", content="test")
        repo_obj.create_character(project_id, name="主角", role="protagonist", description="test", traits="", first_appearance=1)
        repo_obj.create_outline(project_id, level="volume", sequence=1, title="第一卷", content="test", chapters_range="1-10")
        repo_obj.create_instruction(project_id, chapter_number=1, objective="test", key_events="test")

        # Create duplicate to trigger preflight warning
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO characters (project_id, name, role, description, traits, first_appearance)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, "主角", "secondary", "另一个主角", "", 2),
        )
        conn.commit()
        conn.close()

        from novel_factory.api.routes._run_guards import check_chapter_run_guard

        # Guard should pass, but preflight warnings should still be returned
        guard_error, preflight_warnings = check_chapter_run_guard(repo_obj, project_id, 1)

        # Guard error should not exist
        assert guard_error is None

        # Preflight warnings should still be returned
        assert len(preflight_warnings) > 0
        dup_char_warnings = [w for w in preflight_warnings if w["code"] == "duplicate_characters"]
        assert len(dup_char_warnings) == 1


class TestAPISuccessPathPreflight:
    """Test that preflight warnings are exposed in API success responses."""

    def test_run_chapter_sync_exposes_preflight_warnings(self, repo):
        """POST /run/chapter sync should include preflight_warnings on success."""
        import json
        from fastapi.testclient import TestClient
        from novel_factory.api_app import create_api_app

        repo_obj, db_path = repo
        project_id = "v672-api-sync-preflight"
        repo_obj.create_project(
            project_id=project_id,
            name="API Sync Preflight",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        repo_obj.add_chapter(project_id, 1, "第 1 章", status="planned")

        # Set up complete context
        repo_obj.create_genesis_run(project_id, input_json='{"title":"test"}', status="approved")
        repo_obj.create_world_setting(project_id, category="世界观", title="背景", content="test")
        repo_obj.create_character(project_id, name="主角", role="protagonist", description="test", traits="", first_appearance=1)
        repo_obj.create_outline(project_id, level="volume", sequence=1, title="第一卷", content="test", chapters_range="1-10")
        repo_obj.create_instruction(project_id, chapter_number=1, objective="test", key_events="test")

        # Create duplicate to trigger preflight warning
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO characters (project_id, name, role, description, traits, first_appearance)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, "主角", "secondary", "另一个主角", "", 2),
        )
        conn.commit()
        conn.close()

        app = create_api_app(db_path=db_path, llm_mode="stub")
        client = TestClient(app)

        response = client.post(
            "/api/run/chapter",
            json={"project_id": project_id, "chapter": 1},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        # v6.7.2: Preflight warnings should be exposed on success
        assert "preflight_warnings" in data["data"]
        assert len(data["data"]["preflight_warnings"]) > 0
        dup_char_warnings = [w for w in data["data"]["preflight_warnings"] if w["code"] == "duplicate_characters"]
        assert len(dup_char_warnings) == 1
