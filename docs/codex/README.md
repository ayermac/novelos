# Codex 架构文档索引

本目录用于维护小说内容生产工厂的架构、版本路线和阶段规格。为了方便多个 LLM Agent 协作开发，文档拆分为“总架构 + 版本路线 + 当前版本规格”三层。

## 文档列表

| 文档 | 用途 | 读者 |
| --- | --- | --- |
| `novel-content-factory-architecture.md` | 总体架构、Agent 边界、数据流、质量治理、扩展能力 | 架构规划、长期维护 |
| `novel-factory-roadmap.md` | v1 到 v3 的版本路线、每阶段目标和延后项 | 项目管理、迭代规划 |
| `novel-factory-v1-mvp-spec.md` | v1 当前开发规格、目录、接口、状态、验收标准 | 开发 Agent、代码实现 |
| `novel-factory-v1-review-fix-spec.md` | v1 通过后的 review 返工项、测试要求、禁止越界范围 | 开发 Agent、质量验收 |
| `novel-factory-v1.1-stability-spec.md` | v1.1 工程稳定性开发规范、幂等、追踪、超时、防覆盖要求 | 开发 Agent、质量验收 |
| `novel-factory-v1.2-quality-spec.md` | v1.2 质量与一致性增强规范、上下文、校验器、学习模式 | 开发 Agent、质量验收 |
| `novel-factory-v1.3-dispatcher-cli-spec.md` | v1.3 Dispatcher 编排与 CLI 可运行化规范、`novelos` 命令、运行恢复 | 开发 Agent、质量验收 |
| `novel-factory-v1.4-runtime-hardening-spec.md` | v1.4 运行时硬化、配置校验、demo seed、doctor、安装后 smoke run | 开发 Agent、质量验收 |
| `novel-factory-v2-multi-agent-spec.md` | v2 多 Agent 旁路扩展、Scout/Secretary/ContinuityChecker/Architect | 开发 Agent、质量验收 |
| `novel-factory-v2.1-qualityhub-skill-spec.md` | v2.1 QualityHub 与 Skill 插件化质量中枢、AI 去味、质量评分 | 开发 Agent、质量验收 |
| `novel-factory-v2.2-skill-manifest-spec.md` | v2.2 Skill Manifest 化、权限、schema、适用 Agent 和阶段 | 开发 Agent、质量验收 |
| `novel-factory-v2.3-skill-package-spec.md` | v2.3 Skill Package 化、handler、rules、prompts、fixtures、自测 CLI | 开发 Agent、质量验收 |
| `novel-factory-v3.0-batch-production-spec.md` | v3.0 多章节批次自动创作、批次状态、人工 review 闭环 | 开发 Agent、质量验收 |
| `novel-factory-v3.1-llm-routing-spec.md` | v3.1 LLM Profiles、项目 `.env`、默认模型与 Agent 级模型路由 | 架构规划、开发 Agent |
| `novel-factory-v3.2-batch-review-revision-spec.md` | v3.2 批次返修闭环、指定章节重跑、从某章起重跑、review notes 下发 | 开发 Agent、质量验收 |
| `novel-factory-v3.3-batch-continuity-gate-spec.md` | v3.3 批次级连续性审核门禁、approve 阻断、gate 状态查询 | 开发 Agent、质量验收 |
| `novel-factory-v3.4-production-queue-spec.md` | v3.4 本地 SQLite 生产队列、显式 queue-run、暂停、恢复、重试 | 开发 Agent、质量验收 |
| `novel-factory-v3.5-queue-runtime-hardening-spec.md` | v3.5 队列运行期硬化、事件查询、取消、恢复、doctor、limit run | 开发 Agent、质量验收 |
| `novel-factory-v3.6-semi-auto-serial-mode-spec.md` | v3.6 半自动连载计划、分轮 enqueue、人工确认后推进 | 开发 Agent、质量验收 |

## 使用方式

- 做架构判断时，优先读 `novel-content-factory-architecture.md`。
- 做版本排期时，优先读 `novel-factory-roadmap.md`。
- 写代码或 review v1 实现时，优先读 `novel-factory-v1-mvp-spec.md`。
- 修复 v1 review 问题时，优先读 `novel-factory-v1-review-fix-spec.md`。
- 开发 v1.1 稳定性能力时，优先读 `novel-factory-v1.1-stability-spec.md`。
- 开发 v1.2 质量增强能力时，优先读 `novel-factory-v1.2-quality-spec.md`。
- 开发 v1.3 可运行化能力时，优先读 `novel-factory-v1.3-dispatcher-cli-spec.md`。
- 开发 v1.4 运行时硬化能力时，优先读 `novel-factory-v1.4-runtime-hardening-spec.md`。
- 开发 v2 多 Agent 扩展能力时，优先读 `novel-factory-v2-multi-agent-spec.md`。
- 开发 v2.1 质量中枢和 Skill 插件能力时，优先读 `novel-factory-v2.1-qualityhub-skill-spec.md`。
- 开发 v2.2 Skill Manifest 能力时，优先读 `novel-factory-v2.2-skill-manifest-spec.md`。
- 开发 v2.3 Skill Package 能力时，优先读 `novel-factory-v2.3-skill-package-spec.md`。
- 开发 v3.0 批次生产能力时，优先读 `novel-factory-v3.0-batch-production-spec.md`。
- 规划或开发 v3.1 多 Agent 模型路由时，优先读 `novel-factory-v3.1-llm-routing-spec.md`。
- 开发 v3.2 批次返修闭环时，优先读 `novel-factory-v3.2-batch-review-revision-spec.md`。
- 开发 v3.3 批次连续性门禁时，优先读 `novel-factory-v3.3-batch-continuity-gate-spec.md`。
- 开发 v3.4 本地生产队列时，优先读 `novel-factory-v3.4-production-queue-spec.md`。
- 开发 v3.5 队列运行期硬化时，优先读 `novel-factory-v3.5-queue-runtime-hardening-spec.md`。
- 开发 v3.6 半自动连载计划时，优先读 `novel-factory-v3.6-semi-auto-serial-mode-spec.md`。

## 当前版本

当前开发基线是 **v3.6 Semi-Auto Serial Mode 已通过，等待下一阶段规划**。

v1 只实现：

- `Planner -> Screenwriter -> Author -> Polisher -> Editor`
- LangGraph 章节状态流转
- SQLite + Repository
- Pydantic 输出校验
- 单一 OpenAI-compatible LLM Provider
- 基础硬校验和测试闭环

v1 不实现：

- 多 Provider 原生适配
- Skill 热加载
- Web UI / Web API
- Scout / Architect / Secretary
- ContinuityChecker 独立 Agent
- SQLModel 全量 ORM 接管

当前下一步：

- 基于 v3.6 稳定节点，规划下一阶段能力。
- 下一阶段开始前，先由 Codex 输出版本规格与开发验收标准。
