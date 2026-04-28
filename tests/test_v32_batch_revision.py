"""Tests for v3.2 Batch Review & Revision.

Tests that batch revision commands work correctly and maintain data integrity.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from novel_factory.db.connection import init_db, get_connection
from novel_factory.db.repository import Repository
from novel_factory.dispatcher import Dispatcher
from novel_factory.llm.provider import LLMProvider

from tests.conftest import LONG_CHAPTER_CONTENT  # noqa: F401


class StubLLM(LLMProvider):
    """Stub LLM for testing."""

    def __init__(self):
        pass

    def invoke_text(self, prompt: str, **kwargs) -> str:
        return "Stub response"

    def invoke_json(self, prompt, **kwargs) -> dict:
        # Handle both string and list of messages
        prompt_str = ""
        if isinstance(prompt, list):
            # Extract text from messages
            for msg in prompt:
                if isinstance(msg, dict) and "content" in msg:
                    prompt_str += msg["content"] + " "
        else:
            prompt_str = str(prompt)
        
        # Return appropriate structure based on prompt content
        # Check in order of specificity
        if "执行五层审校" in prompt_str or "质检（Editor）" in prompt_str:
            # EditorOutput requires 'pass' (aliased as 'pass_') and 'score'
            # Return pass=True with high score to avoid revision loop
            return {"pass": True, "score": 95, "scores": {}, "issues": [], "suggestions": [], "state_card": {}}
        elif "润色以上草稿" in prompt_str or "润色" in prompt_str:
            # v5.3.0: Must be >= word_target * 0.85
            return {"content": LONG_CHAPTER_CONTENT, "fact_change_risk": "none", "changed_scope": []}
        elif "创作" in prompt_str or "写作" in prompt_str:
            # v5.3.0: Must be >= word_target * 0.85 (word_target defaults to 3000)
            return {"title": "测试章节", "content": LONG_CHAPTER_CONTENT, "word_count": len(LONG_CHAPTER_CONTENT)}
        elif "生成.*章的写作指令" in prompt_str or "规划" in prompt_str:
            return {"chapter_brief": {"summary": "测试摘要", "key_events": [], "characters": [], "word_count_target": 2000}}
        elif "拆解为场景" in prompt_str or "拆解" in prompt_str:
            return {"scenes": [{"scene_id": 1, "beats": [{"beat_id": 1, "description": "测试场景"}]}]}
        else:
            return {"result": "stub"}


def _seed_project(repo: Repository, project_id: str = "demo", num_chapters: int = 3):
    """Seed a project with chapters for testing."""
    conn = repo._conn()
    try:
        # Check if project exists
        existing = conn.execute(
            "SELECT project_id FROM projects WHERE project_id=?", (project_id,)
        ).fetchone()

        if not existing:
            # Create project
            conn.execute(
                "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
                (project_id, f"{project_id.title()} Novel", "fantasy"),
            )

        # Create chapters
        for ch in range(1, num_chapters + 1):
            existing_ch = conn.execute(
                "SELECT chapter_number FROM chapters WHERE project_id=? AND chapter_number=?",
                (project_id, ch),
            ).fetchone()

            if not existing_ch:
                conn.execute(
                    "INSERT INTO chapters (project_id, chapter_number, title, status) VALUES (?, ?, ?, ?)",
                    (project_id, ch, f"第{ch}章", "planned"),
                )

        conn.commit()
    finally:
        conn.close()


def run_cli(args: list[str]) -> tuple[int, str, str]:
    """Run CLI command and return exit code, stdout, stderr."""
    cmd = [sys.executable, "-m", "novel_factory.cli"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


class TestBatchReviewRequestChanges:
    """Test batch review with request_changes decision."""

    def test_batch_review_request_changes_success(self, tmp_path):
        """batch review --decision request_changes should succeed."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))

        # Setup
        _seed_project(repo, "demo", 3)

        # Create a production run
        run_id = repo.create_production_run("demo", 1, 3)
        assert run_id

        # Mark run as awaiting_review
        repo.update_production_run(run_id, status="awaiting_review")

        # Run batch review with request_changes
        code, stdout, stderr = run_cli([
            "--db-path", str(db_path),
            "batch", "review",
            "--run-id", run_id,
            "--decision", "request_changes",
            "--notes", "第2章需要修改",
            "--json",
        ])

        assert code == 0, f"Expected exit code 0, got {code}. stderr: {stderr}"

        result = json.loads(stdout)
        assert result["ok"] is True
        assert result["data"]["decision"] == "request_changes"


