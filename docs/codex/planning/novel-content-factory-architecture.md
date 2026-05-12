# 多 Agent 小说内容生产工厂架构规划

## 1. 目标与设计原则

本文档规划一个基于 **LangGraph + OpenClaw 角色范式** 的小说内容生产工厂系统，用于协同完成从市场洞察、选题策划、世界观搭建、章节编剧、正文写作、润色、审核、返修到发布归档的全流程管理。

系统参考仓库内 `openclaw-agents` 的现有 Agent 角色与实现方式，继承其成熟经验：

- **角色边界清晰**：每个 Agent 只处理职责内事务，不越权写入其他阶段数据。
- **状态驱动调度**：以章节状态、任务状态和工作流状态推动流程前进。
- **异步消息协作**：Agent 不直接互相调用，通过共享状态、消息队列和产物引用交接。
- **质量闸门严格**：审核失败进入返修，多次失败触发熔断与人工介入。
- **长篇一致性优先**：状态卡、角色关系、世界观、伏笔、前文事实通过上下文构建器注入。
- **模块化可扩展**：新增 Agent、质量规则、平台风格或模型供应商时，不重写主流程。

## 2. 技术选型

本系统采用 **Python 生态 + LangGraph 编排 + SQLite 持久化 + Pydantic 强类型约束** 的组合。技术栈选择以“先跑通章节生产闭环，再扩展多模型、多 Agent 与监控治理”为原则，避免第一版过度工程。

### 2.1 推荐技术栈

| 层级 | 推荐选型 | 作用 | v1 要求 |
| --- | --- | --- | --- |
| 开发语言 | Python 3.11+ | 主工程语言，与 LangGraph、OpenClaw 工具链兼容 | 必选 |
| 工作流编排 | LangGraph | 状态图、条件边、checkpoint、人工中断 | 必选 |
| LLM 工具层 | LangChain Core | Prompt、消息结构、模型适配、输出解析 | 必选 |
| 数据库 | SQLite | 复用 OpenClaw 的轻量共享数据库模式 | 必选 |
| 数据访问 | SQLModel 或轻量 Repository | 表模型、CRUD、查询封装 | v1 推荐 Repository 优先 |
| 数据校验 | Pydantic v2 | Agent 输入输出、结构化 JSON、配置校验 | 必选 |
| 配置 | YAML + 环境变量 | Agent、模型、阈值、路径配置 | 必选 |
| CLI | Typer 或 argparse | 本地调试、单节点运行、工作流触发 | 推荐 |
| 日志 | logging + Rich | 结构化日志、CLI 进度展示 | 推荐 |
| HTTP 客户端 | httpx | LLM Provider、外部 API 调用 | 推荐 |
| 测试 | pytest | 节点、校验器、工作流集成测试 | 必选 |
| 可观测性 | LangSmith / 自定义 run log | trace、成本、耗时、失败原因 | v1 可选 |

v1 不建议一开始实现完整多 Provider、多租户 API、Web UI、复杂插件热加载。先把核心章节闭环跑通，再扩展外围能力。

### 2.2 核心编排框架

选择 **LangGraph** 作为主编排框架。

原因：

- 小说生产是长流程、多阶段、可回退的状态机，不是单轮工具调用。
- LangGraph 支持节点、条件边、状态持久化、人工中断和可恢复执行。
- 章节状态流转、返修循环、审核闸门、熔断机制都可以自然表达为图。
- 可以使用 checkpoint 保留执行现场，便于暂停、恢复、审计和重跑。

### 2.3 LangChain 的定位

LangChain 不作为主调度器，而作为工具层补充：

- LLM 调用封装。
- PromptTemplate 与结构化输出解析。
- 检索、工具调用、文档加载。
- JSON schema / Pydantic 输出校验。

### 2.4 数据层选型

v1 继续使用 SQLite，原因是当前 `openclaw-agents` 已经基于 SQLite 和命令式工具形成了共享数据范式，迁移成本低，便于本地开发和调试。

数据访问层建议采用“两阶段策略”：

- v1 使用轻量 Repository 封装 SQL，优先兼容 `openclaw-agents/shared/data/init_db.sql` 的现有表结构。
- v2 再引入 SQLModel 管理新增表和复杂查询，避免 ORM 自动建表与既有 SQL 脚本形成双事实源。

迁移原则：

- 现有 OpenClaw 表结构不由 ORM 自动改写。
- 新增表通过显式 migration SQL 管理。
- Pydantic / SQLModel 可作为应用层输入输出模型，但不能替代数据库 migration。

### 2.5 LLM Provider 选型

v1 推荐只实现一个 **OpenAI-compatible Provider**，通过 `base_url`、`api_key`、`model` 配置兼容 OpenAI、OpenRouter、火山方舟等接口风格相近的服务。

Provider 扩展顺序：

```text
v1: OpenAI-compatible Provider
v2: Agent 级模型路由与 fallback
v3: Anthropic / 千帆 / 京东云等原生 Provider
v4: token 成本统计、Provider 健康检查、动态降级
```

