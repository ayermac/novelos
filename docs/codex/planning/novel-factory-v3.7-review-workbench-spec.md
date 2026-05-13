# v3.7 Review Workbench 开发规范

## Summary

v3.7 的目标是在 v3.6 Semi-Auto Serial Mode 之后，新增“人工 Review 工作台”的 CLI 能力。

v3.6 已经可以让用户按计划分轮生产章节，但人工审核仍然需要在多个命令和多张表之间来回查：

- queue item 是否完成。
- production run 是否等待 review。
- continuity gate 是否通过。
- quality report 是否有阻断项。
- chapter version 是否发生变化。
- revision notes 是否已经下发。
- serial plan 当前推进到哪里。

v3.7 不做 Web UI，而是提供一组本地 CLI 命令，把这些信息汇总为结构化 review pack，帮助用户在“确认 approve / request_changes / pause / cancel”前快速判断当前批次是否可接受。

核心能力：

```text
review pack       -> 汇总某个 batch / serial plan / 章节范围的审核包
review chapter    -> 查看单章审核视图
review timeline   -> 查看 serial / queue / batch / revision / quality 事件时间线
review diff       -> 查看章节版本差异摘要
review export     -> 导出 markdown / json 审核包
```

## Why Now

v3.0-v3.6 已经完成了从单章生产到半自动连载计划的后端闭环：

- v3.0：批次生产。
- v3.2：批次返修。
- v3.3：批次连续性门禁。
- v3.4：生产队列。
- v3.5：队列运行时硬化。
- v3.6：半自动连载计划。

下一步最大的瓶颈不再是“能不能跑”，而是“人如何高效、可靠地判断这一轮能不能过”。

v3.7 的价值是把系统已有的审计数据、质量数据和内容版本组织成可读视图，让人工 review 变得可执行，而不是让用户自己查数据库。

## Goals

v3.7 必须实现：

- 面向人工审核的 review pack 汇总。
- 单章 review 视图。
- 批次 / serial plan 级时间线。
- 章节版本 diff 摘要。
- Markdown / JSON 导出。
- JSON envelope 稳定。
- 不改变任何生产状态。
- 不自动 approve。
- 不自动生成 revision plan。
- 不替代 v3.2 / v3.3 / v3.6 的决策流程，只提供审核辅助信息。

## Non-Goals

v3.7 不做：

- Web UI / FastAPI。
- daemon / cron。
- 自动 approve。
- 自动 publish。
- 自动 request_changes。
- 自动生成 revision plan。
- 新增 Agent。
- 新增 LLM 调用。
- Redis / Celery / Kafka。
- PostgreSQL。
- 多用户权限系统。
- 云端部署。
- token 成本统计。

这些能力留给 v4 或后续生产治理版本。

## Design Principles

### 1. 只读优先

Review Workbench 默认只读，不改变：

- chapter status。
- production run status。
- queue item status。
- serial plan status。
- revision run status。

如果未来需要在 review pack 里直接写入人工决策，必须另开版本。

### 2. 汇总已有数据，不重复造状态

v3.7 不新增复杂业务状态。优先复用：

- `chapters`
- `chapter_versions`
- `workflow_runs`
- `agent_artifacts`
- `reviews`
- `quality_reports`
- `skill_runs`
- `production_runs`
- `production_run_items`
- `human_review_sessions`
- `batch_revision_runs`
- `batch_revision_items`
- `chapter_review_notes`
- `batch_continuity_gates`
- `production_queue`
- `production_queue_events`
- `serial_plans`
- `serial_plan_events`

### 3. 输出可给人读，也可给脚本读

所有命令支持：

- `--json`：稳定 `{ok,error,data}` envelope。
- `--format markdown`：适合人工阅读和归档。
- `--output path`：写入文件。

### 4. 不让用户猜

review pack 必须明确给出：

- 当前对象是否可 approve。
- 如果不可 approve，阻断原因是什么。
- 如果建议 request_changes，原因来自哪里。
- 哪些章节有质量风险。
- 哪些章节发生过返修。
- 哪些检查没有运行。

## Data Model

v3.7 默认不新增 migration。

如果实现中确实需要持久化导出记录，只允许新增轻量表：

```text
review_exports
```

但 v3.7 MVP 不要求该表。优先让 export 命令直接生成文件，不落库。

## Repository Requirements

Repository 需要补充只读查询方法。方法命名可按现有风格调整，但必须覆盖以下能力：

```python
get_review_pack_for_run(run_id: str) -> dict | None
get_review_pack_for_serial(serial_plan_id: str) -> dict | None
get_review_pack_for_range(project_id: str, from_chapter: int, to_chapter: int) -> dict
get_chapter_review_view(project_id: str, chapter: int) -> dict | None
get_chapter_version_diff(project_id: str, chapter: int, from_version: str | None, to_version: str | None) -> dict
get_timeline_events(scope_type: str, scope_id: str) -> list[dict]
```

