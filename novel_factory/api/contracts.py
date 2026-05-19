"""Unified API response contracts for domain-level status semantics (v6.6.10).

Core principle: ok=true means the HTTP request was processed, NOT that
the business operation succeeded. Domain-level success/failure is conveyed
via domain_status, severity, and related fields.

All OperationResult outputs are JSON-serializable and must not leak
API keys, base_url tokens, or full chapter content.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal


DomainStatus = Literal[
    "success",
    "partial_success",
    "fallback",
    "degraded",
    "failed",
    "blocked",
    "needs_human",
    "pending",
    "ignored",
]

Severity = Literal["success", "info", "warning", "error"]

# Sensitive field names that must never appear in OperationResult output
_SENSITIVE_KEYS = frozenset({
    "OPENAI_API_KEY", "API_KEY", "api_key", "apiKey",
    "OPENAI_BASE_URL", "BASE_URL", "base_url", "baseUrl",
    "token", "password", "secret", "authorization", "bearer",
    "content",  # chapter full content — too large, use word_count instead
})


@dataclass
class OperationResult:
    """Unified domain-level operation result.

    Every API endpoint that performs a business operation should return
    this (or embed it in the envelope data) so the frontend can
    consistently interpret business success vs HTTP success.
    """

    ok: bool
    domain_status: DomainStatus
    message: str
    user_message: str = ""
    technical_message: str | None = None
    retryable: bool = False
    blocking: bool = False
    next_action: str | None = None
    action_label: str | None = None
    severity: Severity = "info"
    flags: dict[str, bool] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.user_message:
            self.user_message = self.message
        # Auto-derive severity from domain_status if not explicitly set
        if self.severity == "info" and self.domain_status != "pending":
            self.severity = _domain_status_severity(self.domain_status)
        # Auto-derive blocking from domain_status
        if self.domain_status in ("blocked", "needs_human") and not self.blocking:
            self.blocking = True
        # Auto-derive retryable for failed/degraded
        if self.domain_status in ("failed", "degraded", "fallback") and not self.retryable:
            self.retryable = True

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe dict with sensitive data scrubbed."""
        d = asdict(self)
        _scrub_sensitive(d)
        return d


def _domain_status_severity(status: DomainStatus) -> Severity:
    """Map domain_status to default severity."""
    mapping: dict[str, Severity] = {
        "success": "success",
        "partial_success": "warning",
        "fallback": "warning",
        "degraded": "warning",
        "failed": "error",
        "blocked": "error",
        "needs_human": "warning",
        "pending": "info",
        "ignored": "info",
    }
    return mapping.get(status, "info")


