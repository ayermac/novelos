-- Migration 001: Add workflow-related tables for Novel Factory v1
-- Compatible with existing openclaw-agents schema

-- Scene beats table (Screenwriter output)
CREATE TABLE IF NOT EXISTS scene_beats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    scene_goal TEXT NOT NULL,
    location TEXT,
    characters TEXT DEFAULT '[]',
    conflict TEXT,
    turn TEXT,
    revealed_info TEXT,
    plot_refs TEXT DEFAULT '[]',
    hook TEXT,
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    updated_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_scene_beats_project_chapter
    ON scene_beats(project_id, chapter_number);

-- Polish reports table (Polisher output)
CREATE TABLE IF NOT EXISTS polish_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    source_version INTEGER,
    target_version INTEGER,
    style_changes TEXT DEFAULT '[]',
    rhythm_changes TEXT DEFAULT '[]',
    dialogue_changes TEXT DEFAULT '[]',
    ai_trace_fixes TEXT DEFAULT '[]',
    fact_change_risk TEXT DEFAULT 'none',
    summary TEXT,
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_polish_reports_project_chapter
    ON polish_reports(project_id, chapter_number);

-- Workflow runs table (LangGraph execution tracking)
CREATE TABLE IF NOT EXISTS workflow_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    chapter_number INTEGER,
    graph_name TEXT NOT NULL DEFAULT 'chapter_production',
    status TEXT DEFAULT 'running',
    current_node TEXT,
    checkpoint_ref TEXT,
    started_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    completed_at DATETIME,
    error_message TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_project
    ON workflow_runs(project_id, status);

-- Agent artifacts table (unified product references)
CREATE TABLE IF NOT EXISTS agent_artifacts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    chapter_number INTEGER,
    agent_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    storage_uri TEXT,
    content_json TEXT,
    content_hash TEXT,
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_agent_artifacts_project_chapter
    ON agent_artifacts(project_id, chapter_number);
