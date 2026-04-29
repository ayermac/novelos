-- v5.3.2 Project Genesis & Memory Loop
-- Adds genesis_runs, memory_update_batches, memory_update_items,
-- story_facts, and story_fact_events tables.

CREATE TABLE IF NOT EXISTS genesis_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    input_json TEXT NOT NULL DEFAULT '{}',
    draft_json TEXT DEFAULT '{}',
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', '+8 hours')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_genesis_runs_project
    ON genesis_runs(project_id);

CREATE INDEX IF NOT EXISTS idx_genesis_runs_status
    ON genesis_runs(status);

CREATE TABLE IF NOT EXISTS memory_update_batches (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    chapter_number INTEGER,
    run_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    summary TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', '+8 hours')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_memory_update_batches_project
    ON memory_update_batches(project_id);

CREATE INDEX IF NOT EXISTS idx_memory_update_batches_status
    ON memory_update_batches(status);

CREATE TABLE IF NOT EXISTS memory_update_items (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    target_table TEXT NOT NULL,
    target_id TEXT,
    operation TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT NOT NULL DEFAULT '{}',
    confidence REAL DEFAULT 0.8,
    evidence_text TEXT,
    rationale TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    applied_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (batch_id) REFERENCES memory_update_batches(id),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_memory_update_items_batch
    ON memory_update_items(batch_id);

CREATE INDEX IF NOT EXISTS idx_memory_update_items_project
    ON memory_update_items(project_id);

CREATE INDEX IF NOT EXISTS idx_memory_update_items_status
    ON memory_update_items(status);

CREATE TABLE IF NOT EXISTS story_facts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    fact_key TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    subject TEXT,
    attribute TEXT,
    value_json TEXT NOT NULL DEFAULT '{}',
    unit TEXT,
    scope TEXT DEFAULT 'global',
    status TEXT DEFAULT 'active',
    confidence REAL DEFAULT 1.0,
    source_chapter INTEGER,
    source_agent TEXT,
    last_changed_chapter INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now', '+8 hours')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_story_facts_project
    ON story_facts(project_id);

CREATE INDEX IF NOT EXISTS idx_story_facts_type
    ON story_facts(fact_type);

CREATE INDEX IF NOT EXISTS idx_story_facts_status
    ON story_facts(status);

CREATE INDEX IF NOT EXISTS idx_story_facts_key
    ON story_facts(project_id, fact_key);

CREATE TABLE IF NOT EXISTS story_fact_events (
    id TEXT PRIMARY KEY,
    fact_id TEXT,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    run_id TEXT,
    agent_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT,
    rationale TEXT,
    evidence_text TEXT,
    validation_status TEXT DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_story_fact_events_project
    ON story_fact_events(project_id);

CREATE INDEX IF NOT EXISTS idx_story_fact_events_fact
    ON story_fact_events(fact_id);

CREATE INDEX IF NOT EXISTS idx_story_fact_events_chapter
    ON story_fact_events(project_id, chapter_number);
