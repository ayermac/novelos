# v3.6 Semi-Auto Serial Mode 开发规范

## Summary

v3.6 的目标是在 v3.4 Production Queue 和 v3.5 Queue Runtime Hardening 之上，新增“半自动连载计划”能力。

用户可以为某个项目创建 serial plan，例如“每轮生成 3 章，总共先生成 12 章”。系统根据计划显式创建 queue item，并在每轮完成后停在人工 review，不自动 approve、不自动 publish、不后台常驻。

核心流程：

```text
serial create -> serial plan=draft/active
serial enqueue-next -> 根据计划创建下一轮 queue item
batch queue-run --limit N -> 显式执行队列
batch review / continuity gate / revision -> 人工审核与返修
serial advance -> 人工确认后推进下一轮
serial status -> 查看计划进度
```

## Why Now

v3.0 跑通了多章节批次生产，v3.4 增加了 queue，v3.5 让 queue 可诊断、可取消、可恢复。现在系统已经具备“可控地连续生产”的基础。

v3.6 要解决的是：

- 用户想设置“一篇小说先自动创作 10 章”。
- 生成一轮后需要人工 review。
- 如果 review 不满意，可以进入 v3.2 返修闭环。
- 人工确认后，再进入下一轮。

这不是 daemon，也不是无人值守自动连载。v3.6 是“半自动”，系统负责计划和排队，用户负责关键闸门。

## Goals

v3.6 必须实现：

- serial plan 数据结构。
- 创建 serial plan。
- 查看 serial plan 状态。
- 按计划 enqueue 下一轮。
- 人工确认后 advance 到下一轮。
- serial plan 与 production_queue / production_runs 关联。
- 每轮完成后必须等待人工 review。
- 不经人工确认不得自动进入下一轮。
- JSON envelope 稳定。

## Non-Goals

v3.6 不做：

- 后台 daemon。
- cron / 定时每日自动运行。
- 自动 approve。
- 自动 publish。
- 自动修订计划生成。
- 自动连续 enqueue 到结束。
- 多 worker 并发。
- Redis / Celery / Kafka。
- PostgreSQL。
- Web UI / FastAPI。
- token 成本统计。
- provider fallback。

这些留给 v4 或后续生产治理版本。

## Serial Plan Model

新增 serial plan 状态：

```text
draft
active
waiting_review
paused
completed
cancelled
failed
```

状态含义：

- `draft`：计划已创建但未开始。
- `active`：可以 enqueue 下一轮。
- `waiting_review`：当前轮已完成，等待人工审核或确认。
- `paused`：人工暂停。
- `completed`：计划所有章节已完成。
- `cancelled`：计划取消。
- `failed`：计划推进失败。

## Database Design

新增 migration：

```text
novel_factory/db/migrations/011_v3_6_serial_plan.sql
```

### serial_plans

```sql
CREATE TABLE IF NOT EXISTS serial_plans (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    start_chapter INTEGER NOT NULL,
    target_chapter INTEGER NOT NULL,
    batch_size INTEGER NOT NULL,
    current_chapter INTEGER NOT NULL,
    status TEXT NOT NULL,
    current_queue_id TEXT,
    current_production_run_id TEXT,
    total_planned_chapters INTEGER NOT NULL,
    completed_chapters INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);
```

### serial_plan_events

```sql
CREATE TABLE IF NOT EXISTS serial_plan_events (
    id TEXT PRIMARY KEY,
    serial_plan_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    message TEXT,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (serial_plan_id) REFERENCES serial_plans(id)
);
```

推荐索引：

```sql
CREATE INDEX IF NOT EXISTS idx_serial_plans_project
    ON serial_plans(project_id, created_at);

CREATE INDEX IF NOT EXISTS idx_serial_plans_status
    ON serial_plans(status, updated_at);

CREATE INDEX IF NOT EXISTS idx_serial_plan_events_plan
    ON serial_plan_events(serial_plan_id, created_at);
```

## CLI Design

### 1. serial create

```bash
novelos serial create \
  --project-id demo \
  --name "第一卷连载计划" \
  --start-chapter 1 \
  --target-chapter 10 \
  --batch-size 3 \
  --json
```

返回：

```json
{
  "ok": true,
  "error": null,
  "data": {
    "serial_plan_id": "serial_xxx",
    "status": "active",
    "current_chapter": 1
  }
}
```

### 2. serial status

```bash
novelos serial status --serial-plan-id serial_xxx --json
```

返回：

```json
{
  "ok": true,
  "error": null,
  "data": {
    "serial_plan_id": "serial_xxx",
    "project_id": "demo",
    "status": "waiting_review",
    "current_chapter": 4,
    "target_chapter": 10,
    "batch_size": 3,
    "completed_chapters": 3,
    "current_queue_id": "queue_xxx",
    "current_production_run_id": "batch_xxx",
    "events": []
  }
}
```

### 3. serial enqueue-next

```bash
novelos serial enqueue-next --serial-plan-id serial_xxx --json
```

行为：

- 只允许 `active` 状态。
- 根据 `current_chapter` 和 `batch_size` 计算下一轮范围。
- 调用 v3.4 `enqueue_batch()` 创建 queue item。
- 保存 `current_queue_id`。
- 状态进入 `waiting_review`。
- 写 serial event。

