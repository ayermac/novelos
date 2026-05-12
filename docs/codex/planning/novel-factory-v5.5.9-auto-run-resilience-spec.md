# v5.5.9 Auto-Run Resilience / 自动生产恢复闭环

## 目标

把自动生产从"可控制"升级为"可恢复"：
1. 浏览器刷新后能重新接回正在运行或已暂停的 session
2. SSE 断线后能基于 session_id 恢复订阅
3. 后端明确保存并恢复当前执行点（current_step、last_event、steps）
4. 失败步骤可以更精准地重试
5. 控制台显示清晰的恢复入口、最近一步、session health

## 背景

v5.5.8 已实现：
- `start / sessions / detail / pause / resume / cancel / retry-step`
- SSE 实时监控
- session 与 step 持久化

但还不够"可恢复"：浏览器刷新、SSE 断线、页面切换、服务重启后，用户仍然很难接回自动生产现场。

## 后端改动

### 数据库

Migration `028_v5_5_9_auto_run_resilience.sql`：
- `ALTER TABLE auto_run_sessions ADD COLUMN last_event TEXT;`

### Repository (`novel_factory/db/repositories/auto_run.py`)

- `update_auto_run_session_status` 增加 `last_event` 参数
- 新增 `update_auto_run_session_max_steps(session_id, max_steps)`：resume 时扩展步数上限
- 新增 `get_active_auto_run_session(project_id)`：获取该项目最新的 running 或 paused session

### API (`novel_factory/api/routes/production.py`)

#### `_auto_run_generator` 恢复语义增强

1. **恢复执行点**：
   - 若传入 `session_id`，从 `auto_run_steps` 加载已有步骤
   - 重建 `steps` 列表、`step_count = len(existing_steps)`、`chapters_touched` 从已有步骤的 target_chapter 重建
   - `active_chapter` 从项目 `current_chapter` 重新计算（防止 pause 期间项目状态已推进）

2. **last_event 持久化**：
   - 每次 yield 关键事件（`auto_run_started`、`step_started`、`step_completed`）后
   - 调用 `repo.update_auto_run_session_status(..., last_event=event_name)`

3. **最终状态**：
   - `auto_run_stopped` / `auto_run_completed` / `auto_run_error` 时正常更新 session 状态

#### SSE stream 断开处理 (`run_auto_stream`)

`event_stream()` 生成器捕获 `asyncio.CancelledError` / `GeneratorExit`：
- 若 `session_id` 存在，将 session 标记为 `paused`，`stop_reason = "client_disconnected"`
- 这样用户刷新后可通过 resume 重新接入

#### resume 端点增强

- 接受可选的 `extra_steps` 参数（默认 5）
- 计算 `new_max_steps = session.max_steps + extra_steps`
- 更新 session 的 `max_steps` 为新值
- 允许从 `dry_run` 状态恢复（用户预览后可继续实际执行）

#### 新增 active-session 端点

```
GET /api/projects/{project_id}/production/run-auto/active-session
```

- 返回该项目最新的 running 或 paused session（含 steps）
- 前端刷新后调用此端点恢复现场

## 前端改动 (`frontend/src/components/project/ProjectOverviewModule.tsx`)

### 刷新恢复

- mount 时调用 `/active-session`
- 若有 active session，设置 `activeSessionId`
- 若状态为 paused / client_disconnected，显示"连接已断开，可重新接入"
- 若状态为 running，显示运行中步骤历史

### SSE 断线重连

- `es.onerror` 不再直接显示 error，而是：
  - `setDisconnected(true)`
  - `setStreamStatus('stopped')`
  - `setStreamError({ code: 'NETWORK_ERROR', message: 'SSE 连接失败或已断开，可重新接入' })`
- 显示"重新接入"按钮，点击后调用 `handleResumeSession`

### Session health 展示

- session 历史列表中显示 `last_event`
- 步骤时间线中实时反映步骤结果

### 失败 step 精准重试

- 步骤时间线中，对 `result === 'failed'` 的 step 显示"重试此步骤"按钮
- 点击调用 `POST /retry-step`，前端本地更新该 step 的结果

## 测试 (`tests/test_v559_auto_run_resilience.py`)

共 12 个测试：

| 测试类 | 用例 | 验证点 |
|---|---|---|
| `TestActiveSession` | `test_active_session_returns_running` | active-session 返回 running session |
| `TestActiveSession` | `test_active_session_returns_paused` | active-session 返回 paused session |
| `TestActiveSession` | `test_active_session_none_when_no_session` | 无 session 时返回 active=false |
| `TestResumeWithExtraSteps` | `test_resume_extends_max_steps` | resume 扩展 max_steps 并继续执行 |
| `TestLastEventPersistence` | `test_last_event_persisted` | session 持久化 last_event |
| `TestSessionStateReflection` | `test_session_detail_state` | detail 正确反映 current_step 和 steps |
| `TestRetryStepResilience` | `test_retry_failed_step` | 重试失败步骤成功 |
| `TestRetryStepResilience` | `test_retry_non_failed_step_rejected` | 非失败步骤重试被拒绝 |
| `TestRealModeLLMConfig` | `test_real_mode_without_api_key` | 缺 API key 返回 LLM_CONFIG_MISSING |
| `TestNoAutoPublish` | `test_no_auto_publish` | dry_run 不自动发布 |
| `TestBackwardCompatibility` | `test_post_run_auto_without_session` | 无 session_id 的 POST 仍可用 |
| `TestBackwardCompatibility` | `test_stream_without_session` | 无 session_id 的 SSE 仍可用 |

## 约束

- 不改变"不开启自动发布"的安全边界
- 不引入新的静默 fallback
- 不破坏 v5.5.7 / v5.5.8 的 SSE 和 session 语义
- 优先复用现有控制流，不要重写整套生产系统

## 验收标准

- [x] 关键回归测试全绿（1809/1809）
- [x] 前端 typecheck / lint / build 通过
- [x] 文档基线同步到 v5.5.9
- [x] 用户能在浏览器刷新、断线后重新接回自动生产
- [x] 失败步骤可定位、可重试、可追踪
