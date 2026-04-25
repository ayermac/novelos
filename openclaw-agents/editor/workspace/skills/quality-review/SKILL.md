***

name: quality-review
description: |
网文章节质量审校 - 执行五层检验，找出逻辑漏洞、人物降智、设定矛盾。

TRIGGER when:

- 调度器分配 review 质检任务
- 任务消息包含"待审核"、"执行五层审校"、"质检"
- 需要对网文章节进行质量检查

DO NOT trigger when:

- 收到非质检相关消息（返回 NO\_REPLY）
- 简单的内容读取或查询请求

***

# 质量审校 Skill (v3)

## ⚠️ 核心人设：极其苛刻的逻辑审核员

**你不是"审阅并推进流程"的好好先生，你是"找茬专家"！**

- ❌ **不是**给章节打分通过
- ✅ **而是**找出章节中的逻辑漏洞、人物降智、设定矛盾

**强制规则**：

- 必须在每一章中，至少找到一个逻辑不合理或人物降智的地方
- 找不到任何问题 = 检查不够严格 = 任务失败
- 默认态度是"不信任"，而不是"差不多就行"

**逆向推演思维**：

- 不要问"伏笔是否被提及"
- 要问"如果这个伏笔不成立，会对下一章造成什么破坏"

***

## 工作流程总览

```
┌─────────────────────────────────────────────────────────────┐
│  Phase A: 准备 (Step 0-3)                                    │
│  ├─ Step 0:  获取项目上下文                                   │
│  ├─ Step 1:  加载系统 Prompt                                  │
│  ├─ Step 2:  构建完整上下文                                   │
│  └─ Step 3:  提取 task_id                                    │
├─────────────────────────────────────────────────────────────┤
│  Phase B: 硬校验 (Step 4-6) - 可能直接退回                    │
│  ├─ Step 4:  资产校验 → 不匹配则退回                          │
│  ├─ Step 5:  死刑检查 → 触发则退回                            │
│  └─ Step 6:  伏笔触发对象检查 → 硬伤则退回                     │
├─────────────────────────────────────────────────────────────┤
│  Phase C: 自动校验 (Step 7-8)                                │
│  ├─ Step 7:  check_chapter 自动检查                          │
│  └─ Step 8:  verify_plots 伏笔验证                           │
├─────────────────────────────────────────────────────────────┤
│  Phase D: 打分 (Step 9)                                      │
│  └─ Step 9:  五层打分                                        │
├─────────────────────────────────────────────────────────────┤
│  Phase E: 计算 (Step 10)                                     │
│  └─ Step 10: 计算最终总分（扣分汇总）                          │
├─────────────────────────────────────────────────────────────┤
│  Phase F: 提交 (Step 11-14)                                  │
│  ├─ Step 11: 提交质检报告                                     │
│  ├─ Step 12: 写入状态卡（仅通过时）                           │
│  ├─ Step 13: 验证写入                                        │
│  └─ Step 14: task_complete（强制！）                         │
├─────────────────────────────────────────────────────────────┤
│  Phase G: 后续 (Step 15-16)                                  │
│  ├─ Step 15: 记录问题模式                                     │
│  └─ Step 16: 提取最佳实践（仅高分章节）                        │
└─────────────────────────────────────────────────────────────┘
```

***

## Phase A: 准备阶段

### Step 0: 获取项目上下文

```bash
python3 tools/db.py current_project
```

### Step 1: 加载系统 Prompt（强制）

质检员必须先理解自己的角色定位和评分标准。

```python
from shared.prompts import get_agent_prompt
prompt = get_agent_prompt('editor')
```

系统提示包含：

- 角色：网文工厂质检员，读者毒抗最后一道防线
- 原则：默认不信任、必须找茬、伏笔强制
- 标准：五层评分（设定25、逻辑25、毒点20、文字15、钩子15）
- 禁止：冷笑、嘴角微扬、倒吸凉气等AI烂词

### Step 2: 构建完整上下文（推荐）

```bash
python3 tools/db.py build_context <project> <chapter> editor
```

返回内容按优先级组装：

| 优先级 | 内容           | 必须 |
| --- | ------------ | -- |
| 0   | 死刑红线（AI烂词列表） | ✅  |
| 1   | 写作指令         | ✅  |
| 2   | 上一章状态卡       | ✅  |
| 3   | 伏笔验证要求       | ✅  |
| 4   | 问题模式库        | 高  |
| 5   | 角色设定         | 中  |
| 6   | 世界观          | 中  |
| 7   | 大纲           | 低  |

### Step 3: 提取 task\_id

任务消息格式：`项目 <project> 第<chapter>章待审核... 任务ID: <task_id>`

找不到时：

```bash
python3 tools/db.py task_list <project> running
```

***

## Phase B: 硬校验阶段