这样其他开发 Agent 实现时不会被多厂商适配拖慢主流程。多 Provider 是扩展点，不是 v1 主线。

### 2.6 OpenClaw 范式的定位

OpenClaw 提供 Agent 组织方式与协作规范：

- `SOUL.md` / `IDENTITY.md` 定义角色人格与职责。
- `SKILL.md` 定义工作流程、触发条件、禁止事项和命令。
- `TOOLS.md` 定义可用工具与数据操作边界。
- 共享数据库、消息表、状态表作为 Agent 间协作底座。

建议保留 OpenClaw 的角色文档范式，并将 LangGraph 作为运行时编排层。

### 2.7 v1 技术栈结论

v1 默认技术栈：

```text
Python 3.11+
LangGraph
LangChain Core
SQLite
Pydantic v2
YAML 配置
pytest
OpenAI-compatible LLM Provider
Repository 数据访问层
```

延后到 v2+：

```text
SQLModel 全量 ORM
多 Provider 原生适配
LangSmith 强制接入
Skill 热加载插件系统
Web API / Web UI
跨章 ContinuityChecker 独立 Agent
```

## 3. 总体架构

```text
┌──────────────────────────────────────────────────────────────┐
│                        产品与人工控制层                         │
│  项目配置 / 人工审核 / 熔断处理 / 风格策略 / 发布确认             │
└───────────────────────────────┬──────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────┐
│                       LangGraph 编排层                         │
│  FactoryGraph / 条件边 / checkpoint / retry / interrupt         │
└───────────────────────────────┬──────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────┐
│                         Agent 能力层                           │
│  Dispatcher / Scout / Planner / Screenwriter / Author           │
│  Polisher / Editor / Architect / Secretary                      │
└───────────────────────────────┬──────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────┐
│                         共享数据层                             │
│  projects / chapters / instructions / scene_beats               │
│  plot_holes / reviews / polish_reports / task_status            │
│  agent_messages / workflow_runs / agent_artifacts               │
└───────────────────────────────┬──────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────┐
│                       质量治理与监控层                          │
│  上下文构建 / 状态卡 / 伏笔验证 / 问题模式 / 版本记录            │
│  健康报告 / 告警 / 熔断 / 备份 / 审计日志                        │
└──────────────────────────────────────────────────────────────┘
```

核心思想：

- LangGraph 管流程。
- Agent 管能力。
- 数据库管状态与产物。
- 质量治理层管一致性、回退和可审计性。

## 4. 核心状态模型

### 4.1 FactoryState

`FactoryState` 是 LangGraph 的全局状态对象，承载一次工作流运行的关键上下文。

建议字段：

```python
from typing import Any, Literal, TypedDict


class FactoryState(TypedDict, total=False):
    workflow_run_id: str
    project_id: str
    chapter_number: int
    current_stage: str
    task_id: str
    chapter_status: str
    artifact_refs: dict[str, str]
    quality_gate: dict[str, Any]
    messages: list[dict[str, Any]]
    retry_count: int
    max_retries: int
    requires_human: bool
    error: str | None
```

字段说明：

- `workflow_run_id`：一次流程运行的唯一 ID。
- `project_id`：项目 ID。
- `chapter_number`：当前章节号。
- `current_stage`：当前阶段，例如 `planning`、`writing`、`reviewing`。
- `task_id`：当前任务记录 ID。
- `chapter_status`：章节状态，来源于 `chapters.status`。
- `artifact_refs`：各阶段产物引用，例如市场报告、章节指令、场景 beat、草稿、润色稿、审核报告。
- `quality_gate`：审核评分、退回原因、是否通过。
- `messages`：待处理 Agent 消息。
- `retry_count`：当前章节返修或任务重试次数。
- `max_retries`：熔断阈值，默认 3。
- `requires_human`：是否需要人工介入。
- `error`：异常信息。

### 4.2 章节状态

建议章节状态：

```text
idea          选题/项目概念阶段
outlined      已完成项目或卷纲
planned       已生成章节写作指令
scripted      已完成场景 beat
drafted       已完成正文草稿
polished      已完成润色稿
review        待审核
reviewed      审核通过，待发布
revision      审核退回，待返修
published     已发布/归档
blocking      熔断或人工阻塞
```

状态流转：

```text
idea
  -> outlined
  -> planned
  -> scripted
  -> drafted
  -> polished
  -> review
  -> reviewed
  -> published

review -> revision -> drafted/polished -> review
任意异常状态 -> blocking -> human_review
```

## 5. Agent 角色设计

### 5.1 Dispatcher Agent：调度器

参考 `openclaw-agents/dispatcher`。

职责：

- 周期性发现待处理任务。
- 获取调度锁，避免并发重叠。
- 执行健康检查、状态一致性检查和超时清理。
- 根据章节状态和任务状态路由到对应 Agent。
- 处理重试、熔断和人工介入。

禁止：

