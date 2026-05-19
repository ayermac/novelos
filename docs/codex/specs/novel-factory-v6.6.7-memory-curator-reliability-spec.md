# v6.6.7 Memory Curator Reliability Closure

**Version**: 6.6.7
**Status**: Completed
**Baseline**: v6.6.6 Workflow Recovery & State Integrity Closure (2320 tests passing)

## Problem Statement

Before v6.6.7, Memory Curator had systemic reliability issues:
1. **JSON extraction fragility**: LLM responses with markdown fences, unclosed fences, or prose wrappers could fail to parse
2. **Empty patches not caught**: Real LLM returning empty patches was not reliably detected as failure
3. **Fallback masquerading as success**: State-card fallback batches looked identical to trusted extractions in the UI
4. **No clear semantics**: Users couldn't tell if a memory batch was from real LLM extraction or fallback
5. **Backfill confusion**: Manual backfill couldn't distinguish between trusted and fallback batches
6. **Planner pollution**: Fallback patches could enter Planner's trusted memory context

## Solution

### A. MemoryCurator Output Reliability

#### A1. Robust JSON Extraction

Created `_robust_extract_patches()` in `memory_curator.py`:
- Handles `patches` key directly
- Handles legacy `facts` key with warning
- Handles single patch object responses
- Warns on unrecognized schema

#### A2. Strict Patch Validation

Created `_validate_patches()` with rules:
1. patches must be non-empty list
2. Each patch must have `target_table`, `operation`, `confidence`, `evidence_text`
3. `confidence` must be in [0, 1]
4. `evidence_text` must be non-empty
5. Evidence traceability check (advisory only)

#### A3. Empty Patches Handling

- Empty patches from real LLM → `extraction_success=False`
- No fallback available → `memory_curator_degraded=True`
- Always creates `result_category` field

### B. Three-Category Result Taxonomy

```
trusted_extraction    → real LLM succeeded, patches validated
fallback_candidate    → extraction failed, state-card fallback only
failed_no_memory      → no patches and no fallback available
```

**Fallback requirements**:
- confidence <= 0.45
- batch summary contains "状态卡兜底"
- item rationale contains "状态卡兜底候选"
- Marked as `fallback_created=True`, `extraction_success=False`

### C. Memory Gate Classification

Enhanced `_memory_curator_gate.py`:
- `classify_memory_batch()` → returns "trusted" / "fallback" / "empty" / "ignored"
- `get_memory_status_for_chapter()` → canonical memory status dict
- `is_trusted_memory_batch()` → ignores fallback/degraded markers
- `is_state_card_fallback_batch()` → detects by summary + rationale + confidence

### D. Context Builder Protection

`context_builder.py` already had:
- `_is_trusted_memory_item()` → requires confidence >= 0.75, non-empty evidence, no fallback rationale
- `_is_untrusted_memory_item()` → detects confidence <= 0.45 or fallback rationale
- `_select_trusted_memory_batch()` → excludes fallback batches

**Trusted memory flow**:
1. Planner only gets trusted memory (confidence >= 0.75)
2. Low-confidence items go to advisory context
3. Fallback items never enter trusted memory

### E. Backfill API Enhancement

`POST /runs/{run_id}/memory/backfill`:
- `force=false` + trusted batch exists → skip with message
- `force=false` + only fallback exists → runs extraction (does not skip)
- `force=true` → marks old fallback batches as ignored, re-runs extraction
- Returns `trusted: true/false` field
- Incomplete extraction → `MEMORY_CURATOR_INCOMPLETE` error
- Never changes chapter status

### F. Run Detail Memory Status

`GET /api/runs/{run_id}` now returns:
```json
{
  "memory_status": {
    "memory_status": "trusted|fallback|failed|missing",
    "memory_trusted": true|false,
    "latest_memory_batch_id": "...",
    "batch_count": 1,
    "trusted_batch_count": 1,
    "fallback_batch_count": 0
  }
}
```

### G. Frontend Experience

**RunDetail.tsx**:
- Memory status alert bar (green for trusted, yellow for fallback/missing)
- Button label changes based on memory state:
  - Trusted → "已存在可信记忆" (disabled) + "强制重跑" option
  - Fallback → "重新提取可信记忆"
  - Missing → "补跑记忆提取"
- Backfill failure never shows success toast

**MemoryUpdatesModule.tsx**:
- Fallback batches grouped under "待人工确认候选"
- Visual distinction: orange left border + [低可信] tag
- Fallback apply button uses secondary style

## Testing

**Test File**: `tests/test_v667_memory_curator_reliability.py`

**Coverage** (25 tests):
1. fenced JSON parsing
2. legacy facts key handling
3. empty patches rejection
4. missing fields rejection
5. confidence out-of-range rejection
6. empty evidence rejection
7. valid patches acceptance
8. batch classification by summary
9. batch classification by rationale
10. trusted batch detection
11. fallback batch detection
12. empty batch detection
13. memory status for trusted chapter
14. memory status for fallback chapter
15. memory status for missing chapter
16. trusted memory item confidence threshold
17. trusted memory rejects fallback rationale
18. untrusted memory detects low confidence
19. run detail returns memory_status
20. backfill skips when trusted exists
21. backfill force ignores fallback
22. backfill doesn't change chapter status
23. extraction semantics in result
24. old fallback batch compatibility
25. context builder selects only trusted memory

**Results**: 25/25 passed, 2320/2320 total tests passing

## Constraints Verified

1. ✅ No LangGraph topology changes
2. ✅ Fallback not masqueraded as trusted
3. ✅ Memory extraction failure doesn't silently succeed
4. ✅ Published chapters allow manual retry
5. ✅ Failure/fallback/trusted semantics clear in API and UI
6. ✅ Planner only inherits trusted memory
7. ✅ All changes have test coverage
8. ✅ No project/chapter-specific特例

## Files Modified

| File | Changes |
|------|---------|
| `novel_factory/agents/memory_curator.py` | Robust extraction, validation, three-category taxonomy |
| `novel_factory/api/routes/_memory_curator_gate.py` | classify_memory_batch, get_memory_status_for_chapter |
| `novel_factory/api/routes/runs.py` | Enhanced backfill, memory status in run detail |
| `frontend/src/pages/RunDetail.tsx` | Memory status display, state-aware buttons |
| `frontend/src/components/project/MemoryUpdatesModule.tsx` | Fallback batch grouping |
| `novel_factory/version.py` | Version bump to 6.6.7 |
| `frontend/package.json` | Version sync to 6.6.7 |
| `frontend/package-lock.json` | Version sync to 6.6.7 |
| `tests/test_v667_memory_curator_reliability.py` | NEW - 25 test cases |

## Migration Notes

No database migrations required. Old fallback batches are identified by:
- Summary containing "状态卡兜底"
- Item rationale containing "状态卡兜底候选"
- Item confidence <= 0.45

## Future Work

- Consider adding `memory_status` to production-next recommendations
- Consider batch-level `source` field in DB schema for clearer provenance
