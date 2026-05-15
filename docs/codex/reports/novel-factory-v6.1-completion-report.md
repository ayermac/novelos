# v6.1 Completion Report

## 版本：v6.1 Agent Work Process Streaming & Auditable Execution Evidence

### 状态：完成

### 变更文件列表

**新增文件：**
- `novel_factory/db/migrations/032_v6_1_workflow_execution_events.sql` — 新表迁移
- `novel_factory/db/repositories/execution_event.py` — Repository mixin
- `novel_factory/workflow/execution_events.py` — 事件日志 + 证据校验模块
- `frontend/src/hooks/useWorkflowStream.ts` — 工作流过程直播 SSE hook
- `frontend/src/components/__tests__/WorkflowTimeline.test.tsx` — timeline 证据展示测试
- `tests/test_v61_agent_work_process_streaming.py` — 24 个测试
- `docs/codex/planning/novel-factory-v6.1-agent-work-process-streaming-spec.md`
- `docs/codex/reports/novel-factory-v6.1-completion-report.md`
- `docs/codex/reviews/novel-factory-v6.1-review.md`

**修改文件：**
- `novel_factory/db/repository.py` — 注册 ExecutionEventRepositoryMixin
- `novel_factory/workflow/nodes.py` — 集成执行事件日志 + 证据校验
- `novel_factory/agents/planner.py` — 添加 _exec_events
- `novel_factory/agents/screenwriter.py` — 添加 _exec_events
- `novel_factory/agents/author.py` — 添加 fallback/self_check/artifact 事件
- `novel_factory/agents/polisher.py` — 添加 diff/artifact/skill 事件
- `novel_factory/agents/editor.py` — 添加 fallback/artifact 事件
- `novel_factory/agents/memory_curator.py` — 添加 fallback/artifact 事件
- `novel_factory/api/routes/workflow_timeline.py` — SSE 端点 + timeline 扩展
- `frontend/src/lib/api.ts` — 新增 WorkflowExecutionEvent/WorkflowNodeEvidence 类型
- `frontend/src/components/WorkflowTimeline.tsx` — 执行事件面板 UI
- `frontend/src/components/project/AuthorWritingSurface.tsx` — workflow tab 接入 SSE live events

### 验证结果

- v6.1 测试：24/24 通过
- v5.8 可观测性测试：26/26 通过
- Agent 测试：26/26 通过
- 前端 WorkflowTimeline 测试：2/2 通过
- 前端 typecheck/lint/build：全部通过

### Review 修复补充

- 修复 MemoryCurator 证据校验误用 `chapter_number` 参数的问题，改为读取项目批次后按章节过滤，并补充章节批次命中测试。
- 修复 SSE 显式 `run_id` 只依赖最近运行的问题，timeline 与 stream 均支持按历史 run 精确查询。
- workflow 页面接入 `workflow-stream` SSE，运行中节点可合并实时事件，并对重复 replay 事件去重。
- 证据校验失败/警告在节点折叠态直接显示，不需要展开后才能发现。
- SSE hook 在 run 切换后会重置完成状态，避免上一轮结束导致下一轮不再连接。
