# Novelos v6.11.02 发布完整性与运行时收敛优化计划

> **版本**: v6.11.02
> **主题**: 发布基线修复、章节生产单路径收敛、持久化边界试点、模块与前端性能治理
> **状态**: In Progress — Wave 0 Complete
> **规划日期**: 2026-08-13
> **依赖前提**: v6.11.01 Architecture Debt Optimization 已完成 P0/P1/P3 与部分 P2
> **建议工期**: 4–6 周，按 Wave 0 → Wave 3 顺序推进
> **风险等级**: 中；最高风险集中在 legacy Dispatcher 兼容路径退出

---

## 0. 规划结论

v6.11.02 不继续扩展创作功能，优先把 v6.11.01 之后暴露出的“发布事实与代码事实不一致”收口，并把架构优化从“主路径已收敛”推进到“生产章节执行只有一个实现”。

本版本采用四个可独立验收的执行波次：

| Wave | 主题 | 是否阻塞后续 | 主要结果 |
| --- | --- | --- | --- |
| 0 | 发布完整性恢复 | 是 | 版本源一致，release 基线重新全绿 |
| 1 | 章节生产单路径收敛 | 是 | 所有生产章节执行统一进入 LangGraph |
| 2 | 持久化边界试点 | 否 | 选定高收益读路径采用 Store，减少直接 `_conn()` |
| 3 | 模块与前端性能治理 | 否 | 拆出一个后端垂直边界，建立前端 chunk 预算 |

Wave 0、Wave 1 是 v6.11.02 的发布必需项。Wave 2、Wave 3 必须满足各自进入门禁后才能纳入同一版本；若验证成本或回归风险超出预算，应顺延至 v6.11.03，不阻塞核心收敛版本发布。

---

## 1. 现状证据

以下结论来自 2026-08-13 对 `release/v6.11.01` 的实时代码与测试核查，而不是复用旧 `.planning/codebase/CONCERNS.md`。

### 1.1 已确认完成

- Python runtime 已发布为 `novel_factory/version.py::__version__ == "6.11.01"`。
- API `run/chapter`、CLI `run-chapter`、production auto-run 主入口已调用 `workflow.runner.run_with_graph()`。
- `config.loader.load_settings_with_cli()` 已成为当前配置加载入口，旧 `load_settings()` 已移除。
- `build_chapter_domain_result()` 已抽到 `novel_factory/api/contracts.py`，CLI/API 共用。
- LLM retry、fallback、截断与空流响应已经有稳定 mock transport 回归测试。
- 前端 `typecheck`、`lint`、production build、Vitest 可通过；Vitest 当前为 344/344。

### 1.2 当前阻断问题

#### B0-1：发布版本源漂移

当前版本值：

| 位置 | 当前值 | 目标值 |
| --- | --- | --- |
| `novel_factory/version.py` | `6.11.01` | v6.11.02 发布时统一更新 |
| `frontend/package.json` | `6.10.20` | 与 runtime 一致 |
| `frontend/package-lock.json` | `6.10.20` | 与 runtime 一致 |
| `desktop/package.json` | `6.10.20` | 与 runtime 一致 |
| `desktop/package-lock.json` | `6.10.20` | 与 runtime 一致 |
| `pyproject.toml` | `1.3.0` | `6.11.02`，与产品 runtime 统一 |

定向执行：

```bash
python3 -m pytest \
  tests/test_version_alignment.py \
  tests/test_v6109_core_loop_evidence_governance.py \
  -q -n 0
```

结果为 5 failed / 59 passed。失败均来自 package、lockfile 或历史测试中的版本硬编码漂移。

#### B0-2：发布说明与验证事实不一致

`CHANGELOG.md` 将 v6.11.01 标记为 Complete，并记录 full pytest / frontend 全绿；但 release commit 只更新了 `novel_factory/version.py` 与 changelog，没有同步 package、lockfile 和历史版本断言。发布成功不能只由 changelog 声明，必须由可重复执行的 release gate 证明。

#### B1-1：legacy chapter loop 仍可被生产调用

`dispatch/chapter.py::ChapterDispatchMixin.run_chapter()` 当前行为为：

- Dispatcher 带 `settings`：委托 `run_with_graph()`；
- Dispatcher 不带 `settings`：执行旧 while-loop 与 `_run_agent()` 路径。

