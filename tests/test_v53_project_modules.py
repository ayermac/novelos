"""Tests for project-level modules: Style, Review, Runs.

This test file covers:
- StyleGuideModule: style console API
- ReviewModule: blocking/reviewed/published status, publish API
- RunsModule: project-level runs list API
"""

from __future__ import annotations

import tempfile
import pytest
from pathlib import Path

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.api_app import create_api_app
from fastapi.testclient import TestClient


@pytest.fixture
def test_client():
    """Create test client with isolated database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_db(str(db_path))
        app = create_api_app(db_path=str(db_path), llm_mode="stub")
        client = TestClient(app)
        yield client, str(db_path)


class TestStyleGuideModule:
    """Test StyleGuideModule API requirements."""

    def test_style_console_returns_required_fields(self, test_client):
        """Style console should return style_bibles, style_gate_configs, style_samples, and health."""
        client, _ = test_client
        resp = client.get("/api/style/console")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "style_bibles" in data["data"]
        assert "style_gate_configs" in data["data"]
        assert "style_samples" in data["data"]
        assert "health" in data["data"]

    def test_style_init_creates_bible(self, test_client):
        """Style init should create style bible for project."""
        client, db_path = test_client

        # Create project via onboarding API
        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-style-project",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        # Init style bible
        resp = client.post("/api/style/init", json={"project_id": project_id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        # Verify bible appears in console
        resp2 = client.get("/api/style/console")
        assert resp2.status_code == 200
        bibles = resp2.json()["data"]["style_bibles"]
        assert any(b["project_id"] == project_id for b in bibles)


class TestReviewModule:
    """Test ReviewModule API requirements."""

    def test_workspace_includes_recent_runs(self, test_client):
        """Workspace API should include recent_runs for blocking error display."""
        client, db_path = test_client

        # Create project via onboarding API
        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-workspace-project",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        # Get workspace
        resp = client.get(f"/api/projects/{project_id}/workspace")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "recent_runs" in data["data"]

    def test_publish_endpoint_for_reviewed_chapter(self, test_client):
        """Publish API should allow publishing reviewed chapters."""
        client, db_path = test_client
        repo = Repository(db_path)

        # Create project via onboarding API
        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-publish-project",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        # Update chapter to reviewed status via SQL
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE chapters SET status='reviewed', word_count=3000 WHERE project_id=? AND chapter_number=1",
                (project_id,),
            )
            conn.commit()
        finally:
            conn.close()

        # Publish
        resp = client.post("/api/publish/chapter", json={
            "project_id": project_id,
            "chapter": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        # Verify status changed to published
        chapter = repo.get_chapter(project_id, 1)
        assert chapter["status"] == "published"

    def test_publish_endpoint_backfills_memory_before_publish(self, test_client):
        """Manual publish must not skip MemoryCurator when memory evidence is missing."""
        client, db_path = test_client
        repo = Repository(db_path)

        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-publish-memory-project",
            "name": "Test Memory Publish Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        repo.save_chapter_content(
            project_id,
            1,
            "林默夺回账册，并发现账册夹层里藏着铜钥匙。",
            "第一章",
        )
        repo.save_chapter_state(
            project_id,
            1,
            {
                "new_facts": ["林默夺回账册，并发现账册夹层里藏着铜钥匙"],
                "character_status": {"林默": "掌握铜钥匙线索"},
            },
            "第1章状态卡",
        )
        repo.update_chapter_status(project_id, 1, "reviewed")

        resp = client.post("/api/publish/chapter", json={
            "project_id": project_id,
            "chapter": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["chapter_status"] == "published"
        assert data["data"]["memory_curator_processed"] is True
        assert data["data"]["memory_items_count"] >= 2

        batches = repo.list_memory_batches(project_id)
        assert len(batches) == 1
        assert batches[0]["chapter_number"] == 1
        assert batches[0]["status"] == "applied"

    def test_publish_endpoint_does_not_treat_memory_event_as_evidence(self, test_client):
        """A completed memory_curator event without inbox batch must still be backfilled."""
        client, db_path = test_client
        repo = Repository(db_path)

        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-publish-memory-event-only",
            "name": "Test Memory Event Only",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        repo.save_chapter_content(project_id, 1, "林默发现铜钥匙。", "第一章")
        repo.save_chapter_state(project_id, 1, {"new_facts": ["林默发现铜钥匙"]}, "第1章状态卡")
        repo.update_chapter_status(project_id, 1, "reviewed")
        stale_run_id = repo.create_workflow_run(project_id, 1)
        repo.create_workflow_node_event(
            run_id=stale_run_id,
            project_id=project_id,
            chapter_number=1,
            node_name="memory_curator",
            event_type="completed",
            status="completed",
            message="历史节点事件，不代表收件箱批次存在",
        )

        resp = client.post("/api/publish/chapter", json={
            "project_id": project_id,
            "chapter": 1,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["memory_curator_processed"] is True
        assert data["data"]["memory_items_count"] >= 1

        batches = repo.list_memory_batches(project_id)
        assert len(batches) == 1

    def test_publish_endpoint_allows_state_card_fallback_memory_as_partial_success(self, test_client, monkeypatch):
        """Manual publish may proceed with fallback hints, but reports partial success."""
        client, db_path = test_client
        repo = Repository(db_path)

        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-publish-memory-fallback-block",
            "name": "Test Memory Fallback Block",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        repo.save_chapter_content(project_id, 1, "林默发现铜钥匙。", "第一章")
        repo.save_chapter_state(project_id, 1, {"new_facts": ["林默发现铜钥匙"]}, "第1章状态卡")
        repo.update_chapter_status(project_id, 1, "reviewed")

        def fake_run(self, state):
            batch = self.repo.create_memory_batch(
                state["project_id"],
                chapter_number=state["chapter_number"],
                run_id=state["workflow_run_id"],
                summary="第1章记忆提取 - 状态卡兜底 (1项)",
            )
            self.repo.create_memory_item(
                batch_id=batch["id"],
                project_id=state["project_id"],
                target_table="story_facts",
                operation="create",
                after_json='{"fact_key":"chapter_1.key","value":"林默发现铜钥匙"}',
                confidence=0.45,
                evidence_text="林默发现铜钥匙。",
                rationale="状态卡兜底候选：未经过 MemoryCurator LLM 复核，请人工确认后应用",
            )
            return {
                "memory_curator_processed": True,
                "memory_batch_id": batch["id"],
                "memory_items_count": 1,
                "extraction_success": False,
                "fallback_created": True,
                "memory_curator_fallback": "chapter_state",
            }

        monkeypatch.setattr("novel_factory.agents.memory_curator.MemoryCuratorAgent.run", fake_run)

        resp = client.post("/api/publish/chapter", json={
            "project_id": project_id,
            "chapter": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["chapter_status"] == "published"
        assert data["data"]["memory_incomplete"] is True
        assert data["data"]["fallback_created"] is True
        assert data["data"]["domain_result"]["domain_status"] == "partial_success"
        assert data["data"]["domain_result"]["flags"]["memory_trusted"] is False
        assert repo.get_chapter(project_id, 1)["status"] == "published"

    def test_publish_endpoint_skips_existing_memory_batch_without_reextracting(self, test_client, monkeypatch):
        """Manual publish should not rerun MemoryCurator when a memory batch already exists."""
        client, db_path = test_client
        repo = Repository(db_path)

        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-publish-existing-memory-batch",
            "name": "Test Existing Memory Batch Publish",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        repo.save_chapter_content(project_id, 1, "林默发现铜钥匙。", "第一章")
        repo.save_chapter_state(project_id, 1, {"new_facts": ["林默发现铜钥匙"]}, "第1章状态卡")
        repo.update_chapter_status(project_id, 1, "reviewed")

        batch = repo.create_memory_batch(
            project_id,
            chapter_number=1,
            run_id="existing-memory-run",
            summary="第1章记忆提取 - 状态卡兜底 (1项)",
        )
        repo.create_memory_item(
            batch_id=batch["id"],
            project_id=project_id,
            target_table="story_facts",
            operation="create",
            after_json='{"fact_key":"chapter_1.key","value":"林默发现铜钥匙"}',
            confidence=0.45,
            evidence_text="林默发现铜钥匙。",
            rationale="状态卡兜底候选：未经过 MemoryCurator LLM 复核，请人工确认后应用",
        )

        def fail_if_called(self, state):
            raise AssertionError("publish should not rerun MemoryCurator when a memory batch already exists")

        monkeypatch.setattr("novel_factory.agents.memory_curator.MemoryCuratorAgent.run", fail_if_called)

        resp = client.post("/api/publish/chapter", json={
            "project_id": project_id,
            "chapter": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["chapter_status"] == "published"
        assert data["data"]["memory_curator_processed"] is False
        assert data["data"]["memory_curator_skipped"] is True
        assert data["data"]["domain_result"]["domain_status"] == "partial_success"
        assert data["data"]["domain_result"]["flags"]["memory_trusted"] is False
        assert len(repo.list_memory_batches(project_id)) == 1

    def test_run_detail_memory_backfill_endpoint(self, test_client):
        """Run detail page can backfill MemoryCurator for an already published chapter."""
        client, db_path = test_client
        repo = Repository(db_path)

        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-run-memory-backfill",
            "name": "Test Run Memory Backfill",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        repo.save_chapter_content(
            project_id,
            1,
            "林默夺回账册，并发现账册夹层里藏着铜钥匙。",
            "第一章",
        )
        repo.save_chapter_state(
            project_id,
            1,
            {"new_facts": ["林默夺回账册，并发现账册夹层里藏着铜钥匙"]},
            "第1章状态卡",
        )
        repo.update_chapter_status(project_id, 1, "published")
        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="completed", current_node="publisher")
        repo.create_workflow_node_event(
            run_id=run_id,
            project_id=project_id,
            chapter_number=1,
            node_name="memory_curator",
            event_type="completed",
            status="completed",
            message="历史运行显示记忆整理完成但未创建收件箱批次",
        )

        resp = client.post(f"/api/runs/{run_id}/memory/backfill", json={"confirm": True})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["skipped"] is False
        assert data["data"]["memory_items_count"] >= 1

        batches = repo.list_memory_batches(project_id)
        assert len(batches) == 1
        assert batches[0]["chapter_number"] == 1

    def test_memory_backfill_releases_source_timeout_lock(self, test_client):
        """A timed-out MemoryCurator run should not leave a lock that blocks manual backfill."""
        client, db_path = test_client
        repo = Repository(db_path)

        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-memory-timeout-lock-release",
            "name": "Test Memory Timeout Lock Release",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        repo.save_chapter_content(project_id, 1, "林默夺回账册，并发现账册夹层里藏着铜钥匙。", "第一章")
        repo.save_chapter_state(
            project_id,
            1,
            {"new_facts": ["林默夺回账册，并发现账册夹层里藏着铜钥匙"]},
            "第1章状态卡",
        )
        repo.update_chapter_status(project_id, 1, "reviewed")
        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(
            run_id,
            status="blocked",
            current_node="memory_curator",
            error_message="节点 memory_curator 执行超时（>600秒）",
        )
        lock_result = repo.acquire_memory_curator_lock(project_id, 1, run_id=run_id)
        assert lock_result["acquired"] is True

        resp = client.post(f"/api/runs/{run_id}/memory/backfill", json={"confirm": True})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["skipped"] is False
        assert data["data"]["memory_items_count"] >= 1
        assert repo.get_memory_curator_lock(project_id, 1) is None

    def test_run_detail_memory_backfill_returns_error_for_state_card_fallback(self, test_client, monkeypatch):
        """Run detail backfill should report fallback as incomplete, not success."""
        client, db_path = test_client
        repo = Repository(db_path)

        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-run-memory-fallback-error",
            "name": "Test Backfill Fallback Error",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]
        repo.save_chapter_content(project_id, 1, "林默发现铜钥匙。", "第一章")
        repo.save_chapter_state(project_id, 1, {"new_facts": ["林默发现铜钥匙"]}, "第1章状态卡")
        repo.update_chapter_status(project_id, 1, "published")
        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="completed", current_node="publisher")

        def fake_run(self, state):
            batch = self.repo.create_memory_batch(
                state["project_id"],
                chapter_number=state["chapter_number"],
                run_id=state["workflow_run_id"],
                summary="第1章记忆提取 - 状态卡兜底 (1项)",
            )
            self.repo.create_memory_item(
                batch_id=batch["id"],
                project_id=state["project_id"],
                target_table="story_facts",
                operation="create",
                after_json='{"fact_key":"chapter_1.key","value":"林默发现铜钥匙"}',
                confidence=0.45,
                evidence_text="林默发现铜钥匙。",
                rationale="状态卡兜底候选：未经过 MemoryCurator LLM 复核，请人工确认后应用",
            )
            return {
                "memory_curator_processed": True,
                "memory_batch_id": batch["id"],
                "memory_items_count": 1,
                "extraction_success": False,
                "fallback_created": True,
                "memory_curator_fallback": "chapter_state",
            }

        monkeypatch.setattr("novel_factory.agents.memory_curator.MemoryCuratorAgent.run", fake_run)

        resp = client.post(f"/api/runs/{run_id}/memory/backfill", json={"confirm": True})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "MEMORY_CURATOR_INCOMPLETE"
        assert data["error"]["details"]["memory_batch_id"]

    def test_run_detail_memory_backfill_does_not_skip_state_card_fallback(self, test_client):
        """A state-card fallback batch is only a hint and should not block real re-extraction."""
        client, db_path = test_client
        repo = Repository(db_path)

        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-run-memory-fallback-existing",
            "name": "Test Existing Fallback",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        repo.save_chapter_content(project_id, 1, "林默发现铜钥匙。", "第一章")
        repo.save_chapter_state(project_id, 1, {"new_facts": ["林默发现铜钥匙"]}, "第1章状态卡")
        repo.update_chapter_status(project_id, 1, "published")
        repo.create_memory_batch(project_id, chapter_number=1, summary="第1章记忆提取 - 状态卡兜底 (1项)")
        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="completed", current_node="publisher")

        resp = client.post(f"/api/runs/{run_id}/memory/backfill", json={"confirm": True})

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["skipped"] is False
        assert data["data"]["memory_items_count"] >= 1

    def test_run_detail_memory_backfill_uses_memory_curator_llm_route(self, monkeypatch):
        """Memory backfill should honor agent_llm.memory_curator instead of generic default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config_path = Path(tmpdir) / "config.yaml"
            init_db(str(db_path))
            config_path.write_text(
                """
db_path: "{db_path}"
default_llm: default
llm_profiles:
  default:
    provider: openai_compatible
    base_url: http://default.invalid/v1
    api_key: default-key
    model: wrong-default-model
  memory:
    provider: openai_compatible
    base_url: http://memory.invalid/v1
    api_key: memory-key
    model: memory-route-model
agent_llm:
  memory_curator: memory
""".format(db_path=str(db_path)),
                encoding="utf-8",
            )
            app = create_api_app(
                db_path=str(db_path),
                config_path=str(config_path),
                llm_mode="real",
            )
            client = TestClient(app)
            repo = Repository(str(db_path))
            seen: dict[str, str] = {}

            def fake_run(self, state):
                seen["model"] = getattr(getattr(self.llm, "config", None), "model", "")
                seen["base_url"] = getattr(getattr(self.llm, "config", None), "base_url", "")
                batch = self.repo.create_memory_batch(
                    state["project_id"],
                    chapter_number=state["chapter_number"],
                    run_id=state["workflow_run_id"],
                    summary="第1章记忆提取 (1项)",
                )
                self.repo.create_memory_item(
                    batch_id=batch["id"],
                    project_id=state["project_id"],
                    target_table="story_facts",
                    operation="create",
                    after_json='{"fact_key":"chapter_1.key","value":"林默发现铜钥匙"}',
                    confidence=0.92,
                    evidence_text="林默发现铜钥匙。",
                    rationale="MemoryCurator LLM 正文复核提取",
                )
                return {
                    "memory_batch_id": batch["id"],
                    "memory_items_count": 1,
                    "extraction_success": True,
                    "memory_curator_degraded": False,
                }

            monkeypatch.setattr("novel_factory.agents.memory_curator.MemoryCuratorAgent.run", fake_run)

            resp = client.post("/api/onboarding/projects", json={
                "project_id": "test-memory-route",
                "name": "Test Memory Route",
                "genre": "fantasy",
                "target_words": 100000,
                "total_chapters_planned": 50,
            })
            assert resp.status_code == 200
            project_id = resp.json()["data"]["project"]["project_id"]
            repo.save_chapter_content(project_id, 1, "林默发现铜钥匙。", "第一章")
            repo.update_chapter_status(project_id, 1, "published")
            run_id = repo.create_workflow_run(project_id, 1)
            repo.update_workflow_run(run_id, status="completed", current_node="publisher")

            resp = client.post(f"/api/runs/{run_id}/memory/backfill", json={"confirm": True})
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert data["data"]["skipped"] is False
            assert data["data"]["memory_batch_id"]
            assert seen["model"] == "memory-route-model"
            assert seen["base_url"] == "http://memory.invalid/v1"

    def test_publish_memory_backfill_uses_memory_curator_fallback_route(self, monkeypatch):
        """Manual publish memory extraction should pass agent_llm_fallback to MemoryCurator."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config_path = Path(tmpdir) / "config.yaml"
            init_db(str(db_path))
            config_path.write_text(
                """
