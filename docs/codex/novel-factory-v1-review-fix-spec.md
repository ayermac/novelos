# v1 Review 返工规范

## 目标

本轮不是 v1.1，也不是新功能开发。本轮目标是对已经通过测试的 v1 MVP 做一次质量闸门返工，清理实现中的小债务，确保 v1 可以作为后续 v1.1 的稳定基线。

开发 Agent 必须只修复本文列出的 v1 问题，不得顺手实现 v1.1、v1.2 或 v2 功能。

## 当前状态

开发 Agent 已汇报：

- 98/98 测试通过。
- 5 Agent 流水线已实现。
- 4 大硬验证器已实现。
- 状态前置条件已实现。
- 模板方法模式已实现。
- `agents.yaml` 配置已实现。
- CLI 入口已实现。
- SQLite 指令存储含 UPSERT 已实现。
- 验收测试覆盖核心场景。

本轮基于该状态进行 review 返工。

## 允许修改范围

允许修改：

- `novel_factory/agents/base.py`
- `novel_factory/workflow/nodes.py`
- `novel_factory/workflow/graph.py`
- `novel_factory/db/repository.py`
- `novel_factory/models/state.py`
- `novel_factory/validators/*`
- `tests/*`
- 必要的文档注释和 README

不允许修改：

- 不新增 Agent。
- 不新增 Provider。
- 不新增 Web API / Web UI。
- 不新增 Skill 热加载。
- 不引入 SQLModel 全量 ORM。
- 不改变 v1 固定章节状态枚举。
- 不重构 `openclaw-agents`。

## 必修返工项

### R1：清理 `BaseAgent.run` 重复定义

问题：

- `BaseAgent` 中存在两个 `run` 方法定义。
- Python 会以后一个为准，测试能过，但代码可读性差，容易误导后续开发 Agent。

要求：

- 删除前一个无效的 `run` 定义。
- 保留模板方法模式：公开 `run()` 负责前置检查、异常处理和调用 `_execute()`。
- 子类继续实现 `_execute()`，不要覆盖 `run()`。

验收：

- `BaseAgent` 中只允许出现一个 `def run(`。
- 所有现有 Agent 测试继续通过。

### R2：`task_discovery_node` 必须读取 DB 当前状态

问题：

- 当前 `task_discovery_node` 只检查 `project_id` 和 `chapter_number`，没有从数据库读取最新章节状态。
- 这会导致图状态与数据库状态不一致时继续错误路由。

要求：

- 调整 `task_discovery_node`，使其可以访问 `Repository`。
- 从 DB 读取 `chapters.status`。
- 如果 DB 中不存在章节，返回错误并进入人工处理或停止流程。
- 如果 DB 状态与传入 `FactoryState.chapter_status` 不一致，以 DB 状态为准更新 state。

建议实现：

```python
def task_discovery_node(state: FactoryState, repo: Repository) -> dict:
    status = repo.get_chapter_status(state["project_id"], state["chapter_number"])
    if not status:
        return {"error": "Chapter not found", "requires_human": True}
    return {"chapter_status": status}
```

验收：

- 增加测试：state 中是 `planned`，DB 中是 `scripted`，路由必须按 `scripted` 执行。
- 增加测试：DB 中章节不存在时，不得继续进入 Agent 写入节点。

### R3：Repository 状态更新增加 expected status 保护

问题：

- `update_chapter_status` 注释提到 optimistic lock，但 SQL 没有 `expected_status` 条件。
- 当前实现不能防止过期任务覆盖新状态。

要求：

- 为 `update_chapter_status` 增加可选参数 `expected_status`。
- 当传入 `expected_status` 时，SQL 必须带 `AND status=?`。
- 更新失败时返回 `False`，调用方不得假装成功。

建议接口：

```python
def update_chapter_status(
    self,
    project_id: str,
    chapter_number: int,
    status: str,
    expected_status: str | None = None,
) -> bool:
    ...
```

验收：

- 增加测试：DB 当前状态不等于 expected status 时，更新失败且状态不变。
- 增加测试：DB 当前状态等于 expected status 时，更新成功。
- 现有调用方根据需要传入 expected status。

### R4：Agent 前置条件必须校验 DB 当前状态

问题：

- `BaseAgent.check_precondition` 当前只校验 `FactoryState.chapter_status`。
- 如果 state 过期，Agent 仍可能写入。

要求：

- `check_precondition` 先读取 DB 当前章节状态。
- 以 DB 状态作为真实状态进行权限判断。
- 如果 DB 状态与 state 不一致，应返回错误或更新 state 后由 workflow 重新路由，不允许继续写入。

验收：

- 增加测试：state 为 `scripted`，DB 为 `planned`，Author 不得写入正文。
- 增加测试：state 为 `drafted`，DB 为 `review`，Polisher 不得写入润色稿。

### R5：统一 word count 工具函数

问题：

- Repository 中 `save_chapter_content` 使用 `len(content)` 作为 `word_count`。
- v1 可以接受近似，但必须封装，避免后续多个模块自行计算导致不一致。

要求：

- 新增统一工具函数，例如 `novel_factory/validators/chapter_checker.py::count_words` 或 `novel_factory/utils/text.py::count_words`。
- `save_chapter_content`、Author 校验、Polisher 保存版本使用同一函数。
- 中文场景可继续使用字符数近似，但必须只有一个实现。

验收：

- 增加测试覆盖中文文本计数。
- 搜索代码中不应出现多个独立 `len(content)` 用作 word_count 的逻辑。

## 可选清理项

以下项如果改动小，可以同轮完成；如果牵涉较大，留到 v1.1：

- 删除未使用的 `_make_agents` 或开始复用它，避免死代码。
- 移除未使用 import，例如 `BaseAgent` 中从 `models.schemas` 导入的 `BaseModel`。
- 在 `publisher_node` 中检查 `repo.publish_chapter` 的返回值，失败时返回错误。
- 在 `human_review_node` 中同步写入 `chapter_status=blocking`，如果尚未写入。

## 不允许做的事

- 不实现持久化 checkpoint。
- 不实现 task timeout。
- 不实现多 Provider fallback。
- 不实现 Scout / Architect / Secretary。
- 不实现 ContinuityChecker。
- 不改动 v1 Agent 输出契约。
- 不新增章节状态。

这些属于 v1.1 或后续版本。

## 必须补充的测试

至少新增或确认以下测试：

- `test_base_agent_has_single_run_method`
- `test_task_discovery_uses_db_status_over_state_status`
- `test_task_discovery_missing_chapter_requires_human`
- `test_update_chapter_status_expected_status_success`
- `test_update_chapter_status_expected_status_failure`
- `test_author_rejects_when_state_stale_against_db`
- `test_polisher_rejects_when_state_stale_against_db`
- `test_count_words_is_shared_for_chapter_content`

测试命名可调整，但必须覆盖等价场景。

## 回归要求

开发 Agent 完成本轮返工后必须汇报：

- 修改了哪些文件。
- 新增了哪些测试。
- 完整测试数量。
- 测试结果。
- 是否有未完成项。

验收标准：

- 全量测试通过。
- v1 原有验收测试仍通过。
- 没有新增 v1 范围外能力。
- 本文 R1-R5 必修项全部完成。

## 通过后下一步

本轮通过后，进入 `v1.1 工程稳定性` 规划。

v1.1 才允许处理：

- 持久化 checkpoint。
- workflow run 全链路记录。
- task 超时。
- 幂等写入。
- agent artifact hash。
- 过期任务防覆盖。
