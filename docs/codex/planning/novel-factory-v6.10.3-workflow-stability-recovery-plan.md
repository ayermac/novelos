# Novel Factory v6.10.3 Workflow Diagnostics & Stability Plan

## 背景

v6.10.2 后，章节主链路已经明显稳定：`polisher → quality_gate → editor` 的独立门禁清晰，失败可走 `revision_router`，不再把可返修问题直接变成系统错误。下一步不应继续单纯加 blocking，而应提高故障可诊断性和长期质量稳定性。

v6.10.3 的目标是：**不增加正常创作阻塞率的前提下，让工作流失败原因更清楚、门禁降级更安全、发布前质量缺口更早暴露。**

## 目标

1. 增加 Run Doctor：运行结束后自动归因，区分模型输出失败、确定性质检失败、配置失败、运行超时、记忆整理失败等类型。
2. 增加 Checker 健康分级：必需 checker 失败不能静默通过；advisory checker 失败只进入诊断。
3. 增加标题发布前硬校验：缺失、截断、括号未闭合、正文脱节、过长标题阻止发布。
4. 优化 Memory Curator 降级：真实模式下正文已过审时，记忆整理失败不应让整章进入 human_review，应进入发布就绪并提示补跑记忆。
5. 保留并完善 memory curator 超时恢复入口：提供“补跑记忆提取”，不重置正文、过程稿或审核结果。

## 非目标

- 不新增更高阻塞率的内容质量规则。
- 不重构完整 LangGraph 拓扑。
- 不在本版本落地质量趋势持久化表。
- 不在本版本实现完整 Skill policy matrix 页面化。
- 不把 Run Doctor 诊断结果作为自动路由来源；它只做解释和下一步建议。

## P0 交付范围

### 1. Run Doctor

新增 `novel_factory/workflow/run_doctor.py`：

- `model_output_failure`：空内容、JSON/schema/parse 等模型输出异常。
- `deterministic_quality_failure`：QualityGate、质检门禁、blocking issues。
- `configuration_failure`：配置、profile、API key、LLM route 异常。
- `runtime_timeout`：节点超时、stale running、疑似卡住。
- `memory_failure`：Memory Curator 超时、失败或降级。
- `workflow_failure`：未能归入以上类型的节点失败。

`GET /api/runs/{run_id}` 返回 `run_doctor`，并在独立运行详情页与章节工作流面板展示诊断分类、摘要和建议动作。

### 2. Checker 健康分级

QualityGate checker 分为：

- **mandatory**：`death_penalty`、`word_count_gate`、`chapter_seam`、`continuity_gate`。
- **advisory**：`quality_diagnosis` 等聚合型建议。

规则：

- mandatory checker 正常运行但发现问题：按原本规则进入 blocking 或 advisory。
- mandatory checker 自身异常：进入“门禁降级” blocking，防止静默放行。
- advisory checker 自身异常：记录 `checker_errors`，不阻塞创作。

### 3. 标题发布前校验

新增 `novel_factory/quality/title_guard.py`，发布前检查：

- 标题缺失。
- 标题过短、过长。
- 标题以残缺虚词结尾。
- 括号、引号、书名号未闭合。
- 标题关键词未在正文出现。
- 标题混入换行正文片段。

接入点：

- LangGraph `publisher_node`。
- 手动发布 API `POST /api/publish/chapter`。

### 4. Memory Curator 降级策略

真实模式下，章节已进入 `reviewed / awaiting_publish / published` 时：

- Memory Curator 降级、fallback 或 extraction failure 不再直接路由到 `human_review`。
- 路由到 `awaiting_publish`，并通过 run doctor / timeline / backfill 入口提示补跑记忆。
- Memory lock 冲突仍保持安全保护，不重复启动同章记忆提取。

### 5. Memory Curator 恢复入口

保留补跑记忆能力作为 v6.10.3 稳定性子项：

- 节点超时时释放同源 memory curator lock。
- 时间线 terminal chapter + memory_curator blocked/failed 推荐 `backfill_memory`。
- 手动 backfill 会释放同源 stale/blocked lock，但不会释放其他活跃运行持有的 lock。
- 前端写作台、运行详情和右侧 Agent 面板显示“补跑记忆提取”。
- 前端运行详情展示 Run Doctor 诊断卡片，避免只在 API 中有诊断数据。

## P1 后续候选

- 章节质量趋势报告：持久化 `chapter_quality_metrics`。
- 核心卖点节奏检测：签到/奖励/权力兑现 1–2 章内必须出现。
- 概念预算接事实账本：区分“已出现概念”和“新概念”。
- Skill policy matrix：集中展示 hard/retryable/advisory/experimental。
- 质量趋势页面化。

## 验收标准

1. QualityGate mandatory checker 抛异常时，不静默通过，而是返回门禁降级 blocking。
2. Run detail 返回 `run_doctor`，能识别模型输出失败和确定性质检失败。
3. 手动发布和自动 publisher 都会阻止明显坏标题。
4. Memory Curator 降级在真实模式下不再让已过审正文进入 human_review。
5. Memory Curator timeout 有明确补跑入口，不要求重置整章。
6. 版本号在 runtime/frontend/desktop/package-lock 中保持一致。

## 验证计划

- `python3 -m pytest tests/test_v6103_workflow_diagnostics.py -q`
- `python3 -m pytest tests/test_v676_publish_guard.py tests/test_v685_quality_gate_node.py tests/test_workflow.py::TestRouteAfterMemoryCurator -q`
- `python3 -m pytest tests/test_version_alignment.py -q`
- `npm run lint`
- `npm run typecheck`
