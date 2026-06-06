# v6.7.6 Workflow Recovery CTA Priority Fix — Spec

**Version**: 6.7.6
**Date**: 2026-05-27
**Branch**: `v6.7.6-workflow-recovery-cta-priority-fix`
**Status**: Implemented

---

## Problem Statement

When a workflow run becomes `blocked` or `failed`, the chapter status can still be `awaiting_publish` (or `reviewed`/`published`) from a previous successful run. The UI's recovery panel logic checked terminal chapter statuses before checking `run_status`, causing the UI to show "确认发布" (publish) instead of recovery actions.

Additionally, when a run is still marked `running` but has exceeded the stale threshold (>2 hours), the UI also showed "确认发布" instead of indicating the workflow is stuck.

**User-visible symptom**: Chapter card shows "确认发布" button even though the workflow is broken (blocked/failed/stale-running). The user has no way to recover without manually inspecting the run status.

---

## Root Cause

Both `state_integrity.py` (`_derive_recovery_capability()`) and `workflow_timeline.py` (`_build_recovery()`) had this order:

```
1. if chapter_status in TERMINAL_STATUSES → return PUBLISH_READY (publish)
2. ... other checks ...
```

The `run_status=blocked/failed` check came after the terminal status check, so it was never reached when the chapter was in a terminal status.

---

## Solution

Reorder the checks so `run_status` takes priority over `chapter_status`:

```
1. if run_status == "blocked" → return RESET_TO_PLANNED (reset)
2. if run_status == "failed" → return CLEAR_CHECKPOINT_AND_RERUN (reset)
3. if run_status == "running" and stale → return MANUAL_INTERVENTION_REQUIRED (mark_stuck)
4. if chapter_status in TERMINAL_STATUSES → return PUBLISH_READY (publish)
```

### Affected Files

**Round 1 — Backend recovery state priority:**

| File | Function | Change |
|---|---|---|
| `novel_factory/workflow/state_integrity.py` | `_derive_recovery_capability()` | Add blocked/failed/stale-running checks before terminal status block |
| `novel_factory/workflow/state_integrity.py` | `derive_workflow_recovery_state()` | Detect stale running via `_run_is_recent()` and pass `running_stale` flag |
| `novel_factory/api/routes/workflow_timeline.py` | `_build_recovery()` | Add blocked/failed check before terminal status block |

**Round 2 — Publish CTA must respect recovery priority:**

| File | Change |
|---|---|
| `frontend/src/components/project/AuthorAgentPanel.tsx` | Added `workflowNeedsRecovery` boolean; hide publish cards for `reviewed`/`awaiting_publish` when workflow is broken, show "需要先恢复运行" with recovery link |
| `frontend/src/components/project/AuthorWritingSurface.tsx` | Added `workflowNeedsRecovery` boolean; hide header "确认发布" button when workflow is broken |
| `novel_factory/api/routes/run.py` | Added backend guard in `publish_chapter` returning `WORKFLOW_RECOVERY_REQUIRED` when latest run is blocked/failed/stale-running |

---

## Recovery State Matrix

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

## Acceptance Criteria

### Round 1 — Workflow panel recovery priority

1. `blocked + awaiting_publish` → shows reset button, NOT publish
2. `blocked + reviewed` → shows reset button, NOT publish
3. `blocked + published` → shows reset button, NOT publish
4. `failed + awaiting_publish` → shows reset button, NOT publish
5. `running(stale) + awaiting_publish` → shows mark_stuck button, NOT publish
6. `completed + awaiting_publish` → shows publish button (unchanged)
7. `completed + reviewed` → shows publish button (unchanged)
8. `None + awaiting_publish` → shows publish button (unchanged)
9. All existing tests continue to pass (1841+)

### Round 2 — All publish CTAs respect recovery priority

10. Header publish button hidden when `run_status=blocked` + `reviewed`
11. Header publish button hidden when `run_status=running` + `is_stale` + `reviewed`
12. Agent panel publish card hidden when `run_status=blocked` + `awaiting_publish`, shows "需要先恢复运行"
13. Agent panel publish card hidden when `run_status=failed` + `reviewed`, shows "需要先恢复运行"
14. `POST /api/publish/chapter` returns `WORKFLOW_RECOVERY_REQUIRED` when latest run is `blocked`
15. `POST /api/publish/chapter` returns `WORKFLOW_RECOVERY_REQUIRED` when latest run is `failed`
16. `POST /api/publish/chapter` returns `WORKFLOW_RECOVERY_REQUIRED` when latest run is stale-running (>2h)
17. `POST /api/publish/chapter` allows publish when latest run is `completed` or recent-running

---

## Tests

**Backend:**
- `tests/test_v676_workflow_recovery_cta_priority.py` — 9 tests for recovery state derivation
- `tests/test_v676_publish_guard.py` — 6 tests for publish endpoint guard (blocked/failed/stale-running/completed/no-run)

**Frontend:**
- `frontend/src/components/project/__tests__/v676-recovery-cta-priority.test.tsx` — 9 tests:
  - 4 workflow panel recovery CTA (blocked/failed/stale-running/completed + awaiting_publish)
  - 2 header publish button (blocked/stale-running + reviewed)
  - 3 agent panel publish card (blocked + awaiting_publish, failed + reviewed, completed + reviewed)

---

## Out of Scope

- Changing the `blocking` chapter_status handling (already correct)
- Modifying checkpoint staleness detection logic
