-- v6.1: Workflow execution events for agent-level observability.
-- Adds: workflow_execution_events table for fine-grained agent process evidence.

CREATE TABLE IF NOT EXISTS workflow_execution_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    node_name TEXT NOT NULL,
    agent_id TEXT,
    event_type TEXT NOT NULL,
    status TEXT DEFAULT 'info',
    message TEXT,
    payload_json TEXT,
    artifact_refs_json TEXT,
    token_count INTEGER,
    latency_ms INTEGER,
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (run_id) REFERENCES workflow_runs(id),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_exec_events_run_created
    ON workflow_execution_events(run_id, created_at);

CREATE INDEX IF NOT EXISTS idx_exec_events_project_chapter_created
    ON workflow_execution_events(project_id, chapter_number, created_at);

CREATE INDEX IF NOT EXISTS idx_exec_events_node_name
    ON workflow_execution_events(node_name);

CREATE INDEX IF NOT EXISTS idx_exec_events_event_type
    ON workflow_execution_events(event_type);
