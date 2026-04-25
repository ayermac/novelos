# TOOLS.md - 调度器工具

## 数据库访问

```bash
python3 tools/db.py <command>
```

## 常用命令索引

### 任务管理

| 命令 | 用途 |
|------|------|
| `task_list <p> running` | 查看运行中任务 |
| `task_list <p> pending` | 查看待处理任务 |
| `task_start <p> <type> <c> <agent>` | 启动任务 |
| `task_complete <id> true/false` | 完成任务 |
| `task_timeout <p> <minutes>` | 超时处理 |

### 健康检查

| 命令 | 用途 |
|------|------|
| `health_check <p>` | 快速健康检查 |
| `health_report <p>` | 详细健康报告 |

### 状态更新

| 命令 | 用途 |
|------|------|
| `update_chapter <p> <c> <status>` | 更新章节状态 |
| `increment_retry <task_id>` | 递增重试计数 |

## 可用 Skills

| Skill | 用途 |
|-------|------|
| `dispatcher` | 调度工作流程 |

## 详细流程

参见：`skills/dispatcher/SKILL.md`