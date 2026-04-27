# Codex 架构文档索引

本目录用于维护小说内容生产工厂的架构、版本路线和阶段规格。为了方便多个 LLM Agent 协作开发，文档拆分为“总架构 + 版本路线 + 当前版本规格”三层。

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

- **当前测试基线**: 1293/1293 passed
- **新增测试**:
  - `test_v51_api_e2e_smoke.py`: 17 个端到端 smoke 测试
  - `test_v51_frontend_quality.py`: 8 个前端质量检查
  - `test_v51_api_security.py`: 9 个 API 安全测试
  - `test_v51_p2_fixes.py`: 扩展测试（包括 Style 优雅降级、Acceptance partial 状态）

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
- ✅ 10 个页面组件
- ✅ 中文导航、标题、状态
- ✅ StatusBadge 统一组件
- ✅ EmptyState/ErrorState 统一组件
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

当前开发基线是 **v5.1.4 Workflow Visibility & Interaction Polish 已通过验收，测试基线 1311/1311**。

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

- 进入 v5.1.5 Real LLM Configuration & First Real Generation 规划与开发。
