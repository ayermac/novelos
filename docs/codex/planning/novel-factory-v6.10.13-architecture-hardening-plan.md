# Novelos v6.10.13 Architecture Hardening Plan

> **版本**: v6.10.13
> **主题**: 架构强化 — 借鉴 ainovel-cli 设计模式提升长篇创作可靠性
> **状态**: Draft
> **创建日期**: 2026-06-23
> **依赖版本**: v6.10.7 (Core Loop Evidence Governance)

---

## 1. 背景与动机

### 1.1 当前架构的优势

Novelos 在以下方面已经建立了坚实的基础：

- **结构化记忆管理**：Memory Curator Agent 专职维护角色、世界观、伏笔、事实账本
- **用户审核机制**：记忆更新需用户确认，避免 LLM 误提取导致的记忆污染
- **丰富的质量检查**：30+ Skill 覆盖 AI 痕迹、对白自然度、节奏控制等维度
- **完整的工作流**：17 个节点覆盖从规划到发布的全流程

### 1.2 当前架构的不足

通过对比分析 ainovel-cli 的设计，发现以下可以改进的地方：

| 维度 | 当前问题 | 影响 |
|------|----------|------|
| **断点恢复** | LangGraph checkpoint 是节点级，Agent 内部崩溃需重跑整个节点 | 长章节生成时中断代价大 |
| **路由决策** | 依赖 LLM 语义理解决定下一步 | LLM 不可靠时可能走错分支 |
| **停机防护** | 无物理兜底机制 | Agent 可能提前结束或陷入死循环 |
| **预算控制** | 无成本追踪和预算限制 | 长时间运行可能产生意外费用 |
| **风格统计** | 依赖 LLM 检测风格问题 | 全书级风格 tic 难以被单章检测发现 |
| **用户干预** | 无运行时注入机制 | 创作过程中无法实时调整方向 |

### 1.3 设计目标

借鉴 ainovel-cli 的核心设计哲学：

1. **事实与裁定分离**：代码收集事实，LLM 做裁定
2. **多层防御**：Prompt → Reminder → StopGuard，每层都有升级策略
3. **确定性优先**：能用代码解决的绝不依赖 LLM

---

## 2. 功能范围

### 2.1 P0：核心架构改进

#### 2.1.1 FlowRouter — 纯函数路由

**目标**：将"下一步做什么"的决策从 LLM 推理中剥离为确定性路由

**设计**：

```python
class FlowRouter:
    """纯函数路由：输入 State，输出 Instruction，无 IO"""
    
    @staticmethod
    def route(state: dict) -> Optional[dict]:
        """
        决策优先级（互斥，自上而下匹配）：
        1. Phase=Complete → 结束
        2. PendingRewrites 非空 → 重写
        3. PendingReviews 非空 → 处理评审
        4. PendingMemoryUpdates 非空 → 处理记忆更新
        5. 弧末后处理 → 评审/摘要
        6. 正常续写 → 下一章
        """
        # 纯函数，无副作用，可单测
```

**文件结构**：

```
novel_factory/dispatch/
├── flow_router.py      # 纯函数路由
├── state_loader.py     # 从 Store 加载路由状态
├── dispatcher.py       # 事件驱动的路由执行
└── __init__.py
```

**验收标准**：

- [ ] FlowRouter.route() 纯函数，无 IO、无 Store 调用
- [ ] 决策优先级覆盖所有章节状态
- [ ] 单元测试覆盖率 >= 90%
- [ ] 与现有 LangGraph 工作流集成

#### 2.1.2 SignalStore — 一次性信号机制

**目标**：记录待处理状态，支持跨会话恢复

**设计**：

```python
class SignalStore:
    """管理一次性信号文件"""
    
    def save_pending_commit(self, project_id: str, chapter: int, data: dict):
        """保存待提交状态"""
    
    def load_pending_commit(self, project_id: str) -> Optional[dict]:
        """加载待提交状态"""
    
    def clear_pending_commit(self, project_id: str):
        """清除待提交状态"""
    
    def save_pending_review(self, project_id: str, chapter: int, review: dict):
        """保存待处理评审"""
    
    def clear_stale_signals(self, project_id: str):
        """清理残留信号（进程重启时调用）"""
```

**信号类型**：

