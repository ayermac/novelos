"""Phase C 专项测试 — SSE Streaming + 交互补齐 (v5.2).

验收标准：
- SSE streaming 端点返回正确事件格式
- 项目设置可编辑
- Review approve/reject 工作正常
- Style Bible 可编辑
"""

from __future__ import annotations

import tempfile
import unittest

from novel_factory.config.settings import load_settings
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.workflow.runner import run_with_graph_stream


class TestSSEStreaming(unittest.TestCase):
    """SSE Streaming 功能测试。"""

    def setUp(self):
        """Set up test fixtures with isolated database."""
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_file.name
        self.temp_file.close()
        init_db(self.db_path)
        self.repo = Repository(self.db_path)

    def tearDown(self):
        """Clean up test database."""
        import os
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_stream_returns_step_events(self):
        """SSE stream 返回 step_start/step_complete 事件。"""
        self.repo.create_project("sse-test-1", "SSE Test Project 1")
        conn = self.repo._conn()
        try:
            conn.execute(
                """INSERT INTO chapters
                (project_id, chapter_number, title, status, word_count)
                VALUES (?, ?, ?, ?, ?)""",
                ("sse-test-1", 1, "Test Chapter", "planned", 0),
            )
            conn.commit()
        finally:
            conn.close()

        settings = load_settings()
        settings.db_path = self.db_path
        events = list(run_with_graph_stream("sse-test-1", 1, settings, self.repo, "stub"))

        event_types = [e["type"] for e in events]
        self.assertIn("step_start", event_types)
        self.assertIn("step_complete", event_types)
        self.assertIn("run_complete", event_types)

    def test_step_start_has_required_fields(self):
        """step_start 事件包含必需字段。"""
        self.repo.create_project("sse-test-2", "SSE Test Project 2")
        conn = self.repo._conn()
        try:
            conn.execute(
                """INSERT INTO chapters
                (project_id, chapter_number, title, status, word_count)
                VALUES (?, ?, ?, ?, ?)""",
                ("sse-test-2", 1, "Test Chapter", "planned", 0),
            )
            conn.commit()
        finally:
            conn.close()

        settings = load_settings()
        settings.db_path = self.db_path
        events = list(run_with_graph_stream("sse-test-2", 1, settings, self.repo, "stub"))

        step_starts = [e for e in events if e["type"] == "step_start"]
        self.assertGreater(len(step_starts), 0)

        for event in step_starts:
            self.assertIn("agent", event)
            self.assertIn("timestamp", event)

    def test_step_complete_has_duration(self):
        """step_complete 事件包含 duration_ms。"""
        self.repo.create_project("sse-test-3", "SSE Test Project 3")
        conn = self.repo._conn()
        try:
            conn.execute(
                """INSERT INTO chapters
                (project_id, chapter_number, title, status, word_count)
                VALUES (?, ?, ?, ?, ?)""",
                ("sse-test-3", 1, "Test Chapter", "planned", 0),
            )
            conn.commit()
        finally:
            conn.close()

        settings = load_settings()
        settings.db_path = self.db_path
        events = list(run_with_graph_stream("sse-test-3", 1, settings, self.repo, "stub"))

        step_completes = [e for e in events if e["type"] == "step_complete"]
        self.assertGreater(len(step_completes), 0)

        for event in step_completes:
            self.assertIn("agent", event)
            self.assertIn("duration_ms", event)
            self.assertGreater(event["duration_ms"], 0)

    def test_run_complete_has_status(self):
        """run_complete 事件包含 chapter_status。"""
        self.repo.create_project("sse-test-4", "SSE Test Project 4")
        conn = self.repo._conn()
        try:
            conn.execute(
                """INSERT INTO chapters
                (project_id, chapter_number, title, status, word_count)
                VALUES (?, ?, ?, ?, ?)""",
                ("sse-test-4", 1, "Test Chapter", "planned", 0),
            )
            conn.commit()
        finally:
            conn.close()

        settings = load_settings()
        settings.db_path = self.db_path
        events = list(run_with_graph_stream("sse-test-4", 1, settings, self.repo, "stub"))

        run_complete = next((e for e in events if e["type"] == "run_complete"), None)
        self.assertIsNotNone(run_complete)
        self.assertIn("chapter_status", run_complete)
        self.assertIn("run_id", run_complete)


