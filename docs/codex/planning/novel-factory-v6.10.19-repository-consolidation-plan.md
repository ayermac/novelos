# Novelos v6.10.19 Repository 聚合层计划（Store Facade）

> **版本**: v6.10.19
> **主题**: Repository 聚合层 — Store Facade 设计与双轨迁移
> **状态**: Planned
> **创建日期**: 2026-07-07
> **依赖版本**: v6.10.18 (Validation Simplification)
> **预估工期**: 4-6 个月（Store 聚合层设计 + 渐进迁移 + 双轨验证）

---

## 1. 背景与动机

### 1.1 当前问题

```markdown
Repository 职责分散：
  - Repository 文件: 34 个
  - 每个 Repository 独立管理 CRUD
  - 跨 Repository 的聚合查询需要多次调用

超大文件（代码组织问题，非表结构问题）：
  - chapter.py: 31,984 字节（代码行数过多，但表结构合理）
  - workflow.py: 34,985 字节（同上）
  - review_workbench.py: 25,287 字节（同上）
```

**注意**：这是代码组织问题，不是数据库范式问题。SQLite 表结构和外键约束经过 38 个迁移文件演化，是合理的。

### 1.2 对比 ainovel-cli（重要差异说明）

ainovel-cli 仅有 8 个核心 Store，但其架构前提与 Novelos **有本质差异**：

| 维度 | ainovel-cli | Novelos | 差异影响 |
|------|-------------|---------|----------|
| **存储后端** | 文件系统（jsonl / tmp+rename） | SQLite（关系数据库） | 文件系统 Store 的 `tmp+rename` 原子写入在 SQLite 中无意义；SQLite 已有事务机制 |
| **部署模式** | 单机 CLI | FastAPI Web + CLI 双模式 | Web 模式需要并发安全、连接池，文件系统锁不够 |
| **schema 演化** | 无 schema（schema-less jsonl） | 38 个 SQL 迁移文件 | 表间外键关系、约束、索引不能随意合并 |
| **查询模式** | 简单 key-value 加载 | 复杂 JOIN、filter、pagination | 合并 Store 后可能导致 N+1 查询或性能退化 |

**结论**：不能直接照搬 ainovel-cli 的 8-Store 架构。应在现有 SQLite Repository 模式基础上，增加 **Store 聚合层（Facade）**，而非物理合并 Repository 文件。

### 1.3 设计目标（修正）

1. **Store 聚合层**：在现有 34 个 Repository 之上，增加 8 个聚合 Store 作为**统一入口**（非物理替换）
2. **职责清晰**：每个 Store 聚合一个业务领域，但底层仍使用现有 Repository
3. **零破坏**：不删除任何 Repository 文件；现有调用方可继续工作
4. **渐进迁移**：新代码使用 Store 接口，旧代码逐步迁移，1-2 版本过渡期内双轨并存
5. **性能保障**：每个 Store 实现后必须进行性能基准测试，确保查询性能不劣化

---

## 2. 聚合方案（Store Facade）

### 2.1 目标 Store 结构（8 个聚合层）

```
stores/
  __init__.py
  progress.py          # ProgressStore（进度管理）→ 聚合 workflow + execution_event Repository
  checkpoints.py       # CheckpointStore（checkpoint）→ 聚合 checkpoint 相关 Repository
  drafts.py            # DraftStore（草稿管理）→ 聚合 chapter + draft Repository
  summaries.py         # SummaryStore（摘要）→ 聚合 review + quality Repository
  characters.py        # CharacterStore（角色）→ 聚合 character + style_sample Repository
  world.py             # WorldStore（世界状态）→ 聚合 story_fact + plot_hole + memory Repository
  outline.py           # OutlineStore（大纲）→ 聚合 outline + instruction Repository
  signals.py           # SignalStore（信号）→ 聚合 genesis + project + queue + serial + batch Repository
```

**关键原则**：每个 Store 是**聚合接口**，不是物理替换。底层仍调用现有 Repository 的方法。Store 的生命周期与 Repository 解耦：可以先设计 Store 接口，再逐步将现有调用方从 Repository 迁移到 Store。

### 2.2 聚合映射表

| 原 Repository | 目标 Store | 聚合逻辑 | 底层 Repository 是否保留 |
|---------------|-----------|----------|----------------------|
| chapter.py + draft.py | DraftStore | 草稿与章节聚合查询 | ✅ 保留，Store 调用底层 Repository |
| story_fact.py + plot_hole.py + memory.py | WorldStore | 世界状态统一查询 | ✅ 保留 |
| review.py + quality.py | SummaryStore | 评审摘要化 | ✅ 保留 |
| workflow.py + execution_event.py | ProgressStore | 进度统一查询 | ✅ 保留 |
| character.py + style_sample.py | CharacterStore | 角色统一查询 | ✅ 保留 |
| outline.py + instruction.py | OutlineStore | 大纲指令合并查询 | ✅ 保留 |
| genesis.py + project.py + queue.py + serial.py + batch.py | SignalStore | 信号/队列聚合 | ✅ 保留 |

### 2.3 为什么不做物理合并？

