# Novel Factory v5.3 Authoring System Reset Plan

状态：v5.3.0 已实现 (2026-04-28)

目标：把 v5.2 的”可运行章节生成链路”升级为可信的小说作者工作台。v5.3 不再继续堆页面，而是重置项目创世、章节生产、质量门、人工审核、工作流可观测性和 WebUI 信息架构之间的关系。

## 背景问题

v5.2 已经补齐了真实 LLM、LangGraph、世界观/角色/大纲 CRUD、SSE、token 统计等底层能力，但真实使用中暴露出以下结构性问题：

1. 新建项目只创建 `projects + chapters`，不会自动生成完整小说骨架。
2. 新章节初始为 `planned`，路由直接进入 `screenwriter`，经常绕过 `planner`。
3. 没有世界观、角色、大纲、伏笔、章节指令时仍可生成章节。
4. `editor pass=true` 后自动进入 `publisher`，真实模式下 AI 自审自发。
5. 字数目标没有成为硬质量门，1000 字左右章节也能通过。
6. 工作流页只显示流程灯，缺少每个 Agent 的输入、输出、校验、token、耗时、失败原因。
7. 世界观/角色/大纲被塞进章节页 Tab，信息架构像“章节附属数据”，而不是项目级资料。
8. 还有大量数据库能力没有 WebUI 管理入口：伏笔、章节指令、势力、状态卡、版本、质量报告、连续性报告、人工审核记录、Agent 产物。
9. CLI 有很多零散能力，但没有统一的作者工作流命令。
10. 跨章数值和事实继承只有状态卡、fact_lock、ContinuityChecker 雏形，缺少结构化事实账本、变更审计和发布前强制连续性门禁。

## 产品原则

- 用户只需要给创作意图，不应该从空白表格手填完整小说资料。
- Planner/Genesis 应先生成项目圣经，用户审阅批准后才进入章节生产。
- 真实 LLM 模式默认不能自动发布，AI 审核通过也需要人工确认。
- 任何章节生成必须能解释“用了哪些上下文、每个 Agent 做了什么、为什么通过或失败”。
- 长篇小说中的关键事实、数值、道具、时间、伤势、等级、关系和伏笔状态必须可继承、可追踪、可审计，不能依赖模型记忆或自由文本提示。
- 项目级资料和章节级资料必须分离。
- CLI 与 WebUI 必须共享同一套业务流程，不能形成两套产品。

## v5.3 拆分

v5.3 拆成三个可验收版本，避免一次性大改失控。

| 版本 | 名称 | 核心目标 |
| --- | --- | --- |
| v5.3.0 | Trusted Generation Chain | 项目创世、Planner 必经、上下文完整性检查、字数硬闸门、禁止自动发布 |
| v5.3.1 | Project-Level Author Workspace | 重构 WebUI 信息架构，补项目级模块管理页 |
| v5.3.2 | Workflow Observability | Agent step log、产物明细、token/耗时、质量门详情、版本 diff、人工审核记录 |
| v5.3.3 | Continuity & Fact Ledger | 跨章事实/数值账本、状态继承、冲突检测、连续性发布门禁 |

## v5.3.0 Trusted Generation Chain

### 实现状态 (2026-04-28)

**已实现：**

1. **Context Readiness Gate** ✅
   - 文件：`novel_factory/validators/context_readiness.py`
   - 集成：`novel_factory/workflow/runner.py`
   - API 错误处理：`novel_factory/api/routes/run.py`
   - 检查项：项目简介、世界观设定、主角角色、大纲覆盖、写作指令（或允许 planner 入口）、字数目标

2. **Planner 必经** ✅
   - 文件：`novel_factory/workflow/conditions.py`
   - 路由逻辑：`planned + no instruction -> planner`
   - 路由逻辑：`planned + has instruction -> screenwriter`
   - 状态字段：`FactoryState.has_instruction`

