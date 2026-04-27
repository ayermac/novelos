# 小说内容生产工厂版本路线

## 版本策略

系统按“小闭环先跑通，再逐步增强”的方式迭代。每个版本都必须有明确的范围、验收标准和延后项，避免多个开发 Agent 同时扩散实现。

当前建议路线：

```text
v1   章节生产 MVP
v1r  v1 review 返工闸门
v1.1 工程稳定性
v1.2 质量与一致性增强
v1.3 Dispatcher 编排与 CLI 可运行化
v1.4 运行时硬化与配置化收尾
v2   多 Agent 扩展
v2.1 QualityHub 与 Skill 插件化质量中枢
v2.2 Skill Manifest 化
v2.3 Skill Package 化
v2.4+ 质量与 Skill 增强池（暂缓）
v3.0 Batch Production MVP
v3.1 LLM Profiles & Agent Routing
v3.2 Batch Review & Revision
v3.3 Batch Continuity Gate
v3.4 Production Queue
v3.5 Queue Runtime Hardening
v3.6 Semi-Auto Serial Mode
v3.7 Review Workbench
v3.7.1 CLI Runtime Stable
v3.7.2 Modularity Baseline
v3.8 Skill Import Bridge
v3.9 LLM Model Catalog & Agent Recommendation
v4.0 Style Bible MVP
v4.1 Style Gate & Style Evolution
v4.2 Style Sample Analyzer & Calibration
v4.3 Web UI Acceptance Console MVP
v4.4 Web Review UX Hardening
v4.5 Personal Novel Project Onboarding
v4.6 First Run Guided Workflow
v4.7 Project Workspace / Author Cockpit
v4.8 Web Acceptance Matrix & Parity Hardening
v4.9 Settings / LLM / Agent Ops Console
v4+  Multi-Model & Production Governance
```

## v1：章节生产 MVP

目标：跑通单章创作主链路。

范围：

- `Planner -> Screenwriter -> Author -> Polisher -> Editor`
- LangGraph 状态图。
- `FactoryState`。
- SQLite + Repository。
- Pydantic 输出校验。
- 单一 OpenAI-compatible Provider。
- 基础硬校验。
- 基础 pytest 集成测试。

核心状态：

```text
planned -> scripted -> drafted -> polished -> review -> reviewed -> published
review -> revision -> drafted/polished -> review
任意严重异常 -> blocking
```

验收：

- 一章可以从 `planned` 自动流转到 `published`。
- 审核失败可以进入 `revision`。
- `revision_target=author` 时回到 Author。
- `revision_target=polisher` 时回到 Polisher。
- 同章连续失败达到阈值后进入 `blocking`。
- Agent 输出结构不合法时不写入数据库。

v1 延后：

- Scout。
- Architect。
- Secretary。
- ContinuityChecker。
- 多 Provider 原生适配。
- Skill 热加载。
- Web UI / Web API。

## v1r：v1 review 返工闸门

目标：在进入 v1.1 前，清理 v1 中已经发现的小债务，确保 v1 是稳定基线。

范围：

- 清理 `BaseAgent.run` 重复定义。
- `task_discovery_node` 读取 DB 当前状态。
- `Repository.update_chapter_status` 增加 `expected_status` 保护。
- Agent 前置条件以 DB 当前状态为准。
- 统一 `word_count` 工具函数。
- 补充对应测试。

验收：

- 全量测试通过。
- R1-R5 必修返工全部完成。
- 没有新增 v1.1 或 v2 功能。
- v1 原有验收场景仍通过。

## v1.1：工程稳定性

目标：让 v1 可以反复运行，不产生脏数据。

范围：

- `workflow_runs`。
- `agent_artifacts`。
- `chapter_versions`。
- task 超时处理。
- checkpoint 恢复。
- 幂等写入。
- Repository 状态前置检查。
- 更完整的工作流集成测试。

验收：

- 中断后可以从 checkpoint 恢复。
- 重跑不会重复写入已完成产物。
- 过期任务不能覆盖新章节状态。
- 每个 Agent 产物可追踪来源、版本和 hash。

状态：已通过验收，当前测试基线为 `157/157`。

## v1.2：质量与一致性增强

目标：稳定产出质量，减少返修盲区。

范围：

- 完整 `ContextBuilder`。
- `death_penalty` 检测。
- `state_verifier`。
- `plot_verifier`。
- `learned_patterns`。
- `best_practices`。
- Editor 退回原因分类。
- Polisher 事实变更风险检查。

验收：

- 状态卡不发生静默漂移。
- 伏笔埋设与兑现可验证。
- AI 味和禁用表达能被稳定发现。
- 返修能准确路由到 Author 或 Polisher。

状态：已通过验收，当前测试基线为 `206/206`。

## v1.3：Dispatcher 编排与 CLI 可运行化

目标：让后端无需 Web UI 即可通过 CLI 跑完整章节生产流程。

范围：

- Dispatcher 调度器。
- `novelos` console script。
- `init-db` / `run-chapter` / `status` / `runs` / `artifacts` / `human-resume` 命令。
- 单章状态机运行闭环。
- 人工介入恢复。
- workflow_runs 查询与步骤追踪。
- 自定义 DB 路径。

验收：

- `novelos init-db` 可直接初始化数据库。
- `novelos run-chapter --project-id X --chapter N` 可驱动章节向后运行。
- `novelos status` 可查询章节当前状态和最近错误。
- `blocking` 状态不会继续自动调度。
- `human-resume` 可以恢复到合法状态，但不能直接跳到 `published`。
- 缺失章节、error、requires_human 永远不会进入写入 Agent。
- 全量测试通过，且不回归 v1-v1.2。

v1.3 延后：

- Web UI / Web API。
- Scout / Architect / Secretary。
- ContinuityChecker。
- 多 Provider fallback。
- 云端部署。