示例：

```text
start=1, target=10, batch_size=3, current=1
enqueue range: 1-3
下一次 advance 后 current=4
```

### 4. serial advance

```bash
novelos serial advance --serial-plan-id serial_xxx --decision approve --json
```

行为：

- 只允许 `waiting_review` 状态。
- 必须检查当前 queue item 已完成。
- 必须检查关联 production_run 已进入可接受状态。
- 多章节 batch 必须通过 v3.3 continuity gate 或处于 warning/passed。
- `decision=approve` 时推进 `current_chapter` 到下一轮起点。
- 若超过 `target_chapter`，状态进入 `completed`。
- 否则状态回到 `active`，等待下一次 `serial enqueue-next`。

允许 decision：

```text
approve
request_changes
pause
cancel
```

说明：

- `request_changes` 不自动生成 revision plan，只把 serial plan 保持在 `waiting_review` 并写 event。
- `pause` 进入 `paused`。
- `cancel` 进入 `cancelled`。

### 5. serial pause / resume / cancel

```bash
novelos serial pause --serial-plan-id serial_xxx --json
novelos serial resume --serial-plan-id serial_xxx --json
novelos serial cancel --serial-plan-id serial_xxx --reason "manual stop" --json
```

规则：

- `pause` 允许 `active` / `waiting_review`。
- `resume` 只允许 `paused`，恢复到 `active` 或 `waiting_review` 需要保存 pause 前状态。
- `cancel` 允许非终态。
- 终态 `completed` / `cancelled` 不可 resume / advance / enqueue-next。

v3.6 可以简化：如果不实现 pause 前状态字段，则 resume 统一回到 `active`，但必须在文档和测试中明确。

## Dispatcher Design

新增方法：

- `create_serial_plan(...)`
- `get_serial_status(serial_plan_id)`
- `enqueue_serial_next(serial_plan_id)`
- `advance_serial_plan(serial_plan_id, decision, notes=None)`
- `pause_serial_plan(serial_plan_id)`
- `resume_serial_plan(serial_plan_id)`
- `cancel_serial_plan(serial_plan_id, reason=None)`

要求：

- `enqueue_serial_next()` 必须复用 `enqueue_batch()`。
- 不得直接创建 production_run。
- 不得直接调用 run_batch。
- serial 只负责计划和排队。
- batch/queue 仍负责实际生产。

## Safety Gates

`serial advance --decision approve` 必须检查：

- 当前 queue item 存在。
- 当前 queue item status 是 `completed`。
- `production_run_id` 存在。
- production run status 是 `awaiting_review` 或人工认可的后续状态。
- 如果 batch 多章节，continuity gate 必须是 `passed` 或 `warning`。
- 如果 production run 是 `request_changes`，不得 approve。

若不满足，返回 `ok=false`。

## JSON Envelope

所有 serial 命令必须输出：

```json
{"ok": true, "error": null, "data": {}}
```

或：

```json
{"ok": false, "error": "message", "data": {}}
```

不得输出：

- traceback。
- argparse 裸 usage。
- `success` 字段。
- `data: null`。

## Test Plan

新增 `tests/test_v36_semi_auto_serial_mode.py`，至少覆盖：

1. migration 011 幂等。
2. serial create 成功。
3. create 拒绝 `start_chapter > target_chapter`。
4. create 拒绝 `batch_size < 1`。
5. serial status 返回 plan 和 events。
6. enqueue-next 从 active 创建 queue item。
7. enqueue-next 范围计算正确，例如 1-3、4-6、10-10。
8. enqueue-next 后状态进入 waiting_review。
9. waiting_review 不能重复 enqueue-next。
10. advance approve 前 queue 未 completed 时拒绝。
11. advance approve 前 production_run_id 缺失时拒绝。
12. 多章节 batch continuity gate failed 时拒绝 approve。
13. continuity gate warning/passed 允许 approve。
14. approve 后 current_chapter 前进。
15. approve 最后一轮后 status=completed。
16. request_changes 保持 waiting_review，不自动 revision。
17. pause active 成功。
18. resume paused 成功。
19. cancel active/waiting_review 成功。
20. completed/cancelled 不可 advance/enqueue-next。
21. CLI JSON envelope 覆盖 create/status/enqueue-next/advance/pause/resume/cancel。
22. argparse 缺参 JSON envelope。
23. 全量测试通过。

## Acceptance Criteria

v3.6 通过必须满足：

- 用户可以创建 serial plan。
- 用户可以按计划 enqueue 下一轮 batch。
- 每轮完成后 serial plan 停在 waiting_review。
- 人工 approve 后才推进下一轮。
- 不经人工确认不得自动 enqueue 下一批。
- serial plan 与 queue item / production_run 可追踪。
- continuity gate 可阻止多章节 approve。
- 全路径 JSON envelope 稳定。
- 全量测试通过。

## Delivery Report

开发完成后必须汇报：

1. 修改文件。
2. 新增文件。
3. 新增 migration。
4. 新增 CLI 命令。
5. 新增测试数量。
6. 全量测试数量与结果。
7. 真实 CLI 验证命令与结果。
8. 是否严格遵守禁止范围。
9. 未完成项或风险。

