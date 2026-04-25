# 质检命令速查

## 数据读取命令

| 命令 | 用途 | 示例 |
|------|------|------|
| `current_project` | 获取当前项目ID | `python3 tools/db.py current_project` |
| `instruction` | 读取章节写作指令 | `python3 tools/db.py instruction <project> <chapter>` |
| `outlines` | 读取大纲 | `python3 tools/db.py outlines <project>` |
| `chapter_content` | 读取章节内容 | `python3 tools/db.py chapter_content <project> <chapter> draft` |
| `instructions` | 读取所有指令 | `python3 tools/db.py instructions <project>` |
| `world_settings` | 读取世界观 | `python3 tools/db.py world_settings <project>` |
| `characters` | 读取角色设定 | `python3 tools/db.py characters <project>` |
| `factions` | 读取势力设定 | `python3 tools/db.py factions <project>` |
| `pending_plots` | 读取待处理伏笔 | `python3 tools/db.py pending_plots <project>` |
| `chapter_state` | 读取/写入状态卡 | `python3 tools/db.py chapter_state <project> <chapter>` |

## 质检核心命令

| 命令 | 用途 | 示例 |
|------|------|------|
| `add_review` | 提交质检报告 | 见下方模板 |
| `update_chapter` | 更新章节状态 | `python3 tools/db.py update_chapter <project> <chapter> reviewed <words> <score>` |
| `task_complete` | 标记任务完成 | `python3 tools/db.py task_complete <task_id> true` |
| `verify_plots` | 验证伏笔处理（强制！） | `python3 tools/db.py verify_plots <project> <chapter>` |
| `check_chapter` | 自动检查章节 | `python3 tools/db.py check_chapter <project> <chapter>` |

## 问题模式命令

| 命令 | 用途 | 示例 |
|------|------|------|
| `anti_patterns` | 查看问题模式库 | `python3 tools/db.py anti_patterns --all` |
| `anti_patterns --enabled` | 只看启用的模式 | `python3 tools/db.py anti_patterns --enabled` |
| `context_rules` | 查看上下文规则 | `python3 tools/db.py context_rules` |

## 消息队列命令（向 Planner 提异议）

| 命令 | 用途 | 示例 |
|------|------|------|
| `send_message` | 发送异议消息 | `python3 tools/db.py send_message <project> editor planner ESCALATE <chapter> '<json>' high` |
| `get_messages` | 获取消息 | `python3 tools/db.py get_messages <project> editor pending 10` |
| `resolve_message` | 标记已处理 | `python3 tools/db.py resolve_message <id> "已处理"` |

---

## add_review 参数说明

**⚠️ 重要：参数顺序与文档不同！**

```bash
python3 tools/db.py add_review <project> <chapter> <score> <pass> "<summary>" <set> <logic> <poison> <text> <pace> [issues] [suggestions]
```

| 位置 | 参数 | 说明 |
|------|------|------|
| 1 | project | 项目 ID |
| 2 | chapter | 章节号 |
| 3 | **score** | 最终总分（五层打分 - 扣分）|
| 4 | pass | 通过标志（true/false 或 1/0）|
| 5 | summary | 质检摘要 |
| 6 | set | 设定一致性分数 |
| 7 | logic | 逻辑漏洞分数 |
| 8 | poison | 毒点检测分数 |
| 9 | text | 文字质量分数 |
| 10 | pace | 爽点钩子分数 |
| 11 | issues | 问题列表（JSON）|
| 12 | suggestions | 建议列表（JSON）|

**⚠️ 强制检查：pass 必须与 score 一致！**
- score ≥ 90 → pass 必须是 true
- score < 90 → pass 必须是 false

## 通过模板（≥90分）

```bash
# 1. 质检报告（最终总分 ≥ 90）
python3 tools/db.py add_review <project> <chapter> <final_score> true \
  "<summary>" <set> <logic> <poison> <text> <pace> \
  "[]" "[]"

# 2. 更新章节状态
python3 tools/db.py update_chapter <project> <chapter> reviewed <words> <final_score>

# 3. 写入状态卡
python3 tools/db.py chapter_state <project> <chapter> --set '<JSON>' "<summary>"

# 4. 任务完成
python3 tools/db.py task_complete <task_id> true
```

## 退回模板（<90分）

```bash
# 1. 质检报告（最终总分 < 90）
python3 tools/db.py add_review <project> <chapter> <final_score> false \
  "<summary>" <set> <logic> <poison> <text> <pace> \
  "[\"问题1\",\"问题2\"]" "[\"建议1\",\"建议2\"]"

# 2. 更新章节状态
python3 tools/db.py update_chapter <project> <chapter> revision

# 3. 任务完成
python3 tools/db.py task_complete <task_id> true
```

## 伏笔偏差严重时（向 Planner 提异议）

```bash
# 当 plot_score_deduction >= 20 时，发送 ESCALATE 消息
python3 tools/db.py send_message <project> editor planner ESCALATE <chapter> \
  '{"issue":"伏笔P003无法兑现","reason":"触发条件与当前剧情冲突","suggestion":"建议延后到第15章"}' high
```

---

## 退回建议格式

退回时，`suggestions` 必须包含：

```
1. 【硬伤定位】：具体段落、对话或数值矛盾处
2. 【违规原因】：哪一层出问题，如"触发反派降智"、"AI重复词汇过高"
3. 【修改建议】：具体的剧情微调方向
```

**示例**：
```
1. 【硬伤定位】：第3段"赵国栋威胁继承权"场景
2. 【违规原因】：伏笔兑现逻辑不通 - S004要求"赵婉清被羞辱"，实际触发对象是"继承权"
3. 【修改建议】：让赵国栋直接羞辱赵婉清本人，而非威胁继承权
```
