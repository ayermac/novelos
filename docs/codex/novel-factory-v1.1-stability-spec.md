# v1.1 工程稳定性开发规范

## 目标

v1.1 的目标是把已经通过的 v1 MVP 升级为稳定、可恢复、可追踪、可重复运行的工程基线。

本轮不新增创作能力，不新增 Agent，不改变 v1 的五 Agent 主链路。

v1.1 重点解决：

- 工作流运行可追踪。
- Agent 产物可审计。
- 重跑不重复写入。
- 过期任务不能覆盖新状态。
- 中断后具备恢复基础。
- 任务超时可被识别和标记。

## 当前前置条件

必须基于以下状态开发：

- v1 MVP 已通过。
- v1 review 返工闸门已通过。
- 全量测试当前应为 `112/112` 或更多。
- `route_by_chapter_status` 已对 `requires_human` 和 `error` 做安全兜底。
- Agent 前置条件已以 DB 状态为真实来源。

## 本轮允许实现

允许修改：

- `novel_factory/db/repository.py`
- `novel_factory/db/migrations/*`
- `novel_factory/models/state.py`
- `novel_factory/models/schemas.py`
- `novel_factory/workflow/graph.py`
- `novel_factory/workflow/nodes.py`
- `novel_factory/workflow/conditions.py`
- `novel_factory/agents/*`
- `novel_factory/validators/*`
- `novel_factory/cli.py`
- `tests/*`

允许新增：

- `novel_factory/workflow/checkpoint.py`
- `novel_factory/workflow/run_manager.py`
- `novel_factory/utils/hash.py`
- `novel_factory/utils/time.py`
- `tests/test_stability.py`

## 本轮禁止实现

- 不新增 Scout / Architect / Secretary。
- 不新增 ContinuityChecker。
- 不新增多 Provider fallback。
- 不新增 Web UI / Web API。
- 不新增 Skill 热加载。
- 不引入 SQLModel 全量 ORM。
- 不改变 v1 Agent 输出契约。
- 不新增章节状态枚举。
- 不改变主链路 `Planner -> Screenwriter -> Author -> Polisher -> Editor`。

## 必修项

### S1：workflow_runs 全链路记录

问题：

- 当前已有 `workflow_runs` 表和 Repository 方法，但主 workflow 没有形成稳定的 run 生命周期。

要求：

- 每次图运行必须有 `workflow_run_id`。
- 如果 state 未传入 `workflow_run_id`，入口节点必须创建一个。
- 每个节点执行时更新 `workflow_runs.current_node`。
- 正常结束时标记 `workflow_runs.status=completed`。
- 失败或进入人工处理时标记 `failed` 或 `blocked`。

建议状态：

```text
running
completed
failed
blocked
```

验收：

- 测试覆盖：完整成功路径创建 workflow_run，并最终为 `completed`。
- 测试覆盖：missing chapter / blocking 路径最终为 `blocked`。
- 测试覆盖：节点错误时写入 `error_message`。

### S2：agent_artifacts 写入 hash 与幂等键

问题：

- 当前 `agent_artifacts` 有 `content_hash` 字段，但保存时未计算 hash，也没有幂等写入策略。

要求：

- 新增统一 hash 函数，例如 `stable_json_hash(payload: dict) -> str`。
- `save_artifact` 必须写入 `content_hash`。
- 同一 `project_id + chapter_number + agent_id + artifact_type + content_hash` 不应重复插入。
- 重复保存相同产物时返回已存在 artifact id。

建议：