def _scrub_sensitive(obj: Any) -> None:
    """Recursively remove sensitive keys from a dict (in-place)."""
    if not isinstance(obj, dict):
        return
    keys_to_remove = [k for k in obj if k in _SENSITIVE_KEYS]
    for k in keys_to_remove:
        obj[k] = "[REDACTED]"
    for v in obj.values():
        if isinstance(v, dict):
            _scrub_sensitive(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    _scrub_sensitive(item)


# ── Helper constructors ─────────────────────────────────────────────


def success(
    message: str = "操作成功",
    *,
    user_message: str = "",
    details: dict[str, Any] | None = None,
    flags: dict[str, bool] | None = None,
) -> OperationResult:
    """Business operation fully succeeded."""
    return OperationResult(
        ok=True,
        domain_status="success",
        message=message,
        user_message=user_message,
        severity="success",
        details=details or {},
        flags=flags or {},
    )


def partial_success(
    message: str = "操作部分完成",
    *,
    user_message: str = "",
    next_action: str | None = None,
    action_label: str | None = None,
    details: dict[str, Any] | None = None,
    flags: dict[str, bool] | None = None,
) -> OperationResult:
    """Business operation partially succeeded (e.g., awaiting_publish + memory fallback)."""
    return OperationResult(
        ok=True,
        domain_status="partial_success",
        message=message,
        user_message=user_message,
        severity="warning",
        retryable=True,
        next_action=next_action,
        action_label=action_label,
        details=details or {},
        flags=flags or {},
    )


def fallback(
    message: str = "操作使用降级结果完成",
    *,
    user_message: str = "",
    next_action: str | None = None,
    action_label: str | None = None,
    details: dict[str, Any] | None = None,
    flags: dict[str, bool] | None = None,
) -> OperationResult:
    """Business operation completed with fallback/degraded result."""
    return OperationResult(
        ok=True,
        domain_status="fallback",
        message=message,
        user_message=user_message,
        severity="warning",
        retryable=True,
        next_action=next_action,
        action_label=action_label,
        details=details or {},
        flags=flags or {},
    )


def degraded(
    message: str = "操作降级完成",
    *,
    user_message: str = "",
    next_action: str | None = None,
    action_label: str | None = None,
    details: dict[str, Any] | None = None,
    flags: dict[str, bool] | None = None,
) -> OperationResult:
    """Business operation completed in degraded mode (e.g., MemoryCurator no-op)."""
    return OperationResult(
        ok=True,
        domain_status="degraded",
        message=message,
        user_message=user_message,
        severity="warning",
        retryable=True,
        next_action=next_action,
        action_label=action_label,
        details=details or {},
        flags=flags or {},
    )


def failed(
    message: str = "操作失败",
    *,
    user_message: str = "",
    retryable: bool = True,
    next_action: str | None = None,
    action_label: str | None = None,
    details: dict[str, Any] | None = None,
    flags: dict[str, bool] | None = None,
) -> OperationResult:
    """Business operation failed."""
    return OperationResult(
        ok=False,
        domain_status="failed",
        message=message,
        user_message=user_message,
        severity="error",
        retryable=retryable,
        next_action=next_action,
        action_label=action_label,
        details=details or {},
        flags=flags or {},
    )


def blocked(
    message: str = "操作被阻塞",
    *,
    user_message: str = "",
    next_action: str | None = None,
    action_label: str | None = None,
    details: dict[str, Any] | None = None,
    flags: dict[str, bool] | None = None,
) -> OperationResult:
    """Business operation is blocked (e.g., death penalty, max retries)."""
    return OperationResult(
        ok=False,
        domain_status="blocked",
        message=message,
        user_message=user_message,
        severity="error",
        blocking=True,
        retryable=False,
        next_action=next_action,
        action_label=action_label,
        details=details or {},
        flags=flags or {},
    )


def needs_human(
    message: str = "需要人工介入",
    *,
    user_message: str = "",
    next_action: str | None = None,
    action_label: str | None = None,
    details: dict[str, Any] | None = None,
    flags: dict[str, bool] | None = None,
) -> OperationResult:
    """Business operation requires human intervention."""
    return OperationResult(
        ok=False,
        domain_status="needs_human",
        message=message,
        user_message=user_message,
        severity="warning",
        blocking=True,
        retryable=True,
        next_action=next_action,
        action_label=action_label,
        details=details or {},
        flags=flags or {},
    )


def ignored(
    message: str = "操作已忽略",
    *,
    user_message: str = "",
    details: dict[str, Any] | None = None,
    flags: dict[str, bool] | None = None,
) -> OperationResult:
    """Business operation was intentionally skipped (e.g., duplicate fallback batch)."""
    return OperationResult(
        ok=True,
        domain_status="ignored",
        message=message,
        user_message=user_message,
        severity="info",
        details=details or {},
        flags=flags or {},
    )


# ── Memory domain status mapping ────────────────────────────────────


def memory_status_to_domain_result(
    memory_status: str,
    *,
    project_id: str = "",
    chapter_number: int = 0,
    batch_count: int = 0,
    trusted_batch_count: int = 0,
    fallback_batch_count: int = 0,
    latest_memory_batch_id: str | None = None,
) -> OperationResult:
    """Convert memory_status string to OperationResult.

    Maps the output of get_memory_status_for_chapter() to a unified
    domain result with correct semantics.
    """
    if memory_status == "trusted":
        return success(
            "记忆提取成功：可信记忆已入库",
            details={
                "memory_status": "trusted",
                "batch_count": batch_count,
                "trusted_batch_count": trusted_batch_count,
                "latest_memory_batch_id": latest_memory_batch_id,
            },
            flags={"memory_trusted": True},
        )
    elif memory_status == "fallback":
        return fallback(
            "记忆提取仅产生低可信候选，不可作为后续章节的可信记忆",
            user_message="当前记忆为状态卡兜底候选，建议重新补跑记忆提取",
            next_action="backfill_memory",
            action_label="重新补跑记忆",
            details={
                "memory_status": "fallback",
                "batch_count": batch_count,
                "fallback_batch_count": fallback_batch_count,
                "latest_memory_batch_id": latest_memory_batch_id,
            },
            flags={"memory_trusted": False, "memory_fallback": True},
        )
    elif memory_status == "failed":
        return failed(
            "记忆提取失败：未生成任何记忆批次",
            user_message="记忆提取失败，可尝试重新补跑",
            next_action="backfill_memory",
            action_label="重新补跑记忆",
            details={
                "memory_status": "failed",
                "batch_count": batch_count,
            },
            flags={"memory_trusted": False, "memory_failed": True},
        )
    elif memory_status == "missing":
        return degraded(
            "尚未执行记忆提取",
            user_message="该章节尚未提取记忆，建议补跑",
            next_action="backfill_memory",
            action_label="补跑记忆",
            details={
                "memory_status": "missing",
                "batch_count": 0,
            },
            flags={"memory_trusted": False, "memory_missing": True},
        )
    else:
        return failed(
            f"记忆状态未知: {memory_status}",
            details={"memory_status": memory_status},
            flags={"memory_trusted": False},
        )


# ── Workflow domain status mapping ──────────────────────────────────


def workflow_run_to_domain_status(
    workflow_status: str,
    chapter_status: str,
    memory_status: dict | None = None,
) -> OperationResult:
    """Derive domain-level OperationResult from workflow run state.

    Handles the critical case where workflow reaches awaiting_publish
    but memory extraction failed/fallback — should be partial_success,
    not "success".
    """
    if workflow_status == "running":
        return OperationResult(
            ok=True,
            domain_status="pending",
            message="工作流运行中",
            severity="info",
            flags={"workflow_running": True},
        )

    if workflow_status == "completed" or chapter_status in (
        "awaiting_publish", "published",
    ):
        # Check memory status for partial success
        if memory_status and not memory_status.get("memory_trusted", True):
            mem_result = memory_status_to_domain_result(
                memory_status.get("memory_status", "missing"),
                batch_count=memory_status.get("batch_count", 0),
                trusted_batch_count=memory_status.get("trusted_batch_count", 0),
                fallback_batch_count=memory_status.get("fallback_batch_count", 0),
                latest_memory_batch_id=memory_status.get("latest_memory_batch_id"),
            )
            return partial_success(
                "章节已到待发布状态，但记忆提取未成功",
                user_message="章节正文已通过审核，但记忆提取为降级/兜底状态，建议补跑记忆",
                next_action="backfill_memory",
                action_label="补跑记忆",
                details={
                    "workflow_status": workflow_status,
                    "chapter_status": chapter_status,
                    "memory_domain": mem_result.to_dict(),
                },
                flags={
                    "workflow_completed": True,
                    "memory_degraded": True,
                },
            )

        return success(
            "工作流已完成",
            details={
                "workflow_status": workflow_status,
                "chapter_status": chapter_status,
            },
            flags={"workflow_completed": True, "memory_trusted": True},
        )

    if workflow_status == "failed":
        return failed(
            "工作流执行失败",
            next_action="retry_workflow",
            action_label="重试工作流",
            details={
                "workflow_status": workflow_status,
                "chapter_status": chapter_status,
            },
            flags={"workflow_failed": True},
        )

    if workflow_status == "blocked":
        if chapter_status == "revision":
            return needs_human(
                "章节需要返修",
                next_action="retry_node",
                action_label="重试失败节点",
                details={
                    "workflow_status": workflow_status,
                    "chapter_status": chapter_status,
                },
                flags={"workflow_blocked": True, "revision_needed": True},
            )
        return blocked(
            "工作流被阻塞",
            next_action="reset_chapter",
            action_label="重置章节",
            details={
                "workflow_status": workflow_status,
                "chapter_status": chapter_status,
            },
            flags={"workflow_blocked": True},
        )

    return OperationResult(
        ok=True,
        domain_status="pending",
        message=f"工作流状态: {workflow_status}",
        details={"workflow_status": workflow_status, "chapter_status": chapter_status},
    )
