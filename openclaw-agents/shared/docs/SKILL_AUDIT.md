# Agent SKILL 文件检查报告

## 检查日期：2026-04-06

---

## 一、SKILL 文件概览

| Agent | SKILL 文件 | 状态 |
|-------|-----------|------|
| Dispatcher | skills/dispatcher/SKILL.md | ✅ 存在 |
| Planner | skills/chapter-planning/SKILL.md | ✅ 存在 |
| Planner | skills/plot-tracking/SKILL.md | ✅ 存在 |
| Planner | skills/worldbuilding/SKILL.md | ✅ 存在 |
| Author | skills/novel-writing/SKILL.md | ✅ 存在 |
| Editor | skills/quality-review/SKILL.md | ✅ 存在 |
| Scout | skills/market-analysis/SKILL.md | ✅ 存在 |
| Secretary | skills/daily-report/SKILL.md | ✅ 存在 |
| Architect | 无 | ⚠️ 缺失 |

---

## 二、各 Agent SKILL 检查详情

### 1. Dispatcher ✅ 已更新

**文件**：`dispatcher/workspace/skills/dispatcher/SKILL.md`

**检查项**：
- ✅ 调度流程完整（Step 0-6）
- ✅ 状态机定义清晰
- ✅ 熔断条件明确（≥3次退回）
- ✅ 任务命令正确（task_start, task_complete, task_timeout）
- ✅ 调度动作表清晰
- ⚠️ 缺少消息分发逻辑（pending messages）

**需更新**：
- 添加 Step 4.5：检查待处理消息并分发

---

### 2. Planner - chapter-planning ⚠️ 需更新

**文件**：`planner/workspace/skills/chapter-planning/SKILL.md`

**检查项**：
- ✅ 工作流程完整（发布流程 + 规划流程）
- ✅ 命令基本正确
- ✅ 任务管理正确
- ⚠️ 缺少消息队列命令（get_messages, resolve_message）
- ⚠️ 缺少版本管理命令（list_versions, rollback_version）
- ⚠️ 缺少 increment_retry 命令

**需更新**：
- 添加消息队列相关命令到命令速查
- 添加版本管理说明（发布前可回滚）

---

### 3. Planner - plot-tracking ✅ 已更新

**文件**：`planner/workspace/skills/plot-tracking/SKILL.md`

**检查项**：
- ✅ 命令正确（add_plot, resolve_plot, sync_plots, pending_plots）
- ✅ 同步时机说明
- ✅ 格式示例清晰

---

### 4. Author ✅ 已更新

**文件**：`author/workspace/skills/novel-writing/SKILL.md`

**检查项**：
- ✅ 工作流程完整（创作模式 + 修改模式）
- ✅ Step 0.5 读取问题模式库
- ✅ Step 6 verify_plots 自查
- ✅ Step 8 check_chapter 自动检查
- ✅ 禁止跨 Agent 通信
- ✅ 权限说明（无 add_plot/resolve_plot）
- ✅ references/commands.md 更新

---

### 5. Editor ✅ 已更新

**文件**：`editor/workspace/skills/quality-review/SKILL.md`

**检查项**：
- ✅ 五层审校流程完整
- ✅ Step 0.5 读取问题模式库（强制）
- ✅ Step 6 check_chapter 自动检查
- ✅ Step 6.5 verify_plots 伏笔验证（强制）
- ✅ Step 10 伏笔偏差异议
- ✅ 禁止事项更新
- ✅ references/commands.md 更新

---

### 6. Scout ✅ 基本正确

**文件**：`scout/workspace/skills/market-analysis/SKILL.md`

**检查项**：
- ✅ 工作流程清晰
- ✅ 命令正确（add_market_report, market_reports）
- ✅ 分析原则明确

---

### 7. Secretary ✅ 基本正确

**文件**：`secretary/workspace/skills/daily-report/SKILL.md`

**检查项**：
- ✅ 工作流程清晰
- ✅ 命令正确（stats, chapters, reviews, health_check）
- ✅ 日报格式说明

---

### 8. Architect ⚠️ 缺失 SKILL

**问题**：没有 SKILL.md 文件

**当前状态**：
- 有 TOOLS.md 定义工具
- 有 WORKFLOW.md 定义工作流
- skills/ 目录为空

**建议**：创建 `skills/diagnosis/SKILL.md`

---

## 三、工具命令与 SKILL 对比

### Dispatcher

| 工具命令 | SKILL 中提及 | 状态 |
|----------|-------------|------|
| health_check | ✅ | 一致 |
| chapters | ✅ | 一致 |
| next_chapter | ✅ | 一致 |
| reviews | ✅ | 一致 |
| sync_plots | ✅ | 一致 |
| stats | ✅ | 一致 |
| pending_plots | ✅ | 一致 |
| instruction | ✅ | 一致 |
| task_start | ✅ | 一致 |
| task_complete | ✅ | 一致 |
| task_list | ✅ | 一致 |
| task_reset | ✅ | 一致 |
| task_timeout | ✅ | 一致 |
| send_message | ⚠️ 未提及 | 需更新 |
| get_messages | ⚠️ 未提及 | 需更新 |
| resolve_message | ⚠️ 未提及 | 需更新 |

### Planner

