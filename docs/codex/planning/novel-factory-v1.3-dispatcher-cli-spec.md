# v1.3 Dispatcher 编排与 CLI 可运行化开发规范

## 目标

v1.3 的目标是让已经通过 v1.2 质量验收的章节生产链路真正“可运行、可恢复、可观察、可操作”。

v1.2 已经解决质量与一致性问题：ContextBuilder、death penalty、state/plot verifier、learned_patterns、best_practices、退回分类和 Polisher 事实锁定。v1.3 不继续扩展质量规则，而是把现有能力收束到一个稳定的调度入口和命令行产品形态。

本轮重点：

- Dispatcher 调度器落地。
- CLI 命令从 `python -m novel_factory.cli` 升级为 `novelos`。
- 单章完整流水线可由命令触发。
- 任务发现、状态推进、返修、熔断、人工介入入口可操作。
- workflow_runs / task_status / agent_artifacts 可通过 CLI 查询。
- 本地 SQLite 运行体验稳定。

## 当前前置条件

必须基于以下状态开发：

- v1 MVP 已通过。
- v1 review 返工闸门已通过。
- v1.1 工程稳定性已通过。
- v1.2 质量与一致性增强已通过。
- 当前全量测试应为 `206/206` 或更多。
- 不允许破坏 v1 / v1r / v1.1 / v1.2 任何验收测试。

## 版本定位

v1.3 是后端可运行化版本，不是 Web UI 版本。

本版本完成后，后端应能通过 CLI 独立运行：

```bash
novelos init-db
novelos run-chapter --project-id demo --chapter 1
novelos status --project-id demo --chapter 1
novelos runs --project-id demo
```

Web UI、Web API、Scout、Architect、Secretary、ContinuityChecker、多 Provider fallback 仍然延后。

## 本轮允许实现

允许修改：

- `novel_factory/cli.py`
- `novel_factory/workflow/graph.py`
- `novel_factory/workflow/nodes.py`
- `novel_factory/workflow/conditions.py`
- `novel_factory/db/repository.py`
- `novel_factory/db/connection.py`
- `novel_factory/config/settings.py`
- `novel_factory/config/agents.yaml`
- `novel_factory/models/state.py`
- `novel_factory/agents/*`
- `tests/*`
- packaging 相关文件，例如 `pyproject.toml`

允许新增：

- `novel_factory/dispatcher.py`
- `novel_factory/runtime.py`
- `novel_factory/cli/` 包目录，若开发 Agent 选择拆分 CLI。
- `novel_factory/models/runtime.py`
- `tests/test_dispatcher.py`
- `tests/test_cli.py`
- `tests/test_runtime.py`
- `pyproject.toml`

## 本轮禁止实现

- 不新增 Web UI。
- 不新增 Web API / FastAPI 服务。
- 不新增 Scout / Architect / Secretary。
- 不新增 ContinuityChecker 独立 Agent。
- 不新增多 Provider fallback。
- 不新增 Skill 热加载。
- 不引入 Celery / Redis / Kafka 等外部队列。
- 不引入 PostgreSQL，继续使用 SQLite。
- 不重写为 SQLModel 全量 ORM。
- 不改变主链路核心顺序：`Planner -> Screenwriter -> Author -> Polisher -> Editor`。
- 不绕过现有 Agent 前置检查、质量校验、乐观锁和补偿逻辑。

## 技术栈选型

### 必选

| 模块 | 选型 | 说明 |
| --- | --- | --- |
| 编排 | LangGraph | 保持状态图模型，负责节点和条件边 |
| CLI | Typer 优先，argparse 可接受 | Typer 体验更好；如避免新增依赖可用 argparse |
| 数据库 | SQLite | 延续 v1-v1.2 |
| 配置 | YAML + 环境变量 | 延续 `agents.yaml` / `llm.yaml` / settings |
| 测试 | pytest | 延续现有测试体系 |
| 包入口 | `pyproject.toml` console scripts | 提供 `novelos` 命令 |

### 不选

