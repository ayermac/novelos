# v6.6.11 Workflow Timeline & Node Semantics Closure — Completion Report

## Version

- **Baseline**: v6.6.10 API Contract & Frontend State Semantics Closure
- **New baseline**: v6.6.11 Workflow Timeline & Node Semantics Closure
- **Runtime version**: `6.6.11` (`novel_factory/version.py`)

## Summary

Established unified node-level status semantics for the workflow timeline, ensuring each node accurately conveys whether it truly succeeded, produced warnings, degraded, or failed. The critical `memory_curator` node now correctly shows warning/fallback instead of success green when memory extraction did not produce trusted results.

## New Node-Level Contract Fields

Added `NodeOperationResult` in `novel_factory/api/contracts.py`:

| Field | Type | Description |
|---|---|---|
| `node_name` | `str` | Workflow node identifier |
| `node_status` | `NodeStatus` | `pending \| running \| succeeded \| warning \| failed \| skipped \| blocked` |
| `domain_status` | `DomainStatus` | Business outcome (`success \| fallback \| degraded \| failed \| blocked \| needs_human \| pending \| ignored`) |
| `severity` | `Severity` | Display severity (`success \| info \| warning \| error`) |
| `message` | `str` | Internal message |
| `user_message` | `str` | User-facing message |
| `retryable` | `bool` | Whether the node can be re-executed |
| `blocking` | `bool` | Whether this blocks downstream |
| `next_action` | `str \| None` | Recommended next action |
| `action_label` | `str \| None` | Human-readable action label |
| `flags` | `dict[str, bool]` | Semantic flags |
| `details` | `dict[str, Any]` | Additional details |

### Helper Functions

- `node_success(node_name, ...)` → `succeeded/success`
- `node_warning(node_name, ...)` → `warning/{fallback|degraded}`
- `node_failed(node_name, ...)` → `failed/failed`
- `node_blocked(node_name, ...)` → `blocked/blocked`
- `node_skipped(node_name, ...)` → `skipped/ignored`
- `node_from_operation_result(node_name, op_result)` → maps `OperationResult` to `NodeOperationResult`
- `memory_curator_node_result(memory_status, event_status, ...)` → specialized for memory_curator

## Workflow Timeline API Fields (Added)

`GET /api/projects/{project_id}/chapters/{chapter_number}/workflow-timeline` now returns per-node:

| Field | Description |
|---|---|
| `node_status` | Node lifecycle status |
| `domain_status` | Business outcome |
| `severity` | Display severity |
| `retryable` | Can be re-executed |
| `blocking` | Blocks downstream |
| `next_action` | Recommended action |
| `action_label` | Action label |
| `user_message` | User-facing message |
| `flags` | Semantic flags |

Legacy `status` field remains unchanged for backward compatibility.

## Memory Curator Status Mapping

| Memory State | Event Status | node_status | domain_status | severity | UI Display |
|---|---|---|---|---|---|
| trusted extraction | completed | `succeeded` | `success` | success | Green ✓ |
| fallback candidate | completed | `warning` | `fallback` | warning | Yellow ⚠ "记忆未可信" |
| degraded no-op | completed | `warning` | `degraded` | warning | Yellow ⚠ "降级" |
| failed (no memory) | completed | `failed` | `failed` | error | Red ✗ |
| explicit failure | failed | `failed` | `failed` | error | Red ✗ |
| skipped | skipped | `skipped` | `ignored` | info | Grey ○ |
| running | running | `running` | `pending` | info | Blue ● |
| missing + completed event | completed | `warning` | `degraded` | warning | Yellow ⚠ |

## Frontend Changes

1. **`statusSemantics.ts`**: Added `succeeded` to `NodeStatus`, `normalizeNodeStatus()`, `isNodeBusinessSuccess()`
2. **`WorkflowTimeline.tsx`**: Uses `normalizeNodeStatus()` for icons/classes, shows warning badges for warning nodes, "记忆未可信" for fallback memory_curator, added `step-warning` CSS class
3. **`api.ts`**: Extended `WorkflowTimelineNode` with optional v6.6.11 fields

## Test Results

### Backend
- `tests/test_v6611_workflow_timeline_semantics.py`: **38 passed**
- `tests/test_v6610_api_contract_semantics.py`: **passed**
- `tests/test_v58_workflow_observability.py`: **passed**
- `tests/test_v667_memory_curator_reliability.py`: **29 passed**
- Full suite: **2509 passed, 0 failed**

### Frontend
- `statusSemantics.test.ts`: **60 passed** (expanded from 43)
- typecheck: **passed**
- lint: **passed**
- build: **passed**

## Files Changed

### Backend
- `novel_factory/api/contracts.py` — Added `NodeOperationResult`, helpers
- `novel_factory/api/routes/workflow_timeline.py` — Added `_derive_node_semantics()`, enriched timeline nodes
- `novel_factory/version.py` — `6.6.10` → `6.6.11`

### Frontend
- `frontend/src/lib/api.ts` — Extended `WorkflowTimelineNode`
- `frontend/src/lib/statusSemantics.ts` — Added node-level helpers
- `frontend/src/components/WorkflowTimeline.tsx` — Warning/fallback display
- `frontend/package.json` — `6.6.10` → `6.6.11`

### Tests
- `tests/test_v6611_workflow_timeline_semantics.py` — New, 38 tests
- `frontend/src/lib/statusSemantics.test.ts` — Expanded, 60 tests

### Documentation
- `docs/codex/specs/novel-factory-v6.6.11-workflow-timeline-node-semantics-spec.md`
- `docs/codex/reports/novel-factory-v6.6.11-completion-report.md`
- `docs/codex/reviews/novel-factory-v6.6.11-review.md`

## Known Risks / Not Yet Integrated

1. **SSE stream events**: The `/workflow-stream` SSE endpoint does not yet include `node_status`/`domain_status` fields in event payloads — only timeline nodes are enriched.
2. **RunDetail**: The run detail panel still uses the old status model; node-level semantics are only in the timeline view.
3. **Other nodes**: Only `memory_curator` has specialized domain-aware derivation. Other nodes (planner, author, etc.) currently derive semantics from event status only; they could benefit from domain-specific logic in the future.
4. **Workflow-level domain_result in timeline**: The timeline endpoint doesn't yet return a top-level `domain_result` for the whole workflow run (only per-node).
