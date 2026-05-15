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
