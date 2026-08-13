"""
v6.7.3 Preflight UX & Regression Closure

Tests for:
1. API success paths expose preflight warnings (background start, SSE, auto-run)
2. Enhanced preflight warning details (groups, ids, recommended_actions)
3. Preflight failure resilience (preflight_failed warning without blocking)
"""

import json
import os
import sqlite3
import tempfile

import pytest
from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app
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


def _seed_full_context(repo_obj, project_id):
    """Seed a project with complete context for chapter generation."""
    repo_obj.create_genesis_run(project_id, input_json='{"title":"test"}', status="approved")
    repo_obj.create_world_setting(project_id, category="世界观", title="背景", content="test")
    repo_obj.create_character(project_id, name="主角", role="protagonist", description="test", traits="", first_appearance=1)
    repo_obj.create_outline(project_id, level="volume", sequence=1, title="第一卷", content="test", chapters_range="1-10")
    repo_obj.create_instruction(project_id, chapter_number=1, objective="test", key_events="test")


def _create_duplicate_characters(repo_obj, db_path, project_id):
    """Create duplicate characters to trigger preflight warning."""
    repo_obj.create_character(
        project_id=project_id,
        name="陆澈",
        role="secondary",
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


class TestBackgroundStartPreflight:
    """Test preflight warnings exposed in background start success path."""

    def test_background_start_exposes_preflight_warnings(self, repo):
        """POST /run/chapter/start should include preflight_warnings on success."""
        repo_obj, db_path = repo
        project_id = "v673-bg-start-preflight"
        repo_obj.create_project(
            project_id=project_id,
            name="BG Start Preflight",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        repo_obj.add_chapter(project_id, 1, "第 1 章", status="planned")
        _seed_full_context(repo_obj, project_id)
        _create_duplicate_characters(repo_obj, db_path, project_id)

        app = create_api_app(db_path=db_path, llm_mode="stub")
        client = TestClient(app)

        response = client.post(
            "/api/run/chapter/start",
            json={"project_id": project_id, "chapter": 1},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "preflight_warnings" in data["data"]
        assert len(data["data"]["preflight_warnings"]) > 0
        dup_warnings = [w for w in data["data"]["preflight_warnings"] if w["code"] == "duplicate_characters"]
        assert len(dup_warnings) == 1

    def test_background_start_no_warnings_when_clean(self, repo):
        """Background start should have empty preflight_warnings when no issues."""
        repo_obj, db_path = repo
        project_id = "v673-bg-start-clean"
        repo_obj.create_project(
            project_id=project_id,
            name="BG Start Clean",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        repo_obj.add_chapter(project_id, 1, "第 1 章", status="planned")
        _seed_full_context(repo_obj, project_id)

        app = create_api_app(db_path=db_path, llm_mode="stub")
        client = TestClient(app)

        response = client.post(
            "/api/run/chapter/start",
            json={"project_id": project_id, "chapter": 1},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "preflight_warnings" in data["data"]
        assert len(data["data"]["preflight_warnings"]) == 0


class TestSSEPreflightEvent:
    """Test preflight warnings exposed in SSE stream initial event."""

    def test_sse_emits_preflight_warnings_event(self, repo):
        """SSE stream (/run/chapter/stream) should emit preflight_warnings as initial event."""
        repo_obj, db_path = repo
        project_id = "v673-sse-preflight"
        repo_obj.create_project(
            project_id=project_id,
            name="SSE Preflight",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        repo_obj.add_chapter(project_id, 1, "第 1 章", status="planned")
        _seed_full_context(repo_obj, project_id)
        _create_duplicate_characters(repo_obj, db_path, project_id)

        app = create_api_app(db_path=db_path, llm_mode="stub")
        client = TestClient(app)

        # Connect directly to SSE stream endpoint
        response = client.get(
            f"/api/run/chapter/stream?project_id={project_id}&chapter=1",
            headers={"Accept": "text/event-stream"},
        )
        assert response.status_code == 200

        # Parse SSE events from response body
        events = []
        for line in response.text.strip().split("\n"):
            if line.startswith("data: "):
                try:
                    events.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    pass

        # Check for preflight_warnings event
        preflight_events = [e for e in events if e.get("type") == "preflight_warnings"]
        assert len(preflight_events) == 1
        assert len(preflight_events[0]["warnings"]) > 0
        dup_warnings = [w for w in preflight_events[0]["warnings"] if w["code"] == "duplicate_characters"]
        assert len(dup_warnings) == 1

    def test_sse_no_preflight_event_when_clean(self, repo):
        """SSE stream should not emit preflight event when no warnings."""
        repo_obj, db_path = repo
        project_id = "v673-sse-clean"
        repo_obj.create_project(
            project_id=project_id,
            name="SSE Clean",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        repo_obj.add_chapter(project_id, 1, "第 1 章", status="planned")
        _seed_full_context(repo_obj, project_id)

        app = create_api_app(db_path=db_path, llm_mode="stub")
        client = TestClient(app)

        response = client.get(
            f"/api/run/chapter/stream?project_id={project_id}&chapter=1",
            headers={"Accept": "text/event-stream"},
        )
        assert response.status_code == 200

        events = []
        for line in response.text.strip().split("\n"):
            if line.startswith("data: "):
                try:
                    events.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    pass

        preflight_events = [e for e in events if e.get("type") == "preflight_warnings"]
        assert len(preflight_events) == 0


class TestProductionAutoRunPreflight:
    """Test preflight warnings exposed in production auto-run success path."""

    @pytest.mark.asyncio
    async def test_production_autorun_exposes_preflight_warnings(self, repo, monkeypatch):
        """Production auto-run generate_chapter step should include preflight_warnings."""
        repo_obj, db_path = repo
        project_id = "v673-autorun-preflight"
        repo_obj.create_project(
            project_id=project_id,
            name="AutoRun Preflight",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        repo_obj.add_chapter(project_id, 1, "第 1 章", status="planned")
        _seed_full_context(repo_obj, project_id)
        _create_duplicate_characters(repo_obj, db_path, project_id)

        from novel_factory.api.routes.production import _execute_auto_step
        from novel_factory.config.loader import load_settings_with_cli as load_settings
        import novel_factory.workflow.runner as workflow_runner

        def fake_run_with_graph(*, project_id, chapter_number, settings, repo, llm_mode):
            assert chapter_number == 1
            return {
                "run_id": "v673-fake-run",
                "chapter_status": "awaiting_publish",
                "requires_human": True,
                "awaiting_publish": True,
            }

        monkeypatch.setattr(workflow_runner, "run_with_graph", fake_run_with_graph)
        settings = load_settings()
        settings.db_path = db_path

        result = await _execute_auto_step(
            request=None,
            repo=repo_obj,
            settings=settings,
            llm_mode="stub",
            project_id=project_id,
            next_action={"key": "generate_chapter", "label": "生成第 1 章", "target_chapter": 1},
            ch_start=1,
            ch_end=10,
            active_chapter=1,
        )

        assert result["result"] == "success"
        assert "preflight_warnings" in result
        assert len(result["preflight_warnings"]) > 0
        dup_warnings = [w for w in result["preflight_warnings"] if w["code"] == "duplicate_characters"]
        assert len(dup_warnings) == 1
        # Verify enhanced details
        assert "groups" in dup_warnings[0]["details"]
        assert "recommended_actions" in dup_warnings[0]["details"]

    @pytest.mark.asyncio
    async def test_production_autorun_returns_empty_preflight_warnings_when_clean(self, repo, monkeypatch):
        """Production auto-run should include preflight_warnings even when clean."""
        repo_obj, db_path = repo
        project_id = "v673-autorun-clean"
        repo_obj.create_project(
            project_id=project_id,
            name="AutoRun Clean",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        repo_obj.add_chapter(project_id, 1, "第 1 章", status="planned")
        _seed_full_context(repo_obj, project_id)

        from novel_factory.api.routes.production import _execute_auto_step
        from novel_factory.config.loader import load_settings_with_cli as load_settings
        import novel_factory.workflow.runner as workflow_runner

        def fake_run_with_graph(*, project_id, chapter_number, settings, repo, llm_mode):
            return {
                "run_id": "v673-fake-clean-run",
                "chapter_status": "awaiting_publish",
                "requires_human": True,
                "awaiting_publish": True,
            }

        monkeypatch.setattr(workflow_runner, "run_with_graph", fake_run_with_graph)
        settings = load_settings()
        settings.db_path = db_path

        result = await _execute_auto_step(
            request=None,
            repo=repo_obj,
            settings=settings,
            llm_mode="stub",
            project_id=project_id,
            next_action={"key": "generate_chapter", "label": "生成第 1 章", "target_chapter": 1},
            ch_start=1,
            ch_end=10,
            active_chapter=1,
        )

        assert result["result"] == "success"
        assert "preflight_warnings" in result
        assert result["preflight_warnings"] == []


class TestPreflightWarningDetails:
    """Test enhanced preflight warning details."""

    def test_duplicate_character_warning_has_groups_and_actions(self, repo):
        """Duplicate character warning should include groups and recommended_actions."""
        repo_obj, db_path = repo
        project_id = "v673-dup-char-details"
        repo_obj.create_project(
            project_id=project_id,
            name="Dup Char Details",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        _create_duplicate_characters(repo_obj, db_path, project_id)

        from novel_factory.ops.preflight import check_preflight_diagnostics

        result = check_preflight_diagnostics(repo_obj, project_id)
        dup_warnings = [w for w in result.warnings if w.code == "duplicate_characters"]
        assert len(dup_warnings) == 1

        details = dup_warnings[0].details
        assert "count" in details
        assert "examples" in details
        assert "groups" in details
        assert "recommended_actions" in details

        # groups should have ids and display_values
        if details["groups"]:
            group = details["groups"][0]
            assert "value" in group
            assert "count" in group
            assert "table" in group
            assert "ids" in group
            assert "display_values" in group

        # recommended_actions should be non-empty
        assert len(details["recommended_actions"]) > 0
        action = details["recommended_actions"][0]
        assert "code" in action
        assert "label" in action
        assert "severity" in action

    def test_duplicate_world_setting_warning_has_groups_and_actions(self, repo):
        """Duplicate world_setting warning should include groups and recommended_actions."""
        repo_obj, db_path = repo
        project_id = "v673-dup-world-details"
        repo_obj.create_project(
            project_id=project_id,
            name="Dup World Details",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
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
        dup_warnings = [w for w in result.warnings if w.code == "duplicate_world_settings"]
        assert len(dup_warnings) == 1

        details = dup_warnings[0].details
        assert "groups" in details
        assert "recommended_actions" in details

    def test_pressure_warnings_have_recommended_actions(self, repo):
        """Pressure warnings should include recommended_actions."""
        repo_obj, db_path = repo
        project_id = "v673-pressure-actions"
        repo_obj.create_project(
            project_id=project_id,
            name="Pressure Actions",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )

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
        pressure_warnings = [w for w in result.warnings if w.code == "story_facts_pressure"]
        assert len(pressure_warnings) == 1

        details = pressure_warnings[0].details
        assert "recommended_actions" in details
        assert len(details["recommended_actions"]) > 0
        action = details["recommended_actions"][0]
        assert "code" in action
        assert "label" in action

    def test_context_pressure_has_recommended_actions(self, repo):
        """Context pressure warning should include recommended_actions."""
        repo_obj, db_path = repo
        project_id = "v673-context-pressure-actions"
        repo_obj.create_project(
            project_id=project_id,
            name="Context Pressure Actions",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )

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
        pressure_warnings = [w for w in result.warnings if w.code == "context_pressure"]
        assert len(pressure_warnings) == 1

        details = pressure_warnings[0].details
        assert "recommended_actions" in details
        assert len(details["recommended_actions"]) > 0


class TestPreflightFailureResilience:
    """Test preflight failure does not block chapter generation."""

    def test_preflight_failure_returns_warning_not_error(self, repo):
        """When preflight throws, run guard should return preflight_failed warning."""
        repo_obj, db_path = repo
        project_id = "v673-preflight-failure"
        repo_obj.create_project(
            project_id=project_id,
            name="Preflight Failure",
            genre="fantasy",
            description="test",
            target_words=30000,
            total_chapters_planned=10,
        )
        repo_obj.add_chapter(project_id, 1, "第 1 章", status="planned")
        _seed_full_context(repo_obj, project_id)

        from novel_factory.api.routes._run_guards import check_chapter_run_guard

        # Temporarily break preflight by monkeypatching
        import novel_factory.ops.preflight as preflight_module
        original_fn = preflight_module.check_preflight_diagnostics

        def broken_preflight(*args, **kwargs):
            raise RuntimeError("Simulated preflight failure")

        preflight_module.check_preflight_diagnostics = broken_preflight
        try:
            guard_error, preflight_warnings = check_chapter_run_guard(repo_obj, project_id, 1)
            # Guard should pass (context is complete)
            assert guard_error is None
            # But preflight should have failed gracefully
            assert len(preflight_warnings) == 1
            assert preflight_warnings[0]["code"] == "preflight_failed"
            assert "severity" in preflight_warnings[0]
            assert preflight_warnings[0]["severity"] == "info"
        finally:
            preflight_module.check_preflight_diagnostics = original_fn
