# v3.3 Batch Continuity Gate 开发规范

## Summary

v3.3 的目标是在 v3.0 批次生产、v3.2 批次返修闭环基础上，为整批章节增加批次级连续性审核门禁。

本版本不改变单章生产链路，不新增队列，不做 Web UI。v3.3 只在批次完成后、人工 approve 前，引入 ContinuityChecker 的批次级报告，并用结构化 gate 结果阻止存在严重连续性问题的批次被批准。

核心流程：

```text
batch run -> awaiting_review
-> batch continuity-check
-> 生成 batch continuity gate
-> 若 gate failed，则 batch review approve 被拒绝
-> 用户 request_changes 后走 v3.2 batch revise
-> 返修后可重新运行 continuity gate
-> gate passed 后允许 approve
```

## Why Now

v3.2 已经支持用户指定章节返修，但用户仍缺少批次级判断依据。多章自动创作最容易出问题的地方不是单章语句，而是跨章漂移：

- 角色状态前后不一致。
- 伏笔埋设后没有回收。
- 时间线和地点跳变。
- 多章节奏断裂或重复空转。
- 设定被某一章悄悄改写。

因此 v3.3 要把 ContinuityChecker 从“可手动调用的 sidecar”升级为“批次 review 前的质量门禁”。

## Goals

v3.3 必须实现：

- 批次级连续性检查命令。
- 批次连续性 gate 结果持久化。
- gate failed 时阻止 `batch review --decision approve`。
- gate 问题能映射到章节或章节范围。
- gate 摘要可在 batch status / review 前查询。
- 返修后可重新运行 gate，并覆盖最新 gate 状态。
- JSON envelope 稳定。

## Non-Goals

v3.3 不做：

- 自动生成 revision plan。
- 自动执行 batch revise。
- 自动 approve / publish。
- Web UI / FastAPI。
- 队列、暂停、恢复、后台 daemon。
- Redis / Celery / Kafka。
- PostgreSQL。
- 多模型 fallback。
- 重写 ContinuityChecker Agent。
- 改变 `run_chapter()` 主链路。

## Product Rules

### Gate 状态

批次连续性 gate 只允许这些状态：

```text
not_run
passed
warning
failed
error
```

含义：

- `not_run`：尚未执行 batch continuity gate。
- `passed`：无阻断问题。
- `warning`：有警告，但允许 approve。
- `failed`：存在阻断问题，不允许 approve。
- `error`：gate 执行异常，不允许 approve。

### 阻断规则

以下情况必须阻止 approve：

- gate 未运行，且批次范围超过 1 章。
- gate 状态为 `failed`。
- gate 状态为 `error`。
- continuity report 中存在 severity=`error` 的 issue。
- state_card / character / plot 任一核心一致性为 false 且 issue severity 达到 error。

以下情况允许 approve：

- gate 状态为 `passed`。
- gate 状态为 `warning`，且没有 severity=`error` 的 issue。
- 单章批次可以允许跳过 gate，但必须在返回数据中明确 `gate_required=false`。

## CLI Design

### 1. batch continuity

新增命令：

```bash
novelos batch continuity --run-id batch_xxx --llm-mode stub --json
```

行为：

- 查询 `production_runs` 获取 `project_id/from_chapter/to_chapter`。
- 调用现有 `Dispatcher.run_continuity_check()`。
- 保存 batch continuity gate 结果。
- 返回 gate 状态与 report 摘要。

返回：

```json
{
  "ok": true,
  "error": null,
  "data": {
    "run_id": "batch_xxx",
    "gate_id": "bcgate_xxx",
    "status": "passed",
    "report_id": 12,
    "issue_count": 0,
    "blocking_issues": [],
    "summary": "连续性通过"
  }
}
```

### 2. batch continuity-status

新增命令：

```bash
novelos batch continuity-status --run-id batch_xxx --json
```

返回最新 gate：

```json
{
  "ok": true,
  "error": null,
  "data": {
    "run_id": "batch_xxx",
    "gate": {
      "id": "bcgate_xxx",
      "status": "failed",
      "issue_count": 2,
      "blocking_issues": [
        {
          "chapter_range": "3-4",
          "issue_type": "state_card",
          "severity": "error",
          "description": "第4章角色等级回退"
        }
      ],
      "summary": "存在状态卡连续性问题"
    }
  }
}
```

### 3. batch review approve gate

增强现有命令：

```bash
novelos batch review --run-id batch_xxx --decision approve --json
```

如果 gate failed：

```json
{
  "ok": false,
  "error": "Batch continuity gate failed; approve is blocked",
  "data": {
    "run_id": "batch_xxx",
    "gate_status": "failed",
    "blocking_issues": []
  }
}
```

用户仍可：

```bash
novelos batch review --run-id batch_xxx --decision request_changes --notes "修复连续性问题" --json
```

## Database Design

新增 migration：

```text
novel_factory/db/migrations/009_v3_3_batch_continuity_gate.sql
```

新增表：

### batch_continuity_gates

```sql
CREATE TABLE IF NOT EXISTS batch_continuity_gates (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    from_chapter INTEGER NOT NULL,
    to_chapter INTEGER NOT NULL,
    continuity_report_id TEXT,
    status TEXT NOT NULL,
    issue_count INTEGER DEFAULT 0,
    warning_count INTEGER DEFAULT 0,
    blocking_issues_json TEXT DEFAULT '[]',
    summary TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES production_runs(id)
);
```

