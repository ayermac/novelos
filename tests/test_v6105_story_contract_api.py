"""v6.10.5: Story Contract API integration tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository


def _client_and_repo(tmp_path):
    db_path = str(tmp_path / "v6105_story_contract_api.db")
    init_db(db_path)
    repo = Repository(db_path)
    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        ("proj_api", "API Test Novel", "都市系统"),
    )
    conn.commit()
    conn.close()
    client = TestClient(create_api_app(db_path=db_path, llm_mode="stub"))
    return client, repo


def test_generate_contracts_returns_story_contract(tmp_path):
    client, repo = _client_and_repo(tmp_path)

    res = client.post(
        "/api/projects/proj_api/creative-contracts/generate",
        json={
            "project_id": "proj_api",
            "user_idea": "主角通过核心机会获得收益并完成反制。",
            "genre_profile_id": "generic",
        },
    )

    assert res.status_code == 200
    payload = res.json()
    assert payload["ok"] is True
    data = payload["data"]
    assert data["story_contract"]["project_id"] == "proj_api"
    assert data["story_contract"]["core_loop"]
    assert repo.get_creative_contract("proj_api", "story_contract") is not None


def test_get_contracts_includes_story_contract(tmp_path):
    client, _repo = _client_and_repo(tmp_path)
    client.post(
        "/api/projects/proj_api/creative-contracts/generate",
        json={
            "project_id": "proj_api",
            "user_idea": "主角通过核心机会获得收益并完成反制。",
            "genre_profile_id": "generic",
        },
    )

    res = client.get("/api/projects/proj_api/creative-contracts")

    assert res.status_code == 200
    data = res.json()["data"]
    assert data["story_contract"]
    assert data["story_contract"]["status"] == "draft"


def test_approve_contracts_activates_story_contract(tmp_path):
    client, _repo = _client_and_repo(tmp_path)
    client.post(
        "/api/projects/proj_api/creative-contracts/generate",
        json={
            "project_id": "proj_api",
            "user_idea": "主角通过核心机会获得收益并完成反制。",
            "genre_profile_id": "generic",
        },
    )

    approve = client.post(
        "/api/projects/proj_api/creative-contracts/approve",
        json={"project_id": "proj_api"},
    )
    assert approve.status_code == 200

    res = client.get("/api/projects/proj_api/creative-contracts")
    data = res.json()["data"]
    assert data["is_approved"] is True
    assert data["story_contract"]["status"] == "active"


def test_update_story_contract_endpoint(tmp_path):
    client, _repo = _client_and_repo(tmp_path)
    story_contract = {
        "project_id": "proj_api",
        "core_promise": "每章围绕核心机会完成可见收益。",
        "core_loop": [
            {"id": "trigger", "label": "触发核心机会"},
            {"id": "payoff", "label": "完成核心兑现"},
        ],
        "supporting_mechanisms": [
            {"id": "pressure", "label": "压力机制", "allowed_role": "pressure"},
        ],
        "payoff_types": ["reward"],
        "drift_rules": [
            {
                "id": "payoff_within_window",
                "description": "连续2章内必须有核心兑现",
                "severity": "warning",
                "window_chapters": 2,
                "threshold": 1,
            },
        ],
        "cadence": {"minor_payoff": 1},
        "status": "active",
    }

    res = client.put(
        "/api/projects/proj_api/creative-contracts/story-contract",
        json={"story_contract": story_contract},
    )

    assert res.status_code == 200
    payload = res.json()
    assert payload["ok"] is True
    assert payload["data"]["story_contract"]["core_promise"] == "每章围绕核心机会完成可见收益。"

    detail = client.get("/api/projects/proj_api/creative-contracts").json()["data"]
    assert detail["story_contract"]["core_loop"][1]["label"] == "完成核心兑现"
