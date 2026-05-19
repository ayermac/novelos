# v6.6.10 API Contract & Frontend State Semantics Closure — Review

## Scope

- New `novel_factory/api/contracts.py` with OperationResult / DomainStatus
- Frontend `statusSemantics.ts` with unified display/query helpers
- Integration into `GET /api/runs/{run_id}` and `POST /api/runs/{run_id}/memory/backfill`
- Backend and frontend test coverage

## Findings

### P0 — None

### P1 — None

### P2 — Fixed During Review

1. **`partial_success()` missing `next_action` parameter** — `workflow_run_to_domain_status()` called `partial_success()` with `next_action` and `action_label` but the helper didn't accept those parameters. **Fixed**: Added `next_action` and `action_label` parameters to `partial_success()`.

2. **Backfill error response format breakage** — Initial implementation replaced `error_response("MEMORY_CURATOR_INCOMPLETE", ...)` with a manually constructed envelope, breaking the existing test that expected `data["error"]["code"] == "MEMORY_CURATOR_INCOMPLETE"`. **Fixed**: Reverted to using `error_response()` and embedded `domain_result` in the error `details` dict instead, preserving backward compatibility.

### Advisory

1. **Frontend component migration not yet done** — `RunDetail.tsx`, `Dashboard.tsx`, `WorkflowTimeline.tsx`, `MemoryUpdatesModule.tsx`, and `GenesisModule.tsx` still use hardcoded status logic. The new `statusSemantics.ts` helpers are available for incremental adoption but per spec ("不做大规模 UI 改版"), full migration is deferred.

2. **CSS custom properties need definition** — `statusSemantics.ts` references `--color-success`, `--color-warning`, `--color-error`, `--color-info` CSS custom properties. These need to be defined in `index.css` or a theme file for dark mode support. Currently they fall back to hardcoded hex values.

3. **Additional endpoints not yet integrated** — Memory apply, workflow timeline, chapter run, and recovery endpoints don't yet include `domain_result`. These are P2/P3 items for incremental adoption.

## Verification

- 35 backend tests pass (test_v6610_api_contract_semantics.py)
- 34 frontend tests pass (statusSemantics.test.ts)
- 2471 backend tests pass (full suite)
- Frontend typecheck/lint/build pass
- `git diff --check` clean

## Decision

**PASS** — Ready for commit.
