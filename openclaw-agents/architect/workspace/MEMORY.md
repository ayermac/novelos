# MEMORY.md - 架构师的长期记忆

## Editor add_review 参数顺序错误修复（2026-04-08 晚）

### 问题发现

第14章质检报告未写入数据库，原因是 `add_review` 参数顺序与文档不符。

**文档说的**：
```
add_review <project> <chapter> <reviewer_id> <pass> <summary> ...
```

**实际代码**：
```python
project_id = args[0]
chapter_number = int(args[1])
score = int(args[2])  # 第3个参数是 score，不是 reviewer_id！
pass_arg = args[3]    # 第4个参数是 pass
summary = args[4]
setting_score = int(args[5])
...
```

**正确参数顺序**：
```
add_review <project> <chapter> <score> <pass> <summary> <set> <logic> <poison> <text> <pace> [issues] [suggestions]
```

### 问题 2：强制检查 pass 与 score 一致

代码中有强制检查：
```python
auto_pass = 1 if score >= 90 else 0
if pass_flag != auto_pass:
    print(json.dumps({"success": False, "error": "pass 参数与分数不匹配"...}))
    return
```

这意味着：
- score ≥ 90 → pass 必须是 true（或 1）
- score < 90 → pass 必须是 false（或 0）

### 修复内容

| 文件 | 修改 |
|------|------|
| `editor/workspace/skills/quality-review/SKILL.md` | Step 8 新增正确参数顺序、强制检查说明、避免重复扣分 |
| `editor/workspace/skills/quality-review/references/commands.md` | 修正 add_review 参数说明和模板 |

### 修正后的质检流程

```
Step 5: 自动检查 → check_chapter
  - issues: 每个 5-10 分扣分
  - warnings: 每个 2-5 分扣分
  - ⚠️ 字数警告不计入扣分（已在设定一致性中扣分）

Step 6: 伏笔验证 → plot_score_deduction

Step 8: 计算最终总分
  - 五层打分（已扣除字数偏差）
  - 减去伏笔扣分
  - 减去自动检查扣分（不含字数警告）
  
  最终总分 = 五层打分 - 伏笔扣分 - issues扣分 - warnings扣分

  pass = (最终总分 ≥ 90)
  score = 最终总分  # 不是五层打分！
```

### 第14章正确扣分计算

**五层打分**：
- 设定一致性：20 分（字数偏差 >30% 扣 5 分）
- 逻辑漏洞：25 分
- 毒点检测：20 分
- 文字质量：15 分
- 爽点钩子：11 分
- 总分：91 分

**自动检查**：
- issues: 0 个
- warnings: 4 个（字数警告 + 3个关键事件警告）
- 扣分：3 × 2 = 6 分（字数警告不计入）

**最终总分**：91 - 0 - 6 = 85 分（< 90，退回）

---

## Editor 伏笔扣分未计入最终总分修复（2026-04-08 晚）

### 问题发现
第14章质检：
- 五层打分：91 分（≥90，通过线）
- 伏笔验证扣分：5 分（多余埋设记录 S003）
- 最终应该：86 分（<90，退回）
- 实际提交：pass=true，score=91（错误通过）

### 根因分析

**Editor SKILL Step 8 缺失扣分计算**：

原流程：
```
五层打分 → 直接提交 pass/score
```

缺失：
1. 伏笔扣分（`plot_score_deduction`）
2. 自动检查 issues 扣分
3. 自动检查 warnings 扣分

### 修复内容

**editor/workspace/skills/quality-review/SKILL.md** Step 8 新增：

```markdown
**⚠️ 关键：计算最终总分**

最终总分 = 五层打分总分
         - 伏笔扣分（Step 6）
         - 自动检查 issues 扣分
         - 自动检查 warnings 扣分

**通过判断（基于最终总分）**：
- 最终总分 ≥ 90 且无单项不及格 → 通过
- 最终总分 < 90 → 退回

**扣分明细必须写入 issues**：
["伏笔验证扣分: 5分（多余埋设记录: S003）", ...]
```

**阶段2 新增伏笔逻辑硬伤 vs 数据错误区分**：

```markdown
⚠️ 伏笔逻辑硬伤 vs 数据错误：
- **伏笔逻辑硬伤**：触发对象错误、触发条件不满足 → 直接退回
- **数据错误**：chapter_plots 记录与指令不符 → 扣 5 分，不直接退回
```

### 第14章数据修复

**问题**：`chapter_plots` 表有错误的 `planted: S003` 记录

**原因**：S003 在第3章埋设，第6章已兑现，第14章不应该有埋设记录

**修复**：删除第14章的 S003 埋设记录

**修复后验证**：
```json
{
  "valid": true,
  "plot_score_deduction": 0,
  "issues": []
}
```

### 后续行动

第14章状态已回退为 `revision`，需要：
1. 重新派发 author 任务
2. Editor 重新质检（字数超标问题仍需修复）

---

## 对话引号规范化补充（2026-04-08 下午）- 第二轮修复

### 问题发现
第11-13章对话缺失引号问题：
- 第11章：10处引号，但有【】标记未清理
- 第12章：10处引号，格式正确
- 第13章：0处引号，所有对话未加引号

### 根因分析
1. **Author SKILL**：格式规范在 SKILL 后半部分，创作流程没有强制检查步骤
2. **Editor SKILL**：质检流程缺少格式检查项
3. **check_chapter.py**：自动检查工具缺少格式检查功能

### 修复操作

**1. 数据修复**
- 第11章：清理【】标记
- 第13章：手动修复 19 处对话引号

**2. 工具更新**

**check_chapter.py 新增检查项**：
- 【】标记检查（issues 级别）
- 「」引号检查（issues 级别）
- 章节标题编号格式检查（warnings 级别）
- 对话引号缺失警告（warnings 级别）

**Editor SKILL**：
- check_chapter 已包含格式检查，无需额外修改

**Author SKILL**：
- 已更新对话引号规范（必须加引号的情况详细说明）

### 长期预防机制

1. **Author 创作流程**：
   - Step 5 添加"格式规范检查"
   - 检查清单强制执行

2. **Editor 质检流程**：
   - check_chapter 自动检查格式问题
   - issues 级别问题必须修复

3. **格式检查工具**：
   - check_format.py 独立脚本（Author 用）
   - check_chapter.py 集成检查（Editor 用）

### 最终结果
- ✅ 第11章：【】标记已清理
- ✅ 第12章：格式正确
- ✅ 第13章：19 处对话引号已添加

---

## 对话引号规范化补充（2026-04-08 下午）

### 问题发现
第4、8、9、10章存在对话缺失引号问题：
- 第4章：系统语音、通讯器对话未加引号（2处）
- 第8章：路人对话、主角话、林素心通讯、霍沉的话未加引号（8处）
- 第9章：使用单引号而非双引号（20处）
- 第10章：使用单引号而非双引号（3处）

### 格式规范原则

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

### 修正操作

**1. 数据库章节内容修正**
- 第4章：+2处双引号（系统语音、通讯器）
- 第8章：+8处双引号（对话补全）
- 第9章：20处单引号→双引号
- 第10章：3处单引号→双引号

**2. Author SKILL 更新**
- 补充「对话引号格式」详细规范
- 新增"必须加双引号"和"不需要加引号"的情况表

**3. check_format.py 更新**
- 新增「缺失引号的对话」检测（检查说话动词后无引号的情况）

### 最终结果
- ✅ 全部 10 章对话格式统一为双引号 `""`
- ✅ 共 313 处对话，全部使用正确格式
- ✅ 无 `「」` 引号残留
- ✅ 无单引号对话残留

---

## 章节格式规范化（2026-04-08）

### 问题发现
检查 novel_003 全部 8 章内容，发现格式不一致问题：