| 信号 | 文件 | 用途 |
|------|------|------|
| `pending_commit` | `signals/pending_commit.json` | 提交中断，需要恢复 |
| `pending_review` | `signals/pending_review.json` | 评审结果待处理 |
| `pending_memory` | `signals/pending_memory.json` | 记忆更新待应用 |
| `pending_steer` | `signals/pending_steer.json` | 用户干预待处理 |

**验收标准**：

- [ ] 信号文件支持原子性读写
- [ ] 进程重启时自动清理残留信号
- [ ] 与 FlowRouter 集成

#### 2.1.3 Step 级 Checkpoint — Agent 内部断点

**目标**：在 Agent 内部增加细粒度的 checkpoint，支持中断后精确恢复

**设计**：

```python
class StepCheckpoint:
    """Agent 内部 Step 级 checkpoint"""
    
    def save(self, project_id: str, chapter: int, step: str, data: dict):
        """保存 checkpoint"""
    
    def load(self, project_id: str, chapter: int, step: str) -> Optional[dict]:
        """加载 checkpoint"""
    
    def has_step(self, project_id: str, chapter: int, step: str) -> bool:
        """检查 checkpoint 是否存在"""
```

**Author Agent 改造示例**：

```python
class AuthorAgent(BaseAgent):
    def _execute(self, state: FactoryState) -> dict:
        project_id = state["project_id"]
        chapter = state["chapter_number"]
        
        # Step 1: 构思大纲
        if not self.checkpoint.has_step(project_id, chapter, "plan"):
            plan = self._plan_chapter(state)
            self.checkpoint.save(project_id, chapter, "plan", plan)
        else:
            plan = self.checkpoint.load(project_id, chapter, "plan")
        
        # Step 2: 分段生成正文
        segments = []
        for i, segment_plan in enumerate(plan["segments"]):
            step_name = f"segment_{i}"
            if not self.checkpoint.has_step(project_id, chapter, step_name):
                segment = self._generate_segment(state, segment_plan)
                self.checkpoint.save(project_id, chapter, step_name, segment)
            else:
                segment = self.checkpoint.load(project_id, chapter, step_name)
            segments.append(segment)
        
        # Step 3: 组装终稿
        if not self.checkpoint.has_step(project_id, chapter, "draft"):
            content = self._assemble_segments(segments)
            self.checkpoint.save(project_id, chapter, "draft", {"content": content})
        
        return {"content": content}
```

**验收标准**：

- [ ] Author、MemoryCurator 支持 Step 级 checkpoint
- [ ] 中断后能从最近的 checkpoint 恢复
- [ ] checkpoint 数据自动清理（章节提交后）

---

### 2.2 P1：防御机制

#### 2.2.1 StopGuard — 物理不可停机

**目标**：防止 Agent 提前结束或陷入死循环

**设计**：

```python
class StopGuard:
    """防止 Agent 提前结束的物理兜底"""
    
    def __init__(self, agent_id: str, required_checkpoints: list[str]):
        self.agent_id = agent_id
        self.required_checkpoints = required_checkpoints
        self.baseline_seq = 0
        self.consecutive_blocks = 0
        self.max_consecutive_blocks = 5
    
    def check_can_finish(self, checkpoints: list[dict]) -> tuple[bool, str]:
        """检查是否可以结束"""
        # 检查是否产生了新的必要 checkpoint
        new_checkpoints = [
            cp for cp in checkpoints
            if cp["seq"] > self.baseline_seq
            and cp["step"] in self.required_checkpoints
        ]
        
        if not new_checkpoints:
            self.consecutive_blocks += 1
            if self.consecutive_blocks >= self.max_consecutive_blocks:
                return False, "escalate"  # 升级为终止
            return False, "block"  # 阻止结束
        
        self.consecutive_blocks = 0
        return True, "pass"
```

**各 Agent 的 StopGuard 配置**：

| Agent | 必要 Checkpoint | 说明 |
|-------|-----------------|------|
| Author | `draft`, `commit` | 必须产出草稿并提交 |
| Editor | `review`, `save_summary` | 必须产出评审和摘要 |
| MemoryCurator | `memory_batch` | 必须产出记忆批次 |
| Planner | `instruction` | 必须产出写作指令 |

**验收标准**：

- [ ] 每个 Agent 有对应的 StopGuard
- [ ] 连续 5 次阻止后升级为终止
- [ ] checkpoint 产生后重置计数器

#### 2.2.2 BudgetSentinel — 预算哨兵

**目标**：追踪 LLM 调用成本，防止意外费用

**设计**：

