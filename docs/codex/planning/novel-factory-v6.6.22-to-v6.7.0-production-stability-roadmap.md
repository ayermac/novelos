# v6.6.22 to v6.7.0 Production Stability Roadmap

Status: implementation plan for the production-stability branch.

This umbrella plan turns the post-v6.6.21 stabilization direction into concrete
release gates. The goal is not to add new authoring features; it is to make
long-form real-LLM production measurable, recoverable, and safe to promote.

## Scope

The branch implements the following release slices as one cohesive stability
tooling pass:

| Version | Theme | Deliverable |
| --- | --- | --- |
| v6.6.22 | Real LLM Soak & Quality Acceptance | Deterministic quality acceptance checks and a production stability suite that can run stub soak by default and real soak only by explicit opt-in. |
| v6.6.23 | Workflow Recovery & Fault Self-Healing | Recovery drill diagnostics for blocked/failed/running chapter workflows, including safe recommended actions. |
| v6.6.24 | Long-Form Memory Governance | Project memory audit for duplicate facts, context pressure, and memory trust coverage. |
| v6.6.25 | Quality Closure & Explainable Editing | Chapter quality acceptance report with explicit failed checks and operator-readable next actions. |
| v6.7.0 | Production Candidate Gate | One command that aggregates release smoke, soak, quality, recovery, and memory gates into a machine-readable release-candidate verdict. |

## Architecture

New deterministic ops modules live under `novel_factory/ops/` so scripts and
tests can share logic without shelling out. Scripts under `scripts/` are thin
CLI wrappers that run the gates and emit JSON suitable for release notes or CI.

```text
novel_factory/ops/quality_acceptance.py   chapter quality gate primitives
novel_factory/ops/memory_governance.py    memory/context pressure audit
novel_factory/ops/recovery_drill.py       workflow recovery diagnostics
scripts/production_stability_suite.py     aggregated production-candidate gate
```

## Acceptance Criteria

- `production_stability_suite.py --json` runs without real API keys and returns
  a complete JSON verdict.
- Real LLM execution is never triggered unless `--real-soak` is explicitly set.
- Quality acceptance returns explicit check-level pass/fail data.
- Recovery drill distinguishes terminal, blocked, failed, stale-running, and
  healthy-running workflow states.
- Memory governance reports duplicate facts and context pressure without
  mutating project data.
- The suite exits non-zero if any required gate fails.
- Full backend, frontend, desktop, release smoke, and stub soak verification
  remain passing.

## Non-Goals

- No UI redesign in this branch.
- No automatic mutation of user projects.
- No real LLM run in automated verification without explicit user approval.
- No model-quality claims beyond deterministic acceptance metrics.

## Implementation Tasks

1. Add quality acceptance primitives and tests.
2. Add memory governance audit primitives and tests.
3. Add recovery drill primitives and tests.
4. Add `scripts/production_stability_suite.py`.
5. Update version and docs to the production stability gate baseline.
6. Run verification and perform final code review.

## Manual Real-LLM Gate

The final production candidate still requires one manual real-LLM soak:

```bash
python3 scripts/production_stability_suite.py \
  --db-path acceptance_novel_factory.db \
  --project-id novel_2cmh \
  --chapters 3 \
  --real-soak \
  --config config/local.yaml \
  --json
```

This command may incur provider cost and must not be run automatically.
