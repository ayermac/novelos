"""Project export API regression tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository


def test_export_project_with_chinese_name_uses_rfc5987_filename(tmp_path: Path):
    db_path = str(tmp_path / "export.db")
    init_db(db_path)
    repo = Repository(db_path)
    project_id = "unicode_export_project"
    repo.create_project(project_id, "绝世仙帝在都市")
    repo.add_chapter(project_id, 1, "第一章")
    repo.save_chapter(project_id, 1, "第一章", "这是第一章正文。", 8, "published")

    client = TestClient(create_api_app(db_path=db_path, llm_mode="stub"))
    resp = client.get(f"/api/projects/{project_id}/export?format=markdown")

    assert resp.status_code == 200
    assert "# 绝世仙帝在都市" in resp.text
    disposition = resp.headers["content-disposition"]
    assert 'filename="unicode_export_project.md"' in disposition
    assert "filename*=UTF-8''%E7%BB%9D%E4%B8%96%E4%BB%99%E5%B8%9D" in disposition
