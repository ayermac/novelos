# v6.6.6 Workflow Recovery & State Integrity Closure - Implementation Plan

## Overview

**Goal**: Establish a clear, testable workflow state consistency and recovery action system that ensures "chapter status, workflow run status, checkpoint status, and page recommended actions" are all consistent.

**Current Baseline**: v6.6.5 Runtime Hygiene & Observability Closure (2268/2268 pytest passing)

**Target**: v6.6.6 with full state integrity guarantees and recovery action clarity.

---

## Implementation Phases

### Phase A: State Matrix Definition (Core Foundation)

**File**: `novel_factory/workflow/state_integrity.py` (NEW)

**Purpose**: Define a pure function `derive_workflow_recovery_state()` that computes the canonical recovery state from chapter status, run status, and checkpoint state.

**Implementation**:

```python
# Data structures
class RecoveryCapability(StrEnum):
    NO_RECOVERY_NEEDED = "no_recovery_needed"
    RESUME_FROM_CHECKPOINT = "resume_from_checkpoint"
    CLEAR_CHECKPOINT_AND_RERUN = "clear_checkpoint_and_rerun"
    RESET_TO_PLANNED = "reset_to_planned"
    REOPEN_REVISION = "reopen_revision"
    PUBLISH_READY = "publish_ready"
    MANUAL_INTERVENTION_REQUIRED = "manual_intervention_required"

class WorkflowRecoveryState(BaseModel):
    chapter_status: str
    run_status: Optional[str]
    checkpoint_state: str  # exists, absent, stale, resumable
    recovery_capability: RecoveryCapability
    safe_actions: List[str]  # UI action buttons
    recovery_hint: str  # User-facing explanation
    requires_manual_intervention: bool
    checkpoint_thread_id: Optional[str]
    stale_reason: Optional[str]  # Why checkpoint is stale

def derive_workflow_recovery_state(
    chapter_status: str,
    run_status: Optional[str],
    run_updated_at: Optional[datetime],
    checkpoint_exists: bool,
    checkpoint_node: Optional[str],
    checkpoint_chapter_status: Optional[str],
    checkpoint_age_seconds: Optional[float],
    has_active_run: bool,
) -> WorkflowRecoveryState:
    """
    Pure function that derives recovery state from inputs.
    No side effects, fully testable.
    """
```

**State Matrix Logic**:

| Chapter Status | Run Status | Checkpoint State | Recovery Capability | Safe Actions |
|----------------|------------|------------------|---------------------|--------------|
| planned | - | absent | no_recovery_needed | ["generate"] |
| scripted | completed | absent | no_recovery_needed | ["generate"] |
| drafted | completed | absent | no_recovery_needed | ["generate"] |
| polished | completed | absent | no_recovery_needed | ["generate"] |
| review | completed | absent | no_recovery_needed | ["generate"] |
| reviewed | completed | absent | publish_ready | ["publish"] |
| awaiting_publish | completed | absent | publish_ready | ["publish"] |
| published | - | absent | no_recovery_needed | ["create_revision_draft"] |
| revision | - | absent | reopen_revision | ["reopen_revision"] |
| blocking | - | absent | manual_intervention_required | ["view_detail", "reset"] |
| * | running | resumable | resume_from_checkpoint | ["resume", "view_detail"] |
| * | running | stale | clear_checkpoint_and_rerun | ["rerun", "view_detail"] |
| * | failed | exists | clear_checkpoint_and_rerun | ["rerun"] |
| * | blocked | exists | reset_to_planned | ["reset", "view_detail"] |
| * | cancelled | exists | clear_checkpoint_and_rerun | ["rerun"] |

**Stale Checkpoint Detection**:
```python
def _is_checkpoint_stale(
    run_status: Optional[str],
    checkpoint_node: Optional[str],
    checkpoint_chapter_status: Optional[str],
    current_chapter_status: str,
    checkpoint_age_seconds: Optional[float],
) -> tuple[bool, Optional[str]]:
    """
    Returns (is_stale, reason).
    
    Stale conditions:
    1. Run is not running AND checkpoint exists
    2. Checkpoint node doesn't match expected workflow stage
    3. Checkpoint chapter_status doesn't match current chapter status
    4. Checkpoint age > STALE_CHECKPOINT_SECONDS (default 7 days)
    """
```

**Dependencies**: None (pure function module)

**Testing**: Unit tests for all state matrix combinations (13+ test cases)

---

### Phase B: Run Detail Recommended Actions Fix

**Files**:
- `novel_factory/api/routes/runs.py` (MODIFY)
- `frontend/src/pages/RunDetail.tsx` (MODIFY)

**Changes**:

1. **Backend** (`runs.py`):
   - Import `derive_workflow_recovery_state` from `state_integrity.py`
   - Refactor `_build_recovery_state()` to use the new pure function
   - Add `checkpoint_state` field to recovery response
   - Ensure `safe_actions` list is populated correctly

