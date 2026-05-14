# Novelos v5.8 工作流可观测与恢复增强规格

## 状态

- 类型：可执行规划规格
- 状态：completed
- 基线：v5.7.1 Internal Hardening
- 产品目标：让作者在工作流运行中和运行后都能理解“现在做到了哪里、每个节点做了什么、卡住时该怎么恢复”
- 技术目标：新增节点级运行日志、时间线 API、工作流页可观测 UI，并收紧恢复动作边界
- 完成日期：2026-05-14
- 最终验证：`python3 scripts/verify.py full` 通过，pytest `1878 passed`，vitest `130 passed`，frontend typecheck/lint/build passed

## 背景

v5.7.1 已经把真实项目运行状态、production-next、记忆更新、导出和全量测试收敛到稳定状态。

下一阶段不应该继续扩展大功能，而应该解决作者使用过程中的核心不确定感：

- 工作流页面只显示节点状态，不知道节点里发生了什么；
- 运行疑似卡住时，作者只能看到“当前节点”，缺少最近日志和恢复建议；
- 产物与节点关系还不够清晰；
- 成功、失败、恢复的过程缺少可复盘时间线；
- 后续做 Skills、上下文治理、RAG 前，需要先有稳定的 AgentOps 基础。

v5.8 不是完整 replay 系统，也不是 Agent 框架重写。它只做工作流可观测和恢复可解释的最小闭环。

## 产品原则

1. 作者必须能看懂工作流，而不是只看见内部节点名。
2. 每个节点都应该留下可读日志和产物摘要。
3. 恢复动作必须解释为什么安全、会影响什么。
4. 不增加新的自动覆盖风险。
5. 不重写 LangGraph 主链路。
6. 不把 AgentOps 做成比创作本身更重的主界面。

## 非目标

- 不实现完整 replay/time travel。
- 不做多 Agent 动态编排重构。
- 不引入 Pi 作为运行时依赖。
- 不做大型数据库迁移或外部日志系统。
- 不做 RAG、长篇记忆治理、写作 Skills。
- 不重构 WebUI 视觉系统。
- 不改变 v5.5.15 guard、v5.6.1 recovery、v5.7 editor/versioning 的语义。

## 核心交付

### 1. 节点级运行日志

新增或扩展持久化结构，用于记录每个 workflow run 的节点事件。

建议数据模型：`workflow_node_events`

字段建议：

```text
id
run_id
project_id
chapter_number
node_name
event_type              # started | progress | completed | failed | skipped | recovery
status                  # running | completed | failed | skipped
message                 # 给作者看的短句
input_summary           # 可选，节点输入摘要
output_summary          # 可选，节点输出摘要
artifact_refs_json      # 可选，关联产物
token_count             # 可选
latency_ms              # 可选
cost_estimate           # 可选
error_code              # 可选
error_message           # 可选
created_at
metadata_json           # 可选，保留扩展
```

实现要求：

1. 每个核心节点至少写入 `started` 和 `completed/failed`。
2. 对已有 artifact 生成点建立关联摘要，不需要复制完整正文。
3. message 必须是中文可读文案，不暴露 `scene_plan (screenwriter)` 这类内部表示。
4. 日志写入失败不能导致主工作流失败，但必须进入 backend warning 日志。
5. stub mode 和 real mode 都要可用。

### 2. 工作流时间线 API

新增 API：

```text
GET /api/projects/{project_id}/chapters/{chapter_number}/workflow-timeline
```

返回建议：

```json
{
  "project_id": "novel_3v2o",
  "chapter_number": 11,
  "run_id": "...",
  "run_status": "running",
  "current_node": "polisher",
  "started_at": "...",
  "elapsed_minutes": 12,
  "is_stale": false,
  "recovery": {
    "recommended_action": null,
    "reason": null,
    "safe_actions": []
  },
  "nodes": [
    {
      "node_name": "screenwriter",
      "label": "编剧",
      "status": "completed",
      "started_at": "...",
      "completed_at": "...",
      "duration_ms": 1234,
      "messages": ["已生成章节场景规划"],
      "artifacts": [
        {"type": "scene_plan", "label": "章节场景规划", "artifact_id": "..."}
      ]
    }
  ]
}
```

实现要求：

1. 如果没有 run，返回空 timeline，但不要 500。
2. 如果 run 已 stale，返回 `recovery.recommended_action`。
3. 如果章节是终态但存在 running run，复用现有 contradiction/reconcile 语义。
4. API 不返回超长正文，只返回摘要和 artifact refs。
5. 对历史 runs 支持通过可选 `run_id` 查询：

```text
GET /api/projects/{project_id}/chapters/{chapter_number}/workflow-timeline?run_id=...
```

### 3. 工作流页 UI 增强

在 Author Workbench 的 workflow view 中增强展示：

1. 顶部运行摘要：
   - 当前 run 状态；
   - 当前节点；
   - 运行时长；
   - 是否疑似卡住；
   - 下一步恢复建议。
