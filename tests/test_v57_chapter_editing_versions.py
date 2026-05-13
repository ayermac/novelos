"""v5.7 Chapter Editing & Version Management — backend integration tests.

Covers:
1. Save content creates manual_edit version
2. Published chapter cannot be saved directly
3. Create published revision draft
4. Version list / detail
5. Diff API
6. Restore creates rollback version
7. Stale base_version rejects overwrite
8. Local revision returns candidate without overwriting
9. Accept local revision creates new version
10. Reviewed save cannot stay directly-publishable
11. Cross-chapter diff is rejected
12. Local revision output risk_notes normalization
"""

from __future__ import annotations

import pytest
from pathlib import Path

from fastapi.testclient import TestClient

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.api_app import create_api_app


@pytest.fixture()
def db_path(tmp_path: Path) -> str:
    """Create a fresh test database with migrations applied."""
    path = str(tmp_path / "test_v57.db")
    init_db(path)
    return path


@pytest.fixture()
def repo(db_path: str) -> Repository:
    return Repository(db_path)


@pytest.fixture()
def client(db_path: str) -> TestClient:
    app = create_api_app(db_path=db_path, llm_mode="stub")
    return TestClient(app)


@pytest.fixture()
def seeded_project(repo: Repository) -> str:
    """Create a project with a drafted chapter that has content."""
    pid = "test_v57_project"
    repo.create_project(pid, "v5.7 测试项目")
    repo.add_chapter(pid, 1, "第一章 测试")
    # Simulate AI generation: set content and status
    content = "这是一段测试正文，用于验证版本管理功能。" * 20
    repo.save_chapter(pid, 1, "第一章 测试", content, len(content), "drafted")
    repo.save_version(pid, 1, content, created_by="author", source="ai_generation", summary="AI 生成初稿")
    return pid


# ── 1. Save content creates manual_edit version ────────────


def test_save_content_creates_manual_edit_version(client: TestClient, seeded_project: str):
    pid = seeded_project
    # Get editor state first
    editor = client.get(f"/api/projects/{pid}/chapters/1/editor")
    assert editor.json()["ok"]
    base_vid = editor.json()["data"]["current_version_id"]

    new_content = "这是修改后的正文内容，由人工编辑保存。" * 20
    resp = client.post(
        f"/api/projects/{pid}/chapters/1/content",
        json={
            "content": new_content,
            "summary": "人工编辑测试",
            "base_version_id": base_vid,
        },
    )
    body = resp.json()
    assert body["ok"], body.get("error", {}).get("message", "")
    assert body["data"]["saved"] is True
    assert body["data"]["version_id"] is not None

    # Verify version was created with source=manual_edit
    versions = client.get(f"/api/projects/{pid}/chapters/1/versions")
    vlist = versions.json()["data"]["versions"]
    manual_versions = [v for v in vlist if v["source"] == "manual_edit"]
    assert len(manual_versions) >= 1
    assert manual_versions[0]["source_label"] == "人工编辑"


# ── 2. Published chapter cannot be saved directly ──────────


def test_published_chapter_cannot_save_directly(client: TestClient, repo: Repository):
    pid = "test_pub_protect"
    repo.create_project(pid, "发布保护测试")
    repo.add_chapter(pid, 1, "第一章")
    content = "已发布章节正文" * 20
    repo.save_chapter(pid, 1, "第一章", content, len(content), "published")

    resp = client.post(
        f"/api/projects/{pid}/chapters/1/content",
        json={"content": "尝试直接修改已发布章节" * 20, "summary": "不应该成功"},
    )
    body = resp.json()
    assert not body["ok"]
    assert body["error"]["code"] == "PUBLISHED_PROTECTED"


# ── 3. Create published revision draft ─────────────────────


def test_create_revision_draft_for_published(client: TestClient, repo: Repository):
    pid = "test_revision_draft"
    repo.create_project(pid, "修订版测试")
    repo.add_chapter(pid, 1, "第一章")
    content = "已发布章节正文" * 20
    repo.save_chapter(pid, 1, "第一章", content, len(content), "published")
    repo.save_version(pid, 1, content, source="ai_generation", summary="AI 初稿")

    resp = client.post(
        f"/api/projects/{pid}/chapters/1/revision-draft",
        json={"confirm": True},
    )
    body = resp.json()
    assert body["ok"], body.get("error", {}).get("message", "")
    assert body["data"]["revision_draft_created"] is True
    assert body["data"]["new_status"] == "revision"

    # After revision draft, chapter should be editable
    editor = client.get(f"/api/projects/{pid}/chapters/1/editor")
    assert editor.json()["data"]["editable"] is True


# ── 4. Version list / detail ───────────────────────────────