状态：已通过验收，当前测试基线为 `267/267`。

## v1.4：运行时硬化与配置化收尾

目标：让 `novelos` 从源码可运行升级为安装后可运行、配置可诊断、本地可 smoke test。

范围：

- 包资源完整性。
- `config show` / `config validate`。
- `--llm-mode stub|real` 显式化。
- `seed-demo`。
- `smoke-run`。
- `doctor`。
- `revision_target` 结构化存储。
- CLI 错误码与 JSON 输出稳定性。

验收：

- `pip install -e .` 后 `novelos --help` 可用。
- `novelos init-db` 不依赖 `openclaw-agents` 外部路径。
- `novelos seed-demo` 能创建可运行 demo 数据。
- `novelos run-chapter --llm-mode stub` 可跑 demo。
- `novelos run-chapter --llm-mode real` 缺 key 时清晰失败，不静默降级。
- API key 不出现在 stdout / logs / JSON。
- Dispatcher 优先读取结构化 `reviews.revision_target`。
- 全量测试通过，且不回归 v1-v1.3。

v1.4 延后：

- Web UI / Web API。
- Scout / Architect / Secretary。
- ContinuityChecker。
- 多 Provider fallback。
- token 成本统计。

状态：已通过验收，当前测试基线为 `293/293`。

## v2：多 Agent 扩展

目标：从章节流水线升级为具备旁路协作能力的小说工厂。

范围：

- Scout Agent。
- Architect Agent。
- Secretary Agent。
- ContinuityChecker Agent。
- 市场报告。
- 日报/周报。
- 每 3-5 章跨章一致性检查。
- Prompt / 规则优化建议。
- `agent_messages` 异步协作。
- 旁路 Agent CLI。

验收：

- Scout 不阻塞章节生产。
- ContinuityChecker 周期触发，不进入每章主链路。
- Architect 只提出规则、Prompt、迁移建议，不直接改生产内容。
- Secretary 可导出章节、版本和日报。
- 旁路 Agent 不改变章节状态。
- 旁路产物可追踪、可查询。

状态：已通过验收，当前测试基线为 `321/321`。

## v2.1：QualityHub 与 Skill 插件化质量中枢

目标：把 AI 去味、质量评分、事实一致性、叙事质量等能力统一到可配置质量中枢。

范围：

- QualityHub。
- `skills.yaml`。
- SkillRegistry。
- BaseSkill / TransformSkill / ValidatorSkill。
- HumanizerZhSkill。
- AIStyleDetectorSkill。
- NarrativeQualityScorer。
- Polisher 配置化挂载 Humanizer。
- Editor 配置化挂载 AIStyleDetector。
- quality_reports / skill_runs。

验收：

- QualityHub 可汇总多个质量检查结果。
- Polisher 可配置启用 AI 去味 Skill。
- Editor 可配置启用 AI 味检测 Skill。
- fact_lock 不被 Skill 绕过。
- 每章质量报告可保存和查询。
- Skill 可启用/禁用。
- CLI 可查看和运行 Skill。

状态：已通过验收，当前测试基线为 `359/359`。

## v2.2：Skill Manifest 化

目标：把 v2.1 的内置 Python Skill 升级为有 manifest 契约的能力单元，为后续通用 Agent Skill 做准备。

范围：

- `skill.yaml` manifest 规范。
- Skill 输入输出 schema。
- Skill 权限声明。
- Skill 适用 Agent 与适用阶段声明。
- Skill 失败策略声明。
- Skill 配置 schema 与默认值。
- SkillRegistry 支持读取 manifest。
- 现有 `skills.yaml` 与 manifest 的兼容迁移。

验收：

- 每个内置 Skill 都有 manifest。
- manifest 可被校验。
- SkillRegistry 可从 manifest 构建 skill 元数据。
- Skill 权限超范围时拒绝执行。
- Agent 只能在 manifest 声明的阶段挂载 Skill。
- 旧 `skills.yaml` 配置仍可运行，或有清晰迁移路径。

状态：已通过验收，当前测试基线为 `409/409`。

v2.2 延后：

- Skill 目录包结构。
- 外部 Skill 加载。
- Skill 沙箱执行。
- Skill marketplace。

## v2.3：Skill Package 化

目标：让 Skill 从单个 Python 类升级为可维护的目录包。

范围：

- 每个 Skill 一个目录。
- `manifest.yaml`。
- `handler.py`。
- `prompts/`。
- `rules/`。
- `tests/fixtures`。
- Skill 自测命令。

验收：

- 内置 Skill 可迁移为 package。
- Skill 包可单独运行测试。
- prompt/rules/config 与 handler 分离。

状态：已通过最终验收，当前测试基线为 `478/478`。

## v2.4+：质量与 Skill 增强池（暂缓）

v2.3 之后，v2.x 的质量治理和 Skill Package 主线已经形成闭环。以下能力暂不进入当前开发主线，作为后续增强池保留：

- 通用 Agent Skill Registry。
- 更多内置质量 Skill。
- 平台风格 Skill 包。
- Skill benchmark 与评测集。
- 更复杂 Skill 权限与审计。
- Skill 沙箱执行。
- 外部 Skill marketplace / 热加载。

暂缓原因：

- 当前更高价值的缺口是批次生产调度，而不是继续堆叠 Skill 能力。
- v3.0 需要把 v1 单章主链路和 v2 质量治理能力用于多章节自动创作。
- 外部热加载、沙箱和 marketplace 风险较高，应等批次生产闭环稳定后再规划。

## v3.0：Batch Production MVP

目标：从单章自动创作升级为多章节批次自动创作。

范围：

- `batch run`：指定项目与章节范围，逐章调用现有 `Dispatcher.run_chapter()`。
- `batch status`：查询批次状态和每章执行结果。
- `batch review`：记录人工集中 review 决策。
- `production_runs`。
- `production_run_items`。
- `human_review_sessions`。
- `Dispatcher.run_batch()`。
- `Dispatcher.get_batch_status()`。
- `Dispatcher.review_batch()`。