2. 节点时间线：
   - 每个节点的中文名称；
   - 状态灯；
   - 开始/完成时间；
   - 最近消息；
   - 关联产物入口。
3. 运行中加载动效：
   - 当前节点使用明确 loading 动效；
   - 页面停留时自动刷新 timeline；
   - 刷新失败显示站内错误提示，不用浏览器原生 alert。
4. 卡住/失败恢复：
   - 显示为什么判定为卡住；
   - 展示安全动作：查看产物、标记阻塞、清除阻塞并重置；
   - 禁止对终态章节展示重复生成入口。

### 4. 产物标签可读性补强

工作流节点日志和产物入口必须统一使用中文标签。

建议复用或扩展现有 `state-labels.ts`：

```text
scene_plan -> 章节场景规划
draft -> 章节初稿
polished_content -> 润色稿
review_report -> 审核报告
memory_update -> 记忆更新
```

禁止在主 UI 上暴露：

```text
scene_plan (screenwriter)
polished_content (polisher)
artifact_type
agent_id
```

这些内部字段可以保留在 tooltip 或 debug 折叠区，但不能作为默认主文案。

### 5. 恢复边界说明

在 timeline API 和 UI 中明确恢复语义：

1. `mark_stuck`：只把运行标记为阻塞，不清空正文。
2. `reset_chapter`：清理运行/checkpoint，保留当前正文和版本。
3. `explicit_clear_and_regenerate`：只有用户明确确认时才能清空正文并重新生成。
4. `published/reviewed/awaiting_publish`：不能重复生成，只能编辑修订版或继续下一章。

恢复按钮必须有 pending/loading 状态，避免重复点击。

## 文件范围

优先涉及：

```text
novel_factory/db/migrations/
novel_factory/db/repositories/
novel_factory/workflow/nodes.py
novel_factory/workflow/runner.py
novel_factory/api/routes/runs.py
novel_factory/api/routes/production.py
novel_factory/api/routes/versions.py
frontend/src/components/project/AuthorWritingSurface.tsx
frontend/src/components/project/AuthorAgentPanel.tsx
frontend/src/components/project/AuthorWorkbench.css
frontend/src/lib/api.ts
frontend/src/lib/state-labels.ts
tests/
frontend/src/components/project/__tests__/
```

不要为了 v5.8 主动改动：

```text
LLM provider 主抽象
LangGraph 图结构
项目 onboarding
多租户/权限
RAG/向量库
导出格式
```

## 推荐实施顺序

1. 新增 workflow node event 数据模型和 repository 方法。
2. 在 workflow runner/nodes 中写入节点 started/completed/failed 事件。
3. 新增 timeline API。
4. 增加后端测试：
   - 正常完成 run 生成节点事件；
   - failed/stale run 返回恢复建议；
   - 无 run 返回空 timeline；
   - 终态章节 + running 不回归。
5. 前端接入 timeline API。
6. 工作流页展示 timeline 和节点日志。
7. 补前端测试：
   - timeline 正常渲染；
   - running 节点有 loading；
   - stale run 有恢复建议；
   - artifact label 中文可读；
   - 刷新失败用站内错误。
8. 真实项目 `novel_3v2o` 验收第 11 章生成过程。
9. 运行 `python3 scripts/verify.py full`。
10. 新增 completion report 和 review。

## 验收标准

v5.8 完成必须满足：

1. 章节运行时能看到节点级日志。
2. 章节完成后能看到完整时间线。
3. 卡住/失败时能看到原因和安全恢复动作。
4. 产物标签对作者可读，不暴露内部 key 作为主文案。
5. 页面停留在 workflow view 时能自动刷新。
6. 现有 guard/recovery/editor/versioning 全部不回归。
7. `novel_3v2o` 至少完成一章真实项目验收。
8. `python3 scripts/verify.py full` 通过。
9. 文档新增：

```text
docs/codex/reports/novel-factory-v5.8-completion-report.md
docs/codex/reviews/novel-factory-v5.8-review.md
```

## 开发 Prompt

按以下规格实现 `v5.8 Workflow Observability and Recovery`：

```text
docs/codex/planning/novel-factory-v5.8-workflow-observability-recovery-spec.md
```

目标是增强现有 Author Workbench 的工作流可观测性，而不是重写 Agent 系统。

必须交付：

1. 节点级 workflow event 持久化；
2. workflow timeline API；
3. 工作流页节点日志和自动刷新；
4. 卡住/失败恢复建议；
5. 中文可读 artifact/node label；
6. 后端和前端回归测试；
7. 真实项目 `novel_3v2o` 验收；
8. completion report 和 review。

不要做：

- 不接入 Pi；
- 不替换 LangGraph；
- 不做 RAG；
- 不做多租户/权限；
- 不做大型 UI 视觉重构；
- 不做完整 replay/time travel。

完成前必须运行：

```bash
python3 scripts/verify.py full
```
