-- 数据库升级脚本：统一时区处理
-- 执行：sqlite3 shared/data/novel_factory.db < shared/data/upgrade_timezone.sql
--
-- 问题：部分表使用 CURRENT_TIMESTAMP（UTC），部分使用 datetime('now','+8 hours')（北京时间）
-- 解决：统一使用北京时间（东八区）

-- 备份说明：执行前请先备份数据库
-- cp shared/data/novel_factory.db shared/data/novel_factory.db.bak

-- ============================================================
-- 修复：将 CURRENT_TIMESTAMP 改为 datetime('now','+8 hours')
-- 注意：SQLite 不支持 ALTER TABLE 修改 DEFAULT，需要重建表
-- ============================================================

-- 由于 SQLite 不支持直接修改列默认值，
-- 我们在 Python 代码中确保插入时使用正确的时区即可。
-- 这里的脚本主要用于记录时区规范。

-- 时区规范：
-- 1. 数据库默认值：使用 datetime('now', '+8 hours')
-- 2. Python 插入时：使用 datetime.now() 时确保系统时区为东八区，
--    或者在 SQL 中使用 datetime('now', '+8 hours')

-- 建议的 Python 代码统一写法：
-- 方式一：在 SQL 中使用 SQLite 函数
--   conn.execute("INSERT INTO table (..., created_at) VALUES (..., datetime('now', '+8 hours'))")
--
-- 方式二：使用 Python datetime（需要确保系统时区正确）
--   from datetime import datetime
--   conn.execute("INSERT INTO table (..., created_at) VALUES (..., ?)", (..., datetime.now().isoformat()))

-- 当前代码已统一使用方式一（SQL 中指定时区）
-- 以下是需要在代码中修复的地方：

-- db_common.py 中的时区使用情况：
-- ✅ 已使用 +8 hours 的地方：
--    - published_at
--    - chapter_plots.created_at
--    - outlines.created_at/updated_at
--    - task_status.started_at/completed_at
--    - chapter_state.created_at
--    - anti_patterns.last_seen
--    - agent_messages.processed_at
--
-- ⚠️ 使用 Python datetime.now() 的地方（需要检查）：
--    - feedback_system.py 第 137 行
--    - db_common.py 第 892 行（outlines updated_at）
--    - db_common.py 第 2059 行（anti_patterns updated_at）
--
-- 建议修改：将这些 Python datetime.now() 改为 SQL datetime('now','+8 hours')

-- 查询当前时间验证时区
SELECT 'SQLite 当前时间（UTC）' as description, datetime('now') as time
UNION ALL
SELECT 'SQLite 当前时间（+8小时）', datetime('now', '+8 hours')
UNION ALL
SELECT '系统当前时间', datetime('now', 'localtime');