核心规则：

- 必须复用 `run_chapter()`，不得重写 Agent 主链路。
- 默认 `stop_on_block=true`。
- 某章失败、`requires_human` 或 `blocking` 时，批次进入 `blocked`。
- 全部成功后批次进入 `awaiting_review`，等待人工确认。
- v3.0 不自动最终批准整批内容。

验收：

- `novelos batch run --project-id demo --from-chapter 1 --to-chapter 3 --json` 可运行。
- `novelos batch status --run-id <run_id> --json` 可查询 run 和 items。
- `novelos batch review --run-id <run_id> --decision approve --json` 可记录人工决策。
- 所有 `--json` 输出稳定为 `{ok,error,data}`。
- 全量测试通过，新增测试数量大于 v2.3 基线 `478`。

禁止：

- Web UI / FastAPI。
- daemon 常驻任务。
- 定时自动创作。
- Redis / Celery / Kafka。
- PostgreSQL。
- 多项目并行。
- 复杂并发批处理。
- 章节级复杂返修。
- 自动重写全部章节。
- 自动发布整批内容。
- 改主链路 Agent 顺序。
- 重写 Skill Package 系统。

## v3.1：LLM Profiles & Agent Routing

目标：支持不同 Agent 使用不同大模型 API、key、base_url 和 model。

范围：

- 项目根目录 `.env` 加载本地 API key。
- `.env.example` 占位模板。
- `llm_profiles` 配置。
- `default_llm` 默认模型配置。
- `agent_llm` Agent 到 profile 的映射。
- `LLMRouter.for_agent(agent_id)`。
- Dispatcher 按 Agent 获取 LLMProvider。
- Agent 未单独配置时回退默认 LLM。
- CLI / config 诊断隐藏 key。

配置示例：

```yaml
default_llm: default

llm_profiles:
  default:
    provider: openai_compatible
    base_url_env: OPENAI_BASE_URL
    api_key_env: OPENAI_API_KEY
    model: gpt-4o-mini

  author:
    provider: openai_compatible
    base_url_env: OPENROUTER_BASE_URL
    api_key_env: OPENROUTER_API_KEY
    model: anthropic/claude-3.7-sonnet

agent_llm:
  planner: default
  screenwriter: default
  author: author
  polisher: default
  editor: default
```

规则：

- Agent 有单独配置时使用对应 profile。
- Agent 未单独配置时使用 `default_llm`。
- `stub` 模式下所有 Agent 使用 StubLLM。
- `real` 模式缺 key 或 profile 不存在时清晰失败。
- 不得在日志、JSON 或 `config show` 中泄露明文 key。

验收：

- Author 和 Editor 可使用不同模型配置。
- 未配置 Agent 自动回退默认 LLM。
- `.env` 可维护 key，`.env.example` 不含真实 key。
- 旧单 LLM Stub 测试仍兼容。

禁止：

- 多 Provider fallback。
- Provider 健康检查。
- token 成本统计。
- 预算控制。
- 自动降级。

## v3.2：Batch Review & Revision

目标：在 v3.0 批次生产基础上，支持人工指定章节返修和批次返修闭环。

范围：

- 指定章节返修。
- 指定章节重跑。
- 从某章开始重跑。
- 全批次 request changes。
- review notes 下发给 Planner / Author / Polisher。
- 返修后的批次状态追踪。

验收：

- 用户可选择修改某几章。
- 用户可选择从某章开始重跑后续章节。
- 返修不会覆盖未选中的章节。
- 所有返修动作可审计。

## v3.3：Batch Continuity Gate

目标：为多章节批次增加批次级连续性审核，避免多章自动创作时设定漂移。

范围：

- 批次完成后触发 ContinuityChecker。
- 检查角色状态连续性。
- 检查伏笔埋设与回收。
- 检查时间线和地点跳变。
- 检查多章节奏空转或断裂。
- 连续性报告注入 batch review。

验收：

- 批次级连续性问题能阻止 approve。
- 连续性问题能映射到具体章节。
- review 时能看到跨章风险摘要。

## v3.4：Production Queue

目标：支持多个批次排队、暂停、恢复和失败重试。

范围：

- production queue。
- batch pause / resume。
- batch retry。
- max budget / max chapters guard。
- 批次级 timeout。
- 失败重试策略。

验收：

- 批次可暂停和恢复。
- 失败批次可按策略重试。
- 不需要 Redis/Celery，也能完成本地 SQLite 队列 MVP。

## v3.5：Queue Runtime Hardening

目标：让本地生产队列在真实运行中可诊断、可取消、可恢复。

范围：

- queue events 查询。
- queue cancel。
- stuck running queue item recover。
- queue doctor。
- `queue-run --limit`。
- queue item 到 production_run / workflow_run 的诊断串联。
- 更严格的状态转移矩阵测试。

验收：

- 用户可以查看 queue item 事件历史。
- 用户可以取消未完成 queue item。
- 用户可以恢复卡死 running item。
- 用户可以诊断 queue / production_run / workflow_run 链路。
- 所有新增状态变化都有审计事件。

## v3.6：Semi-Auto Serial Mode

目标：支持半自动连载计划，例如每轮生成固定章节数，但每轮完成后必须等待人工确认。

范围：

- serial plan。
- 每轮生产目标。
- 分轮 enqueue。
- 人工确认后进入下一轮。
- serial plan 与 queue / production run 关联。
- serial plan events 审计。

验收：

- 用户可设置每轮生成章节数和目标章节。
- 每轮完成后进入人工 review。
- 不经人工确认不得自动进入下一轮。
- 多章节 approve 必须通过 continuity gate。
- 所有 serial 操作可审计。

## v3.7：Review Workbench

