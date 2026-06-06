# Novel Factory v6.7.3 — Preflight UX & Regression Closure

**Status**: Complete
**Date**: 2026-05-26
**Baseline**: v6.7.2 Memory Dedup & Preflight Hardening

## Scope

v6.7.3 closes the preflight UX loop and adds regression tests for API success paths that were under-tested in v6.7.2.

### Goals

1. **API Success Path Regression Tests**: Add tests for background start, SSE stream, and production auto-run success paths
2. **Enhanced Preflight Warning Details**: Add `groups` (with ids) and `recommended_actions` to warning details
3. **Frontend Preflight Warning Display**: Non-blocking warning banner in WorkflowTimeline
4. **SSE Preflight Event Consumption**: Frontend hook handles `preflight_warnings` event
5. **GLM/Volcengine JSON Fallback**: Treat `json_object is not supported by this model` as a response_format incompatibility and retry without the hint
6. **Documentation Updates**: Version alignment and completion report

### Non-Goals

- Preflight warning click-to-action (future UX enhancement)
- Preflight warning persistence across sessions
- Preflight warning dismissal/acknowledgment

## Implementation

### 1. API Success Path Regression Tests

**File**: `tests/test_v673_preflight_ux_regression.py`

Tests cover:
- background start success path: POST `/api/run/chapter/start` returns `preflight_warnings`
- SSE stream success path: GET `/api/run/chapter/stream` yields an initial `preflight_warnings` event when warnings exist
- production auto-run success path: `_execute_auto_step()` returns `preflight_warnings`, including the clean `[]` case
- enhanced warning details: duplicate and pressure warnings include groups/ids/recommended_actions
- preflight failure resilience: preflight exceptions return `preflight_failed` without blocking generation

### 2. Enhanced Preflight Warning Details

**File**: `novel_factory/ops/memory_governance.py`

Added helper functions:
- `_duplicate_groups()`: Builds duplicate group info with ids and display values
- `_safe_item_id()`: Safely extracts id from item dict
- `_safe_display_value()`: Safely extracts display value from item dict

Modified `audit_project_memory()` to return `duplicate_groups` with:
- `value`: The duplicate value
- `count`: Number of duplicates
- `ids`: List of database IDs for the duplicates
- `display_values`: List of human-readable names

**File**: `novel_factory/ops/preflight.py`

Enhanced all warning types to include:
- `groups`: Detailed duplicate info with ids (where applicable)
- `recommended_actions`: Structured action suggestions with `code`, `label`, `severity`

Example structure:
```python
details={
    "count": len(duplicate_characters),
    "examples": [d["value"] for d in duplicate_characters[:5]],
    "groups": [
        {
            "value": "张三",
            "count": 2,
            "ids": [1, 2],
            "display_values": ["张三", "张三"]
        }
    ],
    "recommended_actions": [
        {"code": "review_duplicate_characters", "label": "查看重复角色", "severity": "warning"},
    ],
}
```

### 3. Frontend Preflight Warning Display

**File**: `frontend/src/components/WorkflowTimeline.tsx`

- Added `PreflightWarning` interface
- Added `preflightWarnings` prop to component
- Added `PreflightWarningBanner` component for non-blocking warning display
- Banner shows warning message, examples/groups, and recommended actions as tags

**File**: `frontend/src/components/project/AuthorWritingSurface.tsx`

- Added `preflightWarnings` prop to `AuthorWritingSurfaceProps`
- Passed `preflightWarnings` through `WorkflowBody` to `WorkflowTimeline`

**File**: `frontend/src/components/project/AuthorWorkbench.tsx`

- Already had `preflightWarnings` prop and passed it to `AuthorWritingSurface`

**File**: `frontend/src/pages/ProjectDetail.tsx`

- Already extracted `preflightWarnings` from `useSSEStream` hook
- Already passed `preflightWarnings` to `AuthorWorkbench`

### 4. SSE Preflight Event Consumption

**File**: `frontend/src/hooks/useSSEStream.ts`

- Added `PreflightWarning` interface
- Added `preflightWarnings` state
- Added handling for `preflight_warnings` event type in `handleLegacyMessage`
- Exposed `preflightWarnings` in return value

### 5. GLM/Volcengine JSON Fallback

**File**: `novel_factory/llm/openai_compatible.py`

- Extended response_format unsupported-error detection to include provider/model errors that say `json_object is not supported by this model`
- This keeps structured JSON calls compatible with providers that reject `response_format={"type": "json_object"}` while still accepting plain JSON prompting

**File**: `tests/test_json_agent_retry.py`

- Added a regression test using the observed `InvalidParameter` / `response_format.type` / `json_object is not supported by this model` error text

## Verification

### Test Coverage

- 11 new tests in `tests/test_v673_preflight_ux_regression.py`
- `TestResponseFormatFallback` passes, including the GLM/Volcengine `json_object` incompatibility regression
- All tests passing

### Frontend Verification

- TypeScript typecheck: passing
- ESLint: passing
- Production build: passing

## Acceptance Criteria

- [x] API success path regression tests for background start, SSE stream, production auto-run
- [x] Preflight warnings include `groups` with database IDs
- [x] Preflight warnings include `recommended_actions` with structured suggestions
- [x] Frontend displays preflight warnings in non-blocking banner
- [x] SSE hook consumes `preflight_warnings` event
- [x] GLM/Volcengine JSON calls fallback when `response_format.type=json_object` is rejected
- [x] Version updated to 6.7.3
- [x] Documentation updated

## Follow-up

- Consider adding click-to-action for preflight warnings
- Consider preflight warning persistence for session continuity
- Consider preflight warning dismissal/acknowledgment tracking
