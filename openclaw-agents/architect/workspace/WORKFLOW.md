# 网文工厂完整工作流

## 🔄 核心流程图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              用户 (Jason)                                │
│         创建项目 / 发指令给星探 / 查看进度 / 接收日报 / 处理异常           │
└─────────────────────────────────────────────────────────────────────────┘
        │                       │                           ↑
        │ @星探 分析热点         │ 创建项目/查看进度          │ 日报推送
        ↓                       ↓                           │
┌─────────────────┐     ┌─────────────────────────────────────────────────┐
│      星探       │     │                      秘书                       │
│  用户指令驱动   │     │    触发：每日20:00 或 收到调度器通知              │
│  不主动扫描     │     │    动作：汇总数据 → 生成日报 → 推送给用户         │
└─────────────────┘     └─────────────────────────────────────────────────┘
                                   ↑                       ↑
                                   │ 任务状态变化           │ 通过通知
                                   │                       │
┌─────────────────────────────────────────────────────────────────────────┐
│                           调度器 (Dispatcher)                            │
│    触发：Cron 定时（每5分钟）                                             │
│    动作：                                                                │
│      1. 获取调度锁（防重叠）                                              │
│      2. 数据健康检查                                                     │
│      3. 发现最高优先级任务                                                │
│      4. 状态一致性与熔断检查                                              │
│      5. 创建 task_start 并获取真实 task_id                               │
│      6. sessions_spawn 唤醒对应 Agent                                    │
│      7. 释放调度锁                                                       │
│    注意：唤醒后立即结束本轮，等待下次 Cron                                 │
└─────────────────────────────────────────────────────────────────────────┘
         ↓                              ↓                         ↓
         │ spawn Author                 │ spawn Editor            │ spawn Planner
         ↓                              ↓                         ↓
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│        执笔         │    │        质检         │    │        总编         │
│    (Author)         │    │    (Editor)         │    │    (Planner)        │
│                     │    │                     │    │                     │
│ 触发：Dispatcher    │    │ 触发：Dispatcher    │    │ 触发：Dispatcher    │
│ 分配 create/revise  │    │ 分配 review         │    │ 分配 publish/create │
│                     │    │                     │    │                     │
│ 动作：              │    │ 动作：              │    │ 动作：              │
│ 1. 读取状态卡       │    │ 1. 读取草稿         │    │ 1. 读取质检报告     │
│ 2. 读取指令         │    │ 2. 五层审校         │    │ 2. 执行发布操作     │
│ 3. 读取参考资料     │    │ 3. 打分决策         │    │    或               │
│ 4. 创作章节         │    │ 4. 提取状态卡       │    │ 规划下一章指令      │
│ 5. save_draft       │    │ 5. add_review       │    │ 3. task_complete    │
│ 6. task_complete    │    │ 6. task_complete    │    │                     │
│                     │    │                     │    │                     │
│ ⚠️ 禁止通信：       │    │ ⚠️ 禁止通信：       │    │ ⚠️ 禁止通信：       │
│ 不通知任何人        │    │ 不通知任何人        │    │ 不通知任何人        │
│ 只修改DB状态        │    │ 只修改DB状态        │    │ 只修改DB状态        │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                                架构师                                    │
│    触发：用户请求                                                        │
│    动作：读取所有数据 → 诊断问题 → 向用户报告                              │
│    注意：独立于创作流程，不参与日常协作                                     │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## ⚠️ 重要：通信铁律

**所有 Agent 之间禁止直接通信！工作流流转完全由调度器 Cron 轮询负责。**

| Agent | 禁止行为 | 正确做法 |
|-------|---------|---------|
| 星探 | ❌ 禁止 `@总编`、`@执笔` | ✅ 只响应用户指令，输出报告给用户 |
| 总编 | ❌ 禁止 `@执笔`、`@质检`、`@调度` | ✅ 规划/发布 → 更新 DB → task_complete → 结束 |
| 执笔 | ❌ 禁止 `@质检`、`@总编`、`@调度` | ✅ 创作 → save_draft → task_complete → 结束 |
| 质检 | ❌ 禁止 `@总编`、`@执笔`、`@调度` | ✅ 审校 → add_review → task_complete → 结束 |
| 秘书 | ❌ 禁止 `@总编`、`@执笔`、`@质检` | ✅ 读取 DB 数据 → 汇报给用户 |
| 调度器 | ✅ 唯一有权 spawn Agent | ✅ Cron 触发 → 检查状态 → spawn → 结束 |