目标：让人工审核多章节批次和半自动连载计划时，不再需要手动拼接 status、quality、continuity、queue、serial 和版本数据。

范围：

- review pack。
- chapter review view。
- timeline 聚合。
- chapter version diff 摘要。
- markdown / json 导出。
- approve 辅助判断 `decision_hint`。

验收：

- 用户可按 production run、serial plan 或章节范围生成 review pack。
- review pack 能显示 blocking reasons、warnings、continuity gate、quality reports 和章节摘要。
- review timeline 能聚合 serial、queue、batch、revision、quality 等事件。
- review diff 能比较最新版本与上一版本，或指定两个版本。
- review export 可导出 markdown / json。
- 所有 review 命令只读，不改变生产状态。

禁止：

- Web UI / FastAPI。
- 自动 approve。
- 自动 publish。
- 自动 request_changes。
- 自动生成 revision plan。
- 新增 LLM 调用。
- 新增 Agent。

## v3.8：Skill Import Bridge

目标：把 skills.sh / Codex / Claude Code / Cursor 生态里的本地 `SKILL.md` 型 Agent Skill，安全转换为 novel_factory 内部受控 Skill Package 草案。

范围：

- 本地 Skill 目录读取。
- `SKILL.md` frontmatter 解析。
- import plan。
- 生成 `novel_factory/skill_packages/<id>` 草案。
- 生成 manifest / handler stub / fixtures。
- 检测 scripts / references / assets / rules / prompts。
- `skills import-plan`。
- `skills import-apply`。
- `skills import-validate`。

验收：

- 能从本地 `SKILL.md` 目录生成 package 草案。
- 生成的 Skill 默认只允许 `manual/manual`。
- 生成的 Skill 不自动挂载到 Polisher / Editor / Author。
- 外部 scripts 只复制不执行，默认 disabled。
- imported package 可被 `skills validate` / `skills test` 检查。
- 所有 JSON 输出稳定 envelope。

禁止：

- 联网下载 skills.sh skill。
- 调用 `npx skills add`。
- 任意 GitHub clone。
- 外部 Skill 热加载。
- 自动启用 imported Skill。
- 自动修改生产 Agent 挂载配置。
- 自动执行外部 scripts。

状态：已通过验收。

## v3.7.1：CLI Runtime Stable

目标：CLI 稳定化，--version 支持与错误处理增强。

范围：

- `--version` flag 支持。
- CLI 错误码稳定。
- JSON envelope 稳定性。

状态：已通过验收。

## v3.7.2：Modularity Baseline

目标：核心大文件模块化拆分，提升多 Agent 可维护性。

范围：

- CLI 模块化（cli.py ≤ 150 行 → cli_app/ 包）。
- Repository 模块化（repository.py ≤ 300 行 → repositories/ 包）。
- Dispatcher 模块化（dispatcher.py ≤ 300 行 → dispatch/ 包）。
- 文件体积策略测试。

状态：已通过验收。

## v3.9：LLM Model Catalog & Agent Recommendation

目标：建立离线、可审计的 LLM 模型目录和 Agent 模型推荐系统，让用户可以查看"每个 Agent 适合用什么模型"，并生成推荐配置草案。

范围：

- LLM Model Catalog 配置（`novel_factory/config/llm_catalog.yaml`）。
- 每个 provider/model 的能力标签、价格等级、上下文长度、推荐用途。
- Agent 级模型推荐器（`novel_factory/llm/recommender.py`）。
- 根据 Agent 职责自动推荐模型（Planner 偏推理、Author 偏长文本、Editor 偏审校等）。
- CLI 命令：`llm catalog`、`llm recommend`、`llm config-plan`。
- 生成 `llm_profiles` + `agent_llm` 配置草案（只输出不写盘）。
- 保持与 v3.1 LLMRouter 完全兼容。

推荐逻辑：

- Planner/Screenwriter：偏 reasoning + planning + json。
- Author：偏 prose + long_context。
- Polisher：偏 editing + prose + safety。
- Editor：偏 editing + reasoning + json。
- Scout：偏 speed + summarization/reasoning。
- ContinuityChecker：偏 long_context + reasoning + json。
- Architect：偏 reasoning + json。
- Secretary：偏 low cost + speed。

constraints 支持：cost_tier 最大值、quality_tier 最小值、provider 白名单、require_strengths、prefer_low_latency。

验收：

- `novelos llm catalog --json` 可列出所有模型。
- `novelos llm recommend --agent author --json` 可推荐模型。
- `novelos llm recommend --all --json` 可推荐所有 Agent 模型。
- `novelos llm config-plan --all --json` 可输出配置草案。
- 所有 `--json` 输出稳定为 `{ok, error, data}` 信封。
- 推荐输出不包含 API key 或任何 secret。
- 不修改主创作流程、不写用户配置、不联网。
- 现有 v3.1 llm CLI 测试不回归。
- 全量测试通过。

禁止：

- 不实现自动 fallback。
- 不做 provider health check。
- 不做真实 API 调用。
- 不做联网模型榜单同步。
- 不写入用户配置文件。
- 不修改 `.env`。
- 不引入数据库 migration。
- 不修改主 Agent 编排流程。
- 不新增 Web UI / FastAPI。
- 不让推荐器自动覆盖用户现有 `agent_llm`。

状态：已通过验收，当前测试基线为 `932/932`。

## v4.0：Style Bible MVP

目标：支持项目级 Style Bible，让不同平台/受众使用不同的写作风格配置，并集成到 Agent 上下文和质检流程。

范围：

