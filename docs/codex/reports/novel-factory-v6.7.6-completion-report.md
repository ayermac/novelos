# Novel Factory v6.7.6 Workflow Recovery CTA Priority Fix - Completion Report

**Version**: 6.7.6
**Branch**: `v6.7.6-workflow-recovery-cta-priority-fix`
**Date**: 2026-05-27
**Status**: Completed

---

## Summary

Fixed a bug where `run_status=blocked` or `run_status=failed` combined with terminal chapter statuses (`awaiting_publish`, `reviewed`, `published`) incorrectly showed "确认发布" (publish) instead of recovery actions (reset/mark_stuck). The root cause was that terminal status checks in both `state_integrity.py` and `workflow_timeline.py` took priority over `run_status=blocked/failed`, hiding the broken workflow state from the user.

---

## Problem

When a workflow run becomes `blocked` or `failed`, the chapter status can still be `awaiting_publish` (or `reviewed`/`published`) from a previous successful run. The UI's recovery panel logic checked terminal chapter statuses before checking `run_status`, causing:

1. `awaiting_publish` + `run_status=blocked` → showed "确认发布" (wrong)
2. `reviewed` + `run_status=blocked` → showed "确认发布" (wrong)
3. `published` + `run_status=blocked` → showed "确认发布" (wrong)
4. `awaiting_publish` + `run_status=failed` → showed "确认发布" (wrong)

The user had no way to recover the broken workflow without manually inspecting the run status.

---

## Solution

Added blocked/failed run status checks **before** the terminal chapter status checks in both backend files, so recovery actions take priority when the workflow is broken.

### 1. `state_integrity.py` — `_derive_recovery_capability()`

**File**: `novel_factory/workflow/state_integrity.py`

Added blocked/failed run override before the `TERMINAL_STATUSES` block:

- `run_status == "blocked"` → `RESET_TO_PLANNED` (or `MANUAL_INTERVENTION_REQUIRED` if checkpoint is stale)
- `run_status == "failed"` → `CLEAR_CHECKPOINT_AND_RERUN`

Both return safe actions: `["view_content", "view_detail", "reset"]`

### 2. `workflow_timeline.py` — `_build_recovery()`

**File**: `novel_factory/api/routes/workflow_timeline.py`

Added blocked/failed run check before the `terminal_statuses` block:

- `run_status in ("blocked", "failed")` → returns recovery payload with `reset_chapter` action
- Includes `view_artifacts`, `view_content`, optional `retry_node`, and `reset_chapter` safe actions

### 3. Version Bumps

- `novel_factory/version.py`: `__version__` → "6.7.6"
- `frontend/package.json`: version → "6.7.6"
- `desktop/package.json`: version → "6.7.6"

---

## Recovery State Matrix (v6.7.6)

| chapter_status | run_status | checkpoint | recovery_capability | recommended_action |
|---|---|---|---|---|
| awaiting_publish | blocked | exists | RESET_TO_PLANNED | reset |
| awaiting_publish | blocked | stale | MANUAL_INTERVENTION_REQUIRED | reset |
| reviewed | blocked | exists | RESET_TO_PLANNED | reset |
| published | blocked | exists | RESET_TO_PLANNED | reset |
| awaiting_publish | failed | exists | CLEAR_CHECKPOINT_AND_RERUN | reset |
| awaiting_publish | running (stale) | — | MANUAL_INTERVENTION_REQUIRED | mark_stuck |
| awaiting_publish | completed | — | PUBLISH_READY | publish |
| reviewed | completed | — | PUBLISH_READY | publish |
| awaiting_publish | None | — | PUBLISH_READY | publish |

---

## Tests

**File**: `tests/test_v676_workflow_recovery_cta_priority.py`

9 tests covering:
- Blocked run + awaiting_publish/reviewed/published → shows reset (3 tests)
- Failed run + awaiting_publish → shows reset (1 test)
- Healthy completed run + awaiting_publish/reviewed → shows publish (2 tests)
- No run + awaiting_publish → shows publish (1 test)
- Stale running run + terminal status → shows publish (1 test)
- Blocked run + stale checkpoint → shows reset with MANUAL_INTERVENTION_REQUIRED (1 test)

All 9 tests pass. Full regression: 1841 passed, 1 pre-existing failure (unrelated).

---

## Round 2: Publish CTA Must Respect Recovery Priority

Even after round 1 fixed the workflow panel recovery actions, the publish CTAs in other locations still showed "确认发布" when the workflow was broken:

1. **Header publish button** (`AuthorWritingSurface.tsx`) — showed for `reviewed` status regardless of run_status
2. **AI agent panel publish card** (`AuthorAgentPanel.tsx`) — showed for `reviewed` and `awaiting_publish` regardless of run_status
3. **Backend publish endpoint** (`run.py`) — accepted publish even when latest run was blocked/failed/stale

### Round 2 Changes

| File | Change |
|---|---|
| `frontend/src/components/project/AuthorAgentPanel.tsx` | Added `workflowNeedsRecovery` boolean; hide publish cards and show "需要先恢复运行" when workflow is broken |
| `frontend/src/components/project/AuthorWritingSurface.tsx` | Added `workflowNeedsRecovery` boolean; hide header publish button when workflow is broken |
| `novel_factory/api/routes/run.py` | Added backend guard in `publish_chapter` returning `WORKFLOW_RECOVERY_REQUIRED` when latest run is blocked/failed/stale-running |
| `tests/test_v676_publish_guard.py` | New: 6 tests for publish endpoint guard |
| `frontend/src/components/project/__tests__/v676-recovery-cta-priority.test.tsx` | Extended: 5 new tests for header and agent panel publish CTA |
| `CHANGELOG.md` | Updated with round 2 entries |

### Round 2 Verification

- Backend publish guard tests: 6/6 passing
- Frontend CTA tests: 9/9 passing (4 existing + 5 new)
- TypeScript typecheck: passing

---

## Files Changed (Complete)

| File | Change |
|---|---|
| `novel_factory/version.py` | Version bump to 6.7.6 |
| `novel_factory/workflow/state_integrity.py` | Blocked/failed run priority over terminal statuses |
| `novel_factory/api/routes/workflow_timeline.py` | Blocked/failed run priority over terminal statuses |
| `novel_factory/api/routes/run.py` | Backend publish guard for blocked/failed/stale runs |
| `frontend/package.json` | Version bump to 6.7.6 |
| `desktop/package.json` | Version bump to 6.7.6 |
| `frontend/src/components/project/AuthorAgentPanel.tsx` | `workflowNeedsRecovery` — hide publish cards when broken |
| `frontend/src/components/project/AuthorWritingSurface.tsx` | `workflowNeedsRecovery` — hide header publish button when broken |
| `tests/test_v676_workflow_recovery_cta_priority.py` | 9 tests for recovery state derivation |
| `tests/test_v676_publish_guard.py` | 6 tests for publish endpoint guard |
| `frontend/src/components/project/__tests__/v676-recovery-cta-priority.test.tsx` | 9 tests for frontend CTA priority |