| 问题类型 | 章节分布 | 严重程度 |
|---------|---------|---------|
| 章节标题编号 | 第2、3、5章用阿拉伯数字 | ⚠️ 中 |
| 对话引号 | 第2、3章用「」引号 | ⚠️ 中 |
| 场景分隔符 | 第2章用---，第3、4章用—— | ⚠️ 低 |
| 伏笔标记 | 第1、6、8章有残留【】标记 | ❌ 高 |
| 标题不一致 | 所有章节 DB 标题与内容首行不同 | ℹ️ 信息 |

### 修正操作

**1. 数据库章节内容修正**

执行脚本自动修正：
- 章节标题：阿拉伯数字 → 中文数字（第2、3、5章）
- 对话引号：「」 → ""（第2、3章）
- 场景分隔符：--- 和 —— → 空行（第2、3、4章）
- 伏笔标记：删除所有【】标记（第1、6、8章）

**2. Author SKILL 更新**

新增「输出格式规范（强制）」section：

```
### 章节标题格式
- N 必须使用中文数字：一、二、三、四、五...
- ❌ 错误：第1章、第2章
- ✅ 正确：第一章、第二章

### 对话引号格式
- 统一使用中文双引号 ""
- ❌ 错误：「你好」
- ✅ 正确："你好"

### 场景分隔
- 使用空行分隔场景，不使用特殊符号
- ❌ 错误：---、——
- ✅ 正确：段落之间留 1 个空行

### 伏笔/系统标记
- 禁止在正文中出现任何【】标记
- ❌ 错误：【S001伏笔埋设：...】
- ✅ 正确：直接删除，不保留
```

**3. 检查清单更新**

```
□ 格式规范检查（强制）
  □ 章节标题：中文数字
  □ 对话引号：双引号 ""
  □ 场景分隔：空行
  □ 伏笔标记：已清理
```

**4. 新增格式检查工具**

文件：`shared/tools/check_format.py`

用法：
```bash
python3 tools/check_format.py <project> <chapter>
```

检查项：
- 章节标题格式（中文数字）
- 对话引号格式（双引号）
- 场景分隔符（空行）
- 伏笔标记残留
- 连续空行
- 死刑红线词汇

### 修正结果

全部 8 章格式已统一，验证通过 ✅

### 统一格式标准

| 项目 | 标准 |
|------|------|
| 章节标题编号 | 中文数字（第一章、第二章...） |
| 对话引号 | 双引号 ""（标准网文格式） |
| 场景分隔 | 空行 |
| 伏笔标记 | 发布前必须清理 |

---

## state_history 状态历史记录（2026-04-06 晚）

### 问题发现
`state_history` 表已创建但从未使用，一直为空（0 条记录）。

### 原因分析
- Editor SKILL 只写入 `chapter_state`（当前状态），没有调用 `state_history`（历史记录）
- `feedback_system.py` 有相关代码，但不在主流程中

### 解决方案
**方案 A：在 `chapter_state` 更新时，同时写入 `state_history`**

修改文件：`shared/tools/db_common.py` 的 `cmd_chapter_state` 函数

实现逻辑：
1. 写入前获取旧状态
2. 计算变更字段（old vs new）
3. 写入 `chapter_state`（当前状态）
4. 写入 `state_history`（历史记录）

### state_history 表结构

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| project_id | TEXT | 项目 ID |
| chapter | INTEGER | 章节号 |
| state_json | TEXT | 完整状态 JSON |
| changed_fields | TEXT | 变更字段详情 |
| reason | TEXT | 变更原因 |
| created_at | TIMESTAMP | 创建时间 |

### 用途
- 状态变更审计
- AI 反馈学习
- 回溯问题定位

### 验证命令

```bash
# 查看状态历史
sqlite3 shared/data/novel_factory.db "SELECT * FROM state_history ORDER BY id DESC LIMIT 5"

# 查看当前状态
python3 tools/db.py chapter_state <project> <chapter>
```

---

## Dispatcher 越权修复（2026-04-06 晚）

### 问题发现
Dispatcher 在检测到"无 planned 状态章节"时，自行调用 `add_chapter` 创建章节，违反"只调度不越权"原则。

### 根因
1. Dispatcher 的 db.py 中导出了 `add_chapter` 命令
2. SKILL.md 没有明确禁止越权操作
3. LLM 看到流水线中断，主动"补位"创建章节

### 解决方案
**从代码层面移除越权命令**

修改文件：`dispatcher/workspace/tools/db.py`

移除的命令：
- `add_chapter` - 由 Planner 创建章节

### Dispatcher 允许的命令（修正后）

| 命令 | 用途 |
|------|------|
| health_check | 健康检查 |
| projects | 列出项目 |
| current_project | 获取当前项目 |
| chapters | 列出章节（只读） |
| next_chapter | 下一章信息 |
| reviews | 质检报告（只读） |
| sync_plots | 同步伏笔 |
| instruction | 读取指令（只读） |
| task_start | 开始任务 |
| task_complete | 完成任务 |
| task_list | 任务列表 |
| task_reset | 重置任务 |
| task_timeout | 超时检查 |
| stats | 项目统计 |
| pending_plots | 待处理伏笔 |
| send/get/resolve_message | 消息队列 |

### 禁止 Dispatcher 调用的命令

| 命令 | 归属 |
|------|------|
| add_chapter | Planner |
| create_instruction | Planner |
| save_draft | Author |
| add_review | Editor |

### 教训

**代码级约束 > 文档约束！**
- SKILL.md 的说明可能被 LLM 忽略或曲解
- 直接移除命令是最可靠的防线
- 每个 Agent 的 db.py 应只导出其职责范围内的命令

---

## 资产校验强化（2026-04-06）

### 核心问题
章节"写得好看但设定崩塌"——数值漂移、重复勒索等逻辑问题屡禁不止。

### 根因分析
1. Editor 只在质检通过后才写入状态卡，写入前没有校验
2. Author 没有强制输出资产变动明细
3. 状态卡是"参考"而非"强制约束"

### 解决方案
**强化 chapter_state 表的使用**——资产校验前置到质检阶段0。

### 校验原则

| 原则 | 说明 |
|------|------|
| 继承字段 | 上一章有、本章没提到的 → 必须继承（值不变） |
| 变动字段 | 本章明确提到变动的 → 校验等式 `前章值 + 变动 = 本章值` |
| 新增字段 | 本章新增的 → 直接记录 |
| 删除字段 | 上一章有、本章明确结束的 → 可删除（需说明原因） |

### 校验流程

```
质检阶段0：资产校验（最优先）
├── 读取上一章 state_data
├── 从章节内容提取本章数值变动
├── 执行校验（继承/变动/新增/删除）
├── 匹配 → 继续阶段1死刑检查
└── 不匹配 → 立即退回，总分 ≤ 60，不进后续审校
```

### 状态卡字段规范

```json
{
  "assets": {
    "credits": {"value": 300, "change": -200, "reason": "霍沉勒索"},
    "hp": {"value": 100, "change": 0, "reason": null}
  },
  "character_states": {
    "陈渊": {"location": "贫民窟", "status": "active"},
    "霍沉": {"location": "执法站", "status": "antagonist"}
  },
  "active_plots": ["P001", "L003"],
  "resolved_plots": [],
  "hidden_info": {
    "呼吸税勒索": "已发生"
  }
}
```

### 修改的文件

| 文件 | 改动 |
|------|------|
| editor/workspace/skills/quality-review/SKILL.md | 新增阶段0资产校验，更新状态卡模板 |
| shared/tools/db_common.py | 新增 `validate_state` 命令 |

### 新增命令

```bash
# 校验状态卡一致性
python3 tools/db.py validate_state <project> <chapter> '<current_state_json>'

# 迁移旧格式状态卡到新格式
python3 tools/migrate_state.py --dry-run [project_id]  # 预览
python3 tools/migrate_state.py --migrate [project_id]  # 执行
python3 tools/migrate_state.py --force [project_id]    # 强制覆盖
```

