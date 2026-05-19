# v6.6.5 Runtime Hygiene & Observability Closure 规格

## 目标

修复 Novelos 运行时信息不可信、错误信息可能泄露敏感信息、关键路径异常日志不完整、文档入口版本信息不一致的问题。让系统运行时信息可信、错误信息安全、关键异常可诊断。

范围小而硬，不做大重构。

## 核心原则

1. 不改 LangGraph 主拓扑。
2. 不重构 Editor 大方法。
3. 不重写迁移系统。
4. 不把所有 except Exception 一次性清掉。
5. 只处理运行时版本、错误脱敏、关键路径异常可观测、文档同步。
6. 所有改动必须有测试覆盖。
7. 不降低现有安全策略，不暴露 API key、Bearer token、URL userinfo、query token。

## 实施范围

### A. 统一版本来源

- 新增 `novel_factory/version.py`，常量 `__version__ = "6.6.5"`，提供 `get_version()`。
- `api_app.py` FastAPI metadata `version` 和 `description` 从统一版本读取。
- `/api/health` 从统一版本读取 `version`。
- `frontend/package.json` 同步到 `6.6.5`。
- 增加测试验证 health 和 FastAPI app metadata 使用统一版本。

### B. LLM/API 错误脱敏

- 新增 `novel_factory/security/redaction.py`，提供 `redact_sensitive_text(value: str) -> str`。
- 脱敏覆盖：
  - `sk-...` 风格 API key
  - `Bearer xxx`
  - URL userinfo：`https://user:pass@example.com`
  - query 参数：`api_key=...`、`access_token=...`、`token=...`、`key=...`
  - 常见 provider key 环境变量名：`OPENAI_API_KEY=...`、`OPENROUTER_API_KEY=...`、`DEEPSEEK_API_KEY=...`
- 在 `openai_compatible.py` 错误处理路径中使用脱敏：
  - `_handle_api_error` 中的 timeout/connection/general error message
- 用户可见错误必须安全；调试日志也不能出现原始 key。
- 增加单元测试验证脱敏效果和 LLM error wrapping 安全性。

### C. 关键路径异常可观测

范围：
- `novel_factory/api_app.py`
- `novel_factory/llm/openai_compatible.py`
- `novel_factory/workflow/runner.py`
- `novel_factory/workflow/nodes.py`
- `novel_factory/agent_runtime/base.py`

要求：
- 对关键路径 `except Exception` 做最小增强：
  - best-effort 不阻塞的，使用 `logger.warning(..., exc_info=True)` 或 `logger.debug(..., exc_info=True)`。
  - 异常会转成用户错误的，确保日志有上下文但不含敏感信息。
- 不改变业务语义。
- 不把所有 Exception 改成具体异常。
- 增加/更新测试覆盖至少一个 best-effort 异常日志行为。

### D. Health / Diagnostics 可观测信息

- `/api/health` 返回：
  - status
  - version（统一版本）
  - llm_mode
  - db_connected（布尔值，不返回完整路径）
  - timestamp（ISO 格式）
- 不返回 API key、base_url 带 secret、完整环境变量。
- 增加测试验证 health 不泄露敏感配置。

### E. 文档更新

- 更新 `docs/codex/README.md`：
  - 添加 v6.6.5 基线说明
  - 更新当前运行时版本信息
- 更新 `README.md` 和 `README.zh-CN.md`：
  - 更新版本状态
- 如 AGENTS.md 与 CLAUDE.md 存在明显版本差异：
  - 不做大篇重写
  - 只修明显错误或添加说明当前运行时版本来源

### F. 测试要求

新增 `tests/test_v665_runtime_hygiene.py`，覆盖：
1. `novel_factory.version.__version__` 存在且为 `"6.6.5"`。
2. FastAPI app metadata version 与统一版本一致。
3. `/api/health` version 与统一版本一致，包含 timestamp。
4. `redact_sensitive_text()` 能脱敏所有要求的模式。
5. LLM error wrapping 不泄露 secret。
6. health response 不包含 secret。
7. 关键 best-effort exception 日志带 exc_info 或不会静默吞掉。

回归测试：
- `python3 -m pytest tests/test_v665_runtime_hygiene.py -q`
- `python3 -m pytest tests/test_v5512_llm_runtime_reliability.py tests/test_v65_desktop_runtime.py tests/test_v66_desktop_secure_keys.py -q`
- `python3 -m pytest -q`
- `cd frontend && npm run lint && npm run typecheck && npm run build`
- `git diff --check`

## 完成标准

1. 后端运行时版本只有一个可信来源。
2. `/api/health` 和 FastAPI metadata 不再显示旧版本。
3. LLM/API 错误和日志不会泄露 API key/token/userinfo。
4. 关键运行时异常路径不再静默吞掉上下文。
5. 文档与当前运行时状态一致。
6. 全量测试通过后再提交。
