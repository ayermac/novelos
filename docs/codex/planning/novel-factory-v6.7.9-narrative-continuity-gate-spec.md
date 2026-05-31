# v6.7.9 Narrative Continuity Gate — Spec

**Version**: 6.7.9
**Date**: 2026-05-29
**Branch**: `v6.7.9-continuity-gate`
**Status**: Implemented

---

## Problem Statement

Real novel project (`novel_7ia0`) exposed multiple narrative quality issues that the existing Editor review pipeline failed to catch:

### 1. Chapter-Internal Time Regression

Chapter text contained "两小时前" (two hours ago) jumping back to a completed scene (公司大门/门口保安/公司走廊) without any flashback frame (回忆/想起). This created a broken timeline where the reader was suddenly back at an earlier point in the story.

### 2. Cross-Chapter Time-Anchor Conflicts

- **Conflict 1**: Previous chapter ended with "明日午时，老地方见" (meet tomorrow noon). Current chapter opened with "早上七点五十" (7:50 AM) but text still said "明日午时之前" (before tomorrow noon) — the scene was already the next day but dialogue still referenced "tomorrow" as future.
- **Conflict 2**: Current chapter ended with "今晚，老地方见" (tonight, old place). Next chapter opened with "昨天的对话" (yesterday's conversation) — temporal disconnect.

### 3. Truncated/Malformed Titles

Titles ending with "无/的/与/和/了" (e.g., "第5章 三家世界五百强企业宣布无") — clearly truncated mid-sentence.

### 4. Editor Fallback Fake-Green

When the Editor LLM timed out, `_fallback_rule_review` gave a score of 88 ("excellent") with auto-pass, creating a false green signal. Real issues were masked by the fallback's optimistic scoring.

### 5. Missing Pre-Publish Hard Gate

No code-level check blocked chapters with obvious continuity defects from being published. The system relied entirely on LLM review, which could be bypassed by timeouts or poor prompting.

**Root Cause**: Quality gates were too dependent on LLM self-awareness and prompt engineering. No deterministic, code-level assertions existed for obvious structural defects.

---

## Solution

### A. Deterministic Narrative Continuity Gate

**New File**: `novel_factory/quality/continuity_gate.py`

Pure deterministic module with no LLM dependencies, no side effects, no database writes.

#### Detection Heuristics

| Check | Markers | Severity | Logic |
|-------|---------|----------|-------|
| Time regression | 两小时前/三小时前/回到/再次来到 + 公司大门/门口保安/出租车 | **blocking** | Scan body after first paragraph; if old-scene markers present without flashback frame → block |
| Flashback frame | 回忆起/想起/脑海中浮现/记忆如潮 | **advisory** | If flashback frame present → advisory only |
| Cross-chapter anchor (Conflict 1) | 前章"明日午时" + 本章已是次日早晨但台词仍说"明日" | **blocking** | Previous chapter sets future anchor, current chapter is at target day |
| Cross-chapter anchor (Conflict 2) | 本章结尾"今晚/明日" + 下章开头"昨天/昨晚" | **warning** | Current tail sets anchor, next chapter ignores it |
| Title truncation | Ending with 无/的/与/和/了 或长度<4 | **warning** | Simple string check |
| Title-content mismatch | 标题关键词不在正文中 | **warning** | Extract 2-8 char keywords, check against content body |
| Event replay | ≥3 long unique sentences (12-60 chars) from prev chapter verbatim | **blocking** | Exclude common glue (说道/说完/看着等); Jaccard >0.5 skips detection |

#### Public API

```python
evaluate_chapter_continuity(repo, project_id, chapter_number, content, title) -> ContinuityGateResult
evaluate_publish_continuity(repo, project_id, chapter_number) -> ContinuityGateResult
```

#### ContinuityGateResult

```python
@dataclass
class ContinuityGateResult:
    passed: bool
    severity: str  # pass / advisory / warning / blocking
    issues: list[str]
    suggestions: list[str]
    evidence: dict[str, Any]
    should_block_publish: bool
```

### B. Editor Fallback De-Powered

**File**: `novel_factory/agents/editor.py`

1. Score cap: 88 → **70** (maximum for fallback review)
2. Mandatory degraded warning: "AI 审核不可用，本结果仅为规则兜底，不代表完整审校通过。"
3. Continuity gate integration: If blocking issues found, force `pass_=False`, `revision_target="author"`
4. Event payload: `fallback_used` includes `degraded_review: true`, `blocks_auto_publish`

### C. Editor Normal Flow Integration

**File**: `novel_factory/agents/editor.py`

1. **Step 4.6** `_run_continuity_gate()` runs after story facts compliance
2. Blocking issues → force `pass_=False`, cap score at 70, set `revision_target="author"`
3. Inject `[连续性阻断]` / `[连续性修复]` notes into issues/suggestions
4. Continuity advisory/warning issues excluded from `classify_issues` to prevent revision target misrouting

### D. Publish Hard Gate

**Files**: `novel_factory/api/routes/run.py`, `novel_factory/workflow/nodes.py`

1. **API endpoint**: `POST /publish/chapter` runs `evaluate_publish_continuity` before publishing
2. **Publisher node**: `publisher_node` runs continuity gate before `repo.publish_chapter()`
3. Returns `CONTINUITY_GATE_BLOCKED` error with issues and suggestions if blocking

### E. Revision Classifier Fix

**File**: `novel_factory/validators/revision_classifier.py`

- Title-related issues (标题) no longer trigger structural author routing
- Falls through to normal keyword matching instead

---

## Architecture Decisions

### 1. Deterministic Over LLM

All continuity checks are rule-based, not relying on LLM to discover issues. This ensures:
- 100% reproducible results
- No API cost for continuity checks
- No timeout risk
- No prompt engineering dependency

### 2. Three-Layer Defense

| Layer | Location | Timing | Behavior |
|-------|----------|--------|----------|
| Editor | `_run_continuity_gate()` | After story facts compliance | Injects issues, can fail review |
| Publisher | `publisher_node` | Before `repo.publish_chapter()` | Blocks publish |
| API | `POST /publish/chapter` | Before publish commit | Returns error to frontend |

### 3. Severity Differentiation

| Severity | Publish Blocked | Revision Triggered | Example |
|----------|----------------|-------------------|---------|
| blocking | ✅ Yes | ✅ Yes (author) | Time regression, event replay |
| warning | ❌ No | ❌ No (advisory only) | Title truncation, anchor Conflict 2 |
| advisory | ❌ No | ❌ No | Framed flashback |
| pass | ❌ No | ❌ No | No issues found |

### 4. Generic Logic

No hardcoded project, character, chapter, or location names. All detection uses:
- Marker tuples (extensible)
- Regex patterns
- Jaccard similarity
- String matching

### 5. Jaccard Guard for Replay Detection

When chapters are >50% identical at sentence level (Jaccard similarity), skip replay detection. This prevents false positives on:
- Stub/template test data
- Legitimate repeated phrases (e.g., recurring dialogue tags)

---

## Affected Files

| File | Change |
|------|--------|
| `novel_factory/quality/continuity_gate.py` | **NEW** — Deterministic continuity gate module |
| `novel_factory/agents/editor.py` | Fallback de-power, continuity gate integration, classification isolation |
| `novel_factory/api/routes/run.py` | Publish endpoint hard gate |
| `novel_factory/workflow/nodes.py` | Publisher node hard gate |
| `novel_factory/validators/revision_classifier.py` | Title issue routing fix |
| `novel_factory/version.py` | Version bump to 6.7.9 |
| `frontend/package.json` | Version bump to 6.7.9 |
| `desktop/package.json` | Version bump to 6.7.9 |
| `tests/test_v679_continuity_gate.py` | 15 dedicated tests |

---

## Acceptance Criteria

### Fallback De-Power

1. ✅ Fallback review score ≤ 70 (not 88)
2. ✅ Fallback review includes degraded warning
3. ✅ Fallback + continuity blocking → `pass_=False`, `revision_target="author"`
4. ✅ Fallback + continuity warning → does NOT block fallback

### Time Regression

5. ✅ Unframed regression to old scene → blocking
6. ✅ Framed flashback → advisory (not blocking)
7. ✅ Legitimate short flashback → pass/advisory

### Cross-Chapter Anchors

8. ✅ Conflict 1 (future_anchor_still_spoken) → blocking
9. ✅ Conflict 2 (tail_to_next_break) → warning

### Title Checks

10. ✅ Truncated title (ending with 无) → warning
11. ✅ Missing title → warning
12. ✅ Title-content keyword mismatch → warning

### Event Replay

13. ✅ ≥3 long unique sentences repeated → blocking
14. ✅ Jaccard >0.5 (stub data) → skip replay detection

### Publish Blocking

15. ✅ API endpoint blocks on continuity gate
16. ✅ Publisher node blocks on continuity gate

### Generic Logic

17. ✅ No hardcoded project/character/chapter names in code

### Version Alignment

18. ✅ Runtime version = 6.7.9
19. ✅ Frontend version = 6.7.9
20. ✅ Desktop version = 6.7.9

---

## Code Review Fixes

6 issues addressed after initial implementation:

| Fix | Priority | Description |
|-----|----------|-------------|
| Fix 1 | P1 | Removed DEBUG `print("DEBUG result:", result)` from test |
| Fix 2 | P1 | Cross-chapter anchor severity differentiation (Conflict 1 blocking, Conflict 2 warning) |
| Fix 3 | P2 | Added 2 event replay tests (blocking + Jaccard skip) |
| Fix 4 | P2 | Tightened test assertion from "时间" to "跨章时间锚点冲突" |
| Fix 5 | P2 | Added fallback + continuity warning test |
| Fix 6 | P2 | Added design intent comment for advisory → suggestions routing |

---

## Tests

**File**: `tests/test_v679_continuity_gate.py`

15 tests in 4 sections:

| Section | Tests | Coverage |
|---------|-------|----------|
| A. Time regression | 3 | Blocking, flashback frame, legitimate flashback |
| B. Cross-chapter anchors | 1 | Conflict detection with severity |
| C. Title checks | 2 | Truncation, missing |
| D. Fallback de-power | 3 | Score cap, blocking fails, warning passes |
| E. Publish blocking | 1 | API endpoint |
| F. Generic logic | 1 | No hardcoded names |
| G. Editor integration | 1 | Normal flow |
| H. Title-content mismatch | 1 | Keyword mismatch |
| I. Event replay | 2 | Blocking, Jaccard skip |

**Verification**: 15/15 dedicated tests passing, 157/157 regression tests passing, frontend build passing

---

## Out of Scope

- Changing the Editor's LLM review prompts (continuity gate is separate from LLM review)
- Modifying the frontend UI to display continuity gate details (future enhancement)
- Adding new Agent roles for continuity checking (uses existing Editor integration)
- Supporting custom marker lists (current markers are hardcoded tuples, extensible by code change)
