# v6.6.8 Editor Refactor & Review Semantics Closure — Completion Report

## Summary

Refactored Editor's monolithic `_execute()` into 7 clear pipeline steps with typed data classes. Established a single policy decision point (`classify_editor_result`) via `EditorPolicyInput`. Unified review semantics with explicit rules for advisory/priority/blocking/death penalty routing.

## Changes

### Core: `novel_factory/quality/editor_strategy.py`
- Added `EditorPolicyInput` dataclass with all policy-relevant fields
- Added `EditorDecisionType` literal with `advisory`, `advisory_pass`, `revision`, `human_review`, `blocking`
- Added `count_issue_types()` for heuristic blocking/priority/advisory classification
- Added `build_policy_input()` to merge raw editor state into `EditorPolicyInput`
- Added `determine_revision_target()` with explicit routing rules (never returns empty)
- Rewrote `classify_editor_result()` to accept both `EditorPolicyInput` and legacy keyword args
- Updated `post_process_llm_decision()` with `retry_count`/`max_retries` support

### Core: `novel_factory/agents/editor.py`
- Added `EditorInputs`, `QualityDiagnosisResult`, `SeamCheckResult` dataclasses
- Refactored `_execute()` into 7 clear steps:
  1. `_load_editor_inputs()` — load all inputs
  2. `_call_editor_llm()` — LLM call with fallback
  3. `_run_quality_diagnosis()` — QualityHub + feedback bridge
  4. `_run_chapter_seam_check()` — chapter seam evaluation
  5. `_apply_review_strategy()` — THE single decision point
  6. `_persist_editor_artifacts()` — save review/state/artifacts
  7. `_build_editor_state_updates()` — status transitions
- Added `_run_before_review_skills()`, `_run_final_gate()` as extracted helpers
- Added `_build_artifact_payload()` with `_strategy_decision` and `_seam_check` snapshots
- Used DB retry count for circuit breaker (not just state)
- Gate-set revision_target (word count, seam) now preserved over `classify_issues` override

### Tests: `tests/test_v668_editor_semantics.py` (NEW)
- 36 tests covering all classification rules, revision target defaults, boundary conditions
- Pure function tests for `classify_editor_result`, `determine_revision_target`, `count_issue_types`
- Integration tests for EditorAgent behavior compatibility

## Verification

- Backend: 2360/2360 pytest passed
- Frontend: typecheck/lint/build passed
- `git diff --check` clean

## Semantic Guarantees

1. **advisory-only never triggers auto revision** — score >= 85 with only advisory → `advisory` (pass)
2. **diagnosis score never replaces review score** — `EditorPolicyInput.score` is always the review score
3. **revision_target never empty for revision** — `determine_revision_target()` defaults to `"polisher"`
4. **death penalty / blocking always hard-blocks** — Rule 1 in classification
5. **score 80-84 + no priority → advisory pass** — Rule 4, not auto revision
6. **retry_count >= max_retries → human_review** — Rule 2, no more auto revision
