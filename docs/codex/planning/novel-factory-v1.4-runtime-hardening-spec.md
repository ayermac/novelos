# v1.4 运行时硬化与配置化收尾开发规范

## 目标

v1.4 的目标是把 v1.3 已经跑通的 `novelos` 后端 CLI，从“源码目录可运行”推进到“安装后可运行、配置可诊断、错误可解释、本地可 smoke test”。

v1.3 已经完成 Dispatcher 编排与 CLI 可运行化。v1.4 不新增小说生产 Agent，不改变主链路，而是补齐真实落地前的运行体验和工程边界。

本轮重点：

- 打包资源完整性。
- 配置加载与校验。
- Stub LLM 与真实 LLM 模式显式化。
- 本地 demo seed 与 smoke run。
- `revision_target` 结构化存储，去掉 summary 字符串解析依赖。
- CLI doctor / config / diagnostics 能力。
- 安装后 `novelos` 命令可独立初始化并运行 demo。

## 当前前置条件

必须基于以下状态开发：

- v1 MVP 已通过。
- v1 review 返工闸门已通过。
- v1.1 工程稳定性已通过。
- v1.2 质量与一致性增强已通过。
- v1.3 Dispatcher 编排与 CLI 可运行化已通过。
- 当前全量测试应为 `267/267` 或更多。
- 不允许破坏 v1-v1.3 任何验收测试。

## 版本定位

v1.4 是运行时硬化版本，不是新 Agent 扩展版本。

完成后，开发者应能在没有 Web UI 的情况下完成：

```bash
pip install -e .
novelos doctor
novelos init-db --db-path .novelos/demo.db
novelos seed-demo --db-path .novelos/demo.db --project-id demo
novelos run-chapter --db-path .novelos/demo.db --project-id demo --chapter 1 --llm-mode stub
novelos status --db-path .novelos/demo.db --project-id demo --chapter 1 --json
```

真实 LLM 模式也必须行为清晰：

```bash
novelos config validate --config novel_factory/config/llm.yaml
novelos run-chapter --project-id demo --chapter 1 --llm-mode real
```

如果缺少 API key，必须给出清晰错误，不得静默降级为 Stub。

## 本轮允许实现

允许修改：

- `pyproject.toml`
- `novel_factory/cli.py`
- `novel_factory/config/settings.py`
- `novel_factory/config/agents.yaml`
- `novel_factory/config/llm.yaml`
- `novel_factory/db/connection.py`
- `novel_factory/db/repository.py`
- `novel_factory/db/schema/*`
- `novel_factory/db/migrations/*`
- `novel_factory/dispatcher.py`
- `novel_factory/llm/*`
- `tests/*`
- `docs/codex/*`

允许新增：

- `novel_factory/runtime/diagnostics.py`
- `novel_factory/runtime/demo_seed.py`
- `novel_factory/config/loader.py`
- `novel_factory/db/migrations/004_v1_4_runtime.sql`
- `tests/test_runtime_hardening.py`
- `tests/test_config_cli.py`
- `tests/test_packaging_resources.py`

## 本轮禁止实现

- 不新增 Web UI。
- 不新增 Web API / FastAPI 服务。
- 不新增 Scout / Architect / Secretary。
- 不新增 ContinuityChecker 独立 Agent。
- 不新增多 Provider fallback。
- 不新增 Skill 热加载。
- 不引入 Celery / Redis / Kafka。
- 不引入 PostgreSQL。
- 不引入 SQLModel 全量 ORM。
- 不改变主链路 `Planner -> Screenwriter -> Author -> Polisher -> Editor`。
- 不改变章节状态枚举。
- 不把真实 API key 写进仓库。

## 技术栈选型

### 必选

| 模块 | 选型 | 说明 |
| --- | --- | --- |
| CLI | argparse 继续沿用 | v1.3 已使用 argparse，本轮不为 CLI 框架迁移制造噪音 |
| 包资源 | `importlib.resources` 优先 | 安装后稳定读取 schema、migrations、默认 yaml |
| 配置 | YAML + 环境变量 + CLI 覆盖 | 顺序必须明确、可测试 |
| 数据库 | SQLite | 延续现有实现 |
| 测试 | pytest + subprocess | 必须覆盖真实 `novelos` 命令和 `python -m` 入口 |