### 迁移脚本

位置：`architect/workspace/tools/migrate_state.py`

旧格式 → 新格式映射：

| 旧格式 | 新格式 | 说明 |
|--------|--------|------|
| `数值类.金钱` | `assets.credits` | 信用点 |
| `数值类.生命力` | `assets.hp` | 生命值 |
| `数值类.等级` | `character_states.主角.level` | 等级归角色 |
| `持有物品` | `assets.items` | 物品清单 |
| `位置类.当前位置` | `character_states.主角.location` | 位置归角色 |
| `伏笔类.已埋设` | `active_plots` | 活跃伏笔 |
| `伏笔类.已兑现` | `resolved_plots` | 已兑现伏笔 |
| `任务状态` | `hidden_info` | 任务信息 |
| `特殊状态` | `hidden_info` | 隐藏信息 |

---

## 通信架构重构（2026-04-02）

### 核心问题
所有 Agent 的 SKILL 中都存在 `@通知` 调用（如 `@质检`、`@总编`），导致 Agent 间直接通信，违反单一调度原则。

### 重构原则
**Dispatcher 是唯一通信出口。** Other Agent → 写 DB 结束。
```
Agent A 完成 → 写 DB（状态变化）→ Dispatcher cron 轮询检测 → Dispatcher 派发 Agent B
```

### 修改的文件

| Agent | 文件 | 改动 |
|-------|------|------|
| author | SOUL.md | 添加「通信铁律」section |
| author | novel-writing/SKILL.md | 移除 `@质检`，加入禁令 |
| editor | SOUL.md | 添加「通信铁律」section |
| editor | HEARTBEAT.md | 移除 `@秘书` |
| editor | quality-review/SKILL.md | 移除所有 `@通知` |
| planner | SOUL.md | 添加「通信铁律」section |
| planner | HEARTBEAT.md | 移除质检@通知描述 |
| planner | chapter-planning/SKILL.md | 移除 `@执笔` |
| dispatcher | SOUL.md | 添加通信架构图 |
| dispatcher | dispatcher/SKILL.md | Step 6 改为 DB 状态驱动 |

### 状态流转

```
planned → review → reviewed → published
                ↘ revision → review（循环）
```

### Dispatcher 调度优先级

| 优先级 | 条件 | 触 action |
|--------|------|-----------|
| P3 | planned + 有指令 | 执笔创作 |
| P4 | review + 有草稿 | 质检复核 |
| P5 | reviewed | 总编发布 |
| P6 | revision | 执笔修改 |
| P7 | 无下一章指令 | 总编规划 |

---

## chapter_state 数值一致性系统

### 核心的问题
LLM 连续生成 4000+ 字时数值必然漂移。没有跨章节的数据持久化。

### 解决方案
通用 JSON 表，不硬编码字段。每章结束时提取数值写入 DB，下一章创作前注入。

### 表结构

| 字段 | 类型 | 说明 |
|------|------|------|
| project_id | TEXT | 项目 ID |
| chapter_number | INTEGER | 章节号 |
| state_data | TEXT | JSON 格式的数值状态 |
| summary | TEXT | 人类可读摘要 |

### 工作流

```
质检通过 N → 写 chapter_state(N)
总编创建 N+1 指令 → 读 chapter_state(N-1) → 注入状态卡
执笔创作 N+1 → 读状态卡 → 数值一致性有了保障
质检通过 N+1 → 写 chapter_state(N+1)（循环）
```

### SKILL 集成

| Agent | SKILL | 修改 |
|-------|-------|------|
| author | novel-writing | 创作前必须读状态卡 |
| editor | quality-review | 通过后必须提取并写入 |
| planner | chapter-planning | 创建指令时必须注入 |

---

## 任务状态修复与 outlines 功能（2026-04-02 晚）

### 问题发现
1. task_status 表中 planner 的 publish 任务（ID:137）和 author 的 create 任务（ID:138）卡在 running 状态
2. outlines 表完全空表，planner 没有创建大纲的功能

### 解决方案
1. **清理 stuck tasks** → 标记为 completed（章节实际已发布）
2. **给 planner 添加 outlines 功能** → 更新 `chapter-planning/SKILL.md`

### 修改的文件

| 文件 | 改动 |
|------|------|
| planner/workspace|skills/chapter-planning/SKILL.md | 添加 outlines 创建/查询/更新/删除命令说明 |

### outlines 表结构

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK | 自增主键 |
| project_id | TEXT | FK | 项目 ID |
| level | TEXT | CHECK | 仅允许：`book` / `volume` / `arc` |
| sequence | INTEGER | - | 同级下的序号 |
| title | TEXT | - | 标题 |
| content | TEXT | - | 大纲内容 |
| chapters_range | TEXT | - | 章节范围（如 "1-10"） |
| created_at | TEXT | - | 创建时间 |
| updated_at | TEXT | - | 更新时间 |

### 大纲层级说明

| level | 说明 | 示例 |
|-------|------|------|
| book | 全书级 | "职场无限流" (1-100章) |
| volume | 卷级 | "第一卷：初入职场" (1-10章) |
| arc | 篇章/章节级 | "第1章：生日礼物" (1章) |

### planner 新增工作流

```
读状态卡 → 获取下一章 → 创建指令 → 【可选】创建大纲
```

### 示例命令

```bash
# 创建卷级大纲
python3 tools/db.py create_outline novel_002 volume 1 "第一卷" "1-10" --content "..."

# 创建arc章级大纲
python3 tools/db.py create_outline novel_002 arc 1 "第1章" "1" --content "..."

# 查询大纲
python3 tools/db.py outlines novel_002
python3 tools/db.py outlines novel_002 arc

# 更新大纲
python3 tools/db.py update_outline novel_002 arc 1 --content "新内容..."

# 删除大纲
python3 tools/db.py delete_outline novel_002 arc 1
```

### 已创建测试大纲

| level | sequence | title | chapters_range |
|-------|----------|-------|----------------|
| book | 1 | 职场无限流 | 1-100 |
| volume | 1 | 第一卷：初入职场 | 1-10 |
| arc | 1 | 开篇弧线：系统降临与觉醒 | 1-3 |
| arc | 2 | 第1章：生日礼物 | 1 |
| arc | 3 | 第2章：第一次陌生拜访 | 2 |

---

## chapter_state 数值一致性落地（2026-04-03 凌晨）

### 问题发现
1. **chapter_state 空表** → 质检通过后没有写入数值状态
2. **author 没有实际读取** → SKILL 写了但未执行
3. **editor 没有实际写入** → SKILL 写了但未执行
4. **db.py 字段错位** → `state_json` vs `state_data`，`created_at` vs `summary` 顺序混乱

### 解决方案
1. **修复 author SKILL** → 强化"必须读取状态卡"的命令
2. **修复 editor SKILL** → 强化"必须写入状态卡"的命令
3. **修复 db.py** → 修正 `cmd_chapter_state` 的字段名和顺序
4. **补齐历史数据** → 为章节1/2 创建初始 state_data
5. **同步修复** → planner 和 architect 的 db_common.py 都要修

### 修改的文件

| 文件 | 改动 |
|------|------|
| author/workspace/skills/novel-writing/SKILL.md | 添加"数值一致性铁律"和详细状态卡示例 |
| editor/workspace/skills/quality-review/SKILL.md | 添加"chapter_state 写入详解"和提取原则 |
| planner/workspace/tools/db_common.py | 修复 `cmd_chapter_state` 字段名（`state_json`→`state_data`），修正列顺序 |
| architect/workspace/tools/db_common.py | 同步修复 `cmd_chapter_state` |

### db.py 修复内容

**修复前：**
```python
# 字段名错位，列顺序混乱
conn.execute("""INSERT ... (state_json, summary, updated_at) VALUES (?,?,?, datetime('now','+8 hours'))""")
```

