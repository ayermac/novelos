# TOOLS.md - 质检工具

## 数据库访问

```bash
python3 tools/db.py <command>
```

## 常用命令索引

| 命令 | 用途 |
|------|------|
| `current_project` | 获取当前项目 |
| `build_context <p> <c> editor` | 获取完整上下文（推荐） |
| `chapter_content <p> <c> draft` | 读取章节草稿 |
| `instruction <p> <c>` | 读取写作指令 |
| `chapter_state <p> <c>` | 读取状态卡 |
| `verify_plots <p> <c>` | 伏笔验证（强制！） |
| `check_chapter <p> <c>` | 自动检查章节 |
| `add_review ...` | 提交质检报告 |
| `update_chapter <p> <c> reviewed/revision` | 更新状态 |
| `task_complete <id> true/false` | 完成任务 |
| `anti_patterns --all` | 读取问题模式库 |
| `send_message ...` | 发送异议给 Planner |

## 参考资料

| 文档 | 用途 |
|------|------|
| [SKILL.md](skills/quality-review/SKILL.md) | **完整工作流程** |
| [commands.md](skills/quality-review/references/commands.md) | 数据库命令详解 |
| [scoring_criteria.md](skills/quality-review/references/scoring_criteria.md) | 五层打分标准 |
| [death_penalty.md](skills/quality-review/references/death_penalty.md) | 死刑红线 |
| [plot_verification.md](skills/quality-review/references/plot_verification.md) | 伏笔验证 |