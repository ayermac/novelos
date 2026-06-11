# Novel Factory v6.10.5 Story Contract Governance Plan

## 背景

v6.10.3 到 v6.10.4 解决了工作流恢复、记忆链路、发布入口和风格管理的稳定性问题。最新章节质量复盘暴露出一个更底层的问题：系统可以稳定地产出章节，但章节可能稳定地偏离本书的核心爽点。

以《开局签到就无敌》的后段章节为样本，问题不是“倒计时”这个元素本身，而是“压力机制连续替代核心循环”：

- 倒计时、命债、替名、锚点规则不断扩展。
- 签到、奖励、权力兑现、敌人反噬的核心爽点被压低。
- 连续性、事实、记忆、风格都能通过，但读者承诺发生漂移。

这不是单本小说的特例。换成其他类型也会出现同类问题：

- 言情文可能被误会机制长期替代关系推进。
- 悬疑文可能被新谜题长期替代线索兑现。
- 玄幻升级文可能被设定解释长期替代突破和战力兑现。
- 商战文可能被危机堆叠长期替代筹码获取和反制。

v6.10.5 的目标是：**把“创作合同”从展示型配置升级为可执行的 Story Contract Governance，让每本书的核心循环持续约束 planner、screenwriter、author、editor 和 quality gate。**

## 核心判断

不能把具体元素写成系统级规则。

错误方向：

```text
倒计时不能连续两章成为唯一主线。
```

正确抽象：

```text
压力机制不能连续多章替代本书核心循环。
辅助机制必须服务于核心兑现，而不能成为章节唯一主体。
```

“倒计时”只是辅助机制的一种。系统需要识别的是更抽象的漂移模式：

- `pressure_mechanism_dominance`：压力机制主导章节。
- `core_payoff_missing`：本章没有兑现核心读者承诺。
- `new_mechanism_overload`：新规则/新机制过多。
- `payoff_gap`：连续多章没有阶段性回报。
- `protagonist_agency_gap`：主角长期被动应对。
- `promise_drift`：章节目标偏离项目承诺。

## 现有基础

v6.9.0 已经引入创作合同和节奏预算，v6.10.5 不应另起一套系统，而应强化已有链路。

已有能力：

- `ProjectLaunchProfile.primary_payoff_loop`：主要回报循环。
- `ProjectLaunchProfile.hard_do_not_drift_rules`：不可偏离规则。
- `GenreContract.must_have_beats`：类型必备节拍。
- `GenreContract.forbidden_drift`：禁止漂移。
- `GenreContract.payoff_cadence` / `pressure_limits`：回报和压力节奏。
- `ChapterBrief.tier1.reader_payoff`：单章读者回报。
- `RhythmBudgetResult`：压力、回报、升级、谜题等节奏预检。
- `CreativeContractsModule`：项目页已有创作合同查看/生成/审批入口。

现有缺口：

- 创作合同字段偏“文本描述”，缺少可执行结构。
- ChapterBrief 只要求章节目标和读者回报，没有明确“本章执行核心循环哪一步”。
- rhythm budget 依赖章节 metadata，真实章节很可能没有可靠写入 `has_payoff`、`has_visible_upgrade` 等字段。
- Editor 审核可以通过文字质量和连续性，但没有强制检查“本章是否履行本书核心循环”。
- UI 只能生成和审批合同，缺少人工修正核心循环、辅助机制、漂移规则的编辑入口。

## 目标

1. 把项目级创作合同升级为结构化 `StoryContract`。
2. 每个项目明确“核心循环”和“辅助机制”，但不把具体题材元素写死进系统。
3. Planner 生成章节任务时必须声明本章核心兑现。
4. Screenwriter 拆 scene beat 时必须安排核心兑现发生在哪些场景。
5. Author 写正文时必须完成核心兑现，而不是只堆危机或新设定。
6. Editor/QualityGate 检查章节是否履行本书合同。
7. Creative Ledger 持久化每章核心兑现、辅助机制、新机制、漂移信号，供后续章节和趋势检查使用。
8. 页面允许用户查看、编辑、确认本书的核心循环合同。

## 非目标

- 不为《开局签到就无敌》写死“签到”规则。
- 不禁止倒计时、追杀、误会、欠债、诅咒等压力机制。
- 不把所有创作建议都变成 blocking。
- 不要求 LLM 自动覆盖用户确认过的合同。
- 不重写 v6.9.0 创作合同表结构，优先兼容扩展。
- 不在本版本做复杂的全文商业评分系统。

## 设计原则

### 1. 合同管“写什么不能偏”，风格圣经管“怎么写”

- Style Bible：语气、行文、对白、AI 味、句式。
- Story Contract：类型承诺、核心循环、读者回报、漂移边界。

二者都进入 prompt，但职责不能混用。

