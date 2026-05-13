# v5.5.7 Real-Time Production Monitor 规格

## 目标

将 v5.5.5 的自动生产从「一次 HTTP 调用，等最终结果」升级为「实时生产监控」：用户点击开始自动生产后，可以实时看到每个 step 的开始、完成、失败和最终停止原因。

v5.5.7 重点做 streaming + UI 实时追加，不做复杂持久化和真正后端取消任务。

## 范围

### 1. 后端新增 SSE endpoint

- **新增 endpoint**: `GET /api/projects/{project_id}/production/run-auto/stream`
- **Query 参数**:
  - `chapter_start?: int`
  - `chapter_end?: int`
  - `max_steps?: int = 10`
  - `dry_run?: bool = false`
  - `stop_on_review?: bool = true`
  - `confirm?: bool = false`
- 未 `confirm=true` 时发送 `auto_run_error` event，code 为 `CONFIRM_REQUIRED`
- 不破坏已有 `POST /production/run-auto`
- 复用 v5.5.5 现有 `_execute_auto_step()`、range guard、LLM warning normalization、stop reason 常量
- 核心逻辑提取到 `_auto_run_generator()` async generator，POST 和 SSE 共用同一套核心决策/执行逻辑

### 2. SSE 事件格式

标准 SSE 事件：

```text
event: auto_run_started
data: {...}

event: step_started
data: {...}

event: step_completed
data: {...}

event: step_failed
data: {...}

event: auto_run_stopped
data: {...}

event: auto_run_completed
data: {...}

event: auto_run_error
data: {...}
```

每个 data 至少包含：
- `project_id`
- `step`
- `action`
- `label`
- `target_chapter`
- `result`
- `warnings`
- `error`
- `stop_reason`
- `steps_executed`
- `chapters_touched`

事件顺序要求：
- 开始时发送 `auto_run_started`
- 每步执行前发送 `step_started`
- 每步成功/跳过发送 `step_completed`
- 每步失败发送 `step_failed`，随后发送 `auto_run_stopped`
- max_steps、review_required、blocked、completed、unsupported_action 都要发送最终 stop/completed 事件
- dry_run 至少发送 started + step_completed(result=dry_run) + completed/stopped
- real mode 缺 API key 发送 `auto_run_error`，code=`LLM_CONFIG_MISSING`
- 严禁自动发布章节，保持 v5.5.5 的安全语义

### 3. 前端接入实时监控

修改 `frontend/src/components/project/ProjectOverviewModule.tsx`：
- Production Command Center 中「开始自动生产」优先使用 SSE endpoint
- 运行时实时追加 steps timeline
- 当前 step 显示 `running` 状态
- 失败时显示 `step_failed` 详情
- 完成/停止后刷新 `production-next`
- 「预览自动生产」也接入 SSE dry_run
- 运行期间禁用主按钮/预览/开始按钮和配置输入
- 增加「停止监听」按钮：前端关闭 EventSource 即可，后端不用真正取消任务；UI 显示「已停止监听」
- 如果浏览器/环境不支持 EventSource，fallback 到原 POST `/production/run-auto`
- 处理断线/异常：显示 `NETWORK_ERROR` 或 `STREAM_ERROR`，不能静默失败
- 组件 unmount 后清理 EventSource

### 4. 类型整理

TypeScript interface：
- `AutoRunEventData`
- `AutoRunStep.result` 扩展支持 `running`
- 复用已有中文映射：stop_reason、action、result
- `running` 显示为「运行中」

### 5. 测试

新增 `tests/test_v557_realtime_production_monitor.py`，至少覆盖：
- `confirm=false` 返回/发送 `CONFIRM_REQUIRED`
- stream started event
- dry_run 事件顺序
- max_steps 事件顺序
- step_failed 事件包含 error/details
- review_required stop event
- real mode without API key -> `LLM_CONFIG_MISSING`
- 事件 data 包含 project_id/action/step/result/stop_reason/steps_executed

保留并通过：
- `tests/test_v555_autonomous_production_runner.py`
- `tests/test_v554_real_llm_autonomous_planning.py`
- `tests/test_v553_autonomous_production_loop.py`

验证命令：
```bash
python3 -m pytest tests/test_v557_realtime_production_monitor.py tests/test_v555_autonomous_production_runner.py tests/test_v554_real_llm_autonomous_planning.py tests/test_v553_autonomous_production_loop.py -q
python3 -m pytest -q
```

前端：
```bash
cd frontend
npm run typecheck
npm run lint
npm run build
```

### 6. 浏览器验收

在当前 WebUI 中打开项目首页，验证：
- 点击开始自动生产后 steps 实时追加
- 当前 step 有 running 状态
- 完成/停止后 production-next 刷新
- 停止监听按钮能关闭前端 stream，UI 显示「已停止监听」
- 移动端不溢出

### 7. 文档更新

- `README.md`
- `README.zh-CN.md`
- `AGENTS.md`
- `CLAUDE.md`
- `docs/codex/README.md`
- 新增 `docs/codex/planning/novel-factory-v5.5.7-realtime-production-monitor-spec.md`

文档说明：
- v5.5.7 是实时监控/streaming UI，不改变自动生产安全语义
- pytest baseline 如果增加测试，要更新总数
- 前端 typecheck/lint/build 结果
- 如果没有做真正后端 cancel，要明确「停止监听只关闭前端 stream，不取消后端执行」

## Review 自查

- 是否复用 run-auto 语义，避免两套逻辑分叉
- 是否所有 stop reason 都有最终事件
- 是否 step_failed 后不会继续追加成功状态
- 是否前端 unmount 清理 stream
- 是否断线不会卡 loading
- 是否没有自动发布
- 是否没有大范围无关 UI 重构
