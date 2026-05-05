-- v5.4.13 Project-specific Skill Overrides
-- Stores per-project skill override documents without mutating global skills.yaml.

CREATE TABLE IF NOT EXISTS project_skill_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT UNIQUE NOT NULL,
    overrides_json TEXT NOT NULL DEFAULT '{}',
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    updated_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_project_skill_overrides_project
    ON project_skill_overrides(project_id);
