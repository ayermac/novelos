# Novelos v6.11.0 架构优化研究课题（独立于版本路线）

> **课题编号**: v6.11.0-research
> **主题**: 架构优化研究 — 原子工具、统一异常、依赖注入（LangGraph 保留）
> **状态**: Research（研究阶段，**未排入正式版本路线**）
> **创建日期**: 2026-07-07
> **依赖前提**: v6.10.19 Store 聚合层稳定后，方可启动研究
> **预估工期**: 研究阶段 3-6 个月；全面实施 12-18 个月（如果决策通过）
> **风险等级**: 极高（涉及核心架构）
> **决策前提**: **必须在原型验证通过后，方可进入全面实施**

---

## 0. 重要说明：此课题独立于版本路线

**v6.11.0 不是正式版本排期的一部分。** 它是一个**长期技术研究课题**，与 v6.10.17 → v6.10.18 → v6.10.19 的版本链无关。

**版本路线终止于 v6.10.19**：

```
v6.10.16 (baseline)
    ↓
v6.10.17 (Code Slimming) → 文件拆分，降低单文件复杂度
    ↓
v6.10.18 (Validation Simplification) → 字段精简，减少验证复杂度
    ↓
v6.10.19 (Store Aggregation) → 聚合层，简化数据访问
                                    ↓
                          技术研究课题（独立于版本路线）
```

**管理方式**：按季度技术 OKR 管理，每季度评估是否继续投入。如果原型验证失败，则取消课题，不阻塞版本发布。

---

## 1. 背景与动机

### 1.1 当前架构问题（修正：聚焦节点实现，非引擎本身）

```markdown
代码量膨胀：
  - 总代码量：97,448 行（ainovel-cli: 43,830 行，+122%）
  - Python 文件：291 个
  - 异常处理：1,206 个 try/except（原估 249 个严重低估）
  - 状态类：7 个（`models/` 下实际数量；原估 16 个包含 frontend 组件，已澄清）

架构复杂度：
  - LangGraph 工作流节点实现过于庞大（nodes.py 2,851 行，v6.10.17 已计划拆分）
  - 状态传递字段多（FactoryState 含 30+ 字段，但均为业务必需）
  - 验证体系庞大（v6.10.18 已计划简化）
  - 异常处理分散（1,206 个 try/except，缺少统一类型）
```

**核心问题修正**：当前架构的痛点不是"LangGraph 本身有问题"，而是**LangGraph 节点实现过于庞大**和**异常处理缺少统一框架**。v6.10.17 的代码拆分计划已经针对性地解决节点膨胀问题。

### 1.2 ainovel-cli 的架构优势（参考而非照搬）

```go
// ainovel-cli 核心设计原则
1. LLM-First：决策权留模型
2. 最小 Host：架构代码稳定
3. 原子工具：三件套 + 幂等
4. 纯函数路由：错误率趋近 0
5. 观察者纪律：永不介入控制流
```

**ainovel-cli 的适用前提与 Novelos 的差异**：

| 维度 | ainovel-cli | Novelos | 是否可借鉴 |
|------|-------------|---------|-----------|
| 运行模式 | 单机 CLI，一次运行 | Web API + CLI，长期服务 | 部分借鉴 |
| 状态持久化 | 文件系统（jsonl） | SQLite（关系数据库） | 不可直接照搬 |
| 工作流引擎 | 无（Coordinator 主循环） | LangGraph StateGraph | 核心差异 |
| 用户交互 | 无（纯自动） | 有（前端工作台 + 人工审核节点） | 不可直接照搬 |
| 错误恢复 | 简单（重试或退出） | 复杂（checkpoint 恢复、人工干预） | 不可直接照搬 |

**结论**：ainovel-cli 的设计思想（原子工具、纯函数路由、最小 Host）可以作为**设计参考**，但 Novelos 的 **LangGraph + SQLite + Web API** 架构是已经验证的、适合当前业务场景的方案，不应被替换。

### 1.3 研究目标（非设计目标）

1. **代码瘦身**：从 97k 行 → 80-85k 行（通过 v6.10.17 的代码拆分，非架构替换）
2. **架构优化**：在现有 LangGraph 基础上**优化节点实现**（借鉴 ainovel-cli 的原子工具思想），**不替换工作流引擎**
3. **原子工具实验**：在现有 LangGraph 节点内实验"三件套"模式（Artifact 落盘 + Progress 推进 + Checkpoint 追加），验证收益后再扩展
4. **保留优势**：保留 DB 分层 + Index Spine + LangGraph 状态机
5. **状态管理优化**：从 `FactoryState` 增加 `*View` 只读聚合对象（非 1 个扁平 Progress），保持领域边界清晰
6. **异常处理优化**：从 1,206 个 try/except 统一为分层异常框架（不减少数量，统一类型）

