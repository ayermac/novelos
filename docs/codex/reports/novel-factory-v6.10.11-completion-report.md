# Novelos v6.10.11 — Completion Report

> **Version**: v6.10.11
> **Title**: Story Facts Deduplication Fix
> **Status**: Shipped
> **Date**: 2026-06-23

---

## Summary

v6.10.11 is a hotfix that deduplicates story facts before passing them to Author and Editor, eliminating false positives from contradictory active facts.

## Delivered Changes

### Story Facts Deduplication

- `_story_facts_context()` in `agent_runtime/context_builder.py` now keeps only the latest `source_chapter` fact per `subject.attribute`
- Prevents contradictory facts from being passed to the Author

### Editor Compliance Fix

- `_run_story_facts_compliance()` in `agents/editor.py` applies the same deduplication before checking chapter content
- Eliminates false positives from outdated active facts

### Context Fragment Deduplication

- `_frag_story_facts()` in `context/builder.py` also deduplicates so the UI context does not display contradictory facts

### Version Alignment

- Backend runtime, frontend, and desktop packages bumped to `6.10.11`

## Verification

- `pytest tests/test_v532_memory_loop.py tests/test_v662_context_inheritance.py tests/test_v6614_continuity_enforcement.py tests/test_v6109_core_loop_evidence_governance.py tests/test_v667_memory_curator_reliability.py -q`: 187 passed
- `pytest tests/test_version_alignment.py -q`: 8 passed
- `pytest -q --tb=no`: 3,599 passed, 27 failed (pre-existing failures unrelated to this change)

## Known Follow-Up Risk

- The remaining `active` duplicate facts in existing projects may still cause confusion until a cleanup script or automatic supersession is implemented (addressed in v6.10.12 plan)

## Documentation

- `CHANGELOG.md`: v6.10.11 entry