CLI 的 batch、serial、review、demo 等命令仍有多处直接 `Dispatcher(repo, stub_llm, ...)`。其中会调用 `run_chapter()` 的链路可以触发旧实现。现状应描述为“主入口收敛”，不能描述为“章节生产已经物理单路径”。

#### B2-1：Store 层存在但没有生产采用

`novel_factory/stores/` 已有 8 个聚合 Store，但生产代码没有实际调用；同时代码中仍有约 28 处直接 `repo._conn()`。Store 目前是待迁移架构，而不是已生效边界。

#### B3-1：大模块与前端 bundle 仍有集中风险

关键文件规模：

| 文件 | 约行数 |
| --- | ---: |
| `novel_factory/api/routes/production.py` | 3,149 |
| `novel_factory/agents/editor/__init__.py` | 2,526 |
| `novel_factory/agents/author/__init__.py` | 2,285 |
| `novel_factory/workflow/nodes/__init__.py` | 1,686 |

前端 production build 主 JS chunk 约 824 KB，超过 Vite 500 KB 默认提示阈值。当前没有可执行 bundle budget，因此体积可能继续无感增长。

---

## 2. 目标与需求

### 2.1 版本目标

1. **恢复发布可信度**：任何“版本完成”声明都必须由自动化 release gate 支撑。
2. **消除章节执行双实现**：生产代码不得通过 settings 缺失隐式进入 legacy loop。
3. **建立可验证的持久化边界**：Store 只在有明确调用方和查询收益时采用，避免继续增加空抽象。
4. **降低高频改动半径**：先拆清晰、可测试的垂直边界，不追求一次性重写巨型模块。
5. **建立性能预算**：前端 bundle 和关键数据库读路径具备可回归的阈值。

### 2.2 需求编号

| ID | 需求 | 优先级 |
| --- | --- | --- |
| OPT-01 | runtime、API、frontend、desktop、lockfile 版本一致 | P0 |
| OPT-02 | 明确 `pyproject.toml` 包版本策略并自动验证 | P0 |
| OPT-03 | release gate 在版本漂移时失败，并覆盖 build/test | P0 |
| OPT-04 | 所有生产章节执行进入 `run_with_graph()` | P0 |
| OPT-05 | legacy chapter loop 不再由 settings 是否存在隐式选择 | P0 |
| OPT-06 | batch/demo/revision 章节路径具有一致性回归测试 | P0 |
| OPT-07 | 至少两个高收益读场景采用 Store 或明确拒绝采用的 ADR | P1 |
| OPT-08 | 生产模块直接 `repo._conn()` 数量可度量下降 | P1 |
| OPT-09 | 至少一个巨型后端模块完成垂直边界拆分 | P1 |
| OPT-10 | 前端建立 chunk 分割与 bundle budget | P1 |

### 2.3 非目标

- 不引入 v6.11.0 研究课题中的 DI 容器或全面原子工具重构。
- 不修改 LangGraph 的章节状态机和质量门禁业务语义。
- 不做全量 Repository 重写，不在本版本引入 ORM。
- 不删除历史 migration，不改写已发布数据库迁移链。
- 不新增创作功能或重做 UI 视觉设计。
- 不以总 LOC 下降作为成功指标；边界清晰和行为等价优先。

---

## 3. 目标架构约束

### 3.1 章节执行唯一入口

```text
CLI / API / Auto-run / Batch / Demo
                 │
                 ▼
        ChapterRunService / runner facade
                 │
                 ▼
          run_with_graph()
                 │
                 ▼
       LangGraph + checkpoint + events
```

约束：

- `run_with_graph()` 仍是章节生产事实源。
- Dispatcher 可以保留 batch、queue、serial、review 等协调能力，但不得保留第二套 Agent chapter loop。
- settings、repo、llm_mode 必须在组合根显式构造；不得通过 `settings is None` 改变业务执行引擎。
- legacy CLI 若确需保留，必须使用显式命名和独立测试，不能静默回退。

### 3.2 持久化边界

```text
API / Workflow / Agent
       │
       ├── 单领域 CRUD ──► Repository facade / domain mixin
       │
       └── 跨领域只读聚合 ──► Store ──► Repository facade
```

