# v3.4 Production Queue 开发规范

## Summary

v3.4 的目标是在现有 batch production 能力上，增加一个本地 SQLite production queue MVP，让多个批次可以排队、暂停、恢复和失败重试。

本版本不做后台 daemon、不做并发 worker、不引入 Redis/Celery/Kafka。所有队列推进都由 CLI 显式触发，保持本地可运行、可测试、可审计。

核心流程：

```text
batch enqueue -> queue item=pending
batch queue-run --once -> 领取 1 个 pending item -> 调用 run_batch()
batch queue-status -> 查看队列
batch queue-pause / queue-resume -> 控制 item
batch queue-retry -> 失败后重新排队
```

## Why Now

v3.0 已支持多章节批次生产，v3.2 支持返修闭环，v3.3 支持批次连续性门禁。用户下一步会自然产生多个待生产批次：

- 同一小说按卷分批生产。
- 多个项目轮流生产。
- 某个批次失败后稍后重试。
- 暂停一个批次，先处理更紧急的批次。

v3.4 要解决“多个 batch 如何排队和手动推进”，但不要提前进入长期后台运行系统。

## Goals

v3.4 必须实现：

- 创建 queue item。
- 查看 queue 状态。
- 显式执行队列中的下一个 item。
- 暂停和恢复 queue item。
- 失败 item 可重试。
- max chapters guard。
- timeout 标记。
- 所有 queue 动作可审计。
- JSON envelope 稳定。

## Non-Goals

v3.4 不做：

- 后台 daemon。
- 定时任务。
- 多 worker 并发。
- 分布式锁。
- Redis / Celery / Kafka。
- PostgreSQL。
- Web UI / FastAPI。
- 自动连续生产下一批。
- token 成本统计。
- provider fallback。
- 自动发布。

## Queue Model

Queue item 状态：

```text
pending
running
paused
completed
failed
timeout
cancelled
```

规则：

- `pending` 可以被 `queue-run` 执行。
- `paused` 不会被 `queue-run` 领取。
- `failed` 可以 `queue-retry`。
- `timeout` 可以 `queue-retry`。
- `completed` 不可重试。
- `cancelled` 不可自动执行。
- 同一 queue item 一次只允许一个执行过程。

## CLI Design

### 1. batch enqueue

```bash
novelos batch enqueue \
  --project-id demo \
  --from-chapter 1 \
  --to-chapter 10 \
  --priority 50 \
  --json
```

返回：

```json
{
  "ok": true,
  "error": null,
  "data": {
    "queue_id": "queue_xxx",
    "status": "pending"
  }
}
```

### 2. batch queue-run

```bash
novelos batch queue-run --once --llm-mode stub --json
```

行为：

- 领取最高优先级、最早创建的 `pending` item。
- 标记为 `running`。
- 调用现有 `Dispatcher.run_batch(project_id, from_chapter, to_chapter)`。
- 成功后标记 `completed`。
- 失败后标记 `failed` 或 `timeout`。

v3.4 只要求 `--once`，不做循环 daemon。

### 3. batch queue-status

```bash
novelos batch queue-status --project-id demo --json
```

返回：

```json
{
  "ok": true,
  "error": null,
  "data": {
    "items": [
      {
        "queue_id": "queue_xxx",
        "project_id": "demo",
        "from_chapter": 1,
        "to_chapter": 10,
        "status": "pending",
        "priority": 50,
        "attempt_count": 0
      }
    ]
  }
}
```

### 4. batch queue-pause

```bash
novelos batch queue-pause --queue-id queue_xxx --json
```

只允许暂停：

```text
pending
running
```

如果暂停 running item，v3.4 不要求中断正在执行中的 `run_batch()`，只要求在下一次队列推进前不再领取。

### 5. batch queue-resume

```bash
novelos batch queue-resume --queue-id queue_xxx --json
```

只允许恢复：

```text
paused
```

恢复后状态回到 `pending`。

### 6. batch queue-retry

```bash
novelos batch queue-retry --queue-id queue_xxx --json
```

只允许重试：

```text
failed
timeout
```

重试规则：

- `attempt_count += 1`。
- `status = pending`。
- 清空 last_error。
- 保留 previous production_run_id 审计信息。

## Database Design

新增 migration：

```text
novel_factory/db/migrations/010_v3_4_production_queue.sql
```

### production_queue

```sql
CREATE TABLE IF NOT EXISTS production_queue (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    from_chapter INTEGER NOT NULL,
    to_chapter INTEGER NOT NULL,
    priority INTEGER DEFAULT 100,
    status TEXT NOT NULL,
    production_run_id TEXT,
    attempt_count INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    timeout_minutes INTEGER DEFAULT 120,
    last_error TEXT,
    locked_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

推荐索引：

```sql
CREATE INDEX IF NOT EXISTS idx_production_queue_status_priority
    ON production_queue(status, priority, created_at);

