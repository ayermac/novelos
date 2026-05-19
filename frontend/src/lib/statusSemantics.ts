/**
 * Unified status semantics for frontend (v6.6.11).
 *
 * Provides a single source of truth for interpreting domain-level
 * operation results, memory status, workflow status, and node-level
 * timeline status.
 *
 * No component should do raw string comparison like
 * `status === 'fallback'` — use these helpers instead.
 *
 * v6.6.11: Added normalizeNodeStatus(), isNodeBusinessSuccess(),
 * getNodeStatusBadge() now supports warning/succeeded node statuses.
 */

// ── Types ──────────────────────────────────────────────────────────

export type DomainStatus =
  | "success"
  | "partial_success"
  | "fallback"
  | "degraded"
  | "failed"
  | "blocked"
  | "needs_human"
  | "pending"
  | "ignored";

export type Severity = "success" | "info" | "warning" | "error";

export type NodeStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "completed"
  | "warning"
  | "failed"
  | "skipped"
  | "blocked";

export interface OperationResult {
  ok: boolean;
  domain_status: DomainStatus;
  message: string;
  user_message: string;
  technical_message: string | null;
  retryable: boolean;
  blocking: boolean;
  next_action: string | null;
  action_label: string | null;
  severity: Severity;
  flags: Record<string, boolean>;
  details: Record<string, unknown>;
}

// ── Core helpers ───────────────────────────────────────────────────

/**
 * Normalize a raw API response into a typed OperationResult.
 * Handles both new (with domain_result) and legacy (without) responses.
 */
export function normalizeOperationResult(raw: Record<string, unknown>): OperationResult {
  // If backend already provides domain_result, use it
  if (raw.domain_result && typeof raw.domain_result === "object") {
    return raw.domain_result as OperationResult;
  }

  // Legacy: derive from available fields
  return deriveOperationResult(raw);
}

/**
 * Derive OperationResult from legacy response fields.
 * Used when backend hasn't added domain_result yet.
 */
export function deriveOperationResult(raw: Record<string, unknown>): OperationResult {
  const workflowStatus = String(raw.workflow_status || "");
  const chapterStatus = String(raw.chapter_status || "");
  const memoryStatus = raw.memory_status as Record<string, unknown> | undefined;

  // Check memory status for partial success
  const memoryTrusted = memoryStatus?.memory_trusted ?? true;
  const memStatusStr = String(memoryStatus?.memory_status || "");

  if (workflowStatus === "running") {
    return {
      ok: true,
      domain_status: "pending",
      message: "工作流运行中",
      user_message: "工作流运行中",
      technical_message: null,
      retryable: false,
      blocking: false,
      next_action: null,
      action_label: null,
      severity: "info",
      flags: { workflow_running: true },
      details: {},
    };
  }

  if (
    workflowStatus === "completed" ||
    chapterStatus === "awaiting_publish" ||
    chapterStatus === "published"
  ) {
    if (memoryStatus && !memoryTrusted) {
      return {
        ok: true,
        domain_status: "partial_success",
        message: "章节已到待发布状态，但记忆提取未成功",
        user_message: "章节正文已通过审核，但记忆提取为降级/兜底状态，建议补跑记忆",
        technical_message: null,
        retryable: true,
        blocking: false,
        next_action: "backfill_memory",
        action_label: "补跑记忆",
        severity: "warning",
        flags: { workflow_completed: true, memory_degraded: true },
        details: { memory_status: memStatusStr },
      };
    }
    return {
      ok: true,
      domain_status: "success",
      message: "工作流已完成",
      user_message: "工作流已完成",
      technical_message: null,
      retryable: false,
      blocking: false,
      next_action: null,
      action_label: null,
      severity: "success",
      flags: { workflow_completed: true, memory_trusted: true },
      details: {},
    };
  }

  if (workflowStatus === "failed") {
    return {
      ok: false,
      domain_status: "failed",
      message: "工作流执行失败",
      user_message: "工作流执行失败，可尝试重试",
      technical_message: null,
      retryable: true,
      blocking: false,
      next_action: "retry_workflow",
      action_label: "重试工作流",
      severity: "error",
      flags: { workflow_failed: true },
      details: {},
    };
  }

  if (workflowStatus === "blocked") {
    return {
      ok: false,
      domain_status: chapterStatus === "revision" ? "needs_human" : "blocked",
      message: chapterStatus === "revision" ? "章节需要返修" : "工作流被阻塞",
      user_message: chapterStatus === "revision" ? "章节需要返修" : "工作流被阻塞",
      technical_message: null,
      retryable: chapterStatus === "revision",
      blocking: true,
      next_action: chapterStatus === "revision" ? "retry_node" : "reset_chapter",
      action_label: chapterStatus === "revision" ? "重试失败节点" : "重置章节",
      severity: "error",
      flags: { workflow_blocked: true },
      details: {},
    };
  }

  return {
    ok: true,
    domain_status: "pending",
    message: `工作流状态: ${workflowStatus}`,
    user_message: `工作流状态: ${workflowStatus}`,
    technical_message: null,
    retryable: false,
    blocking: false,
    next_action: null,
    action_label: null,
    severity: "info",
    flags: {},
    details: {},
  };
}