---

## 📋 各Agent详细工作流

### 1. 调度器 (Dispatcher) - 核心中枢

**触发条件：**
- Cron 定时触发（每 5 分钟）
- **不响应** subagent completion event（只记录日志，返回 NO_REPLY）

**工作流程：**
```
Step 0: 获取调度锁
    python3 scripts/lock.py acquire
    IF 获取失败: return "NO_REPLY" (另一调度正在进行)

Step 1: 数据健康检查
    python3 tools/db.py health_check <project>
    | severity | 处理 |
    |----------|------|
    | blocking | 暂停调度，message 通知用户 |
    | error    | 记录问题，继续调度 |
    | warning  | 继续流程 |

Step 2: 任务发现
    python3 tools/db.py chapters <project>
    按优先级取最高 1 个：
    1. revision（退回修改）→ spawn Author
    2. review（待审核）→ spawn Editor
    3. reviewed（待发布）→ spawn Planner
    4. planned（待创作）→ spawn Author (create)

Step 3: 一致性与熔断检查
    python3 scripts/consistency_check.py <project> <chapter>
    | action   | 说明 |
    |----------|------|
    | trigger  | 首次触发或前置完成 |
    | retry    | 任务失败，重试 |
    | skip     | 前置任务执行中 |
    | timeout  | 任务超时，标记失败 |
    | abandon  | 熔断，通知人类（≥3次退回）|

Step 4: 调度决策
    IF trigger 或 retry:
        # 1. 记录任务并获取 task_id
        python3 tools/db.py task_start <project> <task_type> <chapter> <agent_id>

        # 2. 使用真实 task_id spawn Agent
        sessions_spawn(
            agentId="<agent_id>",
            runtime="subagent",
            task="项目 <project> 第<chapter>章... 任务ID: <真实task_id>",
            cleanup="delete"
        )

    IF skip: 无操作，直接结束本轮
    IF timeout: python3 tools/db.py task_timeout <project> <task_id>
    IF abandon: message 通知用户

Step 5: 任务清理
    python3 tools/db.py task_timeout <project> 30
    (超时 30 分钟的任务自动标记 failed)

Step 6: 释放调度锁
    python3 scripts/lock.py release
```

**调度动作速查：**

| 状态 | task_type | agent_id | 任务描述 |
|------|-----------|----------|----------|
| revision | revise | author | 读取 reviews 修改重写 |
| review | review | editor | 五层审校并打分 |
| reviewed | publish | planner | 执行发布操作 |
| planned | create | author | 读取指令创作章节 |
| 无指令 | create | planner | 写下一章大纲 |

---

### 2. 星探 (Scout)

**触发条件：**
- 用户 `@星探` 指令（如 `@星探 分析市场热点`）

**工作流程：**
```
1. 收到用户指令
2. 读取 SKILL.md
3. 执行市场分析（热点分析/题材推荐/爆款解构）
4. 写入数据库：python tools/db.py add_market_report ...
5. 回复用户结构化报告
```

**禁止行为：**
- ❌ 禁止主动 `@总编`、`@执笔` 指挥他们干活
- ❌ 禁止直接修改项目的数据库设定

---

### 3. 总编 (Planner)

**触发条件：**
- Dispatcher 调度触发（sessions_spawn）
- 任务消息包含"执行发布操作"或"创建写作指令"

**工作流程：**

#### A. 发布流程（任务类型：publish）
```
1. 读取 SKILL.md
2. 提取 task_id
3. 读取质检通过的章节：python tools/db.py chapter_content <project> <chapter> draft
4. 执行发布：python tools/db.py update_chapter <project> <chapter> published
5. 同步伏笔数据：python tools/db.py sync_plots <project>
6. 任务完成：python tools/db.py task_complete <task_id> true
```

