# Novelos v6.10.19 — Completion Report

> **Version**: v6.10.19
> **Title**: Repository Aggregation — Store Facade Phase A + B
> **Status**: Shipped
> **Date**: 2026-07-09

---

## Summary

v6.10.19 introduces the Store facade layer over 34 repositories, implementing 8 read-only aggregation Stores (BaseStore + ProgressStore + DraftStore + WorldStore + SummaryStore + CharacterStore + OutlineStore + SignalStore + CheckpointStore) to reduce N+1 query patterns and centralize repository access patterns.

## Delivered Changes

### Phase A — Core Stores (4 Stores)

- `BaseStore`: single Repository instance facade (no per-mixin dispatch)
- `ProgressStore`: aggregates workflow + execution_event (7 aggregation methods)
- `DraftStore`: aggregates chapter + instruction + scene_beats (4 aggregation methods)
- `WorldStore`: aggregates story_fact + plot_hole + agent_memory (6 aggregation methods)

### Phase B — Extended Stores (5 Stores)

- `SummaryStore`: project-level summary aggregation
- `CharacterStore`: character state and history aggregation
- `OutlineStore`: outline and arc planning aggregation
- `SignalStore`: cross-session signal persistence
- `CheckpointStore`: workflow checkpoint aggregation

### Design Spec

- `docs/codex/design/v6.10.19-store-interface-spec.md`: complete spec with real method signatures + N+1 risk matrix
- Key correction: `BaseStore(repo)` instead of `_get_repo()` dispatch (Repository is already a single facade class)

### v6.10.18 Carry-Over

- Unified `ChapterBriefValidator` with plugin checker extension
- Migration 039: 4 new ChapterBrief columns to instructions table
- `novel_factory/db/data_migrations/migrate_001_chapter_brief_fields.py`: data migration script with --dry-run and backup

### Tests

- Store unit tests covering all 8 Stores aggregation methods
- N+1 detection tests for `ProgressStore._collect_active_runs`

## Verification

- `pytest -q`: 3,749 passed, 0 failed
- All deferred caller migration to v6.11.0 (Stores remain read-only; writes continue via `store.repo`)

## Known Follow-Up Risk

- Caller migration from direct repository calls to Store aggregation is deferred to v6.11.0
- Frontend Store adoption not yet started

## Documentation

- `docs/codex/planning/novel-factory-v6.10.19-repository-consolidation-plan.md`: original plan
- `docs/codex/design/v6.10.19-store-interface-spec.md`: design spec
- `CHANGELOG.md`: v6.10.19 entry