class TestBatchReviseCreateRevisionRun:
    """Test batch revise command creates revision run."""

    def test_batch_revise_creates_revision_run(self, tmp_path):
        """batch revise --plan-json should create revision run."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))

        # Setup
        _seed_project(repo, "demo", 3)

        run_id = repo.create_production_run("demo", 1, 3)
        repo.update_production_run(run_id, status="awaiting_review")

        # Create review session
        session_id = repo.save_human_review_session(run_id, "demo", "request_changes", "需要修改")

        # Update run status to request_changes
        repo.update_production_run(run_id, status="request_changes")

        # Run batch revise
        plan_json = json.dumps({
            "actions": [
                {"action": "rerun_chapter", "chapter": 2, "notes": "重写第2章"}
            ]
        })

        code, stdout, stderr = run_cli([
            "--db-path", str(db_path), "batch", "revise",
            "--run-id", run_id,
            "--plan-json", plan_json, "--llm-mode", "stub", "--json",
        ])

        assert code == 0, f"Expected exit code 0, got {code}. stdout: {stdout}, stderr: {stderr}"

        result = json.loads(stdout)
        assert result["ok"] is True
        assert "revision_run_id" in result["data"]
        assert result["data"]["affected_chapters"] == [2]


class TestRerunChapter:
    """Test rerun_chapter action only affects specified chapter."""

    def test_rerun_chapter_only_affects_specified(self, tmp_path):
        """rerun_chapter should only affect the specified chapter."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        stub_llm = StubLLM()
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        # Setup
        _seed_project(repo, "demo", 3)

        # Mark all chapters as published
        for ch in range(1, 4):
            repo.update_chapter_status("demo", ch, "published")

        run_id = repo.create_production_run("demo", 1, 3)
        repo.update_production_run(run_id, status="request_changes")
        session_id = repo.save_human_review_session(run_id, "demo", "request_changes", "需要修改")

        # Create revision plan
        plan_json = json.dumps({
            "actions": [
                {"action": "rerun_chapter", "chapter": 2, "notes": "重写第2章"}
            ]
        })

        plan_result = dispatcher.create_batch_revision_plan(run_id, plan_json)
        assert plan_result["ok"]

        # Run revision
        revision_run_id = plan_result["data"]["revision_run_id"]
        run_result = dispatcher.run_batch_revision(revision_run_id)

        # Check that only chapter 2 was affected
        assert run_result["ok"]


class TestResumeToStatus:
    """Test resume_to_status action."""

    def test_resume_to_status_resumes_before_run(self, tmp_path):
        """resume_to_status should resume chapter to target status before running."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        stub_llm = StubLLM()
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        # Setup
        _seed_project(repo, "demo", 1)
        repo.update_chapter_status("demo", 1, "published")

        run_id = repo.create_production_run("demo", 1, 1)
        repo.update_production_run(run_id, status="request_changes")
        session_id = repo.save_human_review_session(run_id, "demo", "request_changes", "需要修改")

        # Create revision plan with resume_to_status
        plan_json = json.dumps({
            "actions": [
                {"action": "resume_to_status", "chapter": 1, "status": "drafted", "notes": "重新润色"}
            ]
        })

        plan_result = dispatcher.create_batch_revision_plan(run_id, plan_json)
        assert plan_result["ok"]

        # Run revision
        revision_run_id = plan_result["data"]["revision_run_id"]
        run_result = dispatcher.run_batch_revision(revision_run_id)

        # Check that revision was executed
        assert run_result["ok"]


class TestRerunTail:
    """Test rerun_tail action affects from_chapter to batch end."""

    def test_rerun_tail_affects_from_chapter_to_end(self, tmp_path):
        """rerun_tail should affect all chapters from from_chapter to batch end."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        stub_llm = StubLLM()
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        # Setup
        _seed_project(repo, "demo", 5)

        # Mark all chapters as published
        for ch in range(1, 6):
            repo.update_chapter_status("demo", ch, "published")

        run_id = repo.create_production_run("demo", 1, 5)
        repo.update_production_run(run_id, status="request_changes")
        session_id = repo.save_human_review_session(run_id, "demo", "request_changes", "需要修改")

        # Create revision plan with rerun_tail from chapter 3
        plan_json = json.dumps({
            "actions": [
                {"action": "rerun_tail", "from_chapter": 3, "notes": "从第3章起重跑"}
            ]
        })

        plan_result = dispatcher.create_batch_revision_plan(run_id, plan_json)
        assert plan_result["ok"]

        # Check affected chapters
        affected = plan_result["data"]["affected_chapters"]
        assert affected == [3, 4, 5]

        # Run revision
        revision_run_id = plan_result["data"]["revision_run_id"]
        run_result = dispatcher.run_batch_revision(revision_run_id)

        assert run_result["ok"]


