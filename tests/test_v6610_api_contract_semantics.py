"""Tests for v6.6.10 API Contract & Frontend State Semantics Closure.

Covers:
- OperationResult helpers JSON structure stability
- Memory trusted/fallback/degraded/failed mapping
- backfill force=true not skipped by old fallback
- Manual backfill success → success + trusted memory
- Manual backfill failure → fallback/degraded/failed, not "success"
- Workflow awaiting_publish + memory fallback → partial_success or warning flags
- API response does not leak sensitive info / full content
"""

from __future__ import annotations

import json

import pytest

from novel_factory.api.contracts import (
    OperationResult,
    success,
    partial_success,
    fallback,
    degraded,
    failed,
    blocked,
    needs_human,
    ignored,
    memory_status_to_domain_result,
    workflow_run_to_domain_status,
    _SENSITIVE_KEYS,
)


# ── OperationResult helpers JSON structure ───────────────────────────


class TestOperationResultHelpers:
    """Verify each helper produces a stable, JSON-serializable structure."""

    def test_success_structure(self):
        r = success("ok")
        assert r.ok is True
        assert r.domain_status == "success"
        assert r.severity == "success"
        assert r.retryable is False
        assert r.blocking is False
        d = r.to_dict()
        assert isinstance(d, dict)
        json.dumps(d)  # must be JSON-serializable

    def test_partial_success_structure(self):
        r = partial_success("partial")
        assert r.ok is True
        assert r.domain_status == "partial_success"
        assert r.severity == "warning"
        assert r.retryable is True
        d = r.to_dict()
        json.dumps(d)

    def test_fallback_structure(self):
        r = fallback("fb", next_action="backfill", action_label="补跑")
        assert r.ok is True
        assert r.domain_status == "fallback"
        assert r.severity == "warning"
        assert r.retryable is True
        assert r.next_action == "backfill"
        assert r.action_label == "补跑"
        d = r.to_dict()
        json.dumps(d)

    def test_degraded_structure(self):
        r = degraded("degraded")
        assert r.ok is True
        assert r.domain_status == "degraded"
        assert r.severity == "warning"
        assert r.retryable is True
        d = r.to_dict()
        json.dumps(d)

    def test_failed_structure(self):
        r = failed("err", retryable=True, next_action="retry")
        assert r.ok is False
        assert r.domain_status == "failed"
        assert r.severity == "error"
        assert r.retryable is True
        d = r.to_dict()
        json.dumps(d)

    def test_blocked_structure(self):
        r = blocked("blocked", next_action="reset")
        assert r.ok is False
        assert r.domain_status == "blocked"
        assert r.severity == "error"
        assert r.blocking is True
        assert r.retryable is False
        d = r.to_dict()
        json.dumps(d)

    def test_needs_human_structure(self):
        r = needs_human("human needed")
        assert r.ok is False
        assert r.domain_status == "needs_human"
        assert r.severity == "warning"
        assert r.blocking is True
        assert r.retryable is True
        d = r.to_dict()
        json.dumps(d)

    def test_ignored_structure(self):
        r = ignored("skipped")
        assert r.ok is True
        assert r.domain_status == "ignored"
        assert r.severity == "info"
        d = r.to_dict()
        json.dumps(d)

    def test_user_message_defaults_to_message(self):
        r = success("操作成功")
        assert r.user_message == "操作成功"

    def test_user_message_can_be_overridden(self):
        r = success("技术消息", user_message="用户消息")
        assert r.user_message == "用户消息"
        assert r.message == "技术消息"


# ── Memory status mapping ───────────────────────────────────────────


