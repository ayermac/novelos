-- Phase 1: 扩展 best_practices 表结构
-- 执行前请备份数据库

-- 新增字段
ALTER TABLE best_practices ADD COLUMN tags TEXT;
ALTER TABLE best_practices ADD COLUMN source_score INTEGER;
ALTER TABLE best_practices ADD COLUMN chapter_numbers TEXT;

-- 更新索引
CREATE INDEX IF NOT EXISTS idx_best_practices_score ON best_practices(avg_score DESC);
CREATE INDEX IF NOT EXISTS idx_best_practices_category ON best_practices(category);
