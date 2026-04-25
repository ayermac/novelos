-- Migration 008: v3.2 Batch Review & Revision
-- Adds tables for batch revision runs, revision items, and chapter review notes

-- Batch revision runs table
CREATE TABLE IF NOT EXISTS batch_revision_runs (
    id TEXT PRIMARY KEY,
    source_run_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    status TEXT NOT NULL,  -- pending, running, completed, blocked, failed
    decision_session_id TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    affected_chapters_json TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (source_run_id) REFERENCES production_runs(id),
    FOREIGN KEY (decision_session_id) REFERENCES human_review_sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_batch_revision_runs_source
    ON batch_revision_runs(source_run_id);
CREATE INDEX IF NOT EXISTS idx_batch_revision_runs_project
    ON batch_revision_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_batch_revision_runs_status
    ON batch_revision_runs(status);

-- Batch revision items table
CREATE TABLE IF NOT EXISTS batch_revision_items (
    id TEXT PRIMARY KEY,
    revision_run_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    action TEXT NOT NULL,  -- rerun_chapter, resume_to_status, rerun_tail
    target_status TEXT,  -- for resume_to_status
    notes TEXT,
    status TEXT NOT NULL,  -- pending, running, completed, failed, skipped
    workflow_run_id TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (revision_run_id) REFERENCES batch_revision_runs(id),
    FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_batch_revision_items_run
    ON batch_revision_items(revision_run_id);
CREATE INDEX IF NOT EXISTS idx_batch_revision_items_chapter
    ON batch_revision_items(revision_run_id, chapter_number);
CREATE INDEX IF NOT EXISTS idx_batch_revision_items_status
    ON batch_revision_items(status);

-- Chapter review notes table
CREATE TABLE IF NOT EXISTS chapter_review_notes (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    source_run_id TEXT NOT NULL,
    revision_run_id TEXT NOT NULL,
    notes TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (source_run_id) REFERENCES production_runs(id),
    FOREIGN KEY (revision_run_id) REFERENCES batch_revision_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_chapter_review_notes_project_chapter
    ON chapter_review_notes(project_id, chapter_number);
CREATE INDEX IF NOT EXISTS idx_chapter_review_notes_source_run
    ON chapter_review_notes(source_run_id);
CREATE INDEX IF NOT EXISTS idx_chapter_review_notes_revision_run
    ON chapter_review_notes(revision_run_id);
