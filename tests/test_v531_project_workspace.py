"""Tests for v5.3.1 Project-Level Author Workspace APIs."""
import os
import tempfile
from pathlib import Path

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
    """Create a project via onboarding and return its ID."""
    resp = client.post("/api/onboarding/projects", json={
        "project_id": "test-novel",
        "name": "Test Novel",
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


class TestFactionsCRUD:
    def test_list_empty(self, client, project_id):
        resp = client.get(f"/api/projects/{project_id}/factions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"] == []

    def test_create(self, client, project_id):
        resp = client.post(f"/api/projects/{project_id}/factions", json={
            "name": "天机阁",
            "type": "宗门",
            "description": "神秘组织",
            "relationship_with_protagonist": "亦敌亦友",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["name"] == "天机阁"

    def test_create_with_minimal_data(self, client, project_id):
        resp = client.post(f"/api/projects/{project_id}/factions", json={"name": "Minimal"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_list_after_create(self, client, project_id):
        client.post(f"/api/projects/{project_id}/factions", json={"name": "A"})
        client.post(f"/api/projects/{project_id}/factions", json={"name": "B"})
        resp = client.get(f"/api/projects/{project_id}/factions")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 2

    def test_get_by_id(self, client, project_id):
        r = client.post(f"/api/projects/{project_id}/factions", json={"name": "X"})
        fid = r.json()["data"]["id"]
        resp = client.get(f"/api/projects/{project_id}/factions/{fid}")
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "X"

    def test_update(self, client, project_id):
        r = client.post(f"/api/projects/{project_id}/factions", json={"name": "Old"})
        fid = r.json()["data"]["id"]
        resp = client.put(f"/api/projects/{project_id}/factions/{fid}", json={"name": "New"})
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "New"

    def test_delete(self, client, project_id):
        r = client.post(f"/api/projects/{project_id}/factions", json={"name": "Del"})
        fid = r.json()["data"]["id"]
        resp = client.delete(f"/api/projects/{project_id}/factions/{fid}")
        assert resp.status_code == 200
        # Verify gone or returns error
        resp = client.get(f"/api/projects/{project_id}/factions/{fid}")
        body = resp.json()
        assert resp.status_code == 404 or body.get("ok") is False or body.get("data") is None

    def test_get_nonexistent(self, client, project_id):
        resp = client.get(f"/api/projects/{project_id}/factions/99999")
        # API returns envelope with error
        body = resp.json()
        assert resp.status_code == 404 or body.get("ok") is False


class TestPlotHolesCRUD:
    def test_list_empty(self, client, project_id):
        resp = client.get(f"/api/projects/{project_id}/plot-holes")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_create(self, client, project_id):
        resp = client.post(f"/api/projects/{project_id}/plot-holes", json={
            "code": "PH-001",
            "type": "悬念",
            "title": "神秘玉佩",
            "description": "主角随身玉佩的来历",
            "planted_chapter": 1,
            "planned_resolve_chapter": 5,
            "status": "planted",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["code"] == "PH-001"

    def test_create_with_minimal_data(self, client, project_id):
        resp = client.post(f"/api/projects/{project_id}/plot-holes", json={
            "code": "PH-MIN", "title": "Minimal",
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_update_status(self, client, project_id):
        r = client.post(f"/api/projects/{project_id}/plot-holes", json={
            "code": "PH-002", "title": "Test", "status": "planted",
        })
        pid = r.json()["data"]["id"]
        resp = client.put(f"/api/projects/{project_id}/plot-holes/{pid}", json={
            "status": "resolved", "resolved_chapter": 5,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "resolved"

    def test_delete(self, client, project_id):
        r = client.post(f"/api/projects/{project_id}/plot-holes", json={
            "code": "PH-DEL", "title": "Delete me",
        })
        pid = r.json()["data"]["id"]
        resp = client.delete(f"/api/projects/{project_id}/plot-holes/{pid}")
        assert resp.status_code == 200

    def test_status_filter(self, client, project_id):
        client.post(f"/api/projects/{project_id}/plot-holes", json={
            "code": "PH-A", "title": "A", "status": "planted",
        })
        client.post(f"/api/projects/{project_id}/plot-holes", json={
            "code": "PH-B", "title": "B", "status": "resolved",
        })
        resp = client.get(f"/api/projects/{project_id}/plot-holes?status=planted")
        assert resp.status_code == 200
        for item in resp.json()["data"]:
            assert item["status"] == "planted"


class TestInstructionsCRUD:
    def test_list_empty(self, client, project_id):
        resp = client.get(f"/api/projects/{project_id}/instructions")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_create(self, client, project_id):
        resp = client.post(f"/api/projects/{project_id}/instructions", json={
            "chapter_number": 1,
            "objective": "开篇引入主角",
            "key_events": "主角出场, 发现玉佩",
            "emotion_tone": "神秘",
            "word_target": 3000,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["chapter_number"] == 1

    def test_create_with_minimal_data(self, client, project_id):
        resp = client.post(f"/api/projects/{project_id}/instructions", json={
            "chapter_number": 1,
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_upsert_same_chapter(self, client, project_id):
        client.post(f"/api/projects/{project_id}/instructions", json={
            "chapter_number": 2, "objective": "V1",
        })
        resp = client.post(f"/api/projects/{project_id}/instructions", json={
            "chapter_number": 2, "objective": "V2",
        })
        assert resp.status_code == 200
        # Should still be one instruction for chapter 2
        resp = client.get(f"/api/projects/{project_id}/instructions")
        ch2 = [i for i in resp.json()["data"] if i["chapter_number"] == 2]
        assert len(ch2) == 1
        assert ch2[0]["objective"] == "V2"

    def test_update(self, client, project_id):
        r = client.post(f"/api/projects/{project_id}/instructions", json={
            "chapter_number": 3, "objective": "Old",
        })
        iid = r.json()["data"]["id"]
        resp = client.put(f"/api/projects/{project_id}/instructions/{iid}", json={
            "objective": "New",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["objective"] == "New"

    def test_delete(self, client, project_id):
        r = client.post(f"/api/projects/{project_id}/instructions", json={
            "chapter_number": 99, "objective": "Delete me",
        })
        iid = r.json()["data"]["id"]
        resp = client.delete(f"/api/projects/{project_id}/instructions/{iid}")
        assert resp.status_code == 200


class TestContextStatus:
    def test_empty_project_context(self, client, project_id):
        resp = client.get(f"/api/projects/{project_id}/context-status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert "ready" in body["data"]
        assert "missing" in body["data"]

    def test_actions_have_paths(self, client, project_id):
        resp = client.get(f"/api/projects/{project_id}/context-status")
        body = resp.json()
        for action in body["data"].get("actions", []):
            assert "label" in action
            assert "path" in action

    def test_nonexistent_project(self, client):
        resp = client.get("/api/projects/nonexistent-id/context-status")
        assert resp.status_code in (404, 200)


class TestChapterReadonlyEndpoints:
    def test_state_history(self, client, project_id):
        resp = client.get(f"/api/projects/{project_id}/chapters/1/state-history")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_versions(self, client, project_id):
        resp = client.get(f"/api/projects/{project_id}/chapters/1/versions")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_quality_reports(self, client, project_id):
        resp = client.get(f"/api/projects/{project_id}/quality-reports")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_artifacts(self, client, project_id):
        resp = client.get(f"/api/projects/{project_id}/artifacts")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestProjectWorkspaceFrontendWiring:
    """Static checks for project-level module routing."""

    @property
    def frontend_src(self) -> Path:
        return Path(__file__).parent.parent / "frontend" / "src"

    def test_overview_module_is_routed(self):
        project_detail = self.frontend_src / "pages" / "ProjectDetail.tsx"
        content = project_detail.read_text()

        assert "ProjectOverviewModule" in content
        assert "case 'overview'" in content
        assert "<ProjectOverviewModule project={project} stats={stats}" in content

    def test_settings_module_is_routed_not_placeholder(self):
        project_detail = self.frontend_src / "pages" / "ProjectDetail.tsx"
        content = project_detail.read_text()

        assert "ProjectSettingsModule" in content
        assert "case 'settings'" in content
        assert "<ProjectSettingsModule projectId={projectId}" in content
        assert 'PlaceholderModule title="项目设置"' not in content

    def test_settings_save_refreshes_workspace(self):
        project_detail = self.frontend_src / "pages" / "ProjectDetail.tsx"
        settings_module = self.frontend_src / "components" / "project" / "ProjectSettingsModule.tsx"

        assert "onWorkspaceChange={loadWorkspace}" in project_detail.read_text()
        settings_content = settings_module.read_text()
        assert "onSaved?: () => void" in settings_content
        assert "onSaved?.()" in settings_content
