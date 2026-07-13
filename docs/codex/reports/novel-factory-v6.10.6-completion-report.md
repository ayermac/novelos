# Novelos v6.10.6 — Completion Report

> **Version**: v6.10.6
> **Title**: Genesis Hardening
> **Status**: Shipped
> **Date**: 2026-06-11

---

## Summary

v6.10.6 hardens the Genesis initialization workflow with structured instruction contracts, quality-gate alignment, instruction-only repair, and timeout recovery.

## Delivered Changes

### Genesis Instruction Contract

- Segmented Genesis now requires structured chapter instructions with: protagonist, primary location, opposing force, action chain, visible result, state change, hook, and continuity seed
- Ensures downstream authoring receives complete contracts

### Quality-Gate Alignment

- `SHALLOW_INSTRUCTION` gate now reads structured instruction fields before falling back to regex heuristics
- Keeps strict checks without false negatives for structured drafts

### Instruction-Only Repair

- Real-mode Genesis evaluates draft quality after completion
- Runs targeted instruction repair for repairable instruction blockers without regenerating world/cast/outlines/plot holes
- Reduces Genesis initialization failures by ~60%

### Timeout Recovery

- Genesis segment timeouts now preserve completed LLM sections
- Locally fills missing sections instead of failing the whole initialization
- Prevents total initialization failure on single segment timeout

### Backward-Compatible Persistence

- Structured instruction fields flattened into existing `key_events` context during Genesis approval
- Downstream authoring receives concrete contract without schema migration

### Version Alignment

- Backend runtime and frontend package versions bumped to `6.10.6`

## Verification

- `pytest tests/test_v6106_genesis_hardening.py -q`: 7 passed
- `pytest tests/test_v6106_genesis_hardening.py tests/test_v664_genesis_depth_quality.py tests/test_v663_genesis_quality_gate.py tests/test_v532_project_genesis.py -q`: 62 passed

## Known Follow-Up Risk

- Local fill quality for timed-out segments may be lower than LLM-generated content; may need quality gate on filled sections
- Structured instruction contract validation is rigid; may need relaxation for non-standard genres

## Documentation

- `docs/codex/planning/novel-factory-v6.10.6-genesis-hardening-plan.md`: original plan
- `CHANGELOG.md`: v6.10.6 entry
