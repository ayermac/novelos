# Novel Factory v5.5.5: Autonomous Production Runner

**Status**: ✅ Completed  
**Branch**: `codex-v5.5-production-reliability`  
**Baseline**: v5.5.4 Real LLM Autonomous Planning (5d0ae9f)  
**Completion**: 2026-05-05

---

## Overview

v5.5.5 implements an autonomous production runner that automatically executes production steps based on `production-next` recommendations. This enables hands-off chapter generation workflows with configurable stop conditions and safety guards.

---

## Goals

1. **Automate Production Workflow**: Execute production steps automatically without manual intervention
2. **Configurable Limits**: Support max_steps, chapter ranges, and dry-run preview
3. **Safety Guards**: Never auto-publish in real mode, stop on human-review requirements
4. **Error Recovery**: Track step execution history and provide actionable error codes
5. **Frontend Integration**: Add Auto Production Console UI for one-click autonomous production

---

## Implementation

### Backend API

#### New Endpoint: `POST /api/projects/{project_id}/production/run-auto`

**Request Body**:
```json
{
  "chapter_start": 1,           // Optional: starting chapter (default: current_chapter)
  "chapter_end": 10,            // Optional: ending chapter (default: chapter_start + 9)
  "max_steps": 10,              // Optional: max steps to execute (default: 10)
  "dry_run": false,             // Optional: preview steps without executing (default: false)
  "stop_on_review": true,       // Optional: stop on review-required actions (default: true)
  "confirm": true               // Required: must be true to execute
}
```

**Response**:
```json
{
  "ok": true,
  "data": {
    "status": "completed",      // completed | stopped | failed | dry_run
    "steps": [
      {
        "step": 1,
        "action": "generate_missing_context",
        "label": "补齐缺失内容",
        "target_chapter": null,
        "result": "success",
        "warnings": [],
        "error": null
      }
    ],
    "final_next_action": {...}, // Next recommended action after stopping
    "chapters_touched": [1, 2, 3],
    "stop_reason": "completed", // max_steps_reached | review_required | blocked | completed | failed | unsupported_action
    "steps_executed": 3
  }
}
```

**Stop Conditions**:
1. `max_steps_reached`: Executed max_steps steps
2. `review_required`: Encountered human-review action (review_genesis, review_chapter, apply_memory_updates)
3. `blocked`: Encountered blocking state (wait_genesis)
4. `completed`: No more actions needed (next_action.key == "none")
5. `failed`: Step execution failed
6. `unsupported_action`: Encountered unsupported action type

**Error Codes**:
- `CONFIRM_REQUIRED`: confirm parameter not set to true
- `AUTO_RUN_STEP_FAILED`: Individual step execution failed
- `LLM_CONFIG_MISSING`: Real mode requested but API key missing
- `AUTO_RUN_UNSUPPORTED_ACTION`: Action type not supported for auto-execution

### Supported Actions

The runner executes these action types automatically:

1. **generate_missing_context**: Calls `/api/projects/{project_id}/production/auto-fill`
2. **generate_arc_plan**: Calls `/api/projects/{project_id}/production/arc-plan`
3. **generate_chapter**: Calls `/api/projects/{project_id}/run-chapter`
4. **continue_next_chapter**: Calls `/api/projects/{project_id}/run-chapter`
5. **recover_blocked_run**: Calls `/api/projects/{project_id}/reset`
6. **apply_memory_updates**: **STOP** - requires human review

### Safety Guards

1. **Never Auto-Publish**: Real mode stops at `awaiting_publish` status
2. **LLM Config Validation**: Real mode validates API key before execution
3. **Stop on Review**: Stops on review_genesis, review_chapter, apply_memory_updates
4. **Max Steps Limit**: Prevents runaway execution
5. **Dry-Run Preview**: Preview actions before execution

### Database Changes

Extended `ProjectRepository.update_project()` to support `current_chapter` parameter:

```python
def update_project(
    self,
    project_id: str,
    # ... existing params ...
    current_chapter: int | None = None,  # NEW in v5.5.5
) -> dict | None:
```

---

### Frontend

#### Auto Production Console

Added to `ProjectOverviewModule.tsx`:

**Features**:
- Config panel: chapter range, max steps, dry-run toggle
- One-click "Start Auto Production" button
- Real-time step timeline with status indicators
- Error display with actionable messages
- Chapters touched summary

**State Management**:
```typescript
const [autoRunning, setAutoRunning] = useState(false);
const [autoResult, setAutoResult] = useState<AutoResult | null>(null);
const [autoConfig, setAutoConfig] = useState<AutoConfig>({
  chapterStart: 1,
  chapterEnd: 10,
  maxSteps: 10,
  dryRun: false,
});
```

**UI Components**:
- Config inputs with validation
- Play button with loading state
- Step timeline with color-coded status
- Error alert with details
- Summary cards (status, steps, chapters)

---

## Testing

### Test Coverage

Created `tests/test_v555_autonomous_production_runner.py` with 14 tests:

