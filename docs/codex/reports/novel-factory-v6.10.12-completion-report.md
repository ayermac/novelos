# Novelos v6.10.12 — Completion Report

> **Version**: v6.10.12
> **Title**: Production Stability Hardening
> **Status**: Shipped
> **Date**: 2026-06-23

---

## Summary

v6.10.12 hardens production stability by adding author over-expansion control, core loop drift detection, and story fact governance with automatic conflict resolution.

## Delivered Changes

### Author Over-Expansion Control

- Added revision length constraints to Author prompts (15% growth limit)
- Automatic compression when drafts exceed allowed expansion threshold
- New `_try_repair_revision_length_overexpansion()` method in `agents/author.py` auto-repairs bloated revisions

### Core Loop Drift Detection

- Extended deterministic `state_delta` patterns in `quality/core_loop_checker.py`
- Recognizes natural-language descriptions of state changes: `归零`, `清零`, `耗尽`, `见底`, `失去`, `消耗`, `抽干` for resource depletion detection

### Story Fact Governance

- Added automatic conflict resolution in `api/routes/memory_updates.py`
- New facts with same `subject+attribute` but different value now auto-supersede older active facts
- Executed cleanup script on novel_978q: 260 facts -> 224 unique (36 duplicates superseded)

### Version Alignment

- Backend runtime, frontend, and desktop packages bumped to `6.10.12`

## Verification

- `pytest -q --tb=no`: 3,597 passed, 29 failed (pre-existing failures, no new regressions)
- Story facts cleanup: `scripts/cleanup_story_facts.py` executed successfully on novel_978q

## Known Follow-Up Risk

- None. v6.10.12 completes the production stability hardening cycle.

## Documentation

- `docs/codex/planning/novel-factory-v6.10.12-production-stability-hardening-plan.md`: original plan
- `CHANGELOG.md`: v6.10.12 entry
