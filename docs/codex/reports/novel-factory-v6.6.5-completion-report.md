# v6.6.5 Runtime Hygiene & Observability Closure 完成报告

## 完成状态

已完成。

## 交付内容

### A. 统一版本来源

- 新增 `novel_factory/version.py`：
  - `__version__ = "6.6.5"`
  - `get_version()` 返回版本字符串
- `novel_factory/api_app.py`：
  - FastAPI `version` 和 `description` 从 `get_version()` 读取
- `novel_factory/api/routes/health.py`：
  - `version` 从 `get_version()` 读取
  - 新增 `timestamp` 字段（ISO 8601 UTC）
- `frontend/package.json`：
  - 版本从 `"5.3.0"` 更新为 `"6.6.5"`
- `tests/test_v51_frontend_build.py`：
  - 更新前端版本断言为 `"6.6.5"`

### B. LLM/API 错误脱敏

- 新增 `novel_factory/security/redaction.py`：
  - `redact_sensitive_text(value: str) -> str`
  - 覆盖：sk-...、Bearer、URL userinfo、api_key/access_token/token/key query 参数、OPENAI_API_KEY/OPENROUTER_API_KEY/DEEPSEEK_API_KEY 环境变量赋值
  - 使用负向前瞻避免对已脱敏内容重复匹配
- `novel_factory/llm/openai_compatible.py`：
  - `_handle_api_error` 对错误消息进行脱敏后再包装为 `LLMConnectionError` / `LLMError`
  - 保留原始异常链 `raise ... from error`
- `novel_factory/api_app.py`：
  - 全局异常处理器对 `str(exc)` 进行脱敏后再返回给客户端
- `novel_factory/workflow/runner.py`：
  - `run_with_graph` 和 `run_with_graph_stream` 返回给用户的错误消息经过脱敏
  - `_validate_llm_config` 和 `_build_llm_router` 的异常也经过脱敏

### C. 关键路径异常可观测

- `novel_factory/workflow/runner.py`：
  - `logger.exception` 已包含 project/chapter 上下文
- `novel_factory/workflow/nodes.py`：
  - `_ensure_skill_registry`、`_ensure_tool_registry`、`_ensure_trace_store`：warning 日志增加 `exc_info=True`
  - `_latest_artifact_content`：debug 日志增加 `exc_info=True`
  - contract validation、context summarizer、exec events、evidence verification 的 `except Exception: pass` 增加 `logger.debug(..., exc_info=True)`
- `novel_factory/agent_runtime/base.py`：
  - `_load_role_profile`、`_get_agent_memory_context`、`_record_trace`：debug 日志增加 `exc_info=True`
  - `_compensate_status`：warning 日志增加 `exc_info=True`
  - `_get_style_bible_context`、`_get_title_contract_context`、`_get_project_skill_overrides`：增加 `logger.debug(..., exc_info=True)`

### D. Health / Diagnostics 可观测信息

- `/api/health` 返回：
  - `status`: "ok"
  - `version`: 统一版本（如 "6.6.5"）
  - `llm_mode`: stub/real
  - `db_connected`: true/false
  - `timestamp`: ISO 8601 UTC 时间戳
- 不返回任何敏感配置信息。

### E. 测试

- 新增 `tests/test_v665_runtime_hygiene.py`（29 个测试）：
  - `TestUnifiedVersion`：8 个测试验证版本统一来源和 health 端点
  - `TestRedaction`：12 个测试验证脱敏规则
  - `TestLLMErrorSafety`：2 个测试验证 LLM 错误包装不泄露 secret
  - `TestBestEffortExceptionLogging`：5 个测试验证关键路径异常可观测
  - `TestGlobalExceptionHandler`：1 个测试验证全局异常处理器脱敏
  - `TestFrontendPackageVersion`：1 个测试验证前端 package.json 版本

## 验证结果

```bash
# v6.6.5 专项测试
python3 -m pytest tests/test_v665_runtime_hygiene.py -q
# 29 passed

# 回归测试
python3 -m pytest tests/test_v5512_llm_runtime_reliability.py tests/test_v65_desktop_runtime.py tests/test_v66_desktop_secure_keys.py -q
# 21 passed

# 全量后端测试
python3 -m pytest -q
# 2268 passed

# 前端验证
cd frontend && npm run lint && npm run typecheck && npm run build
# 全部通过

# git diff 检查
git diff --check
# 通过
```

## 剩余风险

1. **未重构迁移系统**：`connection.py` 的 `_is_migration_applied_by_schema()` 仍是大型 if-elif 链，本版本未触碰。
2. **未拆分 Editor 大方法**：`agents/editor.py` 的 `_execute()` 仍是约 500 行的大方法，本版本未触碰。
3. **未全量清理 except Exception**：项目中仍有大量 `except Exception`，本版本只处理了关键运行时路径。
4. **pyproject.toml 版本未同步**：`pyproject.toml` 中 `version = "1.3.0"` 是 pip 包版本，与运行时 API 版本 `6.6.5` 不同。当前策略是保持 pip 包版本独立，运行时版本通过 `novel_factory/version.py` 统一管理。
5. **前端无版本显示 UI**：本版本未在前端新增复杂的版本显示 UI，仅同步了 `package.json` 版本号。
