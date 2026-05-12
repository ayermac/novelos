# v1 章节生产 MVP 规格

## 目标

v1 的目标是跑通单章小说生产闭环，而不是实现完整小说工厂。

主链路：

```text
Planner -> Screenwriter -> Author -> Polisher -> Editor
```

章节状态：

```text
planned -> scripted -> drafted -> polished -> review -> reviewed -> published
review -> revision -> drafted/polished -> review
任意严重异常 -> blocking
```

## 技术栈

v1 固定技术栈：

```text
Python 3.11+
LangGraph
LangChain Core
SQLite
Pydantic v2
YAML 配置
pytest
OpenAI-compatible LLM Provider
Repository 数据访问层
```

v1 不使用完整 SQLModel ORM 接管既有表。Repository 优先兼容 `openclaw-agents/shared/data/init_db.sql`。

## 必须实现

- `novel_factory/` 主包骨架。
- `FactoryState`。
- Agent 输入输出 Pydantic schema。
- SQLite Repository。
- LangGraph 主流程。
- `BaseAgent`。
- `PlannerAgent`。
- `ScreenwriterAgent`。
- `AuthorAgent`。
- `PolisherAgent`。
- `EditorAgent`。
- OpenAI-compatible LLM Provider。
- 基础硬校验。
- pytest 集成测试。

## 不允许实现

- 多 Provider 原生适配。
- Skill 热加载。
- Web UI / Web API。
- Scout。
- Architect。
- Secretary。
- ContinuityChecker 独立 Agent。
- SQLModel 全量 ORM 接管。
- 新增未记录的 `chapters.status` 状态。

## 推荐目录

```text
novel_factory/
  __init__.py
  config/
    settings.py
    agents.yaml
    llm.yaml
  models/
    state.py
    schemas.py
    outputs.py
  db/
    connection.py
    repository.py
    migrations/
      001_add_workflow_tables.sql
  workflow/
    graph.py
    nodes.py
    conditions.py
  agents/
    base.py
    planner.py
    screenwriter.py
    author.py
    polisher.py
    editor.py
  context/
    builder.py
  validators/
    chapter_checker.py
    state_verifier.py
    plot_verifier.py
    death_penalty.py
  llm/
    provider.py
    openai_compatible.py
  cli.py
tests/
  test_workflow/
  test_agents/
  test_validators/
```

## 状态模型

`FactoryState` 最少字段：

```python
from typing import Any, TypedDict


class FactoryState(TypedDict, total=False):
    workflow_run_id: str
    project_id: str
    chapter_number: int
    current_stage: str
    task_id: str
    chapter_status: str
    artifact_refs: dict[str, str]
    quality_gate: dict[str, Any]
    messages: list[dict[str, Any]]
    retry_count: int
    max_retries: int
    requires_human: bool
    error: str | None
```

## 固定章节状态

v1 只允许使用以下状态：

```text
idea
outlined
planned
scripted
drafted
polished
review
reviewed
revision
published
blocking
```

如果需要更细的内部阶段，写入 `FactoryState.current_stage` 或 `workflow_runs.current_node`，不要扩展 `chapters.status`。

## Agent 职责

### Planner

职责：

- 读取项目、世界观、角色、大纲、伏笔和上一章状态。
- 生成本章 `chapter_brief`。
- 只规划，不写正文。

输出：

```json
{
  "chapter_brief": {
    "objective": "...",
    "required_events": ["..."],
    "plots_to_plant": ["P001"],
    "plots_to_resolve": [],
    "ending_hook": "...",
    "constraints": ["..."]
  }
}
```

### Screenwriter

职责：

- 将 `chapter_brief` 拆成场景 beat。
- 标记冲突、转折、伏笔落点和章末钩子。
- 不改世界观，不写最终正文。

输出：

```json
{
  "scene_beats": [
    {
      "sequence": 1,
      "scene_goal": "...",
      "conflict": "...",
      "turn": "...",
      "plot_refs": ["P001"],
      "hook": "..."
    }
  ]
}
```