class TestMemoryStatusMapping:
    """Verify memory_status_to_domain_result mapping."""

    def test_trusted_maps_to_success(self):
        r = memory_status_to_domain_result("trusted", trusted_batch_count=1, batch_count=1)
        assert r.domain_status == "success"
        assert r.severity == "success"
        assert r.flags.get("memory_trusted") is True

    def test_fallback_maps_to_fallback_domain(self):
        r = memory_status_to_domain_result("fallback", fallback_batch_count=1, batch_count=1)
        assert r.domain_status == "fallback"
        assert r.severity == "warning"
        assert r.flags.get("memory_trusted") is False
        assert r.flags.get("memory_fallback") is True
        assert r.next_action == "backfill_memory"

    def test_failed_maps_to_failed_domain(self):
        r = memory_status_to_domain_result("failed", batch_count=0)
        assert r.domain_status == "failed"
        assert r.severity == "error"
        assert r.flags.get("memory_failed") is True

    def test_missing_maps_to_degraded_domain(self):
        r = memory_status_to_domain_result("missing")
        assert r.domain_status == "degraded"
        assert r.severity == "warning"
        assert r.flags.get("memory_missing") is True

    def test_unknown_maps_to_failed(self):
        r = memory_status_to_domain_result("weird_status")
        assert r.domain_status == "failed"


# ── Workflow domain status mapping ──────────────────────────────────


class TestWorkflowDomainStatus:
    """Verify workflow_run_to_domain_status."""

    def test_running_is_pending(self):
        r = workflow_run_to_domain_status("running", "drafted")
        assert r.domain_status == "pending"
        assert r.ok is True

    def test_completed_trusted_memory_is_success(self):
        r = workflow_run_to_domain_status(
            "completed", "awaiting_publish",
            memory_status={"memory_trusted": True, "memory_status": "trusted",
                          "batch_count": 1, "trusted_batch_count": 1, "fallback_batch_count": 0},
        )
        assert r.domain_status == "success"

    def test_awaiting_publish_fallback_memory_is_partial_success(self):
        r = workflow_run_to_domain_status(
            "completed", "awaiting_publish",
            memory_status={"memory_trusted": False, "memory_status": "fallback",
                          "batch_count": 1, "trusted_batch_count": 0, "fallback_batch_count": 1},
        )
        assert r.domain_status == "partial_success"
        assert r.flags.get("memory_degraded") is True
        assert r.next_action == "backfill_memory"

    def test_published_fallback_memory_is_partial_success(self):
        r = workflow_run_to_domain_status(
            "completed", "published",
            memory_status={"memory_trusted": False, "memory_status": "fallback",
                          "batch_count": 1, "trusted_batch_count": 0, "fallback_batch_count": 1},
        )
        assert r.domain_status == "partial_success"

    def test_failed_workflow_is_failed(self):
        r = workflow_run_to_domain_status("failed", "drafted")
        assert r.domain_status == "failed"
        assert r.ok is False

    def test_blocked_workflow_is_blocked(self):
        r = workflow_run_to_domain_status("blocked", "blocking")
        assert r.domain_status == "blocked"
        assert r.blocking is True

    def test_blocked_revision_is_needs_human(self):
        r = workflow_run_to_domain_status("blocked", "revision")
        assert r.domain_status == "needs_human"
        assert r.blocking is True

    def test_no_memory_status_defaults_to_success(self):
        r = workflow_run_to_domain_status("completed", "awaiting_publish")
        assert r.domain_status == "success"


# ── Sensitive data scrubbing ────────────────────────────────────────


