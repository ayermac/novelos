# Codex 架构文档索引

本目录用于维护小说内容生产工厂的架构、版本路线和阶段规格。为了方便多个 LLM Agent 协作开发，文档拆分为"总架构 + 版本路线 + 当前版本规格"三层。

## 文档列表

| 文档 | 用途 | 读者 |
| --- | --- | --- |
| `novel-content-factory-architecture.md` | 总体架构、Agent 边界、数据流、质量治理、扩展能力 | 架构规划、长期维护 |
| `novel-factory-roadmap.md` | v1 到 v4+ 的版本路线、每阶段目标和延后项 | 项目管理、迭代规划 |
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
| `novel-factory-v3.7-review-workbench-spec.md` | v3.7 人工 Review 工作台、审核包、时间线、版本差异、导出 | 开发 Agent、质量验收 |
| `novel-factory-v3.8-skill-import-bridge-spec.md` | v3.8 skills.sh / Agent Skill 本地导入桥、受控转换为 Skill Package | 开发 Agent、质量验收 |
| `novel-factory-v3.9-llm-model-catalog-spec.md` | v3.9 LLM 模型目录与 Agent 推荐、配置草案输出 | 架构规划、开发 Agent |
| `novel-factory-v4.0-style-bible-mvp-spec.md` | v4.0 Style Bible MVP、项目级风格配置、规则检查 | 开发 Agent、质量验收 |
| `novel-factory-v4.1-style-gate-evolution-spec.md` | v4.1 Style Gate、版本记录、人工确认的风格演进提案 | 开发 Agent、质量验收 |
| `novel-factory-v4.2-style-sample-analyzer-spec.md` | v4.2 本地风格样本分析、校准与 proposal 生成 | 开发 Agent、质量验收 |
| `novel-factory-v4.3-web-ui-acceptance-console-spec.md` | v4.3 Web UI 验收控制台 MVP、浏览器审核与管理入口 | 开发 Agent、质量验收 |
| `novel-factory-v4.4-web-review-ux-hardening-spec.md` | v4.4 Web Review UX 硬化、批次/队列/连载/风格审核体验 | 开发 Agent、质量验收 |
| `novel-factory-v4.5-personal-onboarding-spec.md` | v4.5 个人小说项目 Onboarding、从 Web 创建项目与初始资料 | 开发 Agent、质量验收 |
| `novel-factory-v4.6-first-run-guided-workflow-spec.md` | v4.6 首次运行引导闭环、项目创建后运行第一章并进入审核 | 开发 Agent、质量验收 |
| `novel-factory-v4.7-project-workspace-author-cockpit-spec.md` | v4.7 项目级作者工作台、聚合项目状态和下一步操作 | 开发 Agent、质量验收 |
| `novel-factory-v4.8-web-acceptance-matrix-spec.md` | v4.8 Web 验收矩阵、展示系统能力覆盖情况 | 开发 Agent、质量验收 |
| `novel-factory-v4.9-settings-llm-agent-ops-console-spec.md` | v4.9 Settings / LLM / Agent Ops Console、配置与运行状态控制台 | 开发 Agent、质量验收 |
| `novel-factory-v5.0-implemented-features-webui-acceptance-spec.md` | v5.0 已实现功能整体验收与 WebUI 验收 | 开发 Agent、质量验收 |
| `novel-factory-v5.0.1-webui-productization-chinese-ux-spec.md` | v5.0.1 WebUI 产品化与中文化 UX 规格 | 开发 Agent、质量验收 |
| `novel-factory-v5.1-frontend-separation-api-backend-spec.md` | v5.1 前后端分离、FastAPI JSON API、React 前端 | 开发 Agent、质量验收 |
| `novel-factory-v5.1.1-webui-product-reset-spec.md` | v5.1.1 WebUI 产品化 Reset、中文作者工作台 | 开发 Agent、质量验收 |
| `novel-factory-v5.1.2-chapter-status-model-alignment-spec.md` | v5.1.2 章节状态模型对齐、pending/planned 修复 | 开发 Agent、质量验收 |
| `novel-factory-v5.1.3-author-workflow-usability-closure-spec.md` | v5.1.3 作者主流程闭环、章节阅读、Stub 差异化 | 开发 Agent、质量验收 |
| `novel-factory-v5.1.4-workflow-visibility-interaction-polish-spec.md` | v5.1.4 工作流可视化、演示模式说明、交互优化 | 开发 Agent、质量验收 |
| `novel-factory-v5.1.5-author-workspace-productization-plan.md` | v5.1.5 作者工作台产品化、三栏项目工作台、创作中心 | 产品规划、开发 Agent、质量验收 |
| `novel-factory-v5.1.6-langgraph-activation-spec.md` | v5.1.6 LangGraph 编排激活 + 真实 LLM 首次生成 + 安全收口 | 产品规划、开发 Agent、质量验收 |
| `novel-factory-v5.2-product-completion-real-llm-closure-spec.md` | v5.2 产品能力补齐、真实 LLM 闭环、LangGraph 持久化 | 产品规划、开发 Agent、质量验收 |
| `novel-factory-v5.3-authoring-system-reset-plan.md` | v5.3 作者系统 Reset 规划：项目创世、可信生成链路、工作流透明化 | 产品规划、开发 Agent、质量验收 |
| `novel-factory-v5.3.1-project-level-author-workspace-spec.md` | v5.3.1 项目级作者工作台：项目资料模块、章节工作区、主路径收口 | 开发 Agent、质量验收 |
| `novel-factory-v5.3.2-project-genesis-memory-loop-spec.md` | v5.3.2 项目创世与创作记忆循环：自动生成项目骨架、章节后自动维护资料与事实 | 开发 Agent、质量验收 |
| `novel-factory-v5.4.13-project-specific-skill-overrides-spec.md` | v5.4.13 项目级 Skill 覆盖层、挂载方案、参数默认值 | 开发 Agent、质量验收 |
| `novel-factory-v5.5.0-run-recovery-console-spec.md` | v5.5.0 运行恢复控制台、阻塞/返修恢复、checkpoint 清理 | 开发 Agent、质量验收 |
| `novel-factory-v5.5.1-stuck-run-detection-spec.md` | v5.5.1 卡住运行检测、标记阻塞、run 级恢复 audit | 开发 Agent、质量验收 |
| `novel-factory-v5.5.2-run-health-dashboard-spec.md` | v5.5.2 运行健康面板、异常运行总览、批量标记阻塞 | 开发 Agent、质量验收 |
| `novel-factory-v5.5.3-autonomous-production-loop-spec.md` | v5.5.3 自主生产循环、下一步动作 API、AI 自动补齐、Arc 规划、创世重新定位 | 开发 Agent、质量验收 |
| `novel-factory-v5.5.4-real-llm-autonomous-planning-spec.md` | v5.5.4 真实 LLM 自主规划、配置错误显式化、只补缺失项、Arc range 幂等 | 开发 Agent、质量验收 |
| `novel-factory-v5.5.5-autonomous-production-runner-spec.md` | v5.5.5 自主生产运行器、自动执行生产步骤、步数限制、dry-run、安全防护 | 开发 Agent、质量验收 |
| `novel-factory-v5.5.6-production-command-center-ui-refresh-spec.md` | v5.5.6 生产指挥台 UI 刷新、合并主面板、中文映射、步骤时间线、错误详情 | 开发 Agent、质量验收 |
| `novel-factory-v5.5.7-realtime-production-monitor-spec.md` | v5.5.7 实时监控/streaming UI、SSE endpoint、EventSource 实时追加、停止监听 | 开发 Agent、质量验收 |
| `novel-factory-v5.5.8-auto-run-control-loop-spec.md` | v5.5.8 自动生产控制循环、session 持久化、pause/resume/cancel/retry、协作式控制 | 开发 Agent、质量验收 |
| `novel-factory-v5.5.9-auto-run-resilience-spec.md` | v5.5.9 自动生产恢复闭环、刷新恢复、SSE 断线重连、session health、失败步精准重试 | 开发 Agent、质量验收 |
| `novel-factory-v5.5.10-bounded-autonomy-guardrails-spec.md` | v5.5.10 有界自动生产护栏、token/步数/时长预算、无进展停机、人工闸门 | 产品规划、开发 Agent |
| `novel-factory-v5.5.11-author-centric-workspace-reset-spec.md` | v5.5.11 作者中心工作台重置、项目导航重组、今日生产、阻塞复盘、工作流启动可见性 | 产品规划、开发 Agent |
| `novel-factory-v5.5.12-llm-runtime-reliability-cost-guardrails-spec.md` | v5.5.12 LLM 运行可靠性与成本护栏、指数退避、token 预算、旧运行作废 | 产品规划、开发 Agent |
| `novel-factory-api-contract-guidelines.md` | API 设计规范：Resource API / Action API 边界、POST body-style、兼容迁移策略 | 开发 Agent、代码评审、API 验收 |