- Style Bible 数据模型（Pydantic）：pacing、POV、tone_keywords、forbidden/preferred expressions、AI trace avoidance、sentence/paragraph/chapter rules
- 数据库迁移（012_v4_0_style_bible.sql）：style_bibles 表
- Repository Mixin（StyleBibleRepositoryMixin）：CRUD + rowcount 检查
- 模板系统（5 套预设模板）：default_web_serial、urban_fantasy_fast、xianxia_progression、romance_emotional、mystery_suspense
- ContextBuilder 集成：按 agent_id 注入不同规则子集到 Planner/Author/Editor 上下文
- StyleBibleChecker Skill：纯规则检查（不调 LLM、不联网）
- QualityHub 集成：check_draft 中运行 Style Bible 检查（v4.0 MVP 仅 warning 级）
- CLI 命令：style templates/init/show/update/check/delete
- 禁止模仿作者风格、禁止 LLM 调用检查、禁止联网、禁止自动重写、默认不阻塞主生产流

验收：

- `novelos style templates --json` 列出可用模板。
- `novelos style init --project-id demo --template default_web_serial --json` 创建 Style Bible。
- `novelos style show --project-id demo --json` 展示 Style Bible。
- `novelos style update --project-id demo --set genre=仙侠 --json` 更新字段。
- `novelos style check --project-id demo --chapter 1 --json` 检查章节风格合规。
- `novelos style delete --project-id demo --json` 删除 Style Bible。
- 所有 CLI 输出稳定 `{ok, error, data}` 信封。
- Style Bible 进入 Planner/Author/Editor 上下文（可验证）。
- QualityHub 不阻塞发布（仅 warning 级）。
- Repository 写入有 rowcount 检查。
- Migration 012 幂等。
- 文件体积策略达标。
- 全量测试通过（基线 1015/1015）。

状态：已通过验收。

## v4.1：Style Gate & Style Evolution

目标：将 Style Bible 从"可检查"升级为"可治理"——支持可配置 Style Gate、结构化风格返修建议、Style Bible 版本记录，以及人工确认的风格演进建议。

范围：

- Style Gate：per-project 可配置 gate（off/warn/block），集成 QualityHub
- Style Bible 版本记录：每次更新自动保存版本快照
- 结构化返修建议：rule-based，不调用 LLM
- Style Evolution Proposal：聚合历史风格问题生成提案，人工 approve/reject，不自动应用
- DB 迁移 013：style_bible_versions + style_evolution_proposals 表
- CLI 命令：style gate/gate-set/versions/version-show/propose/proposals/proposal-show/proposal-decide

验收：

- 默认配置不阻断旧流程（enabled=False, mode=warn）
- mode=block 能阻断
- proposal approve 不修改 Style Bible
- Style Bible 更新时自动创建版本快照
- 版本快照包含更新前数据
- CLI 错误路径稳定 envelope，无 traceback
- 无作者模仿字段
- 全量测试通过

状态：已通过验收，测试基线 1093/1093。

## v4.2：Style Sample Analyzer & Calibration

目标：实现"风格样本分析与校准"能力。用户可以导入本地样本文本，系统提取结构化风格特征，并基于样本特征生成 Style Bible 演进提案。

范围：

- Style Sample 数据模型（StyleSampleSource/Status/Metrics/Record）
- DB 迁移 014：style_samples 表
- StyleSampleRepositoryMixin：save/list/show/update/delete/get_by_ids
- 纯规则风格样本分析器（sample_analyzer.py）：句长、对话比、动作/心理/描写比、AI 痕迹风险、氛围关键词、节奏描述
- 基于样本的 Style Evolution Proposal 生成器（sample_proposal.py）：聚合指标 → 生成 pending proposals
- CLI 命令：style sample-import/sample-analyze/sample-list/sample-show/sample-delete/sample-propose
- QualityHub 轻集成：style_sample_alignment 维度 + 低对齐度 warning
- 安全边界：不联网、不抓取、不模仿作者、不训练模型、不保存全文、不自动修改 Style Bible

验收：

- 样本导入自动分析，不保存全文只保存 preview + hash + metrics
- 重复 content_hash 不重复导入
- import 空文件/不存在/超大返回错误 envelope
- propose 从样本生成 pending proposals
- proposal approve 不修改 Style Bible
- QualityHub 没有样本时不报错，有样本时加入 alignment 维度
- 不出现作者模仿字段
- 全量测试通过，0 skipped

状态：已通过验收，测试基线 1175/1175。

## v4.3：Web UI Acceptance Console MVP

目标：提供轻量级 Web UI 验收控制台，让用户通过浏览器进行人工审核、批次管理、队列监控和风格配置，无需终端操作。

范围：

- FastAPI + Jinja2 + HTMX 轻量 Web 服务
- Dashboard：系统状态、最近运行、队列项
- Projects：项目列表与详情
- Run Chapter：单章运行表单
- Batch：批次生产、状态查询、审核决策
- Queue：队列管理（暂停、恢复、重试、恢复）
- Serial：连载计划管理
- Review：审核工作台（pack、chapter、timeline、diff、export）
- Style：Style Bible、Gate、Proposals、Samples 管理
- Config：配置查看（API keys 已脱敏）
- CLI 命令：`novelos web --host 127.0.0.1 --port 8765 --db-path ./novel_factory.db --llm-mode stub`
- 16 项约束：无登录、无多用户、无 WebSocket、无后台 workers、无 Redis/Celery/Kafka、无 PostgreSQL、无 SQLite 替换、无自动发布、无自动批准、无绕过 Dispatcher、无明文 API keys、无 API keys 泄露、无真实 LLM 测试、无 traceback 泄露、文件 <1000 行、模板拆分

验收：

- 所有 26 个 v4.3 测试通过
- 全量测试通过（1201/1201）
- 所有 16 项约束满足
- 文件体积策略达标（最大文件 124 行）
- API keys 永不暴露在 HTML/logs/tests
- 错误页面无 traceback
- 所有路由调用 Dispatcher 方法
- CLI 命令 `novelos web --help` 可用
- 依赖已添加到 pyproject.toml 和 requirements.txt
- 无 config/stderr.txt/API keys 提交到仓库