db_path: "{db_path}"
default_llm: default
llm_profiles:
  default:
    provider: openai_compatible
    base_url: http://default.invalid/v1
    api_key: default-key
    model: wrong-default-model
  memory:
    provider: openai_compatible
    base_url: http://memory.invalid/v1
    api_key: memory-key
    model: memory-route-model
  fast:
    provider: openai_compatible
    base_url: http://fast.invalid/v1
    api_key: fast-key
    model: memory-fallback-model
agent_llm:
  memory_curator: memory
agent_llm_fallback:
  memory_curator: fast
""".format(db_path=str(db_path)),
                encoding="utf-8",
            )
            app = create_api_app(
                db_path=str(db_path),
                config_path=str(config_path),
                llm_mode="real",
            )
            client = TestClient(app)
            repo = Repository(str(db_path))
            seen: dict[str, str] = {}

            def fake_run(self, state):
                seen["primary_model"] = getattr(getattr(self.llm, "config", None), "model", "")
                seen["fallback_model"] = getattr(getattr(self.fallback_llm, "config", None), "model", "")
                batch = self.repo.create_memory_batch(
                    state["project_id"],
                    chapter_number=state["chapter_number"],
                    run_id=state["workflow_run_id"],
                    summary="第1章记忆提取 (1项)",
                )
                self.repo.create_memory_item(
                    batch_id=batch["id"],
                    project_id=state["project_id"],
                    target_table="story_facts",
                    operation="create",
                    after_json='{"fact_key":"chapter_1.key","value":"林默发现铜钥匙"}',
                    confidence=0.92,
                    evidence_text="林默发现铜钥匙。",
                    rationale="MemoryCurator LLM 正文复核提取",
                )
                return {
                    "memory_batch_id": batch["id"],
                    "memory_items_count": 1,
                    "extraction_success": True,
                    "memory_curator_degraded": False,
                }

            monkeypatch.setattr("novel_factory.agents.memory_curator.MemoryCuratorAgent.run", fake_run)

            resp = client.post("/api/onboarding/projects", json={
                "project_id": "test-publish-memory-fallback-route",
                "name": "Test Publish Memory Fallback Route",
                "genre": "fantasy",
                "target_words": 100000,
                "total_chapters_planned": 50,
            })
            assert resp.status_code == 200
            project_id = resp.json()["data"]["project"]["project_id"]
            repo.save_chapter_content(project_id, 1, "林默发现铜钥匙。", "第一章")
            repo.update_chapter_status(project_id, 1, "reviewed")

            resp = client.post("/api/publish/chapter", json={"project_id": project_id, "chapter": 1})
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert seen["primary_model"] == "memory-route-model"
            assert seen["fallback_model"] == "memory-fallback-model"

    def test_run_recovery_survives_missing_config_file(self):
        """Run detail recovery should not fail just because the settings file moved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            init_db(str(db_path))
            app = create_api_app(
                db_path=str(db_path),
                config_path=str(Path(tmpdir) / "missing-local.yaml"),
                llm_mode="real",
            )
            client = TestClient(app)
            repo = Repository(str(db_path))
            repo.create_project(project_id="test-recovery-missing-config", name="Missing Config")
            repo.add_chapter("test-recovery-missing-config", 1, title="第一章", status="reviewed")
            run_id = repo.create_workflow_run("test-recovery-missing-config", 1)
            repo.update_workflow_run(run_id, status="completed", current_node="memory_curator")

            resp = client.get(f"/api/runs/{run_id}/recovery")

            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert data["data"]["timeout_minutes"] == 30

    def test_run_recovery_uses_active_node_age_not_total_run_age(self, test_client):
        """A long run should not be marked stuck when the current node just started."""
        client, db_path = test_client
        repo = Repository(db_path)

        project_id = "test-active-node-age"
        repo.create_project(project_id=project_id, name="Active Node Age")
        repo.add_chapter(project_id, 1, title="第一章", status="polished")
        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="running", current_node="editor")
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE workflow_runs SET started_at=datetime('now','-45 minutes','+8 hours') WHERE id=?",
                (run_id,),
            )
            conn.commit()
        finally:
            conn.close()
        repo.create_workflow_node_event(
            run_id=run_id,
            project_id=project_id,
            chapter_number=1,
            node_name="screenwriter",
            event_type="started",
            status="running",
        )
        repo.create_workflow_node_event(
            run_id=run_id,
            project_id=project_id,
            chapter_number=1,
            node_name="screenwriter",
            event_type="completed",
            status="completed",
        )
        repo.create_workflow_node_event(
            run_id=run_id,
            project_id=project_id,
            chapter_number=1,
            node_name="editor",
            event_type="started",
            status="running",
        )

        resp = client.get(f"/api/runs/{run_id}/recovery")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["elapsed_minutes"] >= 30
        assert data["stuck"] is False
        assert data["actions"]["mark_stuck_blocked"]["enabled"] is False
        assert data["recovery_state"]["recommended_action"] is None

    def test_run_recovery_marks_active_node_stuck_after_node_timeout(self, test_client):
        """A stale active node should still expose mark-stuck recovery."""
        client, db_path = test_client
        repo = Repository(db_path)

        project_id = "test-active-node-stale"
        repo.create_project(project_id=project_id, name="Active Node Stale")
        repo.add_chapter(project_id, 1, title="第一章", status="polished")
        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="running", current_node="editor")
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE workflow_runs SET started_at=datetime('now','-45 minutes','+8 hours') WHERE id=?",
                (run_id,),
            )
            conn.commit()
        finally:
            conn.close()
        repo.create_workflow_node_event(
            run_id=run_id,
            project_id=project_id,
            chapter_number=1,
            node_name="editor",
            event_type="started",
            status="running",
        )
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE workflow_node_events SET created_at=datetime('now','-35 minutes','+8 hours') "
                "WHERE run_id=? AND node_name='editor'",
                (run_id,),
            )
            conn.commit()
        finally:
            conn.close()

        resp = client.get(f"/api/runs/{run_id}/recovery")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["stuck"] is True
        assert data["active_node_elapsed_minutes"] >= 30
        assert data["actions"]["mark_stuck_blocked"]["enabled"] is True

    def test_run_detail_does_not_reconcile_memory_backfill_to_awaiting_publish(self, test_client):
        """Memory backfill runs must stay on memory_curator even when chapter is terminal."""
        client, db_path = test_client
        repo = Repository(db_path)

        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-memory-backfill-not-main-workflow",
            "name": "Test Memory Backfill Isolation",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]
        repo.update_chapter_status(project_id, 1, "reviewed")
        run_id = repo.create_workflow_run(project_id, 1, graph_name="memory_backfill")
        repo.update_workflow_run(run_id, status="running", current_node="memory_curator")

        resp = client.get(f"/api/runs/{run_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["workflow_status"] == "running"
        assert data["data"]["current_node"] == "memory_curator"
        persisted = repo.get_workflow_runs_for_project(project_id, chapter_number=1, limit=5)[0]
        assert persisted["status"] == "running"
        assert persisted["current_node"] == "memory_curator"

    def test_run_detail_memory_backfill_uses_memory_step_timeline(self, test_client):
        """Memory backfill details should not display chapter-production steps."""
        client, db_path = test_client
        repo = Repository(db_path)

        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-memory-backfill-step-timeline",
            "name": "Test Memory Step Timeline",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]
        repo.update_chapter_status(project_id, 1, "reviewed")
        run_id = repo.create_workflow_run(project_id, 1, graph_name="memory_backfill")
        repo.update_workflow_run(run_id, status="completed", current_node="memory_curator")
        repo.create_workflow_node_event(
            run_id=run_id,
            project_id=project_id,
            chapter_number=1,
            node_name="memory_curator",
            event_type="completed",
            status="completed",
            message="运行详情页手动补跑记忆提取完成",
        )

        resp = client.get(f"/api/runs/{run_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert [step["key"] for step in data["data"]["steps"]] == ["memory_curator"]
        assert data["data"]["steps"][0]["status"] == "completed"

    def test_run_detail_memory_backfill_warning_event_is_not_success_log(self, test_client):
        """Warning completion for untrusted memory should remain warning in run detail logs."""
        client, db_path = test_client
        repo = Repository(db_path)

        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-memory-backfill-warning-log",
            "name": "Test Memory Warning Log",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]
        repo.update_chapter_status(project_id, 1, "reviewed")
        run_id = repo.create_workflow_run(project_id, 1, graph_name="memory_backfill")
        repo.update_workflow_run(
            run_id,
            status="failed",
            current_node="memory_curator",
            error_message="记忆提取未成功：没有生成可信记忆批次。",
        )
        repo.create_workflow_node_event(
            run_id=run_id,
            project_id=project_id,
            chapter_number=1,
            node_name="memory_curator",
            event_type="completed",
            status="warning",
            message="运行详情页手动补跑未成功，未生成可信记忆批次",
        )

        resp = client.get(f"/api/runs/{run_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        step = data["data"]["steps"][0]
        assert step["status"] == "failed"
        assert step["logs"][0]["level"] == "warning"

    def test_reset_blocking_chapter(self, test_client):
        """Reset API should allow resetting blocking chapters."""
        client, db_path = test_client
        repo = Repository(db_path)

        # Create project via onboarding API
        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-reset-project",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        # Update chapter to blocking status via SQL
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE chapters SET status='blocking' WHERE project_id=? AND chapter_number=1",
                (project_id,),
            )
            conn.commit()
        finally:
            conn.close()

        # Reset
        resp = client.post(f"/api/projects/{project_id}/chapters/1/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        # Verify status changed to planned
        chapter = repo.get_chapter(project_id, 1)
        assert chapter["status"] == "planned"


class TestRunsModule:
    """Test RunsModule API requirements."""

    def test_project_runs_list(self, test_client):
        """Project runs API should return list of runs with required fields."""
        client, db_path = test_client
        repo = Repository(db_path)

        # Create project via onboarding API
        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-runs-project",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        # Create a workflow run
        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(
            run_id,
            status="completed",
            prompt_tokens=1000,
            completion_tokens=2000,
            total_tokens=3000,
            duration_ms=5000,
        )

        # Get project runs
        resp = client.get(f"/api/projects/{project_id}/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 1

        # Check required fields
        run = data["data"][0]
        assert "run_id" in run or "id" in run
        assert "chapter_number" in run
        assert "status" in run
        assert "total_tokens" in run
        assert "duration_ms" in run

    def test_run_detail_includes_steps_and_artifacts(self, test_client):
        """Run detail API should include steps with artifacts."""
        client, db_path = test_client
        repo = Repository(db_path)

        # Create project via onboarding API
        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-steps-project",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        # Update chapter to published status via SQL
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE chapters SET status='published', word_count=3000 WHERE project_id=? AND chapter_number=1",
                (project_id,),
            )
            conn.commit()
        finally:
            conn.close()

        # Create run
        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="completed")

        # Get run detail
        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        # Check steps
        assert "steps" in data["data"]
        steps = data["data"]["steps"]
        assert len(steps) >= 1

        # Each step should have key, label, status
        for step in steps:
            assert "key" in step
            assert "label" in step
            assert "status" in step

    def test_run_detail_includes_error_message(self, test_client):
        """Run detail API should include error_message for failed runs."""
        client, db_path = test_client
        repo = Repository(db_path)

        # Create project via onboarding API
        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-error-project",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        # Update chapter to blocking status via SQL
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE chapters SET status='blocking' WHERE project_id=? AND chapter_number=1",
                (project_id,),
            )
            conn.commit()
        finally:
            conn.close()

        # Create failed run
        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="failed", error_message="Test error message")

        # Get run detail
        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "error_message" in data["data"]
        assert data["data"]["error_message"] == "Test error message"

    def test_run_detail_explains_empty_blocked_run(self, test_client):
        """Blocked run detail should explain already-blocked chapters even for legacy empty errors."""
        client, db_path = test_client
        repo = Repository(db_path)

        resp = client.post("/api/onboarding/projects", json={
            "project_id": "test-empty-blocked-run",
            "name": "Test Project",
            "genre": "fantasy",
            "target_words": 100000,
            "total_chapters_planned": 50,
        })
        assert resp.status_code == 200
        project_id = resp.json()["data"]["project"]["project_id"]

        previous_run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(
            previous_run_id,
            status="blocked",
            current_node="human_review",
            error_message="LLM provider overloaded",
        )

        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE chapters SET status='blocking' WHERE project_id=? AND chapter_number=1",
                (project_id,),
            )
            conn.commit()
        finally:
            conn.close()

        run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(run_id, status="blocked", current_node="human_review")

        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "已处于阻塞状态" in data["data"]["error_message"]
        assert "LLM provider overloaded" in data["data"]["error_message"]
        blocked_steps = [s for s in data["data"]["steps"] if s["status"] == "blocked"]
        assert blocked_steps
        assert "已处于阻塞状态" in blocked_steps[0]["error_message"]
