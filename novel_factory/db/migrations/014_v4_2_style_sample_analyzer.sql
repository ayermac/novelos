-- v4.2: Style Sample Analyzer tables
-- Idempotent: safe to run multiple times.

-- style_samples: stores imported text samples with extracted metrics.
-- Full source text is NEVER stored; only preview (<=500 chars), hash, and metrics.
CREATE TABLE IF NOT EXISTS style_samples (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    content_preview TEXT,
    metrics_json TEXT DEFAULT '{}',
    analysis_json TEXT DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'imported',
    created_at TEXT NOT NULL,
    analyzed_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

-- Index for listing samples by project and status
CREATE INDEX IF NOT EXISTS idx_style_samples_project_status
    ON style_samples(project_id, status);

-- Unique constraint: same content hash cannot be imported twice for same project
-- among non-deleted samples. Deleted samples can be re-imported.
CREATE UNIQUE INDEX IF NOT EXISTS idx_style_samples_project_hash_active
    ON style_samples(project_id, content_hash) WHERE status != 'deleted';