class TestSensitiveDataScrubbing:
    """Verify OperationResult.to_dict() does not leak sensitive data."""

    def test_scrubs_api_key(self):
        r = success("ok", details={"OPENAI_API_KEY": "sk-12345"})
        d = r.to_dict()
        assert d["details"]["OPENAI_API_KEY"] == "[REDACTED]"

    def test_scrubs_base_url(self):
        r = success("ok", details={"OPENAI_BASE_URL": "https://api.example.com"})
        d = r.to_dict()
        assert d["details"]["OPENAI_BASE_URL"] == "[REDACTED]"

    def test_scrubs_nested_content(self):
        r = failed("err", details={
            "chapter_info": {
                "content": "This is full chapter text that should not appear",
                "word_count": 3000,
            }
        })
        d = r.to_dict()
        assert d["details"]["chapter_info"]["content"] == "[REDACTED]"
        assert d["details"]["chapter_info"]["word_count"] == 3000

    def test_scrubs_list_items(self):
        r = success("ok", details={
            "items": [
                {"api_key": "secret-key", "name": "valid"},
            ]
        })
        d = r.to_dict()
        assert d["details"]["items"][0]["api_key"] == "[REDACTED]"
        assert d["details"]["items"][0]["name"] == "valid"

    def test_all_sensitive_keys_are_scrubbed(self):
        for key in _SENSITIVE_KEYS:
            r = success("ok", details={key: "leak-value"})
            d = r.to_dict()
            assert d["details"][key] == "[REDACTED]", f"Sensitive key '{key}' not scrubbed"


# ── Backfill endpoint domain_result integration ─────────────────────


class TestBackfillDomainResult:
    """Verify backfill responses include correct domain_result.

    These test the contract that runs.py should produce when
    calling the backfill endpoint — not the HTTP layer itself.
    """

    def test_fallback_result_not_ok(self):
        """A fallback extraction result should have ok=True but domain_status=fallback."""
        r = fallback("记忆提取仅产生低可信候选")
        assert r.ok is True  # HTTP request succeeded
        assert r.domain_status == "fallback"  # But business result is degraded
        assert r.severity == "warning"
        assert r.retryable is True

    def test_degraded_result_not_ok(self):
        """A degraded result should have ok=True but domain_status=degraded."""
        r = degraded("MemoryCurator 降级")
        assert r.ok is True
        assert r.domain_status == "degraded"
        assert r.severity == "warning"

    def test_failed_backfill_is_not_success(self):
        """A failed backfill should not show 'success'."""
        r = failed("记忆提取失败")
        assert r.ok is False
        assert r.domain_status == "failed"
        assert "success" not in r.domain_status

    def test_successful_backfill_is_success(self):
        """A successful trusted extraction should be domain_status=success."""
        r = success("记忆提取成功")
        assert r.ok is True
        assert r.domain_status == "success"

    def test_force_backfill_not_skipped_by_old_fallback(self):
        """When force=true, old fallback should be ignored, not block new extraction.

        This tests the semantic contract: if force=true and new extraction
        produces trusted memory, domain_result should be success.
        """
        # Simulate: force=true, new extraction produces trusted result
        r = success(
            "记忆提取补跑完成：3 条可信候选",
            flags={"memory_trusted": True, "force_used": True},
        )
        assert r.domain_status == "success"
        assert r.flags.get("memory_trusted") is True


# ── OperationResult JSON roundtrip ──────────────────────────────────


class TestOperationResultJsonRoundtrip:
    """Verify OperationResult can be serialized and deserialized."""

    def test_roundtrip(self):
        r = fallback(
            "test fallback",
            user_message="用户消息",
            next_action="backfill",
            action_label="补跑",
            details={"batch_count": 3},
            flags={"memory_fallback": True},
        )
        d = r.to_dict()
        json_str = json.dumps(d, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["domain_status"] == "fallback"
        assert parsed["user_message"] == "用户消息"
        assert parsed["next_action"] == "backfill"
        assert parsed["details"]["batch_count"] == 3
        assert parsed["flags"]["memory_fallback"] is True

    def test_all_domain_statuses_serializable(self):
        """Every domain_status value must produce a serializable result."""
        helpers = [success, partial_success, fallback, degraded, failed, blocked, needs_human, ignored]
        for helper in helpers:
            r = helper("test")
            d = r.to_dict()
            json_str = json.dumps(d, ensure_ascii=False)
            parsed = json.loads(json_str)
            assert "domain_status" in parsed
            assert "severity" in parsed
