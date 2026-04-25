# TOOLS.md - 架构师工具

## 数据库访问

```bash
python3 tools/db.py <command>
```

**权限**：只读访问（诊断分析）

## 常用命令索引

### 项目诊断

| 命令 | 用途 |
|------|------|
| `projects` | 列出所有项目 |
| `current_project` | 获取当前项目 |
| `stats <p>` | 项目统计 |
| `health_check <p>` | 快速健康检查 |
| `health_report <p>` | 详细健康报告 |

### 数据查询

| 命令 | 用途 |
|------|------|
| `chapters <p>` | 章节列表 |
| `reviews <p>` | 质检报告 |
| `pending_plots <p>` | 待兑现伏笔 |
| `characters <p>` | 角色设定 |

### 问题模式管理

| 命令 | 用途 |
|------|------|
| `anti_patterns --all` | 查看所有问题模式 |
| `pattern_stats --top 20` | 高频问题统计 |
| `context_rules` | 查看上下文规则 |

## 共享工具

```bash
# 清空项目数据
python3 shared/tools/clean_project.py <project_id> [--delete-project]

# 导出已发布章节
python3 shared/tools/export_chapters.py <project_id> [--list|--all]

# 章节检查
python3 shared/tools/check_chapter.py <project> <chapter>
```

## 数据位置

| 资源 | 路径 |
|------|------|
| 主数据库 | `shared/data/novel_factory.db` |
| 初始化脚本 | `shared/data/init_db.sql` |
| 升级脚本 | `shared/data/upgrade_db.sql` |
