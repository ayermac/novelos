# v6.6.11 Workflow Timeline & Node Semantics Closure — Review

## Review Date

2026-05-19

## Scope

Node-level status semantics for workflow timeline, with special focus on `memory_curator` node showing accurate warning/fallback instead of false success.

## Checklist

### Contract Correctness
- [x] `NodeOperationResult` has all required fields (node_name, node_status, domain_status, severity, message, user_message, retryable, blocking, next_action, action_label, flags, details)
- [x] `NodeStatus` includes `succeeded` (distinct from legacy `completed`)
- [x] `node_success()` → `succeeded/success`
- [x] `node_warning()` → `warning/{fallback|degraded}`
- [x] `node_failed()` → `failed/failed`
- [x] `node_blocked()` → `blocked/blocked`
- [x] `node_skipped()` → `skipped/ignored`
- [x] `node_from_operation_result()` correctly maps all domain statuses
- [x] `memory_curator_node_result()` handles all memory states
- [x] JSON serialization works for all node results
- [x] Sensitive data scrubbing applies to node details

### Memory Curator Mapping
- [x] trusted → succeeded/success (green)
- [x] fallback → warning/fallback (yellow, "记忆未可信")
- [x] degraded → warning/degraded (yellow, "降级")
- [x] failed event → failed/failed (red)
- [x] skipped → skipped/ignored (grey)
- [x] running → running/pending (blue)
- [x] completed event + no trusted memory → warning, NOT succeeded
- [x] missing + completed event → warning/degraded

### Workflow Interaction
- [x] awaiting_publish + fallback → workflow partial_success + node warning
- [x] awaiting_publish + trusted → workflow success + node succeeded

### Timeline API
- [x] Each node includes: node_status, domain_status, severity, retryable, blocking, next_action, action_label, user_message, flags
- [x] Legacy `status` field preserved
- [x] Memory status fetched and passed to _build_node_timeline

### Frontend
- [x] `normalizeNodeStatus()` handles both new and legacy status
- [x] `isNodeBusinessSuccess()` doesn't treat warning/fallback as success
- [x] `getNodeStatusBadge()` supports `succeeded` and `warning`
- [x] `WorkflowTimeline` uses `normalizeNodeStatus()` for icons/classes
- [x] Warning nodes get yellow warning style
- [x] Failed/blocked nodes get red error style
- [x] memory_curator fallback shows "记忆未可信"
- [x] Dark mode CSS variable support (step-warning uses var(--warning))

### Testing
- [x] Backend: 38 tests in test_v6611_workflow_timeline_semantics.py
- [x] Frontend: 60 tests in statusSemantics.test.ts
- [x] All existing tests pass (2509 backend, 60 frontend)
- [x] No sensitive data leaks in test responses

### Non-Regression
- [x] LangGraph topology unchanged
- [x] MemoryCurator extraction prompt unchanged
- [x] RunDetail not rewritten
- [x] Old timeline `status` field preserved
- [x] No destructive migration
- [x] Memory fallback doesn't block publishing

## Issues Found

None critical. All acceptance criteria met.

## Verdict

**PASS** — v6.6.11 successfully establishes node-level status semantics. The memory_curator node now correctly shows warning/fallback instead of false success green. The contract is JSON-safe, backward-compatible, and fully tested.