#### B. 规划流程（任务类型：create）
```
1. 读取 SKILL.md
2. 提取 task_id
3. 读取上一章状态卡：python tools/db.py chapter_state <project> <上一章>
4. 读取设定数据：python tools/db.py characters/factions/world_settings/outlines
5. 数据校对：python tools/db.py validate_data <project> <chapter>
6. 如需埋设新伏笔：python tools/db.py add_plot ...
7. 创建章节记录：python tools/db.py add_chapter ...
8. 创建写作指令：python tools/db.py create_instruction ...
9. 任务完成：python tools/db.py task_complete <task_id> true
```

**禁止行为：**
- ❌ 禁止 `sessions_spawn(author)` — 唤醒执笔是调度器的工作
- ❌ 禁止 `sessions_spawn(editor)` — 唤醒质检是调度器的工作
- ❌ 禁止 `@执笔`、`@质检`、`@调度` 等任何通知

---

### 4. 执笔 (Author)

**触发条件：**
- Dispatcher 调度触发（sessions_spawn）
- 任务消息包含"开始创作"或"修改章节"

**工作流程：**

#### 模式A：全新创作 (create)
```
Step 0: 获取项目上下文
    python tools/db.py current_project

Step 0.5: 读取问题模式库
    python3 tools/db.py anti_patterns --all

Step 1: 提取 task_id

Step 2: 读取状态卡
    python tools/db.py chapter_state <project> <上一章>

Step 3: 读取写作指令
    python tools/db.py instruction <project> <chapter>

Step 4: 读取参考资料
    python tools/db.py characters <project>
    python tools/db.py world_settings <project>
    python tools/db.py pending_plots <project>

Step 5: 创作章节（2000-2500字）

Step 6: 确认伏笔处理
    python tools/db.py verify_plots <project> <chapter>

Step 7: 保存草稿
    python tools/db.py save_draft <project> <chapter> --content "..."

Step 8: 任务完成
    python tools/db.py task_complete <task_id> true
    python tools/db.py update_chapter <project> <chapter> review
```

#### 模式B：质检退回修改 (revise)
```
Step 1-2: 同创作模式

Step 3: 读取质检报告
    python tools/db.py reviews <project>
    (找出 issues 和 suggestions)

Step 4: 读取当前草稿
    python tools/db.py chapter_content <project> <chapter> draft

Step 5: 读取原指令
    python tools/db.py instruction <project> <chapter>

Step 6: 针对性修改（只修复质检指出的问题）

Step 7: 自动检查
    python tools/db.py check_chapter <project> <chapter>

Step 8: 保存草稿 + task_complete
```

**禁止行为：**
- ❌ 禁止 `@质检`、`@总编`、`@调度` 等任何通知
- ❌ 禁止使用 `message` tool 或 `sessions_send` 通知其他 Agent
- ✅ 职责：接收指令 → 写作 → 写入 DB → 结束

---

### 5. 质检 (Editor)

**触发条件：**
- Dispatcher 调度触发（sessions_spawn）
- 任务消息包含"待审核"

**工作流程：**
```
Step 0: 获取项目上下文
    python tools/db.py current_project

Step 0.5: 读取问题模式库（强制！）
    python3 tools/db.py anti_patterns --all

Step 1: 提取 task_id

Step 2: 读取内容 + 字数统计
    python tools/db.py instruction <project> <chapter>
    python tools/db.py outlines <project>
    python tools/db.py chapter_content <project> <chapter> draft

Step 3: 读取设定数据
    python tools/db.py world_settings <project>
    python tools/db.py characters <project>
    python tools/db.py factions <project>
    python tools/db.py pending_plots <project>

Step 4: 读取上一章状态卡
    python tools/db.py chapter_state <project> <上一章>

Step 5: 五层审校（死刑检查 → 伏笔检查 → 打分）

Step 6: 自动检查（强制！）
    python tools/db.py check_chapter <project> <chapter>

Step 7: 提交质检报告
    IF 总分 >= 90:
        python tools/db.py add_review <project> <chapter> 0 true ...
        python tools/db.py update_chapter <project> <chapter> reviewed <words> <score>
        python tools/db.py chapter_state <project> <chapter> --set '<JSON>' "<summary>"
    ELSE:
        python tools/db.py add_review <project> <chapter> 0 false ...
        python tools/db.py update_chapter <project> <chapter> revision

Step 8: 任务完成（最重要！）
    python tools/db.py task_complete <task_id> true
```