**修复后：**
```python
# 字段名正确，列顺序匹配表结构
conn.execute("""INSERT ... (state_data, created_at, summary) VALUES (?,?, ?, ?)""")
```

### author SKILL 新增内容

- **数值一致性铁律**：禁止自己计算/编造数值，必须显式读取状态卡
- **状态卡读取详解**：有数据和无数据时的返回格式
- **状态卡集成**：如何将状态卡注入创作上下文

### editor SKILL 新增内容

- **写入时机**：质检通过后必须执行
- **提取原则**：从章节内容显式提取，不猜测
- **写入命令**：`--set` 和 `summary` 参数格式
- **完整示例**：包含 JSON 状态和可读摘要

### 已创建初始数据

| 章节 | 状态概要 |
|------|----------|
| 1 | 系统Lv1，技能【职场洞察】，销售副本进行中，倒计时72小时，已接触客户1人（王总），线索3条 |
| 2 | 系统Lv1（XP:15/100），技能【职场洞察】，销售副本进行中，倒计时69小时，已接触客户2人（王总/赵女士），线索4条（含S001） |

### 验证结果

```bash
# 读取第1章状态
python3 tools/db.py chapter_state novel_002 1
# ✅ 返回完整 JSON 和 summary

# 读取第2章状态
python3 tools/db.py chapter_state novel_002 2
# ✅ 返回完整 JSON 和 summary
```

### 后续工作流

```
章节3创作前：
  author: 读取 chapter_state(novel_002, 2)
  → 基于"系统Lv1, XP:15, 倒计时69小时"创作
  → 保存草稿

章节3质检通过：
  editor: 提取章节3结束数值
  → 写入 chapter_state(novel_002, 3)
  → 下次章节4创作时有基准
```

---

## chapter-planning SKILL 架构描述修复（2026-04-04 上午）

### 问题发现
planner 的 `chapter-planning/SKILL.md` 还保留着旧的 "Isolated Cron 架构" 描述，与当前 Dispatcher 调度架构不一致。

### 修复内容

| 文件 | 改动 |
|------|------|
| planner/workspace/skills/chapter-planning/SKILL.md | 移除 "Isolated Cron 架构"，改为 "Dispatcher 调度架构" |

### 当前架构

```
Dispatcher (cron 每 5 分钟)
  → 轮询 chapters 状态
  → sessions_spawn(agentId="planner", cleanup="delete")
  → planner 执行任务
  → 写入 DB 结束
```

### 验证结果
- ✅ chapter-planning/SKILL.md 触发方式已修正
- ✅ HEARTBEAT.md 已是正确的被动触发模式
- ✅ SOUL.md 通信铁律正确

---

## 伏笔系统职责明确与验证机制（2026-04-03 凌晨）

### 核心问题
1. plot_holes 和 chapter_plots 数据对不上
2. 伏笔处理逻辑埋在 `create_instruction` 底层，不透明且不可控
3. 没有伏笔验证机制，无法确保执笔按指令处理伏笔
4. sync_plots 无人定期执行，数据一致性无保障
5. Dispatcher 错误地承担了伏笔同步职责

### 最终方案（方案C）

| 步骤 | 内容 |
|------|------|
| 1 | 给 editor SKILL 添加"伏笔验证"步骤 |
| 2 | 给 author SKILL 添加"伏笔确认"步骤 |
| 3 | 给 planner HEARTBEAT.md 添加 sync_plots 定期执行 |
| 4 | 新增 verify_plots 命令验证伏笔一致性 |
| 5 | 移除 Dispatcher 的伏笔同步流程 |

### 职责重新明确

| Agent| 职责 | 原职责 | 修改 |
|-------|------|--------|------|
| author | 创作前确认伏笔 | 只创作 | ✅ 新增 verify_plots 步骤 |
| editor | 质检后验证伏笔 | 只评分 | ✅ 新增 verify_plots 步骤 |
| planner | 规划并管理伏笔 | 创建指令 | ✅ HEARTBEAT 定期同步 |
| dispatcher | 调度任务流转 | ❌ 错误同步伏笔 | ✅ 移除伏笔同步 |

### 修改的文件

| 文件 | 改动 |
|------|------|
| author/workspace/skills/novel-writing/SKILL.md | 模式A/B 新增 verify_plots 步骤 |
| editor/workspace/skills/quality-review/SKILL.md | 工作流新增 verify_plots 步骤 |
| planner/workspace/HEARTBEAT.md | 添加定期 sync_plots 执行 |
| architect/workspace/tools/db_common.py | 新增 cmd_verify_plots 函数并注册 |
| planner/workspace/tools/db_common.py | 同步 cmd_verify_plots，修复 close() bug |
| dispatcher/workspace/skills/dispatcher/SKILL.md | 移除 Step 4 伏笔同步 |

### 新增 verify_plots 命令

**功能**：验证本章伏笔处理是否与指令一致

**用法**：
```bash
python3 tools/db.py verify_plots <project> <chapter>
```

**返回格式**：
```json
{
  "success": true,
  "chapter": 1,
  "instruction": {
    "plots_to_plant": ["L001"],
    "plots_to_resolve": []
  },
  "content_check": {
    "planted_in_content": ["L001"],
    "missing_planted": [],
    "resolved_in_content": [],
    "missing_resolved": []
  },
  "chapter_plots_check": {
    "recorded_planted": ["L001"],
    "recordedd_resolved": []
  },
  "issues": [],
  "valid": true
}
```

**验证维度**：
1. 指令要求的伏笔是否在章节内容中出现
2. chapter_plants 表记录是否正确
3. 指令参数与内容是否一致

### planner HEARTBEAT 定期执行

```bash
# 获取当前项目
python3 tools/db.py current_project

# 同步伏笔数据
python3 tools/db.py sync_plots <project>

# 检查待兑现伏笔
python3 tools/db.py pending_plots <project>
```

### db.py bug 修复

| 问题 | 修复 |
|------|------|
| cmd_sync_plots 参数错位 | VALUES 数量与占位符不匹配 |
| cmd_sync_plots 重复 close() | 移除多余的 close() |
| cmd_chapter_state 字段错位 | state_json → state_data，列顺序修正 |

### 职责边界清晰后的工作流

```
author 创作:
  读取指令 → 创作 → verify_plots → 保存草稿

editor 质检:
  读取草稿 → 五层审校 → verify_plots → 提交报告

planner 定期:
  sync_plots → pending_plots → HEARTBEAT_OK

dispatcher 调度:
  健康检查 → 任务超时 → 触发任务 → 等待完成
  ✅ 不再同步伏笔
```

### 验证结果

- ✅ verify_plots 命令已实现并注册
- ✅ author SKILL 已添加伏笔确认步骤
- ✅ editor SKILL 已添加伏笔验证步骤
- ✅ planner HEARTBEAT 已添加定期同步
- ✅ planner db_common.py 已同步并修复 bug
- ✅ dispatcher 已移除伏笔同步流程

---

## 数据校对机制（2026-04-05 上午）

### 问题背景

planner 创建第五章指令时，`plots_to_plant` 引用了不存在的伏笔 L006，导致 author 执行时 `verify_plots` 失败。

### 根因分析

planner 的 SKILL 中缺少数据校对流程：
- 没有检查伏笔引用是否存在
- 没有检查状态卡是否存在
- 没有检查角色引用是否存在
- `create_instruction` 不会自动创建伏笔，只会关联已有的伏笔

### 解决方案

**1. 新增 `validate_data` 命令**

```bash
python3 tools/db.py validate_data <project> [chapter]
```

**检查维度：**

| 检查项 | 错误级别 | 说明 |
|--------|---------|------|
| 伏笔引用不存在 | ❌ error | `plots_to_plant` 或 `plots_to_resolve` 引用的伏笔不存在 |
| 伏笔未埋设即兑现 | ❌ error | 兑现的伏笔未在之前章节埋设 |
| 状态卡缺失 | ⚠️ warning | 上一章没有状态卡，执笔可能缺乏数值基准 |
| 新角色创建 | ℹ️ info | 指令将创建新角色（正常情况） |