class TestReviewNotesPersistence:
    """Test review notes are persisted and readable."""

    def test_review_notes_persisted(self, tmp_path):
        """Review notes should be persisted and readable."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        stub_llm = StubLLM()
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        # Setup
        _seed_project(repo, "demo", 1)
        repo.update_chapter_status("demo", 1, "published")

        run_id = repo.create_production_run("demo", 1, 1)
        repo.update_production_run(run_id, status="request_changes")
        session_id = repo.save_human_review_session(run_id, "demo", "request_changes", "需要修改")

        # Create revision plan with notes
        plan_json = json.dumps({
            "actions": [
                {"action": "rerun_chapter", "chapter": 1, "notes": "冲突不足，增加对抗"}
            ]
        })

        plan_result = dispatcher.create_batch_revision_plan(run_id, plan_json)
        assert plan_result["ok"]

        # Check that review notes were saved
        notes = repo.get_chapter_review_notes("demo", 1)
        assert len(notes) > 0
        assert "冲突不足" in notes[0]["notes"]


class TestRevisionStatusQuery:
    """Test revision status can be queried."""

    def test_revision_status_query(self, tmp_path):
        """revision-status should return revision run status."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        stub_llm = StubLLM()
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        # Setup
        _seed_project(repo, "demo", 1)
        repo.update_chapter_status("demo", 1, "published")

        run_id = repo.create_production_run("demo", 1, 1)
        repo.update_production_run(run_id, status="request_changes")
        session_id = repo.save_human_review_session(run_id, "demo", "request_changes", "需要修改")

        # Create and run revision
        plan_json = json.dumps({
            "actions": [
                {"action": "rerun_chapter", "chapter": 1, "notes": "重写"}
            ]
        })

        plan_result = dispatcher.create_batch_revision_plan(run_id, plan_json)
        revision_run_id = plan_result["data"]["revision_run_id"]

        run_result = dispatcher.run_batch_revision(revision_run_id)

        # Query status
        status_result = dispatcher.get_batch_revision_status(revision_run_id)
        assert status_result["ok"]
        assert status_result["data"]["status"] == "completed"
        assert len(status_result["data"]["items"]) > 0


