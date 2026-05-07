# v5.5.2 Run Health Dashboard Spec

## Scope

v5.5.2 promotes single-run recovery into an operator-facing run health dashboard.
It focuses on finding stale `running` workflow runs, seeing recent blocked/failed runs, and handling confirmed stuck runs in batches.

## Backend

- `GET /api/runs/health`
  - Optional `project_id` filter.
  - Optional `limit`, clamped to `1..200`.
  - Lists recent `running`, `blocked`, and `failed` workflow runs.
  - Computes stuck state using `settings.workflow.task_timeout_minutes`.
  - Includes run-scoped running task rows, elapsed minutes, current node, chapter status, and action availability.
  - Returns a summary with `total_running`, `healthy_running`, `stuck`, `blocked`, `failed`, and `actionable`.
- `POST /api/runs/health/mark-stuck`
  - Requires `{ "confirm": true, "run_ids": [...] }`.
  - Processes up to 50 runs per request.
  - Reuses the v5.5.1 mark-stuck implementation.
  - Returns per-run success/failure results so partial failures are explicit.

## Frontend

- Settings adds a dedicated **运行健康** section.
- `RunHealthPanel.tsx` shows:
  - Health metrics for stuck, healthy running, blocked, failed, and actionable runs.
  - A table of issue-bearing workflow runs.
  - Run-scoped task summaries.
  - Per-row links to Run Detail and project chapter workspace.
  - Checkbox selection for actionable stuck runs.
  - Batch **标记为阻塞** action with confirmation.

## Safety Rules

- The dashboard cannot mutate non-stuck or terminal runs.
- Batch processing is bounded to 50 run ids.
- Batch responses do not hide partial failures.
- Marking a run stuck still preserves content, artifacts, reviews, and checkpoints.

## Verification

- `tests/test_v552_run_health_dashboard.py`
  - Stuck running run detection in health API.
  - Project filtering.
  - Blocked/failed run visibility.
  - Batch mark-stuck success.
  - Batch partial failure reporting.
  - Confirmation requirement.
  - Settings Run Health UI wiring.