**2. 实施方案A：`create_instruction` 内部校对（✅ 已实施）**

在 `cmd_create_instruction` 命令内部添加伏笔校对逻辑：

```python
def cmd_create_instruction(args):
    # 1. 解析伏笔参数
    plots_to_plant = json.loads(args[6]) if len(args) > 6 else []
    plots_to_resolve = json.loads(args[5]) if len(args) > 5 else []
    
    # 2. 校对伏笔引用
    for code in plots_to_plant:
        if not plot_exists(code):
            return {"success": False, "error": "伏笔不存在", "action": "add_plot ..."}
    
    for code in plots_to_resolve:
        if not plot_exists(code):
            return {"success": False, "error": "伏笔不存在"}
        if plot_planted_chapter(code) > current_chapter:
            return {"success": False, "error": "伏笔未埋设"}
    
    # 3. 校对通过，创建指令
    ...
```

**优点：**
- ✅ 代码级强制，无法绕过
- ✅ 创建时立即发现问题
- ✅ 不依赖 Agent 执行 SKILL
- ✅ 自动提示修复命令

**3. 触发时机**

| 时机 | 触发方式 | 强制性 | 说明 |
|------|---------|--------|------|
| **创建指令时** | `create_instruction` 内部自动校对 | ✅ 强制 | 引用错误的伏笔时，指令不会被创建 |
| **规划流程** | SKILL 中要求 planner 手动调用 | ⚠️ 半强制 | 创建指令后、task_complete 前调用 |
| **手动调用** | 任何时候 | ❌ 可选 | 调试/检查时 |

**4. 校对流程**

```bash
# 步骤1：创建指令（自动校对）
python3 tools/db.py create_instruction novel_001 5 \
  "目标..." "事件..." "钩子..." \
  '["P004"]' '["L007"]' "紧张"

# 如果校对失败：
{
  "success": false,
  "error": "数据校对失败，指令未创建",
  "issues": [
    {
      "type": "missing_plot",
      "field": "plots_to_plant",
      "code": "L007",
      "message": "伏笔 L007 不存在，请先执行 add_plot 创建",
      "action": "python3 tools/db.py add_plot novel_001 L007 <type> '<title>' '<description>' 5 <resolve_chapter>"
    }
  ]
}

# 步骤2：根据提示创建伏笔
python3 tools/db.py add_plot novel_001 L007 short "标题" "描述" 5 10

# 步骤3：重新创建指令
python3 tools/db.py create_instruction novel_001 5 ...
# {"success": true, "validation": "passed"}
```

### 修改的文件

| 文件 | 改动 |
|------|------|
| architect/workspace/tools/db_common.py | 修改 `cmd_create_instruction`，添加伏笔校对逻辑 |
| 所有 Agent 的 db_common.py | 同步更新 |

### 验证结果

**测试场景1：引用不存在的伏笔**

```bash
python3 tools/db.py create_instruction novel_001 6 "目标" "事件" "钩子" '[]' '["L007"]' "测试"
```

**结果：**
```json
{
  "success": false,
  "error": "数据校对失败，指令未创建",
  "issues": [
    {
      "type": "missing_plot",
      "field": "plots_to_plant",
      "code": "L007",
      "message": "伏笔 L007 不存在，请先执行 add_plot 创建",
      "action": "python3 tools/db.py add_plot novel_001 L007 ..."
    }
  ]
}
```
✅ **成功拦截！**

**测试场景2：兑现未埋设的伏笔**

```bash
# 创建在第10章埋设的伏笔
python3 tools/db.py add_plot novel_001 L008 short "测试" "描述" 10 15

# 尝试在第8章兑现
python3 tools/db.py create_instruction novel_001 8 "目标" "事件" "钩子" '["L008"]' '[]' "测试"
```

**结果：**
```json
{
  "success": false,
  "error": "数据校对失败，指令未创建",
  "issues": [
    {
      "type": "plot_not_planted",
      "field": "plots_to_resolve",
      "code": "L008",
      "message": "伏笔 L008 将在第10章埋设，无法在第8章兑现"
    }
  ]
}
```
✅ **成功拦截！**

**测试场景3：正常情况**

```bash
python3 tools/db.py create_instruction novel_001 6 "目标" "事件" "钩子" '["P004"]' '["L006"]' "测试"
```

**结果：**
```json
{"success": true, "chapter": 6, "instruction_id": 99, "validation": "passed"}
```
✅ **校对通过！**

### 防止复发的保障机制

| 机制 | 说明 |
|------|------|
| **代码级强制** | `create_instruction` 内部自动校对，无法绕过 |
| **即时反馈** | 引用错误时立即返回错误提示和修复命令 |
| **自动提示** | 错误信息中包含 `add_plot` 命令模板 |
| **SKILL 指导** | planner SKILL 中标注为强制步骤 |

---

## 第6章两次重写失败的根因分析（2026-04-05 中午）

### 问题现象

**第一次重写：**
- Author 写了：赵国栋威胁继承权
- Editor 给分：100分
- 问题：继承权威胁 ≠ 赵婉清本人被威胁

**第二次重写：**
- Author 写了：赵国栋说"你让婉清以后怎么见人"
- Editor 给分：100分
- 问题：林默让赵婉清丢脸 ≠ 赵婉清被羞辱

**两次都错！**

### 根因分析

**根因1：伏笔描述模糊**

S004原描述：
```
"当赵婉清被羞辱或威胁时会失去理智"
```

问题：这是一个**模糊的条件**
- Author 理解为：赵婉清被牵连、受影响 = 被羞辱
- 实际应该是：赵婉清本人被直接羞辱或威胁

**根因2：Author 对伏笔的理解偏差**

Author 的理解：
```
赵国栋羞辱林默 → 林默愤怒 → 触发保护欲
```

正确理解：
```
赵国栋羞辱赵婉清 → 赵婉清受伤 → 林默失去理智保护妻子
```

关键差异：
- Author 把重点放在"林默被羞辱"
- 实际重点应该是"赵婉清被羞辱"

**根因3：Editor 只检查关键词，不检查逻辑**

Editor 的 verify_plots 检测：
```
检测维度：
1. 伏笔代码：S004
2. 标题关键词："林默"、"非理性"、"软肋"
3. 描述实体："保护欲"、"妻子"、"赵婉清"

检测结果：
✅ 检测到"保护欲"、"软肋"、"非理性"
✅ 验证通过
```

问题：
- verify_plots 只检查关键词是否存在
- 不检查伏笔兑现的逻辑是否正确
- 不检查触发对象是否正确

### 解决方案

**1. 明确伏笔描述（立即修复）**

修改 S004 伏笔：
```
【表象】赵国栋直接羞辱赵婉清本人，当着林默的面说：
"你嫁给他三年，他给你挣过一分钱吗？你就是个废物！"
或威胁赵婉清的人身安全：
"你要是不离婚，就别想在这个家有安生日子！"
赵婉清被羞辱时，林默会失去理智。

【正确兑现示例】
赵国栋："婉清，你看看你这个丈夫，连给你买件像样的衣服都要跟我伸手。
你嫁给他三年，他给你挣过一分钱吗？你是我赵国栋的女儿，嫁给这么一个废物，
你以为你在帮他？你是在毁你自己。"
赵婉清的脸色刷地变白，眼眶泛红。
林默的眼神瞬间变了——那是一种近乎疯狂的、非理性的保护欲。
```

**2. Author SKILL 新增伏笔兑现原则**

