-- v5.8: Workflow node-level event persistence for observability and recovery.
-- Adds: workflow_node_events table for per-node started/completed/failed logs.

CREATE TABLE IF NOT EXISTS workflow_node_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    node_name TEXT NOT NULL,
    event_type TEXT NOT NULL,  -- started | progress | completed | failed | skipped | recovery
    status TEXT,  -- running | completed | failed | skipped
    message TEXT,  -- author-facing Chinese message
    input_summary TEXT,
    output_summary TEXT,
    artifact_refs_json TEXT,  -- JSON array of artifact references
    token_count INTEGER,
    latency_ms INTEGER,
    cost_estimate REAL,
    error_code TEXT,
    error_message TEXT,
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    metadata_json TEXT,
    FOREIGN KEY (run_id) REFERENCES workflow_runs(id),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_workflow_node_events_run
    ON workflow_node_events(run_id, created_at);

CREATE INDEX IF NOT EXISTS idx_workflow_node_events_project_chapter
    ON workflow_node_events(project_id, chapter_number, created_at);
