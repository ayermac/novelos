# 时区处理规范

## 问题发现

数据库中的时区处理不一致：
1. **大部分表**：使用 `DEFAULT (datetime('now', '+8 hours'))` - 东八区（北京时间）
2. **部分表**：使用 `DEFAULT CURRENT_TIMESTAMP` - UTC 时区

## 统一规范

**所有时间存储使用东八区（北京时间，UTC+8）**

### 数据库表默认值

```sql
-- ✅ 正确
created_at DATETIME DEFAULT (datetime('now', '+8 hours'))
updated_at DATETIME DEFAULT (datetime('now', '+8 hours'))

-- ❌ 错误（使用 UTC）
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
```

### Python 代码规范

```python
# ✅ 正确：在 SQL 中使用 SQLite 函数
conn.execute("""
    INSERT INTO table (..., created_at)
    VALUES (..., datetime('now', '+8 hours'))
""")

# ✅ 正确：显示/计算用 Python datetime
from datetime import datetime
now = datetime.now()  # 系统时区（如果是东八区则正确）
elapsed = (datetime.now() - started_at).total_seconds()

# ❌ 错误：Python datetime 用于数据库存储
fields['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
conn.execute("INSERT INTO table (..., created_at) VALUES (..., ?)", (..., fields['created_at']))
```

## 已修复的代码

### db_common.py

1. **第 892 行**（原）：`fields['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')`
   - **修复**：删除此行，由 SQL 语句中的 `datetime('now','+8 hours')` 处理

2. **第 2058 行**（原）：`fields['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')`
   - **修复**：删除此行，由 SQL 语句中的 `datetime('now','+8 hours')` 处理

### feedback_system.py

1. **第 137 行**（原）：`processed_at = datetime.now().isoformat()`
   - **修复**：改为 `processed_at = datetime('now', '+8 hours')` 在 SQL 中

## 需要注意的表

以下表在 `init_db.sql` 中使用了 `CURRENT_TIMESTAMP`，需要确保 Python 代码插入时使用正确时区：

| 表名 | 字段 | 状态 |
|------|------|------|
| chapter_versions | created_at | 由 `save_draft` 命令控制，需检查 |
| state_history | created_at | 由状态卡写入控制，需检查 |
| agent_messages | created_at | 由 `send_message` 命令控制 ✅ 已修复 |
| learned_patterns | first_seen, last_seen | 由模式记录控制，需检查 |
| best_practices | created_at | 由最佳实践记录控制，需检查 |
| anti_patterns | first_seen, last_seen | 由问题模式管理控制 ✅ 已修复 |
| context_rules | created_at, updated_at | 需检查 |

## 验证方法

```bash
# 在 SQLite 中检查当前时间
sqlite3 shared/data/novel_factory.db "SELECT datetime('now') as utc, datetime('now','+8 hours') as beijing;"

# 查看最近插入的记录时间
sqlite3 shared/data/novel_factory.db "SELECT created_at FROM chapters ORDER BY created_at DESC LIMIT 5;"
```

## 后续建议

1. **迁移现有数据**：如果数据库中已有 UTC 时间数据，需要批量转换
2. **统一表定义**：修改 `init_db.sql` 中所有表使用 `datetime('now','+8 hours')`
3. **代码审查**：定期检查新增代码是否遵循时区规范