- 不创作正文。
- 不决定审核通过。
- 不直接修改剧情设定。
- 不越过质量闸门发布章节。

关键规则：

- 同一章节退回次数达到阈值，进入 `blocking`。
- completion event 不立即触发新调度，避免快速循环。
- 只唤醒一个最高优先级任务，避免并发写同一章节。

### 5.2 Scout Agent：市场侦察

参考 `openclaw-agents/scout`。

职责：

- 跟踪题材趋势、平台榜单、读者偏好。
- 输出选题建议、风险提示、差异化机会。
- 为 Planner 提供题材定位和商业目标。

产物：

- `market_reports`
- `genre_opportunities`
- `reader_profile`
- `risk_notes`

禁止：

- 不直接创建章节。
- 不修改正文。
- 不决定项目是否发布。

### 5.3 Planner Agent：策划 / 总编

参考 `openclaw-agents/planner`。

职责：

- 创建项目定位、世界观、角色、势力、卷纲。
- 规划长线伏笔和兑现节奏。
- 为章节生成写作指令。
- 处理 Editor 发来的设定异议。
- 审核通过后执行发布归档决策。

产物：

- `projects`
- `world_settings`
- `characters`
- `factions`
- `outlines`
- `plot_holes`
- `instructions`

禁止：

- 不写正文。
- 不跳过审核直接发布。
- 不唤醒其他 Agent，调度由 Dispatcher 负责。

### 5.4 Screenwriter Agent：编剧

新增角色。

职责：

- 将 Planner 的章节指令拆解成可执行场景 beat。
- 设计场景目标、冲突、转折、信息揭示、章末钩子。
- 控制单章节奏，确保每个场景都有推进作用。
- 标记本章需要埋设或兑现的伏笔在具体场景中的位置。

产物：

- `scene_beats`
- `conflict_map`
- `chapter_hook_plan`

禁止：

- 不改写世界观和角色设定。
- 不写最终正文。
- 不决定审核结果。

### 5.5 Author Agent：写作 / 执笔

参考 `openclaw-agents/author`。

职责：

- 基于写作指令、状态卡、场景 beat 和上下文创作正文草稿。
- 严格落实章节目标、关键事件、伏笔要求和钩子。
- 返修时只修复审核指出的问题，不随意重写全章。

产物：

- `chapters.content`
- `chapter_versions`
- `draft_artifact`

禁止：

- 不创建或修改伏笔。
- 不创建角色。
- 不创建写作指令。
- 不决定发布。
- 不自行编造状态卡中不存在的数值、技能、资源。

### 5.6 Polisher Agent：润色

新增角色。

职责：

- 清理 AI 味表达、模板化句式和陈词滥调。
- 优化语言质感、对话节奏、场景转换和动作描写。
- 保持剧情事实、伏笔、角色动机和数值状态不变。
- 输出润色报告，说明改动范围和风险。

产物：

- `polish_reports`
- `chapter_versions.created_by = polisher`
- `polished_artifact`

禁止：

- 不改变剧情事实。
- 不新增或删除关键事件。
- 不改写 Planner 的伏笔计划。
- 不替 Editor 做通过/退回判断。

### 5.7 Editor Agent：审核 / 质检

参考 `openclaw-agents/editor`。

职责：

- 执行五层审校：设定一致性、逻辑自洽、毒点检测、文字质量、节奏钩子。
- 检查状态卡连续性、伏笔兑现、角色行为动机和 AI 痕迹。
- 给出评分、问题列表、修改建议。
- 审核通过时写入状态卡；不通过时退回 `revision`。
- 严重设定问题通过 `agent_messages` 发送给 Planner。

产物：

- `reviews`
- `chapter_state`
- `agent_messages`
- `learned_patterns`

禁止：

- 不写正文。
- 不修改章节内容。
- 不创建写作指令。

### 5.8 Architect Agent：架构维护

参考 `openclaw-agents/architect`。

职责：

- 维护系统规则、Prompt、数据结构和 Agent 能力边界。
- 分析质量报告和运行指标，提出优化建议。
- 管理迁移、兼容性、监控策略和生产就绪标准。

产物：

- 架构决策记录。
- 数据迁移方案。
- Prompt / Skill 优化建议。
- 质量规则升级报告。

禁止：

- 不参与单章内容创作。
- 不绕过 Dispatcher 直接操作生产流程。

### 5.9 Secretary Agent：秘书 / 归档

参考 `openclaw-agents/secretary`。

职责：

- 生成项目日报、周报和进度摘要。
- 归档章节、导出版本、整理审核记录。
- 汇总 Agent 工作结果和异常事件。

产物：

- `daily_reports`
- `export_records`
- `progress_summary`

禁止：

- 不修改正文。
- 不变更审核结果。
- 不创建剧情设定。

## 6. LangGraph 工作流设计

### 6.1 节点设计

建议节点：

```text
health_check_node
task_discovery_node
market_scout_node
planner_node
screenwriter_node
author_node
polisher_node
editor_node
publisher_node
revision_router_node
human_review_node
archive_node
```