3. **字数硬质量门** ✅
   - 文件：`novel_factory/validators/chapter_checker.py`
   - Author/Polisher 阈值：`word_target * 0.85`
   - Editor 阈值：`word_target * 0.90`
   - 集成：`novel_factory/agents/author.py`, `novel_factory/agents/polisher.py`, `novel_factory/agents/editor.py`

4. **禁止真实模式自动发布** ✅
   - 文件：`novel_factory/workflow/conditions.py` (`route_by_review_result`)
   - 状态字段：`FactoryState.llm_mode`
   - Real mode: `editor pass -> awaiting_publish (NOT publisher)`
   - Stub mode: `editor pass -> publisher (auto-publish retained)`

5. **Manual Publish API** ✅
   - 文件：`novel_factory/api/routes/run.py`
   - 端点：`POST /publish/chapter`
   - 仅允许 `reviewed` 状态章节发布

6. **测试覆盖** ✅
   - 文件：`tests/test_v530_trusted_generation_chain.py`
   - 测试数：29 个测试用例全部通过
   - 覆盖：Context Readiness Gate, Planner Routing, Word Count Quality Gate, Real Mode Auto-Publish Blocking

7. **WebUI 最小适配** ✅
   - 真实模式生成后显示待人工发布状态
   - Run 页面和项目工作台提供确认发布入口
   - Context Readiness Gate 失败时展示缺失项与建议操作

8. **Checkpoint 路径收口** ✅
   - 文件：`novel_factory/workflow/checkpoint.py`, `novel_factory/workflow/runner.py`
   - Checkpoint DB 跟随主 DB 路径，例如 `novelos.db -> novelos.checkpoints.db`
   - `:memory:` 主库不落地 checkpoint 文件

**未实现（v5.3.1 范围）：**
- Project Genesis（项目创世）

**验收结果（2026-04-28）：**
- `python3 -m pytest -q` → 1471 passed
- `cd frontend && npm run typecheck` → passed
- `cd frontend && npm run build` → passed
- Stub CLI smoke：章节生成到 `published`，`awaiting_publish=false`
- Real CLI smoke：真实 LLM 输出不合格时干净停到 `blocking` + `requires_human=true`，未再触发 GraphRecursion

### v5.3.0 状态语义说明

**核心决策：** v5.3.0 采用 `reviewed + awaiting_publish=true` 组合表示真实模式 AI 审核通过、等待人工发布，而不新增 `awaiting_human_review` 作为 DB 章节状态值。

**理由：**
- 避免大规模状态机、迁移、前端、测试变更
- `awaiting_human_review` 是产品语义，不作为本轮 DB 状态新增值
- 兼容现有 `reviewed -> published` 转移路径

**状态映射：**

| 后端 DB 状态 | API/前端展示语义 | 说明 |
|---|---|---|
| `reviewed` + `awaiting_publish=true` | "待人工发布" | 真实模式 AI 审核通过，等待人工确认发布 |
| `reviewed` + `awaiting_publish=false` | "待发布" | 演示模式或其他场景的已审核状态 |
| `published` | "已发布" | 已正式发布 |
| `blocking` | "已阻塞" | 需人工介入 |

### 目标

确保系统不会在缺少小说骨架、章节指令、字数目标或人工确认的情况下生产并发布章节。

### 范围

#### 1. Project Genesis

新增项目创世能力，从一句创作意图生成项目圣经草案。

输入：

- 小说名称或临时标题
- 类型
- 创作意图
- 篇幅目标
- 风格偏好
- 可选约束：人称、节奏、禁忌、目标读者

输出并写入草案表或 pending 状态记录：

- 项目简介
- 核心卖点
- 世界观规则
- 主角/配角/反派
- 势力/组织
- 总体大纲
- 分卷/阶段大纲
- 前 10 章章节指令
- 伏笔/钩子计划
- 风格指南初稿

建议新增状态：

- `project.status = draft | planning_generated | active | archived`
- `genesis_status = not_started | running | generated | approved | rejected`

验收：

- 新建项目默认进入草案状态，不直接进入 active。
- 用户输入一句创意后可生成项目圣经。
- 生成结果不会直接覆盖已批准资料，必须用户确认。
- 批准后写入 `world_settings / characters / factions / outlines / plot_holes / instructions / style_bibles`。

