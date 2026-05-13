# v5.5.1 Stuck Run Detection Spec

## Scope

Run Detail recovery now detects workflow runs that remain `running` beyond the configured task timeout.
The feature is a production safety net for interrupted API processes, dropped SSE streams, or stale LangGraph executions that never reached a terminal state.

## Backend

- `GET /api/runs/{run_id}/recovery`
  - Returns `timeout_minutes`, `elapsed_minutes`, `stuck`, `stuck_reason`, and run-scoped `running_tasks`.
  - Uses `settings.workflow.task_timeout_minutes` as the detection threshold.
  - Only evaluates `workflow_runs.status == "running"`.
  - Only considers `task_status` rows matching the same `workflow_run_id`, so stale legacy task rows cannot mark a new run as stuck.
- `POST /api/runs/{run_id}/recovery/mark-stuck`
  - Requires `{ "confirm": true }`.
  - Rejects non-stuck runs with `RUN_NOT_STUCK`.
  - Rejects terminal chapters such as `reviewed` and `published`.
  - Converts the workflow run to `blocked` and writes a clear stuck-run error message.
  - Closes matching run-scoped `running` task rows as `failed` with the same stuck-run message.
  - Moves the chapter to `blocking` so the existing recovery reset path can be used.
  - Inserts a run-scoped `task_status` audit row with `task_type='recover'`, `agent_id='system'`, and `workflow_run_id`.

## Frontend

- `RunDetail.tsx` extends the **运行恢复** card with:
  - Running elapsed time.
  - A warning state for suspected stuck runs.
  - A list of current run-scoped running tasks and their elapsed time.
  - A guarded **标记为阻塞** action.
- After marking a run as blocked, Run Detail refreshes both recovery state and the main run timeline.

## Safety Rules

- No content, artifacts, reviews, or checkpoints are deleted by mark-stuck.
- Mark-stuck is separate from reset; it only makes a stuck run explicit and recoverable.
- Stuck detection is run-scoped and does not reuse legacy task rows from other executions.
- Terminal chapter states cannot be moved to blocking by this endpoint.

## Verification

- `tests/test_v55_run_recovery.py`
  - Detects stale running runs.
  - Rejects recent running runs.
  - Ensures legacy running task rows do not contaminate current runs.
  - Converts stale runs to blocked and chapters to blocking.
  - Writes run-scoped recovery audit rows.
  - Confirms Run Detail contains the mark-stuck UI wiring.