节点职责：

- `health_check_node`：检查数据库、任务失败率、消息积压、熔断状态。
- `task_discovery_node`：根据章节状态发现下一任务。
- `market_scout_node`：生成市场洞察。
- `planner_node`：生成项目规划、章节指令或发布决策。
- `screenwriter_node`：生成场景 beat。
- `author_node`：生成或返修正文。
- `polisher_node`：生成润色稿和润色报告。
- `editor_node`：审核并写入质量报告。
- `publisher_node`：发布和归档审核通过的章节。
- `revision_router_node`：根据审核问题决定返修进入 Author 还是 Polisher。
- `human_review_node`：处理熔断、冲突和人工决策。
- `archive_node`：生成版本记录、日报和项目摘要。

### 6.2 条件边设计

```text
health_check_node
  -> task_discovery_node
  -> planner_node          当状态为 idea/outlined 或缺少 instruction
  -> screenwriter_node     当状态为 planned
  -> author_node           当状态为 scripted 或 revision_requires_rewrite
  -> polisher_node         当状态为 drafted 或 revision_requires_polish
  -> editor_node           当状态为 polished/review
  -> publisher_node        当状态为 reviewed
  -> human_review_node     当状态为 blocking 或 requires_human=true
  -> archive_node          当状态为 published
```

审核后的条件路由：

```text
editor_node
  -> publisher_node        pass=true 且 score >= threshold
  -> revision_router_node  pass=false 且 retry_count < max_retries
  -> human_review_node     retry_count >= max_retries
```

返修路由：

```text
revision_router_node
  -> author_node           剧情、逻辑、设定、伏笔问题
  -> polisher_node         文风、句式、节奏、AI 痕迹问题
  -> planner_node          指令本身错误或设定冲突
```

### 6.3 图伪代码

```python
from langgraph.graph import END, StateGraph


graph = StateGraph(FactoryState)

graph.add_node("health_check", health_check_node)
graph.add_node("task_discovery", task_discovery_node)
graph.add_node("planner", planner_node)
graph.add_node("screenwriter", screenwriter_node)
graph.add_node("author", author_node)
graph.add_node("polisher", polisher_node)
graph.add_node("editor", editor_node)
graph.add_node("publisher", publisher_node)
graph.add_node("revision_router", revision_router_node)
graph.add_node("human_review", human_review_node)
graph.add_node("archive", archive_node)

graph.set_entry_point("health_check")
graph.add_edge("health_check", "task_discovery")

graph.add_conditional_edges(
    "task_discovery",
    route_by_chapter_status,
    {
        "planning": "planner",
        "screenwriting": "screenwriter",
        "writing": "author",
        "polishing": "polisher",
        "reviewing": "editor",
        "publishing": "publisher",
        "human_review": "human_review",
        "archive": "archive",
    },
)

graph.add_conditional_edges(
    "editor",
    route_by_review_result,
    {
        "publish": "publisher",
        "revise": "revision_router",
        "human_review": "human_review",
    },
)

graph.add_conditional_edges(
    "revision_router",
    route_by_revision_type,
    {
        "rewrite": "author",
        "polish": "polisher",
        "replan": "planner",
        "human_review": "human_review",
    },
)

graph.add_edge("planner", "screenwriter")
graph.add_edge("screenwriter", "author")
graph.add_edge("author", "polisher")
graph.add_edge("polisher", "editor")
graph.add_edge("publisher", "archive")
graph.add_edge("archive", END)
graph.add_edge("human_review", END)

factory_graph = graph.compile(checkpointer=checkpointer)
```

## 7. 数据流设计

### 7.1 继承的核心表

建议保留 OpenClaw 现有核心实体：

- `projects`：项目基础信息。
- `world_settings`：世界观设定。
- `characters`：角色设定。
- `factions`：势力设定。
- `outlines`：项目、卷、阶段大纲。
- `chapters`：章节正文和状态。
- `instructions`：章节写作指令。
- `plot_holes`：伏笔。
- `chapter_plots`：章节与伏笔关联。
- `reviews`：审核报告。
- `chapter_state`：每章结束状态卡。
- `chapter_versions`：章节版本。
- `task_status`：任务状态。
- `agent_messages`：Agent 异步消息。
- `anti_patterns`：问题模式库。
- `best_practices`：高分经验。
- `learned_patterns`：系统学习到的问题模式。

### 7.2 新增逻辑实体

#### scene_beats

用于保存 Screenwriter 的场景拆解。

建议字段：

```sql
CREATE TABLE scene_beats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    scene_goal TEXT NOT NULL,
    location TEXT,
    characters TEXT DEFAULT '[]',
    conflict TEXT,
    turn TEXT,
    revealed_info TEXT,
    plot_refs TEXT DEFAULT '[]',
    hook TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### polish_reports

用于记录 Polisher 的改动范围和风险。

建议字段：

```sql
CREATE TABLE polish_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    source_version INTEGER,
    target_version INTEGER,
    style_changes TEXT DEFAULT '[]',
    rhythm_changes TEXT DEFAULT '[]',
    dialogue_changes TEXT DEFAULT '[]',
    ai_trace_fixes TEXT DEFAULT '[]',
    fact_change_risk TEXT DEFAULT 'none',
    summary TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### workflow_runs