// ── Badge / display helpers ────────────────────────────────────────

export interface StatusBadge {
  label: string;
  severity: Severity;
  cssClass: string;
  icon: string;
}

const DOMAIN_STATUS_BADGES: Record<DomainStatus, StatusBadge> = {
  success: { label: "成功", severity: "success", cssClass: "badge-success", icon: "✓" },
  partial_success: { label: "部分完成", severity: "warning", cssClass: "badge-warning", icon: "⚠" },
  fallback: { label: "降级完成", severity: "warning", cssClass: "badge-warning", icon: "⚠" },
  degraded: { label: "降级", severity: "warning", cssClass: "badge-warning", icon: "⚠" },
  failed: { label: "失败", severity: "error", cssClass: "badge-error", icon: "✗" },
  blocked: { label: "阻塞", severity: "error", cssClass: "badge-error", icon: "⊘" },
  needs_human: { label: "需人工介入", severity: "warning", cssClass: "badge-warning", icon: "⚑" },
  pending: { label: "进行中", severity: "info", cssClass: "badge-info", icon: "◌" },
  ignored: { label: "已忽略", severity: "info", cssClass: "badge-info", icon: "—" },
};

const NODE_STATUS_BADGES: Record<NodeStatus, StatusBadge> = {
  pending: { label: "等待中", severity: "info", cssClass: "step-pending", icon: "◌" },
  running: { label: "运行中", severity: "info", cssClass: "step-running", icon: "●" },
  succeeded: { label: "已完成", severity: "success", cssClass: "step-completed", icon: "✓" },
  completed: { label: "已完成", severity: "success", cssClass: "step-completed", icon: "✓" },
  warning: { label: "警告", severity: "warning", cssClass: "step-warning", icon: "⚠" },
  failed: { label: "失败", severity: "error", cssClass: "step-failed", icon: "✗" },
  skipped: { label: "跳过", severity: "info", cssClass: "step-skipped", icon: "○" },
  blocked: { label: "阻塞", severity: "error", cssClass: "step-blocked", icon: "⊘" },
};

/**
 * Get badge display for a domain status.
 */
export function getStatusBadge(result: OperationResult): StatusBadge {
  return DOMAIN_STATUS_BADGES[result.domain_status] || DOMAIN_STATUS_BADGES.pending;
}

/**
 * Get badge display for a workflow node status.
 */
export function getNodeStatusBadge(nodeStatus: NodeStatus): StatusBadge {
  return NODE_STATUS_BADGES[nodeStatus] || NODE_STATUS_BADGES.pending;
}

// ── Semantic query helpers ─────────────────────────────────────────

/**
 * True only when the business operation truly succeeded.
 * fallback, degraded, partial_success are NOT business success.
 */
export function isBusinessSuccess(result: OperationResult): boolean {
  return result.domain_status === "success";
}

/**
 * True when the operation can be retried.
 */
export function isRetryable(result: OperationResult): boolean {
  return result.retryable;
}

/**
 * True when the operation is blocked and cannot proceed without intervention.
 */
export function isBlocking(result: OperationResult): boolean {
  return result.blocking;
}

/**
 * Get action hint for the user — what to do next.
 */
export function getActionHint(result: OperationResult): string {
  if (result.next_action && result.action_label) {
    return result.action_label;
  }
  switch (result.domain_status) {
    case "fallback":
      return "重新补跑记忆提取";
    case "degraded":
      return "重新执行";
    case "failed":
      return "重试";
    case "blocked":
      return "解除阻塞";
    case "needs_human":
      return "人工处理";
    case "partial_success":
      return "补跑记忆";
    default:
      return "";
  }
}

