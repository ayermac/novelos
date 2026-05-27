# Novel Factory v6.7.5 Chapter Title Generation - Completion Report

**Version**: 6.7.5  
**Branch**: `codex-v6.7.5-chapter-title-generation`  
**Date**: 2026-05-26  
**Status**: Completed

---

## Summary

Successfully implemented independent chapter title generation mechanism in AuthorAgent. The new system generates titles based on comprehensive chapter context instead of deriving from content opening text, resulting in more attractive and meaningful chapter titles.

---

## Implementation Details

### 1. New Model

**File**: `novel_factory/models/schemas.py`

Added `TitleGenerationOutput` for structured LLM title generation:
```python
class TitleGenerationOutput(BaseModel):
    """v6.7.5: Structured output for chapter title generation."""
    title: str
    reasoning: str = ""
```

### 2. New Methods in AuthorAgent

**File**: `novel_factory/agents/author.py`

#### `_generate_chapter_title(state, instruction, content) -> str | None`
- LLM-based title generation with structured prompt
- Uses chapter content, instruction context, scene beats
- Returns `None` on failure (does not raise)
- Only runs in `real` mode
- Title rules enforced: 4-16 chars, no punctuation, no planning verbs

#### `_repair_or_generate_title(state, instruction, content, current_title) -> str | None`
- Called when existing title is opening-derived
- In real mode: calls `_generate_chapter_title`
- In stub mode: falls back to instruction-derived

#### `_is_opening_derived_title(title, content, chapter_number) -> bool`
- Detects if title was derived from content opening
- Used to trigger title repair

### 3. Modified `_derive_title` Fallback Order

**Previous order**:
1. Existing usable title
2. Content heading
3. **Content opening** ← Removed as primary source
4. Instruction-derived
5. "第N章"

**New order (v6.7.5)**:
1. Existing usable title (with repair if opening-derived)
2. **Generated/repaired title** (NEW - LLM-based)
3. Instruction-derived title
4. Explicit content heading (only if actual heading)
5. "第N章"

### 4. Title Generation Prompt

The LLM prompt includes:
- Chapter number
- Instruction objective
- Key events
- Ending hook
- Plots to plant/resolve
- Content opening summary (first 200 chars)
- Content ending summary (last 200 chars)

**Title Rules**:
- 4-12 Chinese characters (max 16)
- No punctuation
- No planning verbs/terms
- Not from content opening
- Highlight key elements

---

## Test Coverage

**File**: `tests/test_v675_chapter_title_generation.py`

### Test Categories

| Category | Tests | Status |
|----------|-------|--------|
| Model Tests | 2 | ✅ |
| Validation Tests | 10 | ✅ |
| Detection Tests | 6 | ✅ |
| Fallback Tests | 3 | ✅ |
| Utility Tests | 15 | ✅ |
| Integration Tests | 2 | ✅ |
| Compliance Tests | 2 | ✅ |
| Token Usage Tests | 4 | ✅ |
| Lazy Derivation Tests | 3 | ✅ |
| Opening-Derived Tests | 4 | ✅ |
| **Total** | **50** | **✅ All Passing** |

### Full Test Suite Results

```
2890 passed, 1 skipped, 1364 warnings
```

---

## Verification

### Python Backend
```bash
python3 -m pytest tests/test_v675_chapter_title_generation.py -v
# 50 passed

python3 -m pytest -q
# 2890 passed, 1 skipped
```

### Version Verification
```bash
python3 -c "from novel_factory.version import get_version; print(get_version())"
# 6.7.5
```

### Frontend
```bash
cd frontend && npm run typecheck && npm run lint
# Both passed
```

---

## Files Changed

| File | Change |
|------|--------|
| `novel_factory/models/schemas.py` | Added `TitleGenerationOutput` model |
| `novel_factory/agents/author.py` | Added 3 new methods, modified `_derive_title` |
| `novel_factory/version.py` | Updated to 6.7.5 |
| `frontend/package.json` | Updated to 6.7.5 |
| `frontend/package-lock.json` | Updated to 6.7.5 |
| `desktop/package.json` | Updated to 6.7.5 |
| `desktop/package-lock.json` | Updated to 6.7.5 |
| `CHANGELOG.md` | Added v6.7.5 entry |
| `tests/test_v675_chapter_title_generation.py` | New test file |
| `docs/codex/specs/novel-factory-v6.7.5-chapter-title-generation-spec.md` | New spec document |

