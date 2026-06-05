-- v6.9.0: Creative contracts, chapter briefs, creative ledgers, editor lens reports
-- Migration 036

-- 项目创作合同
CREATE TABLE IF NOT EXISTS project_creative_contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    contract_type TEXT NOT NULL,  -- 'launch_profile', 'genre_contract'
    contract_data TEXT NOT NULL,  -- JSON 结构化合同数据
    version INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project_id, contract_type)
);

-- 章节简报
CREATE TABLE IF NOT EXISTS chapter_briefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    brief_data TEXT NOT NULL,  -- JSON
    workflow_run_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project_id, chapter_number)
);

-- 创作台账快照
CREATE TABLE IF NOT EXISTS creative_ledger_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    ledger_type TEXT NOT NULL,  -- 'reader_promise', 'power_growth', 'character_arc', 'mystery_reveal', 'conflict', 'payoff', 'style_fatigue'
    ledger_data TEXT NOT NULL,  -- JSON
    patch_from_previous TEXT,   -- JSON 增量 patch
    workflow_run_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project_id, chapter_number, ledger_type, workflow_run_id)
);

-- 编辑视角报告
CREATE TABLE IF NOT EXISTS editor_lens_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    lens_type TEXT NOT NULL,  -- 'type', 'commercial', 'pacing', 'character', 'mystery', 'style', 'continuity'
    report_data TEXT NOT NULL,  -- JSON
    workflow_run_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project_id, chapter_number, lens_type, workflow_run_id)
);
