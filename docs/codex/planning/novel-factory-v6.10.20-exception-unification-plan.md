# Novelos v6.10.20 Exception Unification Framework Plan

> **版本**: v6.10.20
> **主题**: 异常统一框架 — 分层异常类型 + 试点迁移
> **状态**: Planned
> **预估工期**: 2-4 周
> **风险等级**: 低（不改现有 `except Exception`，只新增统一类型）

---

## 1. 现状分析

| 指标 | 数量 | 占比 |
|------|------|------|
| `try:` 总数 | 1,224 | 100% |
| `except Exception` | 686 | 75% |
| `except (TypeError, ...)` | 85 | 9% |
| `except ValueError:` 等 | 110 | 12% |
| bare `except:` | 0 | 0% ✅ |

**重灾区（Top 4）**：
1. `api/` — 277 个 `except Exception`
2. `workflow/` — 86 个
3. `agents/` — 82 个
4. `agent_runtime/` — 75 个

**问题**：75% 的异常处理使用裸 `except Exception`，导致：
- 调试时无法从异常类型快速定位问题层级
- 可能意外吞掉 `KeyboardInterrupt`、`SystemExit`
- API 错误响应格式不一致（每个路由自己拼装错误消息）

---

## 2. 核心策略

**不改现有 `except Exception`** — 避免批量修改带来的回归风险。

**建立分层异常体系** — 新增 `novel_factory/exceptions.py`，定义 4 层异常类型：

```python
# novel_factory/exceptions.py

class AgentExecutionError(Exception):
    """Agent 执行错误 — 由 agent_runtime/ agents 抛出"""
    def __init__(self, agent: str, step: str, error: Exception):
        self.agent = agent
        self.step = step
        self.error = error
        super().__init__(f"[{agent}] {step} failed: {error}")

class DBTransactionError(Exception):
    """数据库事务错误 — 由 db/repositories/ 抛出"""
    pass

class APIValidationError(Exception):
    """API 请求验证错误 — 由 api/routes/ 抛出（请求参数）"""
    pass

class LLMProviderError(Exception):
    """LLM 调用错误 — 由 llm/ 抛出"""
    pass
```

**试点迁移** — 选 1 个高频模块做试点，引入统一异常类型，验证效果。

---

## 3. 试点选择

**候选模块：**

| 模块 | except Exception 数量 | 价值 | 风险 |
|------|----------------------|------|------|
| `api/routes/runs.py` | 277 | 最高频，API 错误响应格式统一收益最大 | 中（API 路由，影响面广） |
| `agent_runtime/base.py` | 75 | 核心基础设施，Agent 执行异常统一 | 低（底层模块，调用方少） |
| `workflow/execution_events.py` | 22 | 工作流事件，边界清晰 | 低 |

**建议试点：`agent_runtime/base.py`**
- 风险最低：底层模块，不直接暴露给 API
- 收益明确：Agent 执行异常是高频调试场景
- 如果成功，可以自然向上推广到 `agents/` 和 `api/`

---

## 4. 实施步骤

### Phase A：框架搭建（3-5 天）

1. 创建 `novel_factory/exceptions.py`（4 层异常类型）
2. 创建 `tests/test_v61020_exceptions.py`（框架单元测试）
3. 在 `agent_runtime/base.py` 试点引入 `AgentExecutionError`
4. 验证：全量测试通过

### Phase B：试点扩展（5-7 天）

1. 在 `api/routes/runs.py` 的 **新增/修改代码** 中使用 `APIValidationError`
2. 在 `db/repositories/` 的 **新增/修改代码** 中使用 `DBTransactionError`
3. 验证：全量测试通过 + 新增测试覆盖

### Phase C：文档与评估（3-5 天）

1. 编写 `docs/codex/design/v6.10.20-exception-unification-spec.md`
2. 评估试点效果：调试效率、代码可读性、测试维护性
3. 决策：是否继续推广到 `workflow/`、`agents/` 等其他模块

---

## 5. 预期收益

| 指标 | 当前 | 目标（v6.10.20） |
|------|------|-----------------|
| 调试时定位问题层级 | 困难（看日志堆栈） | 从异常类型直接识别（`AgentExecutionError`/`DBTransactionError`） |
| API 错误响应格式 | 每个路由自己拼装 | 统一通过 `exceptions.py` 转换 |
| 新增代码异常处理 | 继续使用 `except Exception` | 优先使用分层异常类型 |
| 意外吞掉系统信号 | 可能（`except Exception` 会吞 `KeyboardInterrupt`） | 分层异常明确排除系统信号 |

---

## 6. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 试点模块修改导致回归 | 低 | Medium | 只改新增/重构点，不改现有 `except Exception`；全量测试验证 |
| 开发者不理解分层异常 | 中 | Low | 文档完善；代码审查强制执行 |
| 与现有异常处理冲突 | 低 | Medium | 不改现有代码，只在新增点使用；`except Exception` 仍可捕获统一异常（因为都继承 `Exception`） |

---

## 7. 交付物

- `novel_factory/exceptions.py` — 分层异常类型定义
- `tests/test_v61020_exceptions.py` — 框架单元测试
- `docs/codex/design/v6.10.20-exception-unification-spec.md` — 设计规格
- `CHANGELOG.md` 更新

---

## 8. 执行清单

- [ ] 创建 `novel_factory/exceptions.py`
- [ ] 编写 `tests/test_v61020_exceptions.py`
- [ ] 在 `agent_runtime/base.py` 试点引入 `AgentExecutionError`
- [ ] 在 `api/routes/runs.py` 试点引入 `APIValidationError`
- [ ] 在 `db/repositories/` 试点引入 `DBTransactionError`
- [ ] 全量测试验证（3749 个）
- [ ] 编写设计规格文档
- [ ] `version.py` bump → 6.10.20
- [ ] `CHANGELOG.md` 更新
