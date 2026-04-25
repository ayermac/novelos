# Agent 工作流与数据流转完整文档

## 一、核心工作流程图

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Dispatcher 调度中枢                                │
│                           (Cron 每5分钟触发)                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│  Step 0: 获取调度锁 (skills/dispatcher/scripts/lock.py)                        │
│  Step 1: 数据健康检查 (health_check)                                            │
│  Step 2: 任务发现 (chapters → 按优先级取最高1个)                                 │
│  Step 3: 一致性检查 (skills/dispatcher/scripts/consistency_check.py)           │
│  Step 4: 调度决策 → sessions_spawn(agentId, task, cleanup="delete")             │
│  Step 5: 任务清理 (task_timeout 30分钟)                                         │
│  Step 6: 释放调度锁                                                             │
└─────────────────────────────────────────────────────────────────────────────────┘
                    │
                    │ 按 chapters.status 调度
                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              状态优先级队列                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│  P2: revision   → spawn Author(revise)    质检退回，修改重写                     │
│  P3: review     → spawn Editor(review)    有草稿，待审核                        │
│  P4: reviewed   → spawn Planner(publish)  已通过，待发布                        │
│  P5: planned    → spawn Author(create)    有指令，创作新章                       │
│  P6: 无指令     → spawn Planner(create)    无指令，规划下一章                    │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、Planner（总编）工作流

### 触发场景
| 场景 | 任务类型 | 触发条件 |
|------|---------|---------|
| 规划下一章 | create | chapters 无指令（has_instruction=false） |
| 发布章节 | publish | chapters.status = reviewed |

### 数据读写

```
┌──────────────────────────────────────────────────────────────┐
│                    Planner 数据流                            │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  【读取】                                                     │
│  ├─ projects (current_project)                               │
│  ├─ chapters (next_chapter)                                  │
│  ├─ instructions (instruction)                               │
│  ├─ chapter_state (上一章状态卡)                              │
│  ├─ characters (角色设定)                                     │
│  ├─ factions (势力设定)                                       │
│  ├─ world_settings (世界观)                                   │
│  ├─ outlines (大纲)                                          │
│  ├─ plot_holes (pending_plots - 待处理伏笔)                   │
│  └─ agent_messages (get_messages - 待处理异议)                │
│                                                              │
│  【创建/更新】                                                 │
│  ├─ chapters (add_chapter - 创建章节记录)                     │
│  ├─ instructions (create_instruction - 创建写作指令)          │
│  ├─ plot_holes (add_plot - 创建新伏笔)                        │
│  ├─ plot_holes (resolve_plot - 兑现伏笔)                      │
│  ├─ characters (add_character/update_character - 角色管理)    │
│  ├─ factions (add_faction/update_faction - 势力管理)          │
│  ├─ world_settings (add_world_setting - 世界观设定)           │
│  ├─ outlines (create_outline - 大纲管理)                      │
│  ├─ chapter_plots (sync_plots - 同步伏笔关联)                 │
│  ├─ chapters (update_chapter published - 发布章节)            │
│  ├─ agent_messages (resolve_message - 处理异议)               │
│  └─ task_status (task_complete - 完成任务)                    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 规划流程 (create)

```
Step 0: current_project                    → 获取项目ID
Step 1: task_list running                  → 提取 task_id
Step 2: chapter_state <上一章>             → 读取状态卡
Step 3: next_chapter                       → 获取下一章信息
Step 4: IF has_instruction=false:
           → 规划流程
        IF has_instruction=true:
           → 发布流程

【规划流程】
Step 5: build_context <project> <chapter> planner  → 一次性获取上下文
        或分步读取:
        - characters <project>
        - factions <project>
        - world_settings <project>
        - outlines <project>
        - pending_plots <project>

Step 6: validate_data <project> <chapter> → 数据校对（伏笔引用检查）

Step 7: IF 需要新伏笔:
           add_plot <project> <code> <type> "<title>" "<description>" \
                    <planted_chapter> <planned_resolve>

Step 8: add_chapter <project> <chapter> "<title>" 0 planned

Step 9: create_instruction <project> <chapter> \
          "<objective>" "<key_events>" "<ending_hook>" \
          '<plots_to_resolve>' '<plots_to_plant>' \
          "<emotion_tone>" '<new_characters>'

