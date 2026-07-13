# Novelos v6.10.9 — Completion Report

> **Version**: v6.10.9
> **Title**: Core Loop Pre-Constraints & Fact Lock Awareness
> **Status**: Shipped
> **Type**: Hotfix (v6.10.8 follow-up)

---

## Summary

v6.10.9 adds pre-constraints to the core loop and introduces fact lock awareness in Planner/Screenwriter, preventing structural gaps between pre-planning design and post-hoc Editor detection.

## Delivered Changes

### Core Loop Pre-Constraints

- Planner output now includes "core loop fulfillment" constraints: tells Author which scene must deliver the payoff
- Prevents chapters from missing core payoff targets

### Fact Lock Awareness

- Screenwriter reads character current physical state from `story_facts` (fact locks)
- Prevents beats from violating established character constraints (e.g., locked limb still used in action)
- Fact lock errors surface as `advisory` warnings rather than blocking to avoid over-constraining creative freedom

### Dialogue Slots / Character States JSON Fix

- Fixed JSON string parsing crash in `dialogue_slots` and `character_states` fields
- Prevents workflow crashes on malformed JSON from LLM output

### Beat Count Constraints

- Added `skip_to_quality_gate` for chapters with insufficient beat count
- Score degradation detection: warns when chapter quality drops across revisions

### Database Migration

- Migration 040: persistent `core_loop` and `scene_beats` new columns
- Ensures pre-constraint data survives across sessions

### Version Alignment

- Backend runtime bumped to `6.10.9`

## Verification

- All existing tests pass (no regressions)
- Migration 040 verified on existing projects

## Known Follow-Up Risk

- Fact lock awareness is advisory-only; may need escalation to blocking for critical continuity errors
- Pre-constraint enforcement is prompt-based; may need structured validation in v6.10.10+

## Documentation

- `docs/codex/planning/novel-factory-v6.10.9-core-loop-evidence-governance.md`: original plan
- `CHANGELOG.md`: v6.10.9 entry (via v6.10.10 CHANGELOG reference)
