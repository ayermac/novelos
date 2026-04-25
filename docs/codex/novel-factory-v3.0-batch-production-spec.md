# v3.0 Batch Production MVP 开发规范

## Summary

v3.0 的目标是把系统从“单章自动创作”升级为“多章节批次自动创作”。

本版本不重写现有 Agent，不改变单章主链路，不引入 Web、队列或并发调度。v3.0 只在现有 `Dispatcher.run_chapter()` 上方新增批次调度层，让用户可以指定某个项目一次自动创作多章，并在批次完成后进入人工集中 review。

核心流程：

```text
novelos batch run --project-id demo --from-chapter 1 --to-chapter 10
-> 创建 production_run
-> 创建 production_run_items
-> 逐章调用 Dispatcher.run_chapter()
-> 每章记录结果
-> 全部成功后进入 awaiting_review
-> 用户通过 batch review 记录人工决策
```

默认策略是 `stop_on_block=true`：如果第 N 章出现 `error`、`requires_human` 或 `blocking`，批次停止，不继续创作后续章节。

## Why Now

v1.x 已完成单章主流水线稳定化，v2.x 已完成 sidecar、QualityHub、Skill Manifest、Skill Package 等质量治理能力。

当前最重要的缺口已经不是继续扩展 Skill，而是让这些能力服务于更大的生产流程：

```text
自动创作多章
-> 批次级状态追踪
-> 人工集中 review
-> 后续版本支持指定章节返修和批次连续性检查
```

因此 v2.4+ 暂时进入增强池，v3.0 先开启批次生产主线。

## Goals

v3.0 必须实现：

- 批次生产运行：`batch run`。
- 批次状态查询：`batch status`。
- 批次人工 review 记录：`batch review`。
- 批次数据表：`production_runs`、`production_run_items`、`human_review_sessions`。
- Dispatcher 批次方法：`run_batch()`、`get_batch_status()`、`review_batch()`。
- Repository 批次读写方法。
- 稳定 JSON envelope：`{ok,error,data}`。
- 全量测试不回归。

## Non-Goals

v3.0 不做：

- Web UI / FastAPI。
- daemon 常驻任务。
- 定时自动创作。
- Redis / Celery / Kafka。
- PostgreSQL。
- 多项目并行。
- 复杂并发批处理。
- 章节级复杂返修。
- 自动重写全部章节。
- 自动发布整批内容。
- 改主链路 Agent 顺序。
- 重写 v2.1-v2.3 Skill Package 系统。
- 外部 Skill 热加载。
- 多模型 fallback。
- token 成本统计。

## CLI Design

### batch run

```bash
novelos batch run --project-id demo --from-chapter 1 --to-chapter 10 --json
```

返回：

```json
{
  "ok": true,
  "error": null,
  "data": {
    "run_id": "batch_xxx",
    "project_id": "demo",
    "status": "awaiting_review",
    "from_chapter": 1,
    "to_chapter": 10,
    "completed_chapters": 10,
    "blocked_chapter": null
  }
}
```

规则：

- `from_chapter` 必须小于等于 `to_chapter`。
- 默认 `stop_on_block=true`。
- v3.0 可以不暴露 `--continue-on-error`；如果实现，默认仍必须停止。
- `--json` 错误路径也必须输出 `{ok,error,data}`。

### batch status

```bash
novelos batch status --run-id batch_xxx --json
```

返回：

```json
{
  "ok": true,
  "error": null,
  "data": {
    "run_id": "batch_xxx",
    "project_id": "demo",
    "status": "awaiting_review",
    "from_chapter": 1,
    "to_chapter": 10,
    "completed_chapters": 10,
    "blocked_chapter": null,
    "items": [
      {
        "chapter_number": 1,
        "status": "completed",
        "chapter_status": "published",
        "quality_pass": true,
        "error": null,
        "requires_human": false
      }
    ]
  }
}
```

### batch review

```bash
novelos batch review --run-id batch_xxx --decision approve --json
```

支持 decision：

```text
approve
request_changes
reject
```

可选 notes：

```bash
novelos batch review --run-id batch_xxx --decision request_changes --notes "第 3 章节奏太快" --json
```