推荐索引：

```sql
CREATE INDEX IF NOT EXISTS idx_batch_continuity_gates_run
    ON batch_continuity_gates(run_id, created_at);

CREATE INDEX IF NOT EXISTS idx_batch_continuity_gates_project
    ON batch_continuity_gates(project_id, created_at);

CREATE INDEX IF NOT EXISTS idx_batch_continuity_gates_status
    ON batch_continuity_gates(status);
```

## Repository Design

Repository 至少新增：

- `save_batch_continuity_gate(...)`
- `get_latest_batch_continuity_gate(run_id)`
- `get_batch_continuity_gates(run_id, limit=...)`

要求：

- 写方法返回可判断结果。
- `UPDATE` 检查 rowcount。
- JSON 字段进入上层前应解析为 list/dict，或在方法注释中明确返回字符串。
- 不得静默失败。

## Dispatcher Design

Dispatcher 新增：

- `run_batch_continuity_gate(run_id)`
- `get_batch_continuity_gate_status(run_id)`
- `can_approve_batch(run_id)`

### run_batch_continuity_gate

伪流程：

```text
1. 查询 production_run
2. 校验 run 存在
3. 校验 run 状态为 awaiting_review / request_changes / approved 前可检查状态
4. 调用 run_continuity_check(project_id, from_chapter, to_chapter)
5. 从 continuity report 中提取 issues
6. 计算 gate status
7. 保存 batch_continuity_gates
8. 返回 {ok,error,data}
```

### can_approve_batch

伪流程：

```text
1. 查询 production_run
2. 单章批次 gate_required=false，可 approve
3. 查询 latest batch continuity gate
4. 无 gate -> 不允许 approve
5. gate failed/error -> 不允许 approve
6. gate warning/passed -> 允许 approve
```

### review_batch 集成

现有 `review_batch()` 在 decision=`approve` 时必须先调用 `can_approve_batch()`。

规则：

- approve 被 gate 阻止时，不得保存 human_review_session。
- approve 被 gate 阻止时，不得更新 production_run status。
- request_changes / reject 不受 gate 阻止。

## Gate Calculation

从 `ContinuityCheckerOutput.report` 中计算：

- `issue_count`：severity 为 error 或 warning 的 issue 数。
- `warning_count`：severity 为 warning 的 issue 数。
- `blocking_issues`：severity 为 error 的 issue 列表。

状态：

```text
if continuity_check_result.ok is false -> error
else if blocking_issues not empty -> failed
else if warning_count > 0 -> warning
else -> passed
```

如果 report 中有：

- `state_card_consistency=false`
- `character_consistency=false`
- `plot_consistency=false`

且没有明确 issue，v3.3 可以生成一个 synthetic blocking issue，避免 false 被忽略。

## Context / Review Integration

v3.3 不要求新增复杂 UI，但 batch status / continuity-status 必须能看到：

- latest gate status
- issue_count
- blocking issue 摘要
- report summary

如果 batch review approve 被阻止，返回中必须带 gate 摘要，方便用户下一步 `request_changes`。

## JSON Envelope Rules

所有新增 CLI 命令必须稳定输出：

```json
{"ok": true, "error": null, "data": {}}
```

错误路径：

```json
{"ok": false, "error": "message", "data": {}}
```

不得输出裸 traceback。

## Test Plan

至少覆盖：

1. migration 009 可重复 `init_db()`。
2. `run_batch_continuity_gate()` 成功保存 gate。
3. continuity 无 error issue -> gate `passed`。
4. continuity warning issue -> gate `warning`，允许 approve。
5. continuity error issue -> gate `failed`，阻止 approve。
6. continuity checker 执行失败 -> gate `error`，阻止 approve。
7. 多章批次未运行 gate 时 approve 被阻止。
8. 单章批次未运行 gate 时 approve 允许，但返回 `gate_required=false`。
9. gate failed 时 `batch review approve` 不更新 production_run，不保存 human_review_session。
10. gate failed 后 `request_changes` 仍允许。
11. 返修后重新运行 gate 可覆盖最新状态。
12. `batch continuity --json` 输出稳定 envelope。
13. `batch continuity-status --json` 输出稳定 envelope。
14. 全量测试无回归。

## Acceptance

v3.3 通过必须满足：

- 批次完成后可以运行 continuity gate。
- gate 结果持久化且可查询。
- failed/error gate 能阻止 approve。
- request_changes 不被 gate 阻止。
- continuity issue 能映射到章节或章节范围。
- batch review 返回中能看到 gate 阻断摘要。
- CLI 可运行。
- JSON envelope 稳定。
- migration 幂等。
- 全量测试通过。

## Implementation Order

建议顺序：

1. migration + Repository
2. gate status calculation helper
3. Dispatcher `run_batch_continuity_gate`
4. Dispatcher `can_approve_batch`
5. `review_batch` 集成 approve gate
6. CLI `batch continuity`
7. CLI `batch continuity-status`
8. tests

## Strict Boundaries

本版本严禁顺手加入：

- 自动生成 revision plan
- 自动执行 batch revise
- queue / pause / resume
- Web UI
- 后台 daemon
- 多 provider fallback
- token 成本统计

这些能力留给 v3.4+ 或 v4。
