# v6.6.5 Runtime Hygiene & Observability Closure Review

## Review 检查项

### A. 统一版本来源

| 检查项 | 状态 | 说明 |
|--------|------|------|
| `novel_factory/version.py` 存在且版本为 "6.6.5" | ✅ | 已创建 |
| `api_app.py` 使用 `get_version()` | ✅ | FastAPI metadata 和 description 均使用 |
| `health.py` 使用 `get_version()` | ✅ | 返回统一版本 |
| `desktop/runtime-info` 使用 `get_version()` | ✅ | Follow-up 修复（原硬编码 6.8.0-m6） |
| CLI `--version` 使用 `get_version()` | ✅ | Follow-up 修复（原输出 package metadata 1.3.0） |
| `frontend/package.json` 同步到 6.6.5 | ✅ | 已更新 |
| 测试覆盖版本一致性 | ✅ | `test_v665_runtime_hygiene.py::TestUnifiedVersion` + `TestDesktopRuntimeInfo` + `TestCLIVersion` |

### B. LLM/API 错误脱敏

| 检查项 | 状态 | 说明 |
|--------|------|------|
| `security/redaction.py` 存在且功能完整 | ✅ | 覆盖所有要求的模式 |
| `openai_compatible.py` 错误消息脱敏 | ✅ | `_handle_api_error` 使用 `redact_sensitive_text` |
| `api_app.py` 全局异常处理器脱敏 | ✅ | `str(exc)` 经过脱敏 |
| `runner.py` 返回用户的错误脱敏 | ✅ | `safe_error = redact_sensitive_text(str(e))` |
| 不吞掉原异常链 | ✅ | 保留 `raise ... from error` |
| 测试覆盖脱敏效果 | ✅ | `TestRedaction` 16 个测试 + `TestLLMErrorSafety` 2 个测试 |

### C. 关键路径异常可观测

| 检查项 | 状态 | 说明 |
|--------|------|------|
| `runner.py` 关键异常带上下文 | ✅ | `logger.exception` 包含 project/chapter |
| `nodes.py` best-effort 异常不静默 | ✅ | 多处 `except Exception: pass` 增加 `logger.debug(..., exc_info=True)` |
| `base.py` best-effort 异常不静默 | ✅ | `_load_role_profile`、`_compensate_status` 等增加 `exc_info=True` |
| 不改变业务语义 | ✅ | 原来不阻塞的仍不阻塞 |
| 测试覆盖 | ✅ | `TestBestEffortExceptionLogging` 5 个测试 |

### D. Health / Diagnostics

| 检查项 | 状态 | 说明 |
|--------|------|------|
| health 返回 version | ✅ | 使用统一版本 |
| health 返回 timestamp | ✅ | ISO 8601 UTC |
| health 返回 llm_mode | ✅ | 已有 |
| health 返回 db_connected | ✅ | 布尔值，不泄露路径 |
| health 不返回 secret | ✅ | 测试验证 |

### E. 文档

| 检查项 | 状态 | 说明 |
|--------|------|------|
| spec 文档 | ✅ | `docs/codex/planning/novel-factory-v6.6.5-runtime-hygiene-observability-closure-spec.md` |
| completion report | ✅ | `docs/codex/reports/novel-factory-v6.6.5-completion-report.md` |
| review 文档 | ✅ | 本文档 |
| docs/codex/README.md 更新 | ⚠️ | 待更新 |
| README.md / README.zh-CN.md 更新 | ⚠️ | 待更新 |
| AGENTS.md / CLAUDE.md 同步 | ⚠️ | 待更新 |

## 发现的问题

1. **TestClient 对 sync endpoint 的异常行为**：在编写 `TestGlobalExceptionHandler` 时，发现 `TestClient` 对同步 endpoint 的未处理异常会直接抛出 `ValueError` 而不是返回 500 响应。改为通过 `app.exception_handlers[Exception]` 直接调用处理器进行测试。
2. **脱敏 regex 顺序问题**：早期实现中，通用 `[A-Z_]*API_KEY=[^\s]+` 模式在特定模式之后运行，导致 `OPENAI_API_KEY=***` 被二次匹配为 `API_KEY=***`。修复方式：移除通用模式，使用负向前瞻避免对已脱敏内容重复匹配。
3. **sk- key 长度要求**：早期 `sk-[a-zA-Z0-9]{20,}` 要求 20+ 字符，导致短测试 key 无法匹配。放宽为 `sk-[a-zA-Z0-9_-]+`。
4. **版本来源不统一（已修复）**：初始提交后 review 发现 `desktop/runtime-info` 硬编码 `6.8.0-m6`、CLI `--version` 输出 package metadata `1.3.0`。Follow-up 提交 `5a8e3b8` 已修复，全部改用 `get_version()`。
5. **脱敏格式覆盖不全（已修复）**：初始实现不支持空格/冒号分隔的 key-value 形式（如 `OPENAI_API_KEY = value`、`api_key : value`）和 HTTP header 形式（如 `x-api-key: value`）。Follow-up 已补充。

## 剩余风险

1. **未重构迁移系统**：`connection.py` 的 `_is_migration_applied_by_schema()` 仍是大型 if-elif 链。
2. **未拆分 Editor 大方法**：`agents/editor.py` 的 `_execute()` 仍是约 500 行的大方法。
3. **未全量清理 except Exception**：项目中仍有大量 `except Exception`，本版本只处理了关键运行时路径。
4. **pyproject.toml 版本未同步**：`pyproject.toml` 中 `version = "1.3.0"` 是 pip 包版本，与运行时 API 版本 `6.6.5` 不同。当前策略是保持 pip 包版本独立。
5. **前端无版本显示 UI**：本版本未在前端新增复杂的版本显示 UI。
6. **`key=` 脱敏误伤**：`key=` 模式会误脱敏类似 `monkey=value` / `somekey=value` 的非敏感内容（变为 `monkey=***`）。这是偏保守的误脱敏，不会泄密，只可能让少量日志上下文变少。后续可限定到 query 参数边界（如 `?key=` 或 `&key=`）来减少误伤。

## 结论

核心交付物（统一版本、错误脱敏、关键路径异常可观测、health 增强）已完成并通过测试。Follow-up 提交 `5a8e3b8` 修复了 review 发现的 3 个问题（desktop runtime-info、CLI 版本、脱敏格式覆盖）。

**测试基线**：2274 passed（新增 6 个测试）
