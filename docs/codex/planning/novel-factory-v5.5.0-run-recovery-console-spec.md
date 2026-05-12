# v5.5.0 Run Recovery Console Spec

## Scope

Run Detail now exposes a recovery console for blocked or revision chapters.
It is designed for production recovery after word-count gates, retry-limit
blocks, stale checkpoints, or manual review failures.

## Backend

- `GET /api/runs/{run_id}/recovery`
  - Returns workflow status, chapter status, retry count, checkpoint presence,
    error message, and available recovery actions.
- `POST /api/runs/{run_id}/recovery/reset`
  - Requires `{ "confirm": true }`.
  - Only allows chapters in `blocking` or `revision`.
  - Moves the chapter back to `planned`.
  - Inserts a `task_status` audit row with `workflow_run_id`.
  - Clears the LangGraph checkpoint thread.
  - Preserves chapter content, artifacts, reviews, and run history.

## Frontend

- `RunDetail.tsx` includes a **运行恢复** card.
- Shows retry count, checkpoint state, and whether recovery is available.
- Provides a guarded action to reset the chapter to `planned`.
- Refreshes run detail after recovery.

## Safety Rules

- No destructive deletion of content or artifacts.
- No recovery without explicit confirmation.
- No status change unless current chapter status is `blocking` or `revision`.
- Reset audit is isolated to the originating `workflow_run_id`.

## Verification

- `tests/test_v55_run_recovery.py`
  - Recovery preview for blocked runs.
  - Reset clears retry count and checkpoint thread.
  - Reset writes run-scoped audit.
  - Invalid chapter states are rejected.
  - Run Detail source includes recovery console wiring.