Step 10: task_complete <task_id> true
```

### 发布流程 (publish)

```
Step 1: chapter_content <project> <chapter> draft → 复核章节
Step 2: update_chapter <project> <chapter> published → 发布
Step 3: sync_plots <project> → 同步伏笔回收
Step 4: task_complete <task_id> true
```

---

## 三、Author（执笔）工作流

### 触发场景
| 场景 | 任务类型 | 触发条件 |
|------|---------|---------|
| 创作新章 | create | chapters.status = planned |
| 修改重写 | revise | chapters.status = revision |

### 数据读写

```
┌──────────────────────────────────────────────────────────────┐
│                    Author 数据流                             │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  【读取 - 只读权限】                                           │
│  ├─ projects (current_project)                               │
│  ├─ chapters (chapters, chapter_content)                     │
│  ├─ instructions (instruction)                               │
│  ├─ chapter_state (上一章状态卡)                              │
│  ├─ characters (角色设定)                                     │
│  ├─ world_settings (世界观)                                   │
│  ├─ pending_plots (待处理伏笔)                                │
│  ├─ outlines (大纲)                                          │
│  ├─ anti_patterns (问题模式库 - 避坑指南)                      │
│  └─ reviews (质检报告 - 仅修改模式)                           │
│                                                              │
│  【创建/更新】                                                 │
│  ├─ chapters (save_draft - 保存草稿)                          │
│  │   └─ 自动创建 chapter_versions 记录                        │
│  ├─ chapters (update_chapter review - 提交审核)               │
│  └─ task_status (task_complete - 完成任务)                    │
│                                                              │
│  【禁止操作】                                                  │
│  ├─ ❌ add_plot / resolve_plot (伏笔由 Planner 管理)          │
│  ├─ ❌ add_character (角色由 Planner 规划)                    │
│  └─ ❌ create_instruction (指令由 Planner 创建)               │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 创作流程 (create)

```
Step 0: current_project                    → 获取项目ID
Step 0.5: anti_patterns --all              → 读取问题模式库（避坑指南）
Step 1: task_list running                  → 提取 task_id
Step 2: chapter_state <上一章>             → 读取状态卡（数值基准）
Step 3: instruction <project> <chapter>    → 读取写作指令
Step 4: build_context <project> <chapter> author → 一次性获取上下文
        或分步读取:
        - characters <project>
        - world_settings <project>
        - pending_plots <project>

Step 5: 【创作正文】

Step 6: verify_plots <project> <chapter>   → 验证伏笔处理

Step 7: save_draft <project> <chapter> --content "..." → 保存草稿
        └─ 自动创建 chapter_versions 记录

Step 8: update_chapter <project> <chapter> review → 提交审核

Step 9: task_complete <task_id> true
```

### 修改流程 (revise)

```
Step 0-1: 同创作流程

Step 2: chapter_state <上一章>             → 读取状态卡（关键！）
Step 3: reviews <project>                  → 读取质检报告
Step 4: chapter_content <project> <chapter> draft → 读取当前草稿
Step 5: instruction <project> <chapter>    → 读取原指令
Step 6: build_context <project> <chapter> author → 读取参考资料
        或分步:
        - characters <project>
        - world_settings <project>
        - pending_plots <project>（关键！）
        - outlines <project>

Step 7: 【针对性修改】只修复质检指出的问题

Step 8: verify_plots <project> <chapter>   → 验证伏笔处理

Step 9: check_chapter <project> <chapter>  → 自动检查（禁用词、数值）

Step 10: save_draft <project> <chapter> --content "..."

Step 11: update_chapter <project> <chapter> review

Step 12: task_complete <task_id> true
```

---

## 四、Editor（质检）工作流

### 触发场景
| 场景 | 任务类型 | 触发条件 |
|------|---------|---------|
| 质量审校 | review | chapters.status = review |

### 数据读写

