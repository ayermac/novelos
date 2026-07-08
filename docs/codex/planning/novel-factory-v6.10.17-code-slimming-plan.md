# Novelos v6.10.17 代码瘦身计划

> **版本**: v6.10.17
> **主题**: 代码瘦身 — 文件拆分与职责重构，降低单文件复杂度
> **状态**: Draft
> **创建日期**: 2026-07-07
> **依赖版本**: v6.10.16 (Megafiction Recall Scaling)
> **基线版本**: v6.10.16（`__version__ = "6.10.16"`，**3748/3748** pytest passing）
> **预估工期**: 6-9 周（准备期 1 周 + 拆分期 4-6 周 + 验证期 2 周）

---

## 0. 文档目的与边界

本文档是 v6.10.17 的**版本规划与归档文档**，聚焦 P0 级代码瘦身任务：

1. 超大文件拆分（workflow / agents / API / DB 层）
2. 职责边界重构
3. 代码可读性提升
4. 维护成本降低

**边界**：本文档仅覆盖 backend Python 代码拆分。API 路由层瘦身、前端组件拆分见后续专项计划。

**注意**：`agent_runtime/context_builder.py` 是共享基础设施，不纳入 `agents/author/` 拆分范围。

---

## 1. 背景与动机

### 1.1 v6.10.16 的基础

v6.10.16 已经完成了长篇数据召回优化（DB分层、Index Spine、Pull 通道等），但代码膨胀问题仍然严重：

```markdown
总代码量：97,448 行（ainovel-cli: 43,830 行，+122%）
超大文件（>1500 行或 >20KB）：
  - agents/author.py: 3,657 行 ⚠️
  - api/routes/genesis.py: 3,579 行 ⚠️
  - api/routes/production.py: 3,140 行 ⚠️
  - workflow/nodes.py: 2,851 行 ⚠️
  - agents/editor.py: 2,523 行 ⚠️
  - api/routes/runs.py: 2,477 行 ⚠️
  - api/routes/memory_updates.py: 2,423 行 ⚠️
  - agent_runtime/context_builder.py: 1,924 行 ⚠️（共享基础设施，独立拆分）
  - agents/polisher.py: 1,797 行 ⚠️
  - quality/genesis_quality_gate.py: 1,733 行 ⚠️
  - db/repositories/workflow.py: 34,985 字节 ⚠️
  - db/repositories/chapter.py: 31,984 字节 ⚠️
  - db/repositories/review_workbench.py: 25,287 字节 ⚠️
```

### 1.2 对比 ainovel-cli

| 维度 | ainovel-cli | novelos v6.10.16 | 差距 |
|------|-------------|-------------------|------|
| **总代码量** | 43,830 行 | 97,448 行 | +122% |
| **最大文件** | host.go: ~860 行 | author.py: 3,657 行 | 4.2x |
| **文件拆分** | 每个 ≤800 行 | 5 个文件 >1500 行 | - |
| **维护成本** | 低 | 高 | - |

### 1.3 设计目标

1. **可读性**：单文件代码行数 ≤1000 行（Python 项目务实标准；Go 与 Python 表达能力不同，不宜机械照搬 ainovel-cli 的 800 行标准）
2. **职责单一**：每个模块只负责一件事
3. **维护成本**：降低 30%（通过文件拆分 + 兼容层 shim）
4. **零破坏**：不改变 LangGraph 工作流结构与对外接口；通过 `__init__.py` 兼容层保持原导入路径可用
5. **分层覆盖**：拆分覆盖 agents、workflow、API routes、DB repositories 四层

---

## 2. 超大文件分析

### 2.1 nodes.py (2,851 行)

**问题分析**：

```markdown
职责混杂：
  - 10+ 个节点函数
  - 超时配置
  - 消息映射
  - 事件日志
  - 错误处理
  
依赖过多：
  - 导入 15+ 个模块
  - 循环依赖风险
```

**拆分策略**：

