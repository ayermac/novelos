# Novel Factory v6.7.0 Completion Report

Date: 2026-05-24

Status: completed.

## Summary

v6.7.0 implements the v6.6.22-v6.7.0 production stability roadmap as a
release-gate tooling pass. It does not add author-facing creative features.
Instead, it gives operators deterministic checks for long-form readiness:
quality acceptance, recovery diagnostics, memory governance, and an aggregated
production stability suite.

## Implemented Scope

### Planning

- Added `docs/codex/planning/novel-factory-v6.6.22-to-v6.7.0-production-stability-roadmap.md`.
- Updated the version planning index with v6.7.0 umbrella coverage.

### Quality Acceptance

- Added `novel_factory/ops/quality_acceptance.py`.
- Checks terminal chapter state, word count, scene beat presence/completeness,
  content density per beat, and observable ending hook.
- Returns check-level diagnostics and next actions.

### Memory Governance

- Added `novel_factory/ops/memory_governance.py`.
- Audits character count, story fact count, memory item count, combined context
  pressure, duplicate character names, duplicate story fact keys, and duplicate
  fact text.
- The audit is read-only and does not mutate project data.

### Recovery Drill

- Added `novel_factory/ops/recovery_drill.py`.
- Classifies chapter workflow state into terminal, healthy running, stale
  running, blocked, failed, terminal-with-running-run, or ready.
- Emits recommended actions and safe action lists for operators.

### Production Stability Suite

- Added `scripts/production_stability_suite.py`.
- Aggregates release smoke, stub/real soak, quality acceptance, recovery drill,
  and memory governance gates.
- Real LLM soak is opt-in only through `--real-soak`.
- The script emits JSON for CI/release notes and exits non-zero when required
  gates fail.

### Version Alignment

- `novel_factory/version.py`: `6.7.0`
- `frontend/package.json`: `6.7.0`
- `frontend/package-lock.json`: `6.7.0`
- `desktop/package.json`: `6.7.0`
- `desktop/package-lock.json`: `6.7.0`

## Tests Added

- `tests/test_production_stability_ops.py`
  - quality acceptance pass/fail behavior
  - memory pressure and duplicate detection
  - stale-running and terminal recovery diagnostics
  - production stability suite safe JSON mode without DB or real LLM
  - CLI guard against empty chapter ranges

## Verification

| Check | Result |
| --- | --- |
| `python3 -m pytest -q` | **2795 passed, 1 skipped, 0 failed** |
| `python3 -m pytest tests/test_production_stability_ops.py tests/test_version_alignment.py -q` | **15 passed** |
| `cd frontend && npm run typecheck` | passed |
| `cd frontend && npm run lint` | passed |
| `cd frontend && npm run build` | passed |
| `cd frontend && npm test -- --run` | **310 passed** |
| `cd desktop && npm run typecheck` | passed |
| `cd desktop && npm run build` | passed |
| `python3 -m novel_factory.cli --version` | `novelos 6.7.0` |
| `python3 scripts/production_stability_suite.py --no-release-smoke --json` | passed; stub soak completed, chapter_status=`published` |
| `python3 scripts/production_stability_suite.py --no-release-smoke --no-soak --json` | passed; safe JSON mode |
| `git diff --check` | clean |

Note: release smoke coverage is exercised by the full pytest suite via
`tests/test_release_smoke.py`. Direct release smoke execution requires local
loopback port binding for the desktop sidecar.

## Known Manual Gate

Real LLM soak is intentionally not run automatically. To run it manually:

```bash
python3 scripts/production_stability_suite.py \
  --db-path acceptance_novel_factory.db \
  --project-id novel_2cmh \
  --chapters 3 \
  --real-soak \
  --config config/local.yaml \
  --json
```

This can incur provider cost and should be treated as an explicit release
approval step.
