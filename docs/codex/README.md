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
| `novel-factory-api-contract-guidelines.md` | API 设计规范：Resource API / Action API 边界、POST body-style、兼容迁移策略 | 开发 Agent、代码评审、API 验收 |

## v5.1.1 本地启动与验收

### 快速启动

**启动 API 后端**：
```bash
novelos api --host 127.0.0.1 --port 8765 --llm-mode stub
```

**启动前端开发服务器**：
```bash
cd frontend
npm install  # 首次需要安装依赖
npm run dev
```

访问 http://localhost:5173 即可使用。

### 端口说明

- **API 后端**: 默认 8765 端口
- **前端开发服务器**: 默认 5173 端口

### Smoke 验收脚本

运行完整验收测试：
```bash
./scripts/v51_smoke_acceptance.sh
```

该脚本会自动检查：
- Python 导入和 CLI 命令
- pytest 测试套件
- 前端类型检查和构建
- API 端点 smoke 测试
- .gitignore 规则

### 测试基线

- **当前测试基线**: 1627/1627 passed
- **新增测试**:
  - `test_v51_api_e2e_smoke.py`: 17 个端到端 smoke 测试
  - `test_v51_frontend_quality.py`: 8 个前端质量检查
  - `test_v51_api_security.py`: 9 个 API 安全测试
  - `test_v51_p2_fixes.py`: 扩展测试（包括 Style 优雅降级、Acceptance partial 状态）
  - `test_v516_frontend_closure.py`: 9 个前端收口测试（导航分组、空状态、Acceptance 路由移除）
  - `test_v516_langgraph_activation.py`: 12 个 LangGraph 激活测试（图编译、路由等价、published 短路、配置验证、安全）
  - `test_v530_trusted_generation_chain.py`: 29 个可信生成链路测试
  - `test_v531_project_workspace.py`: 项目级工作台测试
  - `test_v532_project_genesis.py`: 项目创世测试
  - `test_v532_memory_loop.py`: 记忆循环测试
  - `test_v532_fact_ledger.py`: 事实账本测试

### v5.1.1 WebUI 产品化改进

**状态映射**：
- completed → 已完成
- pending → 等待中
- running → 运行中
- failed → 失败
- partial → 迁移中
- pass → 通过
- error → 错误
- review → 待审核
- approved → 已通过
- rejected → 需返修
- blocking → 已阻塞
- fantasy → 奇幻
- urban → 都市
- sci-fi → 科幻
- xianxia → 仙侠

**页面改进**：
- Dashboard: 下一步建议卡片、快捷操作
- Projects: 中文类型标签、工作台入口
- ProjectDetail: NextAction 建议、章节进度统计
- Onboarding: Wizard 表单、成功结果面板
- Run: 项目信息展示、结构化结果面板
- Review: 统计概览、StatusBadge 中文
- Style: 优雅空状态、健康摘要
- Settings: 配置诊断、启动命令示例
- Acceptance: 卡片列表（防溢出）、partial 显示"迁移中"

### 验收覆盖项

**API 后端**:
- ✅ 统一响应格式 `{ok, error, data}`
- ✅ 中文错误消息
- ✅ 不暴露 traceback、绝对路径、API 密钥
- ✅ Stub 模式安全运行
- ✅ 所有端点返回 envelope
- ✅ Style console 对缺失表优雅降级
- ✅ Acceptance summary 包含 partial 计数

**前端**:
- ✅ 9 个页面组件（Acceptance 已移除）
- ✅ 中文导航、标题、状态
- ✅ StatusBadge 统一组件
- ✅ EmptyState 统一组件（支持 actions 多按钮）
- ✅ PageHeader 统一组件
- ✅ 错误和加载状态处理
- ✅ 空状态提示与下一步引导
- ✅ API 客户端正确处理 envelope
- ✅ TypeScript 类型检查通过
- ✅ 生产构建通过