要求：

- 查询方法不得改变 DB。
- 查询失败时返回空结构或清晰错误，不得 traceback。
- 时间线必须按 `created_at` / `updated_at` 升序稳定排序。
- 缺失对象必须返回可解释错误。

## Dispatcher Requirements

新增只读方法：

```python
build_review_pack(...)
get_review_chapter(...)
get_review_timeline(...)
get_review_diff(...)
export_review_pack(...)
```

### build_review_pack

支持三种入口，至少实现其中两种：

```text
--run-id
--serial-plan-id
--project-id + --from-chapter + --to-chapter
```

优先级：

```text
run-id > serial-plan-id > project range
```

返回结构示例：

```json
{
  "ok": true,
  "error": null,
  "data": {
    "scope": {
      "type": "production_run",
      "id": "batch_xxx",
      "project_id": "demo",
      "from_chapter": 1,
      "to_chapter": 3
    },
    "decision_hint": {
      "can_approve": false,
      "blocking_reasons": [
        "continuity_gate_not_run",
        "chapter_2_quality_blocking"
      ],
      "warnings": []
    },
    "chapters": [
      {
        "chapter": 1,
        "status": "published",
        "word_count": 2400,
        "latest_version_id": "ver_xxx",
        "quality": {
          "latest_score": 82,
          "pass": true,
          "blocking_count": 0,
          "warning_count": 2
        },
        "review": {
          "latest_score": 85,
          "passed": true,
          "revision_target": null
        },
        "notes_count": 0
      }
    ],
    "continuity_gate": {
      "status": "warning",
      "issue_count": 1
    },
    "timeline": []
  }
}
```

### decision_hint

`decision_hint.can_approve` 是辅助判断，不写状态。

必须阻断 approve 的情况：

- 多章节 batch 未运行 continuity gate。
- continuity gate 为 `failed` 或 `error`。
- 任一章节存在 latest quality report `pass=false`。
- 任一章节最新 Editor review `passed=false`。
- production run status 为 `request_changes` / `failed` / `blocked`。
- queue item 未 completed。

允许 approve 但要 warning 的情况：

- continuity gate 为 `warning`。
- quality report 有 warning 但无 blocking。
- 有人工 notes 尚未在后续版本中体现。
- 存在返修历史。

### get_review_chapter

返回单章视图：

- 章节基础信息。
- 最新正文摘要。
- 最新版本。
- 最近 N 个版本。
- 最新 review。
- 最新 quality report。
- skill run 摘要。
- review notes。
- artifacts 摘要。

不得输出整章全文到默认 stdout。默认只输出：

- `content_preview`，最多 800 字。
- `word_count`。
- `latest_version_id`。

如需导出全文，必须通过 `review export`。

### get_review_timeline

支持：

```text
--run-id
--serial-plan-id
--queue-id
--chapter
```

时间线事件来源：

- workflow_runs
- production_queue_events
- serial_plan_events
- batch_revision_items
- batch_continuity_gates
- human_review_sessions
- quality_reports

事件结构：

```json
{
  "time": "2026-04-25T12:00:00",
  "source": "serial_plan_events",
  "type": "approved",
  "status": "active",
  "message": "Batch approved",
  "ref_id": "event_xxx"
}
```

### get_review_diff

支持比较：

- 最新版本 vs 上一版本。
- 指定 `--from-version` 与 `--to-version`。

MVP 不要求复杂逐字 diff，可实现摘要型 diff：

- word_count_delta。
- changed_ratio。
- added_preview。
- removed_preview。
- from_version_id。
- to_version_id。

不得引入大依赖。可用 Python 标准库 `difflib`。

### export_review_pack

支持：

```text
--format json
--format markdown
--output path
```

要求：

- 默认不覆盖已有文件，除非传 `--force`。
- 输出路径父目录不存在时返回清晰错误。
- JSON export 必须是 review pack 的 `data`。
- Markdown export 必须包含：
  - 标题。
  - scope。
  - decision hint。
  - chapter summary table。
  - continuity gate。
  - blocking issues。
  - warnings。
  - timeline。

## CLI Design

新增命令组：

```bash
novelos review ...
```

### review pack

```bash
novelos review pack --run-id batch_xxx --json
novelos review pack --serial-plan-id serial_xxx --json
novelos review pack --project-id demo --from-chapter 1 --to-chapter 10 --json
```

### review chapter

```bash
novelos review chapter --project-id demo --chapter 3 --json
```

### review timeline

```bash
novelos review timeline --serial-plan-id serial_xxx --json
novelos review timeline --run-id batch_xxx --json
novelos review timeline --queue-id queue_xxx --json
novelos review timeline --project-id demo --chapter 3 --json
```