状态：已通过验收，测试基线 1201/1201

## v4.4：Web Review UX Hardening

目标：把 v4.3 的本地 Web 验收控制台打磨成更适合个人作者完整验收的操作台，减少手输 ID、减少原始 JSON、增强批次/队列/连载/风格审核的状态可视化。

范围：

- Review 页面卡片化展示 review pack、decision_hint、chapters、quality issues、continuity gate、queue status、timeline。
- Batch 页面展示 production runs 列表、章节范围、进度、阻塞章节，并为 awaiting_review run 提供行内审核表单。
- Queue 页面按状态分组展示 pending/running/failed/timeout/paused/completed，并提供合法操作按钮。
- Serial 页面展示 serial plans、进度、current queue/run，并提供 enqueue-next/advance/pause/resume/cancel 操作。
- Style 页面展示 gate config、samples、pending proposals，并支持行内 approve/reject。
- 统一 result/error panel，错误不泄露 traceback 或 API key。

验收：

- v4.3 + v4.4 Web 测试通过（38/38）。
- 全量测试通过（1213/1213）。
- 文件体积策略通过。
- 所有新增 POST 测试验证真实 DB 状态变化，不只断言 HTTP 200。
- 不引入登录、权限、多用户、WebSocket、daemon、Redis/Celery/Kafka/PostgreSQL。

状态：已通过验收，测试基线 1213/1213

## v4.5：Personal Novel Project Onboarding

目标：让个人作者可以通过 Web UI 从 0 创建小说项目，并一次性初始化初始章节、首章目标、世界观、主角、Style Bible 和可选 Serial Plan。

范围：

- Dashboard / Projects 页面提供 Onboarding 入口。
- 新增 `/onboarding` 项目创建表单。
- 新增 `/onboarding/project` 创建项目提交入口。
- 创建 `projects`、planned chapters、可选 instruction、world setting、character。
- 复用 v4.0 Style Bible 模板系统，默认模板为 `default_web_serial`。
- 可选创建 Serial Plan。
- 单一事务完成所有写入，失败 rollback。
- 成功页提供 Run Chapter、Batch、Serial、Queue、Style、Review、项目详情等下一步入口。

验收：

- v4.5 Onboarding 测试通过（21/21）。
- Web 测试通过（59/59）。
- 文件体积策略通过（65/65）。
- 全量测试通过（1234/1234）。
- `total_chapters_planned` 必须覆盖初始章节范围。
- 创建失败不留下半成品项目或关联数据。
- Style Bible 来自 v4.0 模板系统，不使用硬编码模板。
- 成功页包含开始创作和项目管理入口。
- 不提交本地 `config/acceptance.yaml`、`stderr.txt` 或真实密钥。

状态：已通过验收，测试基线 1234/1234。

## v4.6：First Run Guided Workflow

目标：承接 v4.5 Onboarding，让新项目创建成功后可以自然完成第一章运行、查看结果和进入审核的闭环。

范围：

- 成功页提供第一章 guided run 入口。
- Run Chapter 页面识别新项目并自动带入 project/chapter。
- 运行成功后跳转到 Review 或 Chapter 详情。
- 运行失败时显示可操作错误，不泄露 traceback/API key。
- stub 模式覆盖完整 Web E2E 验收。

验收：

- 从 Onboarding 成功页可以一键进入第一章运行。
- stub 模式下第一章可以完成可验证的运行闭环。
- 运行后的章节状态、run 记录和 review 入口可在 Web 中追踪。
- 失败路径保留上下文并给出下一步操作。
- 不引入登录、权限、多用户、后台 worker 或真实 LLM 测试。

状态：**已通过验收**，测试基线 1254/1254。

## v4.7：Project Workspace / Author Cockpit

目标：将 `/projects/{project_id}` 升级为项目级作者工作台，聚合项目状态、章节进度、最近运行、Review 待办、Queue、Serial、Style 状态和下一步操作。

范围：

- Project Overview：项目基础信息、当前章节、计划章节、目标字数。
- Next Best Action：根据阻塞、待审核、可运行章节、队列失败、Style proposal 等状态推荐下一步。
- Chapter Progress：章节状态分组、最近章节列表、Run/Review 链接。
- Recent Runs：最近 workflow_runs。
- Review Queue：Review Workbench 入口和待审核摘要。
- Production Queue：当前项目 queue items 摘要。
- Serial Plan：当前项目 serial plans 摘要。
- Style Health：Style Bible、Style Gate、pending proposals、samples 摘要。
- Quick Actions：Run Chapter、Batch、Queue、Serial、Review、Style。

验收：

- `/projects/{project_id}` 展示项目工作台。
- 页面展示项目基础信息、章节进度、最近 run。
- 页面展示 Review、Queue、Serial、Style 状态或空状态。
- 页面展示 Quick Actions。
- 项目不存在时显示可读错误，不出现 traceback。
- 页面不包含 API key / secret。
- seeded DB 中的 run/queue/serial/style 数据能在页面出现。
- 不新增生产写入逻辑，不自动运行/approve/publish。
- Next Best Action 正确识别阻塞章节、待审核章节、队列失败、待处理 Style proposals、可运行章节，并按优先级推荐。
- Review Queue 正确识别 `status='review'` 的待审核章节。
- Style Health 正确显示 Style Gate 配置状态和待处理 proposals 数量。

状态：**已通过最终验收**，测试基线 1283/1283。

## v4.8：Web Acceptance Matrix & Parity Hardening

目标：新增 Web Acceptance Matrix，让 Web UI 可以展示所有已实现能力的验收覆盖情况，包括 Web route、CLI command、success test、failure test、DB assertion、secret/traceback safety、status。

范围：

- 新增 `/acceptance` 路由展示验收矩阵
- 集中定义所有能力及其验收状态（14 个能力）
- 展示 Web route、CLI command、测试覆盖、DB 验证、安全检查
- 页面以 read-model 展示为主，不新增生产写入逻辑
- 不执行 pytest 或 shell 命令
- 不泄露 API key、secret、traceback

