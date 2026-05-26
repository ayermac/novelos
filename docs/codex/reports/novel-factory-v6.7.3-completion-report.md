# Novel Factory v6.7.3 Completion Report

**Version**: 6.7.3
**Date**: 2026-05-26
**Status**: Complete

## Summary

v6.7.3 completes the preflight UX loop and adds regression tests for API success paths. This version ensures that preflight warnings are visible to users in a non-blocking manner and that the API success paths have adequate test coverage.

## Changes

### Backend

1. **Enhanced Preflight Warning Details** (`novel_factory/ops/memory_governance.py`)
   - Added `_duplicate_groups()` helper to build detailed duplicate info
   - Added `_safe_item_id()` and `_safe_display_value()` helpers
   - Modified `audit_project_memory()` to return `duplicate_groups` with database IDs

2. **Enhanced Preflight Warning Structure** (`novel_factory/ops/preflight.py`)
   - All warning types now include `groups` with detailed info
   - All warning types now include `recommended_actions` with structured suggestions
   - Example structure:
     ```python
     {
         "code": "duplicate_characters",
         "message": "发现 2 个重复角色名称",
         "severity": "warning",
         "details": {
             "count": 2,
             "examples": ["张三", "李四"],
             "groups": [
                 {"value": "张三", "count": 2, "ids": [1, 2], "display_values": ["张三", "张三"]}
             ],
             "recommended_actions": [
                 {"code": "review_duplicate_characters", "label": "查看重复角色", "severity": "warning"}
             ]
         }
     }
     ```

3. **GLM/Volcengine JSON Fallback Compatibility** (`novel_factory/llm/openai_compatible.py`)
   - Extended `response_format` unsupported-error detection for providers/models that reject `{"type": "json_object"}` with `json_object is not supported by this model`
   - JSON calls now retry without `response_format` while preserving the JSON parse retry budget

### Frontend

1. **SSE Hook Enhancement** (`frontend/src/hooks/useSSEStream.ts`)
   - Added `PreflightWarning` interface
   - Added `preflightWarnings` state
   - Added handling for `preflight_warnings` event type
   - Exposed `preflightWarnings` in return value

2. **WorkflowTimeline Component** (`frontend/src/components/WorkflowTimeline.tsx`)
   - Added `PreflightWarning` interface (exported)
   - Added `preflightWarnings` prop
   - Added `PreflightWarningBanner` component for non-blocking display
   - Banner shows message, examples/groups, and recommended action tags

3. **AuthorWritingSurface Component** (`frontend/src/components/project/AuthorWritingSurface.tsx`)
   - Added `preflightWarnings` prop to interface
   - Passed `preflightWarnings` through component hierarchy to `WorkflowTimeline`
   - Updated all three `WorkflowTimeline` call sites (timeline, runDetail fallback, streaming fallback)

4. **AuthorWorkbench Component** (`frontend/src/components/project/AuthorWorkbench.tsx`)
   - Already had `PreflightWarning` interface and `preflightWarnings` prop
   - Already passed to `AuthorWritingSurface`

5. **ProjectDetail Page** (`frontend/src/pages/ProjectDetail.tsx`)
   - Already extracted `preflightWarnings` from `useSSEStream`
   - Already passed to `AuthorWorkbench`

### Tests

1. **New Test File**: `tests/test_v673_preflight_ux_regression.py`
   - 11 tests covering:
     - Background start success path
     - SSE stream success path
     - Production auto-run success path
     - Preflight warning details structure (groups, ids, recommended_actions)
     - Preflight failure resilience

## Verification Results

### Backend Tests

```
tests/test_v673_preflight_ux_regression.py: 11 passed
tests/test_json_agent_retry.py::TestResponseFormatFallback: 8 passed
```

### Frontend Verification

- TypeScript typecheck: passing
- ESLint: passing
- Production build: passing

### Version Alignment

- `novel_factory/version.py`: 6.7.3
- `frontend/package.json`: 6.7.3
- `desktop/package.json`: 6.7.3

## Files Changed

### Backend
- `novel_factory/ops/memory_governance.py` - Enhanced duplicate group details
- `novel_factory/ops/preflight.py` - Added groups and recommended_actions to warnings
- `novel_factory/llm/openai_compatible.py` - Added GLM/Volcengine response_format fallback pattern
- `novel_factory/version.py` - Version bump to 6.7.3

### Frontend
- `frontend/src/hooks/useSSEStream.ts` - Preflight warnings state and event handling
- `frontend/src/components/WorkflowTimeline.tsx` - PreflightWarningBanner component
- `frontend/src/components/project/AuthorWritingSurface.tsx` - Pass preflightWarnings through
- `frontend/package.json` - Version bump to 6.7.3

### Desktop
- `desktop/package.json` - Version bump to 6.7.3

### Tests
- `tests/test_v673_preflight_ux_regression.py` - New test file
- `tests/test_json_agent_retry.py` - Added GLM/Volcengine response_format fallback regression

### Documentation
- `CHANGELOG.md` - v6.7.3 entry
- `docs/codex/README.md` - Updated baseline
- `docs/codex/planning/novel-factory-version-planning-index.md` - Added v6.7.3 entry
- `docs/codex/specs/novel-factory-v6.7.3-preflight-ux-regression-spec.md` - New spec
- `docs/codex/reports/novel-factory-v6.7.3-completion-report.md` - This report

## Acceptance Criteria

| Criterion | Status |
|-----------|--------|
| API success path regression tests | ✅ Complete |
| Preflight warnings include groups with ids | ✅ Complete |
| Preflight warnings include recommended_actions | ✅ Complete |
| Frontend displays preflight warnings | ✅ Complete |
| SSE hook consumes preflight_warnings event | ✅ Complete |
| Version updated to 6.7.3 | ✅ Complete |
| Documentation updated | ✅ Complete |

## Known Issues

None.

## Follow-up Recommendations

1. **Click-to-action**: Add clickable actions in preflight warning banner that navigate to relevant module
2. **Persistence**: Consider persisting preflight warnings across session for continuity
3. **Dismissal tracking**: Track dismissed warnings to avoid re-showing resolved issues
