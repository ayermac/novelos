# Novelos v6.10.15 — Completion Report

> **Version**: v6.10.15
> **Title**: Megafiction Recall Scaling
> **Status**: Shipped
> **Date**: 2026-07-01

---

## Summary

v6.10.15 scales context recall for projects with 1000+ chapters by introducing DB-layer tiered loading, a lightweight index spine, and Planner integration that caps DB reads from ~5000 rows to ~300 rows.

## Delivered Changes

### S9 — DB-Layer Tiered Loading

- `list_story_facts_tiered` in `StoryFactRepositoryMixin` with three-tier SQL query:
  - Tier 1: recent N chapters (full detail)
  - Tier 2: numeric_state always loaded
  - Tier 3: aged facts with age >= threshold
- Falls back to full load on SQL error

### S10 — Index Spine

- `context/index_spine.py`: compact fact directory (~15 chars/row) injected into `advisory_context`
- Deduplicated, capped at 200 rows / 4000 chars
- Excludes numeric_state (shown in mandatory bucket)
- Lets agents know "what lines exist" without loading full value_json payloads

### S11 — Planner/Agent Tiered Integration

- `_story_facts_context` auto-detects megafiction (>50 chapters) and switches to `list_story_facts_tiered`
- `list_story_fact_index` provides lightweight index for the spine
- For small projects, behavior unchanged (full load)
- Index spine injection into `advisory_context` via `_inject_recall_extras`

### Tests

- `test_v61015_tiered_loading.py`: 12 tests
- `test_v61015_index_spine.py`: 8 tests
- Combined with v6.10.14: 76 tests passing, 0 regressions

## Verification

- 20 new unit tests (all passing)
- Version bumped to 6.10.15

## Known Follow-Up Risk

- Tiered loading threshold (50 chapters) is heuristic; may need tuning based on real project profiles
- Index spine truncation at 200 rows may drop important but older facts for very long projects

## Documentation

- `docs/codex/planning/novel-factory-v6.10.15-megafiction-recall-scaling-plan.md`: original plan
- `CHANGELOG.md`: v6.10.15 entry