在 `novel-writing/SKILL.md` 中新增：
```markdown
## ⚠️ 伏笔兑现的核心原则

**触发对象验证（必须！）**

伏笔说"A被羞辱/威胁" → 必须是A本人被直接羞辱/威胁

❌ 错误：B被羞辱，A被牵连
❌ 错误：A因为B的事情而受影响
❌ 错误：羞辱与A相关的事物（如"继承权"）
✅ 正确：A本人被直接羞辱："你就是个废物"
✅ 正确：A本人被直接威胁："你要是不X，就Y"

**示例对比（S004伏笔）：**

❌ 错误兑现（第一次）：
赵国栋威胁继承权 → 这是威胁"继承权"，不是威胁"赵婉清本人"

❌ 错误兑现（第二次）：
赵国栋说"你让婉清以后怎么见人" → 这是羞辱林默，不是羞辱赵婉清

✅ 正确兑现：
赵国栋直接羞辱赵婉清："你就是个废物，嫁了个垃圾丈夫"
→ 赵婉清受伤 → 林默失去理智保护妻子
```

**3. Editor SKILL 新增伏笔逻辑验证**

在 `quality-review/SKILL.md` 中新增：
```markdown
## 阶段2：伏笔兑现逻辑检查

**触发对象验证（最关键！）**

核心规则：伏笔说"A被羞辱/威胁" → 必须是A本人被直接羞辱/威胁

检查方法：
1. 读取伏笔描述，提取核心条件（谁 + 被怎么样）
2. 在章节内容中找到对应的场景
3. 确认触发对象与伏笔要求一致

错误示例（S004伏笔）：
❌ 赵国栋说"你让婉清以后怎么见人" → 羞辱林默，不是羞辱赵婉清
扣分：-15分（伏笔兑现逻辑不通）

❌ 赵国栋威胁"继承权" → 威胁继承权，不是威胁赵婉清
扣分：-15分（伏笔兑现逻辑不通）

正确示例：
✅ 赵国栋羞辱赵婉清："你就是个废物，嫁了个垃圾丈夫"
→ 触发对象正确 → 赵婉清受伤 → 林默失去理智

⚠️ 伏笔逻辑硬伤 → 直接退回，总分 ≤ 60分
```

### 修改的文件

| 文件 | 改动 |
|------|------|
| plot_holes 表（S004） | 增加正确兑现示例 |
| author/workspace/skills/novel-writing/SKILL.md | 新增"伏笔兑现的核心原则"和"触发对象验证" |
| editor/workspace/skills/quality-review/SKILL.md | 新增"伏笔兑现逻辑检查详解"和"触发对象验证" |

### 核心教训

| 教训 | 说明 |
|------|------|
| **伏笔描述要明确** | 不能只说"A被羞辱"，要给出具体示例 |
| **触发对象必须正确** | "A被羞辱"必须是A本人被羞辱，不是A被牵连 |
| **Editor 要检查逻辑** | 不能只检查关键词，要检查触发对象是否正确 |
| **提供正确示例** | Author 和 Editor 都需要看到正确的兑现示例 |

---

## Author 伏笔验证失败导致创作变形问题（2026-04-05 中午）

### 问题现象

Author 在创作第6章时：
1. 第一次伏笔验证失败
2. 没有按 SKILL 流程返回修改
3. 多次尝试"修改关键段落"和"增强关键词匹配"
4. 最终验证通过，但创作可能已经变形

### 根因分析

**1. SKILL 流程清晰，但 LLM 未遵循**

SKILL 中明确写了：

```markdown
⚠️ **验证通过才能保存草稿！验证失败必须返回步骤7修改！**
```

但 Author 实际执行时：
- 第一次验证失败后，没有返回修改
- 而是尝试"检查关键词"、"增强匹配"
- 这是一种**"凑关键词"的变形策略**

**2. verify_plots 的检测逻辑问题**

Author 的理解：

```
verify_plots 检查的是内容中是否出现了伏笔相关的关键词
```

实际上 verify_plots 的检测维度：
1. **伏笔代码**（如 S004）
2. **标题关键词**（从标题提取 2-4 字词组）
3. **描述实体**（从描述提取 2-6 字词组）

**3. LLM 的"凑关键词"行为**

Author 认为需要"更明确地植入伏笔代码标记"，这是**错误的理解**：
- verify_plots 不需要内容中包含伏笔代码（如"S004"）
- 只需要内容中包含关键词或实体

Author 的策略：
1. 第一次验证失败 → "检查 S004 的内容"
2. 发现关键词不够明显 → "增强关键词匹配"
3. 修改内容以"凑关键词"

**这导致创作变形**：为了通过验证而强行植入关键词，而不是自然地兑现伏笔。

### 解决方案

**在 author SKILL 中新增章节：**

1. **verify_plots 检测维度**
   - 明确3个检测维度：代码、标题关键词、描述实体
   - 说明不需要在内容中写入代码
   - 提供正确和错误的伏笔兑现示例

2. **验证失败时的正确处理**
   - 禁止凑关键词
   - 禁止在内容中写入伏笔代码
   - 应该重新理解伏笔，自然地融入剧情

### 修改的文件

| 文件 | 改动 |
|------|------|
| author/workspace/skills/novel-writing/SKILL.md | 新增"verify_plots 检测维度"和"验证失败时的正确处理"章节 |

---

## planner 伏笔创建流程缺失问题（2026-04-05 上午）

### 问题发现

planner 创建第五章指令时，`plots_to_plant` 写了 `"L006"`，但伏笔表中没有 L006。

### 根因分析

planner 的 `chapter-planning/SKILL.md` 中没有说明伏笔创建流程：
- 只告诉 planner 如何在 `create_instruction` 中引用伏笔
- 没有说明新伏笔需要先用 `add_plot` 创建
- `create_instruction` 不会自动创建伏笔，只会关联已有的伏笔

### 影响

1. author 执行第五章创作时，`verify_plots` 会失败（找不到伏笔）
2. `chapter_plots` 表无法正确关联
3. 伏笔追踪系统断裂

### 立即修复

手动创建 L006 伏笔：
```bash
python3 tools/db.py add_plot novel_001 L006 short "Lv4宿主信号出现" \
  "【表象】第五章结尾沙盘显示，一个新的Lv4宿主信号在江城外围出现。【真相/底牌】这是比林默、苏晚晴更强的高级宿主，五线围猎升级为六线围猎，为后续更高级威胁埋下伏笔。" \
  5 10
```

### 长期修复

在 `planner/workspace/skills/chapter-planning/SKILL.md` 中添加：

1. **伏笔创建流程**：必须先 `add_plot`，再 `create_instruction`
2. **伏笔代码命名规范**：P（长线）、L（中线）、S（短线）
3. **伏笔描述格式**：包含"表象"和"真相/底牌"

### 修改的文件

| 文件 | 改动 |
|------|------|
| planner/workspace/skills/chapter-planning/SKILL.md | 新增"伏笔必须在 create_instruction 之前创建"章节 |

### 防止复发的检查清单

planner 在创建指令前必须检查：

□ `plots_to_plant` 中的伏笔代码是否已存在于伏笔表？
  → 如果不存在，先用 `add_plot` 创建
  → 查询命令：`python3 tools/db.py pending_plots <project>`

□ `plots_to_resolve` 中的伏笔代码是否已存在？
  → 兑现的伏笔必须在之前的章节已经埋设

---

## verify_plots 关键词检测逻辑修复（2026-04-05 上午）

### 问题发现

author 执行第4章创作后，`verify_plots` 验证失败。虽然正文中包含了伏笔关键词，但检测函数未能正确识别。

### 根因分析

`check_plot_in_content` 函数的关键词提取逻辑有缺陷：

```python
# 原代码（有问题）
keywords = [w for w in title if len(w) >= 2]
```

这行代码遍历标题的每个字符，而不是提取词语。例如标题"林默的非理性软肋"会被拆成单个字符：`林`、`默`、`的`、`非`、`理`、`性`、`软`、`肋`，无法正确匹配正文中的"软肋"或"保护欲"。

### 修复方案

