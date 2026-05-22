# v6.1 Agent Work Process Streaming & Auditable Execution Evidence

## 概述

v6.1 将工作流页面从"节点状态图"升级为"实时工作过程 + 节点证据详情 + 历史回放"。

## 设计原则

- **不展示模型原始思考链**：只展示结构化、可审计、可验证的执行过程
- **完成 = 节点完成 + 证据校验通过**：不再是"没有错误就算完成"
- **SSE 首选，轮询兜底**：实时直播优先，刷新后仍可回放历史事件
- **不破坏现有工作流**：所有执行事件日志均为 best-effort

## 核心交付

### A. 数据库：workflow_execution_events 表

新表存储 Agent 级别的细粒度执行证据，与粗粒度的 workflow_node_events 分离。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增主键 |
| run_id | TEXT | 工作流运行 ID |
| project_id | TEXT | 项目 ID |
| chapter_number | INTEGER | 章节号 |
| node_name | TEXT | 节点名称 |
| agent_id | TEXT | Agent ID |
| event_type | TEXT | 事件类型 |
| status | TEXT | 状态 (info/pass/fail/warn) |
| message | TEXT | 中文用户可读消息 |
| payload_json | TEXT | JSON 载荷 |
| artifact_refs_json | TEXT | 产物引用 |
| token_count | INTEGER | Token 数量 |
| latency_ms | INTEGER | 延迟毫秒 |
| created_at | DATETIME | 创建时间 |

### B. 事件类型

| event_type | 说明 |
|---|---|
| node_started | 节点开始执行 |
| context_loaded | 上下文加载完成 |
| llm_started | LLM 调用开始 |
| llm_completed | LLM 调用完成 |
| llm_failed | LLM 调用失败 |
| artifact_saved | 产物保存 |
| skill_completed | Skill 执行完成 |
| self_check_completed | 自检完成 |
| fallback_used | 使用降级/兜底 |
| diff_generated | 润色 diff 生成 |
| evidence_verified | 证据校验 |
| node_completed | 节点完成 |
| node_failed | 节点失败 |

### C. Agent 级证据覆盖

| Agent | 证据项 |
|---|---|
| Planner | context_loaded, llm_completed, artifact_saved, evidence_verified |
| Screenwriter | context_loaded, llm_completed, artifact_saved, skill_completed, evidence_verified |
| Author | context_loaded, llm_completed/fallback_used, self_check_completed, artifact_saved, evidence_verified |
| Polisher | context_loaded, llm_completed, diff_generated, artifact_saved, skill_completed, evidence_verified |
| Editor | context_loaded, llm_completed/fallback_used, artifact_saved, evidence_verified |
| MemoryCurator | context_loaded, llm_completed, fallback_used, artifact_saved, evidence_verified |

### D. 完成证据校验

每个核心 Agent 有独立的证据校验器：

- **Planner**：instruction 存在且包含 objective/key_events/ending_hook → 缺失则 fail
- **Screenwriter**：scene beats 存在且每个 beat 有 goal/conflict/turn/hook → 缺失则 fail
- **Author**：正文非空、标题存在、版本已保存、draft 产物已保存 → 缺失则 fail
- **Polisher**：正文已保存、polished_draft 产物已保存 → 缺失则 fail
- **Editor**：审核记录已保存；通过时状态卡必须已保存 → 缺失则 fail
- **MemoryCurator**：有 memory batch 或明确的 no-op 记录 → 都没有则 warn

### E. SSE API

```
GET /api/projects/{project_id}/chapters/{chapter_number}/workflow-stream
```

- 先回放已有事件（replay=true 默认）
- 然后每 1.5 秒轮询新事件
- 支持 `since_id` 参数过滤已见事件
- 发送 `workflow_event` 和 `workflow_done` SSE 事件
- 最长轮询 30 分钟

### F. Timeline API 扩展

```
GET /api/projects/{project_id}/chapters/{chapter_number}/workflow-timeline
```

每个节点新增字段：
- `events[]`：执行事件列表
- `evidence`：证据摘要 (has_evidence, has_warnings, has_evidence_failure, latest_event_summary)

向后兼容：无执行事件时返回空列表。

### G. 前端 UI

- WorkflowTimeline 组件新增"查看过程"展开面板
- 显示每个节点的实时工作过程事件
- 证据校验状态徽章（通过/有警告/失败）
- 中文标签，不展示内部 token 名称

## 已知限制

- SSE 不使用 WebSocket，依赖 HTTP 长连接
- 执行事件为 best-effort，不会阻断主工作流
- 证据校验失败当前仅记录警告，不阻止节点完成
- 前端 SSE 连接断开时无自动重连（依赖页面刷新）

## 验证命令

```bash
python3 -m pytest tests/test_v61_agent_work_process_streaming.py -q
python3 -m pytest tests/test_v58_workflow_observability.py tests/test_agents.py -q
cd frontend && npm run typecheck && npm run lint && npm run build
```