#### 2. Context Readiness Gate

新增章节运行前置检查。运行章节前必须验证：

- 项目简介存在。
- 世界观至少 1 条。
- 主角至少 1 个。
- 大纲覆盖当前章节。
- 当前章节 instruction 存在。
- 字数目标明确。
- 风格指南存在，或用户明确选择跳过。

失败时返回结构化错误：

```json
{
  "ok": false,
  "error": {
    "code": "PROJECT_CONTEXT_INCOMPLETE",
    "message": "项目资料不完整，无法生成章节",
    "details": {
      "missing": ["world_settings", "characters", "instructions"],
      "actions": ["generate_genesis", "add_character", "plan_chapter"]
    }
  }
}
```

验收：

- 空骨架项目不能进入 `screenwriter/author`。
- WebUI 能显示缺失项和补齐入口。
- CLI 返回同样的错误 envelope。

#### 3. Planner 必经

调整章节状态模型：

- 新章节初始状态改为 `idea` 或 `unplanned`。
- `idea/unplanned -> planner`
- Planner 生成 `instructions` 后进入 `instruction_ready` 或 `planned`。
- `planned -> screenwriter` 只允许在 instruction 存在时发生。

兼容：

- 旧 `planned` 章节如果没有 instruction，先回到 planner。
- 旧 `planned` 章节如果已有 instruction，可继续 screenwriter。

验收：

- 新项目第 1 章必须先出现 Planner step。
- 章节没有 instruction 时不能直接进入 Screenwriter。
- Planner 产物可在 WebUI 和 CLI 查看。

#### 4. 字数硬闸门

将 `word_target` 变成硬质量门。

建议规则：

- `word_target` 默认来自项目目标：`target_words / total_chapters_planned`，最小不低于配置值。
- Author/Polisher 输出低于 `word_target * 0.85` 时失败。
- Editor 输出低于 `word_target * 0.9` 时不得 pass。
- Stub 模式可以降低阈值，但必须明确标注演示阈值。

验收：

- `word_target=2500` 时，1000 字章节不能通过 Editor。
- 失败原因必须显示“字数不足”。
- 字数校验写入质量报告和工作流日志。

#### 5. AI 审核与人工发布分离

真实模式默认禁用自动发布。

推荐状态：

- `drafted`
- `polished`
- `ai_reviewed`
- `reviewed`（配合 `awaiting_publish=true` 表示待人工发布）
- `published`
- `revision`
- `blocking`

流程：

```text
screenwriter -> author -> polisher -> editor
                                    |
                              [pass + llm_mode=real]
                                    |
                         reviewed + awaiting_publish=true
                                    |
                              [人工发布操作]
                                    |
                                 published
```

规则：

- Editor pass 后设置 `awaiting_publish=true`，状态为 `reviewed`（真实模式不自动发布）。
- 用户在 WebUI 点击发布后才变为 `published`。
- 用户可退回修改，生成 `chapter_review_notes` 并进入 `revision`。
- `auto_publish=true` 只允许在配置中显式开启，且 UI 必须显示风险提示。

验收：

- 真实模式生成后不会自动发布。
- Review/项目工作台能发布或退回。
- 发布记录包含操作者、时间和来源。

## v5.3.1 Project-Level Author Workspace

### 目标

把 WebUI 从“章节页面挂一堆 Tab”重构为项目级作者工作台。

### 信息架构

项目页应包含：

- 总览
- 章节
- 世界观
- 角色
- 势力
- 大纲
- 伏笔/钩子
- 章节指令
- 风格指南
- 审核
- 运行记录
- 设置

章节页只包含：

- 正文
- 当前章指令
- 当前章 scene beats
- 当前章工作流
- 当前章版本
- 当前章审核意见

### 必补模块