2. **Frontend** (`RunDetail.tsx`):
   - Update `RunRecovery` interface to include `checkpoint_state` and `safe_actions`
   - Render action buttons based on `safe_actions` array
   - Show `recovery_hint` as user-facing explanation
   - Hide buttons not in `safe_actions` list

**API Response Structure**:
```json
{
  "recovery_state": {
    "chapter_status": "drafted",
    "run_status": "failed",
    "checkpoint_state": "stale",
    "recovery_capability": "clear_checkpoint_and_rerun",
    "safe_actions": ["rerun", "view_detail"],
    "recovery_hint": "Run failed with stale checkpoint. Rerun recommended.",
    "requires_manual_intervention": false,
    "checkpoint_thread_id": "thread-123",
    "stale_reason": "Run status is failed"
  }
}
```

**Dependencies**: Phase A

---

### Phase C: Checkpoint Consistency & Cleanup

**Files**:
- `novel_factory/workflow/checkpoint.py` (MODIFY)
- `novel_factory/workflow/runner.py` (MODIFY)
- `novel_factory/api/routes/runs.py` (MODIFY)

**Changes**:

1. **checkpoint.py**:
   - Add `get_checkpoint_age_seconds()` function
   - Add `get_checkpoint_node()` function
   - Add `get_checkpoint_chapter_status()` function
   - Enhance `inspect_checkpoint_thread()` to return age and metadata

2. **runner.py**:
   - Enhance `_clear_stale_checkpoint_for_new_run()` to use stale detection logic
   - Add `cleanup_stale_checkpoints_for_chapter()` function
   - Log checkpoint cleanup actions

3. **runs.py**:
   - Add `/runs/{run_id}/recovery/cleanup-checkpoint` endpoint
   - Call cleanup logic when user confirms checkpoint cleanup

**Stale Detection Logic**:
```python
STALE_CHECKPOINT_SECONDS = 7 * 24 * 60 * 60  # 7 days

def is_checkpoint_stale_for_run(
    run: WorkflowRun,
    checkpoint_thread_id: Optional[str],
    db_path: str,
) -> tuple[bool, Optional[str]]:
    """
    Determine if checkpoint is stale for a given run.
    Returns (is_stale, reason).
    """
```

**Dependencies**: Phase A

---

### Phase D: Local Edit/Polish State Protection

**Files**:
- `novel_factory/api/routes/versions.py` (MODIFY)
- `novel_factory/workflow/state_integrity.py` (MODIFY)

**Changes**:

1. **versions.py**:
   - Modify `save_chapter_content()` to check if chapter is in local edit state
   - Prevent status transition to `blocking` if chapter is in `awaiting_publish`, `reviewed`, or `published`
   - Add `_is_local_edit_state()` helper function
   - Store local edit flag in chapter metadata

2. **state_integrity.py**:
   - Add `is_local_edit_state()` function
   - Adjust recovery state derivation to respect local edit protection

**Protected States**:
```python
LOCAL_EDIT_PROTECTED_STATUSES = {
    "awaiting_publish",
    "reviewed", 
    "published"
}

def is_local_edit_state(chapter_status: str, has_local_edit: bool) -> bool:
    """Check if chapter is in local edit state that should not enter main workflow blocking."""
    return chapter_status in LOCAL_EDIT_PROTECTED_STATUSES and has_local_edit
```

**Dependencies**: Phase A

---

### Phase E: Manual Block Recovery Path

**Files**:
- `novel_factory/api/routes/runs.py` (MODIFY)
- `novel_factory/workflow/state_integrity.py` (MODIFY)

**Changes**:

1. **state_integrity.py**:
   - Add `derive_manual_block_recovery_suggestions()` function
   - Return specific recovery hints for blocking state

2. **runs.py**:
   - Enhance `/runs/{run_id}/recovery` endpoint to return detailed suggestions
   - Add suggested actions for manual intervention cases

**Recovery Suggestions**:
```python
def derive_manual_block_recovery_suggestions(
    chapter_status: str,
    run_status: Optional[str],
    last_error: Optional[str],
    checkpoint_node: Optional[str],
) -> List[str]:
    """
    Return specific recovery suggestions for blocking state.
    
    Examples:
    - "Reset chapter to planned status and rerun"
    - "Clear checkpoint and rerun from scratch"
    - "Contact support with run_id for investigation"
    """
```

**Dependencies**: Phase A

---

### Phase F: API/Frontend Refresh Consistency

**Files**:
- `novel_factory/api/routes/workflow_timeline.py` (MODIFY)
- `frontend/src/components/project/ChapterWorkspace.tsx` (MODIFY)

**Changes**:

1. **workflow_timeline.py**:
   - Ensure `/workflow-stream` SSE returns consistent state after each node completion
   - Include `recovery_state` in SSE events
   - Fix race condition between run status update and checkpoint write

