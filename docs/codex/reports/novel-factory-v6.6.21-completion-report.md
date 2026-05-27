# Novel Factory v6.6.21 Completion Report

Status: **Completed**

## Scope

v6.6.21 LLM JSON Resilience Hotfix 修复真实 LLM 在 JSON agent（如 screenwriter）输出非合法 JSON 时导致的工作流 blocked、日志误标和详情页不稳定的问题。

## Root Cause

真实日志中 chapter 11 screenwriter 失败：
- LLM 输出接近合法 JSON，但 parser 报 `Expecting ',' delimiter: line 1 column 350`
- `json_parse_attempt=2`, `json_parse_max_attempts=2`
- 失败后 `run_status=blocked`, `current_node=human_review`
- timeline 中 `screenwriter node_started` 被标成 error level
- `human_review node_started/node_completed` 被 error level 污染
- 存在"查看详情白屏"和"日志排序混乱"的用户反馈

## Changes

### 1. JSON Resilience Layer

新增 `novel_factory/llm/json_resilience.py`：
- `extract_json()`: 支持 Markdown code fence、前后夹文字、BOM 去除、嵌套提取
- `parse_json()`: JSON extraction + repair + 诊断信息。错误信息包含 agent_id、schema_name、attempt、error location、content preview
- `safe_parse_json()`: 不抛异常的安全版本，返回 `JSONParseResult`
- 对可安全修复问题做最小修复：尾逗号、单引号字符串、JS 注释、未引用标量值
- 对不可修复的破损 JSON 保留明确错误，不静默吞掉

### 2. 3-Tier JSON Retry

修改 `openai_compatible.py` `invoke_json()`：
- Attempt 1: 正常 JSON 输出 + `response_format={"type":"json_object"}`
- Attempt 2: 带错误信息要求模型重新输出完整合法 JSON
- Attempt 3: 只给上一次原始输出和 schema，要求"修复 JSON，不新增内容"（temperature=0）
- 兼容不支持 `response_format` 的 provider：检测 unsupported parameter 错误后 fallback 到普通调用，不消耗 JSON parse retry 次数
- `response_format_fallback=true` 诊断字段记录在 `last_call_trace.request` 中

### 2a. Review Gap: response_format Fallback (P1)

当 provider 不支持 `response_format` 参数时：
- 检测 `_RESPONSE_FORMAT_UNSUPPORTED_PATTERNS` 中的明确参数不兼容错误
- 移除 `response_format` 后重试同一次 attempt（不消耗 JSON parse retry）
- 不吞掉 auth/balance/timeout/rate-limit/connection 错误
- `last_call_trace.request.response_format_fallback` 记录 fallback 发生

### 3. Scripts Adaptations

- `provider.py` / `stub_provider.py`: `invoke_json` 增加 `agent_id` 参数
- `SelfCheckLoop.run()` 自动传递 agent_id
- `BaseAgent._invoke_json()`: 自动传递 `agent_id=self.agent_id`，对不支持 `agent_id` 参数的 test fake 做 TypeError fallback

### 3a. Review Gap: Agent ID Diagnostics (P2)

- 所有 runtime agent 的 `invoke_json` 调用改为 `self._invoke_json()`，自动传递 `agent_id=self.agent_id`
- `autonomous_planner.py` (模块级函数) 直接传 `agent_id="autonomous_planner"`，带 TypeError fallback
- `continuity_checker.py` (非 BaseAgent 子类) 直接传 `agent_id=self.agent_id`，带 TypeError fallback
- `memory_curator.py` 的 `fallback_llm.invoke_json` 同样传 `agent_id=self.agent_id`，带 TypeError fallback
- JSON parse failure 的 `OutputValidationError` 包含 agent_id 和 schema_name

### 4. Log Level Fixes

- `human_review_node`: 质量门打满/已有阻塞 → `event_type="completed", status="warning"`；意外系统错误 → `event_type="failed", status="failed"`
- `_build_node_timeline`: completed + status in {failed, error} 视为 failed（兜底历史坏数据）
- `_build_steps_timeline`: failed/blocked 步骤始终生成独立的 `info` level started 日志
- `_build_node_timeline`: null timestamp 事件稳定排在末尾

### 4a. Review Gap: human_review Timeline Status (P1)

- 意外系统错误不再使用 `event_type="completed", status="failed"` — 改为 `event_type="failed", status="failed"`
- 质量门打满/已有阻塞使用 `event_type="completed", status="warning"` — 表示预期内的人工干预
- `_build_node_timeline` 兜底识别 `completed + status in {failed, error}` 为 failed（历史兼容）
- `node_started` 仍保持 info，不因节点最终失败回填 error

### 5. Frontend Crash Guards

- `RunDetail.tsx`: `recovery.running_tasks`、`recovery.actions.*`、`memory_status` 新增安全访问
- `WorkflowTimeline.tsx`: 新增 `safePayload()` 容错；logs 按 timestamp stable sort
- null timestamp 的日志不会插到真实执行日志前面

## Test Coverage

### New Tests

- `tests/test_json_resilience.py` (11 tests):
  - `TestExtractJson`: plain JSON, code fence, explanatory text, preamble, array, BOM, nested JSON
  - `TestParseJson`: valid JSON, trailing comma repair, single-quoted repair, invalid JSON raises, attempt in error, safe_parse success/failure
  - `TestParseJsonCodeFence`: code fence JSON with/without explanation
  - `TestParseJsonTrailingComma`: trailing comma in array and object
  - `TestParseJsonUnquotedValues`: unquoted string value repair