```
┌──────────────────────────────────────────────────────────────┐
│                    Editor 数据流                             │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  【读取 - 只读权限】                                           │
│  ├─ projects (current_project)                               │
│  ├─ chapters (chapters, chapter_content)                     │
│  ├─ instructions (instruction, instructions)                 │
│  ├─ chapter_state (上一章状态卡)                              │
│  ├─ characters (角色设定)                                     │
│  ├─ factions (势力设定)                                       │
│  ├─ world_settings (世界观)                                   │
│  ├─ pending_plots (待处理伏笔)                                │
│  ├─ outlines (大纲)                                          │
│  └─ anti_patterns (问题模式库 - 死刑红线)                      │
│                                                              │
│  【创建/更新】                                                 │
│  ├─ reviews (add_review - 添加质检报告)                       │
│  ├─ chapters (update_chapter reviewed/revision - 更新状态)    │
│  ├─ chapter_state (写入状态卡 - 仅通过时)                     │
│  ├─ agent_messages (send_message - 提出异议)                  │
│  └─ task_status (task_complete - 完成任务)                    │
│                                                              │
│  【禁止操作】                                                  │
│  ├─ ❌ add_plot / resolve_plot (伏笔由 Planner 管理)          │
│  ├─ ❌ create_instruction (指令由 Planner 创建)               │
│  └─ ❌ save_draft (内容由 Author 编写)                        │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 质检流程 (review)

```
Step 0: current_project                    → 获取项目ID
Step 0.5: anti_patterns --all              → 读取问题模式库（强制！）
Step 1: task_list running                  → 提取 task_id
Step 2: instruction <project> <chapter>    → 读取写作指令（含 word_target）
        outlines <project>                 → 读取大纲
        chapter_content <project> <chapter> draft → 读取草稿
        → 字数偏差检查

Step 3: build_context <project> <chapter> editor → 一次性获取上下文
        或分步读取:
        - world_settings <project>
        - characters <project>
        - factions <project>
        - pending_plots <project>

Step 4: chapter_state <上一章>             → 读取状态卡（数值连续性）

Step 5: 【五层审校】
        ├─ 阶段1: 死刑机制检查 (death_penalty)
        │   └─ 触发死刑 → 总分=50, pass=false, 结束
        ├─ 阶段2: 伏笔兑现检查 (plot_verification)
        │   └─ 伏笔逻辑硬伤 → 总分≤60, pass=false
        └─ 阶段3: 五层打分 (scoring_criteria)
            ├─ 设定一致性 (25分)
            ├─ 逻辑漏洞 (25分)
            ├─ 毒点检测 (20分)
            ├─ 文字质量 (15分)
            └─ 爽点钩子 (15分)

Step 6: check_chapter <project> <chapter>  → 自动检查
        → 返回 issues/warnings
        → issues 必须添加到 review.issues

Step 6.5: verify_plots <project> <chapter> → 伏笔验证（强制！）
        → 返回 plot_deviation + plot_score_deduction
        → 必须计入最终分数

Step 7: 【提交质检报告】
        IF 总分 ≥ 90 且无单项不及格:
            add_review <project> <chapter> 0 true "<summary>" \
                       <set> <logic> <poison> <text> <pace> "[]" "[]"
            update_chapter <project> <chapter> reviewed <words> <score>
            chapter_state <project> <chapter> --set '<JSON>' "<summary>"
        ELSE:
            add_review <project> <chapter> 0 false "<summary>" \
                       <set> <logic> <poison> <text> <pace> \
                       "[\"问题1\"]" "[\"建议1\"]"
            update_chapter <project> <chapter> revision

Step 8: task_complete <task_id> true

Step 9: chapter_state <project> <chapter>  → 验证写入（仅通过时）

Step 10: IF 伏笔偏差严重:
            send_message <project> editor planner ESCALATE <chapter> '<JSON>'
```

---

## 五、状态流转与数据表关系

### 章节状态流转

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌──────────┐     ┌───────────┐
│ planned │ ──▶ │ review  │ ──▶ │reviewed │ ──▶ │published │     │           │
└─────────┘     └─────────┘     └─────────┘     └──────────┘     │           │
     │               │                                               │           │
     │               │ 退回                                         │  blocking  │
     │               ▼                                               │  (熔断)    │
     │         ┌───────────┐                                         │           │
     └────────▶│ revision  │─────────────────────────────────────▶│           │
               └───────────┘   退回≥3次                              └───────────┘
                    │
                    │ 重写完成
                    ▼
               ┌─────────┐
               │ review  │
               └─────────┘

状态转换触发:
- planned → review:   Author 完成 save_draft + update_chapter review
- review → reviewed:  Editor 质检通过 (score ≥ 90)
- review → revision:  Editor 质检退回 (score < 90)
- revision → review:  Author 重写完成
- reviewed → published: Planner 发布
- 任意 → blocking:    退回≥3次，熔断
```

