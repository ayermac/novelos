-- Base schema for Novel Factory
-- Originally from openclaw-agents/shared/data/init_db.sql
-- Bundled here for packaged installs (novelos init-db must work without external paths)

-- 项目表
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    genre TEXT,
    description TEXT,
    status TEXT DEFAULT 'active',
    current_chapter INTEGER DEFAULT 0,
    total_chapters_planned INTEGER DEFAULT 500,
    target_words INTEGER DEFAULT 1500000,
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    updated_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    is_current INTEGER DEFAULT 0
);

-- 世界观设定表
CREATE TABLE IF NOT EXISTS world_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

-- 角色表
CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    alias TEXT,
    role TEXT,
    description TEXT,
    first_appearance INTEGER,
    status TEXT DEFAULT 'active',
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

-- 势力表
CREATE TABLE IF NOT EXISTS factions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT,
    description TEXT,
    relationship_with_protagonist TEXT,
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

-- 章节表
CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    word_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'planned',
    instruction_id INTEGER,
    draft_saved_at DATETIME,
    published_at DATETIME,
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    updated_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (instruction_id) REFERENCES instructions(id),
    UNIQUE(project_id, chapter_number)
);

-- 指令表
CREATE TABLE IF NOT EXISTS instructions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    objective TEXT,
    key_events TEXT,
    plots_to_resolve TEXT DEFAULT '[]',
    plots_to_plant TEXT DEFAULT '[]',
    emotion_tone TEXT,
    ending_hook TEXT,
    word_target INTEGER DEFAULT 2500,
    status TEXT DEFAULT 'pending',
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    updated_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    UNIQUE(project_id, chapter_number)
);

-- 伏笔表
CREATE TABLE IF NOT EXISTS plot_holes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    code TEXT NOT NULL,
    type TEXT,
    title TEXT NOT NULL,
    description TEXT,
    planted_chapter INTEGER,
    resolved_chapter INTEGER,
    planned_resolve_chapter INTEGER,
    status TEXT DEFAULT 'planted',
    notes TEXT,
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    updated_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    UNIQUE(project_id, code)
);

-- 章节-伏笔关联表
CREATE TABLE IF NOT EXISTS chapter_plots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_id INTEGER NOT NULL,
    plot_id INTEGER NOT NULL,
    action TEXT,
    notes TEXT,
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (chapter_id) REFERENCES chapters(id),
    FOREIGN KEY (plot_id) REFERENCES plot_holes(id)
);

-- 质检报告表
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_id INTEGER NOT NULL UNIQUE,
    pass INTEGER DEFAULT 0,
    score INTEGER DEFAULT 0,
    setting_score INTEGER,
    logic_score INTEGER,
    poison_score INTEGER,
    text_score INTEGER,
    pacing_score INTEGER,
    issues TEXT DEFAULT '[]',
    suggestions TEXT DEFAULT '[]',
    summary TEXT,
    reviewed_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (chapter_id) REFERENCES chapters(id)
);

-- 任务状态表
CREATE TABLE IF NOT EXISTS task_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    chapter_number INTEGER,
    agent_id TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    started_at DATETIME,
    completed_at DATETIME,
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

-- 市场报告表
CREATE TABLE IF NOT EXISTS market_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date TEXT NOT NULL,
    summary TEXT,
    hot_genres TEXT,
    trending_tags TEXT,
    opportunities TEXT,
    risks TEXT,
    actionable_advice TEXT,
    created_at DATETIME DEFAULT (datetime('now', '+8 hours'))
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_chapters_project_number ON chapters(project_id, chapter_number);
CREATE INDEX IF NOT EXISTS idx_instructions_project_number ON instructions(project_id, chapter_number);
CREATE INDEX IF NOT EXISTS idx_plot_holes_project_code ON plot_holes(project_id, code);
CREATE INDEX IF NOT EXISTS idx_task_status_project ON task_status(project_id, status);
CREATE INDEX IF NOT EXISTS idx_reviews_project_chapter ON reviews(project_id, chapter_id);

