# TOOLS.md - 总编工具

## 数据库访问

```bash
python3 tools/db.py <command>
```

## 常用命令索引

| 命令 | 用途 |
|------|------|
| `current_project` | 获取当前项目 |
| `build_context <p> <c> planner` | 获取完整规划上下文（推荐） |
| `chapter_state <p> <c>` | 读取状态卡 |
| `next_chapter <p>` | 获取下一章信息 |
| `create_instruction ...` | 创建写作指令 |
| `validate_data <p> <c>` | 数据校对 |
| `update_chapter <p> <c> published` | 发布章节 |
| `sync_plots <p>` | 同步伏笔数据 |
| `task_complete <id> true` | 完成任务 |
| `get_messages <p> planner pending 10` | 获取待处理消息 |
| `resolve_message <id> "处理结果"` | 标记消息已处理 |

## 可用 Skills

| Skill | 用途 |
|-------|------|
| `worldbuilding` | 世界观构建 |
| `chapter-planning` | 章节规划 |
| `plot-tracking` | 伏笔追踪 |