- Repository 继续承担 SQL 与写事务。
- Store 只承担跨领域只读聚合，不复制写逻辑。
- `_conn()` 仍是 Repository 内部 escape hatch；新业务代码不得新增直接调用。
- 每次迁移 Store 必须有查询次数或调用复杂度对比，不能只做机械包装。

---

## 4. 执行计划

## Wave 0 — 发布完整性恢复（必须完成）

### Task 0.1：定义并实现版本策略

**修改范围**：

- `novel_factory/version.py`
- `frontend/package.json`
- `frontend/package-lock.json`
- `desktop/package.json`
- `desktop/package-lock.json`
- `pyproject.toml`
- `tests/test_version_alignment.py`
- `tests/test_v6109_core_loop_evidence_governance.py`

**实施要求**：

1. 保持 `novel_factory/version.py` 为产品 runtime 唯一真相源。
2. frontend、desktop 及两个 lockfile 必须与 runtime 完全一致。
3. 删除业务测试中的具体版本硬编码；此类测试只验证 `get_version()`、API、package 与 runtime 一致。
4. 将 `pyproject.toml` 统一到 `6.11.02`。本项目当前以同一仓库交付 Python sidecar、CLI、React 和 Electron，不再维护未经文档化的第二套 package 版本。
5. 新增或更新 `docs/codex/release/version-policy.md`，声明 runtime 是唯一真相源，Python package、frontend、desktop 和 lockfile 必须与其相等。

**验收标准**：

```bash
python3 -m pytest tests/test_version_alignment.py -q -n 0
```

- 命令退出码为 0。
- `rg '6\.10\.20' frontend/package*.json desktop/package*.json tests/test_v6109_core_loop_evidence_governance.py` 无旧发布版本残留。
- `GET /api/health`、FastAPI metadata、frontend package、desktop package 与 runtime 一致。

### Task 0.2：建立 release preflight

**建议新增**：

- `scripts/release_preflight.py`
- `tests/test_release_preflight.py`

**修改**：

- `scripts/verify.py`
- `docs/codex/release/` 中现有 release checklist 或 version policy

**实施要求**：

新增 `python3 scripts/release_preflight.py`，至少检查：

- 工作树状态只报告、不自动修改；
- 所有版本源一致；
- changelog 存在目标版本条目；
- package lock root version 与 package version 一致；
- frontend/desktop 必需 manifest 存在；
- 输出结构化逐项 PASS/FAIL，并以非零退出码阻断发布。

在 `scripts/verify.py` 增加 `release` 层级，执行顺序固定为：

1. release preflight；
2. 全量 pytest；
3. frontend typecheck / lint / build / vitest；
4. desktop typecheck / build；
5. release smoke。

**验收标准**：

- 人为将任一临时 fixture 的版本改错时，preflight 必须以非零退出。
- `python3 scripts/verify.py release` 是唯一允许写入 completion report 的发布证据命令。
- release 脚本只读检查，不写版本、不执行 git commit、不访问真实 LLM。

### Wave 0 退出门禁

- [x] OPT-01、OPT-02、OPT-03 全部通过。
- [x] 定向版本测试全绿。
- [x] 完整 release gate 至少成功执行一次并记录总测试数、时间与环境。
- [x] 未通过 Wave 0 时，不开始 legacy runtime 删除。

执行记录（2026-08-13）：`python3 scripts/verify.py release` 通过；preflight 20/20，backend 3784 passed / 1 skipped（614.77s，4 workers），frontend 344 passed，frontend 与 desktop 构建门禁及 release smoke 均通过。受 Codex managed sandbox 限制，sidecar smoke 使用显式的 in-process stub fallback；对外分发前仍需在允许本地端口绑定的 packaging 环境验证 spawned sidecar transport。

---

## Wave 1 — 章节生产单路径收敛（必须完成）

### Task 1.1：收紧章节 Runner 依赖契约

**主要修改范围**：

- `novel_factory/workflow/runner.py`
- `novel_factory/cli_app/common.py`
- `novel_factory/api/deps.py`
- `novel_factory/dispatch/base.py`
- `novel_factory/dispatch/chapter.py`

**实施要求**：