CREATE INDEX IF NOT EXISTS idx_production_queue_project
    ON production_queue(project_id, created_at);
```

### production_queue_events

```sql
CREATE TABLE IF NOT EXISTS production_queue_events (
    id TEXT PRIMARY KEY,
    queue_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    message TEXT,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (queue_id) REFERENCES production_queue(id)
);
```

## Repository Design

至少新增：

- `create_queue_item(...)`
- `get_queue_item(queue_id)`
- `list_queue_items(project_id=None, status=None, limit=...)`
- `claim_next_queue_item()`
- `update_queue_item(...)`
- `record_queue_event(...)`
- `mark_timed_out_queue_items(now, timeout_minutes=None)`

要求：

- 所有写方法返回可判断结果。
- `UPDATE` 必须检查 rowcount。
- `claim_next_queue_item()` 必须尽量原子化。
- SQLite 下可用事务实现：先 select pending，再 conditional update `WHERE id=? AND status='pending'`。
- 不得静默失败。

## Dispatcher Design

新增：

- `enqueue_batch(...)`
- `run_queue_once(...)`
- `get_queue_status(...)`
- `pause_queue_item(queue_id)`
- `resume_queue_item(queue_id)`
- `retry_queue_item(queue_id)`
- `mark_queue_timeouts(...)`

### run_queue_once

伪流程：

```text
1. mark_queue_timeouts()
2. claim_next_queue_item()
3. 如果无 pending item，返回 ok true + status idle
4. 调用 run_batch(project_id, from_chapter, to_chapter)
5. 保存 production_run_id 到 queue item
6. run_batch ok -> queue item completed
7. run_batch ok false -> queue item failed
8. 记录 queue event
```

关键约束：

- 必须复用 `run_batch()`。
- 不得绕开 v2.1-v3.3 的 QualityHub、Skill、LLMRouter、Continuity Gate 等既有逻辑。
- queue-run 不自动 approve。
- queue-run 完成后最多进入 `awaiting_review`，后续仍需人工 review / continuity gate。

## Guards

### max chapters

CLI 必须支持：

```bash
--max-chapters 20
```

如果 `to_chapter - from_chapter + 1 > max_chapters`，拒绝 enqueue。

默认建议：

```text
max_chapters=50
```

### max attempts

每个 queue item 有 `max_attempts`。

规则：

- retry 时如果 `attempt_count >= max_attempts`，拒绝 retry。
- queue-run 执行失败时不自动 retry。

### timeout

`running` 且 `locked_at/started_at` 超过 `timeout_minutes` 的 item 应标记为 `timeout`。

v3.4 不要求后台自动扫描，只要求：

- `queue-run --once` 开始前扫描。
- `batch queue-timeouts --json` 可手动触发扫描。

## JSON Envelope Rules

所有新增 CLI 都必须稳定输出：

```json
{"ok": true, "error": null, "data": {}}
```

错误路径：

```json
{"ok": false, "error": "message", "data": {}}
```

argparse 缺参时也必须遵守 envelope。

## Test Plan

至少覆盖：

1. migration 010 可重复 `init_db()`。
2. `batch enqueue` 创建 pending queue item。
3. enqueue 超过 `--max-chapters` 被拒绝。
4. `queue-run --once` 无 pending item 返回 idle。
5. `queue-run --once` 领取 pending item 并调用 `run_batch()`。
6. `queue-run --once` 成功后 item completed。
7. `queue-run --once` 失败后 item failed。
8. `queue-pause` pending item -> paused。
9. `queue-resume` paused item -> pending。
10. paused item 不会被 queue-run 领取。
11. `queue-retry` failed item -> pending 且 attempt_count 增加。
12. 超过 max_attempts 拒绝 retry。
13. running item timeout 后变 timeout。
14. queue events 被记录。
15. 所有新 CLI `--json` 输出稳定 envelope。
16. 全量测试无回归。

## Acceptance

v3.4 通过必须满足：

- 可以创建多个 queue item。
- 可以显式执行下一个 queue item。
- queue item 可暂停、恢复、重试。
- 失败和 timeout 可审计。
- queue-run 复用 `run_batch()`。
- 不引入后台服务和外部队列。
- CLI 可运行。
- JSON envelope 稳定。
- migration 幂等。
- 全量测试通过。

## Strict Boundaries

本版本严禁加入：

- daemon 常驻进程。
- cron / scheduler。
- 并发 worker。
- Redis / Celery / Kafka。
- PostgreSQL。
- Web UI。
- 自动 approve。
- 自动进入下一批次。
- 成本统计。

这些能力留给 v3.5 或 v4。
