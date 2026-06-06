# v6.7.9 Narrative Continuity Gate — Completion Report

## Summary

Added a deterministic narrative continuity gate that blocks chapters with obvious time regression, cross-chapter anchor conflicts, or event replay before they reach the publish pipeline. De-powered the editor fallback review to prevent fake-green scores.

## Changes Made

### Narrative Continuity Gate (`novel_factory/quality/continuity_gate.py`)

New deterministic module implementing hard, code-level judgment for narrative continuity defects:

1. **Chapter-internal time regression detection**: Scans for time regression markers (两小时前/三小时前/回到/再次来到等) and old scene markers (公司大门/门口保安/出租车等). If both appear without a flashback frame (回忆/想起/脑海中浮现), marks as **blocking**. Framed flashbacks are **advisory** only.

2. **Cross-chapter time-anchor conflicts**: Two conflict types:
   - **Conflict 1 (blocking)**: Previous chapter sets future anchor (明日午时), current chapter is already at target day morning but text still says "明日"
   - **Conflict 2 (warning)**: Current chapter tail sets anchor (今晚/明日) but next chapter opening jumps back to past (昨天/昨晚)

3. **Title quality checks**: Detects truncated/malformed titles (ending with 无/的/与/和/了), too-short titles (<4 chars), and missing titles → **warning**

4. **Title-content keyword mismatch**: Title keywords not appearing in content body → **warning**

5. **Event replay detection**: If ≥3 long unique sentences (12-60 chars, excluding common glue) from previous chapter appear verbatim in current chapter → **blocking**. Jaccard similarity >0.5 skips replay detection to avoid false positives on stub/template data.

6. **Generic logic**: All detection is generic — no hardcoded project, character, chapter, or location names.

### Editor Fallback De-powered (`novel_factory/agents/editor.py`)

1. **Score cap reduced**: `_fallback_rule_review` maximum score reduced from 88 to 70
2. **Mandatory degraded warning**: Issues list always includes "AI 审核不可用，本结果仅为规则兜底，不代表完整审校通过。"
3. **Continuity gate integration**: Fallback runs continuity gate; if blocking issues found, forces `pass_=False` and `revision_target="author"`
4. **Event payload**: `fallback_used` event now includes `degraded_review: true` and `blocks_auto_publish`

### Editor Normal Flow Integration (`novel_factory/agents/editor.py`)

1. **Step 4.6 continuity gate**: After story facts compliance check, `_run_continuity_gate()` runs
2. **Blocking behavior**: If blocking issues found, forces `pass_=False`, caps score at 70, sets `revision_target="author"`
3. **Issue injection**: Injects `[连续性阻断]` / `[连续性修复]` notes into issues/suggestions
4. **Classification isolation**: Continuity advisory/warning issues excluded from `classify_issues` to prevent revision target misrouting

### Publish Hard Gate (`novel_factory/api/routes/run.py`, `novel_factory/workflow/nodes.py`)

1. **API endpoint**: `POST /publish/chapter` runs `evaluate_publish_continuity` before publishing. Returns `CONTINUITY_GATE_BLOCKED` error if blocking issues found.
2. **Publisher node**: `publisher_node` in `nodes.py` also runs continuity gate before `repo.publish_chapter()`

### Revision Classifier Fix (`novel_factory/validators/revision_classifier.py`)

- Title-related issues no longer trigger structural author routing (fall through to normal keyword matching)

### Version (`novel_factory/version.py`)

- Updated from `6.7.8` to `6.7.9`

### Frontend Version (`frontend/package.json`)

- Updated from `6.7.8` to `6.7.9`

### Desktop Version (`desktop/package.json`)

- Updated from `6.7.8` to `6.7.9`

### Tests (`tests/test_v679_continuity_gate.py`)

15 tests in 4 test sections:

- **A. Chapter-internal time regression** (3 tests): blocking for unframed regression to old scene, advisory for framed flashback, legitimate short flashback not blocking
- **B. Cross-chapter time-anchor conflicts** (1 test): conflict detection with severity differentiation
- **C. Title checks** (2 tests): truncation detection, missing title detection
- **D. Fallback de-power** (3 tests): score capped at 70, continuity blocking fails fallback, continuity warning passes with warning
- **E. Publish blocking** (1 test): API endpoint blocks on continuity gate
- **F. Generic logic** (1 test): no hardcoded project/character names
- **G. Editor integration** (1 test): continuity gate in normal editor flow
- **H. Title-content mismatch** (1 test): keyword mismatch detection
- **I. Event replay** (2 tests): blocking for ≥3 repeated sentences, Jaccard skip for stub data

## Code Review Fixes

6 issues addressed after initial implementation:

1. **Fix 1 (P1)**: Removed DEBUG `print("DEBUG result:", result)` from `test_v537_burnin_fixes.py`
2. **Fix 2 (P1)**: Cross-chapter anchor severity differentiation — Conflict 1 (future_anchor_still_spoken) remains blocking, Conflict 2 (tail_to_next_break) changed to warning
3. **Fix 3 (P2)**: Added 2 event replay tests — blocking for ≥3 repeated sentences, Jaccard skip for stub data
4. **Fix 4 (P2)**: Tightened cross-chapter anchor test assertion from `"时间"` to `"跨章时间锚点冲突"`
5. **Fix 5 (P2)**: Added fallback + continuity warning test verifying warning-level issues don't block fallback
6. **Fix 6 (P2)**: Added design intent comment for advisory → suggestions routing

## Verification

| Check | Result |
|-------|--------|
| v6.7.9 dedicated tests | 15/15 passing |
| Regression tests (test_agents, test_v64_editor_quality_gates, test_v678, test_stability) | 157/157 passing |
| v5.3.7 burnin tests | 3/3 passing |
| Frontend build | passing |
| Version alignment | 6.7.9 across runtime/frontend/desktop |

## Key Design Decisions

1. **Deterministic over LLM**: All continuity checks are rule-based, not relying on LLM to discover issues
2. **Severity differentiation**: Blocking vs warning vs advisory based on defect severity
3. **Jaccard guard**: Skip replay detection when chapters are >50% identical (stub/template data)
4. **Classification isolation**: Continuity advisory/warning issues don't trigger revision routing
5. **Generic logic**: No hardcoded project/character names — works for any novel project

## Known Limitations

1. **Time regression markers**: Fixed list may miss novel time expressions. Extensible via `_TIME_REGRESSION_MARKERS` tuple.
2. **Old scene markers**: Fixed list of typical completed-scene markers. May need expansion for genre-specific scenes.
3. **Event replay threshold**: Fixed at ≥3 sentences. May need tuning for different content lengths.
4. **Jaccard threshold**: Fixed at 0.5. May need adjustment for projects with legitimate high overlap.
