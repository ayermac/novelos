# TOOLS.md - 执笔工具

## 数据库访问

```bash
python3 tools/db.py <command>
```

## 常用命令索引

| 命令 | 用途 |
|------|------|
| `current_project` | 获取当前项目 |
| `build_context <p> <c> author` | 获取完整上下文（推荐） |
| `chapter_state <p> <c>` | 读取状态卡 |
| `instruction <p> <c>` | 读取写作指令 |
| `save_draft <p> <c> --content "..."` | 保存草稿 |
| `verify_plots <p> <c>` | 验证伏笔处理 |
| `check_chapter <p> <c>` | 自动检查章节 |
| `task_complete <id> true/false` | 完成任务 |
| `update_chapter <p> <c> review` | 更新状态为待质检 |

## 参考资料

| 文档 | 用途 |
|------|------|
| [SKILL.md](skills/novel-writing/SKILL.md) | **完整工作流程** |
| [commands.md](skills/novel-writing/references/commands.md) | 数据库命令详解 |
| [writing_templates.md](skills/novel-writing/references/writing_templates.md) | 写作模板 |
| [quality-guide.md](skills/novel-writing/references/quality-guide.md) | 质检防退回指南 |