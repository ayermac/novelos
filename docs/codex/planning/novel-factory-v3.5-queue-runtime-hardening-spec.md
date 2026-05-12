# v3.5 Queue Runtime Hardening 开发规范

## Summary

v3.5 的目标是在 v3.4 Production Queue MVP 之上，补齐队列运行期的诊断、取消、卡死恢复和审计查询能力。

本版本仍然不做后台 daemon、不做定时任务、不做并发 worker。所有队列推进仍由 CLI 显式触发。v3.5 要解决的是“队列跑起来以后，如何看清楚、停得住、救得回”。

核心新增能力：

```text
queue-events      查看 queue item 的审计事件
queue-cancel      取消未完成 queue item
queue-recover     恢复卡死 running item
queue-doctor      诊断队列/批次/事件链路
queue-run --limit 连续显式运行 N 个 queue item
```

## Why Now

v3.4 已经支持多个 batch 排队、显式 `queue-run --once`、暂停、恢复和失败重试。下一步如果直接做半自动连载或 daemon，会放大已有运行期问题：

- running item 卡住后无法清晰恢复。
- 用户无法直接查看 queue event。
- queue item 与 production_run / workflow_run 的链路排查成本高。
- 取消能力缺失，用户只能手动改库。
- 多个 pending item 需要手动重复执行 `queue-run --once`。

所以 v3.5 先做 runtime hardening，保持系统可控。

## Goals

v3.5 必须实现：

- queue event 查询 CLI。
- queue item cancel。
- stuck running item recover。
- queue doctor 诊断。
- `queue-run --limit N` 显式运行多个 item。
- queue item 与 production_run / workflow_run 的诊断串联。
- 更严格的 queue 状态转移矩阵测试。
- 所有 `--json` 输出稳定为 `{ok, error, data}`。

## Non-Goals

v3.5 不做：

- 后台 daemon。
- 定时任务。
- cron 集成。
- 多 worker 并发。
- 自动 enqueue 下一批。
- 自动 approve。
- 自动 publish。
- Redis / Celery / Kafka。
- PostgreSQL。
- Web UI / FastAPI。
- token 成本统计。
- provider fallback。

这些能力保留给 v3.6+ 或 v4。

## Queue State Matrix

v3.5 必须显式维护并测试队列状态转移：

| From | Action | To | Allowed |
| --- | --- | --- | --- |
| pending | queue-run claim | running | yes |
| pending | pause | paused | yes |
| pending | cancel | cancelled | yes |
| running | completed | completed | yes |
| running | failed | failed | yes |
| running | timeout | timeout | yes |
| running | recover | pending | yes, only if stuck |
| running | cancel | cancelled | yes, but does not interrupt active process |
| paused | resume | pending | yes |
| paused | cancel | cancelled | yes |
| failed | retry | pending | yes, if attempts remain |
| timeout | retry | pending | yes, if attempts remain |
| completed | retry/cancel/resume | none | no |
| cancelled | retry/resume/run | none | no |

所有非法转移必须返回：

```json
{"ok": false, "error": "...", "data": {}}
```

## CLI Design

### 1. batch queue-events

```bash
novelos batch queue-events --queue-id queue_xxx --json
```

返回：

```json
{
  "ok": true,
  "error": null,
  "data": {
    "queue_id": "queue_xxx",
    "events": [
      {
        "event_type": "enqueued",
        "from_status": null,
        "to_status": "pending",
        "message": "Batch enqueued",
        "created_at": "..."
      }
    ]
  }
}
```

要求：

- queue_id 不存在时返回 `ok=false`。
- events 按 `created_at ASC`。
- 不输出裸文本错误。

### 2. batch queue-cancel

```bash
novelos batch queue-cancel --queue-id queue_xxx --reason "manual stop" --json
```

允许取消：

```text
pending
paused
running
failed
timeout
```

不允许取消：

```text
completed
cancelled
```

说明：

- 取消 running item 不要求中断正在执行中的 Python 进程。
- 如果该 item 正在另一个 `queue-run` 中执行，v3.5 只要求状态和事件记录清楚。
- 后续 daemon/worker 中断留给 v4。

### 3. batch queue-recover

```bash
novelos batch queue-recover --queue-id queue_xxx --json
```

用途：

- 把卡死的 `running` item 恢复为 `pending`。
- 清理 `locked_at` / `started_at` / `completed_at`。
- 写入 `recovered` event。

限制：

- 只允许 `running` 状态。
- 必须满足 stuck 条件：`locked_at` 超过 item 的 `timeout_minutes`，或用户显式传 `--force`。
- `--force` 仍必须写入 event metadata。

### 4. batch queue-doctor

```bash
novelos batch queue-doctor --queue-id queue_xxx --json
```

诊断内容：

