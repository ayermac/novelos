/**
 * Tests for statusSemantics.ts (v6.6.11).
 *
 * Covers:
 * - success/fallback/degraded/failed/blocked/partial_success badge semantics
 * - isBusinessSuccess does not treat fallback/degraded as success
 * - retryable/action hint display logic
 * - dark mode class / token coverage
 * - memory status display
 * - normalizeOperationResult handles legacy and new formats
 * - normalizeNodeStatus for v6.6.11 node-level status
 * - isNodeBusinessSuccess for node-level business success
 * - getNodeStatusBadge for warning/succeeded node statuses
 */

import { describe, it, expect } from "vitest";
import {
  normalizeOperationResult,
  isBusinessSuccess,
  isRetryable,
  isBlocking,
  getStatusBadge,
  getNodeStatusBadge,
  getActionHint,
  getMemoryStatusDisplay,
  severityColor,
  severityBadgeClass,
  normalizeNodeStatus,
  isNodeBusinessSuccess,
  type OperationResult,
  type DomainStatus,
} from "./statusSemantics";

// ── Badge semantics ────────────────────────────────────────────────

describe("getStatusBadge", () => {
  const cases: Array<[DomainStatus, string, string]> = [
    ["success", "成功", "badge-success"],
    ["partial_success", "部分完成", "badge-warning"],
    ["fallback", "降级完成", "badge-warning"],
    ["degraded", "降级", "badge-warning"],
    ["failed", "失败", "badge-error"],
    ["blocked", "阻塞", "badge-error"],
    ["needs_human", "需人工介入", "badge-warning"],
    ["pending", "进行中", "badge-info"],
    ["ignored", "已忽略", "badge-info"],
  ];

  it.each(cases)(
    "domain_status=%s → label=%s, cssClass=%s",
    (status, expectedLabel, expectedClass) => {
      const result: OperationResult = {
        ok: status !== "failed" && status !== "blocked" && status !== "needs_human",
        domain_status: status,
        message: "test",
        user_message: "test",
        technical_message: null,
        retryable: false,
        blocking: false,
        next_action: null,
        action_label: null,
        severity: "info",
        flags: {},
        details: {},
      };
      const badge = getStatusBadge(result);
      expect(badge.label).toBe(expectedLabel);
      expect(badge.cssClass).toBe(expectedClass);
    },
  );
});

// ── isBusinessSuccess ──────────────────────────────────────────────

describe("isBusinessSuccess", () => {
  it("returns true for success", () => {
    const result = makeResult("success");
    expect(isBusinessSuccess(result)).toBe(true);
  });

  it("returns false for fallback", () => {
    const result = makeResult("fallback");
    expect(isBusinessSuccess(result)).toBe(false);
  });

  it("returns false for degraded", () => {
    const result = makeResult("degraded");
    expect(isBusinessSuccess(result)).toBe(false);
  });

  it("returns false for partial_success", () => {
    const result = makeResult("partial_success");
    expect(isBusinessSuccess(result)).toBe(false);
  });

  it("returns false for failed", () => {
    const result = makeResult("failed");
    expect(isBusinessSuccess(result)).toBe(false);
  });

  it("returns false for blocked", () => {
    const result = makeResult("blocked");
    expect(isBusinessSuccess(result)).toBe(false);
  });
});

// ── Retryable / blocking ───────────────────────────────────────────

describe("isRetryable", () => {
  it("returns true when retryable is set", () => {
    const result = makeResult("failed", { retryable: true });
    expect(isRetryable(result)).toBe(true);
  });

  it("returns false when retryable is not set", () => {
    const result = makeResult("success", { retryable: false });
    expect(isRetryable(result)).toBe(false);
  });
});

describe("isBlocking", () => {
  it("returns true for blocked", () => {
    const result = makeResult("blocked", { blocking: true });
    expect(isBlocking(result)).toBe(true);
  });

  it("returns false for success", () => {
    const result = makeResult("success", { blocking: false });
    expect(isBlocking(result)).toBe(false);
  });
});

// ── Action hint ────────────────────────────────────────────────────

describe("getActionHint", () => {
  it("returns action_label when available", () => {
    const result = makeResult("fallback", {
      next_action: "backfill_memory",
      action_label: "重新补跑记忆",
    });
    expect(getActionHint(result)).toBe("重新补跑记忆");
  });

  it("returns default hint for fallback without action_label", () => {
    const result = makeResult("fallback");
    expect(getActionHint(result)).toBe("重新补跑记忆提取");
  });

  it("returns default hint for failed", () => {
    const result = makeResult("failed");
    expect(getActionHint(result)).toBe("重试");
  });

  it("returns empty string for success", () => {
    const result = makeResult("success");
    expect(getActionHint(result)).toBe("");
  });
});

