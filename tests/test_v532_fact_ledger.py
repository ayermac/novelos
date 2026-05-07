"""Tests for v5.3.2 Fact Ledger — story facts CRUD and event history."""

import json
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
        "project_id": "test-facts",
        "name": "Test Facts",
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


@pytest.fixture()
def seeded_facts(client, project_id):
    """Seed story facts via the repository."""
    from novel_factory.db.repository import Repository

    db_path = client.app.state.db_path
    repo = Repository(db_path)

    facts = []
    fact1 = repo.upsert_story_fact(
        project_id,
        fact_key="mc.weapon",
        fact_type="inventory",
        value_json=json.dumps("铁剑", ensure_ascii=False),
        source_chapter=1,
        source_agent="memory_curator",
        subject="主角",
        attribute="weapon",
    )
    facts.append(fact1)

    fact2 = repo.upsert_story_fact(
        project_id,
        fact_key="mc.level",
        fact_type="power_level",
        value_json=json.dumps(5, ensure_ascii=False),
        source_chapter=1,
        source_agent="memory_curator",
        subject="主角",
        attribute="level",
        unit="级",
    )
    facts.append(fact2)

    fact3 = repo.upsert_story_fact(
        project_id,
        fact_key="world.time",
        fact_type="timeline",
        value_json=json.dumps("第三年春", ensure_ascii=False),
        source_chapter=2,
        source_agent="memory_curator",
        subject="世界",
        attribute="currentTime",
    )
    facts.append(fact3)

    return facts


class TestStoryFactsList:
    """v5.3.2: Story facts list API."""

    def test_list_empty(self, client, project_id):
        resp = client.get(f"/api/projects/{project_id}/story-facts")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert isinstance(body["data"], list)

    def test_list_with_seeded_facts(self, client, project_id, seeded_facts):
        resp = client.get(f"/api/projects/{project_id}/story-facts")
        body = resp.json()
        assert body["ok"] is True
        assert len(body["data"]) == 3

    def test_list_filter_by_type(self, client, project_id, seeded_facts):
        resp = client.get(
            f"/api/projects/{project_id}/story-facts?fact_type=inventory"
        )
        body = resp.json()
        assert body["ok"] is True
        assert len(body["data"]) == 1
        assert body["data"][0]["fact_key"] == "mc.weapon"

    def test_list_filter_by_status(self, client, project_id, seeded_facts):
        resp = client.get(
            f"/api/projects/{project_id}/story-facts?status=active"
        )
        body = resp.json()
        assert body["ok"] is True
        assert len(body["data"]) == 3

    def test_list_nonexistent_project(self, client):
        resp = client.get("/api/projects/nonexistent/story-facts")
        body = resp.json()
        assert body["ok"] is False


