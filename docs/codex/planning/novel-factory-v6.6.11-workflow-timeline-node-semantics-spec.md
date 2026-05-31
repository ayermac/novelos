# v6.6.11 Workflow Timeline & Node Semantics Closure Spec

## Problem

The workflow timeline displays `completed` (green) for all nodes that finish without crashing, even when the business result is degraded, fallback, or untrustworthy. Specifically:

1. `memory_curator` with fallback candidates shows as green "completed" — misleading users into thinking memory is reliable.
2. No node-level status field distinguishes "completed successfully" from "completed with warnings/degradation".
3. The frontend `WorkflowTimeline` only understands `completed/failed/running/pending`, no `warning/succeeded` semantics.
4. When a chapter reaches `awaiting_publish` but memory extraction fell back, the timeline looks all-green — hiding the critical memory quality issue.

## Solution

Introduce `NodeOperationResult` — a node-level status contract that separates node lifecycle status from domain-level outcome:

- **node_status**: `pending | running | succeeded | warning | failed | skipped | blocked`
- **domain_status**: Reuses `DomainStatus` from `OperationResult` (`success | fallback | degraded | failed | blocked | needs_human | pending | ignored`)
- **severity**: Display severity (`success | info | warning | error`)
- **Plus**: `retryable`, `blocking`, `next_action`, `action_label`, `user_message`, `flags`

### Core Principle

> Node `completed` ≠ business `success`. A node can complete its execution but produce a warning/fallback/degraded result.

### Memory Curator Mapping

| Memory State | Event Status | node_status | domain_status | severity |
|---|---|---|---|---|
| trusted | completed | `succeeded` | `success` | success |
| fallback | completed | `warning` | `fallback` | warning |
| degraded/missing | completed | `warning` | `degraded` | warning |
| failed | completed | `failed` | `failed` | error |
| any | failed | `failed` | `failed` | error |
| skipped | skipped | `skipped` | `ignored` | info |
| running | running | `running` | `pending` | info |

### Critical Rules

1. **Fallback must never show success green** — `memory_curator` fallback → `node_status=warning`, `severity=warning`
2. **Completed event + no trusted memory → warning** — not `succeeded`
3. **Workflow partial_success + node warning** — chapter awaiting_publish with memory fallback → workflow `partial_success` but memory_curator node `warning`
4. **Legacy fields preserved** — old `status` field remains; new fields are additive

## Changes

### Backend

1. **`novel_factory/api/contracts.py`**: Added `NodeOperationResult`, `NodeStatus`, and helper functions:
   - `node_success()`, `node_warning()`, `node_failed()`, `node_blocked()`, `node_skipped()`
   - `node_from_operation_result()`, `memory_curator_node_result()`

2. **`novel_factory/api/routes/workflow_timeline.py`**: Added `_derive_node_semantics()` that enriches each timeline node with semantic fields. Fetches `memory_status` via `get_memory_status_for_chapter()` and passes it to `_build_node_timeline()`.

### Frontend

1. **`frontend/src/lib/api.ts`**: Extended `WorkflowTimelineNode` with optional v6.6.11 fields: `node_status`, `domain_status`, `severity`, `retryable`, `blocking`, `next_action`, `action_label`, `user_message`, `flags`.

2. **`frontend/src/lib/statusSemantics.ts`**: Added `succeeded` to `NodeStatus`, `normalizeNodeStatus()`, `isNodeBusinessSuccess()`.

3. **`frontend/src/components/WorkflowTimeline.tsx`**: Uses `normalizeNodeStatus()` for icon/class derivation. Shows warning badges for `node_status=warning` nodes. Displays "记忆未可信" for fallback memory_curator. Added `step-warning` CSS class.

## Testing

- Backend: `tests/test_v6611_workflow_timeline_semantics.py` — 38 tests
- Frontend: `statusSemantics.test.ts` — 60 tests (expanded from 43)

## Non-Goals

- Does not change LangGraph topology
- Does not change MemoryCurator extraction prompt
- Does not rewrite RunDetail
- Does not do large-scale frontend UI restructuring
- Does not break old timeline fields
- Does not force memory fallback to block publishing
- Does not do destructive migration