### 不选

| 方案 | 不选原因 |
| --- | --- |
| Typer 重写 CLI | 当前 argparse 已够用，v1.4 聚焦硬化 |
| Pydantic Settings 全量替换 | 可后续做，本轮只做最小可靠配置 |
| 多 Provider 路由 | 放到 v3，不抢 v1.4 范围 |

## 必修项

### H1：包资源完整性

要求：

- `pyproject.toml` 必须正确包含：
  - `novel_factory/db/schema/*.sql`
  - `novel_factory/db/migrations/*.sql`
  - `novel_factory/config/*.yaml`
- `connection.py` 读取 schema/migrations 应优先使用包内路径或 `importlib.resources`。
- 配置默认文件读取不能依赖当前工作目录。
- 安装后 `novelos init-db` 必须可用。

验收：

- 测试覆盖 `config/*.yaml` 被 package-data 包含。
- 测试覆盖从非仓库 cwd 运行 `python -m novel_factory.cli --help`。
- 测试覆盖临时目录下 `novelos init-db --db-path ...` 成功。

### H2：配置加载顺序与校验

要求：

配置优先级必须明确：

```text
CLI 参数 > 环境变量 > --config YAML > 包内默认 YAML > Pydantic 默认值
```

新增或增强：

```bash
novelos config show
novelos config validate
```

要求：

- `config show` 默认隐藏 API key，只显示是否已配置。
- `config show --json` 输出可被 `json.loads` 解析。
- `config validate` 校验 db path、llm provider、model、api key、agents.yaml 基本结构。
- 缺少真实 LLM key 时，在 `--llm-mode real` 下失败并给出清晰错误。

验收：

- 测试覆盖 CLI > env > YAML 的覆盖顺序。
- 测试覆盖 API key 不出现在 stdout。
- 测试覆盖无 key 的 real 模式失败。
- 测试覆盖 stub 模式不需要 key。

### H3：LLM 模式显式化

要求：

v1.3 中无 API key 时自动使用 `_StubLLM`，适合测试，但真实 CLI 使用时容易误解。v1.4 必须显式区分：

```bash
--llm-mode stub
--llm-mode real
```

建议默认：

- `run-chapter` 默认 `real`。
- 测试和 demo 使用 `--llm-mode stub`。
- 如果为了兼容暂时保留自动 stub，必须在输出和 workflow run 中明确标记 `llm_mode=stub`。

要求：

- Stub 模式只能用于本地 smoke/demo。
- Real 模式缺 key 必须失败。
- 不得静默从 real 降级到 stub。

验收：

- `novelos run-chapter --llm-mode real` 缺 key 返回非 0。
- `novelos run-chapter --llm-mode stub` 可用固定假模型跑通 demo。
- workflow run 或输出中可见 `llm_mode`。

### H4：Demo seed 与 smoke run

要求：

新增：

```bash
novelos seed-demo --project-id demo
novelos smoke-run --project-id demo --chapter 1 --llm-mode stub
```

`seed-demo` 必须创建最小可运行数据：

- project
- chapter 1
- instruction
- character
- plot_hole 可选但建议有一个

`smoke-run` 可以是 `init-db + seed-demo + run-chapter + status` 的组合，也可以只针对已有 DB 执行检查。

验收：

- 全新空 DB 上 `seed-demo` 后可 `run-chapter --llm-mode stub`。
- 重复执行 `seed-demo` 幂等，不重复插入项目/章节。
- smoke-run 返回最终状态、steps、error、requires_human。

### H5：`revision_target` 结构化存储

要求：

v1.3 中 Dispatcher 通过 `reviews.summary` 解析 `revision_target=author`。v1.4 必须新增结构化字段或等价结构，避免业务字段复用。

建议 migration：

```sql
ALTER TABLE reviews ADD COLUMN revision_target TEXT;
```

要求：

- migration 必须幂等，兼容旧库已有字段但无 tracking 记录。
- `Repository.save_review()` 写入 `reviews.revision_target`。
- `Dispatcher._route()` 优先读取结构化 `revision_target`。
- 兼容旧数据：字段为空时可 fallback 到 summary 解析。
- `summary` 恢复为真正摘要字段，不再承担路由协议。

