-- 数据库升级脚本：添加缺失的高级功能表
-- 执行方式：sqlite3 shared/data/novel_factory.db < shared/data/upgrade_db.sql
-- 日期：2026-04-05

-- 首先删除旧的 chapter_versions 视图（如果存在）
DROP VIEW IF EXISTS chapter_versions;

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

-- Agent 消息表（异步反馈通道）
CREATE TABLE IF NOT EXISTS agent_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_agent TEXT NOT NULL,
    to_agent TEXT NOT NULL,
    type TEXT NOT NULL,
    priority TEXT DEFAULT 'normal',
    content TEXT NOT NULL,
    chapter_number INTEGER,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    result TEXT
);

-- 问题模式学习表
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

-- 最佳实践表
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

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_chapter_versions ON chapter_versions(project_id, chapter);
CREATE INDEX IF NOT EXISTS idx_state_history ON state_history(project_id, chapter);
CREATE INDEX IF NOT EXISTS idx_agent_messages_status ON agent_messages(status, priority);
CREATE INDEX IF NOT EXISTS idx_agent_messages_to ON agent_messages(to_agent, status);
CREATE INDEX IF NOT EXISTS idx_learned_patterns ON learned_patterns(category, frequency);
CREATE INDEX IF NOT EXISTS idx_learned_patterns_project ON learned_patterns(project_id, category);
CREATE INDEX IF NOT EXISTS idx_best_practices ON best_practices(project_id, category);

-- 验证升级
SELECT '升级完成。当前表：' as message;
SELECT type, name FROM sqlite_master WHERE type='table' ORDER BY name;