| 方案 | 不选原因 |
| --- | --- |
| 纯 LangChain AgentExecutor | 当前系统是长流程状态机，不是单轮工具调用 |
| Celery / Redis 队列 | v1.3 先做单机本地可运行，避免部署复杂化 |
| FastAPI | Web/API 放到后续版本，不抢 v1.3 目标 |
| PostgreSQL | 当前 Repository 和测试都基于 SQLite，先稳住本地闭环 |

## 必修项

### D1：`novelos` CLI 入口

要求：

- 新增标准 Python packaging 配置。
- 安装为可执行命令 `novelos`。
- 不再要求用户输入 `python -m novel_factory.cli`。
- 保留 `python -m novel_factory.cli` 兼容入口，不得破坏旧测试。

建议 `pyproject.toml`：

```toml
[project.scripts]
novelos = "novel_factory.cli:main"
```

CLI 至少支持：

```bash
novelos init-db
novelos run-chapter --project-id demo --chapter 1
novelos status --project-id demo --chapter 1
novelos runs --project-id demo
novelos artifacts --project-id demo --chapter 1
novelos human-resume --project-id demo --chapter 1 --status drafted
```

验收：

- 测试覆盖 `novelos init-db` 可执行。
- 测试覆盖 `novelos --help` 可执行。
- 测试覆盖 `python -m novel_factory.cli --help` 仍可执行。
- 不依赖当前工作目录才能找到配置和 migrations。

### D2：Dispatcher 调度器

要求：

- 新增 Dispatcher 作为运行时调度入口。
- Dispatcher 只负责任务发现、路由、健康检查、重试、熔断、人工介入判断。
- Dispatcher 不直接生成正文，不改写 Agent 输出，不绕过 Agent。
- Dispatcher 必须以 DB 当前状态为准，不信任传入 state。

建议接口：

```python
class Dispatcher:
    def run_chapter(self, project_id: str, chapter_number: int, max_steps: int = 20) -> dict:
        ...

    def discover_next(self, project_id: str | None = None) -> list[dict]:
        ...

    def resume_blocked(self, project_id: str, chapter_number: int, status: str) -> dict:
        ...
```

验收：

- DB 中章节不存在时，Dispatcher 进入人工处理，不调用写入 Agent。
- 状态为 `planned` 时调度 Screenwriter。
- 状态为 `scripted` 时调度 Author。
- 状态为 `drafted` 时调度 Polisher。
- 状态为 `polished` 时调度 Editor。
- 状态为 `reviewed` 时可发布或归档。
- 状态为 `revision` 时按 `revision_target` 路由。
- 状态为 `blocking` 时停止自动调度。

### D3：单章运行闭环

要求：

- `novelos run-chapter --project-id X --chapter N` 能驱动一个章节从当前状态向后运行。
- 默认最多执行 `max_steps=20`，防止无限循环。
- 每一步都写入 `workflow_runs` 或等价追踪记录。
- 返回最终状态、执行节点列表、错误信息、是否需要人工介入。

验收：

- 从 `planned` 可以跑到 `reviewed` 或 `published`。
- 审核退回可以进入 `revision` 并继续返修。
- 连续返修超过阈值进入 `blocking`。
- 任意节点返回 error 时停止并标记 `requires_human=True` 或 `blocking`。
- 重跑已完成章节不会重复写入重复 artifact/version。

### D4：CLI 查询能力

要求：

- `status` 显示项目、章节、当前状态、最近一次 workflow run、最近错误。
- `runs` 显示 workflow run 列表。
- `artifacts` 显示该章节各 Agent 产物摘要。
- 输出格式默认适合人读。
- 可选支持 `--json`，方便后续脚本接入。

验收：

- 测试覆盖正常章节状态查询。
- 测试覆盖不存在项目/章节时返回非 0 或清晰错误。
- 测试覆盖 `--json` 输出可被 `json.loads` 解析。

### D5：人工介入恢复

要求：

- `novelos human-resume` 允许把 `blocking` 或人工修复后的章节恢复到合法状态。
- 必须校验目标状态是否合法。
- 必须记录人工恢复原因或操作日志。
- 不允许从任意状态跳到 `published`。

建议允许目标：

```text
planned
scripted
drafted
polished
revision
```

