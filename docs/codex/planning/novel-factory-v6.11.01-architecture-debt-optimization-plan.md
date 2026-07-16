# Novelos v6.11.01 架构债务优化规划

> **版本**: v6.11.01
> **主题**: 架构债务优化 — 双路径收敛、配置统一、上下文兜底轻量化、连接/查询优化、死代码清理
> **状态**: Planned
> **依赖前提**: v6.10.20 异常统一框架已 shipped；v6.11.0 为独立研究课题（按季度 OKR 管理，不阻塞本版本）
> **预估工期**: 6–10 周（按 P0→P3 分阶段）
> **风险等级**: 中（主要风险来自废弃 Dispatcher 双路径的兼容性）

---

## 0. 与 v6.11.0 研究课题的关系

v6.11.0（`planning/novel-factory-v6.11.0-architecture-refactor-plan.md`）是一项**长期技术研究课题**：原子工具 + 依赖注入 + 统一异常（LangGraph 保留），全面实施需 12–18 个月且以原型验证为前置门槛，**不在正式发布路线内**。

本版本 v6.11.01 与 v6.11.0 **互补而非重叠**：

- v6.11.01 做的是**低风险、可立即落地的"债务收敛"**——消灭已证实的重复与浪费，不改变核心架构范式（LangGraph 保留，与 v6.11.0 一致）。
- v6.11.0 探索的是**更深层的架构重构**（原子工具/DI），在本版本完成收敛后，其原型验证可在更干净的基础上进行。

本版本**不引入**原子工具抽象与 DI 容器；这些留给 v6.11.0 课题决策。

---

## 1. 现状分析

基于全仓代码实地核查（非推测），当前架构债务集中在"演进期并行路径"与"重复实现"上。

### 1.1 规模度量

| 指标 | 数值 |
|------|------|
| Python 总行数 | 98,638 行 / 305 文件 |
| 最大单文件 | `api/routes/genesis.py` 3587 行、`production.py` 3149、`agents/editor/__init__.py` 2526 |
| TODO/FIXME | 仅 2 处（技术债藏于结构而非显式标记） |
| `except ...: pass` 吞异常 | 100 处（健壮性隐患集中点） |

### 1.2 高严重度（架构/正确性风险）

**H1. LangGraph 与 Dispatcher 双路径并存，核心逻辑重复实现**

- LangGraph 入口：`workflow/runner.py:512` `run_with_graph()`；节点 `workflow/nodes/__init__.py:233-1130`
- Dispatcher 入口：`dispatch/chapter.py:248` `_run_agent()`；CLI 的 `demo`/`batch`/`revision` 仍走此路径（`cli_app/commands/demo.py:162`）
- `workflow/nodes/helpers.py:808` 注释自承 `_run_agent_node()` "Equivalent to dispatch/chapter.py ... _run_agent()"
- 后果：任何 agent 行为变更（超时、token 预算、重试、错误映射）需两处同步改，超时/重试语义不完全一致，潜藏行为漂移。

**H2. `__init__.py` 与 `helpers.py` 职责交错**

- 两文件顶部 docstring 逐字相同（`helpers.py:1-6` vs `__init__.py:1-6`）
- `__init__.py:50-78` 又从 helpers 反向 import 30+ 符号，形成"定义-再导入"循环结构。

**H3. 配置加载分散、`.env` 加载与 `db_path` 覆盖语义在两个 loader 间不一致**

- `config/settings.py:177-186` `load_settings()` 直接用 `os.getenv`，**不加载 `.env`**；其中 `db_path` 用 `setdefault`（仅当未设时取 env，行 178），而 `llm.api_key/base_url` 用无条件赋值（行 181/184）。
- `config/loader.py:118-138` `load_settings_with_cli()` 经 `env_getter` **加载 `.env`**（OS env > .env > 默认）；`db_path` 用无条件覆盖（行 119），`llm.api_key/base_url` 同样无条件（行 122/125）。
- 真正分歧收窄为两点：①是否加载 `.env`；②`db_path` 的覆盖语义（setdefault vs 无条件）。两者并存导致配置真相源不唯一，与文档"CLI > Env > .env > YAML > 默认"描述不完全吻合。

### 1.3 中严重度（性能 / 重复 / 健壮性）

**M1. 兜底 audit 构建仍做全量上下文（轻量化机会）**

- `agent_runtime/context_builder.py`；`_save_memory_context_audit_if_missing`（`helpers.py:361`）在 Planner 被跳过（预生成指令直入 Screenwriter）时兜底落 `memory_context_audit`：它先查 artifact 是否已存在（`helpers.py:382-391`），仅当 missing 时调用 `AgentContextBuilder(repo).build_for_planner(...)`（`helpers.py:395`）做一次**全量**上下文构建，仅用于生成 audit。
- 经核实**并非"重复构建两次"**：正常 Planner 路径由 Planner agent 落 audit，本兜底只在 Planner 跳过时触发单次构建；`planner_node`（`nodes/__init__.py:233`）本身不调用 `AgentContextBuilder`。
- 优化空间：兜底路径仅为落 audit 却付出全量 `build_for_planner` 成本，可评估能否降级为轻量摘要，避免无 Planner 时的额外延迟。

