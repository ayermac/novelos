# v5.5.15 Production Readiness Closure

## 背景

v5.5.14 完成了状态真相源收口、健康修复入口和自动生产语义收口。但真实项目验收发现以下残留问题：

1. 健康摘要缺少章节状态与工作流运行状态的矛盾检测。
2. 已有 running workflow 的章节仍可被前端发起重复生成。
3. 断线 obsolete session 在 Overview 上仍可能显示为"重新接入"主 CTA。
4. README 承载了过多版本流水账和测试基线，不适合作为项目入口文档。

本版本只做生产级收口，不新增大功能。

## 目标

1. **状态一致**：Overview、章节页、工作流页、自动生产历史必须使用同一套状态真相。
2. **长任务可靠**：stale running workflow / obsolete auto-run session 不能继续误导用户。
3. **文档可信**：README 去版本化，版本基线只放 `docs/codex/`、`AGENTS.md`、`CLAUDE.md`。
4. **真实项目可验收**：以 `novel_3v2o` 为真实项目验收对象。

## 非目标

- 多 provider fallback
- 多版本生成对比
- SaaS 多用户权限
- 自动发布
- 新的小说生成能力
- 大规模 UI 重写

## 状态真相源规则

```text
workflow_run > chapter_status > auto_run_session > frontend local stream
```

### 具体约束

1. 如果章节已有 running workflow，Overview 和章节页都不能显示可重复启动生成。
2. 如果章节已 `reviewed` / `awaiting_publish` / `published`，旧 auto-run session 不能覆盖章节状态。
3. 如果 auto-run session 是 `paused + client_disconnected`，但目标章节已经推进，必须标记/识别为 obsolete。
4. auto-run session 只能解释"批量执行器状态"，不能作为章节真实状态。

## 健康摘要字段

`/projects/{project_id}/production/health-summary` 应返回：

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | `ok` / `attention` / `blocking` |
| `summary` | object | 各类问题计数 |
| `items` | array | 具体健康项（含 action） |
| `next_action` | object | 推荐的下一步操作 |

新增检测项：

| 检测项 | severity | 说明 |
|--------|----------|------|
| stale running workflow | `blocking` | 运行超过超时阈值 |
| obsolete disconnected session | `warning` | 断线 session 对应章节已推进 |
| chapter/workflow status contradiction | `blocking` | chapter_status 与 workflow_run 状态矛盾 |
| pending memory updates | `attention` | 有待处理的记忆更新 |
| blocking chapter | `blocking` | 章节处于阻塞/返修 |

每个 item 必须包含 `action_label` 和 `action_url`，让作者能理解并操作。

## 前端验收标准

1. Overview 必须调用 `/production/health-summary` 并在健康卡中显示作者可理解的 action。
2. disconnected obsolete session 不显示"重新接入"为主 CTA，改为"清理旧会话"。
3. running workflow 时禁用生成入口（按钮 disabled 或隐藏）。
4. reviewed/published 章节不显示"重新生成"为主 CTA。

## 真实项目验收清单

以 `novel_3v2o` 验收：

- [ ] Overview 不再把旧断线 session 显示为主状态
- [ ] 第 3 章若已 reviewed，主动作应是应用记忆或发布，不是重新生成/重新接入
- [ ] stale running workflow 有明确处理入口
- [ ] 待处理记忆能跳转到记忆收件箱
- [ ] 发布后继续下一章不会重复启动已有 running workflow

## 测试覆盖

### 后端测试 (`tests/test_v5515_production_readiness.py`)

1. reviewed/published 章节不会被 paused disconnected auto-run session 覆盖
2. stale running workflow 被 health-summary 报告
3. 正在 running 的目标章节不会被重复启动
4. pending memory updates 优先进入记忆收件箱
5. obsolete session action 指向明确 session 清理
6. chapter status 与 workflow run 矛盾时 health-summary 返回 blocking/attention

### 前端测试

1. Overview fetches `/production/health-summary`
2. 健康卡显示作者可理解 action
3. disconnected obsolete session 不显示"重新接入"为主 CTA
4. running workflow 禁用生成入口
5. README 不包含测试基线数字或当前版本流水账
