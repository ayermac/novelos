# Novelos v6.10.5 — Completion Report

> **Version**: v6.10.5
> **Title**: Story Contract Governance
> **Status**: Shipped
> **Date**: 2026-06-11

---

## Summary

v6.10.5 introduces the Story Contract system for project-level narrative governance, extending ChapterBrief with core-loop fields and injecting contracts into all agent prompts.

## Delivered Changes

### Story Contract Model

- `StoryContract`, `CoreLoopStep`, `SupportingMechanism`, `DriftRule` models
- Project-level contract governs what each book must keep delivering
- Contract generation alongside launch profile and genre contract
- Approval activates the story contract for enforceable checks

### ChapterBrief Extension

- Core-loop target, primary payoff, payoff evidence plan
- Supporting mechanisms, new mechanism budget, drift risks, contract checklist
- Structured contract fields for downstream agent consumption

### Prompt Injection

- Planner, screenwriter, author, polisher, and editor receive role-specific Story Contract context
- Via `AgentContextBuilder` and legacy agent build-context paths

### Core Loop Quality Gate

- `core_loop_compliance` diagnostics detect: missing core payoff, supporting-mechanism dominance, new mechanism overload, protagonist agency gaps
- Chapter-level contract metrics persisted as creative ledger snapshots

### Creative Contracts UX

- Project Creative Contracts module displays and edits: core promise, core loop, supporting mechanisms, payoff types, drift rules, cadence, status

### Version Alignment

- Backend runtime and frontend packages bumped to `6.10.5`

## Verification

- `pytest tests/test_v6105_story_contract_models.py tests/test_v6105_core_loop_checker.py tests/test_v6105_workflow_contract_injection.py tests/test_v6105_story_contract_api.py -q`: 61 passed
- `pytest tests/test_v690_repository_integration.py tests/test_v690_chapter_brief.py tests/test_v690_rhythm_budget.py -q`: 92 passed
- `npm run typecheck`: passed
- `npm run build`: passed

## Known Follow-Up Risk

- Core loop evidence governance (v6.10.7) expands on this foundation by adding evidence-based payoff detection
- Drift rules are currently advisory; may need escalation to blocking in future versions

## Documentation

- `docs/codex/planning/novel-factory-v6.10.5-story-contract-governance-plan.md`: original plan
- `CHANGELOG.md`: v6.10.5 entry
