# Novelos v5.8 Workflow Observability and Recovery 评审

## 评审结论

**状态：通过**

v5.8 在不重写 LangGraph 主链路的前提下，成功交付了工作流可观测性和恢复边界的最小闭环。所有验收标准已满足，测试通过，真实项目验收成功。

## 验收标准检查

| # | 标准 | 状态 | 说明 |
|---|------|------|------|
| 1 | 章节运行时能看到节点级日志 | ✅ | workflow_node_events 表记录每个节点的 started/completed/failed 事件，message 为中文可读 |
| 2 | 章节完成后能看到完整时间线 | ✅ | Timeline API 返回按时间排序的节点列表，包含 messages 和 artifacts |
| 3 | 卡住/失败时能看到原因和安全恢复动作 | ✅ | `recovery.recommended_action` 和 `safe_actions` 明确展示恢复建议 |
| 4 | 产物标签对作者可读，不暴露内部 key | ✅ | `state-labels.ts` 新增 `ARTIFACT_TYPE_LABEL`，UI 使用中文标签 |
| 5 | 页面停留在 workflow view 时能自动刷新 | ✅ | ProjectDetail.tsx 中 5 秒轮询 timeline API |
| 6 | 现有 guard/recovery/editor/versioning 全部不回归 | ✅ | 1878 后端测试 + 130 前端测试全部通过 |
| 7 | novel_3v2o 至少完成一章真实项目验收 | ✅ | 第 13 章成功生成，timeline API 验证通过，pending memory 已处理 |
| 8 | python3 scripts/verify.py full 通过 | ✅ | verify.py full 完成 |
| 9 | 文档新增 completion report 和 review | ✅ | 已新增 |

## 架构评审

### 数据模型

`workflow_node_events` 表设计合理：
- 字段覆盖 event_type、status、message、artifact_refs、token/latency/cost 等可选字段
- 两个索引（run_id + created_at, project_id + chapter_number + created_at）满足查询需求
- 迁移脚本遵循现有编号规范（030）

### API 设计

Timeline API 返回结构清晰：
- 顶层：run 元数据 + stale 检测 + recovery 建议
- 节点层：中文 label + 状态 + 时间 + messages + artifacts
- 支持可选 run_id 查询历史 run
- 无 run 时返回空 timeline 而不是 500

### 前端集成

- ProjectDetail.tsx 中新增 timeline state 和自动刷新逻辑，与现有 runDetail  polling 共存
- WorkflowBody 优先使用 timeline 数据，保留 runDetail fallback
- timelineError 以站内 alert 形式展示，不触发浏览器原生 alert

## 代码质量

### 优点

1. **最小修改原则**：未重写 LangGraph，未改动 LLM provider 抽象，未引入外部日志系统
2. **Best-effort 事件记录**：`_log_node_event` helper 使用 try/except 包裹，失败时只记录 warning，不阻塞主工作流
3. **向后兼容**：legacy mode 的独立节点函数也添加了事件记录
4. **中文可读性**：所有面向作者的 message 和 label 均使用中文

### 可改进点

1. **事件重复记录**：router mode 中 `_run_agent_node` 记录事件，legacy mode 中独立节点函数也记录事件。虽然一个 graph 实例只使用一种模式，不会实际重复，但代码层面存在两个入口点。
2. **Timeline 刷新频率固定**：当前为 5 秒固定间隔，未来可考虑根据 run_status 动态调整（running 时 5 秒，其他状态不轮询）。
3. **Artifact refs 未在节点事件中存储**：节点事件未直接存储 artifact_refs_json，timeline API 通过查询 agent_artifacts 表动态关联。这符合当前规格，但未来如需完整 replay，可能需要在节点事件中存储引用。

## Review 修复

本次 Review 发现并修复 2 个问题：

1. 新建 workflow run 时，`health_check` 创建 run_id 后没有把 run_id 写回事件 state，导致真实时间线从 `task_discovery` 才开始。
   - 修复：`health_check_node` 使用带 `workflow_run_id` 的 event_state 写入 `started/completed` 事件，并更新 current_node。
   - 测试：新增 `test_health_check_records_started_and_completed_events_for_new_run`。

2. ProjectDetail 切换章节时没有清空旧 timeline，右侧 AI 面板可能短暂读取上一章运行状态。
   - 修复：章节变化时清空 `timeline/timelineError`；timeline 成功加载后清空旧错误。

## 测试评审

### 后端测试（12 个）

| 测试 | 覆盖点 |
|------|--------|
| test_health_check_records_started_and_completed_events_for_new_run | 新建 run 时 health_check 写入 started/completed |
| test_node_events_created_during_run | 节点事件的创建和查询 |
| test_node_event_failure_does_not_block_main_workflow | best-effort 日志不阻塞主流程 |
| test_node_events_stub_and_real_mode_compatible | stub/real 模式兼容性 |
| test_timeline_returns_empty_when_no_run | 无 run 返回空 timeline |
| test_timeline_returns_nodes_and_artifacts | 正常 run 的节点和产物 |
| test_timeline_returns_recovery_for_stale_run | stale run 恢复建议 |
| test_timeline_no_recovery_for_terminal_chapter | 终态章节无恢复建议 |
| test_timeline_with_run_id_query_param | 历史 run 查询 |
| test_timeline_does_not_return_500_for_missing_chapter | 缺失章节不 500 |
| test_terminal_chapter_running_run_reconciled | 终态 + running reconcile |
| test_published_chapter_running_run_reconciled | published + running reconcile |

### 前端测试（5 个新增）

| 测试 | 覆盖点 |
|------|--------|
| renders timeline nodes with chinese labels from timeline data | timeline 正常渲染、中文标签 |
| shows running node loading animation in timeline | running 节点 loading 动效 |
| shows stale run recovery suggestions in timeline | stale run 恢复建议 |
| shows inline error when timeline refresh fails | 刷新失败站内错误 |
| does not show generate button for terminal chapter with timeline | 终态章节不显示生成入口 |

## 最终验证

```bash
python3 scripts/verify.py full
```

结果：

```text
pytest 1878 passed
frontend typecheck passed
frontend lint passed
frontend build passed
vitest 130 passed
```

真实项目补充验收：

- `novel_3v2o` 第 13 章生成并发布；
- timeline 返回 9 个节点，包含 `health_check`；
- 第 13 章记忆批次已应用；
- 当前 pending memory updates 为 0；
- `production-next` 推荐继续生成第 14 章。

## 风险与建议

### 短期（v5.8.x）

- 监控 timeline API 在生产环境（real mode）下的性能，节点事件表可能随时间增长
- 考虑为 workflow_node_events 添加定期清理策略或归档机制

### 中期（v5.9+）

- 基于 v5.8 的 observability 基础，可以安全地引入 Skills、上下文治理或 RAG
- 如需完整 replay/time travel，可扩展 workflow_node_events 的 input_summary/output_summary

## 签字

- 评审人：AI 助手
- 日期：2026-05-14
- 结论：**通过，建议合并**
