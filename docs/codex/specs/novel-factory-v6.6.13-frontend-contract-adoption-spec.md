# v6.6.13 Frontend Contract Adoption Closure — Spec

## Goal

Systematically adopt `domain_result` semantics across all frontend mutation paths
so that degraded, partial, and fallback operation results are never displayed as green success.

## Background

v6.6.10–v6.6.12 introduced unified `OperationResult` / `domain_result` contracts on
the backend. `RunDetail.tsx`, `WorkflowTimeline.tsx`, and `ChapterEditorSurface.tsx`
already consume these semantics. This version closes the remaining mutation-handler gaps.

## Rules

- HTTP `ok=true` is NOT business success.
  Business success requires `domain_result.domain_status === "success"`.
- `partial_success`, `fallback`, `degraded` MUST display warning (⚠), never success (✓).
- `blocked`, `failed` MUST display error.
- `pending` displays info.
- `ignored` displays info/neutral.
- When `next_action` or `action_label` is present, surface the action hint to the user.
- Legacy responses without `domain_result` are handled via `deriveOperationResult()` —
  no breaking changes. The `domain_status !== 'pending'` guard prevents spurious
  warnings from endpoints that have not yet adopted `domain_result`.

## statusSemantics.ts additions

- `isActionable(result: OperationResult): boolean` — true when
  `next_action || action_label` is present. Used to conditionally render
  action hint buttons or labels.

## Components patched

| Component | Handler | Change |
|-----------|---------|--------|
| `MemoryUpdatesModule.tsx` | `handleApply` | Checks `isBusinessSuccess(domainResult)` before showing success message; non-success domain shows warning; legacy (`pending`) falls back to original success message |
| `ReviewModule.tsx` | `handlePublish` | Checks domain_result; shows error banner when domain_status is not pure success and not pending |
| `ContextSidebar.tsx` | `handlePublish` | Checks domain_result; shows warning dialog when domain_status is not pure success and not pending |
| `ProjectOverviewModule.tsx` | `handleRunAuto` | Forward-compat domain_result check — activates when backend adds `domain_result` field to run-auto response |
| `ProjectOverviewModule.tsx` | Status bar | `deriveAutoRunSeverity()` helper — shows ⚠ + "已完成（含警告）" when completed session has step-level warnings |

## Components NOT changed (already complete)

- `RunDetail.tsx` — fully wired since v6.6.10
- `WorkflowTimeline.tsx` — node-level semantics wired since v6.6.11
- `ChapterEditorSurface.tsx` — local-revision wired since v6.6.11

## Session history intentionally NOT changed

`ProjectOverviewModule.tsx` session history (`s.status === 'completed'`) reflects
session lifecycle status, not domain operation result. Out of scope for v6.6.13.

## Test coverage added

- `isActionable`: 6 tests
- Badge edge cases (`ignored`, `needs_human`, `pending`, `partial_success`, `fallback`, `degraded`): 6 tests
- `domain_result` priority over legacy fields: 3 tests
- Total new: 15 tests; total suite: 75 tests