- `tests/test_json_agent_retry.py` (16 tests):
  - `TestInvokeJsonRetry`: first attempt success, second attempt after first fail, third attempt repair only, all attempts fail with diagnostics, temperature=0 on final
  - `TestInvokeJsonResponseFormat`: response_format passed with schema, not passed without schema
  - `TestResponseFormatFallback`: fallback on unsupported response_format, fallback on raw TypeError, no fallback on auth/timeout/rate-limit/connection errors, fallback does not consume JSON retry
  - `TestAgentIdInDiagnostics`: agent_id in trace, agent_id in parse failure error message

- `tests/test_v6621_review_gaps.py` (11 tests):
  - `TestHumanReviewTimelineStatus`: quality gate maxed → completed+warning, unexpected error → failed, pre-existing block → completed+warning
  - `TestBuildNodeTimelineLegacyCompleted`: completed+failed shows as failed, completed+error shows as failed, completed+warning shows as warning, failed node started is info
  - `TestAgentIdInInvokeJson`: screenwriter/author/polisher/editor have correct agent_id

### Verification Results

```bash
python3 -m pytest -q
```

Result: **2788 passed, 1 skipped, 0 failed**

```bash
cd frontend && npm run typecheck && npm run lint && npm run build && npm test -- --run
```

Result: typecheck OK, lint OK, build OK, vitest **310 passed**

```bash
cd desktop && npm run typecheck && npm run build
```

Result: typecheck OK, build OK

```bash
python3 scripts/release_smoke.py --skip-api --json
```

Result: `{"ok": true, "version_expected": "6.6.21", "required_failed": 0}`

```bash
python3 scripts/soak_real_llm_long_chapter.py --llm-mode stub --json
```

Result: `{"ok": true, "version": "6.6.21", "result": {"status": "completed", "chapter_status": "published"}}`

## Files Changed

```
novel_factory/version.py
novel_factory/llm/json_resilience.py          (NEW)
novel_factory/llm/provider.py
novel_factory/llm/openai_compatible.py
novel_factory/llm/stub_provider.py
novel_factory/agent_runtime/base.py
novel_factory/workflow/nodes.py
novel_factory/agents/screenwriter.py
novel_factory/agents/author.py
novel_factory/agents/polisher.py
novel_factory/agents/editor.py
novel_factory/agents/continuity_checker.py
novel_factory/agents/memory_curator.py
novel_factory/agents/planner.py
novel_factory/agents/autonomous_planner.py
novel_factory/api/routes/runs.py
novel_factory/api/routes/workflow_timeline.py
frontend/package.json
frontend/package-lock.json
frontend/src/pages/RunDetail.tsx
frontend/src/components/WorkflowTimeline.tsx
frontend/src/components/__tests__/WorkflowTimeline.null-safety.test.tsx  (NEW)
frontend/src/pages/__tests__/RunDetail.null-safety.test.tsx             (NEW)
desktop/package.json
desktop/package-lock.json
tests/test_json_resilience.py                 (NEW)
tests/test_json_agent_retry.py                (NEW)
tests/test_v6621_review_gaps.py               (NEW)
AGENTS.md
CHANGELOG.md
docs/codex/README.md
docs/codex/planning/novel-factory-version-planning-index.md
docs/codex/reports/novel-factory-v6.6.21-completion-report.md
```

## Known Follow-ups

1. **Real LLM soak**: 需要 API key 验证 3-tier retry 在真实场景下的效果。
2. **Auto-fill / arc-plan JSON agents**: 当前 `invoke_json` 的增强只影响通过 `LLMProvider.invoke_json()` 调用的 Agent 路径。`auto_fill` 和 `arc_plan` 类直接使用 `invoke_text` 的路径未覆盖，后续可统一。

## Acceptance Criteria

- [x] JSON extraction/repair 覆盖 code fence、前后夹文字、尾逗号、无效 JSON 不假成功
- [x] 3-tier retry：模拟坏 JSON → 修复成功、一直坏 → blocked 且错误可诊断
- [x] `response_format={"type":"json_object"}` 传给 schema 调用，兼容无此参数的 provider
- [x] response_format fallback：不支持的 provider 自动移除并重试，不消耗 JSON parse retry
- [x] 不吞掉 auth/balance/timeout/rate-limit/connection 错误
- [x] `human_review` 进入阻塞时 level 不全是 error（warning vs error 按场景区分）
- [x] 意外系统错误 → event_type="failed"，不是 event_type="completed"+status="failed"
- [x] completed + status in {failed, error} 在 timeline 中显示为 failed（历史兼容）
- [x] `node_started` 在节点失败时保持 info level
- [x] Timeline 对 null timestamp 稳定排序
- [x] 前端对 null payload、缺失字段、超长内容不白屏
- [x] 所有 runtime agent invoke_json 传入 agent_id（test fake 兼容）
- [x] JSON parse failure 错误信息包含 agent_id 和 schema_name
- [x] 版本对齐 6.6.21（runtime + frontend + desktop package.json + lockfiles）
- [x] 测试/构建全部通过