| 工具命令 | SKILL 中提及 | 状态 |
|----------|-------------|------|
| current_project | ✅ | 一致 |
| chapter_state | ✅ | 一致 |
| next_chapter | ✅ | 一致 |
| chapter_content | ✅ | 一致 |
| update_chapter | ✅ | 一致 |
| sync_plots | ✅ | 一致 |
| characters | ✅ | 一致 |
| factions | ✅ | 一致 |
| world_settings | ✅ | 一致 |
| outlines | ✅ | 一致 |
| validate_data | ✅ | 一致 |
| add_plot | ✅ | 一致 |
| add_chapter | ✅ | 一致 |
| create_instruction | ✅ | 一致 |
| task_complete | ✅ | 一致 |
| get_messages | ⚠️ 未提及 | 需更新 |
| resolve_message | ⚠️ 未提及 | 需更新 |
| list_versions | ⚠️ 未提及 | 需更新 |
| rollback_version | ⚠️ 未提及 | 需更新 |
| increment_retry | ⚠️ 未提及 | 需更新 |

### Author

| 工具命令 | SKILL 中提及 | 状态 |
|----------|-------------|------|
| chapters | ✅ | 一致 |
| next_chapter | ✅ | 一致 |
| chapter_content | ✅ | 一致 |
| save_draft | ✅ | 一致 |
| update_chapter | ✅ | 一致 |
| instruction | ✅ | 一致 |
| reviews | ✅ | 一致 |
| characters | ✅ | 一致 |
| world_settings | ✅ | 一致 |
| pending_plots | ✅ | 一致 |
| chapter_state | ✅ | 一致 |
| verify_plots | ✅ | 一致 |
| check_chapter | ✅ | 一致 |
| anti_patterns | ✅ | 一致 |
| task_complete | ✅ | 一致 |
| task_list | ✅ | 一致 |

### Editor

| 工具命令 | SKILL 中提及 | 状态 |
|----------|-------------|------|
| chapters | ✅ | 一致 |
| chapter_content | ✅ | 一致 |
| update_chapter | ✅ | 一致 |
| add_review | ✅ | 一致 |
| reviews | ✅ | 一致 |
| check_chapter | ✅ | 一致 |
| verify_plots | ✅ | 一致 |
| instructions | ✅ | 一致 |
| instruction | ✅ | 一致 |
| characters | ✅ | 一致 |
| world_settings | ✅ | 一致 |
| factions | ✅ | 一致 |
| outlines | ✅ | 一致 |
| pending_plots | ✅ | 一致 |
| anti_patterns | ✅ | 一致 |
| context_rules | ✅ | 一致 |
| chapter_state | ✅ | 一致 |
| send_message | ✅ | 一致 |
| get_messages | ✅ | 一致 |
| resolve_message | ✅ | 一致 |
| task_complete | ✅ | 一致 |

---

## 四、需要更新的 SKILL 文件

### 1. Dispatcher SKILL.md

需添加消息分发逻辑：

```markdown
### Step 4.5: 检查待处理消息（可选）

```bash
python3 tools/db.py get_messages <project> planner pending 5
```

如果存在待处理消息（如 Editor 提出的伏笔异议），在调度 Planner 时将消息内容注入任务上下文。
```

### 2. Planner chapter-planning SKILL.md

需添加消息队列和版本管理：

```markdown
## 消息处理

作为规划者，你可能收到 Editor 的异议消息：

```bash
# 查看待处理消息
python3 tools/db.py get_messages <project> planner pending 10

# 处理异议后标记已解决
python3 tools/db.py resolve_message <message_id> "已调整伏笔规划"
```

## 版本管理

发布前可查看章节版本历史，必要时回滚：

```bash
# 查看版本历史
python3 tools/db.py list_versions <project> <chapter>

# 回滚到指定版本
python3 tools/db.py rollback_version <project> <chapter> <version>
```
```

### 3. Architect SKILL.md

需创建新文件：

```markdown
---
name: system-diagnosis
description: |
  系统诊断与优化 Agent，负责检查工厂健康状态、诊断问题、提供优化建议。
  
  TRIGGER when:
  - 用户询问系统状态
  - 需要诊断数据问题
  - 需要优化建议
  
  DO NOT trigger when:
  - 与系统无关的创作任务
---

# 系统诊断 Skill

## 工作流程

1. 健康检查
   python3 tools/db.py health_check

2. 项目统计
   python3 tools/db.py stats <project>

3. 问题分析
   python3 tools/db.py pattern_stats

4. 输出诊断报告
```

---

## 五、总结

| Agent | SKILL 状态 | 需要更新 |
|-------|-----------|----------|
| Dispatcher | ✅ 完整 | ⚠️ 添加消息分发 |
| Planner (chapter-planning) | ⚠️ 部分缺失 | ⚠️ 添加消息/版本 |
| Planner (plot-tracking) | ✅ 完整 | 无 |
| Planner (worldbuilding) | ? | 待检查 |
| Author | ✅ 完整 | 无 |
| Editor | ✅ 完整 | 无 |
| Scout | ✅ 完整 | 无 |
| Secretary | ✅ 完整 | 无 |
| Architect | ❌ 缺失 | 需创建 |

**核心流程相关**：Dispatcher 和 Planner 的 SKILL 需要更新以包含新增的消息队列和版本管理命令。
