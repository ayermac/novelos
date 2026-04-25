-- v3.0 Batch Production MVP
-- Migration: 007_v3_0_batch_production.sql
-- Purpose: Add tables for multi-chapter batch production

-- Production Runs: Track batch production runs
CREATE TABLE IF NOT EXISTS production_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    from_chapter INTEGER NOT NULL,
    to_chapter INTEGER NOT NULL,
    status TEXT NOT NULL,  -- pending, running, awaiting_review, approved, request_changes, rejected, blocked, failed
    total_chapters INTEGER NOT NULL,
    completed_chapters INTEGER DEFAULT 0,
    blocked_chapter INTEGER,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

-- Index for querying runs by project
CREATE INDEX IF NOT EXISTS idx_production_runs_project
ON production_runs(project_id, created_at);

-- Index for querying runs by status
CREATE INDEX IF NOT EXISTS idx_production_runs_status
ON production_runs(status, updated_at);

-- Production Run Items: Track individual chapter execution within a batch
CREATE TABLE IF NOT EXISTS production_run_items (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    workflow_run_id TEXT,
    status TEXT NOT NULL,  -- pending, running, completed, blocked, failed, skipped
    chapter_status TEXT,  -- Status of the chapter after execution
    quality_pass INTEGER,  -- 0 or 1
    error TEXT,
    requires_human INTEGER DEFAULT 0,  -- 0 or 1
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES production_runs(id)
);

-- Index for querying items by run
CREATE INDEX IF NOT EXISTS idx_production_run_items_run
ON production_run_items(run_id, chapter_number);

-- Index for querying items by project and chapter
CREATE INDEX IF NOT EXISTS idx_production_run_items_project_chapter
ON production_run_items(project_id, chapter_number);

-- Human Review Sessions: Track human review decisions for batches
CREATE TABLE IF NOT EXISTS human_review_sessions (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    decision TEXT NOT NULL,  -- approve, request_changes, reject
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES production_runs(id)
);

-- Index for querying review sessions by run
CREATE INDEX IF NOT EXISTS idx_human_review_sessions_run
ON human_review_sessions(run_id, created_at);