1. **TestRunAutoConfirmRequired**: CONFIRM_REQUIRED error when confirm=false
2. **TestRunAutoDryRun**: Dry-run returns steps without executing
3. **TestRunAutoMaxSteps**: max_steps limit is enforced
4. **TestRunAutoChapterRange**: Respects requested chapter range (P2-1, 3 tests)
5. **TestRunAutoAutoFill**: Auto-fill triggered when context missing
6. **TestRunAutoGenerateChapter**: generate_chapter executes chapter run
7. **TestRunAutoStopOnReview**: Stops on review/publish actions
8. **TestRunAutoStepFailed**: AUTO_RUN_STEP_FAILED on single step failure (P2-3)
9. **TestRunAutoStepsExecutedCount**: Steps executed counts consistently (P2-3)
10. **TestRunAutoLLMConfigMissing**: LLM_CONFIG_MISSING in real mode without API key
11. **TestRunAutoNoAutoPublish**: Real mode stops at awaiting_publish
12. **TestRunAutoUnsupportedAction**: Unsupported action returns blocked

**Test Results**: 14/14 passed, 1769 total tests passing

---

## Usage Examples

### Backend API

```bash
# Dry-run preview (stub mode)
curl -X POST http://localhost:8765/api/projects/demo/production/run-auto \
  -H "Content-Type: application/json" \
  -d '{"max_steps": 5, "dry_run": true, "confirm": true}'

# Execute 3 steps (stub mode)
curl -X POST http://localhost:8765/api/projects/demo/production/run-auto \
  -H "Content-Type: application/json" \
  -d '{"max_steps": 3, "confirm": true}'

# Generate chapters 1-10 with real LLM
curl -X POST http://localhost:8765/api/projects/demo/production/run-auto \
  -H "Content-Type: application/json" \
  -d '{"chapter_start": 1, "chapter_end": 10, "max_steps": 20, "confirm": true}'
```

### CLI (Future Enhancement)

```bash
# Planned CLI support
novelos --db-path novel.db run-auto --project-id demo --max-steps 10 --confirm
```

---

## Architecture

### Execution Flow

```
run_auto_production()
  │
  ├─ Validate confirm=true
  ├─ Validate LLM config (real mode)
  │
  └─ Loop (step_count < max_steps):
       │
       ├─ Get production-next recommendation
       │
       ├─ Check stop conditions:
       │    ├─ next_action.key == "none" → COMPLETED
       │    ├─ review_genesis → REVIEW_REQUIRED
       │    ├─ review_chapter → REVIEW_REQUIRED
       │    ├─ apply_memory_updates → REVIEW_REQUIRED
       │    └─ wait_genesis → BLOCKED
       │
       ├─ Dry-run mode:
       │    └─ Record step, return immediately
       │
       ├─ Execute step:
       │    ├─ generate_missing_context → auto-fill
       │    ├─ generate_arc_plan → arc-plan
       │    ├─ generate_chapter → run-chapter
       │    ├─ continue_next_chapter → run-chapter
       │    └─ recover_blocked_run → reset
       │
       ├─ Check step result:
       │    ├─ failed → FAILED
       │    ├─ unsupported → UNSUPPORTED
       │    └─ success → continue
       │
       └─ Check post-step conditions:
            ├─ requires_human → REVIEW_REQUIRED (if stop_on_review)
            └─ published → increment current_chapter
```

### Integration Points

1. **production-next**: Source of truth for next action
2. **auto-fill**: Auto-generate missing context
3. **arc-plan**: Generate arc-level outlines
4. **run-chapter**: Execute chapter workflow
5. **reset**: Recover blocked runs

---

## Migration Notes

### Backward Compatibility

- ✅ No breaking changes to existing APIs
- ✅ New endpoint is additive
- ✅ Database schema unchanged (current_chapter column already exists)
- ✅ Repository change is backward compatible (new optional parameter)

### Upgrade Path

1. Pull latest code from `codex-v5.5-production-reliability`
2. No database migration required
3. Restart API server
4. Frontend rebuild required for Auto Production Console UI

---

## Performance Considerations

1. **Step Execution**: Each step may involve LLM calls (real mode) or database writes
2. **Max Steps**: Default 10 steps prevents runaway execution
3. **Dry-Run**: Lightweight preview, no database writes
4. **Concurrency**: Single-threaded execution per project (no parallel runs)

---

## Future Enhancements

1. **CLI Support**: Add `novelos run-auto` command
2. **Parallel Execution**: Support concurrent multi-project runs
3. **Webhook Notifications**: Notify on completion/failure
4. **Resume from Checkpoint**: Continue interrupted runs
5. **Smart Retry**: Auto-retry failed steps with backoff
6. **Progress Streaming**: WebSocket-based progress updates

---

## References

- **Baseline**: v5.5.4 Real LLM Autonomous Planning
- **Roadmap**: `docs/codex/novel-factory-roadmap.md`
- **API Docs**: `novel_factory/api/routes/production.py`
- **Frontend**: `frontend/src/components/project/ProjectOverviewModule.tsx`
- **Tests**: `tests/test_v555_autonomous_production_runner.py`

---

## Changelog

### v5.5.5 (2026-05-05)

**Added**:
- `POST /api/projects/{project_id}/production/run-auto` endpoint
- `RunAutoRequest` model with configurable parameters
- `_execute_auto_step()` async helper for step execution
- Auto Production Console UI in ProjectOverviewModule
- 14 comprehensive tests for autonomous runner

**Changed**:
- Extended `ProjectRepository.update_project()` to support `current_chapter` parameter
- Extracted `_stub_autofill()` and `_stub_arc_plan()` helpers for reuse

**Fixed**:
- Dry-run mode now returns immediately after first step prediction
- Proper error handling for missing LLM configuration

**Test Results**:
- 1769/1769 pytest passing
- Frontend typecheck passing
- Frontend lint passing
- Frontend build passing