class TestProjectSettingsEdit(unittest.TestCase):
    """项目设置编辑 API 测试。"""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_file.name
        self.temp_file.close()
        init_db(self.db_path)
        self.repo = Repository(self.db_path)

    def tearDown(self):
        import os
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_update_project_name(self):
        self.repo.create_project("edit-test-1", "Original Name")
        updated = self.repo.update_project("edit-test-1", name="New Name")
        self.assertIsNotNone(updated)
        self.assertEqual(updated["name"], "New Name")

    def test_update_project_description(self):
        self.repo.create_project("edit-test-2", "Test Project")
        updated = self.repo.update_project("edit-test-2", description="New description")
        self.assertIsNotNone(updated)
        self.assertEqual(updated["description"], "New description")

    def test_update_multiple_fields(self):
        self.repo.create_project("edit-test-3", "Test Project")
        updated = self.repo.update_project(
            "edit-test-3", name="Updated Name", genre="玄幻", target_words=2000000
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated["name"], "Updated Name")
        self.assertEqual(updated["genre"], "玄幻")


class TestReviewOperations(unittest.TestCase):
    """Review 操作按钮测试。"""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_file.name
        self.temp_file.close()
        init_db(self.db_path)
        self.repo = Repository(self.db_path)

    def tearDown(self):
        import os
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_approve_changes_status_to_reviewed(self):
        self.repo.create_project("review-test-1", "Review Test 1")
        conn = self.repo._conn()
        try:
            conn.execute(
                """INSERT INTO chapters
                (project_id, chapter_number, title, status, word_count)
                VALUES (?, ?, ?, ?, ?)""",
                ("review-test-1", 1, "Test Chapter", "review", 0),
            )
            conn.commit()
        finally:
            conn.close()

        updated = self.repo.update_chapter_status("review-test-1", 1, "reviewed")
        self.assertTrue(updated)

        chapter = self.repo.get_chapter("review-test-1", 1)
        self.assertEqual(chapter["status"], "reviewed")

    def test_reject_changes_status_to_revision(self):
        """reject 将章节状态改为 revision。"""
        self.repo.create_project("review-test-2", "Review Test 2")
        conn = self.repo._conn()
        try:
            conn.execute(
                """INSERT INTO chapters
                (project_id, chapter_number, title, status, word_count)
                VALUES (?, ?, ?, ?, ?)""",
                ("review-test-2", 1, "Test Chapter", "review", 0),
            )
            conn.commit()
        finally:
            conn.close()

        # Note: save_chapter_review_note requires existing workflow_run
        # For this test, we just verify status change
        updated = self.repo.update_chapter_status("review-test-2", 1, "revision")
        self.assertTrue(updated)

        chapter = self.repo.get_chapter("review-test-2", 1)
        self.assertEqual(chapter["status"], "revision")


class TestStyleBibleEdit(unittest.TestCase):
    """Style 编辑入口测试。"""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_file.name
        self.temp_file.close()
        init_db(self.db_path)
        self.repo = Repository(self.db_path)

    def tearDown(self):
        import os
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_save_style_bible(self):
        self.repo.create_project("style-test-1", "Style Test 1")
        bible_dict = {"name": "Test Style", "genre": "玄幻", "voice": {"tone": "轻松"}}
        bible_id = self.repo.save_style_bible("style-test-1", bible_dict)
        self.assertIsNotNone(bible_id)

        saved = self.repo.get_style_bible("style-test-1")
        self.assertIsNotNone(saved)
        self.assertEqual(saved["name"], "Test Style")

    def test_update_style_bible(self):
        self.repo.create_project("style-test-2", "Style Test 2")
        self.repo.save_style_bible("style-test-2", {"name": "Initial", "genre": "玄幻"})

        updated = self.repo.update_style_bible(
            "style-test-2", {"name": "Updated", "genre": "都市"}
        )
        self.assertTrue(updated)

        saved = self.repo.get_style_bible("style-test-2")
        self.assertEqual(saved["name"], "Updated")


if __name__ == "__main__":
    unittest.main()
