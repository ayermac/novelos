# Novelos v5.8 Workflow Observability and Recovery 完成报告

## 状态

- 类型：版本完成报告
- 状态：已完成
- 基线：v5.7.1 Internal Hardening
- 完成日期：2026-05-14

## 交付摘要

v5.8 在不对 LangGraph 主链路进行重写的前提下，完成了工作流可观测性和恢复边界的最小闭环。核心交付包括：

1. 节点级 workflow event 持久化
2. Workflow timeline API
3. 工作流页可观测 UI 增强
4. 恢复边界说明和中文可读标签
5. 后端和前端回归测试
6. 真实项目 `novel_3v2o` 验收

## 修改文件

### 后端

| 文件 | 说明 |
|------|------|
| `novel_factory/db/migrations/030_v5_8_workflow_node_events.sql` | 新增 workflow_node_events 表和索引 |
| `novel_factory/db/connection.py` | 添加 v5.8 迁移检测逻辑 |
| `novel_factory/db/repositories/workflow.py` | 新增 create/get workflow_node_event 方法 |
| `novel_factory/workflow/nodes.py` | 每个核心节点写入 started/completed/failed 事件 |
| `novel_factory/api/routes/workflow_timeline.py` | 新增 GET workflow-timeline API |
| `novel_factory/api/routes/__init__.py` | 导出 workflow_timeline_router |
| `novel_factory/api_app.py` | 注册 timeline 路由 |

### 前端

| 文件 | 说明 |
|------|------|
| `frontend/src/lib/state-labels.ts` | 新增 ARTIFACT_TYPE_LABEL 和 tArtifactType |
| `frontend/src/lib/api.ts` | 新增 WorkflowTimelineData 等类型 |
| `frontend/src/pages/ProjectDetail.tsx` | 新增 timeline 数据获取和自动刷新逻辑 |
| `frontend/src/components/project/AuthorWorkbench.tsx` | 传递 timeline 和 timelineError |
| `frontend/src/components/project/AuthorWritingSurface.tsx` | WorkflowBody 优先使用 timeline 数据展示节点时间线、恢复建议、站内错误 |
| `frontend/src/components/project/AuthorAgentPanel.tsx` | 使用 timeline 数据增强运行状态展示 |

### 测试

| 文件 | 说明 |
|------|------|
| `tests/test_v58_workflow_observability.py` | 12 个后端测试：节点事件、health_check 事件、空 timeline、恢复建议、终态 reconcile |
| `frontend/src/components/project/__tests__/AuthorWorkbench.test.tsx` | 5 个前端测试：timeline 渲染、loading、恢复建议、中文标签、站内错误 |

### 文档

| 文件 | 说明 |
|------|------|
| `docs/codex/reports/novel-factory-v5.8-completion-report.md` | 本报告 |
| `docs/codex/reviews/novel-factory-v5.8-review.md` | 版本评审 |

## 新增 API

```
GET /api/projects/{project_id}/chapters/{chapter_number}/workflow-timeline
GET /api/projects/{project_id}/chapters/{chapter_number}/workflow-timeline?run_id=...
```

返回字段：
- `run_id`, `run_status`, `current_node`, `started_at`, `elapsed_minutes`, `is_stale`
- `recovery`: `recommended_action`, `reason`, `safe_actions`
- `nodes`: 每个节点的 `node_name`, `label`, `status`, `started_at`, `completed_at`, `duration_ms`, `messages`, `artifacts`

## 新增数据结构

### 数据库表

`workflow_node_events`:
- `id`, `run_id`, `project_id`, `chapter_number`
- `node_name`, `event_type`, `status`, `message`
- `input_summary`, `output_summary`, `artifact_refs_json`
- `token_count`, `latency_ms`, `cost_estimate`
- `error_code`, `error_message`, `created_at`, `metadata_json`

### TypeScript 类型

- `WorkflowTimelineData`
- `WorkflowTimelineNode`
- `WorkflowTimelineArtifact`
- `WorkflowTimelineRecovery`

## 测试结果

### 后端

```
pytest tests/test_v58_workflow_observability.py
12 passed
```

全量回归：
```
pytest tests/
1878 passed, 856 warnings
```

### 前端

```
npm run typecheck   # 通过
npm run test        # 130 passed
npm run build       # 通过
```

### verify.py full

```
python3 scripts/verify.py full
✓ full 完成
```

## novel_3v2o 真实项目验收

使用 `novel_3v2o` 项目执行真实章节生成（stub mode）：

- 第 11 章生成并发布，初始 timeline 验证通过。
- Review 过程中发现新建 run 的 `health_check` 没有记录事件，已修复并补测试。
- 修复后重启 API，继续生成第 13 章并发布，`run_id: 22210d4e-0b3d-4c88-8a4d-cebf2bb947a4`。
- 节点事件记录：health_check → task_discovery → screenwriter → author → polisher → editor → memory_curator → publisher → archive，每个节点均有 started 和 completed 事件。
- Timeline API 返回 9 个节点，中文标签正确（预检、任务识别、编剧、执笔、润色、审核等）。
- 产物标签中文可读：章节场景规划、章节初稿、润色稿、审核报告、记忆更新
- 第 13 章记忆批次已应用，当前 pending memory updates 为 0。
- `production-next` 当前推荐继续生成第 14 章。

## 遗留风险

1. **Legacy mode 节点函数**：planner_node、screenwriter_node 等独立节点函数在 router mode 中不被直接调用（由 `_run_agent_node` 替代）。如果未来回退到 legacy mode，事件记录仍然有效，但当前生产路径主要依赖 `_run_agent_node`。
2. **Artifact refs 未在节点运行时自动关联**：当前 `_log_node_event` 的 `artifact_refs` 参数未在节点函数中传入，产物关联是通过 timeline API 查询 `agent_artifacts` 表动态构建的。这符合规格要求，但意味着节点事件本身不存储产物引用。
3. **Timeline 自动刷新间隔**：当前固定为 5 秒，对于极长章节可能不够实时，但符合最小闭环原则。
4. **前端 Error 提示样式**：`timelineError` 使用的是现有的 `alert-error` 样式，未引入新的视觉组件。

## 版本结论

v5.8 完成了工作流可观测性的最小闭环，所有测试通过，真实项目验收成功，无已知回归。建议合并后继续推进 v5.9（Skills、上下文治理或 RAG 等方向）。
