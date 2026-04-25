-- v2.1 QualityHub and Skill Plugin Migration
-- Adds tables for quality_reports and skill_runs

-- Quality reports table (QualityHub)
CREATE TABLE IF NOT EXISTS quality_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    stage TEXT NOT NULL,  -- draft, polished, final
    overall_score REAL NOT NULL DEFAULT 0.0,
    pass INTEGER NOT NULL DEFAULT 0,  -- 0=false, 1=true
    revision_target TEXT,  -- author, polisher, editor, or NULL
    blocking_issues_json TEXT NOT NULL DEFAULT '[]',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    skill_results_json TEXT NOT NULL DEFAULT '[]',
    quality_dimensions_json TEXT NOT NULL DEFAULT '{}',
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_quality_reports_project ON quality_reports(project_id);
CREATE INDEX IF NOT EXISTS idx_quality_reports_chapter ON quality_reports(project_id, chapter_number);
CREATE INDEX IF NOT EXISTS idx_quality_reports_stage ON quality_reports(stage);
CREATE INDEX IF NOT EXISTS idx_quality_reports_created ON quality_reports(created_at);

-- Skill runs table (Skill execution tracking)
CREATE TABLE IF NOT EXISTS skill_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_number INTEGER,
    skill_id TEXT NOT NULL,
    skill_type TEXT NOT NULL,  -- transform, validator, context, report
    agent_id TEXT,  -- which agent triggered this skill
    stage TEXT,  -- before_llm, after_llm, before_save, etc.
    ok INTEGER NOT NULL DEFAULT 0,  -- 0=false, 1=true
    error TEXT,
    input_json TEXT NOT NULL DEFAULT '{}',
    output_json TEXT NOT NULL DEFAULT '{}',
    duration_ms INTEGER,
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE INDEX IF NOT EXISTS idx_skill_runs_project ON skill_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_skill_runs_skill ON skill_runs(skill_id);
CREATE INDEX IF NOT EXISTS idx_skill_runs_agent ON skill_runs(agent_id);
CREATE INDEX IF NOT EXISTS idx_skill_runs_created ON skill_runs(created_at);
