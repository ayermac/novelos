# v3.2 Batch Review & Revision 开发规范

## Summary

v3.2 的目标是在 v3.0 批次生产和 v3.1 LLM 路由基础上，补齐“人工集中 review 后可指定返修范围并重新进入生产闭环”的能力。

本版本解决的核心问题不是“再多生成一批”，而是“批量生成完之后，如何只修改有问题的章节，而不误伤已经通过的章节”。

核心流程：

```text
novelos batch run
-> batch status = awaiting_review
-> human review 选择 approve / request_changes / reject
-> 如果 request_changes:
   - 指定某几章 revision
   - 或指定从某章开始 rerun_tail
   - 或指定单章 rerun
-> review notes 下发到对应章节
-> 重新运行受影响章节
-> 形成新的 batch 状态与审计记录
```

## Why Now

v3.0 已经让系统具备“自动创作多章”的能力，v3.1 已经让不同 Agent 可以走不同模型配置。

当前真正阻塞落地的，不是继续扩展模型或 Skill，而是批次后的人工干预能力还不够细：

- 用户可以知道整批需要修改。
- 但还不能精确指定“第 3 章重写”“第 5 章只润色重跑”“从第 6 章起重跑后续章节”。
- 也不能把人工 review notes 结构化地下发到下一轮 Planner / Author / Polisher。

因此 v3.2 必须先补齐 batch review revision 闭环，再进入 v3.3 的 batch continuity gate。

## Goals

v3.2 必须实现：

- 批次级人工 review 的结构化返修动作。
- 指定章节返修。
- 指定章节重跑。
- 从某章开始重跑后续章节。
- review notes 下发到对应章节上下文。
- 返修动作的持久化与审计。
- 返修后的批次状态追踪。
- CLI 命令可运行，且 JSON envelope 稳定。

## Non-Goals

v3.2 不做：

- Web UI / FastAPI。
- 自动根据 review notes 自主决定返修范围。
- 批次级连续性总闸门。
- 多批次队列、暂停、恢复。
- 后台 daemon。
- Redis / Celery / Kafka。
- PostgreSQL。
- 自动发布整批内容。
- 自动重写全书。
- 改变单章主链路 Agent 顺序。
- 大规模重写 QualityHub / Skill Package 系统。

## Product Rules

### 支持的返修动作

v3.2 只支持以下动作：

```text
approve
request_changes
reject
```

当 `decision=request_changes` 时，必须同时指定 revision plan。

revision plan 只允许以下 action：

```text
rerun_chapter
resume_to_status
rerun_tail
```

含义：

- `rerun_chapter`：重新跑某一章，且只影响该章。
- `resume_to_status`：把某一章人工恢复到指定状态，再重新跑该章。
- `rerun_tail`：从某章开始，将该章及其后续章节纳入重跑范围。

### 不允许的行为

- 不得隐式修改未选中的章节。
- 不得在 `approve` 时偷偷触发重跑。
- 不得在 `reject` 时自动删除历史批次数据。
- 不得覆盖历史 `human_review_sessions`。
- 不得丢失 review notes。

## CLI Design

### 1. batch review

保留 v3.0 现有命令，但增强 `request_changes` 输入能力。

```bash
novelos batch review \
  --run-id batch_xxx \
  --decision request_changes \
  --notes "第3章冲突不够，第5章以后节奏漂移" \
  --json
```

返回：

```json
{
  "ok": true,
  "error": null,
  "data": {
    "run_id": "batch_xxx",
    "decision": "request_changes",
    "status": "request_changes"
  }
}
```

### 2. batch revise

新增命令：

```bash
novelos batch revise \
  --run-id batch_xxx \
  --plan-json '{"actions":[{"action":"rerun_chapter","chapter":3,"notes":"冲突不足"},{"action":"rerun_tail","from_chapter":5,"notes":"后续节奏重新规划"}]}' \
  --json
```

说明：

- v3.2 主输入采用 `--plan-json`，避免过早设计复杂交互式 CLI。
- `--plan-json` 必须是合法 JSON。
- `decision` 必须已是 `request_changes`，否则拒绝执行。

返回：

```json
{
  "ok": true,
  "error": null,
  "data": {
    "run_id": "batch_xxx",
    "revision_run_id": "batchrev_xxx",
    "affected_chapters": [3, 5, 6, 7],
    "status": "running"
  }
}
```

### 3. batch revision-status

新增命令：

```bash
novelos batch revision-status --revision-run-id batchrev_xxx --json
```

返回：

```json
{
  "ok": true,
  "error": null,
  "data": {
    "revision_run_id": "batchrev_xxx",
    "source_run_id": "batch_xxx",
    "status": "completed",
    "affected_chapters": [3, 5, 6, 7],
    "items": [
      {
        "chapter_number": 3,
        "status": "completed",
        "error": null
      }
    ]
  }
}
```

## Revision Plan Schema

`--plan-json` 结构：

```json
{
  "actions": [
    {
      "action": "rerun_chapter",
      "chapter": 3,
      "notes": "冲突不足，重写中段对抗"
    },
    {
      "action": "resume_to_status",
      "chapter": 4,
      "status": "drafted",
      "notes": "保留正文，重新润色和审核"
    },
    {
      "action": "rerun_tail",
      "from_chapter": 5,
      "notes": "从第5章开始重新规划后续节奏"
    }
  ]
}
```

校验规则：