```
workflow/nodes/
  __init__.py              # 统一导出
  planner_node.py          # Planner 相关节点
  author_node.py           # Author 相关节点
  editor_node.py           # Editor 相关节点
  memory_node.py           # Memory Curator 相关节点
  router_node.py           # 路由节点
  publisher_node.py        # Publisher 相关节点
  timeout_config.py        # 超时配置（~100 行）
  messages.py              # 节点消息映射（~50 行）
  helpers.py               # 辅助函数（~200 行）
```

### 2.2 author.py (3,657 行)

**问题分析**：

```markdown
职责混杂：
  - 主撰写逻辑
  - 上下文构建（10+ 个 _build_* 方法）
  - LLM 调用策略
  - 内部修复逻辑
  - 标题生成
  - 契约验证
```

**拆分策略**：

```
agents/author/
  __init__.py              # AuthorAgent 主类（~500 行）
  context_builder.py       # _build_*_context 方法（~800 行）
  invoke_strategies.py     # _invoke_text/json 策略（~600 行）
  repair_logic.py          # 内部修复逻辑（~400 行）
  title_generation.py      # 标题生成逻辑（~300 行）
  contracts.py             # 契约验证逻辑（~200 行）
  helpers.py               # 辅助函数（~200 行）
```

### 2.3 editor.py (2,523 行)

**拆分策略**：

```
agents/editor/
  __init__.py              # EditorAgent 主类（~500 行）
  strategy_router.py       # 策略路由逻辑（~400 行）
  context_builder.py       # 上下文构建（~600 行）
  invoke_strategies.py     # LLM 调用策略（~500 行）
  result_processor.py      # 结果处理逻辑（~300 行）
  helpers.py               # 辅助函数（~200 行）
```

### 2.4 API 路由层（新增）

**`api/routes/genesis.py` (3,579 行)** 和 **`api/routes/production.py` (3,140 行)** 是当前实际最大的两个文件，但此前规划完全遗漏了 API 层拆分。

**拆分策略**：

```
api/routes/genesis/
  __init__.py              # 路由注册（~200 行）
  project_genesis.py         # 项目创世（~800 行）
  chapter_genesis.py         # 章节创世（~800 行）
  memory_genesis.py          # 记忆创世（~800 行）
  helpers.py                 # 共享辅助（~400 行）

api/routes/production/
  __init__.py              # 路由注册（~200 行）
  next_action.py             # production-next（~800 行）
  auto_fill.py               # auto-fill（~600 行）
  arc_plan.py                # arc-plan（~600 行）
  run_auto.py                # run-auto（~600 行）
  helpers.py                 # 共享辅助（~400 行）
```

### 2.5 DB Repository 层（新增）

**`db/repositories/workflow.py` (34,985 字节)** 和 **`db/repositories/chapter.py` (31,984 字节)** 是数据访问层的"超大文件"。

**拆分策略**：

```
db/repositories/
  workflow/
    __init__.py              # 兼容导出（保持原导入路径）
    core.py                  # 核心 workflow CRUD（~800 行）
    checkpoint.py            # checkpoint 相关（~600 行）
    execution.py             # execution_event 相关（~600 行）
  chapter/
    __init__.py              # 兼容导出
    chapter_core.py          # chapter 主表（~800 行）
    draft.py                 # draft 相关（~600 行）
    version.py               # chapter 版本（~500 行）
```

**注意**：DB Repository 拆分必须保持**表结构不变**，仅将代码组织从单文件改为多文件。表结构变更属于 v6.10.19 范畴，不在本版本执行。

---

## 3. 拆分原则

### 3.1 单一职责原则

每个模块只负责一件事：
- nodes/planner_node.py → 只处理 Planner 节点逻辑
- author/context_builder.py → 只负责上下文构建
- editor/strategy_router.py → 只负责策略路由

### 3.2 文件大小限制

目标：单文件 ≤1000 行（Python 项目务实标准；Go 与 Python 表达能力不同，不宜机械照搬 ainovel-cli 的 800 行标准）