def test_version_list_and_detail(client: TestClient, seeded_project: str):
    pid = seeded_project

    # List
    resp = client.get(f"/api/projects/{pid}/chapters/1/versions")
    body = resp.json()
    assert body["ok"]
    versions = body["data"]["versions"]
    assert len(versions) >= 1
    # Source labels should be user-facing, not raw keys
    for v in versions:
        assert v["source_label"] is not None
        assert v["source_label"] != v["source"]  # label is Chinese, key is English

    # Detail
    vid = versions[0]["version_id"]
    detail = client.get(f"/api/projects/{pid}/chapters/1/versions/{vid}")
    detail_body = detail.json()
    assert detail_body["ok"]
    assert detail_body["data"]["content"] is not None
    assert detail_body["data"]["source"] is not None


# ── 5. Diff API ────────────────────────────────────────────


def test_version_diff(client: TestClient, seeded_project: str):
    pid = seeded_project

    # Get initial version
    versions = client.get(f"/api/projects/{pid}/chapters/1/versions").json()["data"]["versions"]
    v1_id = versions[0]["version_id"]

    # Save a new version
    editor = client.get(f"/api/projects/{pid}/chapters/1/editor")
    base_vid = editor.json()["data"]["current_version_id"]
    new_content = "这是修改后的文本，用于测试 diff 功能。" * 20
    client.post(
        f"/api/projects/{pid}/chapters/1/content",
        json={"content": new_content, "base_version_id": base_vid},
    )

    # Get new versions
    versions = client.get(f"/api/projects/{pid}/chapters/1/versions").json()["data"]["versions"]
    v2_id = versions[0]["version_id"]

    # Diff
    diff = client.get(f"/api/projects/{pid}/chapters/1/versions/{v1_id}/diff/{v2_id}")
    diff_body = diff.json()
    assert diff_body["ok"]
    data = diff_body["data"]
    assert "added" in data
    assert "removed" in data
    assert "word_count_delta" in data


# ── 6. Restore creates rollback version ────────────────────


def test_restore_creates_rollback_version(client: TestClient, seeded_project: str):
    pid = seeded_project

    # Get initial version
    versions = client.get(f"/api/projects/{pid}/chapters/1/versions").json()["data"]["versions"]
    original_vid = versions[-1]["version_id"]  # oldest version

    # Save a new version first
    editor = client.get(f"/api/projects/{pid}/chapters/1/editor")
    base_vid = editor.json()["data"]["current_version_id"]
    new_content = "全新修改的内容，准备回滚。" * 20
    client.post(
        f"/api/projects/{pid}/chapters/1/content",
        json={"content": new_content, "base_version_id": base_vid},
    )

    # Restore
    resp = client.post(
        f"/api/projects/{pid}/chapters/1/versions/{original_vid}/restore",
        json={"confirm": True},
    )
    body = resp.json()
    assert body["ok"], body.get("error", {}).get("message", "")
    assert body["data"]["restored"] is True
    assert body["data"]["new_version_id"] is not None

    # Check rollback version exists
    versions = client.get(f"/api/projects/{pid}/chapters/1/versions").json()["data"]["versions"]
    rollback_versions = [v for v in versions if v["source"] == "rollback"]
    assert len(rollback_versions) >= 1

    # Content should match original
    detail = client.get(f"/api/projects/{pid}/chapters/1/versions/{original_vid}").json()["data"]
    chapter = client.get(f"/api/projects/{pid}/chapters/1/editor").json()["data"]
    assert chapter["content"] == detail["content"]


# ── 7. Stale base_version rejects overwrite ────────────────


def test_stale_base_version_rejects_overwrite(client: TestClient, seeded_project: str):
    pid = seeded_project

    # Get current version
    editor = client.get(f"/api/projects/{pid}/chapters/1/editor")
    stale_vid = editor.json()["data"]["current_version_id"]

    # Save once (making stale_vid outdated)
    client.post(
        f"/api/projects/{pid}/chapters/1/content",
        json={"content": "第一次修改" * 20, "base_version_id": stale_vid},
    )

    # Try to save with stale base_version_id
    resp = client.post(
        f"/api/projects/{pid}/chapters/1/content",
        json={"content": "第二次修改" * 20, "base_version_id": stale_vid},
    )
    body = resp.json()
    assert not body["ok"]
    assert body["error"]["code"] == "VERSION_CONFLICT"


# ── 8. Local revision returns candidate without overwriting ─


def test_local_revision_returns_candidate(client: TestClient, seeded_project: str):
    pid = seeded_project
    # Get content
    editor = client.get(f"/api/projects/{pid}/chapters/1/editor")
    content = editor.json()["data"]["content"]

    selected = content[:50]
    resp = client.post(
        f"/api/projects/{pid}/chapters/1/local-revision",
        json={
            "selected_text": selected,
            "selection_start": 0,
            "selection_end": 50,
            "instruction": "润色这段文字",
            "mode": "polish",
        },
    )
    body = resp.json()
    assert body["ok"], body.get("error", {}).get("message", "")
    assert "replacement_text" in body["data"]
    assert body["data"]["replacement_text"] != ""

    # Original content should NOT have changed
    editor2 = client.get(f"/api/projects/{pid}/chapters/1/editor")
    assert editor2.json()["data"]["content"] == content


