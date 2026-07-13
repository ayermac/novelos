# Novelos v6.10.10 — Completion Report

> **Version**: v6.10.10
> **Title**: Core Loop Evidence Governance & Word Count Tolerance
> **Status**: Shipped
> **Type**: Hotfix

---

## Summary

v6.10.10 is a hotfix that strengthens core loop evidence governance and relaxes word count tolerance to reduce false blocking.

## Delivered Changes

### Core Loop Evidence Governance

- Editor core loop checker now evaluates evidence-based payoff completion rather than keyword-only matching
- Reduces false blocking on transition chapters where core payoff is legitimately deferred

### Word Count Tolerance

- Relaxed word count gate tolerance for real-mode LLM variance
- Prevents chapters within acceptable variance from being incorrectly flagged

### Version Alignment

- Backend runtime and frontend packages bumped to `6.10.10`

## Verification

- `pytest -q`: all existing tests pass (no new regressions)

## Known Follow-Up Risk

- Core loop evidence governance fully expanded in v6.10.7 plan
- Word count tolerance may need further tuning based on real-mode project data

## Documentation

- `CHANGELOG.md`: v6.10.10 entry
