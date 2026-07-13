# Novelos v6.10.14 — Completion Report

> **Version**: v6.10.14
> **Title**: Longform Recall Optimization
> **Status**: Shipped
> **Date**: 2026-06-30

---

## Summary

v6.10.14 optimizes context recall for long-form projects by adding mandatory bucket protection, per-bucket truncation, relevance filtering, aging detection, and pull recall channels.

## Delivered Changes

### S1 — Mandatory Bucket Protection

- `format_context_bundle_for_prompt` now force-includes `hard_constraints`, `numeric_state_constraints`, and `timeline_constraints` even when total prompt exceeds `max_chars`
- Eliminates B2/B3 bug where `story_facts` inflation caused numeric state to be dropped

### S2 — Story Facts Relevance Filtering

- `_story_facts_context` accepts optional `brief` parameter and filters facts by entity relevance
- `numeric_state` facts always kept; entity-matched facts kept; aged facts (>=20 chapters) kept
- Without brief, falls back to full-load (no regression)
- Entity extraction uses CJK token splitting plus 2-3 char substring expansion

### S3 — Per-Bucket Truncation (break -> continue)

- Non-mandatory buckets that overflow are truncated in place and the loop *continues* instead of `break`-ing
- Line-by-line truncation avoids UTF-8 multi-byte character corruption

### F8 — Numeric State Truncation Exemption

- `numeric_state` facts exempt from 200-char value truncation
- Ensures mandatory-protected content isn't corrupted by mid-string cuts

### S4 — Aging Detector (`context/aging.py`)

- Detects numeric_state facts not updated for >=15 chapters
- Detects overdue/stale plot holes (>=20 chapters)
- Builds `aging_warning` ContextItems injected into `advisory_context`

### S5 — Pull Recall Channel (`context/recall_channel.py`)

- Proactively retrieves full fact chain for entities mentioned in chapter brief
- Hard upper limit of 10 items
- Injected into `advisory_context` for Author and Editor

### S6 — Continuity Full-Scope Validation

- `continuity_checker._build_context` injects ALL active story_facts as full validation ledger
- Enables detection of contradictions with facts outside `[from, to]` check range

### S7 — Adaptive Budget

- `compute_adaptive_budget`: raises context budget from 14000 to 20000 chars for projects >100 chapters

### F13 — Deprecated Legacy Builder

- `context/builder.py` now emits `DeprecationWarning` on import, directing to `agent_runtime.context_builder`

### F14 — Relaxed Numeric State Limit

- `extract_numeric_state_constraints` limit raised from `[:10]` to `[:20]`

### F15 — Docstring Alignment

- `format_context_bundle_for_prompt` docstring updated to match actual `ordered_buckets` list

### Tests

- 56 new unit tests (all passing): mandatory bucket protection, relevance filtering, numeric state truncation exempt, aging detector, recall channel, continuity full scope

## Verification

- 56 new tests passing
- Full pytest suite: 0 regressions introduced
- Version bumped to 6.10.14 across `version.py`, `frontend/package.json`, `desktop/package.json`, and lockfiles

## Documentation

- `docs/codex/planning/novel-factory-v6.10.14-longform-recall-optimization-plan.md`: original plan
- `CHANGELOG.md`: v6.10.14 entry
