"""Regression tests for v6.1 manual acceptance fixes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository


def _make_client(tmp_path):
    db_path = str(tmp_path / "v61_acceptance.db")
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    return TestClient(app), Repository(db_path)


def test_chapter_detail_and_workspace_derive_quality_score_from_review(tmp_path):
    client, repo = _make_client(tmp_path)
    client.post(
        "/api/onboarding/projects",
        json={
            "project_id": "quality-score-proj",
            "name": "质量分测试",
            "initial_chapter_count": 1,
        },
    )

    repo.update_chapter_status("quality-score-proj", 1, "reviewed")
    chapter = repo.get_chapter("quality-score-proj", 1)
    repo.save_review(
        project_id="quality-score-proj",
        chapter_id=chapter["id"],
        passed=True,
        score=87,
        setting_score=22,
        logic_score=22,
        poison_score=18,
        text_score=12,
        pacing_score=13,
    )
    repo.publish_chapter("quality-score-proj", 1, expected_status="reviewed")

    detail_resp = client.get("/api/projects/quality-score-proj/chapters/1")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["data"]["quality_score"] == 87

    workspace_resp = client.get("/api/projects/quality-score-proj/workspace")
    assert workspace_resp.status_code == 200
    assert workspace_resp.json()["data"]["chapters"][0]["quality_score"] == 87


def test_chapter_detail_derives_quality_score_from_quality_report_without_review(tmp_path):
    client, repo = _make_client(tmp_path)
    client.post(
        "/api/onboarding/projects",
        json={
            "project_id": "quality-report-proj",
            "name": "质量报告测试",
            "initial_chapter_count": 1,
        },
    )

    repo.save_quality_report(
        project_id="quality-report-proj",
        chapter_number=1,
        stage="final",
        overall_score=82.456,
        pass_=True,
    )

    detail_resp = client.get("/api/projects/quality-report-proj/chapters/1")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["data"]["quality_score"] == 82.5


def test_chapter_detail_derives_readable_title_for_legacy_bare_heading(tmp_path):
    client, repo = _make_client(tmp_path)
    client.post(
        "/api/onboarding/projects",
        json={
            "project_id": "title-proj",
            "name": "标题测试",
            "initial_chapter_count": 1,
        },
    )
    repo.save_chapter_content(
        "title-proj",
        1,
        "第1章\n\n雨幕压在城市上空，林默在霓虹灯下醒来。",
        "第1章",
    )

    detail_resp = client.get("/api/projects/title-proj/chapters/1")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()["data"]
    assert detail["title"] == "第1章 雨幕压在城市上空"
    assert detail["content"].startswith("第1章 雨幕压在城市上空\n\n")

    workspace_resp = client.get("/api/projects/title-proj/workspace")
    assert workspace_resp.status_code == 200
    assert workspace_resp.json()["data"]["chapters"][0]["title"] == "第1章 雨幕压在城市上空"


def test_revision_router_updates_run_node_and_timeline_events(tmp_path):
    _, repo = _make_client(tmp_path)
    repo.create_project(project_id="revision-route-proj", name="返修路由测试", genre="urban")
    repo.add_chapter("revision-route-proj", 1, "第1章", status="revision")
    run_id = repo.create_workflow_run("revision-route-proj", 1)
    state = {
        "workflow_run_id": run_id,
        "project_id": "revision-route-proj",
        "chapter_number": 1,
        "chapter_status": "revision",
    }

    from novel_factory.workflow.nodes import revision_router_node

    assert revision_router_node(state, repo) == {
        "quality_gate": {"pass": False, "revision_target": "author"}
    }

    run = repo.get_workflow_runs_for_project("revision-route-proj", chapter_number=1, limit=1)[0]
    assert run["current_node"] == "revision_router"

    events = repo.get_workflow_node_events(run_id)
    assert [event["event_type"] for event in events] == ["started", "completed"]
    assert all(event["node_name"] == "revision_router" for event in events)


def test_timeline_reconciles_editor_completed_revision_running_row(tmp_path):
    client, repo = _make_client(tmp_path)
    repo.create_project(project_id="revision-orphan-proj", name="返修孤儿运行", genre="urban")
    repo.add_chapter("revision-orphan-proj", 1, "第1章", status="revision")
    run_id = repo.create_workflow_run("revision-orphan-proj", 1)
    repo.update_workflow_run(run_id, current_node="editor")
    repo.create_workflow_execution_event(
        run_id=run_id,
        project_id="revision-orphan-proj",
        chapter_number=1,
        node_name="editor",
        event_type="evidence_verified",
        status="pass",
        message="完成证据校验通过",
    )

    resp = client.get("/api/projects/revision-orphan-proj/chapters/1/workflow-timeline")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["run_status"] == "completed"
    assert data["current_node"] == "revision_router"

    run = repo.get_workflow_runs_for_project("revision-orphan-proj", chapter_number=1, limit=1)[0]
    assert run["status"] == "completed"
    assert run["current_node"] == "revision_router"

    events = repo.get_workflow_node_events(run_id)
    assert [event["event_type"] for event in events if event["node_name"] == "revision_router"] == [
        "started",
        "completed",
    ]


def test_timeline_reconciles_author_completed_drafted_running_row(tmp_path):
    client, repo = _make_client(tmp_path)
    repo.create_project(project_id="drafted-orphan-proj", name="起草孤儿运行", genre="urban")
    repo.add_chapter("drafted-orphan-proj", 1, "第1章", status="drafted")
    run_id = repo.create_workflow_run("drafted-orphan-proj", 1)
    repo.update_workflow_run(run_id, current_node="author")
    repo.create_workflow_node_event(
        run_id,
        "drafted-orphan-proj",
        1,
        "author",
        "started",
        status="running",
        message="开始执笔撰写",
    )
    repo.create_workflow_node_event(
        run_id,
        "drafted-orphan-proj",
        1,
        "author",
        "completed",
        status="completed",
        message="已生成章节初稿",
    )
    repo.create_workflow_execution_event(
        run_id=run_id,
        project_id="drafted-orphan-proj",
        chapter_number=1,
        node_name="author",
        event_type="evidence_verified",
        status="pass",
        message="完成证据校验通过",
    )

    resp = client.get("/api/projects/drafted-orphan-proj/chapters/1/workflow-timeline")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["run_status"] == "completed"
    assert data["current_node"] == "author"

    run = repo.get_workflow_runs_for_project("drafted-orphan-proj", chapter_number=1, limit=1)[0]
    assert run["status"] == "completed"
    assert run["current_node"] == "author"
