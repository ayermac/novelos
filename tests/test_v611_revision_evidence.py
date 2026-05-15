"""v6.1.1 Revision Evidence and Routing Integrity tests."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository


def _make_client(tmp_path):
    db_path = str(tmp_path / "v611.db")
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    return TestClient(app), Repository(db_path)


def _seed_project_and_chapter(repo: Repository, project_id: str, chapter_number: int = 1, status: str = "planned"):
    repo.create_project(project_id=project_id, name="V611 Project", genre="fantasy")
    repo.add_chapter(project_id, chapter_number, title=f"Ch{chapter_number}", status=status)


class TestRevisionTargetRecovery:
    """Tests for revision target recovery from latest review."""

    def test_resolve_revision_target_polisher(self, tmp_path):
        """revision_target=polisher routes to polisher, not author."""
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        repo.update_chapter_status("demo", 1, "polished")

        ch = repo.get_chapter("demo", 1)
        repo.save_review(
            project_id="demo", chapter_id=ch["id"],
            passed=False, score=80,
            setting_score=22, logic_score=22, poison_score=18, text_score=10, pacing_score=8,
            issues=["AI痕迹过重"], suggestions=["优化句式节奏"],
            revision_target="polisher",
        )

        from novel_factory.workflow.conditions import resolve_revision_target
        target = resolve_revision_target(repo, "demo", 1)
        assert target == "polisher"

    def test_resolve_revision_target_author(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        repo.update_chapter_status("demo", 1, "polished")

        ch = repo.get_chapter("demo", 1)
        repo.save_review(
            project_id="demo", chapter_id=ch["id"],
            passed=False, score=70,
            setting_score=18, logic_score=18, poison_score=14, text_score=10, pacing_score=10,
            issues=["剧情逻辑问题"], suggestions=["重写关键场景"],
            revision_target="author",
        )

        from novel_factory.workflow.conditions import resolve_revision_target
        target = resolve_revision_target(repo, "demo", 1)
        assert target == "author"

    def test_resolve_revision_target_planner(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        repo.update_chapter_status("demo", 1, "polished")

        ch = repo.get_chapter("demo", 1)
        repo.save_review(
            project_id="demo", chapter_id=ch["id"],
            passed=False, score=60,
            setting_score=15, logic_score=15, poison_score=10, text_score=10, pacing_score=10,
            issues=["指令错误"], suggestions=["重新规划"],
            revision_target="planner",
        )

        from novel_factory.workflow.conditions import resolve_revision_target
        target = resolve_revision_target(repo, "demo", 1)
        assert target == "planner"

    def test_resolve_revision_target_defaults_to_author(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")

        from novel_factory.workflow.conditions import resolve_revision_target
        target = resolve_revision_target(repo, "demo", 1)
        assert target == "author"

    def test_route_by_revision_type_with_recovered_target(self, tmp_path):
        from novel_factory.workflow.conditions import route_by_revision_type
        from novel_factory.models.state import ChapterStatus

        state = {"chapter_status": ChapterStatus.REVISION.value, "quality_gate": {"revision_target": "polisher"}}
        assert route_by_revision_type(state) == "polisher"

        state = {"chapter_status": ChapterStatus.REVISION.value, "quality_gate": {"revision_target": "author"}}
        assert route_by_revision_type(state) == "author"

        state = {"chapter_status": ChapterStatus.REVISION.value, "quality_gate": {"revision_target": "planner"}}
        assert route_by_revision_type(state) == "planner"

        state = {"chapter_status": ChapterStatus.REVISION.value, "quality_gate": {}}
        assert route_by_revision_type(state) == "author"


class TestRevisionContextEvents:
    """Tests for revision context loaded events."""

    def test_author_emits_revision_context_loaded(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        repo.update_chapter_status("demo", 1, "revision")

        from novel_factory.agents.author import AuthorAgent
        from novel_factory.llm.stub_provider import StubLLM

        llm = StubLLM()
        agent = AuthorAgent(repo, llm)
        state = {
            "project_id": "demo",
            "chapter_number": 1,
            "chapter_status": "revision",
            "llm_mode": "stub",
            "workflow_run_id": "test-run",
            "_revision_review": {
                "review_id": 1,
                "score": 80,
                "revision_target": "author",
                "issues": '["剧情逻辑问题"]',
                "suggestions": '["重写关键场景"]',
            },
        }
        result = agent.run(state)
        exec_events = result.get("_exec_events", [])
        event_types = [e["event_type"] for e in exec_events]
        assert "revision_context_loaded" in event_types

        ctx_event = next(e for e in exec_events if e["event_type"] == "revision_context_loaded")
        assert ctx_event["payload"]["review_id"] == 1
        assert len(ctx_event["payload"]["issues"]) > 0

    def test_polisher_emits_revision_context_loaded(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        repo.update_chapter_status("demo", 1, "revision")
        repo.save_chapter_content("demo", 1, "这是测试正文内容。" * 50, "测试章节")

        from novel_factory.agents.polisher import PolisherAgent
        from novel_factory.llm.stub_provider import StubLLM

        llm = StubLLM()
        agent = PolisherAgent(repo, llm)
        state = {
            "project_id": "demo",
            "chapter_number": 1,
            "chapter_status": "revision",
            "llm_mode": "stub",
            "workflow_run_id": "test-run",
            "_revision_review": {
                "review_id": 2,
                "score": 82,
                "revision_target": "polisher",
                "issues": '["AI痕迹过重"]',
                "suggestions": '["优化句式节奏"]',
            },
        }
        result = agent.run(state)
        exec_events = result.get("_exec_events", [])
        event_types = [e["event_type"] for e in exec_events]
        assert "revision_context_loaded" in event_types


class TestRevisionDiffEvent:
    """Tests for revision diff generated events."""

    def test_author_emits_revision_diff_generated(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        repo.update_chapter_status("demo", 1, "revision")
        repo.save_chapter_content("demo", 1, "原始正文内容。" * 100, "测试章节")

        from novel_factory.agents.author import AuthorAgent
        from novel_factory.llm.stub_provider import StubLLM

        llm = StubLLM()
        agent = AuthorAgent(repo, llm)
        state = {
            "project_id": "demo",
            "chapter_number": 1,
            "chapter_status": "revision",
            "llm_mode": "stub",
            "workflow_run_id": "test-run",
        }
        result = agent.run(state)
        exec_events = result.get("_exec_events", [])
        event_types = [e["event_type"] for e in exec_events]
        assert "revision_diff_generated" in event_types

        diff_event = next(e for e in exec_events if e["event_type"] == "revision_diff_generated")
        assert "original_word_count" in diff_event["payload"]
        assert "revised_word_count" in diff_event["payload"]
        assert "word_count_delta" in diff_event["payload"]

    def test_polisher_emits_revision_diff_generated(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        repo.update_chapter_status("demo", 1, "revision")
        repo.save_chapter_content("demo", 1, "原始正文内容。" * 100, "测试章节")

        from novel_factory.agents.polisher import PolisherAgent
        from novel_factory.llm.stub_provider import StubLLM

        agent = PolisherAgent(repo, StubLLM())
        state = {
            "project_id": "demo",
            "chapter_number": 1,
            "chapter_status": "revision",
            "llm_mode": "stub",
            "workflow_run_id": "test-run",
            "_revision_review": {
                "review_id": 6,
                "score": 82,
                "revision_target": "polisher",
                "issues": '["AI痕迹过重"]',
                "suggestions": '["优化句式节奏"]',
            },
        }
        result = agent.run(state)
        exec_events = result.get("_exec_events", [])
        event_types = [e["event_type"] for e in exec_events]
        assert "revision_diff_generated" in event_types

        diff_event = next(e for e in exec_events if e["event_type"] == "revision_diff_generated")
        assert "original_word_count" in diff_event["payload"]
        assert "revised_word_count" in diff_event["payload"]
        assert "word_count_delta" in diff_event["payload"]


class TestRevisionFollowupVerified:
    """Tests for editor revision followup verification."""

    def test_editor_emits_revision_followup_verified(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        repo.update_chapter_status("demo", 1, "polished")
        repo.save_chapter_content("demo", 1, "这是测试正文内容。" * 50, "测试章节")

        from novel_factory.agents.editor import EditorAgent
        from novel_factory.llm.stub_provider import StubLLM

        llm = StubLLM()
        agent = EditorAgent(repo, llm)
        state = {
            "project_id": "demo",
            "chapter_number": 1,
            "chapter_status": "polished",
            "llm_mode": "stub",
            "workflow_run_id": "test-run",
            "_revision_review": {
                "review_id": 3,
                "score": 75,
                "revision_target": "author",
                "issues": '["剧情逻辑问题", "AI痕迹过重"]',
                "suggestions": '["重写关键场景"]',
            },
        }
        result = agent.run(state)
        exec_events = result.get("_exec_events", [])
        event_types = [e["event_type"] for e in exec_events]
        assert "revision_followup_verified" in event_types

        followup = next(e for e in exec_events if e["event_type"] == "revision_followup_verified")
        assert followup["payload"]["source_review_id"] == 3
        assert "resolved" in followup["payload"]
        assert "unresolved" in followup["payload"]


class TestRevisionArtifactMetadata:
    """Tests for revision metadata in artifacts."""

    def test_author_artifact_includes_revision_metadata(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        run_id = repo.create_workflow_run("demo", 1)
        repo.update_workflow_run(run_id, status="running")
        repo.update_chapter_status("demo", 1, "revision")

        from novel_factory.agents.author import AuthorAgent
        from novel_factory.llm.stub_provider import StubLLM

        llm = StubLLM()
        agent = AuthorAgent(repo, llm)
        state = {
            "project_id": "demo",
            "chapter_number": 1,
            "chapter_status": "revision",
            "llm_mode": "stub",
            "workflow_run_id": run_id,
            "_revision_review": {
                "review_id": 5,
                "score": 78,
                "revision_target": "author",
                "issues": '["逻辑问题"]',
                "suggestions": '["重写"]',
            },
        }
        result = agent.run(state)
        assert "error" not in result

        # Query artifact content directly since get_artifacts_for_chapter omits content_json
        conn = repo._conn()
        try:
            row = conn.execute(
                "SELECT content_json FROM agent_artifacts "
                "WHERE project_id='demo' AND chapter_number=1 AND agent_id='author' "
                "AND artifact_type='draft' AND workflow_run_id=? "
                "ORDER BY created_at DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        content = json.loads(row["content_json"])
        assert "_revision_metadata" in content
        assert content["_revision_metadata"]["revision_source_review_id"] == 5
        assert content["_revision_metadata"]["revision_target"] == "author"
        assert content["_revision_metadata"]["revision_issues"] == ["逻辑问题"]
        assert content["_revision_metadata"]["revision_suggestions"] == ["重写"]


class TestPlannerRevisionTarget:
    """Tests for planner-targeted revision execution."""

    def test_planner_accepts_revision_status_and_injects_review_feedback(self, tmp_path):
        _, repo = _make_client(tmp_path)
        _seed_project_and_chapter(repo, "demo")
        repo.update_chapter_status("demo", 1, "revision")

        from novel_factory.agents.planner import PlannerAgent
        from novel_factory.llm.stub_provider import StubLLM

        agent = PlannerAgent(repo, StubLLM())
        state = {
            "project_id": "demo",
            "chapter_number": 1,
            "chapter_status": "revision",
            "llm_mode": "stub",
            "workflow_run_id": "test-run",
            "_revision_review": {
                "review_id": 7,
                "score": 58,
                "revision_target": "planner",
                "issues": '["章节指令与世界观冲突"]',
                "suggestions": '["重新规划本章目标"]',
            },
        }

        context = agent.build_context(state)
        assert "章节指令与世界观冲突" in context
        assert "重新规划本章目标" in context

        result = agent.run(state)
        assert result["chapter_status"] == "planned"
        chapter = repo.get_chapter("demo", 1)
        assert chapter["status"] == "planned"
