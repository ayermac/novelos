"""Tests for workflow/conditions.py — routing logic."""

import pytest
from unittest.mock import patch
from datetime import datetime, timedelta

from novel_factory.models.state import ChapterStatus
from novel_factory.workflow.conditions import (
    hydrate_revision_state,
    normalize_revision_target,
    prepare_resume_after_human_review,
    route_by_chapter_status,
    route_by_quality_gate,
    route_by_review_result,
    route_after_memory_curator,
    route_by_revision_type,
    route_after_agent,
)
from novel_factory.workflow.runner import (
    _block_incomplete_graph_exit,
    _clear_stale_checkpoint_for_new_run,
    _graph_exit_is_success,
)


class TestRouteByChapterStatus:
    @pytest.mark.parametrize(
        "status,expected",
        [
            ("planned", "screenwriter"),
            ("scripted", "author"),
            ("drafted", "polisher"),
            ("polished", "editor"),
            ("review", "editor"),
            ("reviewed", "publisher"),
            ("blocking", "human_review"),
            ("idea", "planner"),
            ("outlined", "planner"),
        ],
    )
    def test_happy_path_routing(self, status, expected):
        # v5.3.0: planned status requires has_instruction=True to route to screenwriter
        if status == "planned":
            state = {"chapter_status": status, "has_instruction": True}
        else:
            state = {"chapter_status": status}
        assert route_by_chapter_status(state) == expected

    def test_planned_without_instruction_routes_to_planner(self):
        """v5.3.0: planned status without instruction should route to planner."""
        state = {"chapter_status": "planned", "has_instruction": False}
        assert route_by_chapter_status(state) == "planner"

    def test_revision_routes_to_author_by_default(self):
        state = {
            "chapter_status": "revision",
            "quality_gate": {"revision_target": "author"},
        }
        assert route_by_chapter_status(state) == "author"

    def test_revision_without_quality_gate_routes_to_author(self):
        state = {"chapter_status": "revision"}
        assert route_by_chapter_status(state) == "author"

    def test_revision_with_invalid_target_routes_to_author(self):
        state = {
            "chapter_status": "revision",
            "quality_gate": {"revision_target": "editor"},
        }
        assert route_by_chapter_status(state) == "author"

    def test_revision_routes_to_polisher(self):
        state = {
            "chapter_status": "revision",
            "quality_gate": {"revision_target": "polisher"},
        }
        assert route_by_chapter_status(state) == "polisher"

    def test_revision_routes_to_planner(self):
        state = {
            "chapter_status": "revision",
            "quality_gate": {"revision_target": "planner"},
        }
        assert route_by_chapter_status(state) == "planner"

    # P1: Safety gate tests — error/requires_human always routes to human_review
    @pytest.mark.parametrize("status", ["planned", "scripted", "drafted", "polished", "reviewed", "revision"])
    def test_requires_human_routes_to_human_review(self, status):
        state = {"chapter_status": status, "requires_human": True}
        assert route_by_chapter_status(state) == "human_review"

    @pytest.mark.parametrize("status", ["planned", "scripted", "drafted", "polished", "reviewed", "revision"])
    def test_error_routes_to_human_review(self, status):
        state = {"chapter_status": status, "error": "some failure"}
        assert route_by_chapter_status(state) == "human_review"

    # P1: Stale checkpoint recovery — DB status overrides stale state
    def test_drafted_with_stale_revision_gate_routes_to_polisher(self):
        """If checkpoint says revision but DB says drafted, must go to polisher."""
        state = {
            "chapter_status": "drafted",
            "quality_gate": {"revision_target": "author"},  # stale gate from old run
        }
        assert route_by_chapter_status(state) == "polisher"

    def test_polished_with_stale_revision_gate_routes_to_editor(self):
        """If checkpoint says revision but DB says polished, must go to editor."""
        state = {
            "chapter_status": "polished",
            "quality_gate": {"revision_target": "planner"},  # stale gate from old run
        }
        assert route_by_chapter_status(state) == "editor"