---

## 2. 核心架构研究（不替换 LangGraph，在现有基础上优化）

### 2.1 不引入 Coordinator 概念（修正）

**原方案**：引入 `Coordinator` 主循环，替换 LangGraph 状态机。

**问题**：
1. LangGraph 已被验证稳定（3,748 测试通过，v6.10.16 生产就绪）
2. `Coordinator` 的 `llm.decide()` 模式取消了确定性路由，与当前 `planned → scripted → drafted → polished → review → reviewed → published` 状态机直接冲突
3. 小说生产流程的**人工审核节点**（`human_review`）和**条件分支**（`revision_router` 根据 editor 5 层 review 结果决定回退目标）无法由 LLM"自主裁定"
4. 3,748 个测试和 38 个 DB 迁移文件都依赖 LangGraph 状态机，替换成本极高

**修正方案**：**不引入 Coordinator。保留 LangGraph 工作流引擎。**

### 2.2 原子工具实验（在现有 LangGraph 节点内验证）

**当前**：LangGraph 节点函数直接执行 Agent 逻辑，缺少统一的"三件套"模式。

**改进方案（实验性）**：

在现有 LangGraph 节点内封装"原子工具"模式，**不修改工作流引擎**：

```python
# workflow/nodes/author_node.py（v6.10.17 拆分后的新文件）
from .base import BaseNodeTool  # 新增：原子工具基类

class AuthorNodeTool(BaseNodeTool):
    """Author 节点的原子工具封装
    
    借鉴 ainovel-cli 的三件套，但保留在 LangGraph 节点内执行。
    """
    
    def execute(self, state: FactoryState) -> dict:
        """原子执行三件套"""
        # 1. 加载上下文（Artifact 读取）
        context = self._load_artifacts(state)
        
        # 2. 执行 Author Agent（核心逻辑）
        result = self._invoke_author(context)
        
        # 3. 保存结果（Artifact 落盘）
        self._save_artifacts(state, result)
        
        # 4. 推进进度（Progress 更新）
        self._update_progress(state, result)
        
        # 5. 追加 Checkpoint（LangGraph checkpoint 已自动处理，此处仅记录 metadata）
        self._append_checkpoint(state, result)
        
        return result
    
    def _is_idempotent(self, state: FactoryState) -> bool:
        """幂等检查：避免重复执行"""
        existing = self._load_checkpoint(state.workflow_run_id)
        if existing and existing.digest == self._compute_digest(state):
            return True
        return False
```

**好处**：
- 不改变 LangGraph 工作流引擎
- 每个节点内部实现统一的三件套模式，提高可维护性
- 幂等检查可以在节点级别实现，避免重复 LLM 调用
- 实验成功后，可逐步推广到其他节点（planner、screenwriter、editor 等）

### 2.3 流程路由优化（不替换为纯函数）

**原方案**：将 `conditions.py` 的 8 个路由函数合并为 1 个 `FlowRouter` 纯函数。

**问题**：
1. 当前 `conditions.py` 的 8 个路由函数处理 10+ 种状态转换，包括 `revision_router` 根据 editor 5 层 review 结果决定回退到 author、polisher 还是 planner
2. 这些路由逻辑是**业务规则**（如 "review 失败时，如果 style 问题占比 >50% 则回退 polisher，否则回退 author"），不是纯函数可以覆盖的
3. 将业务规则硬编码到纯函数中，会导致函数膨胀，失去可维护性

**修正方案**：保留现有 `conditions.py` 的多函数结构，但优化每个函数的实现：

```python
# workflow/conditions.py（优化后，不合并）
# 保留 8 个路由函数，但每个函数内部使用统一的判断模式

def route_by_chapter_status(state: FactoryState) -> str:
    """根据章节状态路由（优化：增加类型安全 + 日志）"""
    status = state.get("chapter_status")
    if status not in ChapterStatus.values():
        logger.error(f"Invalid status: {status}")
        return "error"
    
    # 使用状态转换表（已在 models/state.py 中定义），避免硬编码
    return TRANSITIONS.get(status, ["error"])[0]

# 其他路由函数同理，保留业务逻辑，但增加类型安全、日志和统一错误处理
```

**为什么不合并为 1 个函数？**
- 业务规则需要渐进演进，单一函数会频繁修改
- 每个路由函数的测试用例不同，合并后测试复杂
- LangGraph 的 `build_graph()` 需要每个路由函数作为独立节点引用

---

