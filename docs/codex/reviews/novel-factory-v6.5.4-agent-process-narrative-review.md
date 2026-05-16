# v6.5.4 Agent Process Narrative 评审

## 评审日期

2026-05-16

## 评审范围

- `frontend/src/lib/state-labels.ts`
- `frontend/src/components/project/AuthorAgentPanel.tsx`
- `frontend/src/components/project/AuthorWritingSurface.tsx`
- `frontend/src/components/WorkflowTimeline.tsx`
- `frontend/src/components/__tests__/WorkflowTimeline.test.tsx`
- `frontend/src/components/project/__tests__/AuthorWorkbench.test.tsx`

## 检查清单

### 功能正确性

- [x] `tWorkflowNodeNarrative` 覆盖所有主要节点（planner/screenwriter/author/polisher/editor/memory_curator/publisher/health_check/task_discovery）
- [x] `tEventNarrative` 覆盖 v6.1 execution_events.py 中定义的主要事件类型
- [x] AuthorAgentPanel action-label 根据 currentNode 显示不同叙事
- [x] AuthorAgentPanel action-desc 根据 currentNode 显示详细创作说明
- [x] AuthorAgentPanel streaming 步骤 running 时显示叙事文案
- [x] WorkflowTimeline running 且无日志时显示节点专属叙事
- [x] AuthorWritingSurface WorkflowBody isStreaming 路径 running 描述使用叙事映射
- [x] AuthorAgentPanel 发布/生成/恢复按钮使用 LoadingButton
- [x] AuthorAgentPanel 错误显示使用 InlineMessage

### 向后兼容

- [x] `tWorkflowNodeLabel` 未变更，所有现有调用不受影响
- [x] `WorkflowTimeline` props 接口未变更
- [x] `AuthorAgentPanel` props 接口未变更
- [x] `AuthorWritingSurface` props 接口未变更
- [x] 现有测试全部通过（184 个原测试）

### 代码质量

- [x] 未引入新的 TypeScript 类型错误
- [x] 未引入新的 ESLint 警告（已清理未使用的 Loader2/AlertCircle/showToast）
- [x] 叙事映射集中在 state-labels.ts，避免散落在组件中
- [x] `getAgentActionDesc` 作为局部辅助函数，不污染全局命名空间

### 可访问性

- [x] LoadingButton 自动处理 `aria-busy` 和 `disabled`
- [x] InlineMessage 使用语义化颜色（success/danger）
- [x] 叙事文案使用中文，符合产品语言

### 测试覆盖

| 测试用例 | 状态 |
|----------|------|
| WorkflowTimeline running 节点显示叙事文案（author → 正在撰写章节正文...） | 新增，通过 |
| WorkflowTimeline fallback_used 事件显示人类可读标签 | 新增，通过 |
| AuthorWorkbench AuthorAgentPanel author 节点运行显示叙事 | 新增，通过 |
| AuthorWorkbench AuthorAgentPanel planner 节点运行显示叙事 | 新增，通过 |
| AuthorWorkbench AuthorAgentPanel streaming polisher 显示叙事 | 新增，通过 |
| 原 182 个测试 | 全部通过 |

## 发现的问题

### 已处理

1. **测试中 started_at 时间过早导致 stale 判定**
   - AuthorAgentPanel 叙事测试中使用 `started_at: '2026-05-13T10:00:00'`，距离当前时间超过 30 分钟，触发 `isStaleRunning`，导致 action-label 显示"运行疑似卡住"而非叙事文案。
   - 已改为 `new Date().toISOString()`，避免 stale 判定。

2. **未使用的导入导致 typecheck 失败**
   - `Loader2`、`AlertCircle`、`showToast` 引入后未使用。
   - 已清理。

3. **WorkflowTimeline fallback 测试期望不匹配**
   - `eventLabel` 函数中 `EVENT_TYPE_LABELS['fallback_used']` 已存在（'降级兜底'），所以不会走到 `tEventNarrative`。
   - 测试断言已修正为 '降级兜底'。

### 未处理（建议后续跟进）

1. **timeline 路径描述未叙事化**
   - `timeline.nodes` 的 description 来自后端 `n.messages[0]`，后端消息已经是人类可读的（如"已生成章节场景规划"），所以前端未覆盖。如需更统一的叙事风格，可后续在后端增强。

2. **AuthorAgentPanel 导航按钮未 LoadingButton 化**
   - "查看正文"和"查看运行详情"是即时导航，无异步操作，保持原生 `<button>` 合理。

## 结论

**通过评审。** v6.5.4 按 spec 完成了 Agent 过程叙事的交互体验提升，未引入回归，测试覆盖充分，叙事映射可复用。