**M2. SQLite 每次 `_conn()` 新建连接，无连接池**

- `db/connection.py:63` `get_connection()` 每次 `sqlite3.connect(...)` 重建
- `helpers.py:381,721` 直接调用私有 `repo._conn()` 并 `close()`，绕过 Repository 封装（`repository.py:3` 强调 "Agents must NOT write raw SQL" 却内部直写）。

**M3. N+1 逐章查询**

- `workflow/nodes/__init__.py:1594-1602` `rhythm_budget_preflight_node` 对前 10 章循环 `repo.get_chapter()`，应改为一次批量查询。

**M4. 重复的 JSON 解析分支**

- `workflow/nodes/__init__.py:565-584` `_check_core_loop_compliance` 中 `row` 存在/不存在两分支重复 `get_creative_contract` + `json.loads`，可抽取一次加载复用。

**M5. 测试以 stub 为主，真实 LLM 容错路径覆盖薄弱**

- `tests/test_agents.py:3` 明说 `StubLLMProvider`，全文 120+ 处；`stub_provider.py:447-482` 返回硬编码内容
- 真实容错逻辑（`openai_compatible.py` 的 retry/fallback `:502/:957`、截断检测 `:841`、空流式 fallback `:899`）在 CI 缺乏稳定覆盖。

### 1.4 低严重度（整洁度 / 死代码）

**L1. Retired/legacy 代码仍占维护成本**

- `agents/continuity_checker.py:53` 独立 agent，已被 `quality/continuity_gate.py` 取代
- `agents/guard_example.py` 示例模板混入生产 `agents/` 目录
- `dispatch/serial.py`、`batch.py`、`queue.py`、`sidecar.py` legacy 调度模块与 `workflow/` 并存
- `scout`/`architect`/`secretary` 在 DB migration/schema 留痕但已无 agent 实现类（半死代码）

**L2. CLI 与 API 重复构建 `domain_result`**

- `cli_app/commands/core.py:219-229` `_build_cli_domain_result()` 注释 "Mirrors ... api/routes/run.py"，与 `run.py:938` 镜像，字段映射易漂移。

---

## 2. 核心策略

1. **收敛而非重写**：以 LangGraph 为唯一生产路径，冻结 Dispatcher；不引入原子工具/DI（留给 v6.11.0 课题）。
2. **单一真相源**：配置加载统一为 `loader.load_settings_with_cli()`，删除 `settings.load_settings()` 重复实现，统一 `.env` 加载与 `db_path` 覆盖语义。
3. **复用而非新增**：DB 连接、批量查询以"一次构建/复用"取代重复调用；兜底 audit 构建按需轻量化。
4. **封装而非绕过**：私有 `_conn()` 收口，Repository mixin 不再直写 raw SQL。
5. **渐进清理**：retired agent、legacy dispatch、半死 schema 标记为 deprecated 后按需删除，不影响现有行为。
6. **测试补强**：真实 LLM 容错路径以可稳定的 mock-transport 覆盖 retry/fallback/截断，降低回归风险。

---

## 3. 实施步骤（按优先级分阶）

### P0 — 统一章节生产入口为 LangGraph

- 在 `api/routes/run.py` 与 CLI `run-chapter` 统一调用 `run_with_graph()`。
- 将 CLI `demo`/`batch`/`revision`（`cli_app/commands/demo.py:162` 等）从 `dispatch.Dispatcher` 切到 LangGraph runner；保留 `dispatch/` 作为 `legacy/` 兼容层，标记 `@deprecated`，移除其活跃调用。
- 删除 `workflow/nodes/helpers.py:808` 中"equivalent to dispatch"的重复 `_run_agent_node()`，或将其收敛为 LangGraph node 的内部共享 helper。
- 验证：同一章节在 API 与 CLI 路径下超时/重试语义一致（补一个双路径行为一致性测试）。

### P1 — 配置加载合并

- 删除 `config/settings.py:161` `load_settings()`（env 覆盖区段 177-186）；全仓调用点改为 `loader.load_settings_with_cli()`（env 覆盖区段 118-138）。
- 统一 env 覆盖语义为"无条件覆盖 + 加载 `.env`"（与文档"CLI > Env > .env > YAML > 默认"一致），并补充 loader 单测固化该语义（覆盖 `db_path`、`llm.api_key/base_url`、`.env` 优先级）。
- 清理 `env_loader.py` 与 `loader.py` 的职责重叠，使 env 加载（env_loader）、YAML 合并（loader）、pydantic 模型（settings）边界清晰。