// ── Memory status display ──────────────────────────────────────────

describe("getMemoryStatusDisplay", () => {
  it("trusted is business success with success severity", () => {
    const display = getMemoryStatusDisplay("trusted");
    expect(display.isBusinessSuccess).toBe(true);
    expect(display.severity).toBe("success");
  });

  it("fallback is NOT business success with warning severity", () => {
    const display = getMemoryStatusDisplay("fallback");
    expect(display.isBusinessSuccess).toBe(false);
    expect(display.severity).toBe("warning");
  });

  it("failed is NOT business success with error severity", () => {
    const display = getMemoryStatusDisplay("failed");
    expect(display.isBusinessSuccess).toBe(false);
    expect(display.severity).toBe("error");
  });

  it("missing is NOT business success with warning severity", () => {
    const display = getMemoryStatusDisplay("missing");
    expect(display.isBusinessSuccess).toBe(false);
    expect(display.severity).toBe("warning");
  });
});

// ── Dark mode CSS tokens ───────────────────────────────────────────

describe("severityColor", () => {
  it("uses CSS custom properties for dark mode support", () => {
    expect(severityColor("success")).toContain("var(--color-success");
    expect(severityColor("warning")).toContain("var(--color-warning");
    expect(severityColor("error")).toContain("var(--color-error");
    expect(severityColor("info")).toContain("var(--color-info");
  });
});

describe("severityBadgeClass", () => {
  it("returns correct badge class per severity", () => {
    expect(severityBadgeClass("success")).toBe("badge-success");
    expect(severityBadgeClass("warning")).toBe("badge-warning");
    expect(severityBadgeClass("error")).toBe("badge-error");
    expect(severityBadgeClass("info")).toBe("badge-info");
  });
});

// ── normalizeOperationResult ───────────────────────────────────────

describe("normalizeOperationResult", () => {
  it("uses domain_result when available", () => {
    const raw = {
      workflow_status: "completed",
      domain_result: {
        ok: true,
        domain_status: "success",
        message: "test",
        user_message: "test",
        technical_message: null,
        retryable: false,
        blocking: false,
        next_action: null,
        action_label: null,
        severity: "success",
        flags: {},
        details: {},
      },
    };
    const result = normalizeOperationResult(raw);
    expect(result.domain_status).toBe("success");
  });

  it("derives partial_success for awaiting_publish + memory fallback", () => {
    const raw = {
      workflow_status: "completed",
      chapter_status: "awaiting_publish",
      memory_status: {
        memory_status: "fallback",
        memory_trusted: false,
        batch_count: 1,
        trusted_batch_count: 0,
        fallback_batch_count: 1,
      },
    };
    const result = normalizeOperationResult(raw);
    expect(result.domain_status).toBe("partial_success");
    expect(result.severity).toBe("warning");
    expect(isBusinessSuccess(result)).toBe(false);
  });

  it("derives success for completed + trusted memory", () => {
    const raw = {
      workflow_status: "completed",
      chapter_status: "awaiting_publish",
      memory_status: {
        memory_status: "trusted",
        memory_trusted: true,
        batch_count: 1,
        trusted_batch_count: 1,
        fallback_batch_count: 0,
      },
    };
    const result = normalizeOperationResult(raw);
    expect(result.domain_status).toBe("success");
    expect(isBusinessSuccess(result)).toBe(true);
  });

  it("derives failed for failed workflow", () => {
    const raw = {
      workflow_status: "failed",
      chapter_status: "drafted",
    };
    const result = normalizeOperationResult(raw);
    expect(result.domain_status).toBe("failed");
    expect(result.severity).toBe("error");
  });

  it("derives blocked for blocked workflow", () => {
    const raw = {
      workflow_status: "blocked",
      chapter_status: "blocking",
    };
    const result = normalizeOperationResult(raw);
    expect(result.domain_status).toBe("blocked");
    expect(isBlocking(result)).toBe(true);
  });
});

// ── normalizeNodeStatus (v6.6.11) ──────────────────────────────────