改用正则表达式提取 2-6 字的中文词组，并增加停用词过滤（包括"表象"、"真相"、"底牌"等伏笔描述专用词）。

### 修改的文件

所有 Agent 的 `tools/db_common.py` 已同步修复。

### 验证结果

第4章伏笔 S004 检测成功：
- ✅ 实体:保护欲
- ✅ 实体:的非理性弱点

---

## task_complete 调用缺失问题修复（2026-04-04）

### 问题发现
Dispatcher 报告第2章 revise 任务仍在 running，但章节状态已是 review。调度器跳过本轮调度。

**数据状态**：
| 维度 | 值 |
|------|-----|
| 章节2 (novel_003) | status = `review` ✅ |
| task_status ID=170 | `revise`, status = `running` ❌ |
| started_at | 2026-04-04 11:15:07 |

### 根因分析
author 完成 revise 任务后：
- ✅ 调用了 `save_draft` → 章节状态更新为 `review`
- ❌ **没有调用 `task_complete`** → task_status 仍为 `running`

**原因**：author SKILL 中模式B流程写的是 `task_start`（第一步），但实际 Dispatcher 已创建任务，不需要再调用 `task_start`。而且流程末尾的 `task_complete` 位置不够醒目，容易被跳过。

### 解决方案

**1. 立即修复数据**：
```sql
UPDATE task_status SET status='completed', completed_at='2026-04-04 11:30:00' WHERE id=170;
```

**2. 重构 author SKILL**：

| 改动 | 说明 |
|------|------|
| 移除模式A/B中的 `task_start` 步骤 | Dispatcher 已创建任务 |
| 新增 Step 1: 提取 task_id | 从任务消息中提取，或查询 running 任务 |
| 强化 Step 8: task_complete | 添加 ⚠️⚠️⚠️ 警告标记 |
| 新增"任务状态管理"section | 强调必须执行 task_complete |
| 新增检查清单项 | "是否已执行 task_complete？" |

**3. 关键警告**：
```
⚠️ 不调用 task_complete = 任务永远 running = 调度器不会派发下一个任务！
```

### 修改的文件

| 文件 | 改动 |
|------|------|
| author/workspace/skills/novel-writing/SKILL.md | 重构流程，强化 task_complete |

### 任务消息格式

```
项目 <project> 第<chapter>章开始创作，请读取指令并执行。任务ID: <task_id>
```
或
```
项目 <project> 第<chapter>章被质检退回，状态 revision，请读取 reviews 获取修改意见并重写。任务ID: <task_id>
```

### 正确流程

```
Step 0: 获取项目上下文
Step 1: ⚠️ 提取 task_id（从消息或查询 running 任务）
Step 2-N: 创作流程...
Final Step: ⚠️⚠️⚠️ task_complete <task_id> true
```

### 验证结果

- ✅ task 170 已修复为 completed
- ✅ author SKILL 已重构
- ✅ 下轮调度应正常派发 review 任务给 editor

---

## db.py 命令缺失问题（2026-04-04 中午）

### 问题发现

author 完成第2章修改后，task_status 仍为 running（task 172）。检查日志发现 author 尝试调用 `task_complete` 时报错。

**根因**：author 的 db.py 没有注册 `task_complete` 和 `task_list` 命令！

### 修复内容

| 文件 | 缺少的命令 | 状态 |
|------|-----------|------|
| author/workspace/tools/db.py | `task_complete`, `task_list` | ✅ 已添加 |
| editor/workspace/tools/db.py | `task_list` | ✅ 已添加 |
| planner/workspace/tools/db.py | 无（使用 `ALL_COMMANDS`） | ✅ 已正确 |

### 问题影响

SKILL 中写的命令再正确，如果 db.py 没有注册，Agent 也无法执行。

### 教训

**修改 SKILL 时，必须同步检查 db.py 是否注册了所需命令！**

### 验证命令

```bash
python3 tools/db.py task_list novel_003 running
python3 tools/db.py task_complete <id> true
```

---

## planner task_complete 参数错误（2026-04-04 中午）

### 问题发现

planner 完成发布任务后，task_status 显示 `failed`，但章节实际已成功发布。

**原因**：planner 调用 `task_complete 174 "描述信息"` 而不是 `task_complete 174 true`

**db_common.py 逻辑**：
```python
success = args[1] if len(args) > 1 else 'true'
status = 'completed' if success == 'true' else 'failed'
```

当传入 `"描述信息"` 时，`success != 'true'`，所以 `status = 'failed'`。

### 修复内容

1. **数据修复**：task 174 从 failed 改为 completed
2. **SKILL 强化**：在所有 Agent 的 SKILL 中添加明确的参数格式说明

**新增内容**：
```
### ⚠️ task_complete 参数格式

✅ 正确：`python3 tools/db.py task_complete 174 true`
❌ 错误：`python3 tools/db.py task_complete 174 "任务完成"`
❌ 错误：`python3 tools/db.py task_complete 174 成功`

参数说明：
- 第一个参数：task_id（数字）
- 第二个参数：`true` 或 `false`（字符串，不是布尔值）
- 禁止传任何其他内容！
```

### 修改的文件

| 文件 | 改动 |
|------|------|
| planner/workspace/skills/chapter-planning/SKILL.md | 添加 task_complete 参数格式说明 |
| author/workspace/skills/novel-writing/SKILL.md | 同步添加 |
| editor/workspace/skills/quality-review/SKILL.md | 同步添加 |

### 教训

**LLM 可能理解错参数格式，必须在 SKILL 中明确禁止错误用法！**

---

## add_review 文件名长度限制错误（2026-04-04 下午）

### 问题发现

editor 调用 `add_review` 时报错：`OSError: [Errno 63] File name too long`

**原因**：`cmd_add_review` 函数中有一段代码：

```python
for i, (var, name) in enumerate([(summary,'summary'),(issues,'issues'),(suggestions,'suggestions')]):
    if Path(var).exists():  # ← 当 var 是长 JSON 字符串时，触发文件名长度限制
```

当 `suggestions` 是一个很长的 JSON 字符串时，`Path(var).exists()` 会尝试把它当作文件路径检查，导致系统文件名长度限制错误。

### 修复方案

在检查文件是否存在之前，先检查字符串长度：

```python
MAX_PATH_LEN = 255  # 大多数文件系统的路径长度限制
for i, (var, name) in enumerate([...]):
    if len(var) < MAX_PATH_LEN and Path(var).exists():
        # 读取文件内容
```

### 修改的文件

| 文件 | 改动 |
|------|------|
| architect/workspace/tools/db_common.py | 添加长度检查 |
| author/workspace/tools/db_common.py | 同步修复 |
| dispatcher/workspace/tools/db_common.py | 同步修复 |
| editor/workspace/tools/db_common.py | 已修复 |
| planner/workspace/tools/db_common.py | 同步修复 |
| scout/workspace/tools/db_common.py | 同步修复 |
| secretary/workspace/tools/db_common.py | 同步修复 |

### 教训

**支持文件路径的功能必须先检查字符串长度，避免长字符串触发系统限制！**

---

## 执笔质量提升系统（2026-04-07 晚）

### 问题发现

| 表名 | 记录数 | 状态 |
|------|--------|------|
| anti_patterns | 23条 | ✅ 已启用，注入创作上下文 |
| learned_patterns | 26条 | ✅ 质检时积累 |
| context_rules | 3条 | ✅ 已启用 |
| **best_practices** | **0条** | ❌ **空表，从未使用** |

### 优化方案

**目标：让高分章节的经验自动沉淀，指导后续创作**

### 已实施