### P1 — 兜底 audit 构建轻量化（评估项）

- 评估 `_save_memory_context_audit_if_missing`（`helpers.py:361`）在 Planner 跳过路径下的全量 `build_for_planner`（`helpers.py:395`）能否降级为轻量摘要构建，避免仅为落 `memory_context_audit` 而付出完整上下文成本。
- 注意：本项**非"消除重复构建"**（经核实正常路径由 Planner agent 落 audit，兜底仅单次触发）；若评估显示收益有限则降级或移出本版本。
- 不改动各 agent 的输入契约。

### P2 — SQLite 连接复用与批量查询

- `db/connection.py:63` 引入短生命周期连接复用（如按线程/请求的轻量池或上下文管理器），避免每次 `_conn()` 重建。
- 私有化 `repo._conn()`，mixin 停止直接 `_conn().execute`；通过 Repository 公开方法访问。
- `workflow/nodes/__init__.py:1594-1602` `rhythm_budget_preflight_node` 改为一次批量 `get_chapters(range)` 查询，消除 N+1。
- `_check_core_loop_compliance`（`__init__.py:565-584`）抽取一次 `get_creative_contract` + `json.loads` 复用。

### P2 — 真实 LLM 容错测试补强

- 为 `openai_compatible.py` 的 retry/fallback（`:502/:957`）、截断检测（`:841`）、空流式 fallback（`:899`）增加以可控 transport mock 的稳定单测，覆盖 finish_reason=length、SDK→HTTP 切换、空响应。

### P3 — 死代码清理与共享构建器

- `agents/continuity_checker.py`、`agents/guard_example.py` 标记 `@deprecated`；`guard_example.py` 移出生产 `agents/` 至示例目录。
- `dispatch/serial.py`、`batch.py`、`queue.py`、`sidecar.py` 归入 `legacy/`，移除活跃调用后保留或删除。
- 清理 `scout`/`architect`/`secretary` 在 migration/schema 中的半死痕迹（仅注释/孤立表，不破坏现有迁移链）。
- 抽取 CLI/API 共有 `domain_result` 构建器（`cli_app/commands/core.py:219` 与 `api/routes/run.py:938` 共享），消除字段映射漂移。

---

## 4. 验收标准

| 项目 | 验收条件 |
|------|----------|
| P0 双路径收敛 | CLI `run-chapter`/`demo`/`batch`/`revision` 均经 LangGraph；`dispatch/` 无活跃调用；双路径行为一致性测试通过 |
| P1 配置统一 | 全仓无 `settings.load_settings()` 调用；`.env` 加载与 `db_path`/`llm` 无条件覆盖单测通过 |
| P1 兜底 audit 轻量化 | 评估结论记录在案；若实施则兜底路径不再做全量 `build_for_planner`，audit 内容等价 |
| P2 连接/查询 | 引入连接复用；`_conn()` 私有化；`rhythm_budget_preflight` 单批量查询；N+1 消除测试通过 |
| P2 容错测试 | `openai_compatible.py` retry/fallback/截断/空流均有稳定单测 |
| P3 清理 | deprecated 标记到位；`domain_result` 共享构建器；无新增重复实现 |
| 回归 | 全量 pytest + 前端 typecheck/lint/build/vitest 通过（分层验证 `scripts/verify.py full`） |

---

## 5. 风险与回滚

- **P0 兼容性风险（中）**：废弃 Dispatcher 可能影响历史 CLI 脚本。缓解：保留 `legacy/` 兼容层与 `--use-legacy-dispatcher` 开关一个版本，下个版本再移除；双路径一致性测试先行。
- **P2 连接复用风险（低）**：SQLite WAL/连接状态需谨慎。缓解：先以上下文管理器封装，再逐步替换直连点；保留 `--no-pool` 回退。
- **P1 兜底轻量化风险（低）**：改动 audit 内容可能影响 run detail 展示。缓解：保持 audit 字段结构不变，仅替换构建来源；补 audit 等价性测试。
- **回滚**：每阶段独立提交；P0/P1 任一异常可单独 revert 而不影响其他阶段。

---

## 6. 不在本版本范围

- 原子工具抽象、依赖注入容器（v6.11.0 研究课题）
- 大规模单文件拆分（v6.10.17 已启动，本版本仅顺势清理重复，不主动拆 3500 行文件）
- 全新功能特性

---

## 7. 关联文档

- 研究课题：`planning/novel-factory-v6.11.0-architecture-refactor-plan.md`
- 前置版本：`planning/novel-factory-v6.10.20-exception-unification-plan.md`（异常统一，已 shipped）
- 版本索引：`planning/novel-factory-version-planning-index.md`
