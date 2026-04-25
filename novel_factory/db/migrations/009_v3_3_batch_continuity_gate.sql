-- v3.3 Batch Continuity Gate
-- Stores batch-level continuity gate results for production runs.

CREATE TABLE IF NOT EXISTS batch_continuity_gates (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    from_chapter INTEGER NOT NULL,
    to_chapter INTEGER NOT NULL,
    continuity_report_id TEXT,
    status TEXT NOT NULL,
    issue_count INTEGER DEFAULT 0,
    warning_count INTEGER DEFAULT 0,
    blocking_issues_json TEXT DEFAULT '[]',
    summary TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES production_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_batch_continuity_gates_run
    ON batch_continuity_gates(run_id, created_at);

CREATE INDEX IF NOT EXISTS idx_batch_continuity_gates_project
    ON batch_continuity_gates(project_id, created_at);

CREATE INDEX IF NOT EXISTS idx_batch_continuity_gates_status
    ON batch_continuity_gates(status);