class TestStoryFactDetail:
    """v5.3.2: Story fact detail with event history."""

    def test_get_fact_detail(self, client, project_id, seeded_facts):
        fact_id = seeded_facts[0]["id"]
        resp = client.get(
            f"/api/projects/{project_id}/story-facts/{fact_id}"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["fact_key"] == "mc.weapon"
        assert "events" in body["data"]

    def test_get_nonexistent_fact(self, client, project_id):
        resp = client.get(
            f"/api/projects/{project_id}/story-facts/nonexistent"
        )
        body = resp.json()
        assert body["ok"] is False

    def test_get_fact_wrong_project(self, client, project_id, seeded_facts):
        fact_id = seeded_facts[0]["id"]
        resp = client.get(
            f"/api/projects/wrong-project/story-facts/{fact_id}"
        )
        body = resp.json()
        assert body["ok"] is False


class TestStoryFactUpdate:
    """v5.3.2: Story fact update with correction logging."""

    def test_update_fact_value(self, client, project_id, seeded_facts):
        fact_id = seeded_facts[0]["id"]
        resp = client.put(
            f"/api/projects/{project_id}/story-facts/{fact_id}",
            json={
                "value_json": json.dumps("玄铁剑", ensure_ascii=False),
                "correction_note": "修正武器名称",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        updated = body["data"]
        assert json.loads(updated["value_json"]) == "玄铁剑"

    def test_update_creates_correction_event(self, client, project_id, seeded_facts):
        fact_id = seeded_facts[0]["id"]

        # Update the fact
        client.put(
            f"/api/projects/{project_id}/story-facts/{fact_id}",
            json={
                "value_json": json.dumps("玄铁剑", ensure_ascii=False),
                "correction_note": "修正武器名称",
            },
        )

        # Check events
        resp = client.get(
            f"/api/projects/{project_id}/story-facts/{fact_id}"
        )
        body = resp.json()
        events = body["data"]["events"]
        assert len(events) >= 1
        correction_events = [
            e for e in events if e["event_type"] == "manual_correction"
        ]
        assert len(correction_events) >= 1
        assert correction_events[-1]["rationale"] == "修正武器名称"

    def test_update_nonexistent_fact(self, client, project_id):
        resp = client.put(
            f"/api/projects/{project_id}/story-facts/nonexistent",
            json={"value_json": json.dumps("test")},
        )
        body = resp.json()
        assert body["ok"] is False

    def test_update_no_changes_returns_fact(self, client, project_id, seeded_facts):
        fact_id = seeded_facts[0]["id"]
        resp = client.put(
            f"/api/projects/{project_id}/story-facts/{fact_id}",
            json={},
        )
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["id"] == fact_id


class TestFactEventsList:
    """v5.3.2: Fact events list API."""

    def test_list_events_empty(self, client, project_id):
        resp = client.get(f"/api/projects/{project_id}/fact-events")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert isinstance(body["data"], list)

    def test_list_events_with_corrections(self, client, project_id, seeded_facts):
        fact_id = seeded_facts[0]["id"]

        # Create a correction event
        client.put(
            f"/api/projects/{project_id}/story-facts/{fact_id}",
            json={
                "value_json": json.dumps("玄铁剑", ensure_ascii=False),
                "correction_note": "测试修正",
            },
        )

        resp = client.get(f"/api/projects/{project_id}/fact-events")
        body = resp.json()
        assert body["ok"] is True
        assert len(body["data"]) >= 1

    def test_list_events_nonexistent_project(self, client):
        resp = client.get("/api/projects/nonexistent/fact-events")
        body = resp.json()
        assert body["ok"] is False


class TestFactsCanonicalList:
    """v5.3.2: Canonical GET /api/facts route."""

    def test_list_canonical(self, client, project_id, seeded_facts):
        resp = client.get(f"/api/facts?project_id={project_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert len(body["data"]) == 3

    def test_list_canonical_filter_by_type(self, client, project_id, seeded_facts):
        resp = client.get(f"/api/facts?project_id={project_id}&fact_type=inventory")
        body = resp.json()
        assert body["ok"] is True
        assert len(body["data"]) == 1
        assert body["data"][0]["fact_key"] == "mc.weapon"

    def test_list_canonical_filter_by_status(self, client, project_id, seeded_facts):
        resp = client.get(f"/api/facts?project_id={project_id}&status=active")
        body = resp.json()
        assert body["ok"] is True
        assert len(body["data"]) == 3

    def test_list_canonical_nonexistent_project(self, client):
        resp = client.get("/api/facts?project_id=nonexistent")
        body = resp.json()
        assert body["ok"] is False


class TestFactsCanonicalHistory:
    """v5.3.2: Canonical GET /api/facts/{fact_key}/history route."""

    def test_history_canonical(self, client, project_id, seeded_facts):
        resp = client.get(
            f"/api/facts/mc.weapon/history?project_id={project_id}"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["fact_key"] == "mc.weapon"
        assert "events" in body["data"]

    def test_history_nonexistent_key(self, client, project_id):
        resp = client.get(
            f"/api/facts/nonexistent.key/history?project_id={project_id}"
        )
        body = resp.json()
        assert body["ok"] is False

    def test_history_wrong_project(self, client, project_id, seeded_facts):
        resp = client.get(
            "/api/facts/mc.weapon/history?project_id=wrong-project"
        )
        body = resp.json()
        assert body["ok"] is False


class TestFactsCanonicalCorrect:
    """v5.3.2: Canonical POST /api/facts/correct route."""

    def test_correct_canonical(self, client, project_id, seeded_facts):
        fact_id = seeded_facts[0]["id"]
        resp = client.post("/api/facts/correct", json={
            "project_id": project_id,
            "fact_id": fact_id,
            "value_json": json.dumps("玄铁剑", ensure_ascii=False),
            "correction_note": "修正武器名称",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert json.loads(body["data"]["value_json"]) == "玄铁剑"

    def test_correct_creates_event(self, client, project_id, seeded_facts):
        fact_id = seeded_facts[0]["id"]
        client.post("/api/facts/correct", json={
            "project_id": project_id,
            "fact_id": fact_id,
            "value_json": json.dumps("玄铁剑", ensure_ascii=False),
            "correction_note": "测试修正",
        })

        # Verify event was created via canonical history route
        resp = client.get(
            f"/api/facts/mc.weapon/history?project_id={project_id}"
        )
        body = resp.json()
        events = body["data"]["events"]
        correction_events = [
            e for e in events if e["event_type"] == "manual_correction"
        ]
        assert len(correction_events) >= 1
        assert correction_events[-1]["rationale"] == "测试修正"

    def test_correct_nonexistent_fact(self, client, project_id):
        resp = client.post("/api/facts/correct", json={
            "project_id": project_id,
            "fact_id": "nonexistent",
            "value_json": json.dumps("test"),
        })
        body = resp.json()
        assert body["ok"] is False

    def test_correct_wrong_project(self, client, project_id, seeded_facts):
        fact_id = seeded_facts[0]["id"]
        resp = client.post("/api/facts/correct", json={
            "project_id": "wrong-project",
            "fact_id": fact_id,
            "value_json": json.dumps("test"),
        })
        body = resp.json()
        assert body["ok"] is False

    def test_correct_no_value_returns_fact(self, client, project_id, seeded_facts):
        fact_id = seeded_facts[0]["id"]
        resp = client.post("/api/facts/correct", json={
            "project_id": project_id,
            "fact_id": fact_id,
        })
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["id"] == fact_id