class TestFreshRunCheckpointCleanup:
    class FakeRepo:
        db_path = "test.db"

        def __init__(self, runs):
            self.runs = runs
            self.failed_runs = []

        def get_workflow_runs_for_project(self, project_id, chapter_number=None, limit=20):
            return self.runs

        def get_chapter(self, project_id, chapter_number):
            return {"status": "polished"}

        def update_workflow_run(self, run_id, status=None, error_message=None, **_kwargs):
            self.failed_runs.append({
                "run_id": run_id,
                "status": status,
                "error_message": error_message,
            })
            return True

    def test_clears_checkpoint_when_latest_run_failed(self):
        repo = self.FakeRepo([{"status": "failed"}])

        with patch("novel_factory.workflow.runner.delete_checkpoint_thread") as delete:
            _clear_stale_checkpoint_for_new_run(repo, "demo", 1)

        delete.assert_called_once_with("test.db", "demo", 1)

    def test_keeps_checkpoint_for_active_running_run(self):
        repo = self.FakeRepo([{"status": "running"}])

        with patch("novel_factory.workflow.runner.delete_checkpoint_thread") as delete:
            _clear_stale_checkpoint_for_new_run(repo, "demo", 1)

        delete.assert_not_called()

    def test_clears_checkpoint_for_stale_running_run(self):
        old_started_at = (datetime.utcnow() + timedelta(hours=8) - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
        repo = self.FakeRepo([{"id": "run-old", "status": "running", "started_at": old_started_at}])

        with patch("novel_factory.workflow.runner.delete_checkpoint_thread") as delete:
            _clear_stale_checkpoint_for_new_run(repo, "demo", 1)

        delete.assert_called_once_with("test.db", "demo", 1)
        assert repo.failed_runs[0]["run_id"] == "run-old"
        assert repo.failed_runs[0]["status"] == "failed"

    def test_clears_checkpoint_for_completed_non_terminal_run(self):
        repo = self.FakeRepo([
            {"id": "run-done", "status": "completed", "current_node": "editor"}
        ])

        with patch("novel_factory.workflow.checkpoint.inspect_checkpoint_thread") as inspect:
            inspect.return_value = {
                "checkpoint_exists": True,
                "checkpoint_node": "loop",
            }
            with patch("novel_factory.workflow.runner.delete_checkpoint_thread") as delete:
                _clear_stale_checkpoint_for_new_run(repo, "demo", 1)

        delete.assert_called_once_with("test.db", "demo", 1)

    def test_clears_checkpoint_when_inspection_reports_corruption(self):
        repo = self.FakeRepo([
            {"id": "run-done", "status": "blocked", "current_node": "human_review"}
        ])

        with patch("novel_factory.workflow.checkpoint.inspect_checkpoint_thread") as inspect:
            inspect.return_value = {
                "checkpoint_exists": True,
                "checkpoint_corrupt": True,
                "checkpoint_error": "Error -3 while decompressing data: incorrect header check",
            }
            with patch("novel_factory.workflow.runner.delete_checkpoint_thread") as delete:
                _clear_stale_checkpoint_for_new_run(repo, "demo", 1)

        delete.assert_called_once_with("test.db", "demo", 1)


class TestGraphExitGuard:
    class FakeRepo:
        def __init__(self):
            self.updates = []
            self.events = []

        def get_workflow_runs_for_project(self, project_id, chapter_number=None, limit=20):
            return [
                {
                    "id": "run-1",
                    "status": "running",
                    "current_node": "editor",
                }
            ]

        def update_workflow_run(self, run_id, **kwargs):
            self.updates.append({"run_id": run_id, **kwargs})
            return True

        def create_workflow_node_event(self, **kwargs):
            self.events.append(kwargs)
            return len(self.events)

    def test_graph_exit_requires_terminal_status(self):
        assert _graph_exit_is_success({"chapter_status": "published"}) is True
        assert _graph_exit_is_success({"chapter_status": "awaiting_publish"}) is True
        assert _graph_exit_is_success({
            "chapter_status": "reviewed",
            "awaiting_publish": True,
            "requires_human": True,
        }) is True
        assert _graph_exit_is_success({"chapter_status": "polished"}) is False
        assert _graph_exit_is_success({"chapter_status": "reviewed"}) is False

    def test_incomplete_graph_exit_marks_run_blocked_at_current_node(self):
        repo = self.FakeRepo()
        state = {
            "workflow_run_id": "run-1",
            "project_id": "demo",
            "chapter_number": 1,
            "chapter_status": "polished",
            "total_tokens": 123,
        }

        message = _block_incomplete_graph_exit(repo, state, current_node="polisher")

        assert "WORKFLOW_INTERRUPTED_BEFORE_TERMINAL" in message
        assert repo.updates == [
            {
                "run_id": "run-1",
                "status": "blocked",
                "current_node": "editor",
                "error_message": message,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 123,
                "duration_ms": 0,
            }
        ]
        assert repo.events[0]["event_type"] == "workflow_interrupted"
        assert repo.events[0]["node_name"] == "editor"


class TestAgentNodeStaleDbGuard:
    def test_agent_runner_stops_before_llm_when_db_is_blocking(self, tmp_path):
        """A stale in-memory status must not let downstream agents execute."""
        from novel_factory.config.settings import load_settings
        from novel_factory.db.connection import init_db
        from novel_factory.db.repository import Repository
        from novel_factory.workflow.nodes import create_node_runners

        class FailIfCalledRouter:
            def for_agent(self, agent_name):
                raise AssertionError(f"LLM router should not be called for {agent_name}")

        db_path = tmp_path / "stale-blocking-guard.db"
        init_db(db_path)
        repo = Repository(str(db_path))
        repo.create_project(project_id="stale_guard", name="Stale Guard", genre="fantasy")
        repo.save_chapter("stale_guard", 1, title="第一章", content="正文", word_count=2, status="blocking")
        run_id = repo.create_workflow_run("stale_guard", 1)
        repo.update_workflow_run(run_id, status="running", current_node="author")

        runners = create_node_runners(load_settings(), repo, FailIfCalledRouter())
        result = runners["polisher"]({
            "project_id": "stale_guard",
            "chapter_number": 1,
            "workflow_run_id": run_id,
            "chapter_status": ChapterStatus.DRAFTED.value,
            "requires_human": False,
            "error": None,
            "steps": [],
        })

        assert result["chapter_status"] == ChapterStatus.BLOCKING.value
        assert result["requires_human"] is True
        assert "已处于阻塞状态" in result["error"]
        assert repo.get_workflow_node_events(run_id, node_name="polisher") == []
        run = repo.get_workflow_runs_for_project("stale_guard", chapter_number=1, limit=1)[0]
        assert run["current_node"] == "author"


class TestRouteByReviewResult:
    def test_pass_goes_to_memory_curator_in_stub_mode(self):
        """v5.3.2: Stub mode routes to memory_curator after pass."""
        state = {"quality_gate": {"pass": True}, "retry_count": 0, "max_retries": 3, "llm_mode": "stub"}
        assert route_by_review_result(state) == "memory_curator"

    def test_pass_goes_to_memory_curator_in_real_mode(self):
        """v5.3.2: Real mode routes to memory_curator after pass."""
        state = {"quality_gate": {"pass": True}, "retry_count": 0, "max_retries": 3, "llm_mode": "real"}
        assert route_by_review_result(state) == "memory_curator"

    def test_pass_without_llm_mode_defaults_to_memory_curator(self):
        """v5.3.2: No llm_mode defaults to memory_curator after pass."""
        state = {"quality_gate": {"pass": True}, "retry_count": 0, "max_retries": 3}
        assert route_by_review_result(state) == "memory_curator"

    def test_fail_goes_to_revise(self):
        state = {"quality_gate": {"pass": False}, "retry_count": 1, "max_retries": 3}
        assert route_by_review_result(state) == "revise"

    def test_death_penalty_gate_after_agent_goes_to_revision(self):
        state = {
            "quality_gate": {
                "pass": False,
                "revision_target": "author",
                "death_penalty_fail": True,
            }
        }
        assert route_after_agent(state) == "revision_router"

    def test_version_regression_gate_after_agent_goes_to_revision(self):
        state = {
            "chapter_status": "revision",
            "quality_gate": {
                "pass": False,
                "revision_target": "author",
                "version_regression": True,
            },
        }
        assert route_after_agent(state) == "revision_router"

    def test_polisher_expansion_drift_after_agent_goes_to_revision(self):
        state = {
            "chapter_status": "revision",
            "quality_gate": {
                "pass": False,
                "revision_target": "polisher",
                "expansion_drift_fail": True,
            },
        }
        assert route_after_agent(state) == "revision_router"

    def test_polisher_low_change_routes_to_revision_router(self):
        """v6.10.5: Polisher low_change_fail must route to revision_router, not human_review."""
        state = {
            "chapter_status": "revision",
            "quality_gate": {
                "pass": False,
                "revision_target": "polisher",
                "low_change_fail": True,
            },
        }
        assert route_after_agent(state) == "revision_router"

    def test_polisher_fact_lock_routes_to_revision_router(self):
        """v6.10.5: Polisher fact_lock_fail must route to revision_router, not human_review."""
        state = {
            "chapter_status": "revision",
            "quality_gate": {
                "pass": False,
                "revision_target": "polisher",
                "fact_lock_fail": True,
            },
        }
        assert route_after_agent(state) == "revision_router"

    def test_retryable_gate_takes_priority_over_error(self):
        """v6.10.5: Retryable quality_gate must route to revision_router even when
        the agent also sets an error field (polisher internal retries)."""
        state = {
            "chapter_status": "revision",
            "error": "返修润色无效：修改幅度低于阈值",
            "quality_gate": {
                "pass": False,
                "revision_target": "polisher",
                "low_change_fail": True,
            },
        }
        assert route_after_agent(state) == "revision_router"

    def test_stale_quality_gate_ignored_when_status_advanced(self):
        """A stale quality_gate from a previous failed attempt must not cause
        route_after_agent to send a successful agent run back to revision_router.
        """
        for status in ("drafted", "polished", "reviewed"):
            state = {
                "chapter_status": status,
                "quality_gate": {
                    "pass": False,
                    "word_count_fail": True,
                    "revision_target": "author",
                },
            }
            assert route_after_agent(state) == "next", f"stale gate should be ignored for status={status}"

    def test_max_retries_goes_to_human(self):
        state = {"quality_gate": {"pass": False}, "retry_count": 3, "max_retries": 3}
        assert route_by_review_result(state) == "human_review"


class TestRouteByQualityGate:
    """v6.10.5: Quality gate node routing tests."""

    def test_fail_routes_to_revision_router(self):
        state = {"quality_gate": {"passed": False}, "retry_count": 1, "max_retries": 3}
        assert route_by_quality_gate(state) == "revision_router"

    def test_pass_routes_to_editor(self):
        state = {"quality_gate": {"passed": True}, "retry_count": 0, "max_retries": 3}
        assert route_by_quality_gate(state) == "editor"

    def test_max_retries_routes_to_human_review(self):
        """v6.10.5: Even retryable gates must go to human_review when max retries reached."""
        state = {
            "quality_gate": {"passed": False, "word_count_fail": True},
            "retry_count": 3,
            "max_retries": 3,
        }
        assert route_by_quality_gate(state) == "human_review"

    def test_error_takes_priority(self):
        state = {
            "quality_gate": {"passed": True},
            "error": "some error",
            "requires_human": False,
        }
        assert route_by_quality_gate(state) == "human_review"

    def test_requires_human_takes_priority(self):
        state = {
            "quality_gate": {"passed": True},
            "requires_human": True,
        }
        assert route_by_quality_gate(state) == "human_review"


class TestRouteByRevisionType:
    @pytest.mark.parametrize(
        "target,expected",
        [
            ("author", "author"),
            ("polisher", "polisher"),
            ("planner", "planner"),
        ],
    )
    def test_revision_target_routing(self, target, expected):
        state = {"quality_gate": {"revision_target": target}}
        assert route_by_revision_type(state) == expected

    def test_default_routes_to_author(self):
        state = {"quality_gate": {}}
        assert route_by_revision_type(state) == "author"

    def test_invalid_revision_target_routes_to_author(self):
        state = {"chapter_status": ChapterStatus.REVISION.value, "quality_gate": {"revision_target": "editor"}}
        assert route_by_revision_type(state) == "author"

    def test_missing_quality_gate_routes_to_author(self):
        state = {"chapter_status": ChapterStatus.REVISION.value}
        assert route_by_revision_type(state) == "author"

    # P1: Full stale-revision-gate matrix — when DB status != REVISION, ignore gate
    @pytest.mark.parametrize(
        "db_status,expected",
        [
            (ChapterStatus.IDEA.value, "planner"),
            (ChapterStatus.OUTLINED.value, "planner"),
            (ChapterStatus.PLANNED.value, "planner"),
            (ChapterStatus.SCRIPTED.value, "author"),
            (ChapterStatus.DRAFTED.value, "polisher"),
            (ChapterStatus.POLISHED.value, "editor"),
            (ChapterStatus.REVIEW.value, "editor"),
            (ChapterStatus.REVIEWED.value, "publisher"),
            (ChapterStatus.PUBLISHED.value, "archive"),
            (ChapterStatus.BLOCKING.value, "human_review"),
        ],
    )
    def test_stale_revision_gate_routes_by_db_status(self, db_status, expected):
        """Stale revision gate must never override actual DB status."""
        state = {
            "chapter_status": db_status,
            "quality_gate": {"revision_target": "author"},  # stale gate
        }
        assert route_by_revision_type(state) == expected

    def test_stale_revision_gate_respects_drafted_status(self):
        state = {
            "chapter_status": ChapterStatus.DRAFTED.value,
            "quality_gate": {"revision_target": "author"},
        }
        assert route_by_revision_type(state) == "polisher"

    def test_stale_revision_gate_respects_polished_status(self):
        state = {
            "chapter_status": ChapterStatus.POLISHED.value,
            "quality_gate": {"revision_target": "planner"},
        }
        assert route_by_revision_type(state) == "editor"


class TestRevisionStateHydration:
    class FakeRepo:
        def __init__(self, review=None, retry_count=0):
            self.review = review
            self.retry_count = retry_count

        def get_chapter(self, project_id, chapter_number):
            return {"id": 42, "project_id": project_id, "chapter_number": chapter_number}

        def get_latest_review(self, project_id, chapter_id):
            return self.review

        def get_chapter_retry_count(self, project_id, chapter_number):
            return self.retry_count

    def test_normalize_revision_target_only_allows_routable_agents(self):
        assert normalize_revision_target("author") == "author"
        assert normalize_revision_target("polisher") == "polisher"
        assert normalize_revision_target("planner") == "planner"
        assert normalize_revision_target("editor") == "author"
        assert normalize_revision_target(None) == "author"

    def test_hydrate_revision_state_uses_latest_review_target(self):
        repo = self.FakeRepo({
            "id": 7,
            "score": 69,
            "revision_target": "polisher",
            "issues": '["AI痕迹过重"]',
            "suggestions": '["压缩解释性句子"]',
        })
        state = {
            "project_id": "demo",
            "chapter_number": 2,
            "chapter_status": ChapterStatus.REVISION.value,
        }

        hydrated = hydrate_revision_state(state, repo)

        assert hydrated["quality_gate"] == {"pass": False, "revision_target": "polisher"}
        assert hydrated["_revision_review"]["review_id"] == 7
        assert hydrated["_revision_review"]["revision_target"] == "polisher"

    def test_hydrate_revision_state_invalid_review_target_defaults_to_author(self):
        repo = self.FakeRepo({"id": 8, "score": 67, "revision_target": "editor"})
        state = {
            "project_id": "demo",
            "chapter_number": 2,
            "chapter_status": ChapterStatus.REVISION.value,
        }

        hydrated = hydrate_revision_state(state, repo)

        assert hydrated["quality_gate"]["revision_target"] == "author"
        assert hydrated["_revision_review"]["revision_target"] == "author"

    def test_hydrate_revision_state_keeps_existing_quality_gate(self):
        repo = self.FakeRepo({"id": 9, "revision_target": "planner"})
        state = {
            "project_id": "demo",
            "chapter_number": 2,
            "chapter_status": ChapterStatus.REVISION.value,
            "quality_gate": {"pass": False, "revision_target": "polisher"},
        }

        hydrated = hydrate_revision_state(state, repo)

        assert hydrated["quality_gate"]["revision_target"] == "polisher"
        assert hydrated["_revision_review"]["review_id"] == 9
        assert hydrated["_revision_review"]["revision_target"] == "planner"

    def test_hydrate_revision_state_preserves_existing_revision_review(self):
        repo = self.FakeRepo({"id": 10, "revision_target": "planner"})
        state = {
            "project_id": "demo",
            "chapter_number": 2,
            "chapter_status": ChapterStatus.REVISION.value,
            "quality_gate": {"pass": False, "revision_target": "polisher"},
            "_revision_review": {"review_id": 5, "revision_target": "polisher"},
        }

        hydrated = hydrate_revision_state(state, repo)

        assert hydrated["quality_gate"]["revision_target"] == "polisher"
        assert hydrated["_revision_review"]["review_id"] == 5
        assert hydrated["_revision_review"]["revision_target"] == "polisher"

    def test_hydrate_revision_state_fills_missing_gate_target(self):
        repo = self.FakeRepo({"id": 11, "revision_target": "author"})
        state = {
            "project_id": "demo",
            "chapter_number": 2,
            "chapter_status": ChapterStatus.REVISION.value,
            "quality_gate": {"pass": False},
        }

        hydrated = hydrate_revision_state(state, repo)

        assert hydrated["quality_gate"]["revision_target"] == "author"
        assert hydrated["_revision_review"]["review_id"] == 11

    def test_hydrate_revision_state_overwrites_stale_retry_count_from_db(self):
        repo = self.FakeRepo({"id": 12, "revision_target": "author"}, retry_count=2)
        state = {
            "project_id": "demo",
            "chapter_number": 2,
            "chapter_status": ChapterStatus.REVISION.value,
            "retry_count": 1,
        }

        hydrated = hydrate_revision_state(state, repo)

        assert hydrated["retry_count"] == 2

    def test_prepare_resume_after_human_review_clears_checkpoint_and_flags(self):
        repo = self.FakeRepo()
        repo.db_path = "resume.db"
        state = {
            "project_id": "demo",
            "chapter_number": 2,
            "requires_human": True,
            "error": "blocked",
        }

        with patch("novel_factory.workflow.checkpoint.delete_checkpoint_thread") as delete:
            result = prepare_resume_after_human_review(state, repo)

        delete.assert_called_once_with("resume.db", "demo", 2)
        assert result == {
            "requires_human": False,
            "error": None,
            "current_stage": "resumed",
        }


class TestRouteAfterMemoryCurator:
    """v5.3.2 closure: memory_curator failure routing."""

    def test_stub_mode_no_error_goes_to_publish(self):
        state = {"llm_mode": "stub"}
        assert route_after_memory_curator(state) == "publish"

    def test_real_mode_no_error_goes_to_awaiting_publish(self):
        state = {"llm_mode": "real"}
        assert route_after_memory_curator(state) == "awaiting_publish"

    def test_real_mode_degraded_memory_routes_to_awaiting_publish(self):
        state = {
            "llm_mode": "real",
            "memory_curator_degraded": True,
            "memory_curator_warning": "LLM 未提取出记忆候选",
        }
        assert route_after_memory_curator(state) == "awaiting_publish"

    def test_real_mode_fallback_memory_routes_to_awaiting_publish(self):
        state = {
            "llm_mode": "real",
            "extraction_success": False,
            "fallback_created": True,
        }
        assert route_after_memory_curator(state) == "awaiting_publish"

    def test_no_llm_mode_defaults_to_publish(self):
        state = {}
        assert route_after_memory_curator(state) == "publish"

    def test_requires_human_routes_to_human_review(self):
        """Real mode memory_curator failure blocks publish."""
        state = {"llm_mode": "real", "requires_human": True}
        assert route_after_memory_curator(state) == "human_review"

    def test_error_routes_to_human_review(self):
        """Error in state blocks publish regardless of mode."""
        state = {"llm_mode": "real", "error": "extraction failed"}
        assert route_after_memory_curator(state) == "human_review"

    def test_requires_human_in_stub_also_blocks(self):
        """Even in stub mode, requires_human=True routes to human_review."""
        state = {"llm_mode": "stub", "requires_human": True}
        assert route_after_memory_curator(state) == "human_review"


class TestWorkflowNodeRevisionHardening:
    class FakeGateRepo:
        db_path = "gate.db"

        def __init__(self):
            self.updated_status = None
            self.started_tasks = []
            self.completed_tasks = []

        def get_chapter_retry_count(self, project_id, chapter_number):
            return 0

        def get_chapter_status(self, project_id, chapter_number):
            return ChapterStatus.DRAFTED.value

        def update_chapter_status(self, project_id, chapter_number, status):
            self.updated_status = (project_id, chapter_number, status)
            return True

        def start_task(self, project_id, chapter_number, task_type, agent_id, workflow_run_id=None):
            self.started_tasks.append({
                "project_id": project_id,
                "chapter_number": chapter_number,
                "task_type": task_type,
                "agent_id": agent_id,
                "workflow_run_id": workflow_run_id,
            })
            return 101

        def complete_task(self, task_id, success=True):
            self.completed_tasks.append((task_id, success))
            return True

    def test_retryable_quality_gate_uses_current_result_revision_target(self):
        from novel_factory.workflow.nodes import _handle_retryable_quality_gate

        repo = self.FakeGateRepo()
        state = {
            "project_id": "demo",
            "chapter_number": 2,
            "workflow_run_id": "run-1",
            "max_retries": 3,
            "quality_gate": {"revision_target": "author"},
        }
        result = {
            "error": "word count failed",
            "quality_gate": {
                "pass": False,
                "word_count_fail": True,
                "revision_target": "polisher",
            },
        }

        updated = _handle_retryable_quality_gate(state, repo, result)

        assert updated["chapter_status"] == ChapterStatus.REVISION.value
        assert updated["retry_count"] == 1
        assert updated["requires_human"] is False
        assert updated["retryable_quality_gate"] is True
        assert updated["_exec_events"][0]["event_type"] == "quality_gate_retry"
        assert "error" not in updated
        assert repo.started_tasks[0]["agent_id"] == "polisher"

    def test_scene_beat_coverage_gate_is_retryable_to_author(self):
        from novel_factory.workflow.nodes import _handle_retryable_quality_gate

        repo = self.FakeGateRepo()
        state = {
            "project_id": "demo",
            "chapter_number": 2,
            "workflow_run_id": "run-1",
            "max_retries": 3,
        }
        result = {
            "error": "scene beat coverage failed",
            "quality_gate": {
                "pass": False,
                "scene_beat_coverage_fail": True,
                "revision_target": "author",
            },
        }

        updated = _handle_retryable_quality_gate(state, repo, result)

        assert updated["chapter_status"] == ChapterStatus.REVISION.value
        assert updated["retry_count"] == 1
        assert updated["requires_human"] is False
        assert updated["retryable_quality_gate"] is True
        assert "error" not in updated
        assert repo.started_tasks[0]["agent_id"] == "author"

    def test_version_regression_gate_is_retryable_to_author(self):
        from novel_factory.workflow.nodes import _handle_retryable_quality_gate

        repo = self.FakeGateRepo()
        state = {
            "project_id": "demo",
            "chapter_number": 2,
            "workflow_run_id": "run-1",
            "max_retries": 3,
        }
        result = {
            "error": "revision regressed",
            "quality_gate": {
                "pass": False,
                "version_regression": True,
                "revision_target": "author",
                "message": "新稿比当前短 41.7%，且 Editor 未要求压缩",
            },
        }

        updated = _handle_retryable_quality_gate(state, repo, result)

        assert updated["chapter_status"] == ChapterStatus.REVISION.value
        assert updated["retry_count"] == 1
        assert updated["requires_human"] is False
        assert updated["retryable_quality_gate"] is True
        assert "error" not in updated
        assert repo.started_tasks[0]["agent_id"] == "author"

    def test_retryable_quality_gate_logs_retrying_node_event_not_completed(
        self, tmp_path, monkeypatch
    ):
        from novel_factory.db.connection import init_db
        from novel_factory.db.repository import Repository
        from novel_factory.llm.provider import LLMProvider
        import novel_factory.workflow.nodes as nodes

        class DummyLLM(LLMProvider):
            def invoke_json(self, messages, schema=None, temperature=None, max_tokens=None):
                return {}

            def invoke_text(
                self,
                messages,
                temperature=None,
                max_tokens=None,
                max_retries=None,
                request_timeout_seconds=None,
            ):
                return ""

        class RetryableGateAuthor:
            def __init__(self, *args, **kwargs):
                pass

            def run(self, state):
                return {
                    "error": "字数质量门未通过",
                    "chapter_status": ChapterStatus.SCRIPTED.value,
                    "quality_gate": {
                        "pass": False,
                        "word_count_fail": True,
                        "revision_target": "author",
                        "message": "字数超标: 6355 > 4050 (目标 3000，上限缓冲 500)",
                    },
                }

        db_path = tmp_path / "retrying-node-event.db"
        init_db(db_path)
        repo = Repository(str(db_path))
        repo.create_project(project_id="demo", name="Demo", genre="fantasy")
        repo.add_chapter("demo", 2, title="第2章", status=ChapterStatus.SCRIPTED.value)
        run_id = repo.create_workflow_run("demo", 2)
        repo.update_workflow_run(run_id, status="running", current_node="author")

        monkeypatch.setattr(nodes, "AuthorAgent", RetryableGateAuthor)

        result = nodes.author_node(
            {
                "project_id": "demo",
                "chapter_number": 2,
                "workflow_run_id": run_id,
                "chapter_status": ChapterStatus.SCRIPTED.value,
                "max_retries": 3,
            },
            repo,
            DummyLLM(),
        )

        events = repo.get_workflow_node_events(run_id, node_name="author")
        event_types = [event["event_type"] for event in events]
        messages = [event["message"] for event in events]

        assert result["retryable_quality_gate"] is True
        assert event_types == ["started", "retrying"]
        assert events[-1]["status"] == "warning"
        assert "字数超标" in events[-1]["message"]
        assert "已生成章节初稿" not in messages

    def test_revision_router_node_returns_hydrated_updates_for_langgraph_merge(self):
        from novel_factory.workflow.nodes import revision_router_node

        class Repo:
            db_path = "revision.db"

            def update_workflow_run(self, *args, **kwargs):
                return True

            def log_workflow_node_event(self, *args, **kwargs):
                return 1

            def get_chapter(self, project_id, chapter_number):
                return {"id": 42}

            def get_latest_review(self, project_id, chapter_id):
                return {
                    "id": 7,
                    "score": 72,
                    "revision_target": "planner",
                    "issues": '["规划冲突"]',
                    "suggestions": '["重做章节目标"]',
                }

        state = {
            "workflow_run_id": "run-2",
            "project_id": "demo",
            "chapter_number": 2,
            "chapter_status": ChapterStatus.REVISION.value,
        }

        updates = revision_router_node(state, Repo())

        assert updates["quality_gate"] == {"pass": False, "revision_target": "planner"}
        assert updates["_revision_review"]["review_id"] == 7
        assert updates["_revision_review"]["revision_target"] == "planner"

    def test_revision_router_converts_quality_gate_failure_to_author_revision(self):
        from novel_factory.workflow.conditions import route_by_revision_type
        from novel_factory.workflow.nodes import revision_router_node

        class Repo:
            db_path = "quality-gate-revision.db"

            def __init__(self):
                self.status = ChapterStatus.POLISHED.value
                self.tasks = []

            def update_workflow_run(self, *args, **kwargs):
                return True

            def log_workflow_node_event(self, *args, **kwargs):
                return 1

            def get_chapter_retry_count(self, project_id, chapter_number):
                return len(self.tasks)

            def get_chapter_status(self, project_id, chapter_number):
                return self.status

            def update_chapter_status(self, project_id, chapter_number, status):
                self.status = status

            def start_task(self, project_id, chapter_number, task_type, agent_id, workflow_run_id=None):
                self.tasks.append((task_type, agent_id, workflow_run_id))
                return len(self.tasks)

            def complete_task(self, task_id, success=True):
                return True

            def get_chapter(self, project_id, chapter_number):
                return {"id": 42}

            def get_latest_review(self, project_id, chapter_id):
                return None

        state = {
            "workflow_run_id": "run-qg",
            "project_id": "demo",
            "chapter_number": 3,
            "chapter_status": ChapterStatus.POLISHED.value,
            "max_retries": 3,
            "quality_gate": {
                "passed": False,
                "pass": False,
                "score": 70,
                "revision_target": "author",
                "blocking_issues": [
                    "章间衔接断裂：上一章结尾存在明确时间节点“今晚”，本章开头未承接。",
                    "[连续性阻断] 标题与正文脱节：标题关键词「帝豪血衣令」未在正文中出现。",
                ],
                "priority_issues": [],
                "advisory_issues": ["对白口语化标记不足"],
                "checks_run": ["chapter_seam", "continuity_gate"],
                "timestamp": "2026-06-08T09:35:29+00:00",
            },
        }

        repo = Repo()
        updates = revision_router_node(state, repo)
        routed_state = {**state, **updates}

        assert updates["chapter_status"] == ChapterStatus.REVISION.value
        assert updates["retry_count"] == 1
        assert repo.status == ChapterStatus.REVISION.value
        assert repo.tasks == [("revise", "author", "run-qg")]
        assert updates["_revision_review"]["source"] == "quality_gate"
        assert "章间衔接断裂" in updates["_revision_review"]["issues"][0]
        assert any("QualityGate 阻断项" in s for s in updates["_revision_review"]["suggestions"])
        assert route_by_revision_type(routed_state) == "author"