**安全**:
- ✅ 不暴露 API 密钥
- ✅ 不暴露 traceback
- ✅ 不暴露绝对路径
- ✅ Config plan 不写文件
- ✅ Stub 模式不调用真实 LLM

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

当前开发基线是 **v5.3.x RC**，测试基线 **1627/1627 passed**。

**v5.3 已实现能力**（部分，进行中）：

- v5.3.0 可信生成链路：Context Readiness Gate、Planner 必经路由、字数硬质量门、真实模式人工发布闸门。
- v5.3.1 项目级作者工作台（部分）：项目模块导航、世界观/角色/势力/大纲/伏笔/章节指令 CRUD、项目上下文状态、章节重置/删除。
- v5.3.2 项目创世与记忆循环（部分）：创世生成/批准/拒绝、记忆更新批次、事实账本 CRUD 与事件。

**v5.3 未收口项**：

- 完整工作流可观测性（每步 Agent 输入/输出、Token、耗时、错误详情）。
- 连续性门禁与完整事实账本跨章强制执行。
- 章节工作流中的 Memory Curator 节点。
- v5.3 命令的完整 CLI 对齐。

**v5.2 核心变更:**
- LangGraph SqliteSaver checkpoint 持久化
- 世界观/角色/大纲 CRUD 完整链路
- 项目删除和章节删除/重置能力
- Agent 上下文注入世界观/角色/大纲
- 真实 LLM 端到端验证闭环
- Token 统计记录和健康度展示
- CLI 错误信封格式增强
- Migration 幂等检测
- Dispatcher 保留兼容路径（未删除）
- 全量测试 1425/1425、TypeScript、前端构建通过

**v5.3 规划方向:**
- Project Genesis：从一句创意生成项目圣经，用户批准后才进入 active。
- Project Memory Loop：章节生成后自动提出世界观、角色、大纲、势力、伏笔、章节指令和事实账本更新。
- Context Readiness Gate：项目骨架不完整时禁止章节生成。
- Planner 必经：无章节指令时先规划，再进入 Screenwriter。
- 真实质量门：字数、指令覆盖、上下文完整性、风格和连续性进入硬审核。
- 人工发布闸门：真实模式下 AI 审核通过后进入待人工确认，不自动发布。
- 项目级作者工作台：世界观/角色/大纲/伏笔/章节指令等独立模块管理。
- 工作流透明化：每个 Agent 的输入摘要、输出产物、校验结果、token、耗时、错误可查看。
- 事实账本与连续性门禁：跨章数值、道具、时间线、伤势、关系、伏笔状态必须可继承、可审计，冲突不能静默发布。

**v5.3.0 已验收能力:**
- Context Readiness Gate 已接入 API 与 SSE 生成链路。
- Planner 必经规则已生效：`planned + no instruction -> planner`。
- Author/Polisher/Editor 字数硬质量门已接入。
- 真实模式不自动发布，AI 审核通过后停在 `reviewed + awaiting_publish=true`。
- Manual Publish API 已接入：`POST /api/publish/chapter`。
- Checkpoint 文件跟随主 DB 路径，不再写 repo root。
- 全量测试 1471/1471、TypeScript、前端构建通过。

**v5.1.6 核心变更:**
- LangGraph StateGraph 替代 Dispatcher while 循环作为唯一编排器（API 层已切换）
- 新增 `run_with_graph()` 适配函数，返回值与 `Dispatcher.run_chapter()` 同构
- 新增 `create_node_runners()` 闭包注入 LLMRouter / Repository / skill_registry
- FactoryState 扩展 `steps` 字段
- 修复 `published` 状态死循环 bug（路由到 `archive` 终端节点 + 短路返回）
- Review/Style 空状态重构，消灭产品死胡同
- 导航分组：创作 / 工具 / 开发
- EmptyState 支持 `actions` 多按钮
- Acceptance 页面移除
- 配置验证端点 `POST /api/settings/validate`
- Settings 验证按钮 + real 模式成本提示
- LLMRouter 错误信息中文化
- API Key 不泄露审计通过