用于记录 LangGraph 的运行实例。

建议字段：

```sql
CREATE TABLE workflow_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    chapter_number INTEGER,
    graph_name TEXT NOT NULL,
    status TEXT DEFAULT 'running',
    current_node TEXT,
    checkpoint_ref TEXT,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    error_message TEXT
);
```

#### agent_artifacts

用于统一引用各 Agent 的产物。

建议字段：

```sql
CREATE TABLE agent_artifacts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    chapter_number INTEGER,
    agent_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    storage_uri TEXT,
    content_json TEXT,
    content_hash TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 7.3 数据流转

章节生产数据流：

```text
Planner
  -> instructions
  -> plot_holes / chapter_plots
  -> chapters.status = planned

Screenwriter
  -> scene_beats
  -> agent_artifacts(type=scene_plan)
  -> chapters.status = scripted

Author
  -> chapters.content
  -> chapter_versions(created_by=author)
  -> chapters.status = drafted

Polisher
  -> chapter_versions(created_by=polisher)
  -> polish_reports
  -> chapters.status = polished

Editor
  -> reviews
  -> chapter_state
  -> agent_messages
  -> chapters.status = reviewed 或 revision

Publisher / Planner
  -> chapters.status = published
  -> sync plot_holes / chapter_plots
  -> archive artifacts
```

Agent 消息流：

```text
Editor -> agent_messages -> Planner
Polisher -> agent_messages -> Editor
Author -> agent_messages -> Planner
Dispatcher -> 注入 pending messages -> 目标 Agent
```

## 8. 上下文构建策略

长篇小说生产必须控制上下文优先级，避免设定漂移。

上下文优先级：

```text
P0 死刑红线 / 强制质量规则
P1 当前章节写作指令
P2 上一章状态卡
P3 本章场景 beat
P4 必须埋设或兑现的伏笔
P5 当前章节相关角色与势力
P6 世界观关键规则
P7 近 1-3 章摘要
P8 项目大纲 / 卷纲 / 长线节奏
P9 问题模式库 / 高分最佳实践
```

不同 Agent 的上下文裁剪策略：

- Planner：更重视大纲、伏笔、状态卡、异议消息。
- Screenwriter：更重视章节目标、人物冲突、伏笔落点、节奏曲线。
- Author：更重视写作指令、状态卡、场景 beat、角色语气和禁用表达。
- Polisher：更重视原稿、风格规则、AI 痕迹、事实锁定清单。
- Editor：更重视正文、指令、状态卡、伏笔要求、问题模式库。

事实锁定清单：

- 角色身份、关系、能力。
- 世界观规则。
- 数值状态。
- 伏笔状态。
- 已发布章节事实。
- 当前章节必须发生的关键事件。

## 9. 调度与协作机制

### 9.1 调度优先级

建议 Dispatcher 按以下优先级取任务：

```text
P0 blocking / requires_human     人工阻塞，暂停自动流转
P1 revision                      审核退回，优先返修
P2 review                        已润色，待审核
P3 polished                      已润色，待提交审核
P4 drafted                       已草稿，待润色
P5 scripted                      已编剧，待写作
P6 planned                       已指令，待编剧
P7 outlined / idea               待策划
P8 published                     待归档/日报
```

### 9.2 锁与并发

规则：

- 同一 `project_id + chapter_number` 同一时间只能有一个写入型 Agent 执行。
- Dispatcher 获取全局调度锁，避免 cron 重叠。
- 写作、润色、审核阶段必须记录 `task_status`。
- Agent 写入前检查当前章节状态是否仍符合预期。

### 9.3 重试与熔断

重试规则：

- 工具调用失败可以自动重试。
- LLM 输出结构错误可以重新生成。
- 同一任务底层失败达到 3 次进入人工处理。

返修熔断：

- 同一章节审核退回达到 3 次，进入 `blocking`。
- 状态卡冲突、伏笔无法兑现、指令自相矛盾，进入 `blocking`。
- 数据库状态与 checkpoint 不一致，进入 `blocking`。

### 9.4 人工介入

人工介入入口：

- 章节反复退回。
- Planner 与 Editor 对设定解释冲突。
- 市场策略或题材方向需要人类确认。
- 质量阈值无法稳定达到。
- 出现安全、版权、平台合规风险。

人工处理结果应写回：

- `agent_messages.result`
- `workflow_runs.status`
- `chapters.status`
- 必要时写入 `architect_decisions` 或架构决策文档。

## 10. 质量闸门

### 10.1 审核评分

Editor 采用五层审校：

- 设定一致性。
- 逻辑自洽。
- 毒点检测。
- 文字质量。
- 节奏与钩子。

建议阈值：

- 总分 >= 90 且无严重问题：通过。
- 80-89：原则上退回润色或局部返修。
- 60-79：退回 Author 重写关键问题。
- < 60：严重失败，记录问题模式。
- 触发死刑红线：直接强退或固定低分。

### 10.2 Polisher 质量边界

Polisher 必须输出事实不变声明：

```json
{
  "fact_change_risk": "none",
  "changed_scope": ["dialogue", "rhythm", "sentence"],
  "unchanged_facts": ["plot", "state_card", "plot_holes", "character_relationship"]
}
```

如果 Polisher 发现必须改剧情才能解决问题，只能发消息给 Editor 或 Planner，不能自行改剧情。

### 10.3 Author 权限边界

Author 只写正文和返修正文：

- 不创建伏笔。
- 不修改伏笔状态。
- 不新增角色设定。
- 不修改世界观规则。
- 不决定章节通过或发布。

### 10.4 Planner 权限边界

Planner 可以管理设定、伏笔和写作指令，但不能绕过 Editor：

- 不写正文。
- 不直接将未审核章节标记为 `published`。
- 处理审核异议时必须保留消息处理记录。

## 11. 可扩展性设计

### 11.1 新增 Agent

新增 Agent 时需要定义：

- `agent_id`
- `IDENTITY.md`
- `SOUL.md`
- `SKILL.md`
- 可读数据。
- 可写数据。
- 输入产物。
- 输出产物。
- 失败处理。
- 对应 LangGraph 节点。
- 条件边路由规则。

示例新增 Agent：

- `Continuity Agent`：专职检查长篇一致性。
- `Dialogue Agent`：专职优化角色台词。
- `Platform Adapter Agent`：按起点、番茄、飞卢等平台风格改写。
- `Safety Agent`：检查版权、合规和敏感内容。

### 11.2 新增质量规则

新增质量规则应进入配置或数据库，而不是硬编码在 Agent 中：

- `anti_patterns`
- `context_rules`
- `quality_rubrics`
- `platform_rules`

Editor 和 Polisher 从规则表读取生效规则。

### 11.3 新增模型供应商

模型调用通过统一 `ModelGateway` 抽象：

```python
class ModelGateway:
    def invoke(self, agent_id: str, messages: list[dict], schema: type | None = None):
        ...
