# Agent 权限矩阵

## 概述

本文档定义了各 Agent 对数据表的操作权限，确保职责边界清晰。

## 权限类型

| 符号 | 含义 |
|------|------|
| ✅ CRUD | 完全读写权限 |
| ✅ R | 只读权限 |
| 🚫 | 无权限 |
| 🔔 | 通过消息队列提出异议 |

## 核心数据表权限

### 规划类数据（Planner 专属）

| 表 | Dispatcher | Planner | Author | Editor | 说明 |
|----|------------|---------|--------|--------|------|
| `outlines` | R | CRUD | R | R | 大纲规划 |
| `instructions` | R | CRUD | R | R | 写作指令 |
| `plot_holes` | R | CRUD | R | R | 伏笔管理 |
| `chapter_plots` | R | 系统 | 🚫 | 🚫 | 伏笔关联（自动记录） |
| `characters` | R | CRUD | R | R | 角色设定 |
| `factions` | R | CRUD | R | R | 势力设定 |
| `world_settings` | R | CRUD | R | R | 世界观设定 |

### 创作类数据

| 表 | Dispatcher | Planner | Author | Editor | 说明 |
|----|------------|---------|--------|--------|------|
| `chapters` | R | R | R/W | R | 章节状态（Author 修改状态/草稿） |
| `chapter_versions` | R | R | 系统自动 | R | 版本历史（系统自动保存） |
| `chapter_state` | R | R | R | W | 状态卡（Editor 写入） |

### 质检类数据

| 表 | Dispatcher | Planner | Author | Editor | 说明 |
|----|------------|---------|--------|--------|------|
| `reviews` | R | R | R | CRUD | 质检报告 |
| `learned_patterns` | R | R | 🚫 | W | 学习到的问题模式 |
| `anti_patterns` | R | R | R | R | 反模式库（只读） |
| `context_rules` | R | R | R | R | 上下文规则（只读） |

### 任务与消息

| 表 | Dispatcher | Planner | Author | Editor | 说明 |
|----|------------|---------|--------|--------|------|
| `task_status` | CRUD | R | R | R | 任务状态 |
| `agent_messages` | R/W | R/W | R/W | R/W | 异步消息队列 |

### 项目管理

| 表 | Dispatcher | Planner | Author | Editor | 说明 |
|----|------------|---------|--------|--------|------|
| `projects` | R/W | R | R | R | 项目信息 |
| `market_reports` | R | R | 🚫 | 🚫 | 市场报告 |

## Agent 消息队列

Editor 不能直接修改规划数据，但可以通过 `agent_messages` 表向 Planner 提出异议：

### 消息类型

| 类型 | 用途 | 示例 |
|------|------|------|
| `FLAG_ISSUE` | 标记问题 | "第10章数值与前文矛盾" |
| `ESCALATE` | 紧急升级 | "伏笔P003无法兑现" |
| `SUGGEST` | 改进建议 | "建议调整角色出场顺序" |
| `NOTIFY` | 一般通知 | "第15章质检通过" |

### 使用方式

```bash
# 发送消息（需要 project_id）
python3 tools/db.py send_message xuanhuan editor planner ESCALATE 10 '{"issue":"伏笔P003无法兑现","reason":"触发条件与当前剧情冲突"}' high

# 获取消息（需要 project_id）
python3 tools/db.py get_messages xuanhuan planner pending 10

# 标记已处理
python3 tools/db.py resolve_message 1 "已确认，将调整P003到第15章兑现"
```

## 伏笔验证机制

### Author 权限调整

**已移除的命令**：
- `add_plot` - 由 Planner 负责埋设伏笔
- `resolve_plot` - 由 Planner 负责兑现伏笔
- `add_character` - 由 Planner 负责角色规划

**可用命令**：
- `pending_plots` - 只读查询待兑现伏笔
- `verify_plots` - 自查用（验证伏笔处理）

### Editor 伏笔验证流程

Editor 必须在质检流程中执行 `verify_plots` 命令：

```bash
python3 tools/db.py verify_plots <project> <chapter>
```

**返回结构**：
```json
{
  "success": true,
  "plot_deviation": {
    "missing_plant_count": 0,
    "missing_resolve_count": 1,
    "completion_rate": 0.67
  },
  "plot_score_deduction": 20,
  "issues": ["指令要求兑现但内容中未找到: ['P003']"],
  "valid": false
}
```

**扣分规则**：
- 漏兑现（missing_resolve）：每个扣 **20 分**
- 漏埋（missing_plant）：每个扣 **10 分**
- 额外记录：扣 **5 分**

**严重偏差处理**：
- `plot_score_deduction >= 20` → 总分 ≤ 60，直接退回
- 通过 `agent_messages` 通知 Planner 重新规划

## 数据流向

```
[Planner] 创建指令（含 plots_to_plant/plots_to_resolve）
    │
    ↓
[Author] 根据指令写作 → verify_plots 自查
    │
    ↓
[Editor] 质检 → verify_plots 强制验证
    │
    ├─→ Pass: 写入 chapter_state
    │
    └─→ Fail (偏差严重):
           │
           └─→ agent_messages (ESCALATE) → [Planner] 调整规划
```

## 版本历史

| 日期 | 变更 |
|------|------|
| 2026-04-05 | 移除 Author 的 add_plot/resolve_plot 权限 |
| 2026-04-05 | 添加伏笔验证机制和 plot_score_deduction |
| 2026-04-05 | 添加 agent_messages 消息队列 |
| 2026-04-05 | Editor 可通过消息向 Planner 提出异议 |
