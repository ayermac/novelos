"""Tests for db/repository.py — Repository CRUD operations."""

import json
import tempfile
from pathlib import Path

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database with schema initialized."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return str(db_path)


@pytest.fixture
def repo(tmp_db):
    """Create a Repository with a temp database."""
    return Repository(tmp_db)


@pytest.fixture
def seeded_repo(repo):
    """Create a Repository with a project and chapter seeded."""
    # Add project
    conn = repo._conn()
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        ("test_proj", "Test Novel", "urban",),
    )
    # Add chapter
    conn.execute(
        "INSERT INTO chapters (project_id, chapter_number, title, status) VALUES (?, ?, ?, ?)",
        ("test_proj", 1, "第一章 测试", "planned"),
    )
    conn.commit()
    conn.close()
    return repo


class TestChapterStatus:
    def test_get_chapter_status(self, seeded_repo):
        status = seeded_repo.get_chapter_status("test_proj", 1)
        assert status == "planned"

    def test_get_chapter_status_nonexistent(self, repo):
        status = repo.get_chapter_status("nonexistent", 1)
        assert status is None

    def test_update_chapter_status(self, seeded_repo):
        ok = seeded_repo.update_chapter_status("test_proj", 1, "scripted")
        assert ok
        assert seeded_repo.get_chapter_status("test_proj", 1) == "scripted"


class TestInstructions:
    def test_create_and_get_instruction(self, seeded_repo):
        instr_id = seeded_repo.create_instruction(
            project_id="test_proj",
            chapter_number=1,
            objective="测试目标",
            key_events='["事件1"]',
            plots_to_plant='["P001"]',
        )
        assert instr_id > 0

        instr = seeded_repo.get_instruction("test_proj", 1)
        assert instr is not None
        assert instr["objective"] == "测试目标"


class TestSceneBeats:
    def test_save_and_get_scene_beats(self, seeded_repo):
        beats = [
            {"sequence": 1, "scene_goal": "开场", "conflict": "冲突1", "hook": "钩子1"},
            {"sequence": 2, "scene_goal": "高潮", "conflict": "冲突2"},
        ]
        count = seeded_repo.save_scene_beats("test_proj", 1, beats)
        assert count == 2

        result = seeded_repo.get_scene_beats("test_proj", 1)
        assert len(result) == 2
        assert result[0]["scene_goal"] == "开场"

    def test_save_scene_beats_replaces_existing(self, seeded_repo):
        seeded_repo.save_scene_beats("test_proj", 1, [{"sequence": 1, "scene_goal": "旧"}])
        seeded_repo.save_scene_beats("test_proj", 1, [{"sequence": 1, "scene_goal": "新"}])
        result = seeded_repo.get_scene_beats("test_proj", 1)
        assert len(result) == 1
        assert result[0]["scene_goal"] == "新"


class TestReviews:
    def test_save_and_get_review(self, seeded_repo):
        # Get chapter id
        chapter = seeded_repo.get_chapter("test_proj", 1)
        assert chapter is not None

        review_id = seeded_repo.save_review(
            project_id="test_proj",
            chapter_id=chapter["id"],
            passed=True,
            score=92,
            setting_score=23,
            logic_score=20,
            poison_score=18,
            text_score=16,
            pacing_score=15,
            issues=[],
            suggestions=[],
        )
        assert review_id > 0

        review = seeded_repo.get_latest_review("test_proj", chapter["id"])
        assert review["score"] == 92


class TestChapterState:
    def test_save_and_get_chapter_state(self, seeded_repo):
        state_data = {"assets": {"credits": 100}, "character_states": {"主角": {"level": "Lv1"}}}
        ok = seeded_repo.save_chapter_state("test_proj", 1, state_data, "第1章状态卡")
        assert ok

        result = seeded_repo.get_chapter_state("test_proj", 1)
        assert result is not None
        assert result["state_data"]["assets"]["credits"] == 100


class TestVersions:
    def test_save_version(self, seeded_repo):
        seeded_repo.save_chapter_content("test_proj", 1, "初始内容", "第一章")
        vid = seeded_repo.save_version("test_proj", 1, "初始内容", created_by="author")
        assert vid > 0


class TestTasks:
    def test_start_and_complete_task(self, seeded_repo):
        tid = seeded_repo.start_task("test_proj", 1, "create", "author")
        assert tid > 0
        ok = seeded_repo.complete_task(tid, success=True)
        assert ok

    def test_get_chapter_retry_count(self, seeded_repo):
        assert seeded_repo.get_chapter_retry_count("test_proj", 1) == 0
        seeded_repo.start_task("test_proj", 1, "revise", "author")
        assert seeded_repo.get_chapter_retry_count("test_proj", 1) == 1


class TestMessages:
    def test_send_and_get_messages(self, seeded_repo):
        msg_id = seeded_repo.send_message(
            "test_proj", "editor", "planner", "FLAG_ISSUE",
            {"issue": "设定冲突"}, chapter_number=1,
        )
        assert msg_id > 0

        msgs = seeded_repo.get_pending_messages("test_proj", "planner")
        assert len(msgs) == 1
        assert msgs[0]["from_agent"] == "editor"


class TestArtifacts:
    def test_save_artifact(self, seeded_repo):
        aid = seeded_repo.save_artifact(
            "test_proj", 1, "author", "draft",
            content_json={"title": "第一章", "word_count": 2800},
        )
        assert len(aid) > 0


class TestPublish:
    def test_publish_chapter(self, seeded_repo):
        seeded_repo.update_chapter_status("test_proj", 1, "reviewed")
        ok = seeded_repo.publish_chapter("test_proj", 1)
        assert ok
        assert seeded_repo.get_chapter_status("test_proj", 1) == "published"
