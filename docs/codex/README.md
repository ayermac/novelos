# Codex 文档入口

本目录维护 Novelos 的规划、审查、验收和下一阶段方向文档。根目录只保留本入口页；具体文档按语义分目录，避免把历史规格、完成报告和未来草案混在一起。

## 目录约定

| 目录 | 内容 | 使用场景 |
| --- | --- | --- |
| `planning/` | 架构、路线图、历史版本规格、API 规范 | 做版本排期、开发实现、追溯历史决策 |
| `reports/` | 完成报告、真实项目验收、阶段总结 | 判断某个版本是否闭环、查看验收事实 |
| `reviews/` | Review 检查项、发现的问题、修复验证 | 代码/产品审查与回归验证 |
| `next/` | 下一阶段方向、候选路线、未锁定规划 | 讨论未来方向，不作为当前执行规格 |

## 当前进度

- **生产稳定基线**: v5.5.15 Production Readiness Closure
- **当前 WebUI 基线**: v5.6.1 Workbench Stabilization
- **当前创作者闭环基线**: v5.7 Daily Writing Editing and Versioning
- **当前 Agent 可审计基线**: v6.1 Agent Work Process Streaming & Auditable Execution Evidence
- **当前桌面客户端基线**: v6.2.5 Desktop Release Readiness Checklist
- **当前创作者闭环基线**: v6.3.2 Creator Onboarding Closure
- **当前章节质量基线**: v6.4.6 Chapter Generation Quality Closure
- **当前交互体验基线**: v6.5.7 Visual Polish Pass
- **当前创世质量基线**: v6.6.4 Genesis Initialization Depth & Specificity Closure
- **当前运行时卫生基线**: v6.6.5 Runtime Hygiene & Observability Closure
- **当前工作流恢复基线**: v6.6.6 Workflow Recovery & State Integrity Closure
- **当前记忆可靠性基线**: v6.6.7 Memory Curator Reliability Closure
- **当前审核语义基线**: v6.6.8 Editor Refactor & Review Semantics Closure
- **当前迁移完整性基线**: v6.6.9 Database Migration & Persistence Integrity Closure
- **当前 API 契约基线**: v6.6.10 API Contract & Frontend State Semantics Closure
- **当前下一步**: v6.6+ Agent Evidence UX / Structured Memory Canonicalization
- **状态**: v6.6.4 已完成 Genesis Initialization Depth & Specificity Closure。核心交付：Genesis Prompt 深度要求、Draft Normalization 扩展、Quality Gate 加强（SHALLOW_INSTRUCTION/ABSTRACT_OBJECTIVE/OUTLINE_TOO_ABSTRACT 等 blocker）、前端质量报告按 section 分组、API 语义保持并补充 _meta 审计保留。
- **v6.4 规格**: [planning/novel-factory-v6.4-chapter-quality-closure-spec.md](planning/novel-factory-v6.4-chapter-quality-closure-spec.md) — 解决生成章节"AI 味重"问题，聚焦 prompt 增强、deterministic validator 补充和 skill 升级。
- **v6.5 规格**: [planning/novel-factory-v6.5-interaction-excellence-spec.md](planning/novel-factory-v6.5-interaction-excellence-spec.md) — 解决桌面客户端"后台感"问题，先建立 toast/loading/skeleton 等交互基础设施，再逐页升级工作台体验。
- **测试基线**: backend full suite **2471 passed, 0 failed**；v6.5.7 frontend vitest **198 passed**；`scripts/verify.py smoke` 28 passed；frontend typecheck/lint/build passed；desktop build passed
- **v5.5.15 完成报告**: [reports/novel-factory-v5.5.15-completion-report.md](reports/novel-factory-v5.5.15-completion-report.md)
- **v5.5.15 Review 记录**: [reviews/novel-factory-v5.5.15-review.md](reviews/novel-factory-v5.5.15-review.md)
- **v5.6 完成报告**: [reports/novel-factory-v5.6-author-workbench-completion-report.md](reports/novel-factory-v5.6-author-workbench-completion-report.md)
- **v5.6 Review 记录**: [reviews/novel-factory-v5.6-author-workbench-review.md](reviews/novel-factory-v5.6-author-workbench-review.md)
- **v5.6.1 完成报告**: [reports/novel-factory-v5.6.1-workbench-stabilization-completion-report.md](reports/novel-factory-v5.6.1-workbench-stabilization-completion-report.md)
- **v5.6.1 Review 记录**: [reviews/novel-factory-v5.6.1-workbench-stabilization-review.md](reviews/novel-factory-v5.6.1-workbench-stabilization-review.md)
- **v5.7 完成报告**: [reports/novel-factory-v5.7-completion-report.md](reports/novel-factory-v5.7-completion-report.md)
- **v5.7 Review 记录**: [reviews/novel-factory-v5.7-review.md](reviews/novel-factory-v5.7-review.md)
- **v5.7.1 完成报告**: [reports/novel-factory-v5.7.1-completion-report.md](reports/novel-factory-v5.7.1-completion-report.md)
- **v5.7.1 真实项目验收**: [reports/novel-factory-v5.7.1-real-project-acceptance.md](reports/novel-factory-v5.7.1-real-project-acceptance.md)
- **v5.7.1 Review 记录**: [reviews/novel-factory-v5.7.1-review.md](reviews/novel-factory-v5.7.1-review.md)
- **v5.8 完成报告**: [reports/novel-factory-v5.8-completion-report.md](reports/novel-factory-v5.8-completion-report.md)
- **v5.8 Review 记录**: [reviews/novel-factory-v5.8-review.md](reviews/novel-factory-v5.8-review.md)
- **v5.8.1 真实 LLM 验收**: [reports/novel-factory-v5.8.1-real-llm-acceptance-report.md](reports/novel-factory-v5.8.1-real-llm-acceptance-report.md)
- **v5.9.2 完成报告**: [reports/novel-factory-v5.9.2-completion-report.md](reports/novel-factory-v5.9.2-completion-report.md)
- **v5.9.2 Review 记录**: [reviews/novel-factory-v5.9.2-review.md](reviews/novel-factory-v5.9.2-review.md)
- **v5.9.3 Agent Skill Expansion 规格**: [planning/novel-factory-v5.9.3-agent-skill-expansion-spec.md](planning/novel-factory-v5.9.3-agent-skill-expansion-spec.md)
- **v5.9.3 完成报告**: [reports/novel-factory-v5.9.3-completion-report.md](reports/novel-factory-v5.9.3-completion-report.md)
- **v5.9.3 Review 记录**: [reviews/novel-factory-v5.9.3-review.md](reviews/novel-factory-v5.9.3-review.md)
- **v6.0 Agent Role Capability System 规格**: [planning/novel-factory-v6.0-agent-role-capability-system-spec.md](planning/novel-factory-v6.0-agent-role-capability-system-spec.md)
- **v6.0 完成报告**: [reports/novel-factory-v6.0-completion-report.md](reports/novel-factory-v6.0-completion-report.md)
- **v6.0 Review 记录**: [reviews/novel-factory-v6.0-review.md](reviews/novel-factory-v6.0-review.md)
- **v6.0 真实 LLM 验收**: [reports/novel-factory-v6.0-real-llm-acceptance-report.md](reports/novel-factory-v6.0-real-llm-acceptance-report.md)
- **v6.1 Agent Work Process Streaming 规格**: [planning/novel-factory-v6.1-agent-work-process-streaming-spec.md](planning/novel-factory-v6.1-agent-work-process-streaming-spec.md)
- **v6.1 完成报告**: [reports/novel-factory-v6.1-completion-report.md](reports/novel-factory-v6.1-completion-report.md)
- **v6.1 Review 记录**: [reviews/novel-factory-v6.1-review.md](reviews/novel-factory-v6.1-review.md)
- **桌面客户端规划**: [planning/novel-factory-cross-platform-desktop-client-plan.md](planning/novel-factory-cross-platform-desktop-client-plan.md)
- **v6.2 Desktop Client 完成报告**: [reports/novel-factory-v6.2-desktop-client-completion-report.md](reports/novel-factory-v6.2-desktop-client-completion-report.md)
- **v6.2 Desktop Client Review 记录**: [reviews/novel-factory-v6.2-desktop-client-review.md](reviews/novel-factory-v6.2-desktop-client-review.md)
- **v6.4 Chapter Quality 完成报告**: [reports/novel-factory-v6.4.6-chapter-quality-closure-report.md](reports/novel-factory-v6.4.6-chapter-quality-closure-report.md)
- **v6.4 Chapter Quality Review 记录**: [reviews/novel-factory-v6.4.6-chapter-quality-closure-review.md](reviews/novel-factory-v6.4.6-chapter-quality-closure-review.md)
- **v6.5.1 Interaction Primitives 完成报告**: [reports/novel-factory-v6.5.1-interaction-primitives-report.md](reports/novel-factory-v6.5.1-interaction-primitives-report.md)
- **v6.5.1 Interaction Primitives Review 记录**: [reviews/novel-factory-v6.5.1-interaction-primitives-review.md](reviews/novel-factory-v6.5.1-interaction-primitives-review.md)
- **v6.5.6 Interaction Excellence 完成报告**: [reports/novel-factory-v6.5.6-interaction-excellence-closure-report.md](reports/novel-factory-v6.5.6-interaction-excellence-closure-report.md)
- **v6.5.6 Interaction Excellence Review 记录**: [reviews/novel-factory-v6.5.6-interaction-excellence-closure-review.md](reviews/novel-factory-v6.5.6-interaction-excellence-closure-review.md)
- **v6.5.7 Visual Polish Pass 完成报告**: [reports/novel-factory-v6.5.7-visual-polish-pass-report.md](reports/novel-factory-v6.5.7-visual-polish-pass-report.md)
- **v6.5.7 Visual Polish Pass Review 记录**: [reviews/novel-factory-v6.5.7-visual-polish-pass-review.md](reviews/novel-factory-v6.5.7-visual-polish-pass-review.md)
- **v6.6.4 Genesis Depth & Specificity 规格**: [planning/novel-factory-v6.6.4-genesis-depth-specificity-closure-spec.md](planning/novel-factory-v6.6.4-genesis-depth-specificity-closure-spec.md)
- **v6.6.4 完成报告**: [reports/novel-factory-v6.6.4-completion-report.md](reports/novel-factory-v6.6.4-completion-report.md)
- **v6.6.4 Review 记录**: [reviews/novel-factory-v6.6.4-review.md](reviews/novel-factory-v6.6.4-review.md)
- **v6.6.5 Runtime Hygiene & Observability 规格**: [planning/novel-factory-v6.6.5-runtime-hygiene-observability-closure-spec.md](planning/novel-factory-v6.6.5-runtime-hygiene-observability-closure-spec.md)
- **v6.6.5 完成报告**: [reports/novel-factory-v6.6.5-completion-report.md](reports/novel-factory-v6.6.5-completion-report.md)
- **v6.6.5 Review 记录**: [reviews/novel-factory-v6.6.5-review.md](reviews/novel-factory-v6.6.5-review.md)

