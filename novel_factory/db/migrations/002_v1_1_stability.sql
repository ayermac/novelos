-- Migration 002: v1.1 stability additions
-- - content_hash on chapter_versions for idempotency
-- - idempotency unique index on agent_artifacts

-- Add content_hash column to chapter_versions
ALTER TABLE chapter_versions ADD COLUMN content_hash TEXT;

-- Index for idempotency lookup on chapter_versions
CREATE INDEX IF NOT EXISTS idx_chapter_versions_hash
    ON chapter_versions(project_id, chapter, created_by, content_hash);

-- Idempotency unique index on agent_artifacts
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_artifacts_idempotency
    ON agent_artifacts(project_id, chapter_number, agent_id, artifact_type, content_hash);