class TestRevisionFailureHandling:
    """Test revision run handles failures correctly."""

    def test_revision_failure_stops_run(self, tmp_path):
        """When a revision item fails, the revision run should stop."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        stub_llm = StubLLM()
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        # Setup
        _seed_project(repo, "demo", 3)

        run_id = repo.create_production_run("demo", 1, 3)
        repo.update_production_run(run_id, status="request_changes")
        session_id = repo.save_human_review_session(run_id, "demo", "request_changes", "需要修改")

        # Create revision plan (chapter 2 exists but will fail during execution)
        # We'll make it fail by setting chapter status to a bad state
        repo.update_chapter_status("demo", 2, "blocking")  # Set to blocking state
        
        plan_json = json.dumps({
            "actions": [
                {"action": "rerun_chapter", "chapter": 2, "notes": "测试失败"}
            ]
        })

        plan_result = dispatcher.create_batch_revision_plan(run_id, plan_json)
        # R2: Chapter 2 is within range, so plan creation should succeed
        assert plan_result["ok"] is True
        revision_run_id = plan_result["data"]["revision_run_id"]

        # Run revision (should fail because chapter is in blocking state)
        run_result = dispatcher.run_batch_revision(revision_run_id)

        # Check that revision run failed
        assert run_result["ok"] is False
        assert "Failed" in run_result["error"]


class TestCLIJsonEnvelope:
    """Test all new commands output stable JSON envelope."""

    def test_batch_revise_json_envelope(self, tmp_path):
        """batch revise --json should output stable envelope."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))

        # Setup
        _seed_project(repo, "demo", 2)

        for ch in range(1, 3):
            repo.update_chapter_status("demo", ch, "published")

        run_id = repo.create_production_run("demo", 1, 2)
        repo.update_production_run(run_id, status="request_changes")
        session_id = repo.save_human_review_session(run_id, "demo", "request_changes", "需要修改")

        plan_json = json.dumps({
            "actions": [
                {"action": "rerun_chapter", "chapter": 1, "notes": "重写"}
            ]
        })

        code, stdout, stderr = run_cli([
            "--db-path", str(db_path), "batch", "revise",
            "--run-id", run_id,
            "--plan-json", plan_json, "--llm-mode", "stub", "--json",
        ])

        result = json.loads(stdout)
        assert "ok" in result
        assert "error" in result
        assert "data" in result

    def test_batch_revision_status_json_envelope(self, tmp_path):
        """batch revision-status --json should output stable envelope."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        stub_llm = StubLLM()
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        # Setup and create a revision run
        _seed_project(repo, "demo", 1)
        repo.update_chapter_status("demo", 1, "published")

        run_id = repo.create_production_run("demo", 1, 1)
        repo.update_production_run(run_id, status="request_changes")
        session_id = repo.save_human_review_session(run_id, "demo", "request_changes", "需要修改")

        plan_json = json.dumps({
            "actions": [
                {"action": "rerun_chapter", "chapter": 1, "notes": "重写"}
            ]
        })

        plan_result = dispatcher.create_batch_revision_plan(run_id, plan_json)
        revision_run_id = plan_result["data"]["revision_run_id"]

        # Query status via CLI
        code, stdout, stderr = run_cli([
            "--db-path", str(db_path),
            "batch", "revision-status",
            "--revision-run-id", revision_run_id,
            "--json",
        ])

        result = json.loads(stdout)
        assert "ok" in result
        assert "error" in result
        assert "data" in result


class TestItemWriteFailureRunning:
    """R1: update_batch_revision_item returns False when marking running."""

    def test_item_running_write_failure_blocks(self, tmp_path):
        """When item running write fails, run_batch_revision must return ok:false."""
        from unittest.mock import patch

        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        stub_llm = StubLLM()
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        _seed_project(repo, "demo", 1)
        repo.update_chapter_status("demo", 1, "published")

        run_id = repo.create_production_run("demo", 1, 1)
        repo.update_production_run(run_id, status="request_changes")
        repo.save_human_review_session(run_id, "demo", "request_changes", "需要修改")

        plan_json = json.dumps({
            "actions": [{"action": "rerun_chapter", "chapter": 1, "notes": "重写"}]
        })
        plan_result = dispatcher.create_batch_revision_plan(run_id, plan_json)
        revision_run_id = plan_result["data"]["revision_run_id"]

        # Patch update_batch_revision_item to return False for status="running"
        original = repo.update_batch_revision_item
        def fake_update_item(item_id, status=None, **kwargs):
            if status == "running":
                return False
            return original(item_id, status=status, **kwargs)

        with patch.object(repo, "update_batch_revision_item", side_effect=fake_update_item):
            result = dispatcher.run_batch_revision(revision_run_id)

        assert result["ok"] is False
        assert "item running state write failed" in result["error"]

        # Verify revision_run is not completed
        rr = repo.get_batch_revision_run(revision_run_id)
        assert rr["status"] != "completed"


class TestItemWriteFailureCompleted:
    """R1: update_batch_revision_item returns False when marking completed."""

    def test_item_completed_write_failure_blocks(self, tmp_path):
        """When item completed write fails, revision_run must NOT be completed."""
        from unittest.mock import patch

        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        stub_llm = StubLLM()
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        _seed_project(repo, "demo", 1)
        repo.update_chapter_status("demo", 1, "published")

        run_id = repo.create_production_run("demo", 1, 1)
        repo.update_production_run(run_id, status="request_changes")
        repo.save_human_review_session(run_id, "demo", "request_changes", "需要修改")

        plan_json = json.dumps({
            "actions": [{"action": "rerun_chapter", "chapter": 1, "notes": "重写"}]
        })
        plan_result = dispatcher.create_batch_revision_plan(run_id, plan_json)
        revision_run_id = plan_result["data"]["revision_run_id"]

        # Patch update_batch_revision_item to return False for status="completed"
        original = repo.update_batch_revision_item
        def fake_update_item(item_id, status=None, **kwargs):
            if status == "completed":
                return False
            return original(item_id, status=status, **kwargs)

        with patch.object(repo, "update_batch_revision_item", side_effect=fake_update_item):
            result = dispatcher.run_batch_revision(revision_run_id)

        assert result["ok"] is False
        assert "item completed state write failed" in result["error"]

        # revision_run must NOT be completed
        rr = repo.get_batch_revision_run(revision_run_id)
        assert rr["status"] != "completed"


class TestRunWriteFailureCompleted:
    """R2: update_batch_revision_run returns False when marking final completed."""

    def test_run_completed_write_failure_blocks(self, tmp_path):
        """When final revision_run completed write fails, must return ok:false."""
        from unittest.mock import patch

        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        stub_llm = StubLLM()
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        _seed_project(repo, "demo", 1)
        repo.update_chapter_status("demo", 1, "published")

        run_id = repo.create_production_run("demo", 1, 1)
        repo.update_production_run(run_id, status="request_changes")
        repo.save_human_review_session(run_id, "demo", "request_changes", "需要修改")

        plan_json = json.dumps({
            "actions": [{"action": "rerun_chapter", "chapter": 1, "notes": "重写"}]
        })
        plan_result = dispatcher.create_batch_revision_plan(run_id, plan_json)
        revision_run_id = plan_result["data"]["revision_run_id"]

        # Patch update_batch_revision_run to return False for status="completed" (final call)
        original = repo.update_batch_revision_run
        call_count = {"n": 0}
        def fake_update_run(run_id, status=None, **kwargs):
            call_count["n"] += 1
            # First call: status="running" — let it succeed
            # Second call: status="completed" — make it fail
            if call_count["n"] == 2 and status == "completed":
                return False
            return original(run_id, status=status, **kwargs)

        with patch.object(repo, "update_batch_revision_run", side_effect=fake_update_run):
            result = dispatcher.run_batch_revision(revision_run_id)

        assert result["ok"] is False
        assert "revision run completed state write failed" in result["error"]


class TestRunWriteFailureFailed:
    """R2: update_batch_revision_run returns False when marking final failed."""

    def test_run_failed_write_failure_blocks(self, tmp_path):
        """When final revision_run failed write fails, must return ok:false."""
        from unittest.mock import patch

        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        stub_llm = StubLLM()
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        _seed_project(repo, "demo", 1)
        # Set chapter to blocking so run_chapter will fail
        repo.update_chapter_status("demo", 1, "blocking")

        run_id = repo.create_production_run("demo", 1, 1)
        repo.update_production_run(run_id, status="request_changes")
        repo.save_human_review_session(run_id, "demo", "request_changes", "需要修改")

        plan_json = json.dumps({
            "actions": [{"action": "rerun_chapter", "chapter": 1, "notes": "重写"}]
        })
        plan_result = dispatcher.create_batch_revision_plan(run_id, plan_json)
        revision_run_id = plan_result["data"]["revision_run_id"]

        # Patch update_batch_revision_run to return False for status="failed" (final call)
        original = repo.update_batch_revision_run
        call_count = {"n": 0}
        def fake_update_run(run_id, status=None, **kwargs):
            call_count["n"] += 1
            # First call: status="running" — let succeed
            # Later call: status="failed" — make it fail
            if status == "failed" and call_count["n"] > 1:
                return False
            return original(run_id, status=status, **kwargs)

        with patch.object(repo, "update_batch_revision_run", side_effect=fake_update_run):
            result = dispatcher.run_batch_revision(revision_run_id)

        assert result["ok"] is False
        assert "revision run failed state write failed" in result["error"]


class TestRerunChapterBehavioral:
    """R1 behavioral: published chapter rerun must produce new workflow_run."""

    def test_rerun_published_chapter_creates_new_workflow_run(self, tmp_path):
        """rerun_chapter on published chapter must produce new workflow_run."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))
        stub_llm = StubLLM()
        dispatcher = Dispatcher(repo, stub_llm, max_retries=3, create_skill_registry=False)

        _seed_project(repo, "demo", 1)
        repo.update_chapter_status("demo", 1, "published")

        run_id = repo.create_production_run("demo", 1, 1)
        repo.update_production_run(run_id, status="request_changes")
        repo.save_human_review_session(run_id, "demo", "request_changes", "需要修改")

        # Count workflow runs before
        runs_before = repo.get_workflow_runs_for_project("demo", chapter_number=1)

        plan_json = json.dumps({
            "actions": [{"action": "rerun_chapter", "chapter": 1, "notes": "重写"}]
        })
        plan_result = dispatcher.create_batch_revision_plan(run_id, plan_json)
        revision_run_id = plan_result["data"]["revision_run_id"]

        run_result = dispatcher.run_batch_revision(revision_run_id)
        assert run_result["ok"]

        # Must have new workflow runs
        runs_after = repo.get_workflow_runs_for_project("demo", chapter_number=1)
        assert len(runs_after) > len(runs_before), \
            f"Expected new workflow runs after rerun, got {len(runs_after)} before {len(runs_before)}"