```

路由维度：

- Agent 类型。
- 任务复杂度。
- 上下文长度。
- 成本预算。
- 是否需要结构化输出。

### 11.4 新增平台风格

平台风格通过 `platform_profiles` 配置：

```json
{
  "platform": "qidian",
  "chapter_word_target": 3000,
  "hook_density": "high",
  "prohibited_patterns": ["AI模板句", "弱冲突过渡"],
  "reader_expectation": "强升级、强因果、持续爽点"
}
```

Planner、Screenwriter、Author、Polisher、Editor 均应读取平台风格。

## 12. 监控与运维

核心指标：

- 任务失败率。
- 任务超时率。
- 平均审核分。
- 章节退回率。
- 伏笔兑现率。
- 状态卡缺失率。
- Agent 消息积压。
- 熔断次数。
- 平均单章生产耗时。
- Polisher 事实风险次数。

告警建议：

```text
warning:
  - 平均审核分 < 85
  - 消息积压 > 10
  - 单章生产耗时超过目标 2 倍

error:
  - 任务失败率 > 10%
  - 章节退回率 > 30%
  - 伏笔兑现率 < 70%

critical:
  - 任意章节进入 blocking
  - 数据库状态与 checkpoint 冲突
  - 连续调度失败
```

运维能力：

- 定时备份数据库。
- 导出章节和版本。
- 按项目生成健康报告。
- 支持按 `workflow_run_id` 追踪一次执行。
- 支持人工重置任务或解除熔断。

## 13. 落地路线

### Phase 1：工程骨架与数据契约

目标：

- 创建最小工程目录、配置加载、日志、测试框架。
- 固化 Agent 职责边界。
- 固化章节状态机。
- 固化核心数据表与新增逻辑实体。
- 固化质量闸门和熔断规则。

交付：

- `novel_factory/` 主包骨架。
- `FactoryState` / Agent 输入输出 Pydantic schema。
- 数据表 migration 草案。
- Agent 权限矩阵。
- pytest 基础 fixture。

### Phase 2：v1 章节生产 MVP

目标：

- 实现 `FactoryState`。
- 实现章节级主图。
- 接入 Planner、Screenwriter、Author、Polisher、Editor 五个核心 Agent。
- 使用单一 OpenAI-compatible Provider。
- 使用 Repository 读写 SQLite。
- 支持 checkpoint、review、revision、publish、blocking。

验收：

- 一章可以从 `planned -> scripted -> drafted -> polished -> review -> reviewed -> published`。
- 审核失败可以进入 `revision`，并根据问题类型路由到 Author 或 Polisher。
- 连续失败可以进入 `blocking`。
- Agent 输出结构不合法时不会写入数据库。

### Phase 3：质量与一致性增强

目标：

- 完善硬校验：字数、禁用词、状态卡、伏笔、格式。
- 完善上下文构建优先级与 token 预算。
- 加入 `learned_patterns` 与 `best_practices` 读取。
- 引入章节版本 hash 和产物引用。

验收：

- Author 严格基于 scene beats 创作。
- Polisher 不改变剧情事实。
- Editor 能解释每个退回问题的规则来源。
- 状态卡、伏笔、角色事实不发生静默漂移。

### Phase 4：生产治理

目标：

- 完善监控告警。
- 完善消息积压处理。
- 完善人工介入入口。
- 完善版本导出与日报。

验收：

- 可按项目查看健康报告。
- 可追踪每章产物链路。
- 可恢复中断的 workflow run。

### Phase 5：扩展能力

目标：

- 增加 Scout、Architect、Secretary。
- 增加 ContinuityChecker 独立 Agent。
- 增加平台风格适配。
- 增加市场侦察闭环。
- 增加高分章节学习。
- 增加多模型路由。

验收：

- 新增 Agent 不需要重写主图。
- 新增质量规则可配置生效。
- 不同平台可使用不同创作策略。

## 14. 测试与验收场景

### 14.1 完整流程

输入：

- 一个已有项目。
- 一条章节写作指令。

期望：

- 生成 scene beats。
- 生成草稿。
- 生成润色稿。
- 生成审核报告。
- 审核通过后发布归档。

### 14.2 返修流程

输入：

- Editor 标记逻辑问题。

期望：

- 章节进入 `revision`。
- Dispatcher 路由到 Author。
- Author 修改后重新进入 Polisher 和 Editor。

### 14.3 润色返修

输入：

- Editor 只标记 AI 味、句式、节奏问题。

期望：

- Dispatcher 路由到 Polisher。
- Polisher 不改变剧情事实。
- 再次审核通过或继续退回。

### 14.4 熔断流程

输入：

- 同一章节连续 3 次审核退回。

期望：

- 章节进入 `blocking`。
- Dispatcher 停止自动调度该章节。
- 写入人工介入消息。

### 14.5 数据一致性

输入：

- 状态卡中主角等级为 Lv3。
- 草稿中出现 Lv5。

期望：

- Editor 检出状态卡不一致。
- 审核失败。
- 问题写入 reviews。

### 14.6 权限边界

输入：

- Author 尝试创建伏笔。
- Polisher 尝试改变剧情结果。
- Editor 尝试修改正文。

期望：

- 工具层拒绝越权写入。
- 记录权限违规。
- 必要时进入人工审核。

### 14.7 消息协作

输入：

- Editor 发现 Planner 指令中的伏笔无法兑现。

期望：

- Editor 写入 `agent_messages`。
- Dispatcher 下一次调度 Planner 时注入该消息。
- Planner 处理并写入 `resolve_message`。

### 14.8 恢复能力

输入：

- 工作流在 Polisher 后中断。

期望：

- checkpoint 保存当前状态。
- 恢复后从 Editor 或下一未完成节点继续。
- 不重复写入已完成产物。

## 15. Agent 权限矩阵

| Agent | 可读 | 可写 | 禁止 |
| --- | --- | --- | --- |
| Dispatcher | task_status, chapters, workflow_runs, metrics | task_status, workflow_runs, locks | 创作正文、审核通过、改设定 |
| Scout | market_reports, projects | market_reports, opportunity_reports | 写章节、发布 |
| Planner | projects, outlines, characters, plot_holes, messages | instructions, outlines, plot_holes, world_settings | 写正文、跳过审核 |
| Screenwriter | instructions, outlines, characters, plot_holes | scene_beats, agent_artifacts | 改设定、写最终正文 |
| Author | instructions, scene_beats, chapter_state, context | chapters, chapter_versions | 创建设定、改伏笔、发布 |
| Polisher | chapters, chapter_versions, style_rules | chapter_versions, polish_reports | 改剧情事实、审核通过 |
| Editor | chapters, instructions, context, anti_patterns | reviews, chapter_state, messages | 写正文、创建指令 |
| Architect | metrics, prompts, schema docs | architecture docs, migration plans | 直接改生产章节 |
| Secretary | chapters, reviews, workflow_runs | reports, exports | 改正文、改审核 |

## 16. 实施注意事项

- 先实现章节级最小闭环，再扩展项目级和市场级流程。
- 所有 Agent 输出必须结构化，并通过 schema 校验后写入数据库。
- Agent 产物必须有版本、来源、时间戳和 hash，便于审计。
- 写入数据库前必须检查章节状态，避免过期任务覆盖新结果。
- 任何可以改变故事事实的操作都必须记录版本。
- 任何质量闸门失败都必须可追踪到具体规则和证据。
- 调度器永远只调度，不替代 Agent 做内容决策。

## 17. 给开发 Agent 的实现交接清单

本节用于把架构计划翻译成更容易被其他大模型或工程 Agent 执行的开发约束。后续实现时应优先遵守本节，避免在框架、状态、目录和职责边界上发散。

### 17.1 推荐目录结构

```text
novel_factory/
  __init__.py
  config/
    settings.py
    agents.yaml
    llm.yaml
  models/
    state.py
    schemas.py
    outputs.py
  db/
    connection.py
    repository.py
    migrations/
      001_add_workflow_tables.sql
  workflow/
    graph.py
    nodes.py
    conditions.py
  agents/
    base.py
    planner.py
    screenwriter.py
    author.py
    polisher.py
    editor.py
  context/
    builder.py
  validators/
    chapter_checker.py
    state_verifier.py
    plot_verifier.py
    death_penalty.py
  llm/
    provider.py
    openai_compatible.py
  cli.py