| 模块 | 数据表 | API 状态 | WebUI 状态 | v5.3.1 要求 |
| --- | --- | --- | --- | --- |
| 世界观 | `world_settings` | 已有 CRUD | 放错位置 | 迁移为项目级模块 |
| 角色 | `characters` | 已有 CRUD | 放错位置 | 迁移为项目级模块 |
| 大纲 | `outlines` | 已有 CRUD | 放错位置 | 迁移为项目级模块 |
| 势力 | `factions` | 缺主 API | 缺 UI | 新增 CRUD |
| 伏笔/钩子 | `plot_holes` | 缺主 API | 缺 UI | 新增 CRUD |
| 章节指令 | `instructions` | 缺主 API | 缺 UI | 新增 CRUD/生成入口 |
| 状态卡 | `chapter_state` | 缺主 API | 缺 UI | 新增只读/历史入口 |
| 版本 | `chapter_versions` | 缺主 API | 缺 UI | 新增版本列表和 diff |
| 质量报告 | `quality_reports` | 部分能力 | 缺 UI | 新增报告页 |
| 连续性报告 | `continuity_reports` | 部分能力 | 缺 UI | 新增报告页 |
| 人工审核 | `human_review_sessions` | 部分能力 | 弱 | 融入审核中心 |
| Agent 产物 | `agent_artifacts` | 弱 | 弱 | 工作流详情展示 |

### 高级运行

`/run` 不应作为主导航项。处理方式：

- 从主导航移除。
- 放入“开发工具”或“项目设置 > 调试运行”。
- 默认隐藏，开启 developer mode 后显示。

验收：

- 用户从创作中心进入项目后，看到的是项目级模块。
- 世界观/角色/大纲不再表现为当前章节的 Tab。
- `/run` 不再干扰日常创作主路径。
- 所有项目级模块有空状态、创建入口、编辑入口、删除确认。

## v5.3.2 Workflow Observability

### 目标

让用户能看到每个流程和 Agent 到底做了什么，而不是只看到流程灯。

### 数据模型

建议新增或扩展 `workflow_steps` 表：

```sql
CREATE TABLE workflow_steps (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    agent_id TEXT NOT NULL,
    status_before TEXT,
    status_after TEXT,
    started_at DATETIME,
    completed_at DATETIME,
    duration_ms INTEGER DEFAULT 0,
    model TEXT,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    input_context_summary TEXT,
    input_fragments_json TEXT DEFAULT '[]',
    output_artifact_id TEXT,
    output_summary TEXT,
    validation_results_json TEXT DEFAULT '[]',
    quality_gate_json TEXT DEFAULT '{}',
    warnings_json TEXT DEFAULT '[]',
    error TEXT,
    requires_human INTEGER DEFAULT 0
);
```

### 每个 Agent 必须记录

- Planner：生成了哪些章节指令、伏笔计划、字数目标。
- Screenwriter：拆了哪些 scene beats，引用哪些指令/伏笔。
- Author：实现了哪些关键事件，生成字数，使用哪些角色/世界观。
- Polisher：改了什么，是否改变事实。
- Editor：每个审核维度分数、硬规则结果、失败原因、建议。
- Publisher：谁确认发布，发布时间，发布版本。

### WebUI 工作流页

工作流页应支持：

- 步骤时间线。
- 展开每个步骤。
- 查看输入上下文摘要。
- 查看输出产物摘要。
- 查看校验结果。
- 查看 token 和耗时。
- 查看错误、警告、人工介入原因。
- 跳转到对应章节版本、审核报告、Agent 产物。

验收：

- 真实 LLM 运行后，工作流页不再只有 5 个绿色节点。
- 每个完成节点至少有输出摘要、token、耗时和产物引用。
- Editor 节点必须展示字数门、上下文完整性门、指令覆盖门。
- 用户能解释“为什么这章通过/失败/待审”。

## v5.3.3 Continuity & Fact Ledger

### 目标

把现有的 `chapter_state`、`fact_lock`、`state_verifier`、`ContinuityChecker` 从“旁路质量工具”升级为长篇小说创作的核心连续性系统。系统必须能明确回答：