### 2. 核心循环优先于压力机制

压力机制可以存在，但必须服务于核心循环。

示例：

```json
{
  "core_loop": [
    "触发核心机会",
    "完成核心动作",
    "获得明确收益",
    "兑现收益",
    "外部反馈",
    "下一章钩子"
  ],
  "supporting_mechanisms": [
    "倒计时",
    "追杀",
    "债务",
    "谜题",
    "势力压迫"
  ],
  "drift_rules": [
    "辅助机制不能替代核心循环",
    "连续2章内必须至少完成一次核心兑现",
    "单章新增核心机制不超过1个",
    "压力主导章节必须同时带来阶段性胜利或明确收益"
  ]
}
```

### 3. 不依赖单次 LLM 判断

创作漂移要分层判断：

- 结构层：ChapterBrief 是否声明核心兑现。
- 内容层：章节正文是否出现兑现证据。
- 趋势层：连续章节是否有 payoff gap 或 pressure dominance streak。
- 人工层：用户可修正合同和章节标签。

### 4. 默认先诊断，再逐步阻断

v6.10.5 初期不应大幅增加阻塞率：

- 单章轻微偏移：warning + editor advice。
- 连续偏移：revision to planner/author。
- 合同缺失：preflight warning，不阻断旧项目。
- 合同已确认且连续违反：quality gate blocking。

## P0 交付范围

### 1. StoryContract 数据结构

新增或扩展模型：

```python
class CoreLoopStep(BaseModel):
    id: str
    label: str
    description: str = ""
    payoff_type: str = ""
    required: bool = True

class SupportingMechanism(BaseModel):
    id: str
    label: str
    description: str = ""
    allowed_role: str = "pressure"
    must_serve_core_loop: bool = True

class DriftRule(BaseModel):
    id: str
    description: str
    severity: str = "warning"
    window_chapters: int = 1
    threshold: int = 1

class StoryContract(BaseModel):
    project_id: str
    core_promise: str = ""
    core_loop: list[CoreLoopStep] = []
    supporting_mechanisms: list[SupportingMechanism] = []
    payoff_types: list[str] = []
    drift_rules: list[DriftRule] = []
    cadence: dict[str, int] = {}
    status: str = "draft"
    version: str = "1.0.0"
```

兼容策略：

- 不新建表也可先存为 `project_creative_contracts.contract_type = "story_contract"`。
- 老项目没有 `story_contract` 时，从 `launch_profile` 和 `genre_contract` 派生只读 fallback。
- 已有 `primary_payoff_loop` 继续保留，作为 `core_promise` 来源。

### 2. 合同生成与修正

修改 Genesis/合同生成逻辑：

- 生成 `launch_profile` 和 `genre_contract` 后，同时生成 `story_contract`。
- LLM prompt 必须要求输出：
  - 本书核心承诺。
  - 核心循环步骤。
  - 辅助机制列表。
  - 漂移风险。
  - 连续章节节奏约束。
- Stub 模式根据 genre profile 生成稳定默认值。

示例：都市系统签到爽文应生成：

```json
{
  "core_promise": "主角通过签到获得可见奖励，并用奖励完成权力兑现和敌方反噬。",
  "core_loop": [
    {"id": "trigger", "label": "触发签到机会"},
    {"id": "action", "label": "完成签到"},
    {"id": "reward", "label": "获得明确奖励"},
    {"id": "cash_out", "label": "使用奖励兑现权力"},
    {"id": "reaction", "label": "敌人或势力受到反馈"},
    {"id": "hook", "label": "留下下一处签到或更高危机"}
  ],
  "supporting_mechanisms": [
    {"id": "countdown", "label": "倒计时", "allowed_role": "pressure"},
    {"id": "debt", "label": "命债", "allowed_role": "pressure"},
    {"id": "mystery", "label": "锚点谜团", "allowed_role": "reveal"}
  ],
  "drift_rules": [
    {"id": "pressure_not_primary", "description": "压力机制不能连续替代核心循环"},
    {"id": "payoff_within_window", "description": "连续2章内必须至少完成一次核心兑现"},
    {"id": "new_mechanism_budget", "description": "单章新增核心机制不超过1个"}
  ]
}
```

注意：这只是该项目的合同样例，不是系统内置硬编码。

### 3. ChapterBrief 扩展

扩展 `ChapterBriefTier1`：

- `core_loop_target`: 本章必须推进的核心循环步骤。
- `primary_payoff`: 本章承诺给读者的明确回报。
- `payoff_evidence_plan`: 正文中如何可见地兑现。

扩展 `ChapterBriefTier2`：

- `supporting_mechanisms_used`: 本章允许使用哪些辅助机制。
- `new_mechanisms_allowed`: 本章允许新增哪些机制，默认最多 1 个。
- `drift_risks`: 本章最可能跑偏的风险。
- `contract_checklist`: 给 author/editor 的简短验收清单。