### Author

职责：

- 根据 `chapter_brief`、`scene_beats`、状态卡和上下文写草稿。
- 不创建设定、角色、伏笔。

输出：

```json
{
  "title": "第N章 ...",
  "content": "...",
  "word_count": 2800,
  "implemented_events": ["..."],
  "used_plot_refs": ["P001"]
}
```

### Polisher

职责：

- 去 AI 味、优化句式、节奏和对话。
- 不改变剧情事实。

输出：

```json
{
  "content": "...",
  "fact_change_risk": "none",
  "changed_scope": ["sentence", "dialogue", "rhythm"],
  "summary": "..."
}
```

### Editor

职责：

- 执行设定、逻辑、毒点、文字、节奏审核。
- 通过时写入 `reviewed` 和状态卡。
- 不通过时写入 `revision` 和 `revision_target`。

输出：

```json
{
  "pass": true,
  "score": 92,
  "scores": {
    "setting": 23,
    "logic": 24,
    "poison": 19,
    "text": 13,
    "pacing": 13
  },
  "issues": [],
  "suggestions": [],
  "revision_target": null,
  "state_card": {}
}
```

`revision_target` 只允许为 `author`、`polisher`、`planner` 或 `null`。

## 必须实现的接口

```python
class BaseAgent:
    agent_id: str

    def build_context(self, state: FactoryState) -> str:
        ...

    def run(self, state: FactoryState) -> dict:
        ...

    def validate_output(self, output: dict) -> None:
        ...
```

```python
class Repository:
    def get_chapter_status(self, project_id: str, chapter_number: int) -> str:
        ...

    def update_chapter_status(self, project_id: str, chapter_number: int, status: str) -> None:
        ...

    def save_artifact(self, artifact: dict) -> str:
        ...

    def start_task(self, project_id: str, chapter_number: int, task_type: str, agent_id: str) -> str:
        ...

    def complete_task(self, task_id: str, success: bool, error: str | None = None) -> None:
        ...
```

```python
class LLMProvider:
    def invoke_json(self, messages: list[dict], schema: type) -> dict:
        ...

    def invoke_text(self, messages: list[dict]) -> str:
        ...
```

## 工作流路由

基础路由：

```text
idea/outlined 或缺少章节 brief -> planner_node -> planned
planned -> screenwriter_node -> scripted
scripted -> author_node -> drafted
drafted -> polisher_node -> polished
polished/review -> editor_node -> reviewed 或 revision
review -> editor_node -> reviewed 或 revision
reviewed -> publisher_node -> published
revision -> revision_router -> author_node 或 polisher_node
blocking -> human_review
```

注意：实际实现时可以调整节点命名，但状态流转不得改变。

## 硬校验

v1 最少实现：

- 字数范围检查。
- 禁用词 / 死刑红线检查。
- JSON 输出 schema 校验。
- 章节状态前置检查。
- Polisher `fact_change_risk` 检查。

## 验收测试

必须有集成测试覆盖：

- `planned -> published` 完整成功路径。
- Editor 退回到 Author。
- Editor 退回到 Polisher。
- 连续退回触发 `blocking`。
- Agent 输出 schema 不合法时不写数据库。
- 当前章节状态不匹配时拒绝写入。

## 实现顺序

1. 数据库连接、Repository、状态枚举、migration。
2. Pydantic schema。
3. 假 LLM / stub Agent。
4. LangGraph 主流程。
5. 集成测试跑通。
6. 接入真实 OpenAI-compatible Provider。
7. 补上下文构建和硬校验。

## 禁止事项

- 禁止在 Agent 内直接拼接任意 SQL 写生产表，必须走 Repository。
- 禁止 Agent 自行新增章节状态。
- 禁止 Polisher 改剧情事实后仍声明 `fact_change_risk=none`。
- 禁止 Editor 直接修改正文。
- 禁止 Author 创建伏笔、角色或世界观规则。
- 禁止把多 Provider、插件热加载、Web UI 放进 v1 阻塞主流程。