## 当前执行规则

1. 当前执行真相源仍以 `planning/` 中被明确选定的版本规格为准。
2. `reports/` 和 `reviews/` 记录已经发生的事实，不再承载未来需求。
3. `next/` 只用于方向收口和候选路线，不应被开发 Agent 当作已锁定规格。
4. 历史规格不做大规模改写；如需改变方向，应新增下一阶段文档或新版本规格。
5. 旧 `novel_factory/web` Jinja/静态页面路线已退役。当前 UI 只走 `frontend/` 的 React/Vite，后端只提供 FastAPI API；历史文档中出现的 `web/templates`、`web/static` 或 `web/design` 仅作为旧版本记录，不应作为新开发入口。
6. Agent 角色实现只放在 `novel_factory/agents/`；共享运行底座放在 `novel_factory/agent_runtime/`。`scout`、`architect`、`secretary` 旧旁路 Agent 已退役，后续如确需恢复应重新按当前 Agent Runtime 规范规划。

## 关键文档

- 总体架构: [planning/novel-content-factory-architecture.md](planning/novel-content-factory-architecture.md)
- 版本路线: [planning/novel-factory-roadmap.md](planning/novel-factory-roadmap.md)
- API 规范: [planning/novel-factory-api-contract-guidelines.md](planning/novel-factory-api-contract-guidelines.md)
- v5.5.15 规格: [planning/novel-factory-v5.5.15-production-readiness-closure-spec.md](planning/novel-factory-v5.5.15-production-readiness-closure-spec.md)
- v5.6 WebUI 重构规格: [planning/novel-factory-v5.6-webui-author-workbench-rework-spec.md](planning/novel-factory-v5.6-webui-author-workbench-rework-spec.md)
- v5.6.1 工作台稳定化规格: [planning/novel-factory-v5.6.1-workbench-stabilization-spec.md](planning/novel-factory-v5.6.1-workbench-stabilization-spec.md)
- v5.7 日常写作编辑与版本管理规格: [planning/novel-factory-v5.7-daily-writing-editing-versioning-spec.md](planning/novel-factory-v5.7-daily-writing-editing-versioning-spec.md)
- v5.7.1 内部构建完整与稳定规格: [planning/novel-factory-v5.7.1-internal-hardening-spec.md](planning/novel-factory-v5.7.1-internal-hardening-spec.md)
- v5.8 工作流可观测与恢复增强规格: [planning/novel-factory-v5.8-workflow-observability-recovery-spec.md](planning/novel-factory-v5.8-workflow-observability-recovery-spec.md)
- v5.9.2 UI 控件统一规格: [planning/novel-factory-v5.9.2-ui-controls-standardization-spec.md](planning/novel-factory-v5.9.2-ui-controls-standardization-spec.md)
- v5.9.3 Agent Skill Expansion 规格: [planning/novel-factory-v5.9.3-agent-skill-expansion-spec.md](planning/novel-factory-v5.9.3-agent-skill-expansion-spec.md)
- v6.0 Agent Role Capability System 规格: [planning/novel-factory-v6.0-agent-role-capability-system-spec.md](planning/novel-factory-v6.0-agent-role-capability-system-spec.md)
- 桌面客户端规划: [planning/novel-factory-cross-platform-desktop-client-plan.md](planning/novel-factory-cross-platform-desktop-client-plan.md)
- v5.6 完成报告: [reports/novel-factory-v5.6-author-workbench-completion-report.md](reports/novel-factory-v5.6-author-workbench-completion-report.md)
- v5.6 Review: [reviews/novel-factory-v5.6-author-workbench-review.md](reviews/novel-factory-v5.6-author-workbench-review.md)
- 下一阶段方向: [next/personal-author-workbench-direction.md](next/personal-author-workbench-direction.md)

