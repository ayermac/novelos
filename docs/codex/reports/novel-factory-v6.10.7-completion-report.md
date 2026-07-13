# Novelos v6.10.7 — Completion Report

> **Version**: v6.10.7
> **Title**: Core Loop Evidence Governance
> **Status**: Shipped
> **Type**: Hotfix (v6.10.8 follow-up)

---

## Summary

v6.10.7 implements protagonist integrity defense-in-depth with a 4-layer validation system and fixes character memory update edge cases without target_id.

## Delivered Changes

### Protagonist Integrity Defense-in-Depth (4-Layer)

- Layer 1: Prompt constraint injection — protagonist physical state locked in planner/screenwriter prompts
- Layer 2: Beats validation — screenwriter validates protagonist state consistency across scene beats
- Layer 3: Author awareness — protagonist state injected into author context with explicit lock markers
- Layer 4: Editor enforcement — continuity gate checks protagonist state against established facts

### Character Memory Update Fixes

- Two-layer defense for character memory update without `target_id`: fallback to `target_name` matching, then subject-attribute matching
- Unified `target_name` fallback for all memory tables (`resolve`/`deprecate` downgrade to advisory)
- School-location synonym bridging in chapter seam check (`学院` -> `学校`)

### Word Target Derivation

- Prevents LLM from hallucinating `word_target`; derives from project config instead
- Reduces author/agent word count misalignment

### Version Alignment

- Backend runtime bumped to `6.10.7`

## Verification

- `pytest -q`: all existing tests pass

## Known Follow-Up Risk

- 4-layer defense adds prompt overhead; may need token budget adjustment for long chapters
- Synonym bridging is limited to Chinese education domain; general synonym map deferred

## Documentation

- `docs/codex/planning/novel-factory-v6.10.7-core-loop-evidence-governance-plan.md`: original plan
- `CHANGELOG.md`: v6.10.7 entry (via v6.10.8 CHANGELOG reference)
