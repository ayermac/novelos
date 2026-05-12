# v2 多 Agent 扩展开发规范

## 目标

v2 的目标是把已经稳定可运行的章节生产流水线，扩展为具备旁路协作能力的小说内容生产工厂。

v1.4 已经完成运行时硬化：`novelos` 可安装运行、配置可校验、demo 可 smoke run、真实/Stub LLM 模式明确、`revision_target` 已结构化。v2 在此基础上新增旁路 Agent，但不重写主链路。

本轮重点：

- 新增 Scout Agent。
- 新增 Secretary Agent。
- 新增 ContinuityChecker Agent。
- 新增 Architect Agent。
- Dispatcher 支持旁路 Agent 触发。
- CLI 支持旁路 Agent 命令。
- 旁路 Agent 通过 DB、artifact 和 `agent_messages` 协作，不直接阻塞主链路。

## 当前前置条件

必须基于以下状态开发：

- v1 MVP 已通过。
- v1 review 返工闸门已通过。
- v1.1 工程稳定性已通过。
- v1.2 质量与一致性增强已通过。
- v1.3 Dispatcher 编排与 CLI 可运行化已通过。
- v1.4 运行时硬化与配置化收尾已通过。
- 当前全量测试应为 `293/293` 或更多。
- 不允许破坏 v1-v1.4 任何验收测试。

## 版本定位

v2 是“旁路多 Agent 协作”版本，不是 Web UI 版本，也不是多模型治理版本。

主链路保持：

```text
Planner -> Screenwriter -> Author -> Polisher -> Editor -> Publisher
```

旁路 Agent 只通过数据和消息影响后续流程：

```text
Scout -> market_reports/opportunity_reports -> Planner context
Secretary -> workflow_runs/artifacts/reviews -> reports/exports
ContinuityChecker -> chapters/state/plots -> agent_messages -> Planner/Editor
Architect -> metrics/prompts/rules -> proposals -> human review
```

## 本轮允许实现

允许修改：

- `novel_factory/agents/*`
- `novel_factory/dispatcher.py`
- `novel_factory/cli.py`
- `novel_factory/context/builder.py`
- `novel_factory/db/repository.py`
- `novel_factory/db/connection.py`
- `novel_factory/db/migrations/*`
- `novel_factory/models/*`
- `novel_factory/config/agents.yaml`
- `novel_factory/config/settings.py`
- `tests/*`
- `docs/codex/*`

允许新增：

- `novel_factory/agents/scout.py`
- `novel_factory/agents/secretary.py`
- `novel_factory/agents/continuity_checker.py`
- `novel_factory/agents/architect.py`
- `novel_factory/models/sidecar.py`
- `novel_factory/reports/exporter.py`
- `novel_factory/db/migrations/005_v2_sidecar_agents.sql`
- `tests/test_sidecar_agents.py`
- `tests/test_v2_cli.py`
- `tests/test_continuity_checker.py`
- `tests/test_reports.py`

## 本轮禁止实现

- 不新增 Web UI。
- 不新增 Web API / FastAPI 服务。
- 不新增多 Provider fallback。
- 不新增 Agent 级模型路由。
- 不新增 token 成本统计。
- 不新增 Skill 热加载。
- 不引入 Celery / Redis / Kafka。
- 不引入 PostgreSQL。
- 不引入 SQLModel 全量 ORM。
- 不改变章节状态枚举。
- 不改变主链路顺序。
- 不让旁路 Agent 直接改正文、发布章节或绕过 Editor。
- 不让 Architect 自动修改生产规则，只能生成提案。

## 技术栈选型

### 必选

| 模块 | 选型 | 说明 |
| --- | --- | --- |
| Agent 基类 | 复用 `BaseAgent` 或轻量 SidecarAgent | 保持前置检查、异常处理和 artifact 记录风格 |
| 调度 | 复用 Dispatcher | 增加旁路触发方法，不重写主调度 |
| 数据库 | SQLite + Repository | 延续现有模式 |
| 消息协作 | `agent_messages` | Agent 不直接互相同步调用 |
| 产物记录 | `agent_artifacts` | 旁路 Agent 输出必须可追踪 |
| CLI | argparse | 延续 v1.4 |

### 不选

