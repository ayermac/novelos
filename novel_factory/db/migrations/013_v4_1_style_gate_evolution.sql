-- v4.1 Style Gate & Evolution
-- Adds style_bible_versions and style_evolution_proposals tables.

CREATE TABLE IF NOT EXISTS style_bible_versions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    style_bible_id TEXT NOT NULL,
    version TEXT NOT NULL,
    bible_json TEXT NOT NULL DEFAULT '{}',
    change_summary TEXT,
    created_by TEXT NOT NULL DEFAULT 'system',
    created_at TEXT NOT NULL DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (style_bible_id) REFERENCES style_bibles(id)
);

CREATE INDEX IF NOT EXISTS idx_style_bible_versions_project
    ON style_bible_versions(project_id);

CREATE INDEX IF NOT EXISTS idx_style_bible_versions_bible
    ON style_bible_versions(style_bible_id);

CREATE TABLE IF NOT EXISTS style_evolution_proposals (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    proposal_type TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'quality_reports',
    status TEXT NOT NULL DEFAULT 'pending',
    proposal_json TEXT NOT NULL DEFAULT '{}',
    rationale TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', '+8 hours')),
    decided_at TEXT,
    decision_notes TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_style_evolution_proposals_project
    ON style_evolution_proposals(project_id);

CREATE INDEX IF NOT EXISTS idx_style_evolution_proposals_status
    ON style_evolution_proposals(status);