### review diff

```bash
novelos review diff --project-id demo --chapter 3 --json
novelos review diff --project-id demo --chapter 3 --from-version ver_a --to-version ver_b --json
```

### review export

```bash
novelos review export \
  --run-id batch_xxx \
  --format markdown \
  --output ./review-pack.md
```

## JSON Envelope

所有 `--json` 输出必须稳定：

```json
{
  "ok": true,
  "error": null,
  "data": {}
}
```

错误路径：

```json
{
  "ok": false,
  "error": "message",
  "data": {}
}
```

不得输出：

- 裸 traceback。
- `success` 字段。
- 缺失 `data` 字段。
- `data: null`。

## Markdown Output

Markdown 示例：

```markdown
# Review Pack: demo chapters 1-3

## Decision Hint

- Can approve: no
- Blocking:
  - continuity_gate_not_run
  - chapter_2_quality_blocking

## Chapters

| Chapter | Status | Words | Quality | Review | Notes |
| --- | --- | ---: | --- | --- | ---: |
| 1 | published | 2400 | pass 82 | pass 85 | 0 |

## Timeline

- 2026-04-25T12:00:00 serial created
- 2026-04-25T12:05:00 queue completed
```

## Validation Rules

### Scope Validation

- `review pack` 必须且只能指定一种 scope：
  - `--run-id`
  - `--serial-plan-id`
  - `--project-id + --from-chapter + --to-chapter`
- `from_chapter <= to_chapter`。
- range 最大默认 50 章，超过必须返回错误。
- 缺失对象返回 `ok=false`。

### Read Safety

- 所有命令不得改变业务状态。
- 测试中应验证执行前后相关状态不变。

### Export Safety

- `--output` 已存在且未传 `--force` 时必须失败。
- `--output` 父目录不存在时必须失败。
- `--format` 只允许 `json` / `markdown`。

## Test Plan

新增测试文件：

```text
tests/test_v37_review_workbench.py
```

必须覆盖：

1. `review pack --run-id` 返回章节、quality、continuity、decision_hint。
2. `review pack --serial-plan-id` 能聚合 serial plan 当前 queue/run。
3. `review pack --project-id --from-chapter --to-chapter` 能按范围聚合。
4. 多章节未跑 continuity gate 时 `decision_hint.can_approve=false`。
5. continuity gate `failed/error` 时不可 approve。
6. continuity gate `warning` 时可 approve 但有 warning。
7. quality report `pass=false` 时不可 approve。
8. latest review `passed=false` 时不可 approve。
9. queue item 未 completed 时不可 approve。
10. `review chapter` 默认只返回 preview，不输出整章全文。
11. `review timeline` 事件按时间升序。
12. `review diff` 可比较最新两版。
13. `review diff` 指定不存在 version 返回 envelope。
14. `review export --format markdown` 写入文件。
15. `review export --format json` 写入文件。
16. `review export` 不覆盖已有文件。
17. `review export --force` 可以覆盖已有文件。
18. 所有 `--json` 错误路径是 `{ok,error,data}`。
19. 所有 review 命令执行前后不改变 production/queue/serial/chapter 状态。
20. 全量测试通过。

## CLI Real Verification

开发完成后必须真实执行：

```bash
python3 -m novel_factory.cli --db-path /tmp/v37.db seed-demo --project-id demo --json
python3 -m novel_factory.cli --db-path /tmp/v37.db review chapter --project-id demo --chapter 1 --json
python3 -m novel_factory.cli --db-path /tmp/v37.db review pack --project-id demo --from-chapter 1 --to-chapter 1 --json
python3 -m novel_factory.cli --db-path /tmp/v37.db review export --project-id demo --from-chapter 1 --to-chapter 1 --format markdown --output /tmp/v37-review.md
```

输出必须无 traceback。

## Acceptance Criteria

v3.7 通过标准：

- 全量测试通过。
- 新增专项测试不少于 20 个。
- `novelos review pack/chapter/timeline/diff/export` 可运行。
- 所有 JSON 输出稳定 envelope。
- 默认不输出整章全文。
- review 命令不改变生产状态。
- export 安全策略正确。
- 无新增 migration，除非开发汇报说明必要性。
- 不引入禁止范围能力。

## Developer Report Template

开发 Agent 完成后必须汇报：

```text
## v3.7 开发汇报

### 修改文件
- ...

### 新增文件
- ...

### 新增 migration
- 无 / 有，说明原因

### 新增 CLI 命令
- ...

### 新增测试
- ...

### 全量测试结果
- ...

### 真实 CLI 验证
- ...

### 是否遵守禁止范围
- ...

### 未完成项或风险
- ...
```

