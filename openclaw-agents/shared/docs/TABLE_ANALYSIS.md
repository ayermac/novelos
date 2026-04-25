# 数据表 project_id 关联分析

## 检查日期：2026-04-06

## 表分类

### ✅ 已正确关联 project_id 的表

| 表名 | project_id | 说明 |
|------|------------|------|
| `world_settings` | ✅ NOT NULL | 世界观设定（每部小说独立） |
| `characters` | ✅ NOT NULL | 角色设定（每部小说独立） |
| `factions` | ✅ NOT NULL | 势力设定（每部小说独立） |
| `instructions` | ✅ NOT NULL | 写作指令（每部小说独立） |
| `plot_holes` | ✅ NOT NULL | 伏笔管理（每部小说独立） |
| `chapter_plots` | ✅ NOT NULL | 章节伏笔关联（每部小说独立） |
| `outlines` | ✅ NOT NULL | 大纲（每部小说独立） |
| `chapters` | ✅ NOT NULL | 章节（每部小说独立） |
| `reviews` | ✅ NOT NULL | 质检报告（每部小说独立） |
| `task_status` | ✅ NOT NULL | 任务状态（每部小说独立） |
| `chapter_state` | ✅ NOT NULL (PK) | 章节状态卡（每部小说独立） |
| `chapter_versions` | ✅ NOT NULL | 章节版本（每部小说独立） |
| `state_history` | ✅ NOT NULL | 状态历史（每部小说独立） |

### ⚠️ project_id 可为空的表

| 表名 | project_id | 问题 | 建议 |
|------|------------|------|------|
| `learned_patterns` | 可为 NULL | 问题模式学习记录，project_id 可为空表示全局模式 | ✅ 合理：可为空表示全局通用模式 |
| `best_practices` | 可为 NULL | 最佳实践记录，project_id 可为空表示通用实践 | ✅ 合理：可为空表示全局通用实践 |

### ❌ 缺少 project_id 的表

| 表名 | project_id | 问题分析 | 建议 |
|------|------------|----------|------|
| `projects` | 无（自身是主表） | ✅ 正确：这是项目主表 | 无需修改 |
| `market_reports` | 无 | ✅ 正确：市场报告是全局数据，不关联具体项目 | 无需修改 |
| ~~`agent_messages`~~ | ~~无~~ | ~~⚠️ 消息关联到 chapter_number 但没有 project_id~~ | **✅ 已修复 (2026-04-06)** |
| `anti_patterns` | 无 | ✅ 正确：反模式库是全局共享的 | 无需修改 |
| `context_rules` | 无 | ✅ 正确：上下文规则是全局共享的 | 无需修改 |

---

## ✅ 已修复的问题

### `agent_messages` - 已添加 project_id (2026-04-06)

**修改内容**：
- 添加 `project_id TEXT` 列
- 创建索引 `idx_agent_messages_project`
- 更新 `send_message` 命令参数顺序：`<project_id> <from_agent> <to_agent> <type> <chapter> '<json>' [priority]`
- 更新 `get_messages` 命令参数顺序：`<project_id> <agent> [status] [limit]`

**升级脚本**：`shared/data/upgrade_agent_messages.sql`

---

## 数据共享策略说明

### 全局共享数据（无需 project_id）

| 表 | 用途 | 共享原因 |
|----|------|----------|
| `anti_patterns` | 反模式库 | 所有项目共用同一套问题检测规则 |
| `context_rules` | 上下文规则 | 所有项目共用同一套上下文规则 |
| `market_reports` | 市场报告 | 市场分析是全局性的，服务于所有项目 |

### 项目专属数据（必须有 project_id）

- 规划类：`outlines`, `instructions`, `plot_holes`, `characters`, `factions`, `world_settings`
- 创作类：`chapters`, `chapter_versions`, `chapter_state`, `state_history`
- 质检类：`reviews`, `chapter_plots`
- 任务类：`task_status`

### 可选关联（project_id 可为空）

| 表 | 场景 |
|----|------|
| `learned_patterns` | project_id 为空 = 全局通用问题模式；有值 = 该项目的特有问题 |
| `best_practices` | project_id 为空 = 全局通用最佳实践；有值 = 该项目的特有经验 |

---

## 执行计划

### ✅ 已完成
1. [x] `agent_messages` 添加 `project_id` 列 (2026-04-06)
   - 升级脚本：`shared/data/upgrade_agent_messages.sql`
   - 命令更新：`send_message`, `get_messages` 已支持 project_id 参数

### 可选优化
1. [ ] 为 `learned_patterns` 添加项目级隔离支持
2. [ ] 为 `best_practices` 添加项目级隔离支持