验收：

- GET /acceptance 返回 200
- 页面包含所有核心能力
- 页面包含 pass/partial/missing 状态
- 页面展示 Web route 和测试覆盖信息
- 页面不包含 Traceback/API key/secret
- acceptance matrix 定义来自集中 Python 数据结构，不只是在模板硬编码
- 每个 capability_id 唯一
- 每个 capability 至少有 label/web_route/status
- status 只能是 pass/partial/missing
- 页面有摘要统计
- 页面不展示 raw JSON
- 不执行 pytest 或 shell 命令
- 不写入数据库
- 不触发生产逻辑

状态：**已通过最终验收**，测试基线 1312/1312。

## v4.9：Settings / LLM / Agent Ops Console

目标：新增 Web Settings / LLM / Agent Ops Console，让用户可以在浏览器中查看当前 LLM 配置、Agent 路由、模型推荐、Skill/QualityHub 状态和诊断信息。

范围：

- 新增 `/settings` 路由展示配置与运行状态控制台
- 展示 Runtime Mode（llm_mode, default_llm）
- 展示 LLM Profiles 列表（provider, model, base_url, api_key 状态）
- 展示 Agent Routing（agent_id → profile 映射，fallback 标记）
- 展示 Model Recommendations（Top 3 推荐 per Agent）
- 展示 Skill/QualityHub 状态
- 展示 Diagnostics（配置验证、警告、错误）
- 所有敏感信息脱敏（API keys, secrets）
- 无 raw JSON 显示，无 traceback 泄露
- 只读页面，无生产写入逻辑
- 更新 v4.8 acceptance matrix 新增 settings_ops capability

验收：

- GET /settings 返回 200
- 页面展示 runtime mode 和 default_llm
- 页面展示 LLM profiles 列表
- 页面展示 agent routing 映射
- 页面展示 model recommendations
- 页面展示 skill/qualityhub 状态
- 页面展示 diagnostics
- API keys 和 secrets 已脱敏
- 页面不包含 raw JSON
- 页面不包含 traceback
- 页面不执行生产写入
- 页面不触发生产逻辑
- acceptance matrix 包含 settings_ops capability
- v4.9 测试通过（29/29）
- Web UI 测试通过（166/166）
- 文件体积策略通过（65/65）
- 全量测试通过（1341/1341）

状态：**已通过最终验收**，测试基线 1341/1341。

## v5.0：Implemented Features & WebUI Acceptance

目标：对 v1-v4.9 已实现功能做整体验收和 WebUI 验收，确认每个 pass capability 真实可验证，不新增大功能。

范围：

- 基于 acceptance matrix 梳理 v1-v4.9 已实现能力（16 个 pass capability）
- 确认每个 pass capability 的 web_route 存在并返回可读页面
- 确认 success_test/failure_test 文件真实存在
- 新增 v5.0 整体验收测试
- 覆盖 WebUI 核心链路 12 个路径
- 验证安全：不泄露 API key/secret/traceback/raw JSON
- 验证文档一致性：README、roadmap、v5.0 spec、acceptance matrix
- 如发现已有能力标 pass 但覆盖不足，标注 partial 或补测试

验收：

- 16 个 capability 全部为 pass，无 partial 或 missing
- 所有 success_test 文件真实存在
- 所有 web_route 返回 200
- 无 API key/secret/traceback 泄露
- v5.0 专项测试通过
- Web UI 组合测试通过
- 全量测试通过

状态：**已通过验收**，测试基线 1386/1386。

## v5.0.1：WebUI Productization & Chinese UX

目标：将 v5.0 的"验收控制台"升级为"中文作者工作台"，让现有功能看起来统一、清晰、可日常使用。

范围：

- 全站中文界面（导航、标题、表单、按钮、状态、空状态）。
- 左侧导航 + 顶部状态栏布局（专业 SaaS 风格）。
- 设计系统：卡片、表格、按钮、表单、状态徽章、NBA 面板。
- Review 页面重做：首屏展示审核队列，高级工具折叠。
- Settings 配置中心：LLM 档案、Agent 路由、模型推荐、配置向导。
- Config 页面改为只读诊断入口，引导到 Settings。
- 配置向导：默认只生成配置草案（客户端 JavaScript），不写入真实配置。
- API Key 输入框为 password 类型，页面只显示"已配置/未配置"。
- 所有页面补中文空状态和下一步引导。
- 不新增真实 LLM 调用，不自动 approve/publish。
- 不引入登录、多用户、权限、WebSocket、Redis/Celery。

验收：

- 导航中文化测试通过。
- Review 页面中文化测试通过。
- Config/Settings 页面中文化测试通过。
- 配置向导存在且为草案模式。
- API key 不泄露。
- 生成配置草案不写真实文件。
- 空状态可读。
- 页面无 traceback/raw JSON。
- v5.0 专项测试通过。
- WebUI 组合测试通过。
- 全量测试通过。

状态：**已通过验收**，测试基线 1420/1420。

## v5.1：Frontend Separation & API Backend

目标：废弃 Jinja WebUI，实现前后端分离架构，为后续扩展和部署灵活性打下基础。

范围：

- 删除/弃用 Jinja WebUI（templates、HTML routes、Jinja helpers）
- 创建 FastAPI JSON API 后端（`/api` 路由前缀）
- 创建 React + Vite + TypeScript 独立前端（`frontend/` 目录）
- 保留 CLI、Repository、Dispatcher 和核心业务能力
- API 和 CLI 共享核心服务（API 不通过 shell 调用 CLI）
- 前端基于 v5.0.1 设计规范，面向中文作者工作台

API 要求：