- queue item 基本信息。
- queue events。
- production_run 详情。
- production_run_items。
- workflow_runs。
- 最近 error。
- 是否存在状态不一致。

返回示例：

```json
{
  "ok": true,
  "error": null,
  "data": {
    "queue_id": "queue_xxx",
    "status": "failed",
    "production_run_id": "batch_xxx",
    "checks": [
      {"name": "has_events", "pass": true},
      {"name": "production_run_exists", "pass": true},
      {"name": "completed_has_production_run", "pass": false, "message": "..."}
    ],
    "recent_error": "..."
  }
}
```

### 5. batch queue-run --limit

```bash
novelos batch queue-run --limit 3 --llm-mode stub --json
```

行为：

- `--once` 保持兼容，等价于 `--limit 1`。
- `--limit N` 连续调用 `Dispatcher.run_queue_once()` 最多 N 次。
- 每次仍只 claim 一个 item。
- 如果遇到 `idle`，提前停止。
- 如果某个 item 返回 `ok=false`，停止后续执行。
- 返回 `runs` 数组。

返回：

```json
{
  "ok": true,
  "error": null,
  "data": {
    "limit": 3,
    "executed": 2,
    "stopped_reason": "idle",
    "runs": [
      {"queue_id": "queue_1", "status": "completed"},
      {"status": "idle"}
    ]
  }
}
```

## Repository Design

新增或补齐：

- `cancel_queue_item(queue_id, reason=None) -> bool`
- `recover_queue_item(queue_id, force=False) -> bool`
- `get_queue_diagnostics(queue_id) -> dict`
- `get_queue_item_with_events(queue_id) -> dict | None`

也可以不新增这些方法，而是在 Dispatcher 中组合已有 Repository 方法；但必须保证：

- 所有写入返回可判断结果。
- 所有 UPDATE 检查 `rowcount > 0`。
- 所有状态变化写 event。
- event 写入失败不得静默。

## Dispatcher Design

新增：

- `get_queue_events(queue_id)`
- `cancel_queue_item(queue_id, reason=None)`
- `recover_queue_item(queue_id, force=False)`
- `doctor_queue_item(queue_id)`
- `run_queue(limit=1)`

要求：

- `run_queue(limit=1)` 复用 `run_queue_once()`，不复制 queue-run 逻辑。
- cancel / recover 必须遵守状态矩阵。
- doctor 不修改状态。
- doctor 即使发现不一致，也只报告，不自动修复。

## Diagnostics Checks

`queue-doctor` 至少包含：

- `queue_item_exists`
- `has_events`
- `status_has_valid_transition`
- `running_has_locked_at`
- `completed_has_production_run`
- `failed_has_error`
- `production_run_exists`
- `production_run_items_exist`
- `workflow_runs_exist`

检查失败不代表 CLI 失败。只要 doctor 自身执行成功，返回 `ok=true`，并把失败检查放在 `data.checks`。

## JSON Envelope

所有新增命令都必须输出：

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

新增 `tests/test_v35_queue_runtime_hardening.py`，至少覆盖：

1. `queue-events` 返回事件列表。
2. queue_id 不存在时 `queue-events` 返回 `ok=false`。
3. pending item 可以 cancel。
4. paused item 可以 cancel。
5. running item 可以 cancel，并写 event。
6. completed item 不可 cancel。
7. cancelled item 不可 retry/resume/run。
8. running stuck item 可以 recover。
9. running 未超时 item 不可 recover。
10. `recover --force` 可以恢复未超时 running item。
11. recover 清理 locked_at / started_at / completed_at。
12. recover 写 event。
13. `queue-doctor` 返回 checks。
14. doctor 对 completed 但无 production_run_id 能报告失败检查。
15. `queue-run --limit 1` 等价于 once。
16. `queue-run --limit 3` 可连续执行多个 pending item。
17. `queue-run --limit` 遇到 idle 提前停止。
18. `queue-run --limit` 遇到失败停止。
19. CLI JSON envelope 覆盖所有新增命令。
20. argparse 缺参 JSON envelope。
21. 全量测试通过。

## Acceptance Criteria

v3.5 通过必须满足：

- v3.4 队列能力无回归。
- 用户可以查看 queue item 的事件历史。
- 用户可以取消未完成 queue item。
- 用户可以恢复卡死 running item。
- 用户可以诊断 queue item 与 production_run / workflow_run 的链路。
- 用户可以显式运行最多 N 个 queue item。
- 所有新增状态变化有 event。
- 所有写入失败返回 `ok=false`。
- 全量测试通过。

## Delivery Report

开发完成后必须汇报：

1. 修改文件。
2. 新增文件。
3. 是否新增 migration。
4. 新增 CLI 命令。
5. 新增测试数量。
6. 全量测试数量与结果。
7. 真实 CLI 验证命令与结果。
8. 是否严格遵守禁止范围。
9. 未完成项或风险。

