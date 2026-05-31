# v6.6.6 Workflow Recovery & State Integrity Closure

**Version**: 6.6.6
**Status**: Completed
**Baseline**: v6.6.5 Runtime Hygiene & Observability Closure

## Problem Statement

Before v6.6.6, workflow recovery actions were computed inconsistently across different API endpoints:
- `runs.py` had its own recovery logic
- `workflow_timeline.py` had different recovery logic
- `production.py` had yet another set of heuristics

This led to:
1. **UI Inconsistency**: Action buttons showed different options depending on which API was called
2. **Unsafe Actions**: Some recovery actions were recommended for inconsistent states
3. **Local Edit Pollution**: Local edits on `awaiting_publish`/`reviewed` chapters could enter main workflow blocking state
4. **Stale Checkpoints**: No systematic detection of stale checkpoints from failed/old runs

## Solution

### A. Pure Function: `derive_workflow_recovery_state()`

Created `novel_factory/workflow/state_integrity.py` with a **pure function** that derives canonical recovery state:

```python
def derive_workflow_recovery_state(
    *,
    chapter: dict | None,
    latest_run: dict | None,
    checkpoint_info: dict | None,
    has_existing_content: bool = False,
    is_local_edit: bool = False,
) -> dict[str, Any]:
```

**Key Properties**:
- No side effects (pure function)
- Fully testable with explicit inputs
- Single source of truth for UI actions

### B. Recovery Capability Enum

```python
class RecoveryCapability(str, Enum):
    NO_RECOVERY_NEEDED = "no_recovery_needed"
    PUBLISH_READY = "publish_ready"
    RESUME_FROM_CHECKPOINT = "resume_from_checkpoint"
    CLEAR_CHECKPOINT_AND_RERUN = "clear_checkpoint_and_rerun"
    RESET_TO_PLANNED = "reset_to_planned"
    REOPEN_REVISION = "reopen_revision"
    MANUAL_INTERVENTION_REQUIRED = "manual_intervention_required"
```

### C. Checkpoint State Classification

```python
class CheckpointState(str, Enum):
    ABSENT = "absent"
    EXISTS = "exists"
    STALE = "stale"
    RESUMABLE = "resumable"
```

**Stale Detection Rules**:
1. Run status is not `running`/`blocked` but checkpoint exists
2. Checkpoint node doesn't match current run node
3. Checkpoint node doesn't match expected workflow stage
4. Checkpoint age exceeds 7 days threshold
5. Running run exceeds 2-hour resumable window

### D. State Matrix

| chapter_status | run_status | checkpoint_state | recovery_capability |
|---------------|------------|------------------|---------------------|
| planned | None | absent | NO_RECOVERY_NEEDED |
| planned | running | resumable | RESUME_FROM_CHECKPOINT |
| planned | running | stale | CLEAR_CHECKPOINT_AND_RERUN |
| drafted | running | resumable | RESUME_FROM_CHECKPOINT |
| drafted | running | stale | CLEAR_CHECKPOINT_AND_RERUN |
| drafted | failed | stale | CLEAR_CHECKPOINT_AND_RERUN |
| blocking | blocked | exists | RESET_TO_PLANNED |
| blocking | blocked | stale | MANUAL_INTERVENTION_REQUIRED |
| blocking | running | stale | CLEAR_CHECKPOINT_AND_RERUN |
| reviewed | completed | absent | PUBLISH_READY |
| awaiting_publish | completed | absent | PUBLISH_READY |
| published | completed | absent | NO_RECOVERY_NEEDED |
| revision | completed | absent | REOPEN_REVISION |

### E. Local Edit Protection

```python
LOCAL_EDIT_PROTECTED_STATUSES = frozenset({"awaiting_publish", "reviewed", "published"})

def should_protect_from_blocking(chapter_status: str, is_local_edit: bool) -> bool:
    """Prevent local edits from entering main workflow blocking state."""
```

**Protection Rules**:
- Local edit on `awaiting_publish` → stays `awaiting_publish` (no blocking)
- Local edit on `reviewed` → stays `reviewed` (no blocking)
- Local edit on `published` → stays `published` (no blocking)

### F. API Integration

**Modified Endpoints**:

1. `GET /api/runs/{run_id}` - Added `recovery_state` field
2. `GET /api/runs/{run_id}/recovery` - Uses canonical `recovery_state`
3. `GET /api/projects/{id}/chapters/{num}/workflow-timeline` - Added `recovery_state` to recovery field

**Response Structure**:
```json
{
  "recovery_state": {
    "current_stage": "已起草 · 执笔中",
    "is_consistent": true,
    "recovery_capability": "resume_from_checkpoint",
    "recommended_action": "resume",
    "blocking_reason": null,
    "safe_actions": ["view_detail", "resume"],
    "checkpoint_status": "resumable",
    "chapter_status": "drafted",
    "run_status": "running",
    "run_id": "run-123",
    "checkpoint_thread_id": "proj-chapter-1",
    "stale_reason": null,
    "recovery_hint": "工作流运行中，可从检查点恢复。"
  }
}
```

### G. Runner Enhancement

Enhanced `_clear_stale_checkpoint_for_new_run()` in `runner.py`:
- Uses `state_integrity` module for stale detection
- Logs workflow node events for cleanup actions
- Clearer explanatory logging

### H. Versions Protection

Modified `versions.py`:
- Added `is_local_edit: bool = False` to `SaveContentRequest`
- Uses `should_protect_from_blocking()` to prevent status transitions
- Local edits on protected chapters don't change status

## Testing

**Test File**: `tests/test_v666_workflow_state_integrity.py`

**Coverage**:
- 20 test cases covering state matrix combinations
- Local edit protection tests
- Checkpoint stale detection tests
- API integration tests

**Results**: 20/20 passed, 2294/2294 total tests passing

## Constraints Respected

1. ✅ No changes to LangGraph topology
2. ✅ No rewrite of `production.py` (only uses `recovery_state` for recommendations)
3. ✅ Local edits not connected to main workflow
4. ✅ All behavior changes have test coverage

## Files Modified

| File | Changes |
|------|---------|
| `novel_factory/workflow/state_integrity.py` | NEW - Core module |
| `novel_factory/api/routes/runs.py` | Added `recovery_state` to run detail |
| `novel_factory/api/routes/workflow_timeline.py` | Added `recovery_state` to recovery |
| `novel_factory/workflow/runner.py` | Enhanced stale checkpoint detection |
| `novel_factory/api/routes/versions.py` | Local edit protection |
| `novel_factory/version.py` | Version bump to 6.6.6 |
| `tests/test_v666_workflow_state_integrity.py` | NEW - Test coverage |

## Migration Notes

No database migrations required. All changes are backward compatible.

## Future Work

- Phase E: Frontend RunDetail/WorkflowPanel adjustments (optional)
- Phase F: production-next consistency (optional)