| 方案 | 不选原因 |
| --- | --- |
| 新任务队列系统 | v2 先保持单机 CLI 触发 |
| Web 管理台 | 放到后续 UI 版本 |
| 多模型路由 | 放到 v3 |
| Architect 自动改 Prompt/规则 | 风险高，v2 只产出提案 |

## 新 Agent 职责边界

### A1：Scout Agent

目标：生成市场观察、题材趋势、读者偏好、竞品摘要，为 Planner 提供选题和风格参考。

输入：

- project 信息。
- genre / platform / audience 可选参数。
- 最近章节摘要。
- 用户提供的市场关键词。

输出：

- `market_report`
- `opportunity_report`
- `reader_preferences`
- `competitor_notes`

权限：

- 可以写 `market_reports` 或 `agent_artifacts`。
- 可以给 Planner 发送 `agent_messages`。
- 不能改章节正文。
- 不能改章节状态。
- 不能发布。

CLI：

```bash
novelos scout --project-id demo --topic "都市异能" --llm-mode stub
```

验收：

- Scout 输出结构化报告。
- Scout artifact 可查询。
- Scout 不改变任何章节状态。
- Scout 可选把摘要消息发送给 Planner。

### A2：Secretary Agent

目标：生成日报、周报、章节摘要、运行报告和导出内容。

输入：

- `workflow_runs`
- `agent_artifacts`
- `reviews`
- `chapters`
- `chapter_versions`

输出：

- `daily_report`
- `chapter_export`
- `run_summary`
- `review_summary`

权限：

- 可以写 reports/artifacts。
- 可以导出 Markdown。
- 不能改正文。
- 不能改审核结果。
- 不能改章节状态。

CLI：

```bash
novelos report daily --project-id demo --json
novelos export chapter --project-id demo --chapter 1 --format markdown
```

验收：

- daily report 包含运行数、成功/失败数、章节状态分布、最近错误。
- chapter export 包含标题、正文、版本摘要、审核摘要。
- 无章节时给出清晰错误。
- JSON 输出符合 `{ ok, error, data }` envelope。

### A3：ContinuityChecker Agent

目标：做跨章一致性检查。它不是每章主链路节点，而是每 3-5 章或手动触发一次。

检查内容：

- 状态卡连续性。
- 角色关系连续性。
- 伏笔埋设/兑现连续性。
- 地点/时间线跳变。
- 关键设定漂移。

输入：

- 最近 N 章正文。
- `chapter_state`
- `plot_holes`
- `instructions`
- `reviews`

输出：

- `continuity_report`
- `continuity_issues`
- 发给 Planner/Editor 的 `agent_messages`

权限：

- 可以写报告。
- 可以发消息给 Planner/Editor。
- 不能改章节正文。
- 不能直接改状态卡。
- 不能直接退回章节。

CLI：

```bash
novelos continuity-check --project-id demo --from-chapter 1 --to-chapter 5 --llm-mode stub
```

验收：

- 检测到跨章状态跳变时生成 issue。
- 检测到伏笔计划缺失时生成 warning。
- 生成的消息进入 `agent_messages`。
- 不改变章节状态。

### A4：Architect Agent

目标：根据运行数据、退回原因、learned_patterns、death penalty 命中、workflow 失败，提出规则和 Prompt 改进建议。

输入：

- `reviews`
- `learned_patterns`
- `workflow_runs`
- `agent_artifacts`
- 配置摘要。

输出：

- `architecture_proposal`
- `prompt_proposal`
- `quality_rule_proposal`
- `migration_proposal`

权限：

- 只能写 proposal。
- 不能自动改代码。
- 不能自动改 prompt。
- 不能直接改 DB schema。
- 不能改章节正文。

CLI：

```bash
novelos architect suggest --project-id demo --scope quality --llm-mode stub
```

验收：

- 生成结构化提案。
- 提案必须包含 `risk_level`、`affected_area`、`recommendation`。
- 提案默认状态为 `pending`。
- 不直接修改配置、prompt 或代码。

## 数据库与迁移

允许新增：

- `005_v2_sidecar_agents.sql`

建议新增表：

```sql
market_reports
reports
continuity_reports
architecture_proposals
```

最低字段建议：

```text
id
project_id
chapter_number nullable
agent_id
report_type/proposal_type
status
content_json
summary
created_at
updated_at
```

要求：

- migration 可重复执行。
- `_is_migration_applied_by_schema()` 支持 005 检测。
- 如复用 `agent_artifacts` 即可满足需求，可以少建表，但必须提供 Repository 查询方法。