1. 保持 `workflow.runner.run_with_graph()` 为唯一章节执行 facade，不为本次收敛新增第二个等价 service 层。
2. CLI、API、auto-run 和 Dispatcher 兼容门面全部直接或间接调用 `run_with_graph()`。
3. `ChapterDispatchMixin.run_chapter()` 仅验证 `self.settings` / `self.llm_mode` 并委托 runner，不再包含旧 while-loop。
4. 删除 `settings is None → legacy` 的隐式分支；缺失 settings 时抛出稳定的配置异常，错误信息明确包含 `Dispatcher chapter execution requires Settings`。
5. 将 `Dispatcher.run_chapter(..., max_steps=N)` 的 `N` 原样传给 `run_with_graph(..., max_steps=N)`，不能像当前委托分支一样忽略。

**验收标准**：

- `dispatch/chapter.py::run_chapter` 不包含 Agent 实例化、while-loop 或 `_run_agent()` 调用。
- 全仓生产代码调用章节生产时最终命中 `run_with_graph()`。
- 缺失 settings 的错误包含稳定错误码或明确异常类型，不静默改走另一引擎。

### Task 1.2：迁移 CLI 协调路径

**主要修改范围**：

- `novel_factory/cli_app/commands/demo.py`
- `novel_factory/cli_app/commands/batch.py`
- `novel_factory/cli_app/commands/serial.py`
- `novel_factory/cli_app/commands/review.py`
- `novel_factory/dispatch/batch.py`
- `novel_factory/dispatch/revision.py`
- 必要的 queue/serial compatibility modules

**实施要求**：

- 盘点每个 Dispatcher 调用是“协调操作”还是“章节执行”。
- 协调操作可保留 Dispatcher facade；一旦需要执行章节，必须注入统一 Chapter runner。
- 将 `_build_dispatcher()` 的所有返回分支统一携带 `settings` 与 `llm_mode`；修复 real profile 路径当前遗漏 settings 的分支。
- 直接 `Dispatcher(repo, stub_llm, ...)` 的 CLI 构造迁移到共享 builder，或显式传入完整运行依赖。
- 保持 CLI JSON envelope、退出码、stub 确定性输出与现状兼容。

**验收标准**：

```bash
rg 'Dispatcher\(repo, stub_llm|Dispatcher\(repo, llm' novel_factory/cli_app/commands
```

- 对可能触发章节执行的命令不再出现 settings-less 构造。
- demo、batch revision、queue resume/retry 等章节执行测试均断言 LangGraph runner 被调用。
- 不以删除所有 Dispatcher 为目标；只消除第二套章节生产实现。

### Task 1.3：替换双路径一致性测试

**修改范围**：

- `tests/test_v61101_dispatch_langgraph_consistency.py`
- 新增或扩展 batch/demo/revision 契约测试

**实施要求**：

- 删除“无 settings 时应进入 legacy fallback”的旧断言。
- 新测试覆盖：显式依赖成功、缺依赖 fail-closed、`max_steps` 透传、stub/real mode 透传、run result shape 不漂移。
- API、CLI、Dispatcher compatibility facade 对同一模拟 runner 返回一致的 domain result 核心字段。

### Wave 1 退出门禁

- OPT-04、OPT-05、OPT-06 全部通过。
- `dispatch/chapter.py` 旧 Agent loop 已删除或移至测试专用 fixture，不存在生产 import。
- smoke chapter、API run、CLI run-chapter、demo/batch/revision 定向测试全绿。
- 完整 pytest 通过后才允许进入 Wave 2。

---

## Wave 2 — 持久化边界试点（条件纳入）

### 进入条件

- Wave 0、Wave 1 已完成且 full pytest 恢复全绿。
- 先记录目标调用的基线查询次数；没有可测收益的场景不迁移 Store。

### Task 2.1：选定两个高收益读场景

优先候选：

1. project workspace / dashboard 聚合读取；
2. workflow timeline / run detail 聚合读取；
3. chapter context / quality summary 聚合读取。

每个候选都要记录：调用入口、当前 Repository 调用数、是否存在 N+1、对应 Store 能否复用。最终只选择两个边界清晰且可以通过测试证明收益的场景。

### Task 2.2：采用 Store 并冻结职责

**主要修改范围**：

- `novel_factory/stores/`
- 对应的 `novel_factory/api/routes/*.py`
- 对应 repository mixin 和测试

**实施要求**：

- Store 仅做只读跨领域聚合。
- 写操作仍通过 Repository。
- 不允许 Store 捕获所有异常后返回空结果；失败语义必须保留。
- 为选定场景增加查询次数断言或 spy 测试。