describe("normalizeNodeStatus", () => {
  it("uses node_status when available", () => {
    const node = { status: "completed", node_status: "warning" as const };
    expect(normalizeNodeStatus(node)).toBe("warning");
  });

  it("maps legacy completed to succeeded", () => {
    const node = { status: "completed" };
    expect(normalizeNodeStatus(node)).toBe("succeeded");
  });

  it("maps legacy completed + fallback domain to warning", () => {
    const node = { status: "completed", domain_status: "fallback" };
    expect(normalizeNodeStatus(node)).toBe("warning");
  });

  it("maps legacy completed + degraded domain to warning", () => {
    const node = { status: "completed", domain_status: "degraded" };
    expect(normalizeNodeStatus(node)).toBe("warning");
  });

  it("maps legacy completed + warning severity to warning", () => {
    const node = { status: "completed", severity: "warning" };
    expect(normalizeNodeStatus(node)).toBe("warning");
  });

  it("maps legacy running to running", () => {
    const node = { status: "running" };
    expect(normalizeNodeStatus(node)).toBe("running");
  });

  it("maps legacy failed to failed", () => {
    const node = { status: "failed" };
    expect(normalizeNodeStatus(node)).toBe("failed");
  });

  it("maps legacy blocked to blocked", () => {
    const node = { status: "blocked" };
    expect(normalizeNodeStatus(node)).toBe("blocked");
  });

  it("maps legacy skipped to skipped", () => {
    const node = { status: "skipped" };
    expect(normalizeNodeStatus(node)).toBe("skipped");
  });

  it("maps legacy pending to pending", () => {
    const node = { status: "pending" };
    expect(normalizeNodeStatus(node)).toBe("pending");
  });

  it("prefers node_status over legacy status", () => {
    const node = { status: "completed", node_status: "failed" as const };
    expect(normalizeNodeStatus(node)).toBe("failed");
  });
});

// ── isNodeBusinessSuccess (v6.6.11) ──────────────────────────────

describe("isNodeBusinessSuccess", () => {
  it("returns true for succeeded with success domain", () => {
    expect(isNodeBusinessSuccess({ node_status: "succeeded", domain_status: "success" })).toBe(true);
  });

  it("returns false for warning node", () => {
    expect(isNodeBusinessSuccess({ node_status: "warning", domain_status: "fallback" })).toBe(false);
  });

  it("returns false for failed node", () => {
    expect(isNodeBusinessSuccess({ node_status: "failed", domain_status: "failed" })).toBe(false);
  });

  it("returns false for succeeded with fallback domain", () => {
    expect(isNodeBusinessSuccess({ node_status: "succeeded", domain_status: "fallback" })).toBe(false);
  });

  it("returns false for succeeded with degraded domain", () => {
    expect(isNodeBusinessSuccess({ node_status: "succeeded", domain_status: "degraded" })).toBe(false);
  });

  it("returns false for skipped node", () => {
    expect(isNodeBusinessSuccess({ node_status: "skipped", domain_status: "ignored" })).toBe(false);
  });

  it("returns false when node_status is undefined", () => {
    expect(isNodeBusinessSuccess({ domain_status: "success" })).toBe(false);
  });
});

// ── getNodeStatusBadge (v6.6.11) ──────────────────────────────────

describe("getNodeStatusBadge", () => {
  it("returns warning badge for warning node status", () => {
    const badge = getNodeStatusBadge("warning");
    expect(badge.severity).toBe("warning");
    expect(badge.cssClass).toBe("step-warning");
    expect(badge.icon).toBe("⚠");
  });

  it("returns succeeded badge for succeeded node status", () => {
    const badge = getNodeStatusBadge("succeeded");
    expect(badge.severity).toBe("success");
    expect(badge.cssClass).toBe("step-completed");
    expect(badge.icon).toBe("✓");
  });

  it("returns failed badge for failed node status", () => {
    const badge = getNodeStatusBadge("failed");
    expect(badge.severity).toBe("error");
    expect(badge.cssClass).toBe("step-failed");
  });

  it("returns blocked badge for blocked node status", () => {
    const badge = getNodeStatusBadge("blocked");
    expect(badge.severity).toBe("error");
    expect(badge.cssClass).toBe("step-blocked");
  });

  it("returns skipped badge for skipped node status", () => {
    const badge = getNodeStatusBadge("skipped");
    expect(badge.severity).toBe("info");
    expect(badge.cssClass).toBe("step-skipped");
  });

  it("returns pending badge for pending node status", () => {
    const badge = getNodeStatusBadge("pending");
    expect(badge.severity).toBe("info");
    expect(badge.cssClass).toBe("step-pending");
  });

  it("returns running badge for running node status", () => {
    const badge = getNodeStatusBadge("running");
    expect(badge.severity).toBe("info");
    expect(badge.cssClass).toBe("step-running");
  });

  it("returns completed badge (legacy) for completed node status", () => {
    const badge = getNodeStatusBadge("completed");
    expect(badge.severity).toBe("success");
    expect(badge.cssClass).toBe("step-completed");
  });
});

// ── Helpers ────────────────────────────────────────────────────────

function makeResult(
  status: DomainStatus,
  overrides: Partial<OperationResult> = {},
): OperationResult {
  return {
    ok: status !== "failed" && status !== "blocked" && status !== "needs_human",
    domain_status: status,
    message: "test",
    user_message: "test",
    technical_message: null,
    retryable: false,
    blocking: false,
    next_action: null,
    action_label: null,
    severity: "info",
    flags: {},
    details: {},
    ...overrides,
  };
}