- 当前章继承了哪些事实和数值。
- 本章新增、修改、消耗、解决了哪些事实。
- 某个数值为什么从 A 变成 B。
- 某个角色、道具、地点、倒计时、等级、伤势、关系、伏笔状态是否前后一致。
- 发布前是否通过连续性门禁。

### 当前保留但不足的能力

已存在：

- `chapter_state`：保存每章结束状态卡。
- `EditorAgent`：审核通过时保存 `state_card`。
- `Author/Screenwriter/Editor`：可读取上一章状态卡作为上下文。
- `fact_lock`：可锁定部分事件、伏笔引用、等级和关系。
- `state_verifier`：可做基础状态一致性检查。
- `ContinuityChecker` / `continuity_reports`：可做跨章旁路检查。

不足：

- 没有通用事实账本，无法结构化追踪任意数值和状态。
- `fact_lock` 只覆盖少量字段，不适合倒计时、资产、伤势、道具数量、任务进度等复杂状态。
- 部分质量检查仍从旧 `chapter.metadata.state_card` 路径取状态，可能没有使用 `chapter_state`。
- ContinuityChecker 不在每章主链路中强制运行。
- WebUI 没有展示继承事实、事实变更、冲突和连续性报告。

### 数据模型

建议新增 `story_facts` 表，保存当前项目事实账本：

