"""v6.1 Agent Work Process Streaming & Auditable Execution Evidence tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository


def _make_client(tmp_path):
    db_path = str(tmp_path / "v61.db")
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    return TestClient(app), Repository(db_path)


def _seed_project_and_chapter(repo: Repository, project_id: str, chapter_number: int = 1, status: str = "planned"):
    repo.create_project(project_id=project_id, name="V61 Project", genre="fantasy")
    repo.add_chapter(project_id, chapter_number, title=f"Ch{chapter_number}", status=status)


def _seed_run(repo: Repository, project_id: str, chapter_number: int = 1, status: str = "running", current_node: str = "author") -> str:
    run_id = repo.create_workflow_run(project_id, chapter_number)
    repo.update_workflow_run(run_id, status=status, current_node=current_node)
    return run_id


class TestExecutionEventRepository:
    """Tests for workflow_execution_events table and repository."""

    def test_create_and_query_execution_event(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        run_id = _seed_run(repo, "demo")

        eid = repo.create_workflow_execution_event(
            run_id=run_id,
            project_id="demo",
            chapter_number=1,
            node_name="author",
            event_type="llm_started",
            agent_id="author",
            status="info",
            message="LLM 调用开始：执笔生成正文",
            payload={"model": "gpt-4"},
        )
        assert eid is not None

        events = repo.get_workflow_execution_events(run_id)
        assert len(events) == 1
        assert events[0]["event_type"] == "llm_started"
        assert events[0]["message"] == "LLM 调用开始：执笔生成正文"
        assert events[0]["payload"] == {"model": "gpt-4"}

    def test_multiple_events_ordered_by_created_at(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        run_id = _seed_run(repo, "demo")

        repo.create_workflow_execution_event(
            run_id=run_id, project_id="demo", chapter_number=1,
            node_name="author", event_type="context_loaded", message="读取上下文完成",
        )
        repo.create_workflow_execution_event(
            run_id=run_id, project_id="demo", chapter_number=1,
            node_name="author", event_type="llm_completed", message="LLM 调用完成",
            token_count=3120, latency_ms=64200,
        )

        events = repo.get_workflow_execution_events(run_id)
        assert len(events) == 2
        assert events[0]["event_type"] == "context_loaded"
        assert events[1]["event_type"] == "llm_completed"
        assert events[1]["token_count"] == 3120

    def test_get_events_for_chapter(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        run_id = _seed_run(repo, "demo")

        repo.create_workflow_execution_event(
            run_id=run_id, project_id="demo", chapter_number=1,
            node_name="author", event_type="node_started", message="开始",
        )

        events = repo.get_workflow_execution_events_for_chapter("demo", 1, run_id=run_id)
        assert len(events) == 1

    def test_get_events_since_id(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        run_id = _seed_run(repo, "demo")

        eid1 = repo.create_workflow_execution_event(
            run_id=run_id, project_id="demo", chapter_number=1,
            node_name="author", event_type="context_loaded", message="ctx",
        )
        repo.create_workflow_execution_event(
            run_id=run_id, project_id="demo", chapter_number=1,
            node_name="author", event_type="llm_completed", message="done",
        )

        events = repo.get_workflow_execution_events_since(run_id, since_id=eid1)
        assert len(events) == 1
        assert events[0]["event_type"] == "llm_completed"

    def test_get_latest_event(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        run_id = _seed_run(repo, "demo")

        repo.create_workflow_execution_event(
            run_id=run_id, project_id="demo", chapter_number=1,
            node_name="author", event_type="llm_started", message="start",
        )
        repo.create_workflow_execution_event(
            run_id=run_id, project_id="demo", chapter_number=1,
            node_name="author", event_type="llm_completed", message="done",
        )

        latest = repo.get_latest_workflow_execution_event(run_id, node_name="author", event_type="llm_completed")
        assert latest is not None
        assert latest["message"] == "done"


class TestExecutionEventHelpers:
    """Tests for execution_events helper module."""

    def test_log_execution_event(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        run_id = _seed_run(repo, "demo")

        from novel_factory.workflow.execution_events import log_execution_event
        state = {"workflow_run_id": run_id, "project_id": "demo", "chapter_number": 1}

        eid = log_execution_event(
            repo, state, "author", "context_loaded",
            message="读取上下文完成：3 个场景、4 个关键事件",
            payload={"scene_beat_count": 3},
        )
        assert eid is not None

    def test_log_execution_event_no_run_id(self, tmp_path):
        _, repo = _make_client(tmp_path)
        from novel_factory.workflow.execution_events import log_execution_event
        state = {"workflow_run_id": None, "project_id": "demo", "chapter_number": 1}
        result = log_execution_event(repo, state, "author", "test", message="test")
        assert result is None

    def test_build_context_loaded_messages(self, tmp_path):
        from novel_factory.workflow.execution_events import build_context_loaded_message

        msg = build_context_loaded_message("author", {"scene_beat_count": 3, "required_event_count": 4, "word_target": 3000})
        assert "3 个场景" in msg
        assert "4 个关键事件" in msg
        assert "字数目标 3000" in msg

        msg2 = build_context_loaded_message("polisher", {"original_word_count": 3386, "fact_lock_count": 4})
        assert "3386 字" in msg2
        assert "事实锁 4 条" in msg2

        msg3 = build_context_loaded_message("editor", {"content_word_count": 3500, "review_dimensions": ["a", "b", "c", "d", "e"]})
        assert "3500 字" in msg3
        assert "5 个审校维度" in msg3

    def test_verify_planner_evidence_missing_instruction(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        _seed_run(repo, "demo")

        from novel_factory.workflow.execution_events import verify_agent_completion_evidence
        state = {"project_id": "demo", "chapter_number": 1, "workflow_run_id": "test"}

        result = verify_agent_completion_evidence(repo, state, "planner")
        assert result["ok"] is False
        assert result["severity"] == "fail"
        assert any("指令" in m for m in result["missing"])

    def test_verify_screenwriter_evidence_missing_beats(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        _seed_run(repo, "demo")

        from novel_factory.workflow.execution_events import verify_agent_completion_evidence
        state = {"project_id": "demo", "chapter_number": 1, "workflow_run_id": "test"}

        result = verify_agent_completion_evidence(repo, state, "screenwriter")
        assert result["ok"] is False
        assert any("beat" in m.lower() for m in result["missing"])

    def test_verify_author_evidence_missing_content(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        _seed_run(repo, "demo")

        from novel_factory.workflow.execution_events import verify_agent_completion_evidence
        state = {"project_id": "demo", "chapter_number": 1, "workflow_run_id": "test"}

        result = verify_agent_completion_evidence(repo, state, "author")
        assert result["ok"] is False
        assert any("正文" in m for m in result["missing"])

    def test_verify_author_with_all_evidence(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        run_id = _seed_run(repo, "demo")
        project_id = "demo"
        chapter_number = 1

        content = "这是正文内容。" * 50
        repo.update_chapter_status(project_id, chapter_number, "drafted")
        repo.save_chapter_content(project_id, chapter_number, content, "测试章节")
        repo.save_version(project_id, chapter_number, content, created_by="author")
        repo.save_artifact(project_id, chapter_number, "author", "draft", content_json={"content": "test"}, workflow_run_id=run_id)

        from novel_factory.workflow.execution_events import verify_agent_completion_evidence
        state = {"project_id": project_id, "chapter_number": chapter_number, "workflow_run_id": run_id}

        result = verify_agent_completion_evidence(repo, state, "author")
        assert result["ok"] is True
        assert result["severity"] == "pass"

    def test_verify_editor_pass_without_state_card(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        _seed_run(repo, "demo")
        project_id = "demo"
        chapter_number = 1

        content = "这是正文内容。" * 50
        repo.update_chapter_status(project_id, chapter_number, "polished")
        repo.save_chapter_content(project_id, chapter_number, content, "测试章节")
        ch = repo.get_chapter(project_id, chapter_number)
        repo.save_review(
            project_id=project_id,
            chapter_id=ch["id"],
            passed=True, score=95,
            setting_score=24, logic_score=24, poison_score=19, text_score=14, pacing_score=14,
            issues=[], suggestions=[], revision_target=None,
        )

        from novel_factory.workflow.execution_events import verify_agent_completion_evidence
        state = {"project_id": project_id, "chapter_number": chapter_number, "workflow_run_id": "test"}

        result = verify_agent_completion_evidence(repo, state, "editor")
        assert result["ok"] is False
        assert any("状态卡" in m for m in result["missing"])

    def test_verify_memory_curator_requires_memory_batch(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        _seed_run(repo, "demo")

        from novel_factory.workflow.execution_events import verify_agent_completion_evidence
        state = {"project_id": "demo", "chapter_number": 1, "workflow_run_id": "test"}

        result = verify_agent_completion_evidence(repo, state, "memory_curator")
        assert result["severity"] == "fail"
        assert any("记忆收件箱批次" in m for m in result["missing"])

    def test_verify_memory_curator_does_not_invent_state_card_fallback(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        _seed_run(repo, "demo")
        repo.save_chapter_state("demo", 1, {"new_facts": ["铜钥匙出现"]}, "第1章状态卡")

        from novel_factory.workflow.execution_events import verify_agent_completion_evidence
        state = {"project_id": "demo", "chapter_number": 1, "workflow_run_id": "test"}

        result = verify_agent_completion_evidence(repo, state, "memory_curator")
        assert result["severity"] == "fail"
        assert any("记忆收件箱批次" in m for m in result["missing"])
        assert not any("状态卡兜底" in w for w in result["warnings"])

    def test_verify_memory_curator_detects_chapter_batch(self, tmp_path):
        _, repo = _make_client(tmp_path)
        repo.create_project(project_id="demo", name="V61 Project", genre="fantasy")
        repo.add_chapter("demo", 1, title="Ch1", status="planned")
        repo.add_chapter("demo", 2, title="Ch2", status="planned")
        run_id = _seed_run(repo, "demo", chapter_number=1)
        repo.create_memory_batch("demo", chapter_number=2, run_id="other-run", summary="Other chapter")
        repo.create_memory_batch("demo", chapter_number=1, run_id=run_id, summary="Chapter memory")

        from novel_factory.workflow.execution_events import verify_agent_completion_evidence
        state = {"project_id": "demo", "chapter_number": 1, "workflow_run_id": run_id}

        result = verify_agent_completion_evidence(repo, state, "memory_curator")
        assert result["severity"] == "pass"
        assert result["ok"] is True
        assert result["warnings"] == []


class TestTimelineExecutionEvents:
    """Tests for timeline API with execution events embedded."""

    def test_timeline_returns_execution_events_in_nodes(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        run_id = _seed_run(repo, "demo", status="completed", current_node="author")

        repo.create_workflow_node_event(
            run_id=run_id, project_id="demo", chapter_number=1,
            node_name="author", event_type="started", status="running",
            message="开始执笔撰写",
        )
        repo.create_workflow_node_event(
            run_id=run_id, project_id="demo", chapter_number=1,
            node_name="author", event_type="completed", status="completed",
            message="已生成章节初稿",
        )

        repo.create_workflow_execution_event(
            run_id=run_id, project_id="demo", chapter_number=1,
            node_name="author", event_type="context_loaded",
            message="读取上下文完成：3 个场景、4 个关键事件",
            payload={"scene_beat_count": 3, "required_event_count": 4},
        )
        repo.create_workflow_execution_event(
            run_id=run_id, project_id="demo", chapter_number=1,
            node_name="author", event_type="llm_completed",
            message="LLM 调用完成：耗时 64.2s，3120 tokens",
            token_count=3120, latency_ms=64200,
        )
        repo.create_workflow_execution_event(
            run_id=run_id, project_id="demo", chapter_number=1,
            node_name="author", event_type="evidence_verified",
            message="完成证据校验通过",
            status="pass",
            payload={"ok": True, "severity": "pass"},
        )

        resp = client.get("/api/projects/demo/chapters/1/workflow-timeline")
        assert resp.status_code == 200
        data = resp.json()["data"]

        author_node = next(n for n in data["nodes"] if n["node_name"] == "author")
        assert len(author_node["events"]) == 3
        assert author_node["events"][0]["event_type"] == "context_loaded"
        assert author_node["evidence"]["has_evidence"] is True
        assert author_node["evidence"]["has_evidence_failure"] is False
        assert author_node["evidence"]["event_count"] == 3

    def test_timeline_backward_compatible_without_execution_events(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        run_id = _seed_run(repo, "demo", status="completed")

        repo.create_workflow_node_event(
            run_id=run_id, project_id="demo", chapter_number=1,
            node_name="planner", event_type="started", status="running",
            message="开始章节规划",
        )

        resp = client.get("/api/projects/demo/chapters/1/workflow-timeline")
        assert resp.status_code == 200
        data = resp.json()["data"]
        planner_node = next(n for n in data["nodes"] if n["node_name"] == "planner")
        assert "events" in planner_node
        assert "evidence" in planner_node

    def test_timeline_survives_missing_config_file(self, tmp_path):
        db_path = str(tmp_path / "missing-config.db")
        init_db(db_path)
        app = create_api_app(
            db_path=db_path,
            config_path=str(tmp_path / "missing-local.yaml"),
            llm_mode="real",
        )
        client = TestClient(app)
        repo = Repository(db_path)
        _seed_project_and_chapter(repo, "demo", status="reviewed")
        _seed_run(repo, "demo", status="completed", current_node="memory_curator")

        resp = client.get("/api/projects/demo/chapters/1/workflow-timeline")

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["checkpoint"]["checkpoint_exists"] is False


class TestSSEStreamEndpoint:
    """Tests for SSE streaming endpoint."""

    def test_sse_replays_existing_events(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        run_id = _seed_run(repo, "demo", status="completed", current_node="author")

        repo.create_workflow_execution_event(
            run_id=run_id, project_id="demo", chapter_number=1,
            node_name="author", event_type="context_loaded",
            message="读取上下文完成",
        )
        repo.create_workflow_execution_event(
            run_id=run_id, project_id="demo", chapter_number=1,
            node_name="author", event_type="llm_completed",
            message="LLM 调用完成",
        )

        resp = client.get("/api/projects/demo/chapters/1/workflow-stream")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        body = resp.text
        assert "workflow_event" in body
        assert "context_loaded" in body
        assert "llm_completed" in body
        assert "workflow_done" in body

    def test_sse_returns_done_when_no_run(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")

        resp = client.get("/api/projects/demo/chapters/1/workflow-stream")
        assert resp.status_code == 200
        body = resp.text
        assert "workflow_done" in body
        assert "no_run" in body

    def test_sse_with_since_id_filter(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        run_id = _seed_run(repo, "demo", status="completed")

        eid = repo.create_workflow_execution_event(
            run_id=run_id, project_id="demo", chapter_number=1,
            node_name="author", event_type="context_loaded",
            message="old event",
        )
        repo.create_workflow_execution_event(
            run_id=run_id, project_id="demo", chapter_number=1,
            node_name="author", event_type="llm_completed",
            message="new event",
        )

        resp = client.get(f"/api/projects/demo/chapters/1/workflow-stream?since_id={eid}")
        assert resp.status_code == 200
        body = resp.text
        assert "new event" in body
        assert "old event" not in body

    def test_sse_replays_explicit_historical_run_id(self, tmp_path):
        client, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        old_run_id = _seed_run(repo, "demo", status="completed", current_node="author")
        latest_run_id = _seed_run(repo, "demo", status="completed", current_node="editor")

        repo.create_workflow_execution_event(
            run_id=old_run_id, project_id="demo", chapter_number=1,
            node_name="author", event_type="llm_completed", message="old run event",
        )
        repo.create_workflow_execution_event(
            run_id=latest_run_id, project_id="demo", chapter_number=1,
            node_name="editor", event_type="llm_completed", message="latest run event",
        )

        resp = client.get(f"/api/projects/demo/chapters/1/workflow-stream?run_id={old_run_id}")
        assert resp.status_code == 200
        body = resp.text
        assert "old run event" in body
        assert "latest run event" not in body


class TestAgentExecEvents:
    """Tests that agents emit _exec_events in their results."""

    def test_planner_emits_exec_events(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        _seed_run(repo, "demo")

        from novel_factory.agents.planner import PlannerAgent
        from novel_factory.llm.stub_provider import StubLLM

        llm = StubLLM()
        agent = PlannerAgent(repo, llm)
        state = {
            "project_id": "demo",
            "chapter_number": 1,
            "chapter_status": "planned",
            "llm_mode": "stub",
            "workflow_run_id": "test-run",
        }
        result = agent.run(state)
        assert "error" not in result
        exec_events = result.get("_exec_events", [])
        assert len(exec_events) >= 1
        event_types = [e["event_type"] for e in exec_events]
        assert "artifact_saved" in event_types

    def test_screenwriter_emits_exec_events(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        _seed_run(repo, "demo")

        repo.create_instruction(
            project_id="demo", chapter_number=1,
            objective="测试目标", key_events='["事件1"]',
            ending_hook="钩子", word_target=3000,
        )
        repo.update_chapter_status("demo", 1, "planned")

        from novel_factory.agents.screenwriter import ScreenwriterAgent
        from novel_factory.llm.stub_provider import StubLLM

        llm = StubLLM()
        agent = ScreenwriterAgent(repo, llm)
        state = {
            "project_id": "demo",
            "chapter_number": 1,
            "chapter_status": "planned",
            "llm_mode": "stub",
            "workflow_run_id": "test-run",
        }
        result = agent.run(state)
        assert "error" not in result
        exec_events = result.get("_exec_events", [])
        event_types = [e["event_type"] for e in exec_events]
        assert "artifact_saved" in event_types


class TestExecutionTimer:
    """Tests for ExecutionTimer context manager."""

    def test_timer_measures_latency(self):
        from novel_factory.workflow.execution_events import ExecutionTimer

        with ExecutionTimer() as t:
            time.sleep(0.01)
        assert t.latency_ms >= 10
