# v5.5.12 LLM Runtime Reliability & Cost Guardrails / LLM 运行可靠性与成本护栏

## 目标

解决真实生产中最影响体验的三类问题：

1. LLM 临时限流或超时不应直接把章节生产打死。
2. 章节运行失败后 workflow run 必须明确收口，不能留下“看起来还在跑”的旧状态。
3. 自动生产必须有 token 预算上限，避免用户看不见的循环消耗。

本版本不是再包装 UI 文案，而是收紧运行时语义：失败要可恢复，预算要能停机，旧运行要能作废。

## 范围

### A. LLM 调用重试与超时配置

- `LLMConfig` 新增：
  - `request_timeout_seconds`
  - `retry_attempts`
  - `retry_min_seconds`
  - `retry_max_seconds`
- `OpenAICompatibleProvider` 使用 `tenacity.Retrying` 对 `RateLimitError` 和 `LLMTimeoutError` 做指数退避。
- timeout 文案使用配置值，避免固定写死 60 秒。
- 非临时错误（API key、余额不足、输出校验失败）不做盲目重试。

### B. Workflow token 预算

- `Settings.runtime_budget` 新增：
  - `chapter_token_limit`
  - `project_token_limit`
  - `auto_run_token_limit`
- `FactoryState` 注入：
  - `chapter_token_limit`
  - `project_token_limit`
  - `project_tokens_before_run`
- 每个 agent 节点累计 token 后立即执行预算检查。
- 超预算时返回 `TOKEN_BUDGET_EXCEEDED`，设置 `requires_human=true`，并把 workflow run 标记为 failed/blocked，不留下 running 假象。
- 项目总预算会包含历史 workflow run 的 token 用量。

### C. Auto-run session token 预算

- `RunAutoRequest` 新增 `max_session_tokens`。
- SSE / POST / start stream URL 都透传该字段。
- 自动生产 step 结果携带 `total_tokens`，session 级累计 `session_tokens_used`。
- 超过 session 预算后以 `stop_reason=token_budget_exceeded` 停止。
- final payload 返回：
  - `session_tokens_used`
  - `max_session_tokens`

### D. 旧运行作废

- 章节 reset / run recovery reset / auto-run recovery reset 会作废同章节旧 `running` workflow run。
- 被作废的 run 标记为 `blocked`，写入明确错误：
  - `章节已重置，旧运行已作废，请重新开始新的工作流。`
- 同时清理 checkpoint，避免旧状态继续推进。

## 验收标准

- LLM provider 遇到 rate limit 后按指数退避重试，并保留 token usage。
- 单章 token 超预算时，章节运行返回 `TOKEN_BUDGET_EXCEEDED`，workflow run 不再保持 running。
- 项目 token 超预算时，历史 run token 会被计入总量。
- Auto-run 超过 `max_session_tokens` 或配置的 `auto_run_token_limit` 后停止，返回 `token_budget_exceeded`。
- 章节 reset 后，旧 running run 不再继续显示为正在工作。

## 测试

- `tests/test_v5512_llm_runtime_reliability.py`: 4 passed
- 覆盖：
  - rate limit retry
  - chapter token budget
  - project token budget
  - auto-run session token budget
- 回归：
  - v5.5.5-v5.5.10 自动生产链路
  - v5.2 / v5.5 run recovery

## 非目标

- 不新增自动发布。
- 不新增云端队列。
- 不实现复杂 token 成本计价，只做 token 数量护栏。
- 不重构全部 agent 为原生 async；API 层继续用线程隔离同步 LangGraph 运行，避免阻塞 FastAPI 事件循环。
