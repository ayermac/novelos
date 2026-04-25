-- 数据库升级脚本：为 agent_messages 添加 project_id
-- 执行方式：sqlite3 shared/data/novel_factory.db < shared/data/upgrade_agent_messages.sql
-- 日期：2026-04-06

-- 检查 agent_messages 是否已有 project_id 列
-- SQLite 不支持 IF NOT EXISTS for ALTER TABLE ADD COLUMN，需要手动检查

-- 添加 project_id 列到 agent_messages 表
-- 注意：如果列已存在会报错，但可以忽略
ALTER TABLE agent_messages ADD COLUMN project_id TEXT REFERENCES projects(project_id);

-- 删除旧索引（如果存在）
DROP INDEX IF EXISTS idx_agent_messages_project;

-- 创建新索引
CREATE INDEX IF NOT EXISTS idx_agent_messages_project ON agent_messages(project_id, status);

-- 验证
SELECT '升级完成。agent_messages 表结构：' as message;
PRAGMA table_info(agent_messages);