兼容策略：

- 老 brief 没有新字段时，从 `reader_payoff`、`payoff_budget`、`upgrade_or_skill_use` 推断。
- 缺失新字段不直接阻断旧项目，但对已确认 `story_contract` 的项目进入 planner repair。

### 4. Prompt 注入

统一通过 `AgentContextBuilder` 注入 Story Contract。

Planner 看到：

- 本书核心承诺。
- 核心循环步骤。
- 回报节奏要求。
- 漂移规则。
- 最近 3 章核心兑现趋势。

Screenwriter 看到：

- 本章 core_loop_target。
- 每个 scene beat 应服务哪一步。
- 禁止把辅助机制写成唯一主线。

Author 看到：

- 本章必须兑现什么。
- 哪个场景必须写出兑现证据。
- 允许出现的辅助机制。
- 不允许新增的规则/概念。

Editor 看到：

- 本章验收清单。
- 需要判断：是否完成核心兑现、是否辅助机制喧宾夺主、是否新增机制过载。

### 5. Core Loop Checker

新增 `core_loop_checker`，定位为“项目合同合规检查”，不是通用文学评分。

输入：

```json
{
  "project_id": "novel_x",
  "chapter_number": 20,
  "content": "...",
  "story_contract": {...},
  "chapter_brief": {...},
  "recent_contract_metrics": [...]
}
```

输出：

```json
{
  "passed": true,
  "score": 82,
  "core_payoff_present": true,
  "core_loop_steps_completed": ["cash_out", "reaction"],
  "supporting_mechanism_dominance": false,
  "new_mechanism_count": 1,
  "protagonist_agency_present": true,
  "warnings": [],
  "blocking_issues": []
}
```

判断层级：

- P0 deterministic：基于 ChapterBrief、ledger metadata、最近章节指标。
- P1 LLM-assisted：当 deterministic 无法确认正文是否兑现时，调用低温 JSON 分类。
- P2 trend gate：连续偏移才进入 blocking。

### 6. Creative Ledger 扩展

每章发布或审核后记录：

- `core_payoff_present`
- `payoff_type`
- `core_loop_steps_completed`
- `supporting_mechanisms_used`
- `dominant_mechanism`
- `new_mechanisms_introduced`
- `protagonist_agency`
- `contract_drift_warnings`

这些数据用于：

- 下一章 planner 上下文。
- RhythmBudget 趋势检查。
- Run Doctor 解释“为什么章节越写越偏”。
- 项目页展示“核心循环健康度”。

### 7. UI：创作合同可编辑

扩展项目页“创作合同”模块：

- 展示 `StoryContract`。
- 支持编辑：
  - 核心承诺。
  - 核心循环步骤。
  - 辅助机制。
  - 漂移规则。
  - 节奏阈值。
- 支持“AI 生成建议，但用户确认后生效”。
- 显示最近章节合同健康：
  - 最近几章是否完成核心兑现。
  - 是否连续压力主导。
  - 是否新增机制过多。
  - 下一章建议修正方向。

### 8. 工作流接入点

建议接入顺序：

1. `task_discovery`：检查 story contract 是否存在，缺失则使用 fallback。
2. `planner`：生成/修复 ChapterBrief 时强制带 core loop fields。
3. `rhythm_budget_preflight`：读取 contract metrics，提前发现趋势风险。
4. `screenwriter`：scene beat 必须映射 core loop target。
5. `author`：正文 prompt 必须包含本章核心兑现要求。
6. `editor`：运行 core_loop_checker，输出 review issue。
7. `quality_gate`：连续违反或确认合同下严重违反时进入 revision。
8. `publisher` / `memory_curator` 后：更新 creative ledger contract metrics。

## P1 交付范围

### 1. 项目级合同模板库

按大类提供默认模板：

- 都市系统爽文。
- 玄幻/仙侠升级文。
- 悬疑推理。
- 言情/甜宠/虐恋。
- 商战/权谋。
- 末世/生存。

模板只提供抽象核心循环，不写具体小说元素。

### 2. Drift Trend Report

Run Doctor 增加“创作漂移诊断”：

- 最近 N 章核心兑现次数。
- 压力机制主导章节数量。
- 新机制引入数量。
- 主角主动性趋势。
- 与合同最不一致的章节。
- 下一章修正建议。

### 3. Human Review 辅助入口

当 core loop checker 连续失败：

- 显示“修正合同”与“返修章节”两个入口。
- 如果用户认为合同错了，修改合同。
- 如果合同没错，返修章节。

避免系统把错误合同当成硬约束无限返修。

## P2 交付范围

### 1. 自动合同进化建议

系统可以根据已发布章节提出合同修改建议，但不能自动覆盖：

