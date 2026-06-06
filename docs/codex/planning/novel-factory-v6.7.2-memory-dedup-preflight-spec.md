# Novel Factory v6.7.2: Memory Dedup & Preflight Hardening

**Version**: 6.7.2  
**Baseline**: v6.7.1 Auto Arc Continuation  
**Status**: Completed  
**Date**: 2026-05-26

## Overview

v6.7.2 introduces lightweight preflight diagnostics that expose memory pressure and duplicate detection issues before chapter generation starts. Unlike hard guards, preflight checks emit warnings without blocking the workflow, making issues visible at the exact moment a user tries to start chapter generation.

## Goals

1. **Memory write dedup guards**: Ensure `characters.create` and `world_settings.create` convert to `update` when duplicates exist (already implemented in v5.3.2, verified in this version)
2. **Memory governance audit enhancement**: Verify `world_settings` is included in counts, duplicate detection, and context pressure (already implemented, verified in this version)
3. **Lightweight preflight checks**: Expose duplicate characters, duplicate world_settings, story_facts pressure, memory_items pressure, and context character pressure before chapter generation
4. **Regression tests for all features**

## Implementation

### 1. Preflight Diagnostics Module

**File**: `novel_factory/ops/preflight.py`

New module providing lightweight preflight checks:

```python
@dataclass
class PreflightWarning:
    code: str
    message: str
    severity: str = "warning"
    details: dict[str, Any] = field(default_factory=dict)

def check_preflight_diagnostics(
    repo: Any,
    project_id: str,
    *,
    limits: dict[str, int] | None = None,
) -> PreflightResult:
    """Run lightweight preflight checks before chapter generation."""
```

**Checks performed**:
- Duplicate characters (same name)
- Duplicate world_settings (same title)
- Story facts pressure (count exceeds threshold)
- Memory items pressure (count exceeds threshold)
- Context character pressure (total chars exceeds threshold)

### 2. Run Guard Integration

**File**: `novel_factory/api/routes/_run_guards.py`

Modified `check_chapter_run_guard` to return preflight warnings alongside guard errors:

```python
# Before
def check_chapter_run_guard(repo, project_id: str, chapter_number: int) -> RunGuardError | None:

# After
def check_chapter_run_guard(repo, project_id: str, chapter_number: int) -> tuple[RunGuardError | None, list[dict[str, Any]]]:
```

**Call sites updated**:
- `novel_factory/api/routes/run.py` (2 call sites)
- `novel_factory/api/routes/production.py` (1 call site)
- `novel_factory/api/routes/runs.py` (1 call site)
- Test files (multiple call sites)

### 3. API Response Enhancement

Preflight warnings are now included in both error and success responses:

```json
{
  "error": "CONTEXT_INCOMPLETE",
  "message": "项目上下文不完整...",
  "details": {...},
  "preflight_warnings": [
    {
      "code": "duplicate_characters",
      "message": "发现 1 个重复角色名，可能导致上下文膨胀",
      "severity": "warning",
      "details": {"count": 1, "examples": ["陆澈"]}
    }
  ]
}
```

## Verification

### Existing Features Verified

1. **Memory dedup for characters**: Already implemented in `memory_updates.py` via `_find_character_for_memory_update`
2. **Memory dedup for world_settings**: Already implemented in `memory_updates.py` via `_find_world_setting_for_memory_update`
3. **Memory governance includes world_settings**: Already implemented in `memory_governance.py`

### New Tests Added

**File**: `tests/test_v672_memory_dedup_preflight.py`

- `test_preflight_detects_duplicate_characters`: Verifies duplicate character detection
- `test_preflight_detects_duplicate_world_settings`: Verifies duplicate world_setting detection
- `test_preflight_detects_story_facts_pressure`: Verifies story facts pressure warning
- `test_preflight_detects_memory_items_pressure`: Verifies memory items pressure warning
- `test_preflight_detects_context_pressure`: Verifies context character pressure warning
- `test_preflight_returns_empty_when_no_issues`: Verifies clean state returns no warnings
- `test_run_guard_returns_preflight_warnings`: Verifies integration with run guards (error case)
- `test_run_guard_returns_preflight_warnings_on_success`: Verifies integration with run guards (success case)
- `test_run_chapter_sync_exposes_preflight_warnings`: API-level test for success path (POST /run/chapter)

## Acceptance Criteria

- [x] Preflight diagnostics detect duplicate characters
- [x] Preflight diagnostics detect duplicate world_settings
- [x] Preflight diagnostics detect story_facts pressure
- [x] Preflight diagnostics detect memory_items pressure
- [x] Preflight diagnostics detect context character pressure
- [x] Run guards return preflight warnings alongside guard errors
- [x] Run guards return preflight warnings even when guard passes
- [x] Preflight warnings exposed in API success responses (POST /run/chapter, SSE stream, auto-run)
- [x] Preflight exceptions logged with diagnostic warning instead of silently swallowed
- [x] Frontend/desktop lockfiles synced to 6.7.2
- [x] Documentation entry points updated (README.md, version-planning-index.md)
- [x] All existing tests pass (2826 passed)
- [x] New tests pass (9 new tests)

## Files Changed

### New Files
- `novel_factory/ops/preflight.py`: Preflight diagnostics module
- `tests/test_v672_memory_dedup_preflight.py`: Test file for v6.7.2

### Modified Files
- `novel_factory/version.py`: Version bump to 6.7.2
- `novel_factory/api/routes/_run_guards.py`: Added preflight warnings to return type
- `novel_factory/api/routes/run.py`: Updated call sites for new return type
- `novel_factory/api/routes/production.py`: Updated call site for new return type
- `novel_factory/api/routes/runs.py`: Updated call site for new return type
- `tests/test_v63_creator_onboarding.py`: Updated call sites for new return type
- `tests/test_v671_auto_arc_continuation.py`: Updated call sites for new return type
- `tests/test_v5515_production_readiness.py`: Updated call sites for new return type

## Migration Notes

No database migrations required. This is a pure code change that adds diagnostic capabilities without modifying existing data structures.

## Future Considerations

1. **UI Integration**: Frontend should display preflight warnings in a non-blocking manner (e.g., toast notifications or info banners)
2. **Configurable Thresholds**: Allow users to customize pressure thresholds per project
3. **Auto-remediation**: Consider adding "fix all" buttons for certain warning types (e.g., merge duplicates)

## Review Fixes (Post-Initial Implementation)

### P1: Preflight warnings exposed on success paths
- Added `preflight_warnings` to success responses in:
  - `run.py`: Background start and sync run responses
  - `runs.py`: SSE stream initial event
  - `production.py`: Auto-run success result
- Added API-level regression test for success path

### P2: Lockfile version sync
- Updated `frontend/package-lock.json` to 6.7.2
- Updated `desktop/package-lock.json` to 6.7.2

### P3: Documentation entry points
- Updated `docs/codex/README.md` with v6.7.2 baseline and spec/report links
- Updated `docs/codex/planning/novel-factory-version-planning-index.md` with v6.7.2 row

### P3: Preflight exception handling
- Changed from silent `pass` to logging with warning
- Added `preflight_failed` diagnostic warning when exceptions occur
- Users now know when preflight diagnostics failed instead of seeing empty warnings