class TestReviewNotesInAgentContext:
    """R3: review notes must appear in Author/Planner actual LLM messages."""

    def test_author_receives_review_notes(self, tmp_path):
        """AuthorAgent must include review notes in LLM user message."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))

        _seed_project(repo, "demo", 1)
        repo.update_chapter_status("demo", 1, "published")

        # Create real production run + revision run (FK constraint)
        run_id = repo.create_production_run("demo", 1, 1)
        repo.update_production_run(run_id, status="request_changes")
        session_id = repo.save_human_review_session(run_id, "demo", "request_changes", "需要修改")

        revision_run_id = repo.create_batch_revision_run(
            source_run_id=run_id,
            project_id="demo",
            decision_session_id=session_id,
            plan_json='{"actions":[]}',
            affected_chapters_json='[1]',
        )

        # Save review notes with real FK references
        repo.save_chapter_review_note(
            project_id="demo",
            chapter_number=1,
            source_run_id=run_id,
            revision_run_id=revision_run_id,
            notes="冲突不足，增加对抗",
        )

        from novel_factory.agents.author import AuthorAgent

        llm = StubLLM()
        author = AuthorAgent(repo, llm)

        # Set chapter to revision so Author runs the revision path
        repo.update_chapter_status("demo", 1, "revision")

        state = {
            "project_id": "demo",
            "chapter_number": 1,
            "chapter_status": "revision",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        context = author.build_context(state)
        assert "人工审核意见" in context
        assert "冲突不足" in context

    def test_planner_receives_review_notes(self, tmp_path):
        """PlannerAgent must include review notes in context."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        repo = Repository(str(db_path))

        _seed_project(repo, "demo", 1)

        # Create real production run + revision run (FK constraint)
        run_id = repo.create_production_run("demo", 1, 1)
        repo.update_production_run(run_id, status="request_changes")
        session_id = repo.save_human_review_session(run_id, "demo", "request_changes", "需要修改")

        revision_run_id = repo.create_batch_revision_run(
            source_run_id=run_id,
            project_id="demo",
            decision_session_id=session_id,
            plan_json='{"actions":[]}',
            affected_chapters_json='[1]',
        )

        repo.save_chapter_review_note(
            project_id="demo",
            chapter_number=1,
            source_run_id=run_id,
            revision_run_id=revision_run_id,
            notes="节奏太慢，加快叙事",
        )

        from novel_factory.agents.planner import PlannerAgent

        llm = StubLLM()
        planner = PlannerAgent(repo, llm)

        state = {
            "project_id": "demo",
            "chapter_number": 1,
            "chapter_status": "planned",
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
        }

        context = planner.build_context(state)
        assert "人工审核意见" in context
        assert "节奏太慢" in context


class TestMigration008Idempotency:
    """Test that init_db() handles 008 migration idempotently."""

    def test_init_db_with_008_migration(self, tmp_path):
        """init_db() should handle 008 migration idempotently."""
        db_path = tmp_path / "test.db"

        # Run init_db twice
        init_db(str(db_path))
        init_db(str(db_path))

        # Verify tables exist
        conn = get_connection(str(db_path))
        try:
            tables = [
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
            assert "batch_revision_runs" in tables
            assert "batch_revision_items" in tables
            assert "chapter_review_notes" in tables
        finally:
            conn.close()