- 新增辅助机制。
- 调整回报节奏。
- 合并重复机制。
- 降低误伤规则。

### 2. 类型质量仪表盘

项目页新增长期趋势：

- 核心兑现密度。
- 读者回报间隔。
- 主角能动性。
- 机制复杂度。
- 设定解释比例。
- 章节钩子质量。

## 数据与迁移策略

优先不新增复杂表结构：

- 使用现有 `project_creative_contracts` 存储 `story_contract`。
- 使用现有 creative ledger 或 chapter metadata 记录章节合同指标。
- 如果现有 ledger 结构不足，再新增轻量 `chapter_contract_metrics` 表。

兼容旧项目：

- 没有 `story_contract`：从 `launch_profile`、`genre_contract`、项目 genre 派生 fallback。
- 没有 creative ledger metrics：checker 只检查当前章节和 brief，不做趋势 blocking。
- 没有用户确认：只 warning，不 blocking。

## 测试计划

### Python 单元测试

- `tests/test_v6105_story_contract_models.py`
  - StoryContract schema。
  - fallback from launch_profile / genre_contract。
  - backward compatibility。

- `tests/test_v6105_chapter_brief_contract.py`
  - Planner output normalization。
  - missing core_loop fields repair。
  - old brief compatibility。

- `tests/test_v6105_core_loop_checker.py`
  - core payoff present。
  - supporting mechanism dominance。
  - new mechanism budget。
  - pressure-only streak。
  - trend blocking only after threshold。

- `tests/test_v6105_workflow_contract_injection.py`
  - planner/screenwriter/author/editor prompt contains Story Contract。
  - author plain-text path still receives contract context。

### Frontend 测试

- `CreativeContractsModule` 显示 Story Contract。
- 编辑核心循环步骤。
- 编辑辅助机制和漂移规则。
- 保存后重新加载不丢字段。

### 回归测试

- 现有 v6.9.0 创作合同测试继续通过。
- 现有 rhythm budget 测试继续通过。
- 现有 Style Bible v6.10.4 测试继续通过。
- 旧项目无 story_contract 时不阻塞生产。

### 真实样本验收

使用《开局签到就无敌》作为“压力机制漂移”样本，但不把其具体词写入系统：

- 后段章节应被诊断为 supporting mechanism dominance。
- 系统应指出“压力机制替代核心兑现”，而不是只提示“倒计时太多”。
- 下一章 brief 应要求重新执行核心兑现。

## 验收标准

1. 新项目生成创作合同时，同时生成可编辑 Story Contract。
2. 章节生产 prompt 中包含 Story Contract，且不同 agent 接收不同粒度。
3. Planner 输出的 ChapterBrief 明确声明本章核心兑现。
4. Core Loop Checker 能区分“压力机制服务核心循环”和“压力机制替代核心循环”。
5. 连续偏移会触发可解释的 revision，不会静默通过。
6. 旧项目没有 Story Contract 不会被硬阻断。
7. 用户可以在页面修正合同，系统后续按修正后的合同执行。
8. 文档说明清楚：Story Contract 不是 Style Bible，二者职责不同。

## 风险与缓解

### 风险 1：误伤创作自由

缓解：

- 默认 warning。
- 只有用户确认合同且连续违反才 blocking。
- 用户可修改合同。

### 风险 2：LLM 分类不稳定

缓解：

- deterministic + ledger 优先。
- LLM 只做辅助分类。
- 分类结果必须带证据句。

### 风险 3：合同生成不准确

缓解：

- UI 必须可编辑。
- 生成后状态为 `draft` 或 `needs_review`。
- 未确认合同不做硬阻断。

### 风险 4：又变成复杂配置负担

缓解：

- 页面提供“简洁模式”：只编辑核心承诺、核心循环、漂移规则。
- 高级字段默认折叠。
- AI 只给建议，不强迫用户手填所有字段。

## 建议实施顺序

1. 模型与 fallback：StoryContract + 从旧合同派生。
2. Prompt 注入：先让 planner/screenwriter/author/editor 都能看到。
3. ChapterBrief 扩展：要求本章核心兑现。
4. Core Loop Checker：先 warning，再接 revision。
5. Creative Ledger 指标：为趋势检查提供数据。
6. UI 编辑：让用户能修合同。
7. Run Doctor：解释创作漂移和下一步动作。

## 版本定位

v6.10.5 不是修某本小说，也不是增加一个新的质量 skill。它是把“每本书自己的商业承诺和核心循环”变成系统级可执行约束。

预期结果：

- 下一本小说不会因为系统默认偏好而漂移成别的类型。
- 压力机制、新设定、谜题、倒计时都可以写，但不能长期替代本书核心兑现。
- 用户能看见并修正系统认为的“本书应该怎么写”，而不是只能在章节失败后猜原因。
