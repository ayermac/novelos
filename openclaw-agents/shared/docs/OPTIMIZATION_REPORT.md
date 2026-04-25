# 系统优化检查报告

## 检查日期：2026-04-06

---

## ✅ 已完成

### 1. 数据库表结构
- [x] 所有项目相关表都有 `project_id`
- [x] `agent_messages` 已添加 `project_id`
- [x] 索引完备

### 2. 权限矩阵
- [x] Author 权限收缩（移除 add_plot/resolve_plot/add_character）
- [x] Editor 添加消息队列命令
- [x] Dispatcher 添加消息队列命令
- [x] verify_plots 增强（plot_deviation + plot_score_deduction）

### 3. 文档
- [x] PERMISSIONS.md 权限文档
- [x] TABLE_ANALYSIS.md 表分析文档
- [x] Editor SKILL.md 更新（Step 6.5 伏笔验证）

---

## ⚠️ 需要优化

### 1. Planner 缺少消息队列命令

**问题**：Planner 作为规划的核心角色，应该能接收 Editor 的异议消息。

**当前状态**：Planner 使用 `dict(ALL_COMMANDS)` 拥有所有命令，但没有在 HELP 中列出消息命令。

**建议**：更新 Planner 的 HELP 文档，添加消息队列命令说明。

```python
# 在 HELP 中添加：
  消息队列:  get_messages / resolve_message
```

---

### 2. Editor 的 commands.md 需要更新

**问题**：`references/commands.md` 缺少新增的命令。

**缺少的命令**：
- `anti_patterns` - 查看问题模式库
- `context_rules` - 查看上下文规则
- `send_message` - 发送异议消息
- `get_messages` - 获取消息
- `resolve_message` - 标记消息已处理

**文件位置**：`/agents/editor/workspace/skills/quality-review/references/commands.md`

---

### 3. check_chapter.py 缺少命令入口

**问题**：`check_chapter` 函数在 `db_common.py` 中存在，但 Editor 的 db.py 已添加，需确认其他 Agent 是否需要。

**当前状态**：
- Editor ✅ 已添加
- Author ❌ 未添加（Author 应该有自查能力）
- Planner ❌ 未添加（可选）

**建议**：为 Author 添加 `check_chapter` 命令，用于创作后自查。

---

### 4. Author 缺少问题模式库访问

**问题**：Author 在创作前应该读取问题模式库（anti_patterns）作为"避坑指南"，但 Author 的 db.py 没有这个命令。

**当前状态**：Author 的 SKILL.md Step 0.5 提到要读取问题模式库，但 db.py 没有命令。

**建议**：为 Author 添加：
- `anti_patterns` - 查看问题模式库
- `check_chapter` - 自查章节

---

### 5. 数据库缺少初始数据

**问题**：当前数据库没有项目数据（projects/chapters/instructions 都是 0）。

**影响**：系统需要初始化才能运行。

**建议**：创建初始化脚本或示例数据。

---

### 6. Architect Agent 角色定义不清

**问题**：用户提到 Architect 不参与工厂工作流程，但 `architect/workspace/` 目录存在。

**需要确认**：
- Architect 的实际职责是什么？
- 是否需要 db.py 访问权限？
- 工具路径 `tools/db.py` 是否存在？

---

### 7. init_db.sql 与实际 schema 不同步

**问题**：`init_db.sql` 中的 `agent_messages` 表没有 `project_id` 列，但数据库已升级添加。

**影响**：如果重新初始化数据库，会丢失 `project_id` 列。

**建议**：更新 `init_db.sql` 文件。

---

## 🔧 执行计划

### ✅ 已完成（2026-04-06）

1. [x] 更新 `init_db.sql` 中的 `agent_messages` 表定义（添加 project_id）
2. [x] 为 Author 添加 `anti_patterns` 和 `check_chapter` 命令
3. [x] 更新 Editor 的 `commands.md` 参考文档
4. [x] 为 Planner 添加消息队列命令到 HELP 文档

### 优先级 P1（建议修复）

5. [ ] 创建项目初始化脚本或示例数据

### 优先级 P2（待确认）

6. [ ] 确认 Architect 的角色和工具需求
7. [ ] 考虑是否为其他 SKILL.md 文件更新命令列表
