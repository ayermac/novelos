# v5.1.6 — LangGraph 编排激活 + 真实 LLM 首次生成 + 安全收口

> 版本：v5.1.6 | 日期：2026-04-27 | 状态：**已通过验收**

## 目标

激活 LangGraph StateGraph 作为唯一编排器，替代 Dispatcher while 循环；收口前端空状态；接入真实 LLM 配置验证；确保安全收口。

## 架构变更

```text
之前: API → Dispatcher.run_chapter() → while 循环 → _run_agent() → Agent
现在: API → run_with_graph() → LangGraph StateGraph → create_node_runners() → Agent 闭包
```

关键优势：
1. LangGraph 编排：状态机管理，支持 checkpoint 恢复
2. 依赖注入：`create_node_runners()` 通过闭包注入 LLMRouter、Repository
3. API 兼容：`run_with_graph()` 返回与 `Dispatcher.run_chapter()` 相同结构
4. 安全收口：API Key 不泄露、错误中文化、模式标签

## Phase 0 — 前端收口（原 v5.1.5d）

### 变更文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `frontend/src/components/EmptyState.tsx` | 修改 | 支持 `actions` 多按钮属性 |
| `frontend/src/pages/Review.tsx` | 修改 | 说明横幅 + 多按钮引导空状态 |
| `frontend/src/pages/Style.tsx` | 修改 | 能力卡片 + 空状态引导 |
| `frontend/src/components/Layout.tsx` | 修改 | 导航分组：创作/工具/开发 |
| `frontend/src/App.tsx` | 修改 | 移除 `/acceptance` 路由 |
| `frontend/src/pages/Acceptance.tsx` | 删除 | 不再需要独立验收页面 |

### 关键实现

- `EmptyState` 新增 `actions?: Array<{ label: string; to: string }>` 属性，第一个按钮 `btn-primary`，其余 `btn-secondary`
- 导航新增 `isSectionLabel` 类型，渲染为小号灰色分组标题
- Review 空状态：说明横幅 + 3 个导航入口（项目列表/创作中心/工作流）
- Style 空状态：3 个能力卡片 + 初始化引导

## Phase A — 后端激活 LangGraph

### 变更文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `novel_factory/models/state.py` | 修改 | 新增 `steps` 字段 |
| `novel_factory/workflow/nodes.py` | 修改 | 新增 `create_node_runners()` 工厂函数 |
| `novel_factory/workflow/graph.py` | 修改 | 支持 `llm_router`/`skill_registry` 参数 |
| `novel_factory/workflow/runner.py` | 新建 | `run_with_graph()` + `_build_llm_router()` |
| `novel_factory/workflow/conditions.py` | 修改 | 修复 `published` 状态路由 |

### 关键实现

1. **`create_node_runners(settings, repo, llm_router, skill_registry)`**
   - 闭包注入，对齐 `Dispatcher._run_agent()` 逻辑
   - `llm_router.for_agent(agent_name)` ValueError 捕获 → `_finalize_run("failed")`
   - polisher/editor 的 `skill_registry` 注入
   - 返回 `{planner, screenwriter, author, polisher, editor}` 字典

2. **`run_with_graph(project_id, chapter_number, settings, repo, llm_mode)`**
   - 返回值与 `Dispatcher.run_chapter()` 同构：`{run_id, chapter_status, steps, error, requires_human}`
   - `_build_llm_router()` 统一构建逻辑（stub 模式也返回完整 router）
   - 异常处理包裹 `graph.invoke()`
   - `published` 章节短路返回（避免死循环）
   - 使用 `thread_id` config 配合 checkpointer

3. **`route_by_chapter_status` 修复**
   - 新增 `published → archive` 路由（之前缺失，fallback 到 planner 导致死循环）
   - `graph.py` conditional_edges 映射新增 `"archive": "archive"`

## Phase B — API 切换 + 配置验证

### 变更文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `novel_factory/api/routes/run.py` | 修改 | 改调 `run_with_graph()` |
| `novel_factory/api/routes/settings.py` | 修改 | 新增 `/settings/validate` 端点 |
| `frontend/src/pages/Settings.tsx` | 修改 | 验证按钮 + real 模式成本提示 |

### 关键实现

- `run.py` 只改调用入口（`run_with_graph` 替代 `dispatcher.run_chapter`），响应映射逻辑完全复用
- `validate_config` 端点不仅检查配置存在性，还做实际 LLM 连通性测试
- 前端验证按钮四态：idle/loading/success/error

## Phase C — 安全收口 + 测试

### 变更文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `novel_factory/llm/router.py` | 修改 | 错误信息中文化（4 处 ValueError） |
| `tests/test_llm_router.py` | 修改 | 更新测试匹配模式 |
| `frontend/src/pages/Settings.tsx` | 修改 | real 模式成本提示 |
| `tests/test_v516_langgraph_activation.py` | 新建 | 12 个后端测试 |
| `tests/test_v516_frontend_closure.py` | 新建 | 9 个前端测试 |

### 关键实现

- LLMRouter 4 处错误中文化：
  - `"LLM profile '...' not found"` → `"LLM 档案 '...' 不存在"`
  - `"API key not configured"` → `"API Key 未配置"`
  - `"base_url not configured"` → `"API 地址未配置"`
  - `"Unsupported provider"` → `"不支持的提供商"`

## Bug 修复

### `published` 状态死循环（P0 严重）

**根因**：`route_by_chapter_status()` 的 routing 字典缺少 `published` 状态，fallback 到 `"planner"`，导致 published → planner → screenwriter → ... → published → 无限循环，直到 LangGraph recursion limit (25) 触发 `GraphRecursionError`。

**修复**：
1. `conditions.py`：routing 字典新增 `ChapterStatus.PUBLISHED.value: "archive"`
2. `graph.py`：conditional_edges 映射新增 `"archive": "archive"`
3. `runner.py`：`published` 状态提前返回 `{chapter_status: "published", error: None}`

## 过期测试修复

| 文件 | 变更 |
|------|------|
| `test_v51_frontend_build.py` | `"总览"` → `"创作中心"` |
| `test_v51_frontend_quality.py` | `"总览"` → `"创作中心"`，page 数 10 → 9 |
| `test_v513_usability_closure.py` | Acceptance 测试标记跳过（页面已删除） |
| `test_v516_langgraph_activation.py` | 新增 `published → archive` 和 `revision → author` 路由测试，新增 published 短路测试 |

## 未删除的代码（v5.2 处理）

- `novel_factory/dispatch/` 目录完整保留
- `novel_factory/dispatcher.py` 门面类保留
- CLI 层仍使用 Dispatcher

## 验收结果

- ✅ 全量测试 1365/1365 通过
- ✅ TypeScript 检查通过
- ✅ 前端构建通过
- ✅ Review/Style 空状态有引导和出口
- ✅ 导航三分组（创作/工具/开发）
- ✅ `run_with_graph()` stub 模式行为与 Dispatcher 完全一致
- ✅ `published` 章节不再死循环
- ✅ 配置验证端点可用
- ✅ API Key 不泄露
- ✅ LLMRouter 错误中文化
- ✅ Acceptance 路由已移除

## v5.2 遗留项

| 项目 | 优先级 |
|------|--------|
| Checkpoint 持久化（MemorySaver → SqliteSaver） | P0 |
| SSE Streaming（`graph.stream()` → EventSource） | P0 |
| Dispatcher 删除（dispatch/ 目录 + CLI 层切换） | P1 |
| Batch/Queue mixin 迁移 | P1 |
| 真实 LLM 端到端验证 | P1 |
| ProjectDetail 页面 stub/real 标签 | P2 |