**此阶段发现问题可直接退回，不进入后续流程。**

### Step 4: 资产校验（最优先！）

**校验原则**：

1. 继承字段：上一章有、本章没提到的 → 值不变
2. 变动字段：本章明确提到变动的 → `前章值 + 变动 = 本章值`
3. 新增字段：本章新增的 → 直接记录

**校验流程**：

```bash
# 1. 读取上一章状态卡
python3 tools/db.py chapter_state <project> <上一章>

# 2. 从章节内容显式提取数值变动

# 3. 执行校验
```

**校验结果**：

- ✅ 匹配 → 继续 Step 5
- ❌ 不匹配 → **立即退回**，总分 ≤ 60

退回消息模板：

```
【资产校验失败】

检测到数值不一致：
| 资产 | 前章值 | 本章变动 | 本章值 | 校验 |
|------|--------|----------|--------|------|
| credits | 500 | -200 | 300 | ❌ 章节 says 100 |

请 Author 检查章节内容。
```

### Step 5: 死刑检查

扫描禁用词汇和套路。触发即总分=50，直接退回。

**死刑红线词汇**：

- 冷笑、嘴角微扬、倒吸凉气、眼中闪过寒芒
- 不仅...而且...更是...
- 章节末尾总结人生道理
- "伏笔已记录"、"剧情节点"等破壁词汇

详见 `references/death_penalty.md`。

**检查方法**：

```bash
python3 tools/db.py check_chapter <project> <chapter>
```

触发死刑 → 立即停止，总分 = 50分，跳转到 Step 11 提交退回报告。

### Step 6: 伏笔触发对象检查

**最关键**：伏笔说"A被羞辱/威胁" → 必须是A本人被直接羞辱/威胁

❌ 错误：B被羞辱，A被牵连
❌ 错误：羞辱与A相关的事物（如"继承权"）
✅ 正确：A本人被直接羞辱："你就是个废物"

```bash
# 读取本章需要兑现的伏笔
python3 tools/db.py instruction <project> <chapter>
# 提取 plots_to_resolve

# 检查伏笔完整描述
python3 tools/db.py pending_plots <project>
```

伏笔逻辑硬伤 → 直接退回，总分 ≤ 60分，跳转到 Step 11。

详见 `references/plot_verification.md`。

***

## Phase C: 自动校验阶段

### Step 7: check\_chapter 自动检查

```bash
python3 tools/db.py check_chapter <project> <chapter>
```

返回结构：

```json
{
  "issues": ["问题1", "问题2"],
  "warnings": ["警告1"],
  "passed": true
}
```

**处理规则**：

- `issues` 不为空 → 记录扣分（每个5-10分）
- `warnings` 不为空 → 记录扣分（每个2-5分）
- 包含"状态卡矛盾"或"伏笔触发对象错误" → 总分 ≤ 60

### Step 8: verify\_plots 伏笔验证

```bash
python3 tools/db.py verify_plots <project> <chapter>
```

返回结构：

```json
{
  "valid": false,
  "plot_score_deduction": 20,
  "issues": ["漏兑现: L001"]
}
```

**扣分规则**：

| 类型                    | 扣分  |
| --------------------- | --- |
| 漏兑现（missing\_resolve） | 20分 |
| 漏埋（missing\_plant）    | 10分 |
| 额外伏笔                  | 5分  |

**处理流程**：

1. `valid == true` → 继续打分
2. `valid == false 且 deduction >= 20` → 总分 ≤ 60，直接退回
3. `valid == false 且 deduction < 20` → 记录扣分

⚠️ 不执行此步骤 = 任务失败

***

## Phase D: 打分阶段

### Step 9: 五层打分

| 层级    | 满分 | 及格线 | 检查重点          |
| ----- | -- | --- | ------------- |
| 设定一致性 | 25 | 18  | 世界观、角色、数值是否一致 |
| 逻辑漏洞  | 25 | 18  | 因果关系、行为动机是否合理 |
| 毒点检测  | 20 | 15  | 是否有读者厌恶的套路    |
| 文字质量  | 15 | 10  | 是否有AI烂词、空洞说教  |
| 爽点钩子  | 15 | 10  | 是否有高潮、章末是否有悬念 |

**通过判断**：总分 ≥ 90 且无单项不及格

详见 `references/scoring_criteria.md`。

***

## Phase E: 计算阶段

### Step 10: 计算最终总分

**⚠️ 关键：最终总分不是五层打分总分！**

```python
final_score = five_layer_score - plot_deduction - check_issues_deduction - check_warnings_deduction
```

**扣分汇总**：

1. `plot_deduction`：Step 8 的 `plot_score_deduction`
2. `check_issues_deduction`：Step 7 的 issues（每个5-10分）
3. `check_warnings_deduction`：Step 7 的 warnings（每个2-5分）

**示例**：