tests/
  test_workflow/
  test_agents/
  test_validators/
```

v1 不创建复杂插件系统。`skills/`、多 Provider 原生适配、Web API、Web UI 可在 v2 后补。

### 17.2 必须先实现的接口

```python
class BaseAgent:
    agent_id: str

    def build_context(self, state: FactoryState) -> str:
        ...

    def run(self, state: FactoryState) -> dict:
        ...

    def validate_output(self, output: dict) -> None:
        ...
```

```python
class Repository:
    def get_chapter_status(self, project_id: str, chapter_number: int) -> str:
        ...

    def update_chapter_status(self, project_id: str, chapter_number: int, status: str) -> None:
        ...

    def save_artifact(self, artifact: dict) -> str:
        ...

    def start_task(self, project_id: str, chapter_number: int, task_type: str, agent_id: str) -> str:
        ...

    def complete_task(self, task_id: str, success: bool, error: str | None = None) -> None:
        ...
```

```python
class LLMProvider:
    def invoke_json(self, messages: list[dict], schema: type) -> dict:
        ...

    def invoke_text(self, messages: list[dict]) -> str:
        ...
```

### 17.3 v1 状态枚举不得发散

所有开发 Agent 只能使用以下章节状态：

```text
idea
outlined
planned
scripted
drafted
polished
review
reviewed
revision
published
blocking
```

如果需要更细的内部阶段，写入 `workflow_runs.current_node` 或 `FactoryState.current_stage`，不要新增 `chapters.status` 枚举。

### 17.4 v1 Agent 输出契约

Planner 输出：

```json
{
  "chapter_brief": {
    "objective": "...",
    "required_events": ["..."],
    "plots_to_plant": ["P001"],
    "plots_to_resolve": [],
    "ending_hook": "...",
    "constraints": ["..."]
  }
}
```

Screenwriter 输出：

```json
{
  "scene_beats": [
    {
      "sequence": 1,
      "scene_goal": "...",
      "conflict": "...",
      "turn": "...",
      "plot_refs": ["P001"],
      "hook": "..."
    }
  ]
}
```

Author 输出：

```json
{
  "title": "第N章 ...",
  "content": "...",
  "word_count": 2800,
  "implemented_events": ["..."],
  "used_plot_refs": ["P001"]
}
```

Polisher 输出：

```json
{
  "content": "...",
  "fact_change_risk": "none",
  "changed_scope": ["sentence", "dialogue", "rhythm"],
  "summary": "..."
}
```

Editor 输出：

```json
{
  "pass": true,
  "score": 92,
  "scores": {
    "setting": 23,
    "logic": 24,
    "poison": 19,
    "text": 13,
    "pacing": 13
  },
  "issues": [],
  "suggestions": [],
  "revision_target": null,
  "state_card": {}
}
```

`revision_target` 只允许为 `author`、`polisher`、`planner` 或 `null`。

### 17.5 实现顺序建议

1. 先实现数据库连接、Repository、状态枚举和 migration。
2. 再实现 Pydantic schema，保证 Agent 输出可校验。
3. 再实现假 LLM / stub Agent，让 LangGraph 流程先跑通。
4. 再接入真实 LLM Provider。
5. 再补上下文构建和硬校验。
6. 最后补监控、成本统计、多 Provider、ContinuityChecker。

### 17.6 禁止事项

- 禁止在 Agent 内直接拼接任意 SQL 写生产表，必须走 Repository。
- 禁止 Agent 自行新增章节状态。
- 禁止 Polisher 改剧情事实后仍声明 `fact_change_risk=none`。
- 禁止 Editor 直接修改正文。
- 禁止 Author 创建伏笔、角色或世界观规则。
- 禁止把多 Provider、插件热加载、Web UI 放进 v1 阻塞主流程。

## 18. 结论

该架构将 OpenClaw 的角色化 Agent 工作方式与 LangGraph 的状态机编排能力结合起来，适合长篇小说这种高一致性、高返修率、多阶段协同的内容生产场景。

系统的关键不是让多个 Agent 同时“聊天”，而是让它们围绕同一份结构化状态、同一套权限边界和同一条可审计工作流协作。这样既能提升创作吞吐，也能减少长篇创作中最常见的设定漂移、伏笔断裂、质量不稳定和返修失控问题。
