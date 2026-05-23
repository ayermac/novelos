-- v6.6.19: Per-chapter MemoryCurator extraction locks

CREATE TABLE IF NOT EXISTS memory_curator_locks (
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    run_id TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    locked_at TEXT NOT NULL DEFAULT (datetime('now', '+8 hours')),
    released_at TEXT,
    PRIMARY KEY (project_id, chapter_number),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_memory_curator_locks_status
    ON memory_curator_locks(status);