- 统一信封格式：`{ok: bool, error: {code, message} | null, data: any | null}`
- 标准化错误码和错误消息
- 不暴露 traceback
- 不暴露 API key/secret
- Stub 模式安全（无真实 LLM 调用）

API 端点：

- `GET /api/health` - 健康检查
- `GET /api/dashboard` - 总览数据
- `GET /api/projects` - 项目列表
- `GET /api/projects/{project_id}` - 单个项目
- `GET /api/projects/{project_id}/workspace` - 项目工作台
- `POST /api/onboarding/projects` - 创建项目
- `POST /api/run/chapter` - 运行章节
- `GET /api/review/workbench` - 审核工作台
- `GET /api/review/pack` - 审核包
- `GET /api/review/chapter` - 章节审核
- `GET /api/review/timeline` - 时间线
- `GET /api/review/diff` - 版本差异
- `GET /api/style/console` - 风格控制台
- `GET /api/settings` - 设置
- `POST /api/config/plan` - 配置草案
- `GET /api/acceptance` - 验收矩阵

前端页面（9 个）：

- `/` - 总览（Dashboard）
- `/projects` - 项目列表
- `/projects/:id` - 项目详情
- `/onboarding` - 创建项目
- `/run` - 运行章节
- `/review` - 审核
- `/style` - 风格
- `/settings` - 配置
- `/acceptance` - 验收

禁止：

- 不引入登录/多用户/权限
- 不引入 Redis/Celery/WebSocket
- 不新增真实 LLM 调用测试
- 不提交 config/acceptance.yaml、stderr.txt、真实密钥
- API 不返回 API key 到前端

验收：

- API 信封格式测试通过
- API 错误处理测试通过
- API 安全测试通过（无密钥泄露）
- Stub 模式运行章节测试通过
- CRUD 操作测试通过
- 配置草案生成测试通过
- 前端文件结构测试通过
- 前端中文标签测试通过
- 前端构建配置测试通过
- 全量测试通过

状态：**已通过验收**，测试基线 1252/1252。

## v5.1.1：WebUI Product Reset

目标：将 v5.1 React WebUI 从"API demo"升级为真正的"中文作者工作台"。

范围：

- 统一状态映射（completed→已完成, review→待审核, etc.）
- 新增可复用组件（StatusBadge, EmptyState, ErrorState, PageHeader）
- API 优雅降级（Style console 对缺失表返回 ok=true + 空数据）
- 增强所有 9 个页面：
  - Dashboard: 下一步建议卡片、快捷操作
  - Projects: 中文类型标签
  - ProjectDetail: NextAction 建议、章节进度统计
  - Onboarding: Wizard 表单、成功结果面板
  - Run: 项目信息展示、结构化结果面板
  - Review: 统计概览、StatusBadge 中文
  - Style: 优雅空状态、健康摘要
  - Settings: 配置诊断、启动命令示例
  - Acceptance: 卡片列表（防溢出）、partial 显示"迁移中"
- 修复表格溢出：所有表格增加 overflowX: auto 容器
- 完整 TypeScript 类型检查 + 生产构建

状态：**已通过验收**，测试基线 1255/1255。

## Post-Acceptance Hardening

v5.1 已完成 Post-Acceptance Hardening，新增：

**Smoke 验收脚本**：
- `scripts/v51_smoke_acceptance.sh` - 一键验收脚本

**新增测试**：
- `test_v51_api_e2e_smoke.py` - 17 个端到端 smoke 测试
- `test_v51_frontend_quality.py` - 8 个前端质量检查
- `test_v51_api_security.py` - 9 个 API 安全测试

**验收覆盖**：
- ✅ API 统一响应格式
- ✅ 中文错误消息
- ✅ 不暴露 traceback、绝对路径、API 密钥
- ✅ Stub 模式安全运行
- ✅ 前端中文导航和错误处理
- ✅ Config plan 不写文件

## v5.2+：多模型与生产治理

目标：支持真实长期运行所需的模型、成本、可观测性和数据治理。

范围：

- 多 Provider 原生适配。
- Agent 级模型路由。
- fallback。
- token 成本统计。
- Provider 健康检查。
- LangSmith 或自定义 trace。
- 数据备份与恢复。
- 人工审核 UI 或 CLI。

验收：

- 主模型失败后可以自动降级。
- token 成本可按 Agent 和项目统计。
- 每次失败能定位到模型、规则、数据或流程。
- 生产数据可备份、恢复和审计。

## 旧 v2.4 草案：通用 Agent Skill Registry（已暂缓）

目标：让所有 Agent 都能按配置挂载 Skill，而不只 Polisher/Editor。

范围：

- Planner / Screenwriter / Author / Polisher / Editor / sidecar Agent 的统一 Skill 挂载点。
- `before_context` / `after_context` / `before_llm` / `after_llm` / `before_save` / `after_save` / `before_review` 等阶段枚举。
- Agent 权限矩阵。
- Skill 执行顺序、短路、重试和审计。

验收：

- 新增 Skill 不需要改 Agent 代码。
- Agent 不能执行未授权 Skill。
- 所有 Skill run 可追踪。
- 失败策略可配置且有测试覆盖。

## v2.5：配置化与平台化

目标：减少改代码成本，支持多平台风格。

范围：

- `agents.yaml` 增强。
- `llm.yaml` 增强。
- `quality_rules.yaml`。
- Agent 开关。
- 质量阈值配置。
- 平台风格配置。
- 平台级 Skill 配置。

验收：

- 改评分阈值无需改代码。
- 换模型无需改代码。
- 不同平台可使用不同章节字数、钩子密度和禁用规则。

## 版本推进规则

- 未通过当前版本验收，不进入下一版本。
- 新能力默认进入下一个版本，不随意塞进当前版本。
- 修改 `chapters.status` 枚举必须同步更新架构文档、v1 规格和测试。
- 新增 Agent 必须先定义权限矩阵、输入输出契约和失败处理。
