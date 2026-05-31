# Novel Factory v6.8.2 — Revision Reliability Hardening

**Version**: v6.8.2  
**Type**: Bug Fix + Reliability Hardening  
**Priority**: HIGH  
**Target Date**: 2026-06-01  
**Status**: Planning

---

## Overview

v6.8.2 addresses critical reliability issues in the revision loop that cause frequent chapter blocking. Analysis shows that revision context loss, length control drift, and overly permissive plateau guards are the primary causes of revision failures.

**Problem Statement**: Users report frequent chapter revision blocking, with chapters stuck in retry loops or passing through with substandard quality (78-79 scores).

**Root Causes**:
1. Revision context (Editor review) may be lost during Agent execution
2. Revision length control thresholds are too wide, allowing drift
3. Near-miss plateau guard (78-79 score) triggers too early
4. Internal repair escalation is opaque to users
5. Editor fallback is too conservative (max 70 score)
6. Scene beat coverage warning semantics are inconsistent

---

## Goals

### Primary Goals
- **G1**: Eliminate revision context loss — ensure Author/Polisher always receive Editor feedback
- **G2**: Tighten revision length control — reduce expansion/compression drift
- **G3**: Improve plateau guard reliability — prevent premature pass on marginal quality

### Secondary Goals
- **G4**: Enhance internal repair observability — make escalation visible to users
- **G5**: Relax Editor fallback ceiling — allow fallback to approach pass threshold
- **G6**: Unify scene beat coverage semantics — align Author warning with Editor judgment

---

## Technical Design

### Phase 1: Revision Context Hardening (HIGH)

#### 1.1 Strengthen revision_router_node Hydration

**File**: `novel_factory/workflow/nodes.py`

**Changes**:
- Hydrate `retry_count` in addition to `quality_gate` and `_revision_review`
- Force-load `_revision_review` from DB if still missing after hydration
- Log when force-load occurs

#### 1.2 Add Revision Context Validation

**Files**: `novel_factory/agents/author.py`, `novel_factory/agents/polisher.py`

**Changes**:
- Validate `revision_review` exists when `chapter.status == REVISION`
- Return error with `requires_human=True` if context missing
- Set `quality_gate.context_missing = True` for monitoring

---

### Phase 2: Revision Length Control Tightening (HIGH)

#### 2.1 Reduce Expansion Threshold

**File**: `novel_factory/agents/author.py`

**Change**: `expansion_limit = max(700, int(original_wc * 0.18))` → `max(400, int(original_wc * 0.12))`

#### 2.2 Enhance Compression Detection

**File**: `novel_factory/agents/author.py`

**Change**: Expand `_revision_requests_compression()` keywords from 3 to 12:
- Add: "删减", "去掉", "减少", "过长", "冗余", "啰嗦", "拖沓", "重复", "字数过多", "篇幅过大", "超出", "超标"

#### 2.3 Add Cumulative Budget Tracking

**File**: `novel_factory/agents/author.py::_try_segmented_plain_text_draft`

**Change**: Track accumulated word count after each segment, warn and adjust if approaching upper bound

---

### Phase 3: Plateau Guard Tuning (MEDIUM)

#### 3.1 Raise Plateau Trigger Threshold

**File**: `novel_factory/quality/editor_strategy.py`

**Changes**:
- Score threshold: 78 → 79
- Retry threshold: `> 0` → `>= 2`
- Update reason message to reflect new thresholds

---

### Phase 4: Internal Repair Observability (MEDIUM)

#### 4.1 Enhance Event Logging

**File**: `novel_factory/workflow/nodes.py::_handle_retryable_quality_gate`

**Changes**:
- Add `internal_repair_count` and `internal_repair_limit` to event payload
- Show progress in message: "(内部修复 X/2)"

#### 4.2 Log Escalation Event

**File**: `novel_factory/workflow/nodes.py::_handle_retryable_quality_gate`

**Change**: Add `internal_repair_escalated` event when escalating to chapter retry

---

### Phase 5: Editor Fallback Relaxation (LOW)

#### 5.1 Raise Fallback Ceiling

**File**: `novel_factory/agents/editor.py::_fallback_rule_review`

**Change**: `max_score = 70` → `max_score = 78`

---

### Phase 6: Scene Beat Semantic Alignment (LOW)

#### 6.1 Mark Warnings as Advisory

**File**: `novel_factory/quality/editor_strategy.py::count_issue_types`

**Change**: Recognize "场景 beat 覆盖不完整" + "已降级为警告" as advisory issue

---

## Implementation Plan

### Sprint 1: High Priority (Days 1-2)
- Phase 1: Revision context hardening
- Phase 2: Length control tightening
- Unit tests for Phases 1-2

### Sprint 2: Medium Priority (Day 3)
- Phase 3: Plateau guard tuning
- Phase 4: Internal repair observability
- Unit tests for Phases 3-4

### Sprint 3: Low Priority (Day 4)
- Phase 5: Editor fallback relaxation
- Phase 6: Scene beat semantic alignment
- Unit tests for Phases 5-6
- Integration testing

### Sprint 4: Validation (Day 5)
- Full test suite (2616+ tests)
- Manual validation with real project
- Documentation updates
- Release v6.8.2

---

## Testing Strategy

### New Test Files
- `tests/test_v682_revision_context_validation.py`
- `tests/test_v682_revision_length_control.py`
- `tests/test_v682_plateau_guard.py`
- `tests/test_v682_internal_repair_observability.py`

### Acceptance Criteria
- [ ] All 2616+ existing tests pass
- [ ] 24+ new tests for v6.8.2 features
- [ ] Manual test: Real project revision completes without blocking
- [ ] No regression in revision success rate

---

## Risks & Mitigations

**Risk 1**: Tighter length control may increase revision failures  
**Mitigation**: Monitor failure rate; relax to 15% if >10% increase

**Risk 2**: Plateau delay may frustrate users  
**Mitigation**: Log decision in events; show progress in frontend

**Risk 3**: Context validation may block valid workflows  
**Mitigation**: Only enforce when `status == REVISION`; clear error messages

---

## Success Criteria

1. ✅ All 6 phases implemented and tested
2. ✅ Full test suite passes (2640+ tests)
3. ✅ Manual validation successful
4. ✅ No critical regressions in 7 days
5. ✅ Revision success rate stable or improved

---

**Spec Author**: Claude (Opus 4.8)  
**Review Status**: Pending Human Approval  
**Next Step**: Await approval, then begin Sprint 1 implementation