2. **ChapterWorkspace.tsx**:
   - Update polling logic to use SSE stream for real-time updates
   - Debounce refresh requests during active workflow execution
   - Show consistent action buttons based on `safe_actions`

**SSE Event Structure**:
```json
{
  "event": "node_completed",
  "data": {
    "node": "author",
    "chapter_status": "drafted",
    "run_status": "running",
    "recovery_state": {
      "checkpoint_state": "resumable",
      "recovery_capability": "resume_from_checkpoint",
      "safe_actions": ["resume", "view_detail"]
    }
  }
}
```

**Dependencies**: Phase A, Phase B

---

### Phase G: Documentation

**Files**:
- `docs/codex/planning/novel-factory-v6.6.6-workflow-state-integrity-spec.md` (NEW)
- `docs/codex/reports/novel-factory-v6.6.6-completion-report.md` (NEW)
- `docs/codex/reviews/novel-factory-v6.6.6-review.md` (NEW)

**Content**:
1. **Spec**: Detailed requirements and state matrix definition
2. **Completion Report**: Implementation summary, test results, changes made
3. **Review**: Validation of state integrity guarantees, edge cases covered

**Dependencies**: All implementation phases complete

---

### Phase H: Testing

**File**: `tests/test_v666_workflow_state_integrity.py` (NEW)

**Required Test Cases**:

1. `test_state_matrix_planned_no_run` - planned status with no run
2. `test_state_matrix_running_resumable_checkpoint` - running with resumable checkpoint
3. `test_state_matrix_running_stale_checkpoint` - running with stale checkpoint
4. `test_state_matrix_failed_with_checkpoint` - failed run with checkpoint
5. `test_state_matrix_blocked_with_checkpoint` - blocked run with checkpoint
6. `test_state_matrix_reviewed_ready_to_publish` - reviewed status ready to publish
7. `test_state_matrix_revision_state` - revision status recovery
8. `test_state_matrix_blocking_manual_intervention` - blocking status manual intervention
9. `test_stale_checkpoint_detection_by_age` - checkpoint age > 7 days
10. `test_stale_checkpoint_detection_by_status_mismatch` - checkpoint chapter_status mismatch
11. `test_local_edit_state_protection` - local edit doesn't enter blocking
12. `test_checkpoint_cleanup_after_recovery` - checkpoint cleanup works
13. `test_api_recovery_state_consistency` - API returns consistent recovery state

**Additional Tests**:
- Regression tests for existing workflow execution
- Integration tests for API endpoints
- Frontend component tests for action button rendering

**Dependencies**: All implementation phases complete

---

## Implementation Order

```
Phase A (State Matrix Definition)
    ↓
Phase B (Run Detail API Fix) + Phase C (Checkpoint Cleanup) + Phase D (Local Edit Protection)
    ↓
Phase E (Manual Block Recovery) + Phase F (Refresh Consistency)
    ↓
Phase G (Documentation) + Phase H (Testing)
```

**Parallel Execution Opportunities**:
- Phase B, C, D can be implemented in parallel after Phase A
- Phase E, F can be implemented in parallel after Phase B, C, D
- Phase G, H can be implemented in parallel after all implementation phases

---

## Success Criteria

1. **State Consistency**: Chapter status, run status, checkpoint state, and recommended actions are always consistent
2. **Recovery Clarity**: Users always know what actions are safe to take
3. **Stale Detection**: Stale checkpoints are detected and cleaned up correctly
4. **Local Edit Protection**: Local edits don't pollute main workflow blocking state
5. **Test Coverage**: All 13 required test cases pass + regression tests pass
6. **Documentation**: Spec, completion report, and review documents are complete

---

## Risk Mitigation

1. **Backward Compatibility**: Ensure existing workflows continue to work
2. **Migration Path**: Provide clear path for existing chapters with inconsistent state
3. **Performance**: Stale detection should not impact workflow execution performance
4. **Edge Cases**: Handle all edge cases in state matrix (e.g., cancelled runs, missing checkpoints)

---

## Estimated Effort

- Phase A: 4-6 hours (core logic + unit tests)
- Phase B: 2-3 hours (API + frontend changes)
- Phase C: 3-4 hours (checkpoint cleanup logic)
- Phase D: 2-3 hours (local edit protection)
- Phase E: 1-2 hours (manual block recovery)
- Phase F: 2-3 hours (refresh consistency)
- Phase G: 2-3 hours (documentation)
- Phase H: 4-6 hours (testing + regression)

**Total**: 20-30 hours

---

## Next Steps

1. Review and approve this implementation plan
2. Begin Phase A: Create `novel_factory/workflow/state_integrity.py`
3. Implement state matrix logic and unit tests
4. Proceed with subsequent phases in dependency order
