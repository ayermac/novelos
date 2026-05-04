-- v5.3.6 Workflow Trace Isolation
-- Adds workflow_run_id to task_status for per-run error isolation.

ALTER TABLE task_status ADD COLUMN workflow_run_id TEXT;

CREATE INDEX IF NOT EXISTS idx_task_status_run ON task_status(workflow_run_id);