返回：

```json
{
  "ok": true,
  "error": null,
  "data": {
    "run_id": "batch_xxx",
    "decision": "request_changes"
  }
}
```

## Database Design

新增 migration：

```text
novel_factory/db/migrations/007_v3_0_batch_production.sql
```

migration 必须可重复 `init_db`，不得破坏已有 migration tracking 与 schema 检测逻辑。

### production_runs

```sql
CREATE TABLE IF NOT EXISTS production_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    from_chapter INTEGER NOT NULL,
    to_chapter INTEGER NOT NULL,
    status TEXT NOT NULL,
    total_chapters INTEGER NOT NULL,
    completed_chapters INTEGER DEFAULT 0,
    blocked_chapter INTEGER,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);
```

推荐索引：

```sql
CREATE INDEX IF NOT EXISTS idx_production_runs_project
ON production_runs(project_id, created_at);

CREATE INDEX IF NOT EXISTS idx_production_runs_status
ON production_runs(status, updated_at);
```

状态枚举：

```text
pending
running
awaiting_review
approved
request_changes
rejected
blocked
failed
```

### production_run_items

```sql
CREATE TABLE IF NOT EXISTS production_run_items (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    workflow_run_id TEXT,
    status TEXT NOT NULL,
    chapter_status TEXT,
    quality_pass INTEGER,
    error TEXT,
    requires_human INTEGER DEFAULT 0,
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

推荐索引：

```sql
CREATE INDEX IF NOT EXISTS idx_production_run_items_run
ON production_run_items(run_id, chapter_number);

CREATE INDEX IF NOT EXISTS idx_production_run_items_project_chapter
ON production_run_items(project_id, chapter_number);
```

状态枚举：

```text
pending
running
completed
blocked
failed
skipped
```

### human_review_sessions

```sql
CREATE TABLE IF NOT EXISTS human_review_sessions (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL
);
```

推荐索引：

```sql
CREATE INDEX IF NOT EXISTS idx_human_review_sessions_run
ON human_review_sessions(run_id, created_at);
```

## Repository Requirements

至少新增：

```python
create_production_run(...)
update_production_run(...)
get_production_run(run_id)
list_production_runs(project_id=None, limit=20)

create_production_run_item(...)
update_production_run_item(...)
get_production_run_items(run_id)

save_human_review_session(...)
get_human_review_sessions(run_id)
```

要求：

- 写方法必须返回可判断结果，不能静默失败。
- 时间字段统一 ISO 字符串。
- `requires_human`、`quality_pass` 在 Python 返回中应转成 bool 或清晰的 `0/1`。
- `get_batch_status()` 使用 Repository 查询，不直接拼 SQL 到 CLI。
- 不改变既有 `workflow_runs`、`quality_reports`、`skill_runs` 语义。

## Dispatcher Requirements

### run_batch

```python
def run_batch(
    self,
    project_id: str,
    from_chapter: int,
    to_chapter: int,
    stop_on_block: bool = True,
) -> dict:
    ...
```

返回：

```python
{
    "ok": True,
    "error": None,
    "data": {
        "run_id": "...",
        "project_id": project_id,
        "status": "awaiting_review",
        "from_chapter": from_chapter,
        "to_chapter": to_chapter,
        "completed_chapters": 10,
        "blocked_chapter": None,
    },
}
```

行为：

1. 校验 `from_chapter <= to_chapter`。
2. 创建 `production_run`，初始 `status=running`。
3. 为每章创建 `production_run_item`，初始 `status=pending`。
4. 按章节顺序调用现有 `self.run_chapter(project_id, chapter_number)`。
5. 每章执行前将 item 标记 `running`。
6. 每章执行后保存 item 的 `status`、`chapter_status`、`error`、`requires_human`、`workflow_run_id`。
7. 如果某章返回 `error`、`requires_human=true` 或 `chapter_status=blocking`：
   - 当前 item 标记 `blocked`。
   - `production_run.status=blocked`。
   - 设置 `blocked_chapter` 和 `error`。
   - `stop_on_block=True` 时停止后续章节。
8. 如果全部章节成功：
   - `production_run.status=awaiting_review`。
   - 设置 `completed_at`。
9. 返回稳定 envelope。

注意：

- v3.0 必须复用 `run_chapter()`，不得重新实现 Agent 调度。
- `run_batch()` 不应绕开 QualityHub、Skill、workflow_runs 或 artifact 记录。
- 批次层不负责自动修文，只负责运行和记录。

### get_batch_status

```python
def get_batch_status(self, run_id: str) -> dict:
    ...