## 3. 具体研究方案

### 3.1 状态管理优化（不扁平化，改为领域分组）

**原方案**：16 个状态类 → 1 个 `FactoryProgress`（扁平化）。

**问题**：
1. `FactoryState` 是 LangGraph 的 `TypedDict`，包含 30+ 个字段，不是"冗余"，而是业务必需（workflow_run_id、project_id、chapter_number、artifact_refs、quality_gate、messages、retry_count、token tracking 等）
2. 扁平化为 `phase/flow/current_chapter` 会丢失大量上下文（如 token usage、memory context audit、revision feedback）
3. 前端 `RunDetail.tsx`、`WorkflowTimeline.tsx` 直接消费 `FactoryState` 字段，扁平化后需要完全重写前端状态机

**修正方案**：保留 `FactoryState` 作为 LangGraph 全局状态，但增加**领域状态视图**（只读聚合对象）：

```python
# models/state.py（保留 FactoryState，新增视图）
class FactoryState(TypedDict, total=False):
    """LangGraph 全局状态 — 保留现有字段，不删减"""
    workflow_run_id: str
    project_id: str
    chapter_number: int
    # ... 现有 30+ 字段全部保留 ...

class ChapterProgressView(BaseModel):
    """章节进度视图 — 聚合 FactoryState 的字段，供前端和 API 使用"""
    chapter_number: int
    current_stage: str
    status: str
    word_count: int
    token_usage: TokenUsage
    quality_gate_result: QualityGateResult | None
    revision_count: int
    
    @classmethod
    def from_state(cls, state: FactoryState) -> "ChapterProgressView":
        """从 FactoryState 构建视图"""
        return cls(
            chapter_number=state["chapter_number"],
            current_stage=state["current_stage"],
            status=state["chapter_status"],
            word_count=state.get("total_word_count", 0),
            token_usage=TokenUsage(
                prompt=state.get("prompt_tokens", 0),
                completion=state.get("completion_tokens", 0),
            ),
            quality_gate_result=state.get("quality_gate"),
            revision_count=state.get("retry_count", 0),
        )
```

**好处**：
- `FactoryState` 保持不变，LangGraph 工作流不受影响
- 前端和 API 可以使用 `ChapterProgressView` 获取聚合数据，减少字段访问复杂度
- 视图是只读的，不会破坏状态一致性

### 3.2 异常处理统一框架（从 1,206 个 try/except 优化）

**当前**：1,206 个 `try:` 语句分散在各模块（`agent_runtime/base.py` 40 个、`api/routes/runs.py` 80 个等）。

**优化方案**：不减少 try/except 数量（业务代码需要错误处理），但**统一异常类型和分层处理**：

```python
# novel_factory/exceptions.py（新增）
class AgentExecutionError(Exception):
    """Agent 执行错误 — 由 agent_runtime/ 抛出"""
    def __init__(self, agent: str, step: str, error: Exception):
        self.agent = agent
        self.step = step
        self.error = error
        super().__init__(f"[{agent}] {step} failed: {error}")

class DBTransactionError(Exception):
    """数据库事务错误 — 由 db/repositories/ 抛出"""
    pass

class APIValidationError(Exception):
    """API 请求验证错误 — 由 api/routes/ 抛出"""
    pass

class LLMProviderError(Exception):
    """LLM 调用错误 — 由 llm/ 抛出"""
    pass
```

**分层处理策略**：

```python
# 1. DB 层：捕获 SQLite 错误，转换为 DBTransactionError
try:
    cursor.execute("INSERT INTO ...")
except sqlite3.IntegrityError as e:
    raise DBTransactionError(f"FK constraint failed: {e}") from e

# 2. Agent 层：捕获所有异常，转换为 AgentExecutionError
try:
    result = self._invoke_llm(prompt)
except Exception as e:
    raise AgentExecutionError("author", "invoke_llm", e) from e

# 3. API 层：统一捕获，转换为 HTTP 响应
try:
    result = await service.run_chapter(...)
except AgentExecutionError as e:
    return JSONResponse({"error": str(e), "agent": e.agent}, status_code=500)
except DBTransactionError as e:
    return JSONResponse({"error": "Database error"}, status_code=503)
```

**好处**：
- 不减少 try/except 数量（每个错误边界仍需处理）
- 但统一异常类型后，调试时可以从异常类型快速定位问题层级
- API 层可以统一处理，减少重复的错误响应代码

### 3.3 依赖注入重构（保留，作为独立优化项）

原方案的 `AgentContainer` 依赖注入是合理的，可以独立实施：