### Task 2.3：减少 `_conn()` escape hatch

- 对生产层 28 处直接 `repo._conn()` 分类：Repository 内部、诊断脚本、API/Agent/Workflow 业务层。
- 本版本至少迁移选定场景涉及的业务层直连。
- 增加静态卫生测试：被迁移目录不得新增 `repo._conn()`。

### Wave 2 退出门禁

- OPT-07、OPT-08 通过。
- 至少两个真实生产调用方采用 Store，或形成 ADR 明确说明 Store 不适合并提出替代边界。
- 选定场景查询次数不高于基线，响应 envelope 和字段保持兼容。

---

## Wave 3 — 模块与前端性能治理（条件纳入）

### Task 3.1：拆分一个高变更后端垂直边界

锁定拆分 `api/routes/production.py` 中 auto-run session 管理边界：start、list、detail、cancel、pause、resume、active-session、retry-step、delete、cleanup。路由可迁移到 `api/routes/production_sessions.py`，共享编排逻辑迁移到 `api/services/production_sessions.py`；`api_app.py` 继续在 `/api` 前缀下注册，外部 URL 不变。

约束：

- 路由路径、请求响应模型、错误码、SSE event schema 不变。
- 先建立 characterization tests，再移动代码。
- 拆分目标不是把大文件平均切片，而是形成单向依赖和可独立测试的服务边界。
- 原 route module 应保留清晰 composition root，不通过 `import *` 维持兼容。

### Task 3.2：建立 frontend bundle budget

**修改范围**：

- `frontend/src/App.tsx`
- `frontend/vite.config.ts`
- `frontend/package.json`
- 必要的 lazy-loading fallback 组件与测试

**实施要求**：

- 对 Settings、AgentOps、Review、Style 等非首屏页面使用 `React.lazy()` + `Suspense` 路由级拆分。
- 保证桌面 HashRouter 与浏览器 BrowserRouter 行为一致。
- 增加构建产物检查脚本；首屏 entry chunk 建议预算 ≤ 500 KB，单个 lazy chunk 建议 ≤ 350 KB。若第三方依赖使阈值不可达，必须在完成报告中记录基线、原因和后续阈值，不得只调高 warning limit。
- 不为了体积移除现有用户功能或测试。

### Wave 3 退出门禁

- OPT-09、OPT-10 通过。
- 后端拆分模块的 API/SSE characterization tests 全绿。
- frontend typecheck、lint、build、344+ Vitest 全绿。
- build 输出满足预算，或存在经评审的例外记录。

---

## 5. 测试与验证矩阵

| 层级 | 命令 | 使用时机 | 通过条件 |
| --- | --- | --- | --- |
| Release fast | `python3 scripts/release_preflight.py` | 每次版本相关改动 | 所有检查 PASS |
| Version | `python3 -m pytest tests/test_version_alignment.py -q -n 0` | Wave 0 | 0 failed |
| Runtime convergence | `python3 -m pytest tests/test_v61101_dispatch_langgraph_consistency.py -q -n 0` | Wave 1 | 新单路径契约全绿 |
| Backend impacted | `python3 -m pytest <impacted files> -q -n 0` | 每个 task | 0 failed |
| Backend full | `python3 -m pytest -q` | 每个 Wave 退出 | 全量通过 |
| Frontend | `python3 scripts/verify.py frontend` | 前端改动 | typecheck/lint/vitest 通过 |
| Frontend build | `cd frontend && npm run build` | Wave 3 | 构建成功且满足 budget |
| Desktop | `cd desktop && npm run typecheck && npm run build` | Wave 0/release | 两项通过 |
| Release full | `python3 scripts/verify.py release` | 版本关闭前 | 全部通过并记录证据 |

测试执行注意事项：

- 并行 pytest 适合作为最终基线，但失败定位应使用 `-n 0` 复现。
- Vitest 首次全量执行可能受系统负载导致 5 秒 timeout；应单文件复现后再判断是否为产品回归，不能直接扩大全局 timeout 掩盖慢测试。
- completion report 必须记录实际命令、测试数、跳过数、耗时和已知 warning。

---

## 6. 风险与威胁模型

### 6.1 工程风险

