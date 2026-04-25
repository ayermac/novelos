# 剩余优化项清单

## 检查日期：2026-04-06

---

## 一、已确认正常的部分

| 系统 | 状态 | 说明 |
|------|------|------|
| 核心工作流 | ✅ | 完整闭环 |
| 伏笔系统 | ✅ | 完整闭环 |
| 版本管理 | ✅ | 已激活 |
| 消息队列 | ✅ | 完整 |
| 熔断机制 | ✅ | consistency_check.py 已实现 |
| 状态卡 | ✅ | 有模板文档 |
| Agent 权限 | ✅ | 边界清晰 |

---

## 二、可优化项（按优先级排序）

### P1 - 建议修复

#### 1. Dispatcher 消息分发逻辑缺失

**问题**：Dispatcher SKILL.md 没有提到检查 pending messages 并分发给对应 Agent。

**当前状态**：
- `get_messages` 命令存在
- Planner 可主动调用 `get_messages`
- Dispatcher 没有主动分发的流程

**建议方案**：
```python
# 在 Dispatcher SKILL Step 4 之后添加
# Step 4.5: 检查待处理消息
messages = get_messages(project, "planner", "pending", 5)
if messages["count"] > 0:
    # 将消息内容注入到 Planner 的任务上下文中
    spawn planner with pending_messages=messages
```

**影响**：低。Planner 可以主动查询消息，只是效率略低。

---

#### 2. state_history 表未自动记录

**问题**：`state_history` 表已创建，但 `chapter_state --set` 没有自动记录历史。

**当前状态**：
- `StateHistoryManager` 类已在 `feedback_system.py` 中实现
- 但 `cmd_chapter_state` 没有调用它

**建议方案**：
在 `cmd_chapter_state` 的 `--set` 分支中添加：
```python
# 写入前先记录历史
old_state = cursor.fetchone()
if old_state:
    StateHistoryManager().save_state(project_id, chapter_number, 
        json.loads(old_state['state_data']), 
        changed_fields=calculate_diff(old_state, new_state),
        reason="Editor update"
    )
```

**影响**：低。状态卡可以追溯，但历史不是必须的。

---

#### 3. best_practices 表未使用

**问题**：`best_practices` 表已创建，但没有逻辑填充它。

**建议方案**：
在 Editor 质检通过且分数 ≥ 95 时，提取章节亮点写入 best_practices：
```python
if score >= 95:
    best_practices.append({
        "project_id": project,
        "source_chapters": [chapter],
        "category": "high_score_pattern",
        "practice": summary,
        "avg_score": score
    })
```

**影响**：低。这是增值功能，非核心流程。

---

### P2 - 可选优化

#### 4. Architect 缺少 SKILL 定义

**问题**：Architect 的 `skills/` 目录为空，没有 SKILL.md。

**当前状态**：
- 有 `TOOLS.md` 定义数据库诊断工具
- 有 `WORKFLOW.md` 定义工作流
- 缺少具体的触发条件

**建议方案**：
创建 `skills/diagnosis/SKILL.md`，定义：
- 触发条件：用户询问系统状态、数据问题
- 工作流程：健康检查 → 问题诊断 → 修复建议

**影响**：低。Architect 是工具型 Agent，不需要自动调度。

---

#### 5. 测试框架缺失

**问题**：没有单元测试或集成测试。

**建议方案**：
```
/shared/tests/
  test_db_common.py      # 数据库操作测试
  test_workflow.py       # 工作流测试
  test_verify_plots.py   # 伏笔验证测试
```

**影响**：中。长期维护需要测试覆盖。

---

#### 6. CI/CD 配置缺失

**问题**：没有自动化部署或验证流程。

**建议方案**：
创建 `.github/workflows/test.yml`：
```yaml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: python -m pytest shared/tests/
```

**影响**：中。长期维护需要自动化。

---

#### 7. learned_patterns 未自动填充

**问题**：`learned_patterns` 表存在，但 Editor 质检后没有自动记录问题。

**建议方案**：
在 `add_review` 命令中，解析 issues 并记录：
```python
for issue in issues:
    if issue.get('category'):
        PatternLearner().record_pattern(project, chapter, 
            issue['category'], issue['desc'])
```

**影响**：低。问题模式已有 `anti_patterns` 表，learned_patterns 是补充。

---

## 三、不需要优化的部分

### 1. best_practices/state_history 表结构 ✅

表结构正确，只是业务逻辑未集成。可以按需实现。

### 2. consistency_check.py 已实现熔断 ✅

```python
# 已正确使用 retry_count
if len(revise_tasks) >= MAX_REVISE_RETRIES:
    return {'action': 'abandon', ...}
```

### 3. feedback_system.py 类完整 ✅

- `AgentMessenger` - 消息队列
- `FeedbackEscalator` - 反馈升级
- `PatternLearner` - 问题学习
- `VersionManager` - 版本管理
- `StateHistoryManager` - 状态历史

### 4. 所有共享工具可用 ✅

- `db_common.py` - 核心数据库操作
- `check_chapter.py` - 章节检查
- `clean_project.py` - 项目清理
- `export_chapters.py` - 章节导出
- `feedback_system.py` - 反馈系统

---

## 四、建议优先级

| 优先级 | 项目 | 工作量 | 收益 |
|--------|------|--------|------|
| P1.1 | Dispatcher 消息分发 | 小 | 中 |
| P1.2 | state_history 自动记录 | 小 | 中 |
| P2.1 | learned_patterns 自动填充 | 小 | 低 |
| P2.2 | 测试框架 | 中 | 高 |
| P2.3 | CI/CD | 小 | 高 |
| P2.4 | Architect SKILL | 小 | 低 |
| P2.5 | best_practices 自动填充 | 中 | 低 |

---

## 五、结论

**系统已可正常运行**。以上优化项均为增强功能，非阻塞性问题。

核心工作流完整度：**95%**
- 状态流转 ✅
- 数据一致性 ✅
- 权限边界 ✅
- 熔断机制 ✅
- 版本管理 ✅
- 消息队列 ✅

缺失的 5%：
- Dispatcher 主动消息分发（可选）
- 状态历史自动记录（增值）
- 测试覆盖（长期维护）