### 任务状态流转

```
┌─────────────┐
│   pending   │ ◀── Dispatcher: task_start()
└─────────────┘
       │
       │ sessions_spawn(Agent)
       ▼
┌─────────────┐
│   running   │ ◀── Agent 执行中
└─────────────┘
       │
       ├──────────────┬──────────────┐
       │              │              │
       ▼              ▼              ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  completed  │ │   failed    │ │   timeout   │
└─────────────┘ └─────────────┘ └─────────────┘
       │              │              │
       ▼              ▼              ▼
   下一步调度      retry 或 abandon  标记失败

任务字段:
- task_type: create / revise / review / publish
- agent_id: author / editor / planner
- status: pending / running / completed / failed
- retry_count: 重试次数（≥3 触发熔断）
```

---

## 六、数据表关系图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              projects                                       │
│  project_id (PK) | name | genre | status | is_current | current_chapter    │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        │ project_id (FK)
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              chapters                                       │
│  id (PK) | project_id | chapter_number | title | content | status | ...    │
│  instruction_id (FK) ───────────────────────────────────────────┐           │
└─────────────────────────────────────────────────────────────────────────────┘
        │                                           │
        │ chapter_id                                │
        ▼                                           ▼
┌───────────────────────┐              ┌───────────────────────────────────────┐
│       reviews         │              │            instructions               │
│  chapter_id (FK)      │              │  id (PK) | project_id | chapter_number │
│  pass | score | ...   │              │  objective | key_events | plots_*     │
└───────────────────────┘              └───────────────────────────────────────┘
        │
        │ project_id
        ▼
┌───────────────────────┐              ┌───────────────────────────────────────┐
│    chapter_state      │              │           plot_holes                  │
│  project_id | chapter │              │  code | type | status | planted_ch    │
│  state_data | summary │              │  resolved_chapter | description      │
└───────────────────────┘              └───────────────────────────────────────┘
                                               │
                                               │ plot_id (FK)
                                               ▼
                                      ┌───────────────────────┐
                                      │    chapter_plots      │
                                      │  chapter_id | plot_id │
                                      │  action | notes       │
                                      └───────────────────────┘

┌───────────────────────┐              ┌───────────────────────────────────────┐
│     characters        │              │          world_settings               │
│  project_id | name    │              │  project_id | category | title        │
│  role | description   │              │  content | notes                     │
└───────────────────────┘              └───────────────────────────────────────┘

┌───────────────────────┐              ┌───────────────────────────────────────┐
│     task_status       │              │          agent_messages               │
│  project_id | task_type│              │  project_id | from_agent | to_agent  │
│  chapter | agent_id   │              │  type | priority | content | status   │
│  status | retry_count │              └───────────────────────────────────────┘
└───────────────────────┘

┌───────────────────────┐              ┌───────────────────────────────────────┐
│   chapter_versions    │              │          anti_patterns                │
│  project_id | chapter │              │  code | category | pattern | severity │
│  version | content    │              │  description | alternatives          │
│  created_by | review_id│             └───────────────────────────────────────┘
└───────────────────────┘
```

---

## 七、关键数据流转场景

### 场景1：新章节创作

```
1. Dispatcher 发现 planned 状态章节
   → chapters.status = planned
   → instructions 存在

2. Dispatcher spawn Author(create)
   → task_status: {task_type: create, agent_id: author, status: running}

3. Author 读取数据
   → chapter_state(上一章): 数值状态
   → instructions: 写作指令
   → characters, world_settings, pending_plots: 设定
   → anti_patterns: 避坑指南

4. Author 创作
   → save_draft: chapters.content 更新
   → chapter_versions: 自动创建版本记录

5. Author 提交
   → update_chapter review: chapters.status = review
   → task_complete: task_status.status = completed