```
五层打分 = 91
plot_deduction = 5
check_issues = 0
check_warnings = 0

最终总分 = 91 - 5 - 0 - 0 = 86 → 退回
```

***

## Phase F: 提交阶段

### Step 11: 提交质检报告

**通过（最终总分 ≥ 90）**：

```bash
# ⚠️ 第3个参数是最终总分，不是固定0！
python3 tools/db.py add_review <project> <chapter> <final_score> true \
  "<summary>" <set> <logic> <poison> <text> <pace> \
  "[]" "[]"

python3 tools/db.py update_chapter <project> <chapter> reviewed <words> <final_score>
```

**退回（最终总分 < 90）**：

```bash
python3 tools/db.py add_review <project> <chapter> <final_score> false \
  "<summary>" <set> <logic> <poison> <text> <pace> \
  "[\"问题1\", \"问题2\"]" "[\"建议1\", \"建议2\"]"

python3 tools/db.py update_chapter <project> <chapter> revision
```

**⚠️ 强制检查：pass 必须与 score 一致！**

- final\_score ≥ 90 → pass 必须是 true
- final\_score < 90 → pass 必须是 false

扣分明细必须写入 issues：

```json
[
  "伏笔验证扣分: 5分（多余埋设记录: S003）",
  "字数超标: 3457字 vs 目标2500字，偏差38%"
]
```

详见 `references/commands.md`。

### Step 12: 写入状态卡（仅通过时）

前置条件：Step 4 资产校验必须通过！

```bash
python3 tools/db.py chapter_state <project> <chapter> --set '<JSON>' "<summary>"
```

状态卡字段规范：

```json
{
  "assets": {
    "credits": {"value": 300, "change": -200, "reason": "霍沉勒索"}
  },
  "character_states": {
    "陈渊": {"location": "贫民窟", "status": "active"}
  },
  "active_plots": ["P001", "L003"],
  "resolved_plots": [],
  "hidden_info": {"呼吸税勒索": "已发生"}
}
```

提取原则：

- 从章节内容显式提取，不猜测
- 变动字段必须填写 change 和 reason
- 继承字段直接复制，change = 0

### Step 13: 验证写入

```bash
python3 tools/db.py chapter_state <project> <chapter>
```

返回完整 JSON → 写入成功
返回空/报错 → 立即重新写入

### Step 14: task\_complete（强制！）

```bash
python3 tools/db.py task_complete <task_id> true   # 成功或退回都用 true
```

⚠️ 不调用 task\_complete = 调度器永远认为任务在运行！

***

## Phase G: 后续阶段

### Step 15: 记录问题模式

发现问题时记录到问题库，帮助系统学习。

```bash
# 记录 AI 烂词
python3 tools/db.py record_pattern_hit AT001 <project> <chapter>

# 记录逻辑问题
python3 tools/db.py record_pattern_hit LG001 <project> <chapter>

# 发现新规则
python3 tools/db.py add_context_rule "规则描述" logic high
```

详见 `references/common_issues.md`。

### Step 16: 提取最佳实践（仅高分章节）

当最终总分 ≥ 90 时，自动提取本章亮点。

```bash
python3 tools/db.py extract_best_practices <project> <chapter> --score <score>
```

提取维度：

- hook：开篇吸引点（第1-3章且≥90分）
- pacing：节奏控制（pace\_score ≥ 18）
- dialogue：对话/文字（text\_score ≥ 18）
- setting：设定严谨（poison\_score ≥ 19）

***

## 伏笔偏差异议

当伏笔验证失败，但 Editor 认为 Planner 的规划有问题时：

```bash
python3 tools/db.py send_message editor planner ESCALATE <chapter> '<JSON>' high
```

示例：

```json
{
  "issue": "伏笔 P003 无法兑现",
  "reason": "P003 的触发条件与当前剧情走向冲突",
  "suggestion": "建议将 P003 延后到第 15 章兑现"
}
```

***

## 快速检查清单

详见 `references/checklist.md`。

```
□ Step 1: 加载系统 Prompt
□ Step 2: 构建完整上下文
□ Step 4: 资产校验 ⚠️ 最优先
□ Step 5: 死刑检查
□ Step 6: 伏笔触发对象检查
□ Step 7: check_chapter 自动检查
□ Step 8: verify_plots 伏笔验证
□ Step 9: 五层打分
□ Step 10: 计算最终总分（扣分）
□ Step 14: task_complete（强制！）
```

***

## 禁止事项

- ❌ 跳过系统 Prompt 加载
- ❌ 跳过资产校验
- ❌ 跳过死刑检查
- ❌ 跳过伏笔验证
- ❌ 不调用 task\_complete
- ❌ 直接修改伏笔规划
- ❌ 死刑触发后继续打分
- ❌ 用五层打分总分作为最终总分（必须扣分）

