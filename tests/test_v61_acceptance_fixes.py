"""Regression tests for v6.1 manual acceptance fixes."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository


def _make_client(tmp_path):
    db_path = str(tmp_path / "v61_acceptance.db")
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    return TestClient(app), Repository(db_path)


def _backdate_run_activity(repo: Repository, run_id: str, minutes_old: int = 5) -> None:
    timestamp = (
        datetime.utcnow() + timedelta(hours=8) - timedelta(minutes=minutes_old)
    ).strftime("%Y-%m-%d %H:%M:%S")
    conn = repo._conn()
    try:
        conn.execute("UPDATE workflow_runs SET started_at=? WHERE id=?", (timestamp, run_id))
        conn.execute("UPDATE workflow_node_events SET created_at=? WHERE run_id=?", (timestamp, run_id))
        conn.execute("UPDATE workflow_execution_events SET created_at=? WHERE run_id=?", (timestamp, run_id))
        conn.commit()
    finally:
        conn.close()


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
    _backdate_run_activity(repo, run_id)

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
    _backdate_run_activity(repo, run_id)

    resp = client.get("/api/projects/drafted-orphan-proj/chapters/1/workflow-timeline")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["run_status"] == "completed"
    assert data["current_node"] == "author"

    run = repo.get_workflow_runs_for_project("drafted-orphan-proj", chapter_number=1, limit=1)[0]
    assert run["status"] == "completed"
    assert run["current_node"] == "author"


def test_timeline_does_not_reconcile_fresh_polisher_completed_running_row(tmp_path):
    client, repo = _make_client(tmp_path)
    repo.create_project(project_id="fresh-polisher-proj", name="活跃润色运行", genre="urban")
    repo.add_chapter("fresh-polisher-proj", 1, "第1章", status="polished")
    run_id = repo.create_workflow_run("fresh-polisher-proj", 1)
    repo.update_workflow_run(run_id, current_node="polisher")
    repo.create_workflow_node_event(
        run_id,
        "fresh-polisher-proj",
        1,
        "polisher",
        "started",
        status="running",
        message="开始润色",
    )
    repo.create_workflow_node_event(
        run_id,
        "fresh-polisher-proj",
        1,
        "polisher",
        "completed",
        status="completed",
        message="润色完成",
    )
    repo.create_workflow_execution_event(
        run_id=run_id,
        project_id="fresh-polisher-proj",
        chapter_number=1,
        node_name="polisher",
        event_type="artifact_saved",
        status="info",
        message="保存产物：润色稿",
    )

    resp = client.get("/api/projects/fresh-polisher-proj/chapters/1/workflow-timeline")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["run_status"] == "running"
    assert data["current_node"] == "polisher"

    run = repo.get_workflow_runs_for_project("fresh-polisher-proj", chapter_number=1, limit=1)[0]
    assert run["status"] == "running"
    assert run["current_node"] == "polisher"


def test_timeline_does_not_reconcile_fresh_editor_revision_running_row(tmp_path):
    client, repo = _make_client(tmp_path)
    repo.create_project(project_id="fresh-revision-proj", name="活跃返修运行", genre="urban")
    repo.add_chapter("fresh-revision-proj", 1, "第1章", status="revision")
    run_id = repo.create_workflow_run("fresh-revision-proj", 1)
    repo.update_workflow_run(run_id, current_node="editor")
    repo.create_workflow_execution_event(
        run_id=run_id,
        project_id="fresh-revision-proj",
        chapter_number=1,
        node_name="editor",
        event_type="evidence_verified",
        status="pass",
        message="完成证据校验通过",
    )

    resp = client.get("/api/projects/fresh-revision-proj/chapters/1/workflow-timeline")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["run_status"] == "running"
    assert data["current_node"] == "editor"

    run = repo.get_workflow_runs_for_project("fresh-revision-proj", chapter_number=1, limit=1)[0]
    assert run["status"] == "running"
    assert run["current_node"] == "editor"


def test_timeline_completed_non_terminal_run_offers_continue_generate(tmp_path):
    client, repo = _make_client(tmp_path)
    repo.create_project(project_id="completed-polished-proj", name="提前结束运行", genre="urban")
    repo.add_chapter("completed-polished-proj", 1, "第1章", status="polished")
    run_id = repo.create_workflow_run("completed-polished-proj", 1)
    repo.update_workflow_run(run_id, status="completed", current_node="editor")

    resp = client.get("/api/projects/completed-polished-proj/chapters/1/workflow-timeline")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["run_status"] == "completed"
    assert data["chapter_status"] == "polished"
    assert data["recovery"]["recommended_action"] == "generate"
    assert {action["key"] for action in data["recovery"]["safe_actions"]} >= {
        "view_content",
        "generate",
    }
    generate = next(action for action in data["recovery"]["safe_actions"] if action["key"] == "generate")
    assert generate["label"] == "继续生成"


def test_timeline_author_retry_recovery_scripted_offers_continue_generate(tmp_path):
    client, repo = _make_client(tmp_path)
    repo.create_project(project_id="completed-scripted-proj", name="作者恢复后继续", genre="urban")
    repo.save_chapter("completed-scripted-proj", 1, "第1章", "已有正文", 4, "scripted")
    run_id = repo.create_workflow_run("completed-scripted-proj", 1)
    repo.update_workflow_run(run_id, status="completed", current_node="author_retry_recovery")

    resp = client.get("/api/projects/completed-scripted-proj/chapters/1/workflow-timeline")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["run_status"] == "completed"
    assert data["chapter_status"] == "scripted"
    assert data["recovery"]["recommended_action"] == "generate"
    assert {action["key"] for action in data["recovery"]["safe_actions"]} >= {
        "view_content",
        "generate",
    }
    generate = next(action for action in data["recovery"]["safe_actions"] if action["key"] == "generate")
    assert generate["label"] == "继续生成"
    assert "不覆盖" in generate["note"]