6. Dispatcher 发现 review 状态
   → spawn Editor(review)

7. Editor 质检
   → 通过: add_review + update_chapter reviewed + chapter_state 写入
   → 退回: add_review + update_chapter revision

8. Dispatcher 根据结果调度
   → reviewed: spawn Planner(publish)
   → revision: spawn Author(revise)
```

### 场景2：伏笔流转

```
1. Planner 创建伏笔
   → add_plot: plot_holes 新增记录
   → {code, type, description, planted_chapter, planned_resolve_chapter}

2. Planner 创建指令时关联伏笔
   → create_instruction: plots_to_plant=['P001'], plots_to_resolve=['L002']
   → validate_data: 检查伏笔是否存在

3. Author 创作时处理伏笔
   → pending_plots: 读取待处理伏笔
   → verify_plots: 验证伏笔是否正确处理

4. Editor 质检时验证伏笔
   → verify_plots: 返回 plot_deviation + plot_score_deduction
   → 偏差严重: send_message 提出异议

5. Planner 发布时同步
   → sync_plots: 更新 chapter_plots 关联表
   → resolve_plot: 更新 plot_holes.status = resolved
```

### 场景3：状态卡流转

```
1. Editor 质检通过后写入
   → chapter_state --set '<JSON>' "<summary>"
   → 提取本章结束时的数值状态

2. 下一章 Author 创作前读取
   → chapter_state <上一章>
   → 基于状态卡的数值继续创作

3. 状态卡内容
   {
     "数值类": {"金钱": 10000, "修为": 1500, "等级": "筑基初期"},
     "位置类": {"当前位置": "青云宗", "所属势力": "青云宗"},
     "伏笔类": {"已埋设": ["P001"], "已兑现": ["L002"]},
     "隐藏信息": {"匿名邮件": "周五17:50定时发送"}
   }
```

### 场景4：异议消息流转

```
1. Editor 发现伏笔问题
   → verify_plots 返回 plot_deviation
   → send_message editor planner ESCALATE <chapter> '<JSON>'
   → agent_messages: {from: editor, to: planner, type: ESCALATE, status: pending}

2. Dispatcher 调度 Planner 前
   → get_messages planner pending
   → 将待处理消息注入任务上下文

3. Planner 处理异议
   → 读取消息，调整规划
   → resolve_message <id> "已调整伏笔规划"

4. 消息状态变更
   → agent_messages.status = resolved
```

---

## 八、问题检查清单

### ✅ 工作流正确性

| 检查项 | 状态 | 说明 |
|--------|------|------|
| Dispatcher 调度优先级 | ✅ | revision > review > reviewed > planned |
| 熔断机制 | ✅ | 3次退回触发 abandon |
| 锁机制 | ✅ | lock.py 防止重叠 |
| 一致性检查 | ✅ | consistency_check.py 检查任务状态 |
| sessions_spawn 清理 | ✅ | cleanup="delete" |

### ✅ 数据读写权限

| Agent | 可创建 | 可更新 | 只读 |
|-------|--------|--------|------|
| Planner | chapters, instructions, plot_holes, characters, factions, world_settings, outlines | 同左 + chapter_plots(sync) | reviews |
| Author | chapter_versions(自动) | chapters(content, status) | instructions, characters, world_settings, plot_holes, anti_patterns |
| Editor | reviews, chapter_state, agent_messages | chapters(status) | instructions, characters, world_settings, plot_holes, anti_patterns |

### ✅ 状态流转

| 状态 | 触发 Agent | 动作 |
|------|-----------|------|
| planned → review | Author | save_draft + update_chapter review |
| review → reviewed | Editor | add_review(pass) + update_chapter reviewed |
| review → revision | Editor | add_review(fail) + update_chapter revision |
| revision → review | Author | save_draft + update_chapter review |
| reviewed → published | Planner | update_chapter published + sync_plots |

### ✅ 关键数据一致性

| 数据 | 一致性保障 |
|------|-----------|
| 伏笔 | validate_data 创建指令时校验，verify_plots 创作/质检时验证 |
| 状态卡 | Editor 通过后写入，Author 创作前读取 |
| 版本 | save_draft 自动创建 chapter_versions |
| 任务 | task_start/task_complete 配对，超时检测 |