**v5.1.5 核心变更:**
- `/projects/:id` 重构为三栏作者项目工作台：章节导航、章节内容区、上下文侧栏。
- 日常生成入口回归项目工作台，`/run` 保留为高级运行入口。
- 工作流步骤抽取为共享组件，并为 stub 模式补充结构化 Agent 产物。
- Dashboard 重构为"创作中心"，主 CTA 导向项目工作台。
- Settings 新增"生成记录健康度"，避免把历史成功率误称为 LLM 连通性。
- Projects 页从表格改为卡片布局。
- 旧路由 `/projects/:id/chapters/:num` 与 `/runs/:runId` 保持兼容。
- 版本号统一更新至 v5.1.5。

**v5.1.4 核心变更:**
- 新增运行详情 API：`GET /api/runs/{run_id}` 返回工作流步骤时间线
- 新增 RunDetail 页面：路由 `/runs/:runId`，显示 5 个 Agent 步骤
- 演示模式说明强化：全局状态栏、Run 页面、ChapterReader 提示
- 生成交互优化：loading skeleton、步骤状态、结果卡片、下一步引导
- 章节阅读页交互优化：导航、正文样式、来源标签
- 配置体验优化：复制反馈、切换指引
- 修复 P1 问题：前端 API path 双 /api 问题
- 新增测试覆盖：防止双 /api 前缀问题
- 版本号统一更新至 v5.1.4

**v5.1.3 核心变更:**
- 新增章节详情 API：`GET /api/projects/{id}/chapters/{num}` 返回正文内容
- 新增 ChapterReader 页面：路由 `/projects/:id/chapters/:num`，阅读宽度排版
- ProjectDetail 章节表新增"操作"列：有正文→"查看正文"，无正文→"生成本章"
- Stub 内容按章节号区分：3 套故事模板 + 确定性动态生成，每章 ≥500 字
- NextAction 只检查最近一次运行（不再被历史失败误导）
- Run 结果页新增操作按钮：查看正文/生成下一章/重新运行
- Settings 页改为配置草案生成器，Provider 切换自动更新字段
- Review 空状态说明当前流程直接发布
- Acceptance 卡片默认隐藏 capability_id
- Onboarding 自动生成项目 ID（CJK 感知 slug）
- i18n 新增 `blocked: '已阻塞'` 映射
- 版本号统一更新至 v5.1.3

**v5.1.2 核心变更:**
- 统一章节状态模型：`chapter.status` vs `workflow_run.status` vs `queue.status` 明确区分
- 修复 onboarding 初始章节状态：`pending` → `planned`
- Dispatcher `STATUS_ROUTE` 兼容旧 `pending` 章节：`pending` → `screenwriter`
- 修复 `/api/run/chapter` 响应结构：新增 `workflow_status`、`chapter_status`、`requires_human`、`error`
- 修复 Run 页面章节选择：使用 workspace 获取 chapters，select 下拉选择可生成章节
- ProjectDetail recent_runs 增加 blocked 兜底说明
- 前端新增 `tWorkflowStatus()` / `tChapterStatus()` 避免状态混淆

**v5.1.1 核心变更:**
- 将 v5.1 React WebUI 从 API demo 升级为可用的中文作者工作台
- 统一状态映射：completed→已完成, review→待审核, etc.
- 新增可复用组件：StatusBadge, EmptyState, ErrorState, PageHeader
- API 优雅降级：Style console 对缺失表返回 ok=true + 空数据
- 增强页面：Dashboard 下一步建议、Settings 配置诊断、Acceptance 卡片列表
- 修复表格溢出：所有表格增加 overflowX: auto 容器
- 完整 TypeScript 类型检查 + 生产构建

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
- Scout / Architect / Secretary
- ContinuityChecker 独立 Agent
- SQLModel 全量 ORM 接管

当前下一步：

- v5.3.1 Project-Level Author Workspace：补项目创世、项目级世界观/角色/大纲/伏笔/章节指令管理入口，并继续收口 WebUI 主创作路径。