## 本地启动与验收

### 快速启动

日常开发建议使用仓库内服务脚本：

```bash
scripts/novelos-service.sh start      # 启动 API + WebUI
scripts/novelos-service.sh stop       # 停止 API + WebUI
scripts/novelos-service.sh restart    # 重启 API + WebUI
scripts/novelos-service.sh status     # 查看服务状态
scripts/novelos-service.sh logs       # 查看最近日志
```

默认使用 `acceptance_novel_factory.db`、`config/local.yaml`、`LLM_MODE=real`、API 端口 `8765` 和 WebUI 端口 `5173`。

也可以手动启动 API 与前端：

```bash
novelos api --host 127.0.0.1 --port 8765 --db-path acceptance_novel_factory.db --llm-mode stub
```

```bash
cd frontend
npm run dev
```

访问 http://localhost:5173 即可使用。

### 测试基线

- **当前测试基线**: 1828/1828 passed
- **v5.5.9 专项**: 12 passed
- **v5.5.10 专项**: 8 passed
- **v5.5.11 专项**: 15 passed
- **v5.5.12 专项**: 4 passed
- **前端**: typecheck / lint / production build / vitest passed

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
- 开发 v3.7 人工 Review 工作台时，优先读 `novel-factory-v3.7-review-workbench-spec.md`。
- 开发 v3.8 Skill 导入桥时，优先读 `novel-factory-v3.8-skill-import-bridge-spec.md`。
- 规划或开发 v3.9 LLM 模型目录与 Agent 推荐时，优先读 `novel-factory-v3.9-llm-model-catalog-spec.md`。
- 开发 v4.0 Style Bible MVP 时，优先读 `novel-factory-v4.0-style-bible-mvp-spec.md`。
- 开发 v4.1 Style Gate 与风格演进时，优先读 `novel-factory-v4.1-style-gate-evolution-spec.md`。
- 开发 v4.2 风格样本分析与校准时，优先读 `novel-factory-v4.2-style-sample-analyzer-spec.md`。
- 开发 v4.3 Web UI 验收控制台时，优先读 `novel-factory-v4.3-web-ui-acceptance-console-spec.md`。
- 开发 v4.4 Web Review UX 硬化时，优先读 `novel-factory-v4.4-web-review-ux-hardening-spec.md`。
- 开发 v4.5 个人小说项目 Onboarding 时，优先读 `novel-factory-v4.5-personal-onboarding-spec.md`。
- 开发 v4.6 首次运行引导闭环时，优先读 `novel-factory-v4.6-first-run-guided-workflow-spec.md`。
- 开发 v4.7 项目级作者工作台时，优先读 `novel-factory-v4.7-project-workspace-author-cockpit-spec.md`。
- 开发/验收 v4.8 Web Acceptance Matrix 时，优先读 `novel-factory-v4.8-web-acceptance-matrix-spec.md`。
- 开发/验收 v4.9 Settings / LLM / Agent Ops Console 时，优先读 `novel-factory-v4.9-settings-llm-agent-ops-console-spec.md`。
- 验收 v5.0 已实现功能与 WebUI 时，优先读 `novel-factory-v5.0-implemented-features-webui-acceptance-spec.md`。