```python
class BudgetSentinel:
    """预算状态机"""
    
    STATE_NORMAL = "normal"
    STATE_WARNED = "warned"
    STATE_STOP_PENDING = "stop_pending"
    STATE_STOPPED = "stopped"
    
    def __init__(self, limit_usd: float, warn_threshold: float = 0.8):
        self.limit = limit_usd
        self.warn_threshold = warn_threshold
        self.state = self.STATE_NORMAL
        self.total_cost = 0.0
    
    def on_cost(self, cost: float) -> Optional[dict]:
        """每次 LLM 调用后更新成本"""
    
    def can_start(self) -> tuple[bool, str]:
        """启动前检查"""
    
    def should_stop(self) -> bool:
        """是否应该停机"""
```

**验收标准**：

- [ ] 支持项目级预算配置
- [ ] 80% 预算时告警
- [ ] 100% 预算时停机
- [ ] 子代理边界停机（不浪费 in-flight 章节）

---

### 2.3 P2：质量保障

#### 2.3.1 StyleStats — 纯代码风格统计

**目标**：用确定性代码检测全书级风格问题

**统计维度**：

| 维度 | 检测方法 | 阈值 |
|------|----------|------|
| AI 文风 tic | 正则匹配 | 全书计数 + 每章均值 |
| 高频短语 | n-gram 挖掘 | >= max(8, 章数/2) |
| 跨章重复句 | 逐字比对 | >= 3 章出现的 >= 12 字句子 |
| 章末形态 | 模式匹配 | 短结尾比例 + 中位字数 |
| 开头时间词率 | 关键词计时 | 以"夜/清晨/黎明"开头的比例 |

**设计**：

```python
class StyleStats:
    """纯代码风格统计，不做裁定"""
    
    def compute(self, chapters: list[str], titles: list[str]) -> Optional[dict]:
        """计算全书风格统计"""
        if len(chapters) < 5:
            return None  # 样本太小
        
        return {
            "ai_tic_counts": self._count_ai_tics(chapters),
            "high_freq_phrases": self._find_high_freq_phrases(chapters),
            "repeated_sentences": self._find_repeated_sentences(chapters),
            "ending_patterns": self._analyze_ending_patterns(chapters),
            "opening_time_words": self._count_opening_time_words(chapters),
            "title_format_consistency": self._check_title_format(titles),
        }
```

**验收标准**：

- [ ] 统计结果注入 Editor 上下文
- [ ] 少于 5 章不出统计
- [ ] 统计结果持久化到数据库

#### 2.3.2 DiagnosisSystem — 诊断系统

**目标**：静态分析 + 运行时诊断

**诊断维度**：

| 维度 | 规则示例 |
|------|----------|
| Flow | rewrite_loop, stage_stuck, chapter_skip |
| Quality | low_score_dimensions, contract_miss_rate, excessive_rewrites |
| Planning | foreshadow_stagnation, compass_outdated, outline_exhausted |
| Memory | character_disappearance, timeline_gap, relationship_stale |

**设计**：

```python
class DiagnosisSystem:
    """静态分析 + 运行时诊断"""
    
    def diagnose(self, project_id: str) -> list[Finding]:
        """运行所有诊断规则"""
        snapshot = self._capture_snapshot(project_id)
        findings = []
        
        for dimension, rules in self.RULES.items():
            for rule_name in rules:
                rule_func = getattr(self, rule_name)
                results = rule_func(snapshot)
                findings.extend(results)
        
        return findings
```

**验收标准**：

- [ ] 诊断规则覆盖 4 个维度
- [ ] Finding 包含 severity、confidence、suggestion
- [ ] 诊断结果可通过 API 查询

---

### 2.4 P3：用户体验

#### 2.4.1 SteerManager — 用户干预

**目标**：支持创作过程中实时注入修改意见

**设计**：

```python
class SteerManager:
    """用户干预管理"""
    
    def steer(self, project_id: str, text: str):
        """运行时注入干预"""
        if self.is_running(project_id):
            # 直接注入到当前工作流
            self.inject_message(project_id, f"[用户干预] {text}")
        else:
            # 持久化，下次启动时注入
            self.repo.save_pending_steer(project_id, text)
    
    def resume_with_steer(self, project_id: str) -> Optional[str]:
        """恢复时检查是否有待处理的干预"""
        pending = self.repo.load_pending_steer(project_id)
        if pending:
            self.repo.clear_pending_steer(project_id)
            return f"用户在停机期间留下了一条干预意见：「{pending}」"
        return None
```