硬性规则：
- 超过 1500 行 → 必须拆分
- 1000-1500 行 → 建议拆分
- <1000 行 → 可接受

### 3.3 兼容层策略（新增）

拆分后必须保持**原导入路径可用**，通过在新目录的 `__init__.py` 中提供 re-export 实现：

```python
# agents/author.py（原文件）→ 保留为兼容层 shim
# 内容改为：
from .author.context_builder import ContextBuilder
from .author.invoke_strategies import InvokeStrategies
# ... 其他 re-export

# 或直接在 agents/__init__.py 中：
from .author import ContextBuilder, InvokeStrategies, AuthorAgent
```

**好处**：
- 现有 41 个 API 路由文件和 30+ 个 CLI 命令无需立即修改导入路径
- 拆分和调用方迁移可以并行、渐进进行
- 降低回归风险

### 3.4 测试友好

每个拆分后的模块：
- 独立单元测试
- Mock 依赖简单
- 边界清晰

---

## 4. 实施策略

### 4.1 渐进式拆分（含兼容层）

```markdown
阶段 1：准备期（1 周）
  - 创建新目录结构
  - 分析依赖关系（使用 `pydeps` 或 `import-deps` 生成依赖图）
  - 设计拆分边界
  - 确定兼容层 shim 策略
  - 评估 LangGraph graph.py 的节点注册适配

阶段 2：拆分期（4-6 周）
  - 按文件优先级拆分
  - author.py → editor.py → nodes.py → api/routes/genesis.py → api/routes/production.py → db/repositories/*
  - 每拆分一个文件，立即运行测试（~3748 个）
  - 优先拆分 agents 层（影响面最小），最后拆分 API 层（影响面最大）

阶段 3：验证期（2 周）
  - 全量 pytest（3748 个测试）
  - 集成测试（LangGraph 端到端）
  - 手动回归测试（API + CLI）
  - 兼容层 shim 验证（确保原导入路径仍可用）
```

### 4.2 LangGraph 适配（新增）

`nodes.py` 拆分后，节点函数被分散到多个子模块。`workflow/graph.py` 中的 `build_graph()` 需要适配：

**方案**：在 `workflow/nodes/__init__.py` 中统一 re-export 所有节点函数，保持 `graph.py` 的导入方式不变：

```python
# workflow/nodes/__init__.py
from .planner_node import planner_node
from .author_node import author_node
# ... 其他节点

# graph.py 的导入保持不变：
from . import nodes
# nodes.planner_node(...) 仍可工作
```

### 4.3 优先级排序

P0（必须拆分，>2000 行）：
- author.py (3,657 行)
- api/routes/genesis.py (3,579 行)
- api/routes/production.py (3,140 行)
- nodes.py (2,851 行)
- editor.py (2,523 行)
- api/routes/runs.py (2,477 行)

