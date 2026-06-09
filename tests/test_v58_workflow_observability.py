"""v5.8 Workflow Observability and Recovery tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository


def _make_client(tmp_path):
    db_path = str(tmp_path / "v58.db")
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    return TestClient(app), Repository(db_path)


def _seed_project_and_chapter(repo: Repository, project_id: str, chapter_number: int = 1, status: str = "planned"):
    repo.create_project(project_id=project_id, name="Observability Project", genre="fantasy")
    repo.add_chapter(project_id, chapter_number, title=f"Ch{chapter_number}", status=status)


def _seed_run(repo: Repository, project_id: str, chapter_number: int = 1, status: str = "running", current_node: str = "author") -> str:
    run_id = repo.create_workflow_run(project_id, chapter_number)
    repo.update_workflow_run(run_id, status=status, current_node=current_node)
    return run_id


def _backdate_run(repo: Repository, run_id: str, minutes_old: int) -> None:
    started_at = (datetime.now() - timedelta(minutes=minutes_old)).strftime("%Y-%m-%d %H:%M:%S")
    conn = repo._conn()
    try:
        conn.execute("UPDATE workflow_runs SET started_at=? WHERE id=?", (started_at, run_id))
        conn.commit()
    finally:
        conn.close()


class TestWorkflowNodeEvents:
    """Tests for workflow_node_events persistence."""

    def test_health_check_records_started_and_completed_events_for_new_run(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_health")

        from novel_factory.workflow.nodes import health_check_node

        result = health_check_node(
            {
                "project_id": "obs_health",
                "chapter_number": 1,
                "workflow_run_id": "",
            },
            repo,
        )

        run_id = result["workflow_run_id"]
        events = repo.get_workflow_node_events(run_id, node_name="health_check")
        assert [event["event_type"] for event in events] == ["started", "completed"]
        assert [event["message"] for event in events] == ["开始工作流预检", "预检通过"]

    def test_node_events_created_during_run(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_run")
        run_id = _seed_run(repo, "obs_run", status="running", current_node="screenwriter")

        # Simulate node events written by nodes.py
        repo.create_workflow_node_event(
            run_id=run_id,
            project_id="obs_run",
            chapter_number=1,
            node_name="health_check",
            event_type="started",
            status="running",
            message="开始工作流预检",
        )
        repo.create_workflow_node_event(
            run_id=run_id,
            project_id="obs_run",
            chapter_number=1,
            node_name="screenwriter",
            event_type="started",
            status="running",
            message="开始编剧",
        )
        repo.create_workflow_node_event(
            run_id=run_id,
            project_id="obs_run",
            chapter_number=1,
            node_name="screenwriter",
            event_type="completed",
            status="completed",
            message="已生成章节场景规划",
        )

        events = repo.get_workflow_node_events(run_id)
        assert len(events) == 3
        assert events[0]["node_name"] == "health_check"
        assert events[0]["event_type"] == "started"
        assert events[1]["node_name"] == "screenwriter"
        assert events[2]["event_type"] == "completed"
        assert events[2]["message"] == "已生成章节场景规划"

    def test_node_event_failure_does_not_block_main_workflow(self, tmp_path):
        """Event logging failures are best-effort and do not raise."""
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_fail")
        run_id = _seed_run(repo, "obs_fail")

        # Directly calling with a closed connection or bad state would be hard to simulate,
        # so we verify the helper is best-effort by ensuring no exception propagates
        # when logging with a missing run_id (which returns early).
        from novel_factory.workflow.nodes import _log_node_event
        state = {"project_id": "obs_fail", "chapter_number": 1, "workflow_run_id": ""}
        # Should not raise even with empty run_id
        _log_node_event(state, repo, "author", "started", status="running")
        events = repo.get_workflow_node_events(run_id)
        # No events logged because run_id was empty
        assert len(events) == 0

    def test_node_events_stub_and_real_mode_compatible(self, tmp_path):
        """Event table exists and is usable regardless of llm_mode."""
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_mode")
        run_id = _seed_run(repo, "obs_mode")

        event_id = repo.create_workflow_node_event(
            run_id=run_id,
            project_id="obs_mode",
            chapter_number=1,
            node_name="author",
            event_type="started",
            status="running",
            message="开始执笔撰写",
        )
        assert event_id > 0
        event = repo.get_workflow_node_events(run_id)[0]
        assert event["message"] == "开始执笔撰写"


class TestWorkflowTimelineApi:
    """Tests for GET /api/projects/{id}/chapters/{n}/workflow-timeline."""

    def test_timeline_returns_empty_when_no_run(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_empty")

        resp = client.get("/api/projects/obs_empty/chapters/1/workflow-timeline")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["project_id"] == "obs_empty"
        assert data["chapter_number"] == 1
        assert data["run_id"] is None
        assert data["run_status"] is None
        node_names = [node["node_name"] for node in data["nodes"]]
        assert "health_check" in node_names
        assert "memory_curator" in node_names
        assert "awaiting_publish" in node_names
        assert "archive" in node_names
        assert all(node["status"] == "pending" for node in data["nodes"])
        assert data["checkpoint"]["checkpoint_exists"] is False
        assert data["checkpoint"]["recovery_available"] is False
        assert data["is_stale"] is False

    def test_timeline_returns_nodes_and_artifacts(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_timeline", status="scripted")
        run_id = _seed_run(repo, "obs_timeline", status="completed", current_node="author")

        # Seed node events
        repo.create_workflow_node_event(
            run_id=run_id, project_id="obs_timeline", chapter_number=1,
            node_name="screenwriter", event_type="started", status="running", message="开始编剧",
        )
        repo.create_workflow_node_event(
            run_id=run_id, project_id="obs_timeline", chapter_number=1,
            node_name="screenwriter", event_type="completed", status="completed", message="已生成章节场景规划",
        )
        repo.create_workflow_node_event(
            run_id=run_id, project_id="obs_timeline", chapter_number=1,
            node_name="author", event_type="started", status="running", message="开始执笔撰写",
        )
        repo.create_workflow_node_event(
            run_id=run_id, project_id="obs_timeline", chapter_number=1,
            node_name="author", event_type="completed", status="completed", message="已生成章节初稿",
        )

        # Seed artifact
        repo.save_artifact("obs_timeline", 1, "screenwriter", "scene_plan", workflow_run_id=run_id)

        resp = client.get("/api/projects/obs_timeline/chapters/1/workflow-timeline")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["run_id"] == run_id
        assert data["run_status"] == "completed"
        assert len(data["nodes"]) >= 13

        screenwriter_node = next(n for n in data["nodes"] if n["node_name"] == "screenwriter")
        assert screenwriter_node["label"] == "编剧"
        assert screenwriter_node["node_group"] == "creative_agent"
        assert screenwriter_node["status"] == "completed"
        assert "已生成章节场景规划" in screenwriter_node["messages"]
        assert len(screenwriter_node["artifacts"]) == 1
        assert screenwriter_node["artifacts"][0]["label"] == "章节场景规划"
        assert screenwriter_node["artifacts"][0]["type"] == "scene_plan"

        author_node = next(n for n in data["nodes"] if n["node_name"] == "author")
        assert author_node["label"] == "执笔"
        assert author_node["status"] == "completed"
        memory_node = next(n for n in data["nodes"] if n["node_name"] == "memory_curator")
        awaiting_node = next(n for n in data["nodes"] if n["node_name"] == "awaiting_publish")
        assert memory_node["label"] == "记忆整理"
        assert memory_node["node_group"] == "support_agent"
        assert memory_node["status"] == "pending"
        assert awaiting_node["label"] == "等待发布"
        assert awaiting_node["node_group"] == "terminal"

    def test_memory_curator_blocked_terminal_run_recommends_backfill(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_memory_timeout", status="reviewed")
        run_id = _seed_run(
            repo,
            "obs_memory_timeout",
            status="blocked",
            current_node="memory_curator",
        )
        repo.create_workflow_node_event(
            run_id=run_id,
            project_id="obs_memory_timeout",
            chapter_number=1,
            node_name="memory_curator",
            event_type="failed",
            status="failed",
            message="节点执行超时（>600秒），需要人工介入",
        )

        resp = client.get("/api/projects/obs_memory_timeout/chapters/1/workflow-timeline")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["recovery"]["recommended_action"] == "backfill_memory"
        actions = {action["key"]: action for action in data["recovery"]["safe_actions"]}
        assert "backfill_memory" in actions
        assert actions["backfill_memory"]["label"] == "补跑记忆提取"

    def test_timeline_includes_complete_canonical_node_skeleton(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_skeleton", status="planned")
        _seed_run(repo, "obs_skeleton", status="running", current_node="planner")

        resp = client.get("/api/projects/obs_skeleton/chapters/1/workflow-timeline")
        assert resp.status_code == 200
        data = resp.json()["data"]
        nodes = {node["node_name"]: node for node in data["nodes"]}
        expected_groups = {
            "health_check": "system",
            "task_discovery": "system",
            "planner": "creative_agent",
            "brief_validation": "system",  # v6.9.0
            "rhythm_budget_preflight": "system",  # v6.9.0
            "screenwriter": "creative_agent",
            "author": "creative_agent",
            "polisher": "creative_agent",
            "quality_gate": "quality",  # v6.8.5: 新增质检门禁节点
            "editor": "creative_agent",
            "memory_curator": "support_agent",
            "publisher": "terminal",
            "creative_ledger_curator": "support_agent",  # v6.9.0
            "awaiting_publish": "terminal",
            "archive": "terminal",
            "revision_router": "router",
            "human_review": "terminal",
        }
        assert list(nodes.keys())[:18] == list(expected_groups.keys())
        for node_name, group in expected_groups.items():
            assert nodes[node_name]["node_group"] == group
            assert nodes[node_name]["node_type"] == group
        assert nodes["planner"]["status"] == "running"
        assert nodes["screenwriter"]["status"] == "pending"

    def test_timeline_overlays_events_onto_canonical_nodes(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_overlay", status="drafted")
        run_id = _seed_run(repo, "obs_overlay", status="running", current_node="polisher")
        repo.create_workflow_node_event(
            run_id=run_id, project_id="obs_overlay", chapter_number=1,
            node_name="author", event_type="started", status="running", message="开始执笔撰写",
        )
        repo.create_workflow_node_event(
            run_id=run_id, project_id="obs_overlay", chapter_number=1,
            node_name="author", event_type="completed", status="completed", message="已生成章节初稿",
        )
        repo.create_workflow_node_event(
            run_id=run_id, project_id="obs_overlay", chapter_number=1,
            node_name="polisher", event_type="started", status="running", message="开始润色",
        )

        resp = client.get("/api/projects/obs_overlay/chapters/1/workflow-timeline")
        assert resp.status_code == 200
        nodes = {node["node_name"]: node for node in resp.json()["data"]["nodes"]}
        assert nodes["author"]["status"] == "completed"
        assert nodes["polisher"]["status"] == "running"
        assert nodes["editor"]["status"] == "pending"
        assert "已生成章节初稿" in nodes["author"]["messages"]

    def test_timeline_marks_planner_skipped_when_manual_instruction_starts_downstream(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_planner_skipped", status="scripted")
        run_id = _seed_run(repo, "obs_planner_skipped", status="running", current_node="author")
        repo.create_workflow_node_event(
            run_id=run_id, project_id="obs_planner_skipped", chapter_number=1,
            node_name="screenwriter", event_type="started", status="running", message="开始编剧",
        )
        repo.create_workflow_node_event(
            run_id=run_id, project_id="obs_planner_skipped", chapter_number=1,
            node_name="screenwriter", event_type="completed", status="completed", message="已生成章节场景规划",
        )

        resp = client.get("/api/projects/obs_planner_skipped/chapters/1/workflow-timeline")
        assert resp.status_code == 200
        nodes = {node["node_name"]: node for node in resp.json()["data"]["nodes"]}
        assert nodes["planner"]["status"] == "skipped"
        assert "本轮从执笔继续，跳过该节点。" in nodes["planner"]["messages"]
        assert nodes["screenwriter"]["status"] == "completed"

    def test_timeline_uses_latest_event_for_repeated_revision_nodes(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_repeated", status="revision")
        run_id = _seed_run(repo, "obs_repeated", status="running", current_node="author")
        repo.create_workflow_node_event(
            run_id=run_id, project_id="obs_repeated", chapter_number=1,
            node_name="author", event_type="started", status="running", message="开始执笔撰写",
        )
        repo.create_workflow_node_event(
            run_id=run_id, project_id="obs_repeated", chapter_number=1,
            node_name="author", event_type="completed", status="completed", message="已生成章节初稿",
        )
        repo.create_workflow_node_event(
            run_id=run_id, project_id="obs_repeated", chapter_number=1,
            node_name="editor", event_type="started", status="running", message="开始审核",
        )
        repo.create_workflow_node_event(
            run_id=run_id, project_id="obs_repeated", chapter_number=1,
            node_name="editor", event_type="completed", status="completed", message="审核完成",
        )
        repo.create_workflow_node_event(
            run_id=run_id, project_id="obs_repeated", chapter_number=1,
            node_name="author", event_type="started", status="running", message="开始执笔撰写",
        )

        resp = client.get("/api/projects/obs_repeated/chapters/1/workflow-timeline")
        assert resp.status_code == 200
        nodes = {node["node_name"]: node for node in resp.json()["data"]["nodes"]}
        assert nodes["author"]["status"] == "running"
        assert nodes["author"]["completed_at"] is None
        assert nodes["editor"]["status"] == "completed"
        assert nodes["polisher"]["status"] == "pending"

    def test_timeline_marks_upstream_nodes_skipped_when_resuming_from_later_status(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_resume_later", status="polished")
        run_id = _seed_run(repo, "obs_resume_later", status="running", current_node="editor")
        repo.create_workflow_node_event(
            run_id=run_id, project_id="obs_resume_later", chapter_number=1,
            node_name="editor", event_type="started", status="running", message="开始审核",
        )

        resp = client.get("/api/projects/obs_resume_later/chapters/1/workflow-timeline")
        assert resp.status_code == 200
        nodes = {node["node_name"]: node for node in resp.json()["data"]["nodes"]}
        assert nodes["screenwriter"]["status"] == "skipped"
        assert nodes["author"]["status"] == "skipped"
        assert nodes["polisher"]["status"] == "skipped"
        assert "本轮从审核继续，跳过该节点。" in nodes["author"]["messages"]
        assert nodes["editor"]["status"] == "running"

    def test_timeline_does_not_attach_chapter_fallback_artifacts_to_eventful_run(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_no_artifact_leak", status="polished")
        old_run_id = _seed_run(repo, "obs_no_artifact_leak", status="blocked", current_node="human_review")
        repo.save_artifact("obs_no_artifact_leak", 1, "author", "draft", workflow_run_id=old_run_id)
        new_run_id = _seed_run(repo, "obs_no_artifact_leak", status="running", current_node="editor")
        repo.create_workflow_node_event(
            run_id=new_run_id, project_id="obs_no_artifact_leak", chapter_number=1,
            node_name="editor", event_type="started", status="running", message="开始审核",
        )

        resp = client.get("/api/projects/obs_no_artifact_leak/chapters/1/workflow-timeline")
        assert resp.status_code == 200
        nodes = {node["node_name"]: node for node in resp.json()["data"]["nodes"]}
        assert nodes["author"]["artifacts"] == []
        assert nodes["editor"]["status"] == "running"

    def test_timeline_marks_current_node_when_no_events_exist(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_current_fallback", status="drafted")
        _seed_run(repo, "obs_current_fallback", status="running", current_node="polisher")

        resp = client.get("/api/projects/obs_current_fallback/chapters/1/workflow-timeline")
        assert resp.status_code == 200
        nodes = {node["node_name"]: node for node in resp.json()["data"]["nodes"]}
        assert nodes["polisher"]["status"] == "running"
        assert nodes["author"]["status"] == "skipped"

    def test_timeline_reconciles_latest_blocked_run_to_blocking_chapter(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_blocked_truth", status="planned")
        run_id = _seed_run(repo, "obs_blocked_truth", status="blocked", current_node="human_review")
        repo.create_workflow_node_event(
            run_id=run_id, project_id="obs_blocked_truth", chapter_number=1,
            node_name="author", event_type="completed", status="completed", message="已生成章节初稿",
        )
        repo.create_workflow_node_event(
            run_id=run_id, project_id="obs_blocked_truth", chapter_number=1,
            node_name="human_review", event_type="failed", status="failed", message="需要人工干预",
        )

        resp = client.get("/api/projects/obs_blocked_truth/chapters/1/workflow-timeline")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["run_status"] == "blocked"
        assert data["recovery"]["recommended_action"] == "reset_chapter"
        assert repo.get_chapter("obs_blocked_truth", 1)["status"] == "blocking"

    def test_workspace_reconciles_latest_blocked_run_but_ignores_old_blocked_run(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_workspace_blocked", status="planned")
        old_run_id = _seed_run(repo, "obs_workspace_blocked", status="blocked", current_node="human_review")
        _backdate_run(repo, old_run_id, 5)

        resp = client.get("/api/projects/obs_workspace_blocked/workspace")
        assert resp.status_code == 200
        data = resp.json()["data"]
        chapter = data["chapters"][0]
        assert chapter["status"] == "blocking"
        assert data["stats"]["status_counts"]["blocking"] == 1

        repo.reset_chapter("obs_workspace_blocked", 1)
        _seed_run(repo, "obs_workspace_blocked", status="completed", current_node="publish")

        resp = client.get("/api/projects/obs_workspace_blocked/workspace")
        assert resp.status_code == 200
        data = resp.json()["data"]
        chapter = data["chapters"][0]
        assert chapter["status"] == "planned"
        assert data["stats"]["status_counts"]["planned"] == 1

    def test_chapter_reset_marks_blocked_run_recovered_so_reconcile_does_not_reblock(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_reset_recovered", status="blocking")
        run_id = _seed_run(repo, "obs_reset_recovered", status="blocked", current_node="human_review")

        reset_resp = client.post("/api/projects/obs_reset_recovered/chapters/1/reset")
        assert reset_resp.status_code == 200
        reset_data = reset_resp.json()["data"]
        assert reset_data["new_status"] == "planned"
        assert reset_data["recovered_blocked_runs"] == 1

        workspace_resp = client.get("/api/projects/obs_reset_recovered/workspace")
        assert workspace_resp.status_code == 200
        workspace = workspace_resp.json()["data"]
        assert workspace["chapters"][0]["status"] == "planned"
        assert workspace["stats"]["status_counts"]["planned"] == 1
        runs = repo.get_workflow_runs_for_project("obs_reset_recovered", chapter_number=1, limit=1)
        assert runs[0]["id"] == run_id
        assert runs[0]["status"] == "completed"
        assert runs[0]["current_node"] == "reset_recovery"
        assert runs[0]["error_message"] is None

        timeline_resp = client.get("/api/projects/obs_reset_recovered/chapters/1/workflow-timeline")
        assert timeline_resp.status_code == 200
        timeline = timeline_resp.json()["data"]
        assert timeline["run_id"] is None
        assert all(node["status"] == "pending" for node in timeline["nodes"])

    def test_run_recovery_reset_marks_target_blocked_run_recovered(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_run_reset_recovered", status="blocking")
        run_id = _seed_run(repo, "obs_run_reset_recovered", status="blocked", current_node="human_review")

        reset_resp = client.post(
            f"/api/runs/{run_id}/recovery/reset",
            json={"confirm": True},
        )
        assert reset_resp.status_code == 200
        reset_data = reset_resp.json()["data"]
        assert reset_data["new_status"] == "planned"
        assert reset_data["recovered_blocked_runs"] == 1

        workspace_resp = client.get("/api/projects/obs_run_reset_recovered/workspace")
        assert workspace_resp.status_code == 200
        workspace = workspace_resp.json()["data"]
        assert workspace["chapters"][0]["status"] == "planned"
        runs = repo.get_workflow_runs_for_project("obs_run_reset_recovered", chapter_number=1, limit=1)
        assert runs[0]["status"] == "completed"
        assert runs[0]["current_node"] == "reset_recovery"

    def test_chapter_reset_recovers_failed_running_run_instead_of_reblocking(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_reset_failed_running", status="blocking")
        run_id = _seed_run(repo, "obs_reset_failed_running", status="running", current_node="screenwriter")
        repo.update_workflow_run(
            run_id,
            status="failed",
            current_node="screenwriter",
            error_message="Screenwriter: stale state, status advance failed",
        )

        reset_resp = client.post("/api/projects/obs_reset_failed_running/chapters/1/reset")
        assert reset_resp.status_code == 200
        reset_data = reset_resp.json()["data"]
        assert reset_data["new_status"] == "planned"
        assert reset_data["recovered_blocked_runs"] == 1
        assert reset_data["invalidated_runs"] == 1

        chapter = repo.get_chapter("obs_reset_failed_running", 1)
        assert chapter["status"] == "planned"
        runs = repo.get_workflow_runs_for_project("obs_reset_failed_running", chapter_number=1, limit=1)
        assert runs[0]["id"] == run_id
        assert runs[0]["status"] == "completed"
        assert runs[0]["current_node"] == "reset_recovery"
        assert runs[0]["error_message"] is None

        workspace_resp = client.get("/api/projects/obs_reset_failed_running/workspace")
        assert workspace_resp.status_code == 200
        workspace = workspace_resp.json()["data"]
        assert workspace["chapters"][0]["status"] == "planned"

    def test_production_next_reconciles_blocked_run_before_recommendation(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_prod_next_blocked", status="planned")
        _seed_run(repo, "obs_prod_next_blocked", status="blocked", current_node="human_review")

        resp = client.get("/api/projects/obs_prod_next_blocked/production-next")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["next_action"]["key"] == "recover_blocked_run"
        assert data["next_action"]["target_chapter"] == 1
        assert repo.get_chapter("obs_prod_next_blocked", 1)["status"] == "blocking"

    def test_production_next_prioritizes_blocked_memory_curator_backfill(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_prod_next_memory_blocked", status="reviewed")
        run_id = _seed_run(
            repo,
            "obs_prod_next_memory_blocked",
            status="blocked",
            current_node="memory_curator",
        )

        resp = client.get("/api/projects/obs_prod_next_memory_blocked/production-next")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["next_action"]["key"] == "backfill_memory"
        assert data["next_action"]["run_id"] == run_id
        assert data["next_action"]["target_chapter"] == 1
        assert data["domain_result"]["next_action"] == "backfill_memory"

    def test_production_next_blocks_timeout_memory_curator_before_publish(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_prod_next_memory_timeout", status="reviewed")
        run_id = _seed_run(
            repo,
            "obs_prod_next_memory_timeout",
            status="running",
            current_node="memory_curator",
        )
        repo.create_workflow_node_event(
            run_id=run_id,
            project_id="obs_prod_next_memory_timeout",
            chapter_number=1,
            node_name="memory_curator",
            event_type="failed",
            status="failed",
            message="节点执行超时（>600秒），需要人工介入",
        )
        repo.acquire_memory_curator_lock("obs_prod_next_memory_timeout", 1, run_id=run_id)

        resp = client.get("/api/projects/obs_prod_next_memory_timeout/production-next")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["next_action"]["key"] == "backfill_memory"
        assert data["next_action"]["run_id"] == run_id
        assert repo.get_memory_curator_lock("obs_prod_next_memory_timeout", 1) is None
        runs = repo.get_workflow_runs_for_project(
            "obs_prod_next_memory_timeout",
            chapter_number=1,
            limit=1,
        )
        assert runs[0]["status"] == "blocked"
        assert runs[0]["current_node"] == "memory_curator"

    def test_timeline_maps_legacy_publish_current_node_to_publisher(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_publish_alias", status="published")
        _seed_run(repo, "obs_publish_alias", status="completed", current_node="publish")

        resp = client.get("/api/projects/obs_publish_alias/chapters/1/workflow-timeline")
        assert resp.status_code == 200
        nodes = {node["node_name"]: node for node in resp.json()["data"]["nodes"]}
        assert nodes["publisher"]["status"] == "completed"

    def test_timeline_includes_checkpoint_metadata_when_available(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_checkpoint", status="drafted")
        _seed_run(repo, "obs_checkpoint", status="running", current_node="author")

        from novel_factory.workflow.checkpoint import (
            derive_checkpoint_db_path,
            get_checkpoint_thread_id,
            get_sqlite_checkpointer,
        )

        cp_path = derive_checkpoint_db_path(repo.db_path)
        thread_id = get_checkpoint_thread_id("obs_checkpoint", 1)
        with get_sqlite_checkpointer(cp_path) as cp:
            cp.put(
                {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
                {
                    "v": 1,
                    "ts": "2026-05-13T10:00:00Z",
                    "id": "ckpt-obs",
                    "channel_values": {
                        "current_node": "author",
                        "chapter_status": "drafted",
                    },
                    "channel_versions": {},
                    "versions_seen": {},
                },
                {"source": "author", "writes": {"author": {"chapter_status": "drafted"}}},
                {},
            )

        resp = client.get("/api/projects/obs_checkpoint/chapters/1/workflow-timeline")
        assert resp.status_code == 200
        checkpoint = resp.json()["data"]["checkpoint"]
        assert checkpoint["checkpoint_exists"] is True
        assert checkpoint["checkpoint_node"] == "author"
        assert checkpoint["current_node"] == "author"
        assert checkpoint["recovery_available"] is True
        assert "chapter_status" in checkpoint["state_keys"]

    def test_timeline_returns_recovery_for_stale_run(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_stale", status="drafted")
        run_id = _seed_run(repo, "obs_stale", status="running", current_node="author")
        _backdate_run(repo, run_id, 35)

        resp = client.get("/api/projects/obs_stale/chapters/1/workflow-timeline")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_stale"] is True
        recovery = data["recovery"]
        assert recovery["recommended_action"] is not None
        assert any(a["key"] == "mark_stuck" for a in recovery["safe_actions"])
        assert any(a["key"] == "reset_chapter" for a in recovery["safe_actions"])

    def test_timeline_hides_recovery_for_healthy_running_run(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_active", status="scripted")
        _seed_run(repo, "obs_active", status="running", current_node="author")

        resp = client.get("/api/projects/obs_active/chapters/1/workflow-timeline")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["run_status"] == "running"
        assert data["is_stale"] is False
        assert data["recovery"]["recommended_action"] is None
        assert data["recovery"]["safe_actions"] == []

    def test_timeline_no_recovery_for_terminal_chapter(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_terminal", status="published")
        run_id = _seed_run(repo, "obs_terminal", status="completed", current_node="publish")

        resp = client.get("/api/projects/obs_terminal/chapters/1/workflow-timeline")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["run_status"] == "completed"
        recovery = data["recovery"]
        assert recovery["recommended_action"] is None

    def test_timeline_with_run_id_query_param(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_runid", status="planned")
        run_id = _seed_run(repo, "obs_runid", status="running", current_node="planner")

        resp = client.get(f"/api/projects/obs_runid/chapters/1/workflow-timeline?run_id={run_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["run_id"] == run_id

    def test_timeline_does_not_return_500_for_missing_chapter(self, tmp_path):
        client, repo = _make_client(tmp_path)
        resp = client.get("/api/projects/obs_missing/chapters/99/workflow-timeline")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "CHAPTER_NOT_FOUND"


class TestWorkflowTimelineReconcile:
    """Tests that terminal chapter + running run is reconciled without regression."""

    def test_terminal_chapter_running_run_reconciled(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_reconcile", status="reviewed")
        run_id = _seed_run(repo, "obs_reconcile", status="running", current_node="author")

        resp = client.get("/api/projects/obs_reconcile/chapters/1/workflow-timeline")
        assert resp.status_code == 200
        data = resp.json()["data"]
        # Reconciliation should close the running run
        assert data["run_status"] == "completed"
        assert data["current_node"] == "awaiting_publish"

    def test_published_chapter_running_run_reconciled(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "obs_pub_recon", status="published")
        run_id = _seed_run(repo, "obs_pub_recon", status="running", current_node="author")

        resp = client.get("/api/projects/obs_pub_recon/chapters/1/workflow-timeline")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["run_status"] == "completed"
        assert data["current_node"] == "publish"