**禁止行为：**
- ❌ 禁止 `@总编`、`@执笔`、`@调度` 等任何通知
- ❌ 禁止跳过死刑检查
- ❌ 禁止不调用 task_complete

---

### 6. 秘书 (Secretary)

**触发条件：**
- 定时：每日20:00
- 实时：收到调度器的任务完成通知

**工作流程：**

#### 定时日报
```
1. 读取统计数据
   python tools/db.py stats <project>
   python tools/db.py chapters <project>
   python tools/db.py pending_plots <project>
   python tools/db.py task_list <project> completed 10

2. 生成日报

3. 推送给用户
   @Jason "📊 网文工厂日报..."
```

#### 实时更新
```
收到任务完成通知后：
@Jason "✅ 任务完成：第X章已发布，评分XX分"
```

**禁止行为：**
- ❌ 禁止 `@总编`、`@执笔`、`@质检` 去命令他们干活
- ❌ 禁止自己修改项目的大纲或章节内容
- ✅ 职责：读取 DB 数据 → 分析提炼 → 推送给人类老板

---

### 7. 架构师 (Architect)

**触发条件：**
- 用户请求

**工作流程：**
```
1. 读取所有数据
   python tools/db.py stats <project>
   python tools/db.py chapters <project>
   python tools/db.py pending_plots <project>
   ... (全面扫描)

2. 分析
   - 工作流效率
   - 配置合理性
   - 数据质量

3. 向用户报告
   @Jason "📋 架构诊断报告..."
```

**注意：架构师独立于创作流程，不参与日常协作**

---

## 🔗 状态流转

```
章节状态流转：
planned → drafting → review → revision → published
                    ↑___________|
                     (退回修改)
```

---

## 📅 时间线示例

```
Day 1:
09:00 - 用户创建项目
09:05 - 用户请求星探分析市场
09:10 - 星探完成报告，回复用户
09:15 - 用户确认题材方向
09:20 - 总编（由用户触发）创建世界观、大纲、第1章指令
       (此时章节状态为 planned)
09:25 - Dispatcher Cron 触发，发现 planned 章节，spawn Author
09:30 - Author 开始创作，读取指令和状态卡
11:00 - Author 完成，save_draft，task_complete
       (章节状态变为 review)
11:05 - Dispatcher Cron 触发，发现 review 章节，spawn Editor
11:30 - Editor 完成审校，打分 92 分，通过
       (章节状态变为 reviewed)
11:35 - Dispatcher Cron 触发，发现 reviewed 章节，spawn Planner
11:40 - Planner 执行发布，task_complete
       (章节状态变为 published)
11:45 - Planner 创建第2章指令
       (第2章状态变为 planned)
... 循环继续
20:00 - 秘书定时推送日报
```

---

## 🚨 熔断机制

调度器会检测以下异常情况并触发熔断：

1. **死循环熔断**：同一章节退回 ≥ 3 次
   - 自动挂起任务
   - 通知人类介入

2. **超时熔断**：任务运行 > 30 分钟
   - 自动标记为 failed
   - 下次 Cron 可重试

3. **底层错误熔断**：工具调用失败 ≥ 3 次
   - 停止调度
   - 通知人类

---

## 📝 数据一致性保障

1. **状态卡系统**：每章结束后必须提取状态卡，为下一章提供数值基准
2. **伏笔追踪**：`verify_plots` 自动检查伏笔是否正确处理
3. **数据校对**：`validate_data` 在创建指令前检查引用完整性
4. **章节检查**：`check_chapter` 自动检测字数、状态卡矛盾、指令对齐等问题