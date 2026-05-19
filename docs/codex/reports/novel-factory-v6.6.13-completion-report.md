# v6.6.13 Frontend Contract Adoption Closure — Completion Report

## Summary

Closed all remaining frontend mutation-handler gaps where `res.ok` was used as a proxy
for business success. No backend changes. No API additions. No UI architectural changes.

## Changes Delivered

### statusSemantics.ts
- Added `isActionable(result: OperationResult): boolean`.

### statusSemantics.test.ts
- 15 new tests across 3 new suites: `isActionable` (6), `badge edge cases` (6),
  `normalizeOperationResult: domain_result priority` (3).
- Total suite: 75 tests, all passing.

### MemoryUpdatesModule.tsx
- `handleApply`: added `normalizeOperationResult` + `isBusinessSuccess` check.
- `partial_success`/`fallback`/`degraded` responses show `type: 'error'` message.
- Legacy responses (no domain_result → `pending`) fall back to original success message.

### ReviewModule.tsx
- `handlePublish`: normalizes domain_result; shows error banner when domain_status is
  not pure `"success"` and not `"pending"` (legacy guard).

### ContextSidebar.tsx
- `handlePublish`: normalizes domain_result; shows warning dialog when domain_status is
  not pure `"success"` and not `"pending"` (legacy guard).

### ProjectOverviewModule.tsx
- Added `deriveAutoRunSeverity(result, steps)` helper.
- `handleRunAuto`: forward-compat domain_result check (no-op until backend ships it).
- Status bar: completed sessions with step-level warnings show ⚠ + "已完成（含警告）"
  instead of ✓ + "已完成".
- Session history `s.status === 'completed'` display intentionally unchanged.

## Verification

| Check | Result |
|-------|--------|
| `npm run typecheck` | 0 errors |
| `npm run lint` | 0 errors |
| `npm run build` | success |
| `npx vitest run` | 282/282 pass (18 test files) |
| Python tests | unaffected (no backend changes) |

## Unmigrated / Out-of-scope

| Location | Status |
|----------|--------|
| Session history `s.status === 'completed'` in ProjectOverviewModule | Intentional — session lifecycle, not domain result |
| SSE stream step `result` field | String enum from SSE events, no domain_result shape |
| `handleIgnore` / `handleRetry` in MemoryUpdatesModule | Simple administrative actions, not domain-result-sensitive |
| Chapter reset in ReviewModule (`if (res.ok) load()`) | Data reload only, no user-visible success state |
