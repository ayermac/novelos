-- v5.3.x: Add workflow_run_id to agent_artifacts for run-level isolation

-- Add workflow_run_id column (nullable for backward compatibility with legacy data)
ALTER TABLE agent_artifacts ADD COLUMN workflow_run_id TEXT;

-- Drop old idempotency index that did not include run_id
-- (same content across different runs should be allowed as separate artifacts)
DROP INDEX IF EXISTS idx_agent_artifacts_idempotency;

-- New idempotency index including workflow_run_id
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_artifacts_idempotency
    ON agent_artifacts(project_id, chapter_number, agent_id, artifact_type, content_hash, workflow_run_id);

-- Index for run-level artifact queries
CREATE INDEX IF NOT EXISTS idx_agent_artifacts_run
    ON agent_artifacts(workflow_run_id);
