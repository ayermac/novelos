-- v4.0 Style Bible MVP
-- Adds style_bibles table for project-level style specifications.

CREATE TABLE IF NOT EXISTS style_bibles (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    genre TEXT,
    target_platform TEXT,
    target_audience TEXT,
    bible_json TEXT NOT NULL DEFAULT '{}',
    version TEXT NOT NULL DEFAULT '1.0.0',
    created_at TEXT NOT NULL DEFAULT (datetime('now', '+8 hours')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    UNIQUE(project_id)
);

CREATE INDEX IF NOT EXISTS idx_style_bibles_project
    ON style_bibles(project_id);
