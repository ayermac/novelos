"""Tests for v6.6.11 Workflow Timeline & Node Semantics Closure.

Covers:
- NodeOperationResult contract structure and JSON safety
- node_success / node_warning / node_failed / node_blocked / node_skipped helpers
- node_from_operation_result mapping
- memory_curator_node_result for all memory states
- memory_curator trusted → succeeded/success
- memory_curator fallback → warning/fallback
- memory_curator degraded → warning/degraded
- memory_curator failed event → failed/failed
- awaiting_publish + fallback → workflow partial_success + node warning
- completed event but no trusted memory → node warning, not succeeded
- skipped node → skipped/ignored
- Response does not leak sensitive info / API key / token
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from novel_factory.api_app import create_api_app
from novel_factory.api.contracts import (
    NodeOperationResult,
    OperationResult,
    success,
    partial_success,
    fallback,
    degraded,
    failed,
    blocked,
    node_success,
    node_warning,
    node_failed,
    node_blocked,
    node_skipped,
    node_from_operation_result,
    memory_curator_node_result,
    memory_status_to_domain_result,
    workflow_run_to_domain_status,
    _SENSITIVE_KEYS,
)
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository


# ── NodeOperationResult contract structure ───────────────────────────


class TestNodeOperationResultStructure:
    """Verify NodeOperationResult produces stable, JSON-serializable output."""

    def test_node_success_structure(self):
        r = node_success("planner", "规划完成")
        assert r.node_name == "planner"
        assert r.node_status == "succeeded"
        assert r.domain_status == "success"
        assert r.severity == "success"
        assert r.retryable is False
        assert r.blocking is False
        d = r.to_dict()
        assert isinstance(d, dict)
        json.dumps(d)  # must be JSON-serializable

    def test_node_warning_structure(self):
        r = node_warning("memory_curator", "记忆降级", domain_status="fallback")
        assert r.node_name == "memory_curator"
        assert r.node_status == "warning"
        assert r.domain_status == "fallback"
        assert r.severity == "warning"
        assert r.retryable is True
        d = r.to_dict()
        json.dumps(d)

    def test_node_failed_structure(self):
        r = node_failed("editor", "审核失败", retryable=True)
        assert r.node_name == "editor"
        assert r.node_status == "failed"
        assert r.domain_status == "failed"
        assert r.severity == "error"
        assert r.retryable is True
        d = r.to_dict()
        json.dumps(d)

    def test_node_blocked_structure(self):
        r = node_blocked("author", "节点阻塞", next_action="retry_node")
        assert r.node_name == "author"
        assert r.node_status == "blocked"
        assert r.domain_status == "blocked"
        assert r.severity == "error"
        assert r.blocking is True
        assert r.retryable is False
        d = r.to_dict()
        json.dumps(d)

    def test_node_skipped_structure(self):
        r = node_skipped("planner", "规划已跳过")
        assert r.node_name == "planner"
        assert r.node_status == "skipped"
        assert r.domain_status == "ignored"
        assert r.severity == "info"
        d = r.to_dict()
        json.dumps(d)

    def test_user_message_defaults_to_message(self):
        r = node_success("test", "内部消息")
        assert r.user_message == "内部消息"

    def test_user_message_can_be_overridden(self):
        r = node_warning("test", "内部", user_message="用户消息")
        assert r.user_message == "用户消息"
        assert r.message == "内部"


# ── node_from_operation_result mapping ───────────────────────────────


class TestNodeFromOperationResult:
    """Verify OperationResult → NodeOperationResult mapping."""

    def test_success_maps_to_succeeded(self):
        op = success("ok")
        r = node_from_operation_result("planner", op)
        assert r.node_status == "succeeded"
        assert r.domain_status == "success"

    def test_fallback_maps_to_warning(self):
        op = fallback("fb")
        r = node_from_operation_result("memory_curator", op)
        assert r.node_status == "warning"
        assert r.domain_status == "fallback"

    def test_degraded_maps_to_warning(self):
        op = degraded("degraded")
        r = node_from_operation_result("memory_curator", op)
        assert r.node_status == "warning"
        assert r.domain_status == "degraded"

    def test_partial_success_maps_to_warning(self):
        op = partial_success("partial")
        r = node_from_operation_result("memory_curator", op)
        assert r.node_status == "warning"
        assert r.domain_status == "partial_success"

    def test_failed_maps_to_failed(self):
        op = failed("err")
        r = node_from_operation_result("editor", op)
        assert r.node_status == "failed"
        assert r.domain_status == "failed"

    def test_blocked_maps_to_blocked(self):
        op = blocked("blocked")
        r = node_from_operation_result("author", op)
        assert r.node_status == "blocked"
        assert r.domain_status == "blocked"

    def test_needs_human_maps_to_blocked(self):
        op = OperationResult(
            ok=False, domain_status="needs_human", message="human needed",
            blocking=True, retryable=True, severity="warning",
        )
        r = node_from_operation_result("editor", op)
        assert r.node_status == "blocked"
        assert r.domain_status == "needs_human"

    def test_ignored_maps_to_skipped(self):
        op = OperationResult(
            ok=True, domain_status="ignored", message="skipped", severity="info",
        )
        r = node_from_operation_result("planner", op)
        assert r.node_status == "skipped"
        assert r.domain_status == "ignored"

    def test_pending_maps_to_running(self):
        op = OperationResult(
            ok=True, domain_status="pending", message="running", severity="info",
        )
        r = node_from_operation_result("author", op)
        assert r.node_status == "running"
        assert r.domain_status == "pending"

    def test_preserves_flags_and_details(self):
        op = fallback("fb", flags={"memory_fallback": True}, details={"batch_count": 2})
        r = node_from_operation_result("memory_curator", op)
        assert r.flags.get("memory_fallback") is True
        assert r.details.get("batch_count") == 2


# ── memory_curator_node_result mapping ──────────────────────────────


class TestMemoryCuratorNodeResult:
    """Verify memory_curator node status derivation for all states."""

    def test_trusted_extraction_is_succeeded_success(self):
        r = memory_curator_node_result(
            "trusted", event_status="completed",
            batch_count=1, trusted_batch_count=1,
        )
        assert r.node_status == "succeeded"
        assert r.domain_status == "success"
        assert r.severity == "success"
        assert r.flags.get("memory_trusted") is True

    def test_fallback_candidate_is_warning_fallback(self):
        r = memory_curator_node_result(
            "fallback", event_status="completed",
            batch_count=1, fallback_batch_count=1,
        )
        assert r.node_status == "warning"
        assert r.domain_status == "fallback"
        assert r.severity == "warning"
        assert r.flags.get("memory_trusted") is False
        assert r.flags.get("memory_fallback") is True
        assert r.retryable is True
        assert r.next_action == "backfill_memory"

    def test_degraded_noop_is_warning_degraded(self):
        r = memory_curator_node_result(
            "degraded", event_status="completed",
        )
        assert r.node_status == "warning"
        assert r.domain_status == "degraded"
        assert r.severity == "warning"
        assert r.flags.get("memory_degraded") is True

    def test_failed_no_memory_is_failed(self):
        r = memory_curator_node_result(
            "failed", event_status="completed",
        )
        assert r.node_status == "failed"
        assert r.domain_status == "failed"
        assert r.severity == "error"
        assert r.flags.get("memory_failed") is True

    def test_failed_event_is_failed(self):
        r = memory_curator_node_result(
            "fallback", event_status="failed",
            has_error=True, error_message="LLM timeout",
        )
        assert r.node_status == "failed"
        assert r.domain_status == "failed"
        assert r.severity == "error"

    def test_skipped_is_skipped_ignored(self):
        r = memory_curator_node_result("skipped", event_status="skipped")
        assert r.node_status == "skipped"
        assert r.domain_status == "ignored"
        assert r.severity == "info"

    def test_running_is_running_pending(self):
        r = memory_curator_node_result("unknown", event_status="running")
        assert r.node_status == "running"
        assert r.domain_status == "pending"
        assert r.severity == "info"

    def test_missing_is_warning_degraded(self):
        r = memory_curator_node_result("missing")
        assert r.node_status == "warning"
        assert r.domain_status == "degraded"
        assert r.severity == "warning"

    def test_completed_but_no_trusted_memory_is_warning_not_succeeded(self):
        """Critical: completed event but 0 trusted batches → warning, NOT succeeded."""
        r = memory_curator_node_result(
            "fallback", event_status="completed",
            batch_count=1, trusted_batch_count=0, fallback_batch_count=1,
        )
        assert r.node_status == "warning"
        assert r.domain_status == "fallback"
        # Must NOT be succeeded
        assert r.node_status != "succeeded"

    def test_completed_event_missing_memory_is_warning_not_succeeded(self):
        """Even completed event with missing memory → warning degraded, not succeeded."""
        r = memory_curator_node_result(
            "missing", event_status="completed",
        )
        assert r.node_status == "warning"
        assert r.domain_status == "degraded"
        assert r.node_status != "succeeded"

    def test_memory_status_running_overrides(self):
        r = memory_curator_node_result("running")
        assert r.node_status == "running"
        assert r.domain_status == "pending"


# ── Workflow + memory interaction (awaiting_publish + fallback) ──────


class TestWorkflowMemoryInteraction:
    """Verify workflow-level and node-level status interact correctly."""

    def test_awaiting_publish_with_fallback_memory(self):
        """Chapter awaiting_publish + memory fallback → workflow partial_success,
        but memory_curator node must be warning."""
        # Workflow level
        wf_result = workflow_run_to_domain_status(
            "completed", "awaiting_publish",
            memory_status={
                "memory_trusted": False,
                "memory_status": "fallback",
                "batch_count": 1,
                "trusted_batch_count": 0,
                "fallback_batch_count": 1,
            },
        )
        assert wf_result.domain_status == "partial_success"

        # Node level
        mc_node = memory_curator_node_result(
            "fallback", event_status="completed",
            batch_count=1, fallback_batch_count=1,
        )
        assert mc_node.node_status == "warning"
        assert mc_node.domain_status == "fallback"

    def test_awaiting_publish_with_trusted_memory(self):
        wf_result = workflow_run_to_domain_status(
            "completed", "awaiting_publish",
            memory_status={
                "memory_trusted": True,
                "memory_status": "trusted",
                "batch_count": 1,
                "trusted_batch_count": 1,
                "fallback_batch_count": 0,
            },
        )
        assert wf_result.domain_status == "success"

        mc_node = memory_curator_node_result(
            "trusted", event_status="completed",
            batch_count=1, trusted_batch_count=1,
        )
        assert mc_node.node_status == "succeeded"


# ── Sensitive data scrubbing ────────────────────────────────────────


class TestNodeOperationResultSensitiveData:
    """Verify NodeOperationResult.to_dict() does not leak sensitive data."""

    def test_scrubs_api_key_in_details(self):
        r = node_success("test", "ok", details={"OPENAI_API_KEY": "sk-12345"})
        d = r.to_dict()
        assert d["details"]["OPENAI_API_KEY"] == "[REDACTED]"

    def test_scrubs_base_url_in_details(self):
        r = node_warning("test", "warn", details={"OPENAI_BASE_URL": "https://api.example.com"})
        d = r.to_dict()
        assert d["details"]["OPENAI_BASE_URL"] == "[REDACTED]"

    def test_scrubs_nested_content(self):
        r = node_success("test", "ok", details={
            "chapter": {"content": "full chapter text", "word_count": 3000}
        })
        d = r.to_dict()
        assert d["details"]["chapter"]["content"] == "[REDACTED]"
        assert d["details"]["chapter"]["word_count"] == 3000

    def test_scrubs_token_in_details(self):
        r = node_failed("test", "err", details={"token": "secret-token"})
        d = r.to_dict()
        assert d["details"]["token"] == "[REDACTED]"

    def test_all_sensitive_keys_scrubbed(self):
        for key in _SENSITIVE_KEYS:
            r = node_success("test", "ok", details={key: "leak-value"})
            d = r.to_dict()
            assert d["details"][key] == "[REDACTED]", f"Sensitive key '{key}' not scrubbed"


# ── JSON roundtrip ──────────────────────────────────────────────────


class TestNodeOperationResultJsonRoundtrip:
    """Verify NodeOperationResult can be serialized and deserialized."""

    def test_roundtrip_node_success(self):
        r = node_success("planner", "规划完成", user_message="规划节点成功")
        d = r.to_dict()
        json_str = json.dumps(d, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["node_status"] == "succeeded"
        assert parsed["domain_status"] == "success"
        assert parsed["user_message"] == "规划节点成功"

    def test_roundtrip_node_warning(self):
        r = node_warning(
            "memory_curator", "记忆降级",
            domain_status="fallback",
            user_message="记忆未可信",
            next_action="backfill_memory",
            action_label="补跑记忆",
            details={"batch_count": 3},
            flags={"memory_fallback": True},
        )
        d = r.to_dict()
        json_str = json.dumps(d, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["node_status"] == "warning"
        assert parsed["domain_status"] == "fallback"
        assert parsed["next_action"] == "backfill_memory"
        assert parsed["details"]["batch_count"] == 3

    def test_all_node_statuses_serializable(self):
        helpers = [node_success, node_warning, node_failed, node_blocked, node_skipped]
        for helper in helpers:
            r = helper("test", "test message")
            d = r.to_dict()
            json_str = json.dumps(d, ensure_ascii=False)
            parsed = json.loads(json_str)
            assert "node_status" in parsed
            assert "domain_status" in parsed
            assert "severity" in parsed


# ── Workflow timeline API run isolation ───────────────────────────────


def _make_timeline_client(tmp_path):
    db_path = str(tmp_path / "v6611_timeline.db")
    init_db(db_path)
    app = create_api_app(db_path=db_path, llm_mode="stub")
    return TestClient(app), Repository(db_path)


class TestWorkflowTimelineMemoryRunIsolation:
    """Verify timeline memory semantics are isolated by workflow run_id."""

    def test_old_fallback_run_not_green_after_later_trusted_backfill(self, tmp_path):
        client, repo = _make_timeline_client(tmp_path)
        project_id = "v6611-memory-run-isolation"
        repo.create_project(project_id=project_id, name="Memory Isolation", genre="fantasy")
        repo.add_chapter(project_id, 1, title="Ch1", status="awaiting_publish")

        fallback_run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(fallback_run_id, status="completed", current_node="memory_curator")
        repo.create_workflow_node_event(
            run_id=fallback_run_id,
            project_id=project_id,
            chapter_number=1,
            node_name="memory_curator",
            event_type="completed",
            status="warning",
            message="LLM 提取为空，使用章节状态卡兜底",
        )
        fallback_batch = repo.create_memory_batch(
            project_id,
            chapter_number=1,
            run_id=fallback_run_id,
            summary="第1章记忆提取 - 状态卡兜底 (1项)",
        )
        repo.create_memory_item(
            fallback_batch["id"],
            project_id,
            target_table="story_facts",
            operation="create",
            after_json='{"fact_key":"chapter_1.state_card"}',
            confidence=0.45,
            evidence_text="状态卡：主角发现异常",
            rationale="状态卡兜底候选",
        )

        trusted_run_id = repo.create_workflow_run(project_id, 1)
        repo.update_workflow_run(trusted_run_id, status="completed", current_node="memory_curator")
        repo.create_workflow_node_event(
            run_id=trusted_run_id,
            project_id=project_id,
            chapter_number=1,
            node_name="memory_curator",
            event_type="completed",
            status="completed",
            message="记忆提取补跑完成",
        )
        trusted_batch = repo.create_memory_batch(
            project_id,
            chapter_number=1,
            run_id=trusted_run_id,
            summary="第1章记忆提取 (1项)",
        )
        repo.create_memory_item(
            trusted_batch["id"],
            project_id,
            target_table="story_facts",
            operation="create",
            after_json='{"fact_key":"chapter_1.real_extraction"}',
            confidence=0.92,
            evidence_text="林泽在地铁站第一次确认系统存在误报。",
            rationale="MemoryCurator LLM 复核",
        )

        old_resp = client.get(
            f"/api/projects/{project_id}/chapters/1/workflow-timeline?run_id={fallback_run_id}"
        )
        assert old_resp.status_code == 200
        old_nodes = old_resp.json()["data"]["nodes"]
        old_memory = next(n for n in old_nodes if n["node_name"] == "memory_curator")
        assert old_memory["status"] == "warning"
        assert old_memory["node_status"] == "warning"
        assert old_memory["domain_status"] == "fallback"
        assert old_memory["severity"] == "warning"
        assert old_memory["flags"]["memory_trusted"] is False

        new_resp = client.get(
            f"/api/projects/{project_id}/chapters/1/workflow-timeline?run_id={trusted_run_id}"
        )
        assert new_resp.status_code == 200
        new_nodes = new_resp.json()["data"]["nodes"]
        new_memory = next(n for n in new_nodes if n["node_name"] == "memory_curator")
        assert new_memory["node_status"] == "succeeded"
        assert new_memory["domain_status"] == "success"
        assert new_memory["severity"] == "success"
        assert new_memory["flags"]["memory_trusted"] is True