验收：

- 测试覆盖 review 写入 revision_target 字段。
- 测试覆盖 Dispatcher 从字段路由到 Author/Polisher。
- 测试覆盖旧 summary fallback 仍可用。
- 测试覆盖 migration 重复执行不报错。

### H6：Doctor 与诊断输出

要求：

新增：

```bash
novelos doctor
```

至少检查：

- Python 版本。
- package 版本。
- schema/migrations 是否可定位。
- config yaml 是否可定位。
- DB 路径是否可写。
- LLM 配置是否存在。
- `novelos` console script 是否可用。

输出：

- 默认人类可读。
- `--json` 可解析。
- 不输出 API key。

验收：

- 测试覆盖 doctor 成功。
- 测试覆盖 doctor --json。
- 测试覆盖 key 脱敏。

### H7：CLI 错误码与 JSON 稳定性

要求：

- 成功命令返回 0。
- 用户输入错误返回 2 或 argparse 默认错误。
- 运行时错误返回 1。
- `--json` 模式下错误也输出 JSON。
- JSON 字段稳定，至少包含：

```json
{
  "ok": true,
  "error": null,
  "data": {}
}
```

可以渐进式支持，不要求所有旧命令一次性完全统一，但 v1.4 新命令必须遵守。

验收：

- 测试覆盖 real mode 缺 key 的 JSON 错误。
- 测试覆盖 status 缺章节 JSON 错误。
- 测试覆盖 config validate JSON 输出。

## 数据库与迁移

允许新增：

- `004_v1_4_runtime.sql`

推荐内容：

- `reviews.revision_target`
- 如需要记录 llm_mode，可在 `workflow_runs` 增加 `llm_mode` 或把它写入可查询 metadata 字段。

要求：

- migration 可重复执行。
- `_is_migration_applied_by_schema()` 支持 004 检测。
- 旧库已手动添加字段但无 tracking 记录时，`init_db()` 不报错并补记 tracking。

## 测试要求

必须新增或补充：

- `tests/test_runtime_hardening.py`
- `tests/test_config_cli.py`
- `tests/test_packaging_resources.py`

最低测试覆盖：

- package data 包含 SQL 和 YAML。
- 非仓库 cwd 下 CLI help 可用。
- `novelos init-db` 在临时目录可用。
- `config show --json`。
- `config validate`。
- API key 脱敏。
- real mode 缺 key 失败。
- stub mode demo run 成功。
- `seed-demo` 幂等。
- `smoke-run` 可返回稳定结构。
- `revision_target` 字段写入。
- Dispatcher 优先读取 `reviews.revision_target`。
- summary fallback 兼容旧数据。
- migration 004 幂等。
- workflow run 或运行输出能显示 llm_mode。

全量测试必须通过，测试数应大于 v1.3 的 `267`。

## 验收标准

v1.4 通过必须同时满足：

- 全量测试通过。
- `pip install -e .` 后 `novelos --help` 可用。
- `novelos init-db` 不依赖 openclaw-agents 路径。
- `novelos seed-demo` 可创建可运行 demo。
- `novelos run-chapter --llm-mode stub` 可跑 demo。
- `novelos run-chapter --llm-mode real` 缺 key 时清晰失败。
- API key 不在日志/stdout/JSON 中泄露。
- `revision_target` 不再依赖 summary 字符串作为主路径。
- 不引入 v2 范围能力。

## 给开发 Agent 的执行顺序

建议按以下顺序开发：

1. 修正 package data，确保 `config/*.yaml` 被打包。
2. 抽出配置 loader，明确 CLI/env/YAML/default 优先级。
3. 新增 `config show` / `config validate`。
4. 增加 `--llm-mode stub|real`，禁止 real 静默降级。
5. 新增 demo seed。
6. 新增 smoke-run。
7. 新增 004 migration，把 `revision_target` 结构化。
8. Dispatcher 改为优先读取结构化 `revision_target`。
9. 新增 doctor。
10. 补齐测试并跑全量。

## 非目标

以下内容不要在 v1.4 做：

- 新 Agent。
- Web 管理界面。
- FastAPI。
- 多模型 fallback。
- 成本统计。
- 云端部署。
- 复杂数据备份恢复。
- 跨章 ContinuityChecker。