| 风险 | 严重度 | 触发信号 | 缓解与回滚 |
| --- | --- | --- | --- |
| Dispatcher 迁移改变历史 CLI 语义 | 高 | CLI exit code、JSON shape 或 stub 输出变化 | characterization tests 先行；Wave 1 独立提交，可整体 revert |
| LangGraph `max_steps` 透传遗漏 | 高 | 长流程提前中断或无限递归 | 单测断言 recursion limit；保留默认 100 |
| Store 迁移吞掉真实错误 | 中 | API 错误变成空数组/空对象 | 禁止 broad fallback；保留 typed exception/envelope |
| SQLite 查询优化改变事务边界 | 中 | WAL 锁、连接泄漏、并行测试不稳定 | 只读试点；连接关闭/回滚测试；不引入全局连接池 |
| 模块拆分破坏 SSE schema | 高 | 前端时间线停止更新 | event snapshot/characterization tests；路由和 event type 不变 |
| 路由 lazy loading 破坏桌面 HashRouter | 中 | 桌面深链白屏 | BrowserRouter + HashRouter 双模式测试 |
| 只提高 chunk warning 阈值形成假优化 | 中 | bundle 体积不降但 build 无警告 | 独立产物预算脚本，以实际字节数验收 |

### 6.2 安全边界

本版本不新增外部服务、认证或远程存储，但必须保持以下安全性质：

- release/preflight 输出不得打印 `.env`、API Key、LLM headers 或绝对凭据内容。
- API 全局异常继续经过 `redact_sensitive_text()`；模块拆分不能绕过脱敏。
- Electron 继续通过 `safeStorage` 注入 secrets；版本脚本不得读取或复制 secret store。
- SQLite 路径来自现有 settings/app state，不接受未校验的 shell 拼接。
- release 脚本不得自动 commit、push、发布或调用真实 LLM。

高严重度安全性质任一回归时，当前 Wave 立即阻断，不允许以文档豁免通过。

---

## 7. 提交与回滚策略

建议按 task 原子提交：

1. `fix(v6.11.02): restore version alignment and release preflight`
2. `refactor(v6.11.02): make LangGraph the only chapter runner`
3. `refactor(v6.11.02): migrate explicit CLI chapter execution paths`
4. `refactor(v6.11.02): adopt store boundary for selected read paths`
5. `refactor(v6.11.02): extract production service boundary`
6. `perf(v6.11.02): add route code splitting and bundle budget`
7. `release(v6.11.02): close verification evidence and version ledger`

禁止在同一提交同时进行版本修复、章节引擎替换和大模块搬迁。任一 Wave 失败时回滚该 Wave 的提交，不回滚已通过的前置 Wave。

---

## 8. 完成定义

v6.11.02 只有在以下条件全部满足时才能标记 Complete：

- [ ] OPT-01 至 OPT-06 全部完成；OPT-07 至 OPT-10 若未纳入，已明确顺延到 v6.11.03。
- [ ] 所有版本源符合已批准的 version policy。
- [ ] 章节生产不存在可被生产代码触发的 legacy Agent loop。
- [ ] API、CLI、auto-run、demo/batch/revision 的章节执行契约有回归覆盖。
- [ ] `python3 scripts/verify.py release` 退出码为 0。
- [ ] completion report 记录实际验证证据，不复制旧版本测试数字。
- [ ] version planning index、README、CHANGELOG 与 runtime 状态一致。
- [ ] 没有真实 LLM 凭据、数据库或构建产物进入 git。

---

## 9. 后续路线

若 Wave 2、Wave 3 未纳入 v6.11.02，建议按以下顺序延续：

| 版本 | 主题 | 进入条件 |
| --- | --- | --- |
| v6.11.03 | Persistence Boundary Adoption | v6.11.02 release 与 runtime convergence 全绿 |
| v6.11.04 | Production/Genesis Module Decomposition | Store/Repository 职责稳定 |
| v6.12.0 | Architecture Research Decision | v6.11.0 原型有量化收益和迁移成本结论 |

---

## 10. 关联文档

- `docs/codex/planning/novel-factory-v6.11.01-architecture-debt-optimization-plan.md`
- `docs/codex/planning/novel-factory-v6.11.0-architecture-refactor-plan.md`
- `docs/codex/planning/novel-factory-v6.10.20-exception-unification-plan.md`
- `docs/codex/planning/novel-factory-version-planning-index.md`
- `CHANGELOG.md`
- `AGENTS.md`