1. **数据库范式不可违背**：SQLite 表间存在外键约束（38 个迁移文件定义），物理合并 Repository 会导致事务边界模糊、外键约束难以维护。
2. **查询性能风险**：不同 Repository 的查询模式完全不同（`workflow.py` 按 project_id + chapter 查，`execution_event.py` 按 run_id + timestamp 查）。强行合并到一个 Store 类会导致 N+1 查询。
3. **测试债务**：`tests/test_repository.py` 和 30+ 个集成测试直接依赖现有 Repository 的 API。物理合并等于重写所有测试的 setup 和 mock，工作量巨大。
4. **LangGraph 依赖**：`workflow/graph.py` 和 `workflow/runner.py` 直接依赖 `db/repositories/workflow.py` 的 checkpoint 方法。物理合并会破坏工作流引擎。
5. **回滚困难**：物理合并后，如果发现 Store 设计有问题，回退到旧 Repository 的成本极高。聚合层则可以在 Store 层快速调整，不影响底层。

---

## 3. Store 设计规范（基于 SQLite + Repository）

### 3.1 设计原则

1. **Store 是聚合层，不是替代层**：Store 调用底层 Repository，不直接操作数据库。
2. **保持事务边界**：跨 Repository 的操作在 Store 层协调，但事务仍由底层 Repository 管理。
3. **查询聚合，写入分发**：Store 的核心价值是**聚合查询**（如 "获取某项目的所有进度信息"），而非替代 Repository 的写入逻辑。

### 3.2 统一接口

```python
from novel_factory.db.repositories import (
    WorkflowRepository, ExecutionEventRepository,
    # ... 其他 Repository
)

class BaseStore:
    """Store 基类 — 基于 SQLite + Repository 模式，非文件系统"""

    def __init__(self, db: Connection | Repository):
        """
        Args:
            db: 数据库连接或 Repository 实例。
                与 ainovel-cli 不同：这里使用 SQLite 连接/事务，而非文件路径。
        """
        self._db = db
        # 底层 Repository 实例在子类中按需初始化

    def _get_repo(self, repo_class: type[T]) -> T:
        """获取 Repository 实例（支持连接复用）"""
        if repo_class not in self._repos:
            self._repos[repo_class] = repo_class(self._db)
        return self._repos[repo_class]
```

### 3.3 各 Store 职责

```python
class ProgressStore(BaseStore):
    """进度管理：聚合 workflow + execution_event 的查询"""
    
    def get_project_progress(self, project_id: str) -> ProjectProgress:
        """聚合查询：项目进度、执行事件、当前章节"""
        workflow_repo = self._get_repo(WorkflowRepository)
        event_repo = self._get_repo(ExecutionEventRepository)
        
        workflow = workflow_repo.get_by_project(project_id)
        events = event_repo.get_recent(project_id, limit=10)
        
        return ProjectProgress(
            workflow=workflow,
            recent_events=events,
        )
    
    # 注意：写入仍通过底层 Repository 的原有方法，Store 不封装写入

class DraftStore(BaseStore):
    """草稿管理：聚合 chapter + draft 的查询"""
    
    def get_chapter_with_drafts(self, chapter_id: str) -> ChapterWithDrafts:
        """聚合查询：章节 + 所有草稿版本"""
        chapter_repo = self._get_repo(ChapterRepository)
        draft_repo = self._get_repo(DraftRepository)
        
        chapter = chapter_repo.get(chapter_id)
        drafts = draft_repo.get_by_chapter(chapter_id)
        
        return ChapterWithDrafts(chapter=chapter, drafts=drafts)

class WorldStore(BaseStore):
    """世界状态：聚合 story_facts + plot_holes + memory 的查询"""
    
    def get_world_state(self, project_id: str) -> WorldState:
        """聚合查询：世界设定、情节漏洞、记忆"""
        fact_repo = self._get_repo(StoryFactRepository)
        hole_repo = self._get_repo(PlotHoleRepository)
        memory_repo = self._get_repo(MemoryRepository)
        
        return WorldState(
            facts=fact_repo.get_by_project(project_id),
            plot_holes=hole_repo.get_by_project(project_id),
            memories=memory_repo.get_by_project(project_id),
        )
```

### 3.4 与现有代码的集成方式

**双轨并存策略**（1-2 版本过渡期）：

```python
# 现有代码（继续使用 Repository，不受影响）
from novel_factory.db.repositories import WorkflowRepository
repo = WorkflowRepository(db)
workflow = repo.get_by_project(project_id)

# 新代码（使用 Store，获得聚合查询能力）
from novel_factory.stores import ProgressStore
store = ProgressStore(db)
progress = store.get_project_progress(project_id)
```

**好处**：
- 现有代码零修改即可继续工作
- 新代码可以选择使用 Store 或 Repository，按需渐进
- 如果 Store 设计有问题，可以快速调整 Store 层，不影响底层 Repository

---

## 4. 实施计划（4-6 个月）

### 4.1 阶段 1：Store 接口设计（4-6 周）

