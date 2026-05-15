-- v6.0: Agent Memory and Decision Trace tables

CREATE TABLE IF NOT EXISTS agent_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    key TEXT NOT NULL,
    value_json TEXT NOT NULL DEFAULT '{}',
    confidence REAL DEFAULT 1.0,
    source_run_id TEXT,
    source_chapter_number INTEGER,
    enabled INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    updated_at DATETIME DEFAULT (datetime('now', '+8 hours'))
);

CREATE INDEX IF NOT EXISTS idx_agent_memories_project_agent
ON agent_memories(project_id, agent_id);

CREATE INDEX IF NOT EXISTS idx_agent_memories_type
ON agent_memories(project_id, agent_id, memory_type);

CREATE TABLE IF NOT EXISTS agent_decision_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    agent_id TEXT NOT NULL,
    stage TEXT,
    role_profile_id TEXT,
    input_summary TEXT,
    capability_packs_json TEXT DEFAULT '[]',
    tool_calls_json TEXT DEFAULT '[]',
    skill_results_json TEXT DEFAULT '[]',
    self_check_json TEXT DEFAULT '{}',
    autonomy_decision_json TEXT DEFAULT '{}',
    repair_attempts_json TEXT DEFAULT '[]',
    contract_validation_json TEXT DEFAULT '{}',
    token_count INTEGER DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT (datetime('now', '+8 hours'))
);

CREATE INDEX IF NOT EXISTS idx_agent_traces_run
ON agent_decision_traces(run_id);

CREATE INDEX IF NOT EXISTS idx_agent_traces_project
ON agent_decision_traces(project_id, chapter_number);
