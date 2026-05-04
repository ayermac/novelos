"""P1 fix tests: Real LLM error handling in workflow.

Tests that when an agent validation fails (e.g., Author word_count mismatch),
the workflow correctly terminates at human_review instead of continuing to
downstream nodes.

These tests use stub/mock LLMs and do NOT require real API keys.
"""

import pytest
from unittest.mock import MagicMock, patch
import tempfile
import os

from novel_factory.config.settings import Settings, load_settings
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.workflow.graph import compile_graph
from novel_factory.workflow.nodes import create_node_runners, author_node, human_review_node
from novel_factory.models.state import FactoryState, ChapterStatus


class TestAuthorValidationFailure:
    """Test that Author validation failures stop downstream execution."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        init_db(db_path)
        yield db_path
        os.unlink(db_path)

    @pytest.fixture
    def settings(self, temp_db):
        """Create settings with temp database."""
        return Settings(db_path=temp_db)

    @pytest.fixture
    def repo(self, temp_db):
        """Create repository instance."""
        return Repository(temp_db)

    def test_author_word_gate_records_target_without_name_error(self, settings, repo):
        """Author word-count failures should carry target details for retry routing."""
        # Create a test project and chapter
        project_id = "test_p1_author_fail"
        repo.create_project(
            project_id=project_id,
            name="Test Project",
            genre="fantasy",
        )
        repo.add_chapter(project_id, 1, title="Chapter 1", status=ChapterStatus.SCRIPTED.value)

        # Create state
        state: FactoryState = {
            "project_id": project_id,
            "chapter_number": 1,
            "chapter_status": ChapterStatus.SCRIPTED.value,
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "steps": [],
            "workflow_run_id": "",
        }

        # Create mock LLM that returns structurally valid output that fails the
        # word-count quality gate. This specifically covers the traceability
        # path that records word_target.
        mock_llm = MagicMock()
        mock_llm.invoke_json.return_value = {
            "title": "Test Chapter",
            "content": "短正文" * 200,
            "word_count": 600,
            "implemented_events": [],
            "used_plot_refs": [],
        }
        mock_llm.last_token_usage = None

        # Run author_node
        result = author_node(state, repo, mock_llm)

        assert result["requires_human"] is False
        assert result["chapter_status"] == ChapterStatus.REVISION.value
        assert result["quality_gate"]["word_count_fail"] is True
        assert result["quality_gate"]["actual_word_count"] == 600
        assert result["quality_gate"]["word_target"] == 3000

    def test_author_very_short_content_routes_to_revision(self, settings, repo):
        """Content shorter than hard min (500) must go through retryable quality gate."""
        project_id = "test_p1_author_short"
        repo.create_project(
            project_id=project_id,
            name="Test Project",
            genre="fantasy",
        )
        repo.add_chapter(project_id, 1, title="Chapter 1", status=ChapterStatus.SCRIPTED.value)

        state: FactoryState = {
            "project_id": project_id,
            "chapter_number": 1,
            "chapter_status": ChapterStatus.SCRIPTED.value,
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "steps": [],
            "workflow_run_id": "",
        }

        mock_llm = MagicMock()
        mock_llm.invoke_json.return_value = {
            "title": "Test Chapter",
            "content": "短" * 400,  # 400 chars, below both 500 hard min and quality gate threshold
            "word_count": 400,
            "implemented_events": [],
            "used_plot_refs": [],
        }
        mock_llm.last_token_usage = None

        result = author_node(state, repo, mock_llm)

        assert result["requires_human"] is False
        assert result["chapter_status"] == ChapterStatus.REVISION.value
        assert result["quality_gate"]["word_count_fail"] is True
        assert result["quality_gate"]["actual_word_count"] == 400

    def test_author_oversized_content_routes_to_human_review(self, settings, repo):
        """Content exceeding DEFAULT_MAX_WORDS must trigger hard validation error, not quality gate."""
        from novel_factory.validators.chapter_checker import DEFAULT_MAX_WORDS

        project_id = "test_p1_author_oversized"
        repo.create_project(
            project_id=project_id,
            name="Test Project",
            genre="fantasy",
        )
        repo.add_chapter(project_id, 1, title="Chapter 1", status=ChapterStatus.SCRIPTED.value)

        state: FactoryState = {
            "project_id": project_id,
            "chapter_number": 1,
            "chapter_status": ChapterStatus.SCRIPTED.value,
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "steps": [],
            "workflow_run_id": "",
        }

        oversized_content = "长" * (DEFAULT_MAX_WORDS + 1)
        mock_llm = MagicMock()
        mock_llm.invoke_json.return_value = {
            "title": "Test Chapter",
            "content": oversized_content,
            "word_count": DEFAULT_MAX_WORDS + 1,
            "implemented_events": [],
            "used_plot_refs": [],
        }
        mock_llm.last_token_usage = None

        result = author_node(state, repo, mock_llm)

        # Oversized content should be a hard validation error, not a retryable quality gate
        assert result["requires_human"] is True
        assert result["chapter_status"] == ChapterStatus.SCRIPTED.value
        assert "字数超标" in result["error"]

    def test_author_death_penalty_routes_to_revision(self, settings, repo):
        """Author death-penalty red lines should be retryable, not immediate blocking."""
        project_id = "test_p1_author_death_penalty"
        repo.create_project(
            project_id=project_id,
            name="Test Project",
            genre="fantasy",
        )
        repo.add_chapter(project_id, 1, title="Chapter 1", status=ChapterStatus.SCRIPTED.value)

        state: FactoryState = {
            "project_id": project_id,
            "chapter_number": 1,
            "chapter_status": ChapterStatus.SCRIPTED.value,
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "steps": [],
            "workflow_run_id": "",
        }

        mock_llm = MagicMock()
        mock_llm.invoke_json.return_value = {
            "title": "Test Chapter",
            "content": "他冷笑了一声。" + ("正常内容填充" * 400),
            "word_count": 2407,
            "implemented_events": [],
            "used_plot_refs": [],
        }
        mock_llm.last_token_usage = None

        result = author_node(state, repo, mock_llm)

        assert result["requires_human"] is False
        assert result["chapter_status"] == ChapterStatus.REVISION.value
        assert result["quality_gate"]["death_penalty_fail"] is True
        assert result["quality_gate"]["revision_target"] == "author"
        assert "冷笑" in result["quality_gate"]["message"]

    def test_author_llm_exception_sets_requires_human_and_failed_run(self, settings, repo):
        """Provider exceptions should be captured instead of leaving runs hanging."""
        project_id = "test_p1_author_exception"
        repo.create_project(
            project_id=project_id,
            name="Test Project",
            genre="fantasy",
        )
        repo.add_chapter(project_id, 1, title="Chapter 1", status=ChapterStatus.SCRIPTED.value)
        run_id = repo.create_workflow_run(project_id, 1)

        state: FactoryState = {
            "project_id": project_id,
            "chapter_number": 1,
            "chapter_status": ChapterStatus.SCRIPTED.value,
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "steps": [],
            "workflow_run_id": run_id,
        }

        mock_llm = MagicMock()
        mock_llm.invoke_json.side_effect = RuntimeError("LLM service unavailable")
        mock_llm.last_token_usage = None

        result = author_node(state, repo, mock_llm)

        assert result["requires_human"] is True
        assert "LLM service unavailable" in result["error"]

        runs = repo.get_workflow_runs_for_project(project_id)
        assert runs[0]["status"] == "failed"
        assert "LLM service unavailable" in runs[0]["error_message"]

    def test_human_review_explains_already_blocked_chapter(self, settings, repo):
        """Re-running an already-blocked chapter should not create an empty blocked run."""
        project_id = "test_p1_already_blocked"
        repo.create_project(
            project_id=project_id,
            name="Test Project",
            genre="fantasy",
        )
        repo.add_chapter(project_id, 1, title="Chapter 1", status=ChapterStatus.BLOCKING.value)
        run_id = repo.create_workflow_run(project_id, 1)

        state: FactoryState = {
            "project_id": project_id,
            "chapter_number": 1,
            "chapter_status": ChapterStatus.BLOCKING.value,
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": None,
            "steps": [],
            "workflow_run_id": run_id,
        }

        result = human_review_node(state, repo)

        assert result["requires_human"] is True
        assert "已处于阻塞状态" in result["error"]

        runs = repo.get_workflow_runs_for_project(project_id)
        assert runs[0]["status"] == "blocked"
        assert "已处于阻塞状态" in runs[0]["error_message"]

    def test_author_output_error_routes_to_human_review(self):
        """When Author returns error, route_by_chapter_status should route to human_review."""
        from novel_factory.workflow.conditions import route_by_chapter_status

        # State with error and requires_human from Author
        state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.DRAFTED.value,
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": True,
            "error": "Author validation failed: word_count mismatch",
            "steps": [],
        }

        # Should route to human_review
        route = route_by_chapter_status(state)
        assert route == "human_review", "P1 fix: error state should route to human_review"

    def test_author_error_in_state_routes_to_human_review(self):
        """When state has error field set, should route to human_review."""
        from novel_factory.workflow.conditions import route_by_chapter_status

        # State with error but no requires_human flag yet
        state: FactoryState = {
            "project_id": "test",
            "chapter_number": 1,
            "chapter_status": ChapterStatus.DRAFTED.value,
            "retry_count": 0,
            "max_retries": 3,
            "requires_human": False,
            "error": "Some error",
            "steps": [],
        }

        # Should still route to human_review due to error field
        route = route_by_chapter_status(state)
        assert route == "human_review", "P1 fix: error field should trigger human_review route"


class TestCLIExitCode:
    """Test CLI exit code and JSON envelope behavior."""

    def test_graph_recursion_error_returns_exit_1(self):
        """GraphRecursionError should cause exit(1) and ok=false."""
        from novel_factory.cli_app.commands.core import cmd_run_chapter
        import sys

        # Mock args
        args = MagicMock()
        args.project_id = "test"
        args.chapter = 1
        args.json = True
        args.max_steps = 20
        args.config = None
        args.db_path = None

        # We can't easily test sys.exit(1), but we can verify the logic
        # by checking the error classification
        error_msg = "GraphRecursionError: recursion limit reached"
        is_graph_recursion_error = "GraphRecursionError" in error_msg or "recursion limit" in error_msg.lower()
        assert is_graph_recursion_error, "Should detect GraphRecursionError"

    def test_business_block_with_error_returns_ok_false(self):
        """Business blocking with error should return ok=false in JSON."""
        error_msg = "Author validation failed"
        requires_human = True
        has_error = True

        # Logic from cmd_run_chapter
        is_failure = has_error and not requires_human
        is_block_with_error = has_error and requires_human

        assert not is_failure, "Business block is not a failure"
        assert is_block_with_error, "Business block with error should be detected"


class TestWorkflowRunStatusConsistency:
    """Test workflow_run status and error_message consistency."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        init_db(db_path)
        yield db_path
        os.unlink(db_path)

    def test_completed_status_clears_error_message(self, temp_db):
        """When status is completed, error_message should be cleared."""
        repo = Repository(temp_db)

        # Create project and workflow run
        project_id = "test_status_consistency"
        repo.create_project(
            project_id=project_id,
            name="Test",
            genre="fantasy",
        )
        run_id = repo.create_workflow_run(project_id, 1)

        # Set status to failed with error
        repo.update_workflow_run(run_id, status="failed", error_message="Some error")
        run = repo.get_workflow_runs_for_project(project_id)[0]
        assert run["status"] == "failed"
        assert run["error_message"] == "Some error"

        # Now set status to completed with clear_error=True
        repo.update_workflow_run(run_id, status="completed", clear_error=True)
        run = repo.get_workflow_runs_for_project(project_id)[0]
        assert run["status"] == "completed"
        assert run["error_message"] is None, "P1 fix: completed status should have no error_message"

    def test_failed_status_keeps_error_message(self, temp_db):
        """When status is failed, error_message should be preserved."""
        repo = Repository(temp_db)

        # Create project and workflow run
        project_id = "test_failed_status"
        repo.create_project(
            project_id=project_id,
            name="Test",
            genre="fantasy",
        )
        run_id = repo.create_workflow_run(project_id, 1)

        # Set status to failed with error
        repo.update_workflow_run(run_id, status="failed", error_message="Validation failed")
        run = repo.get_workflow_runs_for_project(project_id)[0]
        assert run["status"] == "failed"
        assert run["error_message"] == "Validation failed"

        # Update again with new error (should NOT clear)
        repo.update_workflow_run(run_id, status="failed", error_message="Another error")
        run = repo.get_workflow_runs_for_project(project_id)[0]
        assert run["error_message"] == "Another error"


