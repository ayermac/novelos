-- v3.6 Semi-Auto Serial Mode
-- Adds serial_plans and serial_plan_events tables for managing semi-automated serial production.

-- Serial plans table
CREATE TABLE IF NOT EXISTS serial_plans (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    start_chapter INTEGER NOT NULL,
    target_chapter INTEGER NOT NULL,
    batch_size INTEGER NOT NULL,
    current_chapter INTEGER NOT NULL,
    status TEXT NOT NULL,
    current_queue_id TEXT,
    current_production_run_id TEXT,
    total_planned_chapters INTEGER NOT NULL,
    completed_chapters INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

-- Serial plan events table
CREATE TABLE IF NOT EXISTS serial_plan_events (
    id TEXT PRIMARY KEY,
    serial_plan_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    message TEXT,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (serial_plan_id) REFERENCES serial_plans(id)
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_serial_plans_project
    ON serial_plans(project_id, created_at);

CREATE INDEX IF NOT EXISTS idx_serial_plans_status
    ON serial_plans(status, updated_at);

CREATE INDEX IF NOT EXISTS idx_serial_plan_events_plan
    ON serial_plan_events(serial_plan_id, created_at);
