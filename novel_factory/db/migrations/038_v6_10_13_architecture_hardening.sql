-- v6.10.13: Architecture hardening — new tables for BudgetSentinel, DiagnosisSystem, and StyleStats

-- Budget records table
CREATE TABLE IF NOT EXISTS budget_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Diagnosis findings table
CREATE TABLE IF NOT EXISTS diagnosis_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    dimension TEXT NOT NULL,      -- flow / quality / planning / memory
    severity TEXT NOT NULL,       -- critical / warning / info
    confidence TEXT NOT NULL,     -- high / medium / low
    message TEXT NOT NULL,
    evidence TEXT,
    suggestion TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Style statistics table
CREATE TABLE IF NOT EXISTS style_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_count INTEGER NOT NULL,
    stats_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id)
);