**验收标准**：

- [ ] 支持运行时注入
- [ ] 支持停机时持久化
- [ ] 支持恢复时重注入
- [ ] 干预消息带 `[用户干预]` 前缀

#### 2.4.2 Notifier — 通知系统

**目标**：无人值守告警

**设计**：

```python
class Notifier:
    """无人值守告警"""
    
    def __init__(self, command: str = None, events: list[str] = None):
        self.command = command  # 自定义命令（如 curl）
        self.events = events  # 过滤的事件类型
    
    def send(self, notification: dict):
        """异步发送通知"""
        if self.events and notification.get("kind") not in self.events:
            return
        
        threading.Thread(
            target=self._send_impl,
            args=(notification,),
            daemon=True
        ).start()
```

**通知事件**：

| 事件 | 触发时机 |
|------|----------|
| `run_end` | 创作完成或停止 |
| `budget_warn` | 预算告警 |
| `repeat_warn` | 指令重复告警 |
| `memory_pending` | 记忆更新待处理 |

**验收标准**：

- [ ] 支持自定义通知命令
- [ ] 支持事件过滤
- [ ] 异步非阻塞

---

## 3. 技术方案

### 3.1 文件结构变更

```
novel_factory/
├── dispatch/                    # 新增：路由层
│   ├── __init__.py
│   ├── flow_router.py           # 纯函数路由
│   ├── state_loader.py          # 状态加载器
│   └── dispatcher.py            # 事件驱动调度
├── guards/                      # 新增：防御层
│   ├── __init__.py
│   ├── stop_guard.py            # StopGuard
│   └── budget_sentinel.py       # BudgetSentinel
├── signals/                     # 新增：信号层
│   ├── __init__.py
│   └── store.py                 # SignalStore
├── stats/                       # 新增：统计层
│   ├── __init__.py
│   └── style_stats.py           # StyleStats
├── diag/                        # 新增：诊断层
│   ├── __init__.py
│   └── diagnosis.py             # DiagnosisSystem
├── notify/                      # 新增：通知层
│   ├── __init__.py
│   └── notifier.py              # Notifier
├── steer/                       # 新增：干预层
│   ├── __init__.py
│   └── steer_manager.py         # SteerManager
├── agent_runtime/               # 修改：增加 checkpoint 支持
│   ├── base.py                  # 增加 StepCheckpoint
│   └── step_checkpoint.py       # 新增
├── context/                     # 修改：增加风格统计注入
│   └── builder.py               # 增加 StyleStats 片段
└── workflow/                    # 修改：集成新组件
    ├── graph.py                 # 集成 FlowRouter
    └── nodes.py                 # 集成 StopGuard
```

### 3.2 数据库变更

```sql
-- 新增：诊断结果表
CREATE TABLE IF NOT EXISTS diagnosis_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    dimension TEXT NOT NULL,      -- flow / quality / planning / memory
    severity TEXT NOT NULL,       -- critical / warning / info
    confidence TEXT NOT NULL,     -- high / medium / low
    message TEXT NOT NULL,
    evidence TEXT,
    suggestion TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 新增：风格统计表
CREATE TABLE IF NOT EXISTS style_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    chapter_count INTEGER NOT NULL,
    stats_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id)
);

-- 新增：预算记录表
CREATE TABLE IF NOT EXISTS budget_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3.3 API 变更

```
# 诊断 API
GET  /api/diagnosis/{project_id}           # 获取诊断结果
POST /api/diagnosis/{project_id}/run       # 运行诊断

# 预算 API
GET  /api/budget/{project_id}              # 获取预算状态
PUT  /api/budget/{project_id}              # 设置预算限制

# 干预 API
POST /api/steer/{project_id}               # 注入干预