```

行为：

- 查询 `production_run`。
- 查询 `production_run_items`。
- 不存在时返回 `ok=false`。
- 返回 `{ok,error,data}`。

### review_batch

```python
def review_batch(
    self,
    run_id: str,
    decision: str,
    notes: str | None = None,
) -> dict:
    ...
```

规则：

- 只允许 `approve`、`request_changes`、`reject`。
- 非法 decision 返回 `ok=false`。
- 写入 `human_review_sessions`。
- 更新 `production_runs.status`：
  - `approve -> approved`
  - `request_changes -> request_changes`
  - `reject -> rejected`
- v3.0 不实现章节级返修动作，只记录人工决策。

## Failure Handling

### Chapter blocked

```text
run_chapter returns error/requires_human/blocking
-> item.status = blocked
-> run.status = blocked
-> stop_on_block=true 时停止
```

### Invalid range

```text
from_chapter > to_chapter
-> ok=false
-> 不创建 production_run
```

### Repository write failure

```text
任意关键写入失败
-> ok=false
-> run.status=failed 或 blocked
-> error 记录清晰原因
```

### Missing run

```text
batch status / batch review 找不到 run_id
-> ok=false
-> error="production run not found: ..."
-> data={}
```

## Test Plan

新增：

```text
tests/test_batch_production.py
tests/test_v3_0_cli.py
```

至少覆盖：

1. `run_batch` 创建 `production_run`。
2. `run_batch` 创建每章 `production_run_item`。
3. 多章全部成功后 `production_run.status=awaiting_review`。
4. 某章失败后 `production_run.status=blocked`。
5. `stop_on_block=True` 时后续章节不继续执行，并标记 skipped 或保持 pending。
6. `get_batch_status` 返回 run 和 items。
7. `review_batch approve` 写入 `human_review_sessions`。
8. `review_batch request_changes` 支持 notes。
9. 非法 decision 返回 `ok=false`。
10. `batch run --json` envelope 稳定。
11. `batch status --json` envelope 稳定。
12. `batch review --json` envelope 稳定。
13. CLI 缺参数或非法参数时 JSON 错误 envelope 稳定。
14. 不破坏已有 `478` 个测试。

建议真实 CLI 验证：

```bash
python3 -m novel_factory.cli seed-demo --project-id demo --json
python3 -m novel_factory.cli batch run --project-id demo --from-chapter 1 --to-chapter 3 --json
python3 -m novel_factory.cli batch status --run-id <run_id> --json
python3 -m novel_factory.cli batch review --run-id <run_id> --decision approve --json
```

如果项目使用 `novelos` console script，也需要验证：

```bash
novelos batch run --project-id demo --from-chapter 1 --to-chapter 3 --json
novelos batch status --run-id <run_id> --json
novelos batch review --run-id <run_id> --decision approve --json
```

## Acceptance Criteria

v3.0 通过必须满足：

- 全量测试通过。
- 新增测试数量必须大于当前 v2.3 基线 `478`。
- `batch run/status/review` 三类命令可运行。
- 所有 `--json` 输出稳定为 `{ok,error,data}`。
- `run_batch()` 复用 `run_chapter()`。
- 默认 `stop_on_block=true`。
- 批次成功后进入 `awaiting_review`，不是直接 `approved`。
- 人工 review 决策被持久化。
- 未引入 v3.0 禁止范围能力。

## Handoff Report Format

开发完成后必须汇报：

1. 修改了哪些文件。
2. 新增了哪些文件。
3. 新增 migration 内容。
4. 新增 CLI 命令。
5. 新增测试数量。
6. 全量测试数量和结果。
7. 真实 CLI 验证结果。
8. 是否严格遵守禁止范围。
9. 未完成项或风险。