```python
class AgentContainer:
    """依赖注入容器"""
    
    def __init__(self, repo: Repository, llm: LLMProvider):
        self.repo = repo
        self.llm = llm
        self._agents = {}
    
    def get_author(self) -> AuthorAgent:
        if "author" not in self._agents:
            self._agents["author"] = AuthorAgent(self.llm, self.repo)
        return self._agents["author"]
```

**注意**：此优化可以独立实施（在 v6.10.17 或 v6.10.18 中），不依赖 v6.11.0 的架构重构。建议提前实施。

---

## 4. 实施计划（研究 → 原型 → 决策 → 实施）

### 4.1 研究阶段（3-6 个月，可并行于 v6.10.17-19）

- [ ] 原子工具原型：在 `workflow/nodes/author_node.py` 内实现 `BaseNodeTool` 三件套模式
  - [ ] 通过 3,748 个测试（stub 模式）
  - [ ] 性能基准测试（对比原实现）
  - [ ] 维护性评估（3 名开发者评审）
- [ ] 异常统一框架原型：在 `novel_factory/exceptions.py` 中定义 4 层异常类型，在 `api/routes/runs.py` 中验证统一处理
  - [ ] 测试覆盖率 ≥95%
- [ ] 依赖注入容器原型：在 `novel_factory/agents/` 中实现 `AgentContainer`
  - [ ] 验证单例和懒加载
  - [ ] 内存泄漏测试
- [ ] 状态视图原型：在 `models/state.py` 中新增 `ChapterProgressView`，在 `api/routes/runs.py` 中验证聚合查询
  - [ ] 前端 `RunDetail.tsx` 适配验证
- [ ] 决策评审：原型验证通过后，决定是否进入全面实施

### 4.2 原型验证决策（1 个月）

- [ ] 原型验证报告：每个原型的测试通过率、性能对比、维护性评估
- [ ] 决策会议：是否将原子工具、异常统一、依赖注入、状态视图推广到全项目
- [ ] **如果任一原型验证失败，则放弃该方向的全面实施，保留现有方案**

### 4.3 全面实施（如果决策通过，12-18 个月）

- [ ] 原子工具推广：将 `BaseNodeTool` 应用到所有 LangGraph 节点
- [ ] 异常统一推广：将所有模块的异常处理改为统一类型
- [ ] 依赖注入推广：所有 Agent 创建通过 `AgentContainer`
- [ ] 状态视图推广：API 层全部使用 `*View` 对象替代直接访问 `FactoryState`
- [ ] 全量测试（3,748 个）
- [ ] 性能回归测试
- [ ] version.py bump → 6.11.0
- [ ] CHANGELOG.md 更新

**注意**：如果原型验证未通过，v6.11.0 可能永远不会发布，或退化为更小的优化版本（如 v6.10.20 异常统一）。

---

## 5. 预期收益

### 5.1 代码量对比（修正）

| 指标 | 当前（v6.10.16） | v6.10.17-19 | v6.11.0（如果实施） |
|------|------------------|-------------|---------|
| 总代码量 | 97,448 行 | 90,000 行（拆分+Store层） | 85,000 行（优化后） |
| 文件数量 | 291 个 | 310 个（拆分增加） | 300 个（优化后略降） |
| 最大文件 | 3,657 行 | ≤1,500 行 | ≤1,500 行 |
| 异常处理 | 1,206 个 | 1,100 个 | 1,000 个（统一框架减少重复） |
| 工作流引擎 | LangGraph | LangGraph | **LangGraph（保留）** |

**修正说明**：
- 原方案的"97k → 70k"过于激进，实际 v6.10.17 的代码拆分会增加文件数量和兼容层 shim，代码量短期会增加
- v6.11.0 如果实施，也不会减少代码量，而是**优化代码质量**（统一异常、原子工具、依赖注入）
- 真正的代码量下降需要长期演化（多版本迭代），而非一次大重构

### 5.2 架构对比（修正）

| 维度 | v6.10.16 | v6.11.0（修正后） |
|------|----------|---------|
| 工作流引擎 | LangGraph StateGraph | **LangGraph StateGraph（保留）** |
| 状态管理 | `FactoryState` TypedDict（30+ 字段） | `FactoryState` + `*View` 聚合对象 |
| 路由逻辑 | 8 个路由函数（`conditions.py`） | 8 个路由函数（优化实现，增加类型安全） |
| 工具设计 | 分散逻辑 | 原子工具模式（在 LangGraph 节点内实验） |
| 异常处理 | 1,206 个 try/except（分散） | 1,206 个 try/except（统一类型） |
| 依赖管理 | 直接导入 | 依赖注入容器（可选） |