# 通知 API
GET  /api/notify/config                    # 获取通知配置
PUT  /api/notify/config                    # 设置通知配置
```

---

## 4. 实施计划

### 4.1 第一阶段：核心架构（v6.10.13-alpha）

**时间**：2 周

| 任务 | 优先级 | 负责人 | 状态 |
|------|--------|--------|------|
| FlowRouter 实现 | P0 | - | ✅ DONE |
| SignalStore 实现 | P0 | - | ✅ DONE |
| StepCheckpoint 实现 | P0 | - | ✅ DONE |
| 单元测试 | P0 | - | TODO |

### 4.2 第二阶段：防御机制（v6.10.13-beta）

**时间**：2 周

| 任务 | 优先级 | 负责人 | 状态 |
|------|--------|--------|------|
| StopGuard 实现 | P1 | - | ✅ DONE |
| BudgetSentinel 实现 | P1 | - | ✅ DONE |
| 集成测试 | P1 | - | TODO |

### 4.3 第三阶段：质量保障（v6.10.13-rc）

**时间**：2 周

| 任务 | 优先级 | 负责人 | 状态 |
|------|--------|--------|------|
| StyleStats 实现 | P2 | - | ✅ DONE |
| DiagnosisSystem 实现 | P2 | - | ✅ DONE |
| API 集成 | P2 | - | TODO |

### 4.4 第四阶段：用户体验（v6.10.13）

**时间**：2 周

| 任务 | 优先级 | 负责人 | 状态 |
|------|--------|--------|------|
| SteerManager 实现 | P3 | - | ✅ DONE |
| Notifier 实现 | P3 | - | ✅ DONE |
| 前端集成 | P3 | - | TODO |

---

## 5. 验收标准

### 5.1 功能验收

- [ ] FlowRouter 纯函数路由覆盖所有章节状态
- [ ] SignalStore 支持 4 种信号类型
- [ ] StepCheckpoint 支持 Author、MemoryCurator
- [ ] StopGuard 防止 Agent 提前结束
- [ ] BudgetSentinel 防止意外费用
- [ ] StyleStats 检测 5 种风格问题
- [ ] DiagnosisSystem 覆盖 4 个诊断维度
- [ ] SteerManager 支持运行时注入
- [ ] Notifier 支持自定义通知

### 5.2 测试验收

- [ ] 单元测试覆盖率 >= 80%
- [ ] 集成测试覆盖核心流程
- [ ] 端到端测试覆盖创作全流程

### 5.3 性能验收

- [ ] FlowRouter 路由延迟 < 10ms
- [ ] StyleStats 统计延迟 < 5s（100 章）
- [ ] DiagnosisSystem 诊断延迟 < 10s

---

## 6. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 与现有 LangGraph 工作流冲突 | 中 | 渐进式集成，保持向后兼容 |
| StepCheckpoint 增加 IO 开销 | 低 | 异步写入，批量清理 |
| StopGuard 误判导致终止 | 中 | 可配置阈值，支持手动覆盖 |
| 预算计算不准确 | 低 | 支持手动调整，提供估算工具 |

---

## 7. 参考资料

- [ainovel-cli 项目分析](https://github.com/voocel/ainovel-cli)
- [Novelos v6.10.7 Core Loop Evidence Governance](novel-factory-v6.10.7-core-loop-evidence-governance-plan.md)
- [Novelos v6.10.12 Production Stability Hardening](novel-factory-v6.10.12-production-stability-hardening-plan.md)

---

## 附录 A：与 ainovel-cli 设计对比

| 维度 | ainovel-cli | Novelos (v6.10.13) | 说明 |
|------|-------------|---------------------|------|
| 路由决策 | FlowRouter 纯函数 | FlowRouter 纯函数 | 相同设计 |
| 断点恢复 | Step 级 checkpoint | Step 级 checkpoint | 相同设计 |
| 停机防护 | StopGuard | StopGuard | 相同设计 |
| 预算控制 | BudgetSentinel | BudgetSentinel | 相同设计 |
| 风格统计 | StyleStats | StyleStats | 相同设计 |
| 用户干预 | Steer 机制 | SteerManager | 相同设计 |
| 记忆管理 | 分层摘要 | Memory Curator | Novelos 更优 |
| 用户审核 | 无 | 有 | Novelos 更优 |
| 质量检查 | Editor 七维评审 | 30+ Skill | Novelos 更优 |

---

## 附录 B：版本更新日志

```markdown
## v6.10.13 (2026-XX-XX)

### 新增
- FlowRouter 纯函数路由
- SignalStore 一次性信号机制
- StepCheckpoint Agent 内部断点
- StopGuard 物理不可停机
- BudgetSentinel 预算哨兵
- StyleStats 纯代码风格统计
- DiagnosisSystem 诊断系统
- SteerManager 用户干预
- Notifier 通知系统

### 改进
- 优化断点恢复机制
- 增强长篇创作可靠性
- 提升用户体验

### 修复
- 修复 Agent 提前结束问题
- 修复长时间运行的预算风险
```
