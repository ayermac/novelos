"""v5.5.3 Autonomous Production Loop Tests.

Tests for:
1. GET /api/projects/{id}/production-next returns correct next_action
2. POST /api/projects/{id}/production/auto-fill creates missing context
3. POST /api/projects/{id}/production/arc-plan generates arc outlines + instructions
4. Auto-fill does not overwrite existing user content
5. Frontend source contains required copy
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """Create test client with initialized database."""
    from novel_factory.api_app import create_api_app
    from novel_factory.db.connection import init_db

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    test_client = TestClient(app)
    yield test_client
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture()
def project_id(client):
    """Create a project and return its ID."""
    resp = client.post("/api/onboarding/projects", json={
        "project_id": "test-auto-prod",
        "name": "Test Auto Production",
        "genre": "奇幻",
        "description": "A test novel",
        "total_chapters_planned": 10,
        "target_words": 30000,
    })
    assert resp.status_code == 200
    data = resp.json()
    pid = data.get("data", {}).get("project", {}).get("project_id")
    assert pid, f"Expected project ID, got: {data}"
    return pid


class TestProductionNextAPI:
    """GET /api/projects/{id}/production-next decision logic."""

    def test_new_project_returns_generate_genesis(self, client, project_id):
        """1. New project without genesis should suggest generate_genesis."""
        resp = client.get(f"/api/projects/{project_id}/production-next")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["next_action"]["key"] == "generate_genesis"
        assert data["health"]["has_genesis"] is False
        assert data["health"]["has_approved_genesis"] is False
        assert len(data["missing"]) >= 1

    def test_pending_genesis_returns_review_genesis(self, client, project_id):
        """2. Project with generated (but not approved) genesis should suggest review."""
        # Generate genesis first
        gen_resp = client.post(f"/api/projects/{project_id}/genesis/generate", json={
            "title": "Test Novel",
            "genre": "奇幻",
            "premise": "A test premise",
            "target_chapters": 10,
            "target_words": 30000,
        })
        assert gen_resp.status_code == 200
        assert gen_resp.json()["ok"] is True

        resp = client.get(f"/api/projects/{project_id}/production-next")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["next_action"]["key"] == "review_genesis"
        assert data["health"]["has_genesis"] is True
        assert data["health"]["has_approved_genesis"] is False

    def test_approved_genesis_missing_context_returns_generate_missing(self, client, project_id):
        """3. Approved genesis but missing context should suggest auto-fill."""
        # Generate and approve genesis
        gen_resp = client.post(f"/api/projects/{project_id}/genesis/generate", json={
            "title": "Test Novel",
            "genre": "奇幻",
            "premise": "A test premise",
            "target_chapters": 10,
            "target_words": 30000,
        })
        assert gen_resp.status_code == 200
        genesis_id = gen_resp.json()["data"]["id"]

        app_resp = client.post(f"/api/projects/{project_id}/genesis/{genesis_id}/approve")
        assert app_resp.status_code == 200
        assert app_resp.json()["ok"] is True

        # Delete all created context to simulate missing context
        ws_resp = client.get(f"/api/projects/{project_id}/world-settings")
        for ws in ws_resp.json().get("data", []):
            client.delete(f"/api/projects/{project_id}/world-settings/{ws['id']}")
        ch_resp = client.get(f"/api/projects/{project_id}/characters")
        for ch in ch_resp.json().get("data", []):
            client.delete(f"/api/projects/{project_id}/characters/{ch['id']}")
        ol_resp = client.get(f"/api/projects/{project_id}/outlines")
        for ol in ol_resp.json().get("data", []):
            client.delete(f"/api/projects/{project_id}/outlines/{ol['id']}")
        inst_resp = client.get(f"/api/projects/{project_id}/instructions")
        for inst in inst_resp.json().get("data", []):
            client.delete(f"/api/projects/{project_id}/instructions/{inst['id']}")

        resp = client.get(f"/api/projects/{project_id}/production-next")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["health"]["has_approved_genesis"] is True
        assert data["next_action"]["key"] == "generate_missing_context"
        assert len(data["missing"]) >= 1

    def test_ready_context_planned_chapter_returns_generate_chapter(self, client, project_id):
        """4. Planned chapter with ready context should suggest generate_chapter."""
        # Generate and approve genesis
        gen_resp = client.post(f"/api/projects/{project_id}/genesis/generate", json={
            "title": "Test Novel",
            "genre": "奇幻",
            "premise": "A test premise",
            "target_chapters": 10,
            "target_words": 30000,
        })
        assert gen_resp.status_code == 200
        genesis_id = gen_resp.json()["data"]["id"]
        client.post(f"/api/projects/{project_id}/genesis/{genesis_id}/approve")

        # Ensure chapter 1 exists in planned status
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db
        # We can't easily access repo from client; instead use auto-fill to ensure instructions exist
        client.post(f"/api/projects/{project_id}/production/auto-fill", json={
            "scope": "missing_context", "chapter_start": 1, "chapter_end": 10, "confirm": True,
        })

        resp = client.get(f"/api/projects/{project_id}/production-next")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        # With approved genesis and instructions present, next action must be generate_chapter
        assert data["next_action"]["key"] == "generate_chapter"

    def test_blocking_chapter_returns_recover_blocked_run(self, client, project_id):
        """5. Blocking chapter should suggest recover_blocked_run."""
        from novel_factory.api_app import create_api_app
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        app = create_api_app(db_path=db_path, llm_mode="stub")
        tc = TestClient(app)
        tc.post("/api/onboarding/projects", json={
            "project_id": "block-test", "name": "Block Test", "genre": "奇幻",
            "description": "test", "total_chapters_planned": 10, "target_words": 30000,
        })
        tc.post("/api/projects/block-test/genesis/generate", json={
            "title": "T", "genre": "奇幻", "premise": "p", "target_chapters": 10, "target_words": 30000,
        })
        gid = tc.get("/api/projects/block-test/genesis/latest").json()["data"]["id"]
        tc.post(f"/api/projects/block-test/genesis/{gid}/approve")
        tc.post("/api/projects/block-test/production/auto-fill", json={
            "scope": "missing_context", "chapter_start": 1, "chapter_end": 10, "confirm": True,
        })
        # Set chapter to blocking
        repo = Repository(db_path)
        repo.update_chapter_status("block-test", 1, "blocking")

        resp = tc.get("/api/projects/block-test/production-next")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["next_action"]["key"] == "recover_blocked_run"
        assert data["health"]["has_blocking_chapter"] is True
        os.unlink(db_path)

    def test_pending_memory_updates_returns_apply_memory_updates(self, client, project_id):
        """6. Pending memory updates should suggest apply_memory_updates."""
        from novel_factory.api_app import create_api_app
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        app = create_api_app(db_path=db_path, llm_mode="stub")
        tc = TestClient(app)
        tc.post("/api/onboarding/projects", json={
            "project_id": "mem-test", "name": "Mem Test", "genre": "奇幻",
            "description": "test", "total_chapters_planned": 10, "target_words": 30000,
        })
        tc.post("/api/projects/mem-test/genesis/generate", json={
            "title": "T", "genre": "奇幻", "premise": "p", "target_chapters": 10, "target_words": 30000,
        })
        gid = tc.get("/api/projects/mem-test/genesis/latest").json()["data"]["id"]
        tc.post(f"/api/projects/mem-test/genesis/{gid}/approve")
        tc.post("/api/projects/mem-test/production/auto-fill", json={
            "scope": "missing_context", "chapter_start": 1, "chapter_end": 10, "confirm": True,
        })
        # Create a pending memory batch and item
        repo = Repository(db_path)
        batch = repo.create_memory_batch("mem-test", chapter_number=1, summary="test batch")
        repo.create_memory_item(
            batch_id=batch["id"],
            project_id="mem-test",
            target_table="characters",
            operation="update",
            after_json='{"name":"Test"}',
            target_id="1",
        )
        # With all context ready and pending memory, it should suggest apply_memory_updates
        resp = tc.get("/api/projects/mem-test/production-next")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["health"]["has_pending_memory_updates"] is True
        assert data["next_action"]["key"] == "apply_memory_updates"
        os.unlink(db_path)

    def test_old_failure_after_success_ignored(self, client, project_id):
        """7. Same-chapter old failure after later success should NOT suggest recovery."""
        from novel_factory.api_app import create_api_app
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        app = create_api_app(db_path=db_path, llm_mode="stub")
        tc = TestClient(app)
        tc.post("/api/onboarding/projects", json={
            "project_id": "old-fail-test", "name": "Old Fail Test", "genre": "奇幻",
            "description": "test", "total_chapters_planned": 10, "target_words": 30000,
        })
        tc.post("/api/projects/old-fail-test/genesis/generate", json={
            "title": "T", "genre": "奇幻", "premise": "p", "target_chapters": 10, "target_words": 30000,
        })
        gid = tc.get("/api/projects/old-fail-test/genesis/latest").json()["data"]["id"]
        tc.post(f"/api/projects/old-fail-test/genesis/{gid}/approve")
        tc.post("/api/projects/old-fail-test/production/auto-fill", json={
            "scope": "missing_context", "chapter_start": 1, "chapter_end": 10, "confirm": True,
        })

        repo = Repository(db_path)
        # Create an old failed run for chapter 1
        run1 = repo.create_workflow_run("old-fail-test", 1)
        repo.update_workflow_run(run1, status="failed", error_message="old error")
        # Create a newer completed run for chapter 1
        run2 = repo.create_workflow_run("old-fail-test", 1)
        repo.update_workflow_run(run2, status="completed")

        resp = tc.get("/api/projects/old-fail-test/production-next")
        assert resp.status_code == 200
        data = resp.json()["data"]
        # Latest run is completed, so no recovery needed
        assert data["health"]["has_stuck_run"] is False
        assert data["next_action"]["key"] == "generate_chapter"
        os.unlink(db_path)

    def test_published_chapter_returns_continue_next_with_target(self, client, project_id):
        """8. Published chapter should suggest continue_next_chapter with target_chapter=2."""
        from novel_factory.api_app import create_api_app
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        app = create_api_app(db_path=db_path, llm_mode="stub")
        tc = TestClient(app)
        tc.post("/api/onboarding/projects", json={
            "project_id": "pub-test", "name": "Pub Test", "genre": "奇幻",
            "description": "test", "total_chapters_planned": 10, "target_words": 30000,
        })
        tc.post("/api/projects/pub-test/genesis/generate", json={
            "title": "T", "genre": "奇幻", "premise": "p", "target_chapters": 10, "target_words": 30000,
        })
        gid = tc.get("/api/projects/pub-test/genesis/latest").json()["data"]["id"]
        tc.post(f"/api/projects/pub-test/genesis/{gid}/approve")
        tc.post("/api/projects/pub-test/production/auto-fill", json={
            "scope": "missing_context", "chapter_start": 1, "chapter_end": 10, "confirm": True,
        })

        repo = Repository(db_path)
        # Chapter 1 already exists from auto-fill; set it to reviewed then publish
        repo.update_chapter_status("pub-test", 1, "reviewed")
        repo.publish_chapter("pub-test", 1, expected_status="reviewed")
        # Ensure chapter 2 exists
        if repo.get_chapter("pub-test", 2) is None:
            repo.add_chapter("pub-test", 2, "第 2 章", status="planned")

        resp = tc.get("/api/projects/pub-test/production-next")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["next_action"]["key"] == "continue_next_chapter"
        assert data["next_action"].get("target_chapter") == 2
        assert data["health"]["target_chapter"] == 2
        os.unlink(db_path)

    def test_production_next_reports_running_target_chapter(self, client, project_id):
        """Published current chapter should report running workflow on target next chapter."""
        from novel_factory.api_app import create_api_app
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        app = create_api_app(db_path=db_path, llm_mode="stub")
        tc = TestClient(app)
        tc.post("/api/onboarding/projects", json={
            "project_id": "target-run-test", "name": "Target Run Test", "genre": "奇幻",
            "description": "test", "total_chapters_planned": 10, "target_words": 30000,
        })
        tc.post("/api/projects/target-run-test/genesis/generate", json={
            "title": "T", "genre": "奇幻", "premise": "p", "target_chapters": 10, "target_words": 30000,
        })
        gid = tc.get("/api/projects/target-run-test/genesis/latest").json()["data"]["id"]
        tc.post(f"/api/projects/target-run-test/genesis/{gid}/approve")
        tc.post("/api/projects/target-run-test/production/auto-fill", json={
            "scope": "missing_context", "chapter_start": 1, "chapter_end": 10, "confirm": True,
        })

        repo = Repository(db_path)
        repo.update_chapter_status("target-run-test", 1, "reviewed")
        repo.publish_chapter("target-run-test", 1, expected_status="reviewed")
        if repo.get_chapter("target-run-test", 2) is None:
            repo.add_chapter("target-run-test", 2, "第 2 章", status="planned")
        run_id = repo.create_workflow_run("target-run-test", 2)
        repo.update_workflow_run(run_id, status="running", current_node="polisher")

        resp = tc.get("/api/projects/target-run-test/production-next")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["next_action"]["key"] == "continue_next_chapter"
        assert data["next_action"]["target_chapter"] == 2
        assert data["health"]["has_running_chapter_workflow"] is False
        assert data["health"]["has_running_target_workflow"] is True
        assert data["health"]["target_workflow_run_id"] == run_id
        assert data["health"]["target_workflow_current_node"] == "polisher"
        os.unlink(db_path)

    def test_blocking_non_current_chapter_returns_correct_target(self, client, project_id):
        """9. Blocking chapter 2 while current_chapter=9 should target chapter 2."""
        from novel_factory.api_app import create_api_app
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        app = create_api_app(db_path=db_path, llm_mode="stub")
        tc = TestClient(app)
        tc.post("/api/onboarding/projects", json={
            "project_id": "non-curr-test", "name": "Non Curr Test", "genre": "奇幻",
            "description": "test", "total_chapters_planned": 20, "target_words": 60000,
        })
        tc.post("/api/projects/non-curr-test/genesis/generate", json={
            "title": "T", "genre": "奇幻", "premise": "p", "target_chapters": 20, "target_words": 60000,
        })
        gid = tc.get("/api/projects/non-curr-test/genesis/latest").json()["data"]["id"]
        tc.post(f"/api/projects/non-curr-test/genesis/{gid}/approve")
        tc.post("/api/projects/non-curr-test/production/auto-fill", json={
            "scope": "missing_context", "chapter_start": 1, "chapter_end": 10, "confirm": True,
        })

        repo = Repository(db_path)
        # Set current_chapter to 9
        repo.update_chapter_status("non-curr-test", 9, "planned")
        conn = repo._conn()
        conn.execute("UPDATE projects SET current_chapter=? WHERE project_id=?", (9, "non-curr-test"))
        conn.commit()
        conn.close()
        # Block chapter 2
        repo.update_chapter_status("non-curr-test", 2, "blocking")

        resp = tc.get("/api/projects/non-curr-test/production-next")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["next_action"]["key"] == "recover_blocked_run"
        assert data["next_action"].get("target_chapter") == 2
        os.unlink(db_path)

    def test_same_second_runs_use_latest(self, client, project_id):
        """10. Same-second runs should still pick the latest (higher id) run."""
        from novel_factory.api_app import create_api_app
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        app = create_api_app(db_path=db_path, llm_mode="stub")
        tc = TestClient(app)
        tc.post("/api/onboarding/projects", json={
            "project_id": "same-sec-test", "name": "Same Sec Test", "genre": "奇幻",
            "description": "test", "total_chapters_planned": 10, "target_words": 30000,
        })
        tc.post("/api/projects/same-sec-test/genesis/generate", json={
            "title": "T", "genre": "奇幻", "premise": "p", "target_chapters": 10, "target_words": 30000,
        })
        gid = tc.get("/api/projects/same-sec-test/genesis/latest").json()["data"]["id"]
        tc.post(f"/api/projects/same-sec-test/genesis/{gid}/approve")
        tc.post("/api/projects/same-sec-test/production/auto-fill", json={
            "scope": "missing_context", "chapter_start": 1, "chapter_end": 10, "confirm": True,
        })

        repo = Repository(db_path)
        # Insert two runs with the exact same started_at timestamp.
        same_time = "2024-01-01 10:00:00"
        conn = repo._conn()
        conn.execute(
            "INSERT INTO workflow_runs (id, project_id, chapter_number, graph_name, status, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("run-old", "same-sec-test", 1, "chapter_production", "failed", same_time),
        )
        conn.execute(
            "INSERT INTO workflow_runs (id, project_id, chapter_number, graph_name, status, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("run-new", "same-sec-test", 1, "chapter_production", "completed", same_time),
        )
        conn.commit()
        conn.close()

        resp = tc.get("/api/projects/same-sec-test/production-next")
        assert resp.status_code == 200
        data = resp.json()["data"]
        # Higher-id run is completed, so old failed run should be ignored
        assert data["health"]["has_stuck_run"] is False
        assert data["next_action"]["key"] == "generate_chapter"
        os.unlink(db_path)


class TestAutoFillAPI:
    """POST /api/projects/{id}/production/auto-fill."""

    def test_auto_fill_creates_missing_context(self, client, project_id):
        """7. Auto-fill creates world_settings, characters, outlines, instructions."""
        from novel_factory.api_app import create_api_app
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        init_db(db_path)
        app = create_api_app(db_path=db_path, llm_mode="stub")
        tc = TestClient(app)
        tc.post("/api/onboarding/projects", json={
            "project_id": "af-test", "name": "AF Test", "genre": "奇幻",
            "description": "test", "total_chapters_planned": 10, "target_words": 30000,
        })
        # Approve genesis so auto-fill runs in approved-genesis mode
        tc.post("/api/projects/af-test/genesis/generate", json={
            "title": "T", "genre": "奇幻", "premise": "p", "target_chapters": 10, "target_words": 30000,
        })
        gid = tc.get("/api/projects/af-test/genesis/latest").json()["data"]["id"]
        tc.post(f"/api/projects/af-test/genesis/{gid}/approve")

        # Delete all created context to simulate gaps
        repo = Repository(db_path)
        for ws in repo.list_world_settings("af-test"):
            repo.delete_world_setting("af-test", ws["id"])
        for ch in repo.list_characters("af-test", include_inactive=True):
            repo.delete_character("af-test", ch["id"])
        for ol in repo.list_outlines("af-test"):
            repo.delete_outline("af-test", ol["id"])
        # Also delete instructions created by genesis
        for inst in repo.list_instructions("af-test"):
            repo.delete_instruction("af-test", inst["id"])

        resp = tc.post("/api/projects/af-test/production/auto-fill", json={
            "scope": "missing_context",
            "chapter_start": 1,
            "chapter_end": 10,
            "confirm": True,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["filled"] is True
        assert data["created"]["world_settings"] >= 2
        assert data["created"]["characters"] >= 3
        assert data["created"]["outlines"] >= 3
        assert data["created"]["instructions"] >= 10
        os.unlink(db_path)

    def test_auto_fill_does_not_overwrite_existing(self, client, project_id):
        """8. Auto-fill should not overwrite existing user content."""
        # Approve genesis
        gen_resp = client.post(f"/api/projects/{project_id}/genesis/generate", json={
            "title": "Test Novel", "genre": "奇幻", "premise": "A test premise",
            "target_chapters": 10, "target_words": 30000,
        })
        genesis_id = gen_resp.json()["data"]["id"]
        client.post(f"/api/projects/{project_id}/genesis/{genesis_id}/approve")

        # Manually create a world setting before auto-fill
        client.post(f"/api/projects/{project_id}/world-settings", json={
            "category": "地理", "title": "已有设定", "content": "用户手动添加",
        })

        resp = client.post(f"/api/projects/{project_id}/production/auto-fill", json={
            "scope": "missing_context", "chapter_start": 1, "chapter_end": 10, "confirm": True,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]

        # Verify the manual setting still exists and wasn't duplicated by title
        ws_resp = client.get(f"/api/projects/{project_id}/world-settings")
        ws_list = ws_resp.json().get("data", [])
        manual = [w for w in ws_list if w.get("title") == "已有设定"]
        assert len(manual) == 1
        assert manual[0]["content"] == "用户手动添加"


class TestArcPlanAPI:
    """POST /api/projects/{id}/production/arc-plan."""

    def test_arc_plan_generates_instructions_for_range(self, client, project_id):
        """9. Arc plan generates outlines and instructions for 11-20."""
        # Approve genesis and auto-fill 1-10
        gen_resp = client.post(f"/api/projects/{project_id}/genesis/generate", json={
            "title": "Test Novel", "genre": "奇幻", "premise": "A test premise",
            "target_chapters": 20, "target_words": 60000,
        })
        genesis_id = gen_resp.json()["data"]["id"]
        client.post(f"/api/projects/{project_id}/genesis/{genesis_id}/approve")
        client.post(f"/api/projects/{project_id}/production/auto-fill", json={
            "scope": "missing_context", "chapter_start": 1, "chapter_end": 10, "confirm": True,
        })

        resp = client.post(f"/api/projects/{project_id}/production/arc-plan", json={
            "chapter_start": 11,
            "chapter_end": 20,
            "confirm": True,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["planned"] is True
        assert data["chapter_start"] == 11
        assert data["chapter_end"] == 20
        # Should create at least some instructions for 11-20
        assert data["created"]["instructions"] >= 10

    def test_arc_plan_requires_confirm(self, client, project_id):
        """Arc plan without confirm should return error."""
        resp = client.post(f"/api/projects/{project_id}/production/arc-plan", json={
            "chapter_start": 11, "chapter_end": 20, "confirm": False,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "CONFIRM_REQUIRED" in body["error"]["code"]

    def test_arc_plan_requires_approved_genesis(self, client, project_id):
        """Arc plan without approved genesis should fail."""
        resp = client.post(f"/api/projects/{project_id}/production/arc-plan", json={
            "chapter_start": 1, "chapter_end": 10, "confirm": True,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "GENESIS_REQUIRED" in body["error"]["code"]


class TestFrontendCopy:
    """10. Frontend source contains required copy for v5.5.3."""

    def test_project_overview_module_has_next_action_copy(self):
        """ProjectOverviewModule contains the production command center copy."""
        path = os.path.join(os.path.dirname(__file__), "../frontend/src/components/project/ProjectOverviewModule.tsx")
        path = os.path.abspath(path)
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        assert "今日生产" in source
        assert "让 AI 补齐缺失资料" in source
        assert "让 AI 补齐世界观" in source or "让 AI 补齐" in source

    def test_project_overview_module_has_arc_plan_copy(self):
        """ProjectOverviewModule contains arc plan related copy."""
        path = os.path.join(os.path.dirname(__file__), "../frontend/src/components/project/ProjectOverviewModule.tsx")
        path = os.path.abspath(path)
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        assert "生成章节计划" in source or "generate_arc_plan" in source

    def test_project_overview_generate_chapter_opens_workflow_stream(self):
        """Generate chapter from overview should open the chapter workflow and auto-start generation."""
        path = os.path.join(os.path.dirname(__file__), "../frontend/src/components/project/ProjectOverviewModule.tsx")
        path = os.path.abspath(path)
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        assert "view=workflow&auto_generate=1" in source
        assert "generate_chapter" in source

    def test_project_detail_autogenerate_query_triggers_workflow(self):
        """ProjectDetail should auto-start chapter generation when auto_generate=1 is present."""
        path = os.path.join(os.path.dirname(__file__), "../frontend/src/pages/ProjectDetail.tsx")
        path = os.path.abspath(path)
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        assert "auto_generate" in source
        assert "handleGenerate()" in source

    def test_genesis_module_reframed_as_init(self):
        """GenesisModule reframes genesis as one-time initialization."""
        path = os.path.join(os.path.dirname(__file__), "../frontend/src/components/project/GenesisModule.tsx")
        path = os.path.abspath(path)
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        assert "项目初始化" in source
        assert "创世只需一次" in source or "只需一次" in source

    def test_recovery_action_normalizes_api_prefix(self):
        """Recovery action strips /api prefix from action_url to avoid /api/api double prefix."""
        path = os.path.join(os.path.dirname(__file__), "../frontend/src/components/project/ProjectOverviewModule.tsx")
        path = os.path.abspath(path)
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        assert "replace(/^\\/api/, '')" in source or "replace('/api', '')" in source

    def test_chapter_workspace_has_auto_fill_button(self):
        """ChapterWorkspace contains '让 AI 补齐缺失资料' button."""
        path = os.path.join(os.path.dirname(__file__), "../frontend/src/components/project/ChapterWorkspace.tsx")
        path = os.path.abspath(path)
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        assert "让 AI 补齐缺失资料" in source