## 下一阶段方向

v5.5.15 和 v5.6 Phase 1 完成后，下一阶段不优先展开多租户、企业权限或复杂商业化后台。项目方向先收敛为：

```text
个人创作者的 AI Agent 长篇内容生产工作台
```

近期优先级：

1. v6.2.5 桌面发布准备：release checklist、version policy、release manifest、安装/升级/卸载说明。
2. v6.3 从 0 到 1 创作体验闭环：创建小说后进入创世设定、世界观、角色、大纲、章节规划，而不是直接跳章节。
3. v6.5 Interaction Excellence：先把客户端操作反馈、等待状态、错误恢复、页面节奏做到顺滑。
4. v6.6+ Agent 执行证据 UX / 结构化记忆与事实证据链：把 Agent 输入、输出、工具调用、Skill、Memory、diff、审核依据做成用户能看懂的过程直播，并把角色、世界观、伏笔、时间线做准；向量/RAG 后续只用于风格和参考作品检索。

详细方向见 [next/personal-author-workbench-direction.md](next/personal-author-workbench-direction.md)。

## 本地启动与验收

日常开发建议使用仓库内服务脚本：

```bash
scripts/novelos-service.sh start
scripts/novelos-service.sh stop
scripts/novelos-service.sh restart
scripts/novelos-service.sh status
scripts/novelos-service.sh logs
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

### 分层验证策略

全量测试（1892+ pytest / 130+ vitest）应作为稳定基线声明或提交前闸门，不应作为每次小改动后的默认验证方式。推荐使用分层验证入口：

```bash
python3 scripts/verify.py smoke     # 快速后端关键回归（日常小改动后）
python3 scripts/verify.py v57       # v5.7 编辑/版本相关测试（编辑器改动后）
python3 scripts/verify.py frontend  # 前端 typecheck + lint + vitest（前端改动后）
python3 scripts/verify.py full      # 全量后端 + 前端（稳定基线声明或提交前）
python3 scripts/verify.py durations # 查看 pytest 最慢用例耗时
```

| 场景 | 推荐命令 | 说明 |
|------|----------|------|
| 后端小改动后 | `smoke` | 跑关键回归测试，秒级反馈 |
| 编辑器/版本相关改动后 | `v57` | 跑 v5.7 后端测试 + 前端 ChapterEditorSurface 测试 |
| 前端改动后 | `frontend` | typecheck + lint + vitest，不跑后端 |
| 准备提交或声明稳定基线 | `full` | pytest 全量 + 前端 typecheck + lint + build + vitest |
| 排查测试耗时 | `durations` | 查看最慢的 30 个 pytest 用例 |