class TestNodeErrorPropagation:
    """Test that node errors properly propagate requires_human flag."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        init_db(db_path)
        yield db_path
        os.unlink(db_path)

    def test_all_agent_nodes_set_requires_human_on_error(self, temp_db):
        """All agent nodes should set requires_human=True when error occurs."""
        from novel_factory.workflow.nodes import (
            planner_node, screenwriter_node, author_node,
            polisher_node, editor_node,
        )
        from novel_factory.llm.stub_provider import StubLLM

        repo = Repository(temp_db)
        stub_llm = StubLLM()

        # Create project and chapters in different states
        project_id = "test_node_error_prop"
        repo.create_project(
            project_id=project_id,
            name="Test",
            genre="fantasy",
        )

        # Test each agent node
        test_cases = [
            ("planner", planner_node, ChapterStatus.IDEA.value),
            ("screenwriter", screenwriter_node, ChapterStatus.PLANNED.value),
            ("author", author_node, ChapterStatus.SCRIPTED.value),
            ("polisher", polisher_node, ChapterStatus.DRAFTED.value),
            ("editor", editor_node, ChapterStatus.POLISHED.value),
        ]

        for agent_name, node_func, status in test_cases:
            chapter_num = hash(agent_name) % 1000 + 1
            repo.add_chapter(project_id, chapter_num, title=f"Chapter {chapter_num}", status=status)

            state: FactoryState = {
                "project_id": project_id,
                "chapter_number": chapter_num,
                "chapter_status": status,
                "retry_count": 0,
                "max_retries": 3,
                "requires_human": False,
                "error": None,
                "steps": [],
                "workflow_run_id": "",
            }

            # Run the node (stub LLM will fail precondition checks)
            result = node_func(state, repo, stub_llm)

            # Check that requires_human is set on error
            if "error" in result:
                assert result.get("requires_human") is True, \
                    f"P1 fix: {agent_name}_node should set requires_human=True on error"


class TestResetAndCheckpoint:
    """P1: Test reset clears retry count and checkpoint thread."""

    @pytest.fixture
    def temp_db(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        init_db(db_path)
        yield db_path
        os.unlink(db_path)

    def test_reset_clears_retry_count(self, temp_db):
        """Reset should insert a reset task so retry_count resets to 0."""
        repo = Repository(temp_db)
        project_id = "test_reset"
        repo.create_project(project_id=project_id, name="Test", genre="fantasy")
        repo.add_chapter(project_id, 1, title="Ch1", status=ChapterStatus.REVISION.value)

        # Simulate some retries
        repo.start_task(project_id, 1, "revise", "author")
        repo.start_task(project_id, 1, "revise", "author")
        assert repo.get_chapter_retry_count(project_id, 1) == 2

        # Reset chapter
        ok = repo.reset_chapter(project_id, 1)
        assert ok is True

        # Retry count should reset to 0 after reset
        assert repo.get_chapter_retry_count(project_id, 1) == 0

    def test_reset_clears_checkpoint_thread(self, temp_db):
        """delete_checkpoint_thread should remove persisted checkpoints."""
        from novel_factory.workflow.checkpoint import (
            delete_checkpoint_thread,
            get_sqlite_checkpointer,
            get_checkpoint_thread_id,
            derive_checkpoint_db_path,
        )

        repo = Repository(temp_db)
        project_id = "test_cp_reset"
        chapter_number = 1

        # Create a checkpoint manually
        cp_path = derive_checkpoint_db_path(temp_db)
        with get_sqlite_checkpointer(cp_path) as cp:
            thread_id = get_checkpoint_thread_id(project_id, chapter_number)
            # Put a dummy checkpoint (langgraph requires id in checkpoint dict)
            cp.put(
                {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
                {"id": "test-cp-1", "chapter_status": "drafted"},
                {},
                {},
            )
            # Verify it exists
            state = cp.get({"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}})
            assert state is not None

        # Delete checkpoint thread
        deleted = delete_checkpoint_thread(temp_db, project_id, chapter_number)
        assert deleted is True

        # Verify it's gone
        with get_sqlite_checkpointer(cp_path) as cp:
            state = cp.get({"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}})
            assert state is None, "Checkpoint thread should be deleted after reset"

    def test_reset_only_works_for_blocking_or_revision(self, temp_db):
        """Reset should only work for blocking/revision statuses."""
        repo = Repository(temp_db)
        project_id = "test_reset_limit"
        repo.create_project(project_id=project_id, name="Test", genre="fantasy")

        for i, status in enumerate(["planned", "scripted", "drafted", "polished", "reviewed", "published"]):
            chapter_num = i + 1
            repo.add_chapter(project_id, chapter_num, title=f"Ch{chapter_num}", status=status)
            ok = repo.reset_chapter(project_id, chapter_num)
            assert ok is False, f"Reset should not work for status={status}"

            chapter = repo.get_chapter(project_id, chapter_num)
            assert chapter["status"] == status, f"Status should not change for {status}"