- [ ] 设计 BaseStore 接口（基于 SQLite + Repository，非文件系统）
- [ ] 设计 8 个 Store 的职责边界和聚合查询方法
- [ ] 评估每个 Store 对底层 Repository 的调用模式（识别 N+1 查询风险）
- [ ] 设计性能基准测试方案（Store 查询 vs 直接 Repository 查询）
- [ ] 确定双轨迁移策略（哪些模块先迁移，哪些后迁移）
- [ ] 产出 `docs/codex/design/v6.10.19-store-interface-spec.md`

### 4.2 阶段 2：Store 实现（8-10 周）

- [ ] 实现 ProgressStore（聚合 workflow + execution_event）
- [ ] 实现 DraftStore（聚合 chapter + draft）
- [ ] 实现 WorldStore（聚合 story_fact + plot_hole + memory）
- [ ] 实现其他 5 个 Store
- [ ] 每个 Store 实现后，进行性能基准测试（确保查询性能不劣化）
- [ ] 单元测试覆盖（Store 层独立测试，Mock 底层 Repository）
- [ ] 产出 `docs/codex/design/v6.10.19-store-implementation-spec.md`

### 4.3 阶段 3：调用方迁移与验证（6-8 周）

- [ ] 选择 1-2 个低风险模块（如 API 路由的辅助函数）先迁移到 Store
- [ ] 验证双轨并存的可行性（Store 和 Repository 同时使用，无冲突）
- [ ] 逐步迁移 `api/routes/` 的调用方（从只读查询开始）
- [ ] 逐步迁移 `agents/` 的调用方
- [ ] 全量 pytest（3748 个测试）
- [ ] 性能回归测试（Store 查询 vs 原 Repository 查询）
- [ ] version.py bump → 6.10.19
- [ ] CHANGELOG.md 更新

---

## 5. 预期收益

### 5.1 量化目标

| 指标 | 当前 | 目标（v6.10.19） | 改进 |
|------|------|----------------|------|
| Repository 文件 | 34 个 | 34 个（**不删除**）+ 8 个 Store 新增 | 0%（物理文件数不变） |
| 聚合查询接口 | 0 个 | 8 个 Store | 新增 |
| 调用方直接使用 Repository | 100% | 80%（Store 覆盖） | 逐步降低 |
| 数据访问层代码 | ~80k 行 | ~85k 行（Store 层新增 ~5k 行） | +6%（短期增加，长期降低理解成本） |
| 最大 Repository | 34,985 字节 | 34,985 字节（不变） | 0% |

### 5.2 架构收益

- ✅ 新增聚合查询能力（一次调用获取跨 Repository 数据）
- ✅ 数据访问层职责更清晰（Repository = 底层 CRUD，Store = 业务聚合）
- ✅ 现有代码零破坏（双轨并存）
- ✅ 易于理解和扩展（新开发者通过 Store 接口了解数据访问模式）
- ⚠️ 维护成本短期增加（Store 层新增），长期降低（聚合查询减少重复代码）

---

## 6. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| Store 查询性能劣化 | 中 | High | 每个 Store 实现后必须做性能基准测试；识别 N+1 查询并优化 |
| 双轨并存导致混乱 | 中 | Medium | 明确文档：新代码优先使用 Store，旧代码逐步迁移；代码审查强制执行 |
| 过度聚合导致 Store 臃肿 | 中 | Medium | Store 只做查询聚合，不做写入；写入仍通过底层 Repository |
| 合并破坏导入 | 低 | Medium | **不做物理合并，不删除 Repository 文件，零导入破坏风险** |
| 数据迁移丢失 | 低 | High | **无数据迁移**（Store 是聚合层，不涉及表结构变更） |
| 性能退化 | 低 | Low | 基准测试对比（Store 聚合查询 vs 手动多次 Repository 查询） |
| LangGraph 工作流引擎破坏 | 低 | High | workflow/runner.py 继续直接使用 Repository，不迁移到 Store（避免引入不必要的抽象层） |

---

## 7. 执行清单

### 7.1 阶段 1：Store 接口设计（4-6 周）
- [ ] BaseStore 接口设计（基于 SQLite + Repository）
- [ ] 8 个 Store 的职责边界和聚合查询方法设计
- [ ] 识别 N+1 查询风险评估
- [ ] 性能基准测试方案设计
- [ ] 双轨迁移策略确定
- [ ] 产出 `store-interface-spec.md`

### 7.2 阶段 2：Store 实现（8-10 周）
- [ ] 实现 ProgressStore
- [ ] 实现 DraftStore
- [ ] 实现 WorldStore
- [ ] 实现其他 5 个 Store
- [ ] 每个 Store 性能基准测试（劣化 >5% 则回退优化）
- [ ] 单元测试覆盖（Store 层独立测试）
- [ ] 产出 `store-implementation-spec.md`

### 7.3 阶段 3：迁移与验证（6-8 周）
- [ ] 选择 1-2 个低风险模块先迁移到 Store
- [ ] 验证双轨并存可行性
- [ ] 逐步迁移 `api/routes/` 调用方
- [ ] 逐步迁移 `agents/` 调用方
- [ ] 全量 pytest（3748 个测试）
- [ ] 性能回归测试
- [ ] version.py bump → 6.10.19
- [ ] CHANGELOG.md 更新