验收：

- `blocking -> drafted` 可恢复。
- `blocking -> polished` 可恢复。
- `blocking -> published` 必须失败。
- 人工恢复后再次 `run-chapter` 可以继续调度。

### D6：运行时配置收束

要求：

- CLI 能明确选择 DB 路径。
- CLI 能明确选择 LLM 配置。
- 默认配置能在仓库内测试环境直接运行。
- 不把真实 API key 写入代码或测试。

建议参数：

```bash
novelos --db-path .novelos/novel.db init-db
novelos --config novel_factory/config/llm.yaml run-chapter --project-id demo --chapter 1
```

验收：

- 测试覆盖自定义 DB 路径。
- 测试覆盖缺少 LLM key 时给出清晰错误或使用测试 fake provider。
- 测试不访问真实网络。

## 状态路由规则

v1.3 必须显式固化状态路由表：

| 当前状态 | 下一步 |
| --- | --- |
| `planned` | `screenwriter` |
| `scripted` | `author` |
| `drafted` | `polisher` |
| `polished` | `editor` |
| `reviewed` | `publisher` 或结束 |
| `published` | 结束 |
| `revision` + `revision_target=author` | `author` |
| `revision` + `revision_target=polisher` | `polisher` |
| `revision` + `revision_target=planner` | 人工处理或 planner |
| `blocking` | `human_review` |
| `requires_human=True` | `human_review` |
| `error` 非空 | `human_review` |

安全要求：

- `requires_human` / `error` 永远优先于 `chapter_status`。
- DB 状态永远优先于内存 state。
- 缺失章节永远不得进入写入 Agent。

## 数据库与迁移

v1.3 原则上不强制新增 migration。

如确实需要新增字段，必须满足：

- migration 可重复执行。
- 兼容旧库已手动添加字段但无 tracking 记录的情况。
- 有 schema 检测测试。
- 不破坏 001/002/003。

可能需要的最小字段：

- `workflow_runs.finished_at`
- `workflow_runs.error`
- `workflow_runs.requires_human`
- `workflow_runs.steps_json`

如果现有表已有等价字段，优先复用，不新增。

## 测试要求

必须新增或补充：

- `tests/test_dispatcher.py`
- `tests/test_cli.py`
- `tests/test_runtime.py`

最低测试覆盖：

- CLI help。
- `novelos init-db`。
- 自定义 DB path。
- Dispatcher 路由表。
- 缺失章节不进入 Agent。
- planned 到 scripted。
- scripted 到 drafted。
- drafted 到 polished。
- polished 到 reviewed / revision。
- revision 按目标路由。
- blocking 停止调度。
- max_steps 防无限循环。
- workflow_runs 记录步骤。
- artifacts 查询。
- status JSON 输出。
- human-resume 合法状态。
- human-resume 禁止 published。
- 旧 `python -m novel_factory.cli` 兼容。

全量测试必须通过，并且测试数应大于 v1.2 的 `206`。

## 验收标准

v1.3 通过必须同时满足：

- 全量测试通过。
- `novelos` 命令可用。
- 后端无需 Web UI 即可完成单章运行、查询、恢复。
- Dispatcher 不绕过 DB 状态和 Agent 前置检查。
- 所有异常路径不会留下“状态推进但产物缺失”的半完成数据。
- 不引入 v2 范围能力。

## 给开发 Agent 的执行顺序

建议按以下顺序开发，避免同时改太多层：

1. 添加 `pyproject.toml` 和 `novelos` console script。
2. 梳理现有 CLI，保留兼容入口。
3. 新增 Dispatcher，只做路由与单步调度。
4. 实现 `run_chapter(max_steps)`。
5. 接入 CLI `run-chapter/status/runs/artifacts/human-resume`。
6. 补齐 workflow run 记录。
7. 补全测试。
8. 全量测试。

## 非目标

以下内容不要在 v1.3 做：

- 浏览器管理界面。
- 多项目 dashboard。
- 模型成本统计。
- 多模型 fallback。
- 自动市场侦察。
- 自动规则演进。
- 长篇跨章一致性 Agent。
- 云端部署。

