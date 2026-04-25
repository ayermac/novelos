-- v3.4 Production Queue
-- Adds production_queue and production_queue_events tables for batch queue management.

CREATE TABLE IF NOT EXISTS production_queue (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    from_chapter INTEGER NOT NULL,
    to_chapter INTEGER NOT NULL,
    priority INTEGER DEFAULT 100,
    status TEXT NOT NULL DEFAULT 'pending',
    production_run_id TEXT,
    attempt_count INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    timeout_minutes INTEGER DEFAULT 120,
    last_error TEXT,
    locked_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_production_queue_status_priority
    ON production_queue(status, priority, created_at);

CREATE INDEX IF NOT EXISTS idx_production_queue_project
    ON production_queue(project_id, created_at);

CREATE TABLE IF NOT EXISTS production_queue_events (
    id TEXT PRIMARY KEY,
    queue_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    message TEXT,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (queue_id) REFERENCES production_queue(id)
);

CREATE INDEX IF NOT EXISTS idx_production_queue_events_queue
    ON production_queue_events(queue_id, created_at);