// ── Memory status display ──────────────────────────────────────────

export type MemoryStatusCode = "trusted" | "fallback" | "failed" | "missing";

export interface MemoryStatusDisplay {
  label: string;
  severity: Severity;
  cssClass: string;
  userMessage: string;
  isBusinessSuccess: boolean;
}

const MEMORY_STATUS_DISPLAY: Record<MemoryStatusCode, MemoryStatusDisplay> = {
  trusted: {
    label: "可信记忆",
    severity: "success",
    cssClass: "memory-trusted",
    userMessage: "可信记忆已提取，可用于后续章节生成",
    isBusinessSuccess: true,
  },
  fallback: {
    label: "兜底候选",
    severity: "warning",
    cssClass: "memory-fallback",
    userMessage: "当前为状态卡兜底候选，不可作为可信记忆，建议重新补跑",
    isBusinessSuccess: false,
  },
  failed: {
    label: "提取失败",
    severity: "error",
    cssClass: "memory-failed",
    userMessage: "记忆提取失败，可尝试重新补跑",
    isBusinessSuccess: false,
  },
  missing: {
    label: "未提取",
    severity: "warning",
    cssClass: "memory-missing",
    userMessage: "该章节尚未提取记忆，建议补跑",
    isBusinessSuccess: false,
  },
};

/**
 * Get display properties for a memory status string.
 */
export function getMemoryStatusDisplay(status: MemoryStatusCode): MemoryStatusDisplay {
  return MEMORY_STATUS_DISPLAY[status] || MEMORY_STATUS_DISPLAY.missing;
}

// ── Severity to CSS color mapping ──────────────────────────────────

/**
 * Get CSS color variable for a severity level.
 * Works with both light and dark modes (CSS custom properties).
 */
export function severityColor(severity: Severity): string {
  switch (severity) {
    case "success":
      return "var(--color-success, #10b981)";
    case "info":
      return "var(--color-info, #3b82f6)";
    case "warning":
      return "var(--color-warning, #f59e0b)";
    case "error":
      return "var(--color-error, #ef4444)";
    default:
      return "var(--color-info, #3b82f6)";
  }
}

/**
 * Get CSS class for badge background based on severity.
 * Compatible with dark mode — uses CSS custom properties.
 */
export function severityBadgeClass(severity: Severity): string {
  switch (severity) {
    case "success":
      return "badge-success";
    case "info":
      return "badge-info";
    case "warning":
      return "badge-warning";
    case "error":
      return "badge-error";
    default:
      return "badge-info";
  }
}

// ── Node-level status helpers (v6.6.11) ───────────────────────────

/**
 * Normalize a timeline node's status for display.
 *
 * Handles backward compatibility:
 * - If node_status is present (v6.6.11+), use it
 * - If only legacy status is present, map completed→succeeded, etc.
 * - Returns the most accurate NodeStatus for display
 */
export function normalizeNodeStatus(node: {
  status: string;
  node_status?: string;
  domain_status?: string;
  severity?: string;
}): NodeStatus {
  // v6.6.11+: Use node_status if available
  if (node.node_status) {
    return node.node_status as NodeStatus;
  }

  // Legacy mapping: derive node_status from old status field
  const legacy = node.status;
  switch (legacy) {
    case "completed":
      // Check if domain_status indicates non-success
      if (node.domain_status === "fallback" || node.domain_status === "degraded" || node.domain_status === "partial_success") {
        return "warning";
      }
      // Check if severity indicates warning
      if (node.severity === "warning") {
        return "warning";
      }
      return "succeeded";
    case "running":
      return "running";
    case "failed":
      return "failed";
    case "blocked":
      return "blocked";
    case "skipped":
      return "skipped";
    default:
      return "pending";
  }
}

/**
 * True only when a node has genuinely succeeded at the business level.
 * warning, failed, skipped, blocked are NOT business success.
 * "succeeded" with domain_status=fallback is also NOT business success.
 */
export function isNodeBusinessSuccess(node: {
  node_status?: string;
  domain_status?: string;
  severity?: string;
}): boolean {
  const ns = node.node_status;
  if (!ns) return false;

  if (ns !== "succeeded") return false;

  // Even succeeded nodes can have fallback/degraded domain
  const ds = node.domain_status;
  if (ds === "fallback" || ds === "degraded" || ds === "partial_success" || ds === "failed") {
    return false;
  }

  return true;
}