# ── 9. Accept local revision creates new version ────────────


def test_accept_local_revision_creates_version(client: TestClient, seeded_project: str):
    pid = seeded_project
    editor = client.get(f"/api/projects/{pid}/chapters/1/editor")
    content = editor.json()["data"]["content"]
    base_vid = editor.json()["data"]["current_version_id"]

    # Get revision candidate
    selected = content[:50]
    revision = client.post(
        f"/api/projects/{pid}/chapters/1/local-revision",
        json={
            "selected_text": selected,
            "selection_start": 0,
            "selection_end": 50,
            "instruction": "润色这段文字",
            "mode": "polish",
        },
    ).json()["data"]

    # Accept: replace selection and save
    replacement = revision["replacement_text"]
    new_content = replacement + content[50:]
    resp = client.post(
        f"/api/projects/{pid}/chapters/1/content",
        json={
            "content": new_content,
            "base_version_id": base_vid,
            "summary": "接受局部返修",
        },
    )
    body = resp.json()
    assert body["ok"]

    # Check version created with source=manual_edit (saved through content API)
    versions = client.get(f"/api/projects/{pid}/chapters/1/versions").json()["data"]["versions"]
    recent = versions[0]
    assert recent["summary"] == "接受局部返修"


# ── 10. Reviewed save cannot stay directly-publishable ──────


def test_reviewed_save_transitions_to_polished(client: TestClient, repo: Repository):
    pid = "test_reviewed_save"
    repo.create_project(pid, "审核保存测试")
    repo.add_chapter(pid, 1, "第一章")
    content = "审核通过章节正文" * 20
    repo.save_chapter(pid, 1, "第一章", content, len(content), "reviewed")
    repo.save_version(pid, 1, content, source="ai_generation")

    # Save content on reviewed chapter
    new_content = "修改后的审核章节" * 20
    resp = client.post(
        f"/api/projects/{pid}/chapters/1/content",
        json={"content": new_content, "summary": "审核后修改"},
    )
    body = resp.json()
    assert body["ok"], body.get("error", {}).get("message", "")
    assert body["data"]["status"] == "polished"
    assert body["data"]["status_changed"] is True
    assert body["data"]["previous_status"] == "reviewed"


# ── 11. Cross-chapter diff is rejected ───────────────────────


def test_cross_chapter_diff_rejected(client: TestClient, repo: Repository, seeded_project: str):
    """Diff between versions of different chapters must return VERSION_NOT_FOUND."""
    pid = seeded_project

    chapter2_content = "第二章正文，用于验证跨章节版本对比边界。" * 20
    repo.add_chapter(pid, 2, "第二章 测试")
    repo.save_chapter(pid, 2, "第二章 测试", chapter2_content, len(chapter2_content), "drafted")
    chapter2_vid = repo.save_version(
        pid,
        2,
        chapter2_content,
        created_by="author",
        source="ai_generation",
        summary="第二章 AI 初稿",
    )

    chapter1_versions = client.get(f"/api/projects/{pid}/chapters/1/versions").json()["data"]["versions"]
    chapter1_vid = chapter1_versions[0]["version_id"]

    # Both versions exist, but one belongs to chapter 2. The chapter 1 diff endpoint must reject it.
    diff_resp = client.get(f"/api/projects/{pid}/chapters/1/versions/{chapter1_vid}/diff/{chapter2_vid}")
    diff_body = diff_resp.json()
    assert not diff_body["ok"]
    assert diff_body["error"]["code"] == "VERSION_NOT_FOUND"


# ── 12. Local revision output risk_notes normalization ──────


def test_local_revision_risk_notes_normalization(client: TestClient, seeded_project: str):
    """risk_notes must always be a list of strings, even if provider returns non-list."""
    pid = seeded_project

    # Get content
    editor = client.get(f"/api/projects/{pid}/chapters/1/editor")
    content = editor.json()["data"]["content"]

    selected = content[:50]
    resp = client.post(
        f"/api/projects/{pid}/chapters/1/local-revision",
        json={
            "selected_text": selected,
            "selection_start": 0,
            "selection_end": 50,
            "instruction": "润色这段文字",
            "mode": "polish",
        },
    )
    body = resp.json()
    assert body["ok"], body.get("error", {}).get("message", "")

    # risk_notes must be a list
    assert isinstance(body["data"]["risk_notes"], list)
    # Every element must be a string
    for note in body["data"]["risk_notes"]:
        assert isinstance(note, str)