### 5.3 维护成本（修正）

- 理解成本降低 30%（原子工具统一模式、统一异常类型）
- 调试成本降低 25%（异常类型统一，定位问题层级更快）
- 扩展成本降低 20%（依赖注入、状态视图提供清晰的扩展点）
- LLM 升级直接受益（原子工具模式使 LLM 调用逻辑更统一）

**注意**：原方案的"理解成本降低 60%"等数据缺乏基准测试支撑，已修正为更务实的估计。

---

## 6. 风险与缓解（重大修正）

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 架构重构破坏功能 | **极高** | **High** | **不进行全面重构**；仅做原子工具、异常统一、依赖注入的原型实验，验证通过后再推广 |
| 替换 LangGraph 导致工作流引擎失效 | **极高** | **High** | **保留 LangGraph**；不引入 Coordinator；原子工具在现有节点内实验 |
| 原型验证失败导致时间浪费 | 中 | Medium | 研究阶段可与 v6.10.17-19 并行，不影响主线版本交付；失败时放弃该方向 |
| 性能退化 | 中 | Medium | 每个原型必须有性能基准测试；劣化 >5% 则放弃 |
| 学习成本 | 中 | Low | 文档完善；原子工具模式与现有代码风格一致，学习成本较低 |
| 状态扁平化丢失上下文 | 高 | High | **不扁平化**；改为状态视图模式，保留 `FactoryState` 完整字段 |
| 纯函数路由无法覆盖业务规则 | 高 | High | **不合并路由函数**；保留现有 `conditions.py` 结构，优化实现 |
| 长期投入无业务价值释放 | 高 | High | 将 v6.11.0 从版本路线中移除，改为**季度技术 OKR**；每个季度评估是否继续投入 |

---

## 7. 执行清单（研究课题管理）

### 7.1 研究阶段（与 v6.10.17-19 并行）
- [ ] 原子工具原型（Author 节点内实现 `BaseNodeTool`）
  - [ ] 通过 3,748 个测试（stub 模式）
  - [ ] 性能基准测试（对比原实现）
  - [ ] 维护性评估（3 名开发者评审）
- [ ] 异常统一框架原型
  - [ ] 定义 4 层异常类型
  - [ ] 在 `api/routes/runs.py` 中验证统一处理
  - [ ] 测试覆盖率 ≥95%
- [ ] 依赖注入容器原型
  - [ ] 在 `agents/` 中实现 `AgentContainer`
  - [ ] 验证单例和懒加载
  - [ ] 内存泄漏测试
- [ ] 状态视图原型
  - [ ] 新增 `ChapterProgressView`
  - [ ] 在 `api/routes/runs.py` 中验证聚合查询
  - [ ] 前端 `RunDetail.tsx` 适配验证
- [ ] 决策评审：原型验证通过后，决定是否进入全面实施

### 7.2 全面实施（如果决策通过）
- [ ] 原子工具推广到所有 LangGraph 节点
- [ ] 异常统一推广到所有模块
- [ ] 依赖注入推广到所有 Agent
- [ ] 状态视图推广到所有 API 路由
- [ ] 全量测试（3,748 个）
- [ ] 性能回归测试
- [ ] version.py bump → 6.11.0
- [ ] CHANGELOG.md 更新

### 7.3 如果决策不通过
- [ ] 记录研究结论和教训
- [ ] 将可独立实施的优化（如异常统一、依赖注入）拆分为 v6.10.20+ 的小版本
- [ ] 关闭 v6.11.0 研究课题
- [ ] 将精力集中到业务功能开发（如前端用户体验优化、新 Skill 开发）

---

## 8. 设计原则（ainovel-cli 参考）

### 8.1 借鉴 ainovel-cli 的思想（非照搬）

```markdown
思想一：工具只返事实，不返跨调度指令 → 在 LangGraph 节点内实现
思想二：流程路由由业务规则承担（非纯函数） → 保留现有 conditions.py
思想三：最小 Host 原则 → 问自己"为什么不让 LLM 更聪明"
```

### 8.2 观察者纪律

```markdown
- 观察层只观察，不介入控制流
- diag 只读、只产 Finding、不修复
- 永不自己动手
```

### 8.3 最小 Host 原则

```markdown
有人想让 Host 更聪明时，先问"为什么不让 LLM 更聪明"
这个问题回答不出"Host 必须"的理由，就不要往 Host 里加代码
```

---

## 9. 参考资料

- ainovel-cli 架构文档
- LangGraph 最佳实践
- v6.10.17 代码瘦身计划
- v6.10.18 验证体系简化计划
- v6.10.19 Repository 聚合层计划