```sql
CREATE TABLE story_facts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    fact_key TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    subject TEXT,
    attribute TEXT,
    value_json TEXT NOT NULL,
    unit TEXT,
    scope TEXT DEFAULT 'global',
    status TEXT DEFAULT 'active',
    confidence REAL DEFAULT 1.0,
    source_chapter INTEGER,
    source_agent TEXT,
    last_changed_chapter INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

建议新增 `story_fact_events` 表，记录事实变更流水：

```sql
CREATE TABLE story_fact_events (
    id TEXT PRIMARY KEY,
    fact_id TEXT,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    run_id TEXT,
    agent_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT,
    rationale TEXT,
    evidence_text TEXT,
    validation_status TEXT DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

事实类型至少覆盖：

- `time_counter`：倒计时、天数、时间线。
- `resource`：金钱、灵石、弹药、库存数量。
- `inventory`：道具获得、消耗、丢失、损坏。
- `character_state`：伤势、境界、能力、心理状态。
- `relationship`：角色关系、阵营关系、仇恨/信任变化。
- `location`：当前位置、已探索地点、不可达地点。
- `quest`：主线/支线目标进度。
- `plot_hook`：伏笔 planted/resolved/abandoned。
- `world_rule`：世界规则、限制、例外。

### 工作流规则

章节生成前：

- ContextBuilder 必须读取 `story_facts` 当前有效事实。
- Planner/Screenwriter 必须显式声明本章会读取和可能修改的事实。
- 如果项目没有事实账本，Genesis 或 Planner 必须从项目圣经和上一章状态初始化。

Agent 输出时：

- Planner 输出 `planned_fact_changes`。
- Screenwriter 输出 `expected_fact_usage`。
- Author 输出 `observed_fact_changes`。
- Polisher 必须证明没有无意改变关键事实。
- Editor 必须执行事实差异审核。
- ContinuityChecker 必须对本章事实事件与历史事实账本做冲突检测。

发布前：

- 真实模式下，连续性门禁必须通过或由人工明确覆盖。
- 数值冲突、死亡角色复活、道具重复获得、倒计时回退、等级跳变、关系反转等必须阻止自动发布。
- 人工覆盖必须写入 `story_fact_events`，包含原因。

### WebUI 要求

项目级新增“事实账本/连续性”模块：

- 按类型查看当前事实。
- 查看某个事实的完整变更历史。
- 查看冲突列表和待确认变更。
- 支持人工修正事实值，并要求填写原因。
- 支持将事实标记为 active/resolved/deprecated。

章节工作流页新增：

- 本章继承事实。
- 本章新增事实。
- 本章修改事实。
- 本章消耗/解决事实。
- 连续性校验结果。
- 人工覆盖记录。

章节正文页新增：

- 可从正文片段跳到相关事实。
- 展示“本章状态变化摘要”，例如倒计时、地点、道具、伤势、关系变化。

### CLI 对齐

新增或整理命令：

- `novelos facts list --project-id`
- `novelos facts show --project-id --fact-key`
- `novelos facts history --project-id --fact-key`
- `novelos facts reconcile --project-id --chapter`
- `novelos continuity check --project-id --chapter`
- `novelos continuity approve-override --project-id --chapter --reason`

要求：

- CLI 和 WebUI 使用同一套 fact ledger service。
- 所有冲突返回 JSON envelope。
- 不允许 CLI 发布绕过连续性门禁。

### 验收

- 第 1 章写入倒计时、道具、地点、目标后，第 2 章必须继承这些事实。
- 第 2 章不能把 `23:50:00` 无理由改回 `24:00:00`。
- 已消耗的道具不能无记录再次出现。
- 角色死亡、重伤、关系破裂、境界变化等必须进入事实事件流。
- Editor 通过但连续性门禁失败时，真实模式不能发布。
- WebUI 能展示本章事实变更和冲突原因。
- 人工覆盖后，覆盖原因可在事实历史中追踪。
- 全量 pytest、前端 typecheck、前端 build 通过。

## CLI 对齐

新增或整理命令：

- `novelos project genesis`
- `novelos project context-status`
- `novelos project approve-genesis`
- `novelos chapter plan`
- `novelos chapter run`
- `novelos chapter review`
- `novelos chapter publish`
- `novelos runs show --detail`
- `novelos facts list/show/history/reconcile`
- `novelos continuity check/approve-override`

要求：

- CLI 和 WebUI 使用同一套 service/API，不复制业务逻辑。
- 所有命令支持 JSON envelope。
- 真实模式错误必须可读，不泄露 API key。

## 测试策略

### Python

新增专项测试：

- `test_v53_project_genesis.py`
- `test_v53_context_readiness_gate.py`
- `test_v53_planner_required.py`
- `test_v53_quality_gates.py`
- `test_v53_human_publish_gate.py`
- `test_v53_workflow_steps.py`
- `test_v53_cli_author_workflow.py`
- `test_v53_fact_ledger.py`
- `test_v53_continuity_gate.py`

### Frontend

新增测试：

- 项目级模块导航存在。
- 世界观/角色/大纲不在章节 Tab 中。
- 缺上下文时显示补齐入口。
- 生成后真实模式显示“待人工审核”，不是“已发布”。
- 工作流节点可展开并显示明细。
- 事实账本能展示当前事实、事实历史和本章变更。
- 连续性冲突能阻止发布并显示人工覆盖入口。
- 高级运行不在主导航。

### Real LLM Smoke

保留人工触发，不进默认 CI：

1. 创建新项目。
2. 生成项目圣经。
3. 批准项目圣经。
4. 生成第 1 章。
5. 验证章节状态为 `reviewed`，`awaiting_publish=true`。
6. 查看工作流明细。
7. 查看本章事实变更和连续性校验结果。
8. 人工发布。
9. 验证状态为 `published`。

## 非目标

- 不做多人协作权限系统。
- 不做云端部署。
- 不做商业支付或订阅。
- 不彻底移除 Dispatcher 兼容路径。
- 不把所有历史 CLI 一次性重构完。

## 完成定义

v5.3 完成时应满足：

- 空项目不能生成章节。
- 新项目能从一句创意生成项目圣经。
- Planner 是章节生产必经流程。
- 字数不达标不能通过审核。
- 真实模式 AI 审核通过后不会自动发布。
- 用户可以在 WebUI 中管理项目级世界观/角色/大纲/势力/伏笔/章节指令。
- 工作流详情能解释每个 Agent 做了什么。
- 系统能继承并审计跨章事实/数值变化，连续性冲突不能静默发布。
- CLI 和 WebUI 主流程一致。
- 全量 pytest、前端 typecheck、前端 build 通过。