- `actions` 不能为空。
- `rerun_chapter` 必须有 `chapter`。
- `resume_to_status` 必须有 `chapter` 和 `status`。
- `resume_to_status.status` 只允许合法 chapter status。
- `rerun_tail` 必须有 `from_chapter`。
- 同一 plan 中允许多个 action，但最终受影响章节集合不得冲突或重复产生歧义。
- 若同时存在 `rerun_tail(from=5)` 和 `rerun_chapter(6)`，应归并为一个受影响集合，而不是重复执行。

## Database Design

新增 migration：

```text
novel_factory/db/migrations/008_v3_2_batch_revision.sql
```

建议新增三张表：

### batch_revision_runs

```sql
CREATE TABLE IF NOT EXISTS batch_revision_runs (
    id TEXT PRIMARY KEY,
    source_run_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    status TEXT NOT NULL,
    decision_session_id TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    affected_chapters_json TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);
```

状态建议：

```text
pending
running
completed
blocked
failed
```

### batch_revision_items

```sql
CREATE TABLE IF NOT EXISTS batch_revision_items (
    id TEXT PRIMARY KEY,
    revision_run_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    action TEXT NOT NULL,
    target_status TEXT,
    notes TEXT,
    status TEXT NOT NULL,
    workflow_run_id TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);
```

### chapter_review_notes

```sql
CREATE TABLE IF NOT EXISTS chapter_review_notes (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    source_run_id TEXT NOT NULL,
    revision_run_id TEXT NOT NULL,
    notes TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

用途：

- 不把 review notes 只塞在批次 session 里。
- 让后续章节运行时可以按章读取人工修改意见。
- 为 Planner / Author / Polisher 的上下文注入提供持久化来源。

## Dispatcher Design

Dispatcher 新增方法：

- `create_batch_revision_plan(...)`
- `run_batch_revision(...)`
- `get_batch_revision_status(...)`

### run_batch_revision 核心规则

伪流程：

```text
1. 校验 source_run 存在且状态为 request_changes
2. 校验 revision plan 合法
3. 计算 affected chapters
4. 创建 batch_revision_run
5. 为每个 affected chapter 创建 batch_revision_item
6. 写入 chapter_review_notes
7. 逐章执行修复
   - rerun_chapter: 直接调用 run_chapter
   - resume_to_status: 先 human_resume，再 run_chapter
   - rerun_tail: 从 from_chapter 到 source_run.to_chapter 顺序 run_chapter
8. 汇总状态
9. 返回 revision_run 结果
```

关键约束：

- 必须复用现有 `Dispatcher.run_chapter()` 和 `resume_blocked()`，不得重写单章主链路。
- 每个 revision item 都必须可审计。
- 失败时必须停止后续受影响章节，除非未来版本显式支持 continue 策略。

## Context Injection

v3.2 必须把人工 review notes 注入后续运行上下文，但范围要可控。

建议做法：

- `ContextBuilder` 新增读取 `chapter_review_notes` 的片段。
- Planner / Screenwriter / Author / Polisher 至少要能读到本章最新 review notes。
- `rerun_tail` 场景下，后续章节也应能看到“从某章开始重跑”的批次说明。

最小要求：

- 本章级 notes 能进入后续被重跑章节的提示词。
- 不要求在 v3.2 做复杂跨章 notes 摘要器。

## Repository Design

Repository 至少新增：

- `create_batch_revision_run()`
- `update_batch_revision_run()`
- `get_batch_revision_run()`
- `create_batch_revision_item()`
- `update_batch_revision_item()`
- `get_batch_revision_items()`
- `save_chapter_review_note()`
- `get_chapter_review_notes()`
- `get_latest_human_review_session()`

所有写方法都必须：

- 返回可判断结果。
- 检查 `rowcount`。
- 不得静默失败。

## JSON Envelope Rules

v3.2 新增 CLI 必须统一：

```json
{
  "ok": true,
  "error": null,
  "data": {}
}
```

错误路径也必须保持：

```json
{
  "ok": false,
  "error": "message",
  "data": {}
}
```

不得输出裸文本错误，除非用户未使用 `--json`。

## Test Plan

至少覆盖：

1. `batch review --decision request_changes` 可成功记录。
2. `batch revise --plan-json ...` 可创建 revision run。
3. `rerun_chapter` 只影响指定章节。
4. `resume_to_status` 会先做 human resume，再进入 `run_chapter()`。
5. `rerun_tail` 会影响从指定章节到批次末尾的所有章节。
6. 未选中的章节内容和状态不被覆盖。
7. review notes 被持久化，并能被读取。
8. revision run / items 状态可查询。
9. 任一 item 失败时，revision run 进入 `blocked` 或 `failed`。
10. 所有新命令 `--json` 输出稳定为 `{ok,error,data}`。
11. `init_db()` 重复执行不因 008 migration 出错。
12. 全量测试不回归。

## Acceptance

v3.2 通过必须满足：

- 用户可以只返修某几章。
- 用户可以从某章开始重跑后续章节。
- 未选中的章节不会被隐式覆盖。
- 人工 review notes 能进入返修闭环。
- 返修动作和结果可审计、可查询。
- CLI 命令可运行。
- `--json` 输出稳定。
- 全量测试通过。

## Implementation Order

建议实现顺序：

1. migration + Repository
2. revision plan schema
3. Dispatcher revision methods
4. CLI `batch revise`
5. CLI `batch revision-status`
6. review notes 注入
7. 测试补齐

## Strict Boundaries

本版本严禁顺手加入：

- v3.3 的 continuity batch gate
- v3.4 的 queue / pause / resume
- v3.5 的 serial plan
- Web UI
- 自动决定 revision plan 的 AI reviewer
- 批次级自动 approve / publish

如果实现时发现需要这些能力，必须停在接口预留，不得越界开发。
