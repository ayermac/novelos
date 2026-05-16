# v6.5.4 Agent Process Narrative 完成报告

## 状态

- 版本：v6.5.4
- 类型：前端交互体验增强
- 基线：v6.5.1 Interaction Primitives + v6.5.2 Project Overview + v6.5.3 Chapter Writing Surface
- 完成日期：2026-05-16

## 目标

把 Agent 执行过程从日志/节点状态，升级成用户能理解的创作过程叙事。

## 改动范围

### 1. 节点叙事映射（state-labels.ts）

新增 `WORKFLOW_NODE_NARRATIVE` 和 `tWorkflowNodeNarrative`：

| 节点 | 叙事文案 |
|------|----------|
| health_check | 正在检查运行环境... |
| task_discovery | 正在识别创作任务... |
| planner | 正在规划章节结构... |
| screenwriter | 正在编排场景与情节... |
| author | 正在撰写章节正文... |
| polisher | 正在润色文字表达... |
| editor | 正在审核内容质量... |
| memory_curator | 正在整理章节记忆... |
| publisher / publish | 正在发布章节... |
| awaiting_publish | 等待人工确认发布 |
| archive | 正在归档本章... |
| revision_router | 正在分析返修方向... |
| human_review | 等待人工审核 |

新增 `EVENT_NARRATIVE` 和 `tEventNarrative`，覆盖 node_started、context_loaded、llm_started/completed/failed、artifact_saved、fallback_used、diff_generated、evidence_verified、node_skipped、quality_diagnosed 等事件类型。

### 2. AuthorAgentPanel 叙事化

重构前：
- action-label 在运行中统一显示"正在生成..."
- action-desc 在运行中统一显示"AI 正在处理本章，请稍候。"
- 所有按钮使用原生 `<button>`
- 错误使用 `author-agent-error` CSS 类

重构后：
- action-label 根据 `currentNode` 显示节点专属叙事（如"正在撰写章节正文..."）
- action-desc 根据 `currentNode` 显示详细创作说明（如"AI 正在根据场景规划撰写章节正文。"）
- 定义 `getAgentActionDesc` 辅助函数，为每个节点提供专属描述
- 所有异步按钮替换为 `LoadingButton`
- 错误显示使用 `InlineMessage` 组件
- streaming SSE 步骤 running 时也显示叙事文案
- 启动阶段文案从"正在启动节点日志..."改为"正在启动创作流程..."

### 3. WorkflowTimeline 叙事化

重构前：
- running 且无日志的节点显示"节点运行中，正在等待模型或工具返回。"

重构后：
- running 且无日志的节点显示 `tWorkflowNodeNarrative(step.key)`（如"正在撰写章节正文..."）
- `eventLabel` 函数增强：在 EVENT_TYPE_LABELS 未命中时 fallback 到 `tEventNarrative`

### 4. AuthorWritingSurface WorkflowBody 叙事化

重构前：
- isStreaming 路径中 running 状态的 description = '处理中...'
- running 且无日志时的默认日志消息 = '节点运行中，正在等待模型或工具返回。'

重构后：
- isStreaming 路径中 running 状态的 description = `tWorkflowNodeNarrative(s.key)`
- running 且无日志时的默认日志消息 = `tWorkflowNodeNarrative(s.key)`

## 文件变更

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `frontend/src/lib/state-labels.ts` | 修改 | 新增 WORKFLOW_NODE_NARRATIVE、EVENT_NARRATIVE 映射及翻译函数 |
| `frontend/src/components/project/AuthorAgentPanel.tsx` | 修改 | 叙事文案 + LoadingButton + InlineMessage |
| `frontend/src/components/project/AuthorWritingSurface.tsx` | 修改 | WorkflowBody running 描述叙事化 |
| `frontend/src/components/WorkflowTimeline.tsx` | 修改 | running 空日志节点叙事 + eventLabel 增强 |
| `frontend/src/components/__tests__/WorkflowTimeline.test.tsx` | 修改 | 新增 2 个叙事测试 |
| `frontend/src/components/project/__tests__/AuthorWorkbench.test.tsx` | 修改 | 新增 3 个 Agent 面板叙事测试 |
| `docs/codex/planning/novel-factory-v6.5-interaction-excellence-spec.md` | 修改 | 更新 v6.5.4 为已实现 |
| `docs/codex/reports/novel-factory-v6.5.4-agent-process-narrative-report.md` | 新增 | 本报告 |
| `docs/codex/reviews/novel-factory-v6.5.4-agent-process-narrative-review.md` | 新增 | 评审文档 |

## 验证结果

| 检查项 | 结果 |
|--------|------|
| `npm run typecheck` | 通过 |
| `npm run lint` | 通过 |
| `npm run build` | 通过 |
| `npm run test -- --run` | 15 files, 187 tests passed |
| `python3 scripts/verify.py smoke` | 13 passed |

## 已知限制

- `AuthorAgentPanel` 中的"查看正文"和"查看运行详情"导航按钮保持原生 `<button>`，因为它们是即时导航操作，不需要 LoadingButton。
- timeline 路径（`timeline.nodes`）的节点描述来自后端 `n.messages[0]`，已经是人类可读消息，未做覆盖。
- 事件叙事映射 `EVENT_NARRATIVE` 目前主要作为 `EVENT_TYPE_LABELS` 的 fallback 使用，已有标签的 event type 保持原标签不变。