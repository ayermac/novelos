-- v5.5.8: Auto-Run Control Loop — session persistence for production runner

CREATE TABLE IF NOT EXISTS auto_run_sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    chapter_start INTEGER,
    chapter_end INTEGER,
    max_steps INTEGER DEFAULT 10,
    dry_run INTEGER DEFAULT 0,
    stop_on_review INTEGER DEFAULT 1,
    status TEXT DEFAULT 'running',
    stop_reason TEXT,
    current_step INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT (datetime('now','+8 hours')),
    updated_at DATETIME DEFAULT (datetime('now','+8 hours')),
    ended_at DATETIME
);

CREATE TABLE IF NOT EXISTS auto_run_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    action TEXT,
    label TEXT,
    target_chapter INTEGER,
    result TEXT,
    warnings TEXT,
    error TEXT,
    started_at DATETIME,
    completed_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_auto_run_sessions_project ON auto_run_sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_auto_run_steps_session ON auto_run_steps(session_id);