## 当前版本

当前开发基线是 **v5.5.12 LLM Runtime Reliability & Cost Guardrails**，测试基线 **1828/1828 passed**（含 v5.5.9 专项 12 passed、v5.5.10 专项 8 passed、v5.5.11 专项 15 passed、v5.5.12 专项 4 passed）。

**近期已实现能力**：

- v5.3.0 可信生成链路：Context Readiness Gate、Planner 必经路由、字数硬质量门、真实模式人工发布闸门。
- v5.3.1 项目级作者工作台（部分）：项目模块导航、世界观/角色/势力/大纲/伏笔/章节指令 CRUD、项目上下文状态、章节重置/删除。
- v5.3.2 项目创世与记忆循环（部分）：创世生成/批准/拒绝、记忆更新批次、事实账本 CRUD 与事件。
- v5.3.3-v5.3.4 Skill 可视化与测试台：Skill 列表、挂载关系、配置验证、fixtures 测试、手动试运行。
- v5.3.5 记忆可靠性：结构化字段应用、失败原因可见、失败项重试、批次状态重算。
- v5.4.0-v5.4.13 WebUI 重构：ProjectShell 分组导航、章节工作区拆分、Settings Console 拆分、Attention Panel、Agent Skill Matrix、视觉 QA polish、Agent Skill Configuration Console、文件夹导入桥、启用状态管理与安全审查、挂载引导、项目级 Skill 覆盖层。
- v5.5.0 运行恢复控制台：Run Detail 恢复状态、retry/checkpoint 可见、安全 reset、run 级 audit。
- v5.5.1 卡住运行检测：running 超时识别、run-scoped running task 可见、标记阻塞、system recovery audit。
- v5.5.2 运行健康面板：全局异常运行总览、项目过滤、批量 mark-stuck、部分失败可见。
- v5.5.3 自主生产循环：项目工作台「下一步生产动作」、AI 自动补齐缺失资料、章节批次规划 Arc Plan、创世重新定位。
- v5.5.4 真实 LLM 自主规划：real-mode 配置错误显式化、auto-fill 只补缺失类型、arc-plan 章节范围幂等保护。
- v5.5.5 自主生产运行器：自动执行生产步骤、步数限制、dry-run 预览、安全防护。
- v5.5.6 生产指挥台 UI 刷新：合并主面板、中文状态映射、步骤时间线、错误详情。
- v5.5.7 实时监控/streaming UI：SSE endpoint、EventSource 实时追加、停止监听。
- v5.5.8 自动生产控制循环：session 持久化、pause/resume/cancel/retry、协作式控制。
- v5.5.9 自动生产恢复闭环：刷新恢复、SSE 断线重连、session health、失败步精准重试。
- v5.5.10 有界自动生产护栏：入口收敛、预算可见、空转检测、重复失败检测、session 清理。
- v5.5.11 作者中心工作台重置：项目导航重组（作者任务/小说设定/系统状态分组）、今日生产面板、阻塞复盘卡、工作流启动可见性、记忆收件箱合并视图、前端测试基线。
- v5.5.12 LLM 运行可靠性与成本护栏：LLM 限流/超时指数退避、单章/项目/自动生产 token 预算、超预算显式停机、章节重置时作废旧 running workflow run。

历史版本的详细规格请从上方文档列表进入对应版本文档，不再在本索引中重复维护长篇 changelog。
