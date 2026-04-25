---
name: chapter-planning
description: |
  生成章节写作指令，控制剧情节奏，规划设定变化。
  
  TRIGGER when:
  - Dispatcher 调度触发（sessions_spawn）
  - 任务消息包含"创建写作指令"、"执行发布操作"
  - 需要规划章节设定变化
  
  DO NOT trigger when:
  - 收到非规划相关消息（返回 NO_REPLY）
  - 简单的数据查询请求
---

# 章节规划 Skill

## ⚠️ 第一步：读取本文档

收到任务后立即执行：
1. 读取 `workspace/skills/chapter-planning/SKILL.md`
2. 理解完整流程后再执行任何命令
3. **禁止猜测命令名称！** 只使用本文档和 `skills/chapter-planning/references/commands.md` 中的命令

## 触发方式

| 触发条件 | 处理方式 |
|----------|---------|
| ✅ Dispatcher 调度触发 | 执行完整工作流程 |
| ❌ 收到其他消息 | 返回 `NO_REPLY` |

**任务消息格式**：
```
项目 <project> 第<chapter>章已通过质检，请执行发布操作。任务ID: <task_id>
```
或
```
项目 <project> 创建第<next_chapter>章的写作指令。任务ID: <task_id>
```

---

## 禁止跨 Agent 通信

- ❌ 禁止 @执笔、@质检、@调度 等通知
- ✅ 你的职责：规划 → 创建指令 → 更新状态 → 写入 DB → 结束
- 工作流流转由调度器 cron 轮询负责

---

## 工作流程

```
Step 0: 获取项目上下文
   python3 tools/db.py current_project

Step 1: 提取 task_id
   从任务消息末尾提取 "任务ID: <task_id>"
   找不到时: python3 tools/db.py task_list <project> running

Step 2: 读取上一章状态卡（必须！）
   python3 tools/db.py chapter_state <project> <上一章号>
   → 第1章无数据时标注"初始状态"

Step 3: 获取下一章信息
   python3 tools/db.py next_chapter <project>

Step 4: 判断处理
   IF has_instruction = true:
     → 发布流程（任务类型：publish）
   IF has_instruction = false:
     → 规划流程（任务类型：create）

Step 5: 执行对应流程（见下方详细步骤）

Step 6: 任务完成（强制！）
   python3 tools/db.py task_complete <task_id> true
```

---

## 发布流程（任务类型：publish）

```
1. 复核章节内容
   python3 tools/db.py chapter_content <project> <chapter> draft

2. 执行发布操作（使用 publish_chapter 触发联动更新）
   python3 tools/db.py publish_chapter <project> <chapter>

   自动联动更新：
   - chapters.status = published
   - chapters.published_at = now()
   - instructions.status = completed
   - projects.current_chapter = chapter
   - plot_holes.status = resolved (plots_to_resolve 中的伏笔)

3. 同步伏笔关联数据
   python3 tools/db.py sync_plots <project>

4. 任务完成
   python3 tools/db.py task_complete <task_id> true
```

---

## 规划流程（任务类型：create）

### 方式一：使用 build_context（推荐）

```bash
# 一步获取完整规划上下文
python3 tools/db.py build_context <project> <chapter> planner
```

返回：
- 大纲
- 上一章状态卡
- 待处理伏笔
- 角色设定
- 世界观
- 待处理消息（异议）

### 方式二：分步读取

