# v5.5.8 Auto-Run Control Loop 规格

## 目标

在 v5.5.7 实时自动生产监控的基础上，补齐"真正的控制能力"：停止/取消、运行历史、暂停/继续、失败步骤重试。让生产指挥台从"能看见"升级成"能控制、能回看、能恢复"。

## 范围

### 1. 后端：自动生产会话与控制接口

新增轻量会话控制层，持久化到 SQLite：

- `auto_run_sessions` 表：session 配置和状态
- `auto_run_steps` 表：每步执行记录

**新增 API：**

- `POST /api/projects/{project_id}/production/run-auto/start`
  - 创建 auto-run session，返回 session_id + stream_url
- `GET /api/projects/{project_id}/production/run-auto/sessions`
  - 列出最近 sessions
- `GET /api/projects/{project_id}/production/run-auto/sessions/{session_id}`
  - 查看 session 详情与 steps
- `POST /api/projects/{project_id}/production/run-auto/sessions/{session_id}/cancel`
  - 标记取消，generator 在下一步检查到后停止
- `POST /api/projects/{project_id}/production/run-auto/sessions/{session_id}/pause`
  - 标记暂停，协作式暂停
- `POST /api/projects/{project_id}/production/run-auto/sessions/{session_id}/resume`
  - 恢复暂停的 session，返回新的 stream_url
- `POST /api/projects/{project_id}/production/run-auto/sessions/{session_id}/retry-step`
  - 重试指定失败步骤

**修改现有 API：**

- `GET /production/run-auto/stream` 支持 `session_id` query 参数
- `_auto_run_generator` 支持可选的 `session_id`，添加协作式 pause/cancel 检查点和 step 持久化

### 2. 控制语义

- **cancel**：设置 session status=cancelled。generator 在 while 循环顶部检查到后 yield `auto_run_stopped(stop_reason='cancelled')` 并 return。是真正的控制语义。
- **pause**：设置 session status=paused。generator 在下一步检查到后 yield `auto_run_stopped(stop_reason='paused')` 并 return。属于协作式暂停（不硬中断正在执行的 LLM 调用）。
- **resume**：resume 端点设置 status=running，返回新的 stream_url。客户端重新连接 SSE 继续执行。
- **retry-step**：读取失败 step 的 action，使用当前项目状态重新执行 `_execute_auto_step`。不绕过安全门，不自动发布。

### 3. 前端：Production Command Center 增强

修改 `ProjectOverviewModule.tsx`：

- 自动生产运行时显示 pause / cancel / 停止监听 按钮
- pause 后显示"继续自动生产"按钮
- 实时运行时显示 session 状态（通过 stream 事件）
- 新增"自动生产历史"折叠面板，显示时间、状态、范围、steps 数、stop_reason
- 保持现有控制台视觉风格

### 4. 测试

新增 `tests/test_v558_auto_run_control_loop.py`，覆盖：
- start 创建 session
- cancel 停止后续步骤
- pause 后停止
- resume 能继续
- session history 可查询
- retry-step 对失败步骤有效
- real mode 缺 API key -> LLM_CONFIG_MISSING
- 向后兼容（不带 session_id 的 SSE/POST）

### 5. 验证

后端：
```bash
python3 -m pytest tests/test_v558_auto_run_control_loop.py tests/test_v557_realtime_production_monitor.py tests/test_v555_autonomous_production_runner.py tests/test_v554_real_llm_autonomous_planning.py tests/test_v553_autonomous_production_loop.py -q
python3 -m pytest -q
```

前端：
```bash
cd frontend
npm run typecheck
npm run lint
npm run build
```

### 6. 安全边界

- 不改变自动生产安全语义：不自动发布章节
- cancel 是真正的控制语义，不只是前端断开监听
- pause/resume 是协作式的，明确说明不硬中断 inflight LLM 调用
- retry-step 不能绕过安全门

## Review 自查

- cancel 是否真能阻止后续 step
- pause/resume 是否不会把状态搞乱
- retry-step 是否不会绕过安全门
- 运行历史是否能真实回看
- 前端按钮在各状态下可用性是否正确
- 有没有破坏 v5.7 的 SSE 实时监控
- 有没有自动发布或语义分叉
