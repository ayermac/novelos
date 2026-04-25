---
name: dispatcher-scheduler
description: |
  网文工厂调度器 - 监控系统健康、检查任务状态、调度 Agent 执行创作流程。
  
  TRIGGER when:
  - Cron 定时触发（每 5 分钟）
  - 收到 subagent completion event（检查熔断状态，更新记忆，返回 NO_REPLY）
  - 用户询问调度状态或任务进度
  
  DO NOT trigger when:
  - 收到非调度相关的消息（直接返回 NO_REPLY）
  - 简单的数据库查询请求（使用 db.py 直接查询）
---

# 调度器 Skill (v2)

## ⚠️ 核心原则

1. **只调度，不越权** - 不决定稿件通过/退回，只负责查看状态并唤醒 Agent
2. **防死循环** - 同一章节退回 ≥3 次立即熔断，通知人类
3. **防重叠** - 使用文件锁防止 Cron 重叠执行
4. **即用即毁** - 子会话必须 `cleanup="delete"`

## 触发方式与响应规则

| 触发条件 | 响应 |
|----------|------|
| ✅ Cron 定时触发 | 执行完整调度流程 |
| ✅ subagent completion event | 检查熔断状态 → 更新记忆 → 返回 `NO_REPLY` |
| ❌ 非调度相关消息 | 返回 `NO_REPLY`，不执行逻辑 |

**⚠️ completion event 不触发新调度** - 避免快速循环，等待下一次 Cron

## 调度流程

```
Step 0: 获取调度锁（防止重叠）
Step 1: 数据健康检查
Step 2: 任务发现
Step 3: 状态一致性与熔断检查
Step 4: 调度决策与唤醒
Step 5: 任务清理和恢复
Step 6: 释放调度锁
```

---

### Step 0: 获取调度锁

```bash
python3 skills/dispatcher/scripts/lock.py acquire
```

返回 0 = 获取成功，返回 1 = 已被占用

详见 `skills/dispatcher/scripts/lock.py`

---

### Step 1: 系统健康检查

**使用监控系统获取完整健康报告。**

```bash
# 生成 JSON 健康报告
python3 -c "
from shared.monitoring import SystemMonitor
import json
monitor = SystemMonitor('shared/data/novel_factory.db')
report = monitor.generate_report('<project>')
print(json.dumps(report, ensure_ascii=False, indent=2))
"
```

**返回结构**：
```json
{
  "status": "healthy|warning|error|critical",
  "metrics": {
    "task_failure_rate": {"value": 5.0, "unit": "%"},
    "avg_review_score": {"value": 85.5, "unit": "分"},
    "plot_resolution_rate": {"value": 80.0, "unit": "%"},
    "fuse_count": {"value": 0, "unit": "次"},
    "message_backlog": {"value": 2, "unit": "条"}
  },
  "alerts": [
    {"level": "warning", "message": "平均质检分数过低: 75", "suggestion": "查看质检报告"}
  ]
}
```

**处理规则**：
| status | 处理 |
|--------|------|
| `healthy` | 继续调度 |
| `warning` | 记录日志，继续调度 |
| `error` | 暂停调度，`message` 通知用户 |
| `critical` | 立即熔断，`message` 通知用户 |

**或使用简单检查**：
```bash
python3 tools/db.py health_check <project>
```

---

### Step 2: 任务发现

```bash
python3 tools/db.py chapters <project>
```

按优先级取最高 1 个：
1. `revision`（退回修改）
2. `review`（待审核）
3. `reviewed`（待发布）
4. `planned`（待创作）

---

### Step 3: 一致性与熔断检查

```bash
python3 skills/dispatcher/scripts/consistency_check.py <project> <chapter>
```

返回值：

| action | 说明 |
|--------|------|
| `trigger` | 首次触发或前置完成 |
| `retry` | 任务失败，重试 |
| `skip` | 前置任务执行中 |
| `timeout` | 任务超时，标记失败 |
| `abandon` | 熔断，通知人类 |

**熔断条件**：
- 同一章节退回 ≥ 3 次 → 死循环熔断
- 底层错误重试 3 次失败 → 人工干预

详见 `skills/dispatcher/references/state_machine.md`

---

### Step 4: 调度决策

根据 Step 3 返回值执行：

#### trigger / retry

```bash
# 1. 记录任务并获取 task_id
python3 tools/db.py task_start <project> <task_type> <chapter> <agent_id>

# 2. 使用真实 task_id spawn Agent
sessions_spawn(
    agentId="<agent_id>",
    runtime="subagent",
    task="项目 <project> 第<chapter>章... 任务ID: <真实task_id>",
    cleanup="delete"
)
```

#### skip
无操作，直接结束本轮

#### timeout
```bash
python3 tools/db.py task_timeout <project> <task_id>
```

#### abandon
使用 `message` 通知用户

---

### Step 4.5: 检查待处理消息（可选）

在调度 Planner 前，检查是否有待处理的消息（如 Editor 提出的异议）：

```bash
python3 tools/db.py get_messages <project> planner pending 5
```

如果有待处理消息，在 spawn Planner 时将消息内容注入任务上下文：

```
项目 <project> 第<chapter>章规划... 任务ID: <task_id>

【待处理消息】
- Editor 提出异议：伏笔 P003 无法兑现，建议延后到第 15 章
```

---

### Step 5: 任务清理

```bash
python3 tools/db.py task_timeout <project> 30
```

超时 30 分钟的任务自动标记 `failed`

---

### Step 6: 释放锁

```bash
python3 skills/dispatcher/scripts/lock.py release
```

---

## 调度动作速查

| 状态 | task_type | agent_id | 任务描述 |
|------|-----------|----------|----------|
| revision | revise | author | 读取 reviews 修改重写 |
| review | review | editor | 五层审校并打分 |
| reviewed | publish | planner | 执行发布操作 |
| planned | create | author | 读取指令创作章节 |
| 无指令 | create | planner | 写下一章大纲 |

## 命令速查

| 命令 | 用途 |
|------|------|
| `health_check [project]` | 健康检查 |
| `chapters <project>` | 列出章节 |
| `next_chapter [project]` | 下一章信息 |
| `task_start <p> <type> <n> <agent>` | 任务开始 |
| `task_complete <id> [true\|false]` | 任务完成 |
| `task_list <p> [status] [limit]` | 列出任务 |
| `task_reset <id>` | 重置任务 |
| `task_timeout <p> <minutes>` | 超时检查 |
| `get_messages <p> <agent> [status]` | 获取消息 |
| `send_message <p> <from> <to> <type> <ch> '<json>' [pri]` | 发送消息 |
| `resolve_message <id> [result]` | 解决消息 |

## ⚠️ 关键纪律

1. **真实 ID 注入** - 绝不能发送 `<task_id>` 占位符，必须用 `task_start` 返回的真实数字
2. **每次只调度一个** - 触发完毕后直接返回，结束本轮
3. **异常必叫人** - 超时、熔断、报错立即 `message` 通知用户