---

## Acceptance Criteria

- [x] `TitleGenerationOutput` model added to schemas
- [x] `_generate_chapter_title` method implemented in AuthorAgent
- [x] `_repair_or_generate_title` method implemented
- [x] `_is_opening_derived_title` method implemented
- [x] `_derive_title` fallback order updated
- [x] Content opening removed as primary title source
- [x] Title generation failure does not block workflow
- [x] Plain text path uses new title logic
- [x] Test file created with comprehensive coverage
- [x] All tests pass (2890 passed, 50 v6.7.5 tests)
- [x] Version updated to 6.7.5
- [x] Frontend typecheck/lint pass
- [x] No lint errors

---

## Review Fixes (2026-05-27)

### P1.1: Token Usage Overwrite Fix
- **Problem**: Title generation LLM call overwrites Author token usage
- **Fix**: Preserve and combine prior token usage with title generation usage
- **Impact**: Run detail totals and token budgets now correctly accumulate

### P1.2: Opening-Derived Title Repair
- **Problem**: Usable-but-opening-derived AuthorOutput titles were not repaired
- **Fix**: `_sanitize_output` now also checks `_is_opening_derived_title`
- **Impact**: v6.7.5 goal fully achieved - all opening-derived titles are repaired

### P2: Opening-Derived Generated Title Rejection
- **Problem**: Generated titles from opening text could pass validation
- **Fix**: `_generate_chapter_title` now checks `_is_opening_derived_title`
- **Impact**: Generated titles matching opening text are properly rejected

### P3.1: Documentation Updates
- **Problem**: Documentation entry points not updated to v6.7.5
- **Fix**: Updated `docs/codex/README.md` and version planning index
- **Impact**: Documentation now properly references v6.7.5

### P3.2: Test Coverage
- **Problem**: Some tests were placeholders without assertions
- **Fix**: Replaced with actual validation assertions
- **Impact**: Test coverage now accurately reflects behavior

---

## Review Fixes Round 2 (2026-05-27)

### P1: Token Usage Leaky Branches
- **Problem**: `_generate_chapter_title` did not restore prior token usage on early return paths (empty title, opening-derived rejection)
- **Fix**: Added `prior_usage` restoration before returning `None` on empty title (line 1664) and opening-derived rejection (line 1681)
- **Impact**: Token usage accounting no longer corrupted when title generation rejects output

### P2: Unconditional LLM Call in `_sanitize_output`
- **Problem**: `_sanitize_output` unconditionally called `_derive_title`, causing unnecessary LLM calls in real mode when title was already valid
- **Fix**: Moved `_derive_title` call inside `if should_replace:` guard block (line 1924)
- **Impact**: No unnecessary LLM calls when title is already usable and not opening-derived

### P3: Missing Regression Tests
- **Problem**: No regression tests for token usage preservation or lazy derivation behavior
- **Fix**: Added 7 new tests:
  - `TestTokenUsagePreservation` (4 tests): empty title, opening-derived, success combination, exception
  - `TestSanitizeOutputLazyDerivation` (3 tests): usable title (not called), unusable (called), opening-derived (called)
- **Impact**: Regression coverage for critical P1/P2 fixes

**Commits**:
- `c06b46d` - fix(v6.7.5): address round 2 review findings

---

## Known Issues

None.

---

## Future Considerations

1. **Title Templates**: Configurable title templates per genre
2. **Title History**: Track title generation attempts for analysis
3. **Title Rating**: User rating of generated titles for feedback
4. **Multi-title Options**: Generate multiple title options for user selection

---

## References

- Spec: `docs/codex/specs/novel-factory-v6.7.5-chapter-title-generation-spec.md`
- Tests: `tests/test_v675_chapter_title_generation.py`
- Implementation: `novel_factory/agents/author.py`