-- 章节状态表（存储每章结束时的数值状态，防止长篇漂移）
CREATE TABLE IF NOT EXISTS chapter_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    state_data TEXT,
    summary TEXT,
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    UNIQUE(project_id, chapter_number)
);

-- 大纲表（支持多层大纲结构）
CREATE TABLE IF NOT EXISTS outlines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    level TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    chapters_range TEXT,
    created_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    updated_at DATETIME DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

-- 创建额外索引
CREATE INDEX IF NOT EXISTS idx_chapter_state_project ON chapter_state(project_id, chapter_number);
CREATE INDEX IF NOT EXISTS idx_outlines_project ON outlines(project_id, level, sequence);

-- ============================================================
-- 高级功能表（版本管理、反馈升级、学习模式）
-- ============================================================

-- 章节版本表（支持回退和历史追溯）
CREATE TABLE IF NOT EXISTS chapter_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    content TEXT,
    word_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT DEFAULT 'author',
    review_id INTEGER,
    notes TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (review_id) REFERENCES reviews(id),
    UNIQUE(project_id, chapter, version)
);

-- 状态卡历史表（追踪数值变化）
CREATE TABLE IF NOT EXISTS state_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    changed_fields TEXT,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

-- Agent 消息表（异步反馈通道，非实时通知）
CREATE TABLE IF NOT EXISTS agent_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT,
    from_agent TEXT NOT NULL,
    to_agent TEXT NOT NULL,
    type TEXT NOT NULL,
    priority TEXT DEFAULT 'normal',
    content TEXT NOT NULL,
    chapter_number INTEGER,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    result TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

-- 问题模式学习表（质检发现的问题自动记录）
CREATE TABLE IF NOT EXISTS learned_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT,
    chapter_number INTEGER,
    category TEXT NOT NULL,
    pattern TEXT NOT NULL,
    frequency INTEGER DEFAULT 1,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    enabled INTEGER DEFAULT 1
);

-- 最佳实践表（高分章节提取的经验）
CREATE TABLE IF NOT EXISTS best_practices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT,
    source_chapters TEXT,
    avg_score REAL,
    category TEXT NOT NULL,
    practice TEXT NOT NULL,
    evidence TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建高级功能索引
CREATE INDEX IF NOT EXISTS idx_chapter_versions ON chapter_versions(project_id, chapter);
CREATE INDEX IF NOT EXISTS idx_state_history ON state_history(project_id, chapter);
CREATE INDEX IF NOT EXISTS idx_agent_messages_project ON agent_messages(project_id, status);
CREATE INDEX IF NOT EXISTS idx_agent_messages_status ON agent_messages(status, priority);
CREATE INDEX IF NOT EXISTS idx_agent_messages_to ON agent_messages(to_agent, status);
CREATE INDEX IF NOT EXISTS idx_learned_patterns ON learned_patterns(category, frequency);
CREATE INDEX IF NOT EXISTS idx_learned_patterns_project ON learned_patterns(project_id, category);

-- ============================================================
-- 问题模式表（原 anti_patterns.json）
-- ============================================================

CREATE TABLE IF NOT EXISTS anti_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL CHECK(category IN ('ai_trace', 'logic', 'setting', 'poison', 'pacing')),
    code TEXT UNIQUE NOT NULL,
    pattern TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('critical', 'high', 'medium', 'low')),
    alternatives TEXT,
    check_rules TEXT,
    examples TEXT,
    enabled INTEGER DEFAULT 1,
    frequency INTEGER DEFAULT 0,
    last_seen TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 上下文规则表
CREATE TABLE IF NOT EXISTS context_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('critical', 'high', 'medium')),
    enabled INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 问题模式索引
CREATE INDEX IF NOT EXISTS idx_anti_patterns_category ON anti_patterns(category);
CREATE INDEX IF NOT EXISTS idx_anti_patterns_severity ON anti_patterns(severity);
CREATE INDEX IF NOT EXISTS idx_anti_patterns_enabled ON anti_patterns(enabled);
CREATE INDEX IF NOT EXISTS idx_anti_patterns_code ON anti_patterns(code);
CREATE INDEX IF NOT EXISTS idx_context_rules_category ON context_rules(category);
