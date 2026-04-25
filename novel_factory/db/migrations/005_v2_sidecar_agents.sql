-- v2 Sidecar Agents Migration
-- Adds tables for Scout, Secretary, ContinuityChecker, and Architect agents

-- Scout reports table (Scout Agent) - renamed from market_reports to avoid conflict with base schema
CREATE TABLE IF NOT EXISTS scout_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_number INTEGER,
    agent_id TEXT NOT NULL DEFAULT 'scout',
    report_type TEXT NOT NULL,
    status TEXT DEFAULT 'completed',
    content_json TEXT NOT NULL DEFAULT '{}',
    summary TEXT DEFAULT '',
    topic TEXT,
    keywords TEXT DEFAULT '[]',
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    updated_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_scout_reports_project ON scout_reports(project_id);
CREATE INDEX IF NOT EXISTS idx_scout_reports_created ON scout_reports(created_at);

-- Reports table (Secretary Agent)
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_number INTEGER,
    agent_id TEXT NOT NULL DEFAULT 'secretary',
    report_type TEXT NOT NULL,
    status TEXT DEFAULT 'completed',
    content_json TEXT NOT NULL DEFAULT '{}',
    summary TEXT DEFAULT '',
    report_date TEXT,
    export_format TEXT DEFAULT 'json',
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    updated_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_reports_project ON reports(project_id);
CREATE INDEX IF NOT EXISTS idx_reports_type ON reports(report_type);
CREATE INDEX IF NOT EXISTS idx_reports_date ON reports(report_date);

-- Continuity reports table (ContinuityChecker Agent)
CREATE TABLE IF NOT EXISTS continuity_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_number INTEGER,
    agent_id TEXT NOT NULL DEFAULT 'continuity_checker',
    report_type TEXT NOT NULL DEFAULT 'continuity_check',
    status TEXT DEFAULT 'completed',
    content_json TEXT NOT NULL DEFAULT '{}',
    summary TEXT DEFAULT '',
    from_chapter INTEGER NOT NULL,
    to_chapter INTEGER NOT NULL,
    issue_count INTEGER DEFAULT 0,
    warning_count INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    updated_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_continuity_reports_project ON continuity_reports(project_id);
CREATE INDEX IF NOT EXISTS idx_continuity_reports_chapters ON continuity_reports(from_chapter, to_chapter);

-- Architecture proposals table (Architect Agent)
CREATE TABLE IF NOT EXISTS architecture_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_number INTEGER,
    agent_id TEXT NOT NULL DEFAULT 'architect',
    proposal_type TEXT NOT NULL,
    scope TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    risk_level TEXT DEFAULT 'medium',
    affected_area TEXT DEFAULT '[]',
    recommendation TEXT NOT NULL,
    rationale TEXT,
    implementation_notes TEXT,
    status TEXT DEFAULT 'pending',
    content_json TEXT DEFAULT '{}',
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    updated_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_architecture_proposals_project ON architecture_proposals(project_id);
CREATE INDEX IF NOT EXISTS idx_architecture_proposals_status ON architecture_proposals(status);
CREATE INDEX IF NOT EXISTS idx_architecture_proposals_scope ON architecture_proposals(scope);
