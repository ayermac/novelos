"""v6.6.12 Chapter Production Result Contract Closure tests.

Tests that chapter production-related API endpoints return domain_result
with correct domain_status semantics.

Core principles:
- HTTP ok=true means request processed, NOT business success
- Business success/failure determined by domain_result.domain_status
- fallback/degraded/partial_success must never display as success
- Memory fallback, review revision, human_review, blocked, failed must have
  clear next_action/action_label
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository


@pytest.fixture()
def contract_client(tmp_path):
    db_path = str(tmp_path / "v6612_contract.db")
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    return TestClient(app), Repository(db_path)


class TestDomainResultContract:
    """Tests for domain_result contract compliance."""

    def test_domain_result_has_required_fields(self):
        """domain_result must have all required fields."""
        from novel_factory.api.contracts import success, failed, blocked, needs_human, partial_success

        # Test success
        result = success("test").to_dict()
        assert "ok" in result
        assert "domain_status" in result
        assert "message" in result
        assert "user_message" in result
        assert "severity" in result
        assert "retryable" in result
        assert "blocking" in result
        assert "flags" in result
        assert "details" in result

        # Test failed
        result = failed("test").to_dict()
        assert result["ok"] is False
        assert result["domain_status"] == "failed"
        assert result["severity"] == "error"

        # Test blocked
        result = blocked("test").to_dict()
        assert result["ok"] is False
        assert result["domain_status"] == "blocked"
        assert result["blocking"] is True

        # Test needs_human
        result = needs_human("test").to_dict()
        assert result["ok"] is False
        assert result["domain_status"] == "needs_human"
        assert result["blocking"] is True

        # Test partial_success
        result = partial_success("test").to_dict()
        assert result["ok"] is True
        assert result["domain_status"] == "partial_success"
        assert result["severity"] == "warning"

    def test_domain_status_never_success_for_degraded_states(self):
        """fallback, degraded, partial_success must never have severity='success'."""
        from novel_factory.api.contracts import fallback, degraded, partial_success

        assert fallback("test").to_dict()["severity"] != "success"
        assert degraded("test").to_dict()["severity"] != "success"
        assert partial_success("test").to_dict()["severity"] != "success"

    def test_next_action_present_for_actionable_states(self):
        """blocked, needs_human, partial_success should have next_action."""
        from novel_factory.api.contracts import blocked, needs_human, partial_success

        result = blocked("test", next_action="reset", action_label="重置").to_dict()
        assert result["next_action"] == "reset"
        assert result["action_label"] == "重置"

        result = needs_human("test", next_action="review", action_label="审核").to_dict()
        assert result["next_action"] == "review"
        assert result["action_label"] == "审核"

        result = partial_success("test", next_action="backfill", action_label="补跑").to_dict()
        assert result["next_action"] == "backfill"
        assert result["action_label"] == "补跑"

    def test_run_chapter_domain_result_helper(self):
        """Test _build_run_chapter_domain_result helper function."""
        from novel_factory.api.routes.run import _build_run_chapter_domain_result

        # Test failed case
        result = _build_run_chapter_domain_result(
            workflow_status="failed",
            chapter_status="planned",
            error="Test error",
            requires_human=False,
            awaiting_publish=False,
            has_trusted_memory=False,
            llm_mode="stub",
            run_id="test-run",
        )
        assert result["domain_status"] == "failed"
        assert result["ok"] is False

        # Test blocked case
        result = _build_run_chapter_domain_result(
            workflow_status="blocked",
            chapter_status="blocking",
            error=None,
            requires_human=False,
            awaiting_publish=False,
            has_trusted_memory=False,
            llm_mode="stub",
            run_id="test-run",
        )
        assert result["domain_status"] == "blocked"
        assert result["blocking"] is True

        # Test revision case
        result = _build_run_chapter_domain_result(
            workflow_status="blocked",
            chapter_status="revision",
            error=None,
            requires_human=True,
            awaiting_publish=False,
            has_trusted_memory=False,
            llm_mode="stub",
            run_id="test-run",
        )
        assert result["domain_status"] == "needs_human"
        assert result["blocking"] is True

        # Test success with trusted memory
        result = _build_run_chapter_domain_result(
            workflow_status="completed",
            chapter_status="awaiting_publish",
            error=None,
            requires_human=False,
            awaiting_publish=True,
            has_trusted_memory=True,
            llm_mode="stub",
            run_id="test-run",
        )
        assert result["domain_status"] == "success"
        assert result["ok"] is True

        # Test partial success without trusted memory
        result = _build_run_chapter_domain_result(
            workflow_status="completed",
            chapter_status="awaiting_publish",
            error=None,
            requires_human=False,
            awaiting_publish=True,
            has_trusted_memory=False,
            llm_mode="stub",
            run_id="test-run",
        )
        assert result["domain_status"] == "partial_success"
        assert result["severity"] == "warning"

    def test_production_next_domain_result_helper(self):
        """Test _build_production_next_domain_result helper function."""
        from novel_factory.api.routes.production import (
            _build_production_next_domain_result,
        )

        # Test ready case
        result = _build_production_next_domain_result(
            health={"has_blocking_chapter": False, "has_stuck_run": False},
            next_action={"key": "generate_chapter", "label": "生成章节"},
            missing=[],
        )
        assert result["domain_status"] == "success"

        # Test blocked case
        result = _build_production_next_domain_result(
            health={"has_blocking_chapter": True, "has_stuck_run": False},
            next_action={"key": "recover_blocked_run", "label": "恢复阻塞"},
            missing=[],
        )
        assert result["domain_status"] == "needs_human"

        # Test missing context case
        result = _build_production_next_domain_result(
            health={"has_blocking_chapter": False, "has_stuck_run": False},
            next_action={"key": "generate_genesis", "label": "生成设定"},
            missing=[{"key": "world_settings", "severity": "blocking"}],
        )
        assert result["domain_status"] == "blocked"

    def test_run_auto_domain_result_helper(self):
        """Test _build_run_auto_domain_result helper function."""
        from novel_factory.api.routes.production import _build_run_auto_domain_result

        # Test completed with chapters
        result = _build_run_auto_domain_result({
            "stop_reason": "completed",
            "steps_executed": 5,
            "chapters_touched": [1, 2, 3],
            "status": "completed",
        })
        assert result["domain_status"] == "success"

        # Test review needed
        result = _build_run_auto_domain_result({
            "stop_reason": "review_needed",
            "steps_executed": 3,
            "chapters_touched": [1],
            "status": "paused",
        })
        assert result["domain_status"] == "needs_human"

        # Test failed
        result = _build_run_auto_domain_result({
            "stop_reason": "failed",
            "steps_executed": 2,
            "chapters_touched": [],
            "status": "failed",
        })
        assert result["domain_status"] == "failed"

        # Test no chapters
        result = _build_run_auto_domain_result({
            "stop_reason": "completed",
            "steps_executed": 1,
            "chapters_touched": [],
            "status": "completed",
        })
        assert result["domain_status"] == "partial_success"


class TestChapterProductionEndpointContract:
    """Endpoint-level regressions for v6.6.12 contract closure."""

    def test_run_chapter_context_incomplete_error_includes_domain_result(self, contract_client):
        client, repo = contract_client
        project_id = "v6612-context-incomplete"
        repo.create_project(project_id=project_id, name="Context Incomplete")
        repo.add_chapter(project_id, 1, title="Ch1", status="planned")

        resp = client.post(
            "/api/run/chapter",
            json={"project_id": project_id, "chapter": 1, "llm_mode": "stub"},
        )
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "CONTEXT_INCOMPLETE"
        domain = body["error"]["details"]["domain_result"]
        assert domain["domain_status"] == "blocked"
        assert domain["severity"] == "error"
        assert domain["next_action"] in {"generate_genesis", "generate_missing_context"}

    def test_run_chapter_terminal_guard_error_includes_domain_result(self, contract_client):
        client, repo = contract_client
        project_id = "v6612-terminal-guard"
        repo.create_project(project_id=project_id, name="Terminal Guard")
        repo.add_chapter(project_id, 1, title="Ch1", status="reviewed")

        resp = client.post(
            "/api/run/chapter",
            json={"project_id": project_id, "chapter": 1, "llm_mode": "stub"},
        )
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "CHAPTER_ALREADY_COMPLETED"
        domain = body["error"]["details"]["domain_result"]
        assert domain["domain_status"] == "blocked"
        assert domain["blocking"] is True
        assert domain["next_action"] == "reset_chapter"

    def test_run_chapter_blocking_guard_error_includes_domain_result(self, contract_client):
        client, repo = contract_client
        project_id = "v6612-blocking-guard"
        repo.create_project(project_id=project_id, name="Blocking Guard")
        repo.add_chapter(project_id, 1, title="Ch1", status="blocking")

        resp = client.post(
            "/api/run/chapter",
            json={"project_id": project_id, "chapter": 1, "llm_mode": "stub"},
        )
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "CHAPTER_NEEDS_RECOVERY"
        domain = body["error"]["details"]["domain_result"]
        assert domain["domain_status"] == "blocked"
        assert domain["blocking"] is True
        assert domain["next_action"] == "reset_chapter"

    def test_local_revision_success_includes_domain_result(self, contract_client):
        client, repo = contract_client
        project_id = "v6612-local-revision-success"
        repo.create_project(project_id=project_id, name="Local Revision")
        content = "这是一段用于局部润色的测试正文。" * 20
        repo.add_chapter(project_id, 1, title="Ch1", status="drafted")
        repo.save_chapter(project_id, 1, "Ch1", content, len(content), "drafted")

        selected = content[:20]
        resp = client.post(
            f"/api/projects/{project_id}/chapters/1/local-revision",
            json={
                "selected_text": selected,
                "selection_start": 0,
                "selection_end": len(selected),
                "instruction": "润色这段文字",
                "mode": "polish",
            },
        )
        body = resp.json()
        assert body["ok"], body.get("error", {}).get("message", "")
        domain = body["data"]["domain_result"]
        assert domain["domain_status"] == "success"
        assert domain["flags"]["local_revision_candidate"] is True

    def test_local_revision_empty_response_error_includes_domain_result(
        self,
        contract_client,
        monkeypatch: pytest.MonkeyPatch,
    ):
        class EmptyReplacementProvider:
            def invoke_json(self, messages, schema=None, **kwargs):  # noqa: ANN001
                return {
                    "replacement_text": "",
                    "change_summary": "",
                    "risk_notes": [],
                }

        class EmptyReplacementRouter:
            def for_agent(self, agent_name: str):  # noqa: ARG002
                return EmptyReplacementProvider()

        def fake_router(settings, llm_mode):  # noqa: ANN001, ARG001
            return EmptyReplacementRouter()

        monkeypatch.setattr("novel_factory.workflow.runner._build_llm_router", fake_router)

        client, repo = contract_client
        project_id = "v6612-local-revision-empty"
        repo.create_project(project_id=project_id, name="Local Revision Empty")
        content = "这是一段用于局部润色的测试正文。" * 20
        repo.add_chapter(project_id, 1, title="Ch1", status="drafted")
        repo.save_chapter(project_id, 1, "Ch1", content, len(content), "drafted")

        selected = content[:20]
        resp = client.post(
            f"/api/projects/{project_id}/chapters/1/local-revision",
            json={
                "selected_text": selected,
                "selection_start": 0,
                "selection_end": len(selected),
                "instruction": "润色这段文字",
                "mode": "polish",
            },
        )
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "REVISION_FAILED"
        domain = body["error"]["details"]["domain_result"]
        assert domain["domain_status"] == "failed"
        assert domain["severity"] == "error"
        assert domain["next_action"] == "retry_local_revision"

    def test_path_style_memory_apply_success_includes_domain_result(self, contract_client):
        client, repo = contract_client
        project_id = "v6612-memory-apply-path"
        repo.create_project(project_id=project_id, name="Memory Apply Path")
        batch = repo.create_memory_batch(project_id, chapter_number=1, summary="可信记忆")
        repo.create_memory_item(
            batch_id=batch["id"],
            project_id=project_id,
            target_table="story_facts",
            operation="create",
            after_json=(
                '{"fact_key":"chapter_1.test_fact","fact_type":"event",'
                '"value":{"text":"test"},"source_chapter":1}'
            ),
            confidence=0.9,
            evidence_text="正文证据",
        )

        resp = client.post(
            f"/api/projects/{project_id}/memory-batches/{batch['id']}/apply"
        )
        body = resp.json()
        assert body["ok"], body.get("error", {}).get("message", "")
        domain = body["data"]["domain_result"]
        assert domain["domain_status"] == "success"
        assert domain["flags"]["memory_applied"] is True

    def test_fallback_memory_apply_error_includes_domain_result(self, contract_client):
        client, repo = contract_client
        project_id = "v6612-memory-apply-fallback"
        repo.create_project(project_id=project_id, name="Memory Apply Fallback")
        batch = repo.create_memory_batch(
            project_id,
            chapter_number=1,
            summary="第1章记忆提取 - 状态卡兜底 (1项)",
        )
        repo.create_memory_item(
            batch_id=batch["id"],
            project_id=project_id,
            target_table="story_facts",
            operation="create",
            after_json='{"fact_key":"chapter_1.fallback"}',
            confidence=0.45,
            evidence_text="",
            rationale="状态卡兜底候选",
        )

        resp = client.post("/api/memory/apply", json={
            "project_id": project_id,
            "batch_id": batch["id"],
        })
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "FALLBACK_MEMORY_REQUIRES_REEXTRACTION"
        domain = body["error"]["details"]["domain_result"]
        assert domain["domain_status"] == "blocked"
        assert domain["next_action"] == "backfill_memory"

    def test_run_auto_step_failed_error_includes_domain_result(
        self,
        contract_client,
        monkeypatch: pytest.MonkeyPatch,
    ):
        async def fake_generator(request, project_id, body):  # noqa: ANN001, ARG001
            yield {
                "event": "step_failed",
                "data": {
                    "project_id": project_id,
                    "step": 1,
                    "action": "generate_chapter",
                    "label": "生成章节",
                    "target_chapter": 1,
                    "result": "failed",
                    "warnings": [],
                    "error": "boom",
                    "chapters_touched": [],
                    "steps_executed": 1,
                },
            }

        monkeypatch.setattr(
            "novel_factory.api.routes.production._auto_run_generator",
            fake_generator,
        )

        client, repo = contract_client
        project_id = "v6612-run-auto-step-failed"
        repo.create_project(project_id=project_id, name="Run Auto Step Failed")

        resp = client.post(f"/api/projects/{project_id}/production/run-auto", json={})
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "AUTO_RUN_STEP_FAILED"
        domain = body["error"]["details"]["domain_result"]
        assert domain["domain_status"] == "failed"
        assert domain["next_action"] == "retry_auto_run_step"

    def test_run_auto_error_event_includes_domain_result(
        self,
        contract_client,
        monkeypatch: pytest.MonkeyPatch,
    ):
        async def fake_generator(request, project_id, body):  # noqa: ANN001, ARG001
            yield {
                "event": "auto_run_error",
                "data": {
                    "project_id": project_id,
                    "error": "INTERNAL_ERROR",
                    "message": "自动生产运行失败: boom",
                },
            }

        monkeypatch.setattr(
            "novel_factory.api.routes.production._auto_run_generator",
            fake_generator,
        )

        client, repo = contract_client
        project_id = "v6612-run-auto-error"
        repo.create_project(project_id=project_id, name="Run Auto Error")

        resp = client.post(f"/api/projects/{project_id}/production/run-auto", json={})
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "INTERNAL_ERROR"
        domain = body["error"]["details"]["domain_result"]
        assert domain["domain_status"] == "failed"
        assert domain["next_action"] == "retry_auto_run"