P1（建议拆分，1500-2000 行）：
- api/routes/memory_updates.py (2,423 行)
- agent_runtime/context_builder.py (1,924 行) → **独立拆分，不纳入 author/**
- agents/polisher.py (1,797 行)
- quality/genesis_quality_gate.py (1,733 行)

P2（建议拆分，>20KB）：
- db/repositories/workflow.py (34,985 字节)
- db/repositories/chapter.py (31,984 字节)
- db/repositories/review_workbench.py (25,287 字节)

P3（拆分后顺手处理，<1500 行）：
- api/routes/workflow_timeline.py (1,405 行)
- agents/memory_curator.py (1,385 行)

---

## 5. 预期收益

### 5.1 量化目标

| 指标 | 当前（v6.10.16） | 目标（v6.10.17） | 验收方式 |
|------|------------------|------------------|----------|
| 超大文件数量（>1500行） | 10 个 | ≤2 个 | `find . -name "*.py" -exec wc -l {} \;` |
| 超大文件数量（>1000行） | 14 个 | ≤6 个 | `wc -l` |
| 最大文件行数 | 3,657 行 | ≤1,500 行 | `wc -l` |
| 代码可读性评分 | 中 | 高 | 人工评审 |
| pytest 基线 | 3748 passing | ≥3748 passing | `pytest -q` |
| 兼容层 shim 覆盖率 | 0% | 100% | 检查所有拆分目录的 `__init__.py` |

### 5.2 维护成本

预期降低：
- 理解成本：-30%（非 -40%，拆分增加目录深度可能带来一定导航成本）
- 调试成本：-25%（需要定位子模块，但单文件更小更易理解）
- 扩展成本：-30%（新增功能只需修改单一职责模块）

---

## 6. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 拆分破坏测试 | 高 | Medium | 每拆分一个文件，立即运行测试；使用兼容层 shim 降低调用方影响 |
| 循环依赖 | 中 | Medium | 拆分前分析依赖关系；使用 `pydeps` 生成依赖图 |
| 导入路径混乱 | 中 | Low | 统一在 `__init__.py` 导出；原文件保留为 shim（1-2 版本） |
| 回归 Bug | 中 | High | 全量 pytest（3748 个）+ 手动回归测试 |
| LangGraph 节点注册失效 | 中 | High | `workflow/nodes/__init__.py` 统一 re-export；拆分后验证 `build_graph()` |
| 代码量增加 | 高 | Low | 兼容层 shim + 目录结构增加约 5-10% 代码量，属于可接受的过渡成本 |

---

## 7. 版本迭代记录

| 版本 | 日期 | 变更 | 状态 |
|------|------|------|------|
| v6.10.16 | 2026-07-02 | Megafiction Recall Scaling | Released |
| **v6.10.17** | **2026-07-07** | **代码瘦身计划（本文档）** | **Draft（待评审）** |

---

## 8. 执行清单（待用户确认后启动）

### 8.1 阶段 1：准备期（1 周）
- [ ] 创建 `workflow/nodes/` 目录
- [ ] 创建 `agents/author/` 目录
- [ ] 创建 `agents/editor/` 目录
- [ ] 创建 `api/routes/genesis/` 目录
- [ ] 创建 `api/routes/production/` 目录
- [ ] 创建 `db/repositories/workflow/` 和 `db/repositories/chapter/` 目录
- [ ] 使用 `pydeps` 分析 agents / workflow / API / DB 四层依赖关系
- [ ] 设计兼容层 shim 策略（哪些原文件保留为 re-export shim）
- [ ] 评估 `workflow/graph.py` 的 `build_graph()` 节点注册适配方案

### 8.2 阶段 2：拆分期（4-6 周）
- [ ] author.py 拆分为 7 个文件（P0）
- [ ] editor.py 拆分为 6 个文件（P0）
- [ ] nodes.py 拆分为 9 个文件（P0）
- [ ] api/routes/genesis.py 拆分为 5 个文件（P0）
- [ ] api/routes/production.py 拆分为 6 个文件（P0）
- [ ] api/routes/runs.py 拆分（P0）
- [ ] db/repositories/workflow.py 拆分为 3 个文件（P2）
- [ ] db/repositories/chapter.py 拆分为 3 个文件（P2）
- [ ] 每拆分一个文件，立即运行 `pytest -q`（~3748 个测试）
- [ ] 验证所有兼容层 shim 的导入路径可用

### 8.3 阶段 3：验证期（2 周）
- [ ] 全量 pytest（3748 个测试）
- [ ] LangGraph 端到端集成测试（stub 模式 + real 模式）
- [ ] API 手动回归测试（`novelos api` + curl / frontend）
- [ ] CLI 手动回归测试（`novelos run-chapter`、`novelos status` 等）
- [ ] version.py bump → 6.10.17
- [ ] CHANGELOG.md 更新
- [ ] 标记兼容层 shim 为 deprecated（计划在 v6.10.18 或 v6.10.19 移除）

---

## 9. 参考资料

- ainovel-cli 架构文档
- v6.10.14 长篇召回优化计划
- v6.10.15 Megafiction Recall Scaling 计划
