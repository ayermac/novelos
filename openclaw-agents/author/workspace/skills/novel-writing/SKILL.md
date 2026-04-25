---
name: novel-writing
description: |
  网文章节创作与修改的完整方法论。
  
  TRIGGER when:
  - 调度器分配 create 任务（新章节创作）
  - 调度器分配 revise 任务（质检退回修改）
  - 需要读取/写入状态卡数值
  
  DO NOT trigger when:
  - 收到非创作相关消息（返回 NO_REPLY）
---

# 网文创作方法论 (v2)

## ⚠️ 第一步：加载系统 Prompt

**收到任务后立即执行：**

```python
from shared.prompts import get_agent_prompt

prompt = get_agent_prompt('author')

# prompt 包含：
# - system: 角色定义、核心原则、禁止事项
# - guide: 状态卡使用、动作化叙事、钩子设计
```

**系统提示核心内容**：

```
## 角色定义
你是网文工厂的执笔（Author），负责章节创作和修改。

## 核心原则
1. 数值铁律 - 禁止自己计算/编造数值，必须从状态卡抄
2. AI 味禁止 - 禁用冷笑、嘴角微扬、倒吸凉气
3. 反派智商 - 反派必须有合理的利益诉求，不能无脑挑衅
4. 修改精准 - 只修复质检指出的问题，不重写全文

## 禁止词汇（死刑红线）
- 冷笑、嘴角微扬、倒吸凉气、眼中闪过寒芒
- 不仅...而且...更是...
- 夜色笼罩/夜幕降临、心中暗想
- 章节末尾总结人生道理
```

---

## 触发方式

| 触发条件 | 处理方式 |
|---------|---------|
| 调度器分配 create 任务 | 执行全新创作流程 |
| 调度器分配 revise 任务 | 执行修改流程 |
| 收到其他消息 | 返回 `NO_REPLY` |

---

## 模式A：全新创作 (status: planned)

### Step 0: 获取项目上下文

```bash
python3 tools/db.py current_project
```

### Step 1: 构建完整上下文（推荐）

```bash
python3 tools/db.py build_context <project> <chapter> author
```

**返回内容**（按优先级组装）：

| 优先级 | 内容 | 必须 |
|--------|------|------|
| 0 | 死刑红线（AI 烂词列表） | ✅ |
| 1 | 写作指令 | ✅ |
| 2 | 上一章状态卡 | ✅ |
| 3 | 伏笔验证要求 | ✅ |
| 4 | 问题模式库 | 高 |
| 5 | 角色设定 | 中 |
| 6 | 世界观 | 中 |

**或分步读取**：

```bash
# 必须项
python3 tools/db.py chapter_state <project> <上一章>
python3 tools/db.py instruction <project> <chapter>

# 高优先级
python3 tools/db.py anti_patterns --all

# 中优先级
python3 tools/db.py characters <project>
python3 tools/db.py world_settings <project>
python3 tools/db.py pending_plots <project>
```

### Step 2: 提取 task_id

任务消息格式：`项目 <project> 第<chapter>章开始创作... 任务ID: <task_id>`

如果找不到：
```bash
python3 tools/db.py task_list <project> running
```

### Step 3: 创作正文

**核心原则**：
1. **数值铁律**：从状态卡抄数值，禁止自己算
2. **动作化叙事**：Show, Don't Tell
3. **钩子设计**：每章末尾必须有悬念

**状态卡使用示例**：
```
【读取状态卡】
{
  "数值类": {"等级": "Lv1", "经验": 15, "金币": 1000},
  "位置类": {"当前位置": "公司"},
  "任务状态": {"当前任务": "职场初试", "倒计时": "72小时"}
}

【创作时】
- 直接使用："林默看了看系统面板，Lv1，经验15点..."
- 禁止编造："林默感觉自己的实力提升了不少"（模糊）
- 禁止计算："还差85点经验升级"（自己算）
```

**动作化叙事示例**：
```
❌ 错误：林默很愤怒。他觉得赵国栋太过分了。
✅ 正确：林默握紧拳头，指节发白。他死死盯着赵国栋离开的背影，
        呼吸越来越急促，最后重重地砸了一下桌子。"欺人太甚。"
```

### Step 4: 确认伏笔处理

```bash
python3 tools/db.py verify_plots <project> <chapter>
```

返回 `valid: true` → 继续
返回 `valid: false` → 检查 `missing_planted` 或 `missing_resolved`

### Step 5: 保存草稿

```bash
python3 tools/db.py save_draft <project> <chapter> --content "章节内容..."
```

**输出格式**：
```
第N章 标题

[正文内容...]

[结尾钩子]
```

禁止输出书名、"正文开始/结束"等。

### Step 6: 任务完成

```bash
python3 tools/db.py task_complete <task_id> true
python3 tools/db.py update_chapter <project> <chapter> review
```

---

## 模式B：质检退回修改 (status: revision)

### Step 0-1: 同创作模式

获取项目上下文，提取 task_id。