## Repository 要求

必须新增或补充方法：

```python
save_market_report(...)
get_market_reports(...)
save_report(...)
get_reports(...)
save_continuity_report(...)
get_continuity_reports(...)
save_architecture_proposal(...)
get_architecture_proposals(...)
```

如果选择统一存入 `agent_artifacts`，也必须提供语义化 wrapper，避免 CLI 直接拼 artifact 查询。

## Dispatcher 要求

新增旁路调度方法：

```python
run_scout(project_id: str, topic: str | None = None, llm_mode: str = "real") -> dict
run_secretary_report(project_id: str, report_type: str = "daily") -> dict
run_continuity_check(project_id: str, from_chapter: int, to_chapter: int) -> dict
run_architect_suggest(project_id: str, scope: str = "quality") -> dict
```

要求：

- 旁路方法不得调用 `run_chapter()`。
- 旁路方法不得改变章节状态。
- 每次旁路运行必须创建 workflow_run 或 artifact。
- 失败必须返回 `error`，不能静默成功。

## CLI 要求

新增命令：

```bash
novelos scout --project-id demo --topic "都市异能" --llm-mode stub --json
novelos report daily --project-id demo --json
novelos export chapter --project-id demo --chapter 1 --format markdown
novelos continuity-check --project-id demo --from-chapter 1 --to-chapter 5 --llm-mode stub --json
novelos architect suggest --project-id demo --scope quality --llm-mode stub --json
```

所有新增命令：

- 必须支持 `--json`。
- JSON 必须符合 `{ ok, error, data }`。
- 真实 LLM 缺 key 必须失败。
- Stub 模式必须可测试。
- 不得输出 API key。

## ContextBuilder 集成

要求：

- Planner/Author 上下文可以读取最近的 Scout market report。
- Editor/Planner 可读取 ContinuityChecker 的 pending messages 或报告摘要。
- Architect 的 proposal 不自动进入上下文，除非状态被人工标记 accepted。

验收：

- 有 market report 时，Planner context 包含市场摘要。
- 有 continuity warning 时，Editor 或 Planner context 包含 warning。
- pending architecture proposal 不进入生产上下文。

## 测试要求

必须新增或补充：

- `tests/test_sidecar_agents.py`
- `tests/test_v2_cli.py`
- `tests/test_continuity_checker.py`
- `tests/test_reports.py`

最低测试覆盖：

- Scout 生成报告。
- Scout 不改变章节状态。
- Scout artifact 可查询。
- Secretary daily report。
- Secretary chapter export。
- ContinuityChecker 检测状态跳变。
- ContinuityChecker 发送 agent_messages。
- ContinuityChecker 不改变章节状态。
- Architect 生成 pending proposal。
- Architect 不修改配置或章节。
- Dispatcher 旁路方法不调用 run_chapter。
- CLI 新命令 JSON envelope。
- Real mode 缺 key 失败。
- Stub mode 可运行。
- ContextBuilder 注入 market report。
- ContextBuilder 注入 continuity warning。
- migration 005 幂等。

全量测试必须通过，测试数应大于 v1.4 的 `293`。

## 验收标准

v2 通过必须同时满足：

- 全量测试通过。
- 四个旁路 Agent 均有实现和测试。
- 新 CLI 命令可运行。
- 主链路 `run-chapter` 行为不回归。
- 旁路 Agent 不改变章节状态。
- 所有旁路产物可追踪、可查询。
- `agent_messages` 能承载旁路 Agent 给 Planner/Editor 的异步消息。
- 不引入 v2 禁止范围能力。

## 给开发 Agent 的执行顺序

建议按以下顺序开发：

1. 新增 v2 数据模型和 005 migration。
2. 补 Repository 语义化读写方法。
3. 实现 Scout Agent 和 CLI。
4. 实现 Secretary reports/export。
5. 实现 ContinuityChecker。
6. 实现 Architect proposal。
7. Dispatcher 增加旁路方法。
8. ContextBuilder 接入 market report 和 continuity warning。
9. 补齐 CLI JSON envelope 测试。
10. 全量测试。

## 非目标

以下内容不要在 v2 做：

- Web UI。
- REST API。
- 多模型 fallback。
- token 成本统计。
- Agent 级模型路由。
- 云端部署。
- 自动修改 prompt / 规则 / schema。
- 自动发布到平台。

