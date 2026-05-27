# Novel Factory v6.7.6 Workflow Recovery CTA Priority Fix - Completion Report

**Version**: 6.7.6
**Branch**: `codex-v6.7.6-workflow-recovery-cta-priority`
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

## Files Changed

| File | Change |
|---|---|
| `novel_factory/version.py` | Version bump to 6.7.6 |
| `novel_factory/workflow/state_integrity.py` | Blocked/failed run priority over terminal statuses |
| `novel_factory/api/routes/workflow_timeline.py` | Blocked/failed run priority over terminal statuses |
| `frontend/package.json` | Version bump to 6.7.6 |
| `desktop/package.json` | Version bump to 6.7.6 |
| `tests/test_v676_workflow_recovery_cta_priority.py` | New: 9 tests for recovery CTA priority |