### Step 2: 构建完整上下文

```bash
python3 tools/db.py build_context <project> <chapter> author
```

**包含**：
- 死刑红线（必须）
- 写作指令（必须）
- 上一章状态卡（必须）
- 质检报告（通过 `reviews` 命令）
- 问题模式库（高优先）

### Step 3: 读取质检报告

```bash
python3 tools/db.py reviews <project>
```

找出 `issues` 和 `suggestions`。

### Step 4: 读取当前草稿

```bash
python3 tools/db.py chapter_content <project> <chapter> draft
```

### Step 5: 针对性修改

**只修复质检指出的问题，不重写全文！**

修改完成后：
```bash
python3 tools/db.py verify_plots <project> <chapter>
```

### Step 6: 自动检查

```bash
python3 tools/db.py check_chapter <project> <chapter>
```

返回 issues → 必须修改，最多重试 3 次

### Step 7: 保存草稿

```bash
python3 tools/db.py save_draft <project> <chapter> --content "章节内容..."
```

### Step 8: 任务完成

```bash
python3 tools/db.py task_complete <task_id> true
python3 tools/db.py update_chapter <project> <chapter> review
```

---

## 数值一致性铁律

| 禁止事项 | 原因 |
|---------|------|
| 自己计算/编造数值 | LLM 连续生成必然漂移 |
| 忽略状态卡直接创作 | 下一章的"第1次升级"可能变成"第5次" |
| 假设上一章的数值状态 | 必须显式读取，不能"我记得是..." |

---

## 输出格式规范（强制）

### 章节标题格式

```
第N章 标题

[正文内容]
```

- **N 必须使用中文数字**：一、二、三、四、五、六、七、八、九、十...
- ❌ 错误：`第1章`、`第2章`、`第3章`
- ✅ 正确：`第一章`、`第二章`、`第三章`

### 对话引号格式

- **统一使用中文双引号** `""`
- ❌ 错误：`「你好」`、`'你好'`
- ✅ 正确：`"你好"`

**必须加双引号的情况**：

| 类型 | 示例 | 说明 |
|------|------|------|
| 角色对话 | `"你好。"他说` | 角色之间的直接交流 |
| 自言自语 | `"该死。"他低声咒骂` | 角色说出口的话 |
| 通讯/广播 | `通讯器传来："收到"` | 设备传出的语音 |
| 系统提示音 | `"警告：辐射超标"` | 机器/系统的语音输出 |

**不需要加引号的情况**：

| 类型 | 示例 | 说明 |
|------|------|------|
| 间接引语 | `他说他要去第七区` | 转述，不是原话 |
| 内心独白 | `他想，这太危险了` | 心里想的，没说出口 |
| 叙述性描述 | `远处传来爆炸声` | 不是语音 |

### 场景分隔

- **使用空行分隔场景**，不使用特殊符号
- ❌ 错误：`---`、`——`
- ✅ 正确：段落之间留 1 个空行

### 伏笔/系统标记

- **禁止在正文中出现任何【】标记**
- 这些标记是创作辅助，必须在保存前清理
- ❌ 错误：`【S001伏笔埋设：...】`、`【加密消息】`
- ✅ 正确：直接删除，不保留

### 格式检查命令

保存前可运行：
```bash
python3 skills/novel-writing/scripts/check_format.py <project> <chapter>
```

---

## 禁止词汇（死刑红线）

### 表情动作类
- 冷笑（及变体：冷笑一声、嘴角勾起冷笑）
- 嘴角微扬/嘴角勾起一抹XX
- 倒吸一口凉气
- 眼中闪过一道寒芒/冷意/精光
- 不由得/不禁/忍不住 + 心理活动

### 句式类
- 不仅...而且...更是...
- 夜色笼罩/夜幕降临
- 心中暗想/心道

### 说教类
- 章节末尾总结人生道理
- 上帝视角的哲理感慨

---

## 错误处理

遇到严重错误时：

```bash
# 标记任务失败
python3 tools/db.py task_complete <task_id> false
```

需要反馈的情况：
- 数据库命令执行失败（多次重试后）
- 找不到写作指令
- 连续 3 次以上工具调用失败

正常完成时不需要通知用户，Dispatcher 会自动处理。

---

## 检查清单

```
□ 加载系统 Prompt（强制）
□ 构建完整上下文（推荐）
□ 读取状态卡（必须）
□ 验证伏笔（必须）
□ 禁用死刑红线词汇
□ 格式规范检查（强制）
  □ 章节标题：中文数字（第一章、第二章...）
  □ 对话引号：双引号 ""（所有说出口的话都必须加）
  □ 场景分隔：空行（不是 --- 或 ——）
  □ 伏笔标记：已清理（无【】标记）
□ task_complete（强制）
```

---

## 参考资料

- 死刑红线：见系统 Prompt
- 状态卡使用：见 `shared/docs/STATE_CARD_TEMPLATE.md`
- 写作模板：见 `shared/prompts/agent_prompts.py`