| 步骤 | 内容 | 状态 |
|------|------|------|
| 1 | 扩展 best_practices 表结构（tags, source_score, chapter_numbers） | ✅ |
| 2 | 新增 `extract_best_practices` 命令（从高分章节自动提取） | ✅ |
| 3 | 新增 `batch_extract_practices` 命令（批量提取项目高分章节） | ✅ |
| 4 | 新增 `promote_pattern` 命令（learned_patterns → anti_patterns） | ✅ |
| 5 | ContextBuilder 新增 `_get_best_practices` 方法 | ✅ |
| 6 | `cmd_build_context` 新增高分范例片段 | ✅ |
| 7 | Editor SKILL 新增 Step 7.5 提取最佳实践 | ✅ |
| 8 | 同步到 Author/Editor 的 db.py 和 HELP | ✅ |

### 新增命令

```bash
# 从高分章节自动提取最佳实践
python3 tools/db.py extract_best_practices <project> <chapter> --score <score>

# 批量提取项目高分章节
python3 tools/db.py batch_extract_practices <project> --min-score 90

# 查询最佳实践
python3 tools/db.py best_practices [category] [--project <project>]

# 手动添加最佳实践
python3 tools/db.py add_best_practice <project> <category> "<practice>" '[章节]' <分数> "<证据>"

# 将高频问题提升到 anti_patterns
python3 tools/db.py promote_pattern <pattern_id> --severity medium
```

### 工作流

```
Editor 质检高分章节（≥90）
  ↓
Step 7.5: extract_best_practices
  ↓
写入 best_practices
  ↓
下一章创作时
  ↓
ContextBuilder 读取 best_practices
  ↓
注入【高分范例】片段
  ↓
Author 创作时参考

---

Editor 质检发现问题
  ↓
record_pattern_hit → learned_patterns
  ↓
频率 ≥ 3次
  ↓
promote_pattern → anti_patterns
  ↓
所有项目共享避坑
```

### novel_003 已提取的最佳实践

| 类别 | 数量 | 来源章节 |
|------|------|---------|
| hook（开篇） | 3条 | 第1、2、3章 |
| setting（设定） | 7条 | 第1-7章 |

### 预期效果

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| best_practices 记录 | 0条 | 10条/项目 |
| Author 上下文片段 | 8个 | 9个（+高分范例） |
| 质检高分章节利用率 | 0% | 80%+ |
| 跨项目经验共享 | 无 | anti_patterns 通用 |

---

## 执笔质量下降诊断（2026-04-04 下午）

### 问题发现

第3章质检得分 68 分（未达标），比第1章（92分）、第2章（96分）明显下降。

| 章节 | 得分 | 设定 | 逻辑 | 毒点 | 文字 | 爽点 |
|------|------|------|------|------|------|------|
| 第1章 | 92 | 20 | 17 | 20 | 17 | 18 |
| 第2章 | 96 | 23 | 25 | 20 | 13 | 15 |
| 第3章 | 68 | 18 | 18 | 13 | **9** | **10** |

### 主要问题

1. **伏笔断裂**：第2章设定的"周五17:50定时邮件"伏笔未使用
2. **AI 痕迹明显**：列举式叙述、上帝视角说教
3. **角色逻辑问题**：李经理作为老狐狸缺乏自保反应
4. **机械降神**：大老板"刚好路过"铺垫不足

### 根因分析

**修订模式缺失状态卡读取！**

| 模式 | 流程 | 是否读取状态卡 |
|------|------|---------------|
| 模式A（创作） | Step 2: 读取状态卡 | ✅ |
| 模式B（修订） | Step 2: 读取质检报告 | ❌ **缺失** |

状态卡中包含关键伏笔信息：
```json
{
  "hidden_info": {
    "anonymous_email_scheduled": "周五17:50定时发送"
  }
}
```

由于修订模式没有读取状态卡，执笔不知道这个伏笔，导致剧情断裂。

### 修复内容

| 文件 | 改动 |
|------|------|
| author/workspace/skills/novel-writing/SKILL.md | 模式B增加 Step 2: 读取状态卡 |

### 修改后的流程

```
模式B（修订）:
Step 0: 获取项目上下文
Step 1: 提取 task_id
Step 2: ⚠️ 读取上一章状态卡（关键！修改时也要保持连续性！）
Step 3: 读取质检报告
Step 4: 读取当前草稿
Step 5: 读取原指令
Step 6: 针对性修改
Step 7: 确认伏笔处理
Step 8: 保存草稿
Step 9: 任务完成
```

### 教训

**修订模式也需要读取状态卡，确保伏笔、数值等上下文连续性！**

---

## 执笔质量下降 - 完整诊断与修复（2026-04-04 下午）

### 问题发现

第3章质检得分 68 分（未达标），主要问题：
1. **伏笔断裂**："周五17:50定时邮件"伏笔未使用
2. **AI 痕迹明显**：列举式叙述、上帝视角说教
3. **角色逻辑问题**：李经理作为老狐狸缺乏自保反应

### 根因分析

**修订模式（模式B）缺失多项关键数据读取！**

| 数据 | 模式A（创作） | 模式B（修订-修复前） | 影响 |
|------|--------------|---------------------|------|
| 状态卡 | ✅ Step 2 | ❌ | 伏笔/数值丢失 |
| 指令 | ✅ Step 3 | ✅ Step 5 | - |
| 角色 | ✅ Step 4 | ❌ | 角色不一致 |
| 世界观 | ✅ Step 4 | ❌ | 设定漂移 |
| 伏笔 | ✅ Step 4 | ❌ | **关键伏笔断裂** |
| 大纲 | ❌ | ❌ | 剧情连贯性 |

**从 author 日志确认**：
修订第3章时，author 只执行了 `reviews` 命令，没有执行：
- `chapter_state`（状态卡）
- `characters`（角色）
- `world_settings`（世界观）
- `pending_plots`（伏笔）
- `outlines`（大纲）

### 完整修复

**author SKILL 模式B 修订后流程**：

```
Step 0: 获取项目上下文
Step 1: 提取 task_id
Step 2: ⚠️ 读取上一章状态卡（关键！修改时也要保持连续性！）
Step 3: 读取质检报告
Step 4: 读取当前草稿
Step 5: 读取原指令
Step 6: ⚠️ 读取参考资料（关键！修改时也要保持一致性！）
   - characters <project>      # 角色设定
   - world_settings <project>   # 世界观
   - pending_plots <project>    # 待处理伏笔
   - outlines <project>         # 大纲（可选）
Step 7: 针对性修改
Step 8: 确认伏笔处理
Step 9: 保存草稿
Step 10: 任务完成
```

### 修改的文件

| 文件 | 改动 |
|------|------|
| author/workspace/skills/novel-writing/SKILL.md | 模式B新增 Step 2（状态卡）和 Step 6（参考资料） |

### 教训

**修订模式必须与创作模式读取相同的数据源，确保角色、世界观、伏笔的一致性！**

---

## editor 和 planner SKILL 同步修复（2026-04-04 中午）

### 问题发现

检查 editor 和 planner 的 SKILL 后，发现类似问题：

| Agent | 问题 |
|-------|------|
| editor | 工作流程 Step 1 写的是 `task_start`，与底部"不要调用 task_start"矛盾 |
| planner | 工作流程没有明确提取 task_id 的步骤，`task_complete` 不够醒目 |

### 修复内容

| 文件 | 改动 |
|------|------|
| editor/workspace/skills/quality-review/SKILL.md | 移除错误的 `task_start`，新增 Step 1: 提取 task_id，强化 `task_complete` 警告 |
| planner/workspace/skills/chapter-planning/SKILL.md | 新增 Step 1: 提取 task_id，强化 `task_complete` 警告 |

### 统一格式

所有 Agent SKILL 现在遵循相同格式：

```
Step 0: 获取项目上下文
Step 1: ⚠️ 提取 task_id（关键！）
   - 从任务消息末尾提取
   - 找不到则查 task_list running
Step 2-N: 业务流程...
Final Step: ⚠️⚠️⚠️ 【强制最后一步】task_complete
```

### 关键警告

所有 SKILL 底部新增：

```
⚠️ 不调用 task_complete = 任务永远 running = 调度器不会派发下一个任务！
```