- 为 `agent_artifacts` 增加唯一索引 migration：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_artifacts_idempotency
ON agent_artifacts(project_id, chapter_number, agent_id, artifact_type, content_hash);
```

验收：

- 测试覆盖：同一 artifact 保存两次只产生一条记录。
- 测试覆盖：内容变化时产生新 artifact。
- 测试覆盖：hash 对 JSON key 顺序不敏感。

### S3：chapter_versions 幂等与来源追踪

问题：

- 当前版本保存会自增版本号，但重跑同一 Agent 同一内容可能产生重复版本。

要求：

- 保存版本时计算 content hash。
- 如果同一 `project_id + chapter + created_by + content_hash` 已存在，不新增版本，返回已有版本 id。
- 如果现有表没有 `content_hash` 字段，新增 migration。
- `notes` 中不得塞结构化关键数据；结构化信息应进入字段或 artifact。

建议 migration：

```sql
ALTER TABLE chapter_versions ADD COLUMN content_hash TEXT;
CREATE INDEX IF NOT EXISTS idx_chapter_versions_hash
ON chapter_versions(project_id, chapter, created_by, content_hash);
```

验收：

- 测试覆盖：同一内容重复保存不增加版本数量。
- 测试覆盖：内容变化时版本号递增。
- 测试覆盖：created_by 不同时允许分别记录。

### S4：Repository 写入方法返回值必须可判断失败

问题：

- v1 中部分 Repository 写入方法总是返回成功，调用方无法知道是否真的写入。

要求：

- 所有更新类方法必须返回 `bool` 或具体 id。
- 更新类方法必须检查 `cursor.rowcount`。
- Agent 调用写入失败时必须返回 `error`，不得继续推进状态。

至少检查：

- `save_chapter_content`
- `update_chapter_status`
- `publish_chapter`
- `save_chapter_state`
- `complete_task`
- `update_workflow_run`

验收：

- 测试覆盖：目标章节不存在时，保存正文失败并不推进状态。
- 测试覆盖：发布不存在章节时返回错误。
- 测试覆盖：workflow_run 不存在时更新失败。

### S5：过期任务防覆盖

问题：

- v1r 已增加 expected status，但各 Agent 写入链路需要系统性使用。

要求：

- Agent 写入章节状态时必须传入 `expected_status`。
- Author 只能 `scripted -> drafted`。
- Polisher 只能 `drafted -> polished`。
- Editor 只能 `polished/review -> reviewed/revision/blocking`。
- Publisher 只能 `reviewed -> published`。
- Revision 路径必须保持原有安全检查。

验收：

- 测试覆盖：Author 写完正文前 DB 状态被改为 `review`，不得推进到 `drafted`。
- 测试覆盖：Polisher 写入前 DB 状态被改为 `review`，不得推进到 `polished`。
- 测试覆盖：Publisher 只能发布 `reviewed` 状态章节。

### S6：task 超时标记

问题：

- 当前有 `task_status`，但缺少超时扫描和标记能力。

要求：

- Repository 增加 `mark_timed_out_tasks(project_id: str, timeout_minutes: int) -> int`。
- 将 `running` 且 `started_at` 超过阈值的任务标记为 `timeout` 或 `failed`。
- 推荐使用 `timeout`，但不得新增章节状态。
- 超时处理不自动重试，不自动唤醒 Agent。

验收：

- 测试覆盖：超时 running task 被标记。
- 测试覆盖：未超时 running task 不变。
- 测试覆盖：completed task 不变。

### S7：checkpoint 恢复基础

问题：

- v1 使用 `MemorySaver`，进程重启不可恢复。

要求：

- 不要求完整生产级 checkpoint，但必须提供可替换接口。
- `compile_graph(checkpoint=True)` 应支持传入 checkpointer。
- 默认仍可使用 `MemorySaver`。
- 文档和代码注释必须明确：v1.1 默认 checkpoint 仍不保证跨进程恢复，除非传入持久化 checkpointer。

建议接口：

```python
def compile_graph(
    settings: Settings | None = None,
    repo: Repository | None = None,
    llm: LLMProvider | None = None,
    checkpointer: Any | None = None,
    checkpoint: bool = True,
):
    ...
```

验收：

- 测试覆盖：可以传入自定义 checkpointer。
- 测试覆盖：`checkpoint=False` 时不使用 checkpointer。

## 测试要求

新增测试文件建议：

- `tests/test_stability.py`
- 或按现有结构拆入 `test_repository.py`、`test_workflow.py`

必须覆盖：

- workflow run 成功路径。
- workflow run blocking 路径。
- artifact 幂等写入。
- artifact hash key 顺序稳定。
- chapter version 幂等写入。
- Repository 写入失败返回 false/error。
- expected status 防覆盖。
- task timeout 标记。
- compile_graph 自定义 checkpointer。

完成后全量测试必须通过。

## 回归要求

开发 Agent 完成本轮后必须汇报：

- 修改文件列表。
- 新增 migration。
- 新增测试列表。
- 全量测试数量。
- 测试结果。
- 是否有未完成项或风险。

## 验收标准

- v1 原有测试全部通过。
- v1r 返工测试全部通过。
- v1.1 新增测试全部通过。
- 没有新增 v1.2 / v2 能力。
- 幂等、追踪、超时、防覆盖四类稳定性能力均有测试。

## 通过后下一步

v1.1 通过后，进入 **v1.2 质量与一致性增强**。

v1.2 才允许重点处理：

- 完整 ContextBuilder。
- 更强 death penalty。
- 更强 state verifier。
- 更强 plot verifier。
- learned_patterns。
- best_practices。
- Editor 退回原因分类。