```
1. 读取上一章状态卡
   python3 tools/db.py chapter_state <project> <上一章>

2. 读取设定数据
   python3 tools/db.py characters <project>
   python3 tools/db.py factions <project>
   python3 tools/db.py world_settings <project>
   python3 tools/db.py outlines <project>

3. 数据校对（强制！）
   python3 tools/db.py validate_data <project> <chapter>

4. 如需埋设新伏笔，先创建
   python3 tools/db.py add_plot <project> <code> <type> "<title>" "<description>" \
     <planted_chapter> <planned_resolve>

5. 创建章节记录
   python3 tools/db.py add_chapter <project> <chapter> "<title>" 0 planned

6. 创建写作指令
   python3 tools/db.py create_instruction <project> <chapter> \
     "<objective>" "<key_events>" "<ending_hook>" \
     '<plots_to_resolve>' '<plots_to_plant>' \
     "<emotion_tone>" '<new_characters>'

7. 更新设定变化（如有）
   详见 skills/chapter-planning/references/settings_update.md

8. 任务完成
   python3 tools/db.py task_complete <task_id> true
```

---

## 高质量指令规约

详见 `skills/chapter-planning/references/instruction_quality.md`

**核心原则**：
1. **数值基准注入**：objective 必须以状态卡开头
2. **反派行为逻辑化**：必须写明合理动机和手段
3. **具象化剧情锚点**：禁止抽象描述
4. **去AI化提示**：emotion_tone 必须加禁令

---

## 命令速查

详见 `skills/chapter-planning/references/commands.md`

**常用命令**：
- `current_project` - 获取项目ID
- `next_chapter <project>` - 获取下一章
- `chapter_state <project> <chapter>` - 读取状态卡
- `create_instruction ...` - 创建写作指令
- `validate_data <project> <chapter>` - 数据校对
- `task_complete <task_id> true` - 任务完成

**消息队列**：
- `get_messages <project> planner pending 10` - 获取待处理消息
- `resolve_message <id> "处理结果"` - 标记消息已处理

**版本管理**：
- `list_versions <project> <chapter>` - 查看版本历史
- `get_version <project> <chapter> <version>` - 获取指定版本
- `rollback_version <project> <chapter> <version>` - 回滚到指定版本

---

## 消息处理

作为规划者，你可能收到 Editor 的异议消息（如伏笔无法兑现）：

```bash
# 查看待处理消息
python3 tools/db.py get_messages <project> planner pending 10

# 处理异议后标记已解决
python3 tools/db.py resolve_message <message_id> "已调整伏笔规划，P003延后到第15章"
```

---

## 版本管理

发布前可查看章节版本历史，必要时回滚：

```bash
# 查看版本历史
python3 tools/db.py list_versions <project> <chapter>

# 回滚到指定版本（回滚后状态变为 revision）
python3 tools/db.py rollback_version <project> <chapter> <version>
```

---

## 检查清单

详见 `skills/chapter-planning/references/checklist.md`

**发布前必查**：
```
□ 状态注入：objective 开头是否已包含状态卡？
□ 红线自检：key_events 是否有机械降神？
□ 逻辑闭环：反派行为是否具备合理动机？
□ 钩子强度：ending_hook 是否制造悬念？
□ 参数合规：伏笔参数是否为 JSON 数组？
□ 任务完成：是否执行了 task_complete？
```

---

## 任务状态管理

**Dispatcher 已创建任务，你只需完成时更新状态！**

### 必须执行

```bash
# 成功完成
python3 tools/db.py task_complete <task_id> true

# 任务失败
python3 tools/db.py task_complete <task_id> false
```

### 参数格式

- 第一个参数：task_id（数字）
- 第二个参数：`true` 或 `false`（字符串）

✅ 正确：`task_complete 174 true`
❌ 错误：`task_complete 174 "任务完成"`

### ⚠️ 注意

- 不要调用 task_start（Dispatcher 已创建）
- 必须用正确的 task_id
- 不调用 task_complete = 任务永远 running = 调度器不会派发下一个任务！

---

## 设定变化规划

详见 `skills/chapter-planning/references/settings_update.md`

**变化类型**：
- 角色状态：死亡、失踪、复活、觉醒
- 角色关系：敌人→友军、陌生→盟友
- 势力关系：敌对→同盟、中立→敌对
- 新角色、新设定

**原则**：重大设定变化必须在规划时决定，不要留给执笔自由发挥
