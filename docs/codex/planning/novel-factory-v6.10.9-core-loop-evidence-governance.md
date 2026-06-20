# Novel Factory v6.10.9 — 核心循环前置约束与事实锁感知

> 状态：规划阶段 | 基于 v6.10.8 生产问题（Chapter 16 连续 3 轮返修后仍卡在 human_review）

---

## 问题总结（v6.10.8 暴露）

Chapter 16 经历了 3 轮完整返修（Author→Polisher→Editor），评分从 68→69→68 徘徊，最终卡在 human_review。

**Editor 无法消除的硬问题：**
1. **核心循环漂移** —— 连续 2 章没有核心兑现证据（`reward_used` 缺失）
2. **事实一致性矛盾** —— 第 15 章陆璃被锁死，第 16 章 beats 设计却包含肢体互动
3. **对白占比过低** —— 4.6%，Author 改不上来
4. **章末钩子薄弱** —— 信息量不足，威胁不具体

**根本原因：** Planner/Screenwriter 的输出与 Editor 的审核标准之间存在**结构性 gap**。Editor 是"事后检测"，Planner/Screenwriter 是"事前设计"，两者标准不对齐。

---

## 设计缺陷定位

| 层面 | 当前状态 | 问题 |
|------|----------|------|
| **Planner** | 输出 chapter instruction：objective、key_events、plots_to_plant、ending_hook | **没有"核心循环兑现"约束**，不告诉 Author 第几个事件必须是爽点 |
| **Screenwriter** | 输出 scene_beats：sequence、scene_goal、conflict、turn、hook | **没有对白设计**，不预留对白空间；**没有事实锁感知**，不读取角色当前物理状态 |
| **Author** | 根据 beats 写正文 | 按 beats 执行，beats 本身有问题则正文必然有问题 |
| **Editor** | 五维度审核，含"爽点钩子"15分 + "核心循环检测" | 发现问题时已经太晚，只能返修 |

---

## v6.10.9 改进方案

### 目标

将 Editor 的审核标准**前置**到 Planner/Screenwriter 阶段，让"核心循环兑现"和"事实一致性"成为**设计约束**而非**事后检测**。

### 1. Planner 增加核心循环约束

#### 1.1 `ChapterInstruction` 新增字段

```python
# novel_factory/models/schemas.py (新增)
class CoreLoopDesign(BaseModel):
    """v6.10.9: 核心循环设计约束 —— Planner 输出时必须指定"""
    
    # 第几个 key_event 负责核心爽点兑现（1-based index）
    reward_event_index: int = Field(
        ..., ge=1, le=5,
        description="指定第几个关键事件为核心爽点兑现"
    )
    
    # 爽点类型：能力展示 / 智斗胜利 / 情感爆发 / 身份揭示 / 资源获取
    reward_type: str = Field(
        ..., 
        pattern="^(ability|intellect|emotion|identity|resource)$"
    )
    
    # 爽点具体描述（禁止抽象，必须有可感知的胜利标志）
    reward_evidence: str = Field(
        ..., min_length=20,
        description="具体的爽点证据描述，如'陆璃短暂恢复意识说了一个字'"
    )
    
    # 主角在爽点中的主动决策（必须有，不能是被动的）
    protagonist_decision: str = Field(
        ..., min_length=10,
        description="主角做出的关键决策或行动"
    )


class ChapterInstruction(BaseModel):
    """v6.10.9: 增强版章节指令"""
    objective: str
    chapter_goal: str
    key_events: list[str]  # 限制最多 3-4 个（见 1.2）
    plots_to_plant: list[str]
    plots_to_resolve: list[str]
    ending_hook: str
    constraints: list[str]
    
    # v6.10.9 新增
    core_loop: CoreLoopDesign  # 核心循环设计约束
    dialogue_target_ratio: float = 0.15  # 目标对白占比 ≥ 15%
    fact_locks: list[str]  # 从上一章继承的事实锁（角色物理状态等）
```

#### 1.2 Planner 系统提示增强

```
PLANNER_SYSTEM_PROMPT 追加：

【核心循环设计约束 v6.10.9】
每个 chapter instruction 必须包含 core_loop 字段：
1. 从 key_events 中指定 1 个事件作为核心爽点兑现（reward_event_index）
2. 爽点必须有具体的、可感知的胜利标志（reward_evidence）
3. 主角在爽点中必须有主动决策（protagonist_decision），不能是被动接受系统提示
4. key_events 总数不超过 3 个（给每个事件留出展开空间）
5. ending_hook 必须包含具体威胁或明确的后续行动指向

【事实锁继承 v6.10.9】
1. 必须读取上一章的 fact_locks，明确各角色的物理状态
2. 如果角色被"锁死/濒死/昏迷"，本章不能设计与之的肢体互动
3. 所有涉及前章设定的 key_event 必须与 fact_locks 兼容

【对白设计约束 v6.10.9】
1. 目标对白占比 ≥ 15%
2. 至少设计 1 段有冲突或潜台词的角色对白
```

### 2. Screenwriter 增加对白设计与事实锁感知

#### 2.1 `SceneBeat` 增强

```python
# novel_factory/models/schemas.py (修改)
class SceneBeat(BaseModel):
    """v6.10.9: 增强版场景 beat"""
    
    sequence: int
    scene_goal: str
    conflict: str = ""
    turn: str = ""
    plot_refs: list[str] = Field(default_factory=list)
    hook: str = ""
    
    # v6.10.9 新增
    # 该 beat 是否承载核心爽点
    is_reward_beat: bool = False
    
    # 对白设计槽位（每个 beat 预留 0-2 段对白）
    dialogue_slots: list[DialogueSlot] = Field(default_factory=list)
    
    # 该 beat 涉及的角色及当前可用状态
    character_states: dict[str, str] = Field(
        default_factory=dict,
        description="角色在本 beat 中的物理状态，如{'陆璃': '锁死于金属床，无意识'}"
    )


class DialogueSlot(BaseModel):
    """v6.10.9: 对白设计槽位"""
    speakers: list[str]  # 对话双方
    conflict_type: str = ""  # 立场对立 / 信息差 / 潜台词
    key_line: str = ""  # 必须包含的关键台词（可留空让 Author 发挥）
    must_convey: str = ""  # 这段对白必须传递的信息
```

#### 2.2 Screenwriter 系统提示增强

```
SCREENWRITER_SYSTEM_PROMPT 追加：

【核心循环前置 v6.10.9】
1. 读取 Planner instruction 中的 core_loop.reward_event_index
2. 将该事件对应的 beat 标记为 is_reward_beat = true
3. 确保该 beat 的 scene_goal 明确包含核心爽点的展开
4. 确保主角在该 beat 中有主动行动，不是被动接受

【事实锁感知 v6.10.9】
1. 读取 instruction.fact_locks 中的角色物理状态
2. 每个 beat 的 character_states 必须反映这些限制
3. 如果角色状态是"锁死/无意识"，dialogue_slots 中不能包含该角色的主动发言

【对白设计 v6.10.9】
1. 总对白槽位数 ≥ 3（对应 15% 占比目标）
2. 至少 1 段对白必须有冲突（conflict_type 不为空）
3. 避免所有信息通过旁白/说明传递，优先设计对白
```

### 3. Author 根据新字段调整写作

#### 3.1 系统提示增强

```
AUTHOR_SYSTEM_PROMPT 追加：

【核心循环写作约束 v6.10.9】
1. 识别 scene_beats 中 is_reward_beat = true 的 beat
2. 该 beat 必须写出具体的爽点兑现，不能模糊
3. 爽点必须有主角的主动决策或高光行动
4. 爽点兑现后不要马上切入新事件，留 1-2 句余韵

【对白写作 v6.10.9】
1. 优先填充 dialogue_slots 中的对白槽位
2. 对白要有角色目的、潜台词或冲突
3. 不同角色语气有差异
4. 禁止所有信息通过旁白说明传递

【事实锁遵守 v6.10.9】
1. 严格按照 character_states 中的角色状态写作
2. 被锁死的角色不能有主动肢体动作或语言
```

### 4. Editor 审核标准与前置约束对齐

#### 4.1 检测逻辑调整

```python
# novel_factory/agents/editor.py (修改)
# 原有的"核心循环漂移"检测改为：
# 1. 读取 scene_beats 中 is_reward_beat 的位置
# 2. 检查正文是否在该位置有对应的爽点兑现
# 3. 如果没有，不是"作者写得不好"，而是"Screenwriter 没设计好"
#    → 路由到 Screenwriter 重新设计 beats（新增路由路径）
```

#### 4.2 新增路由：`screenwriter_redesign`

当 Editor 检测到：
- 核心循环缺失（但 scene_beats 中 is_reward_beat = true）
- 事实一致性矛盾（但 character_states 与正文不符）

路由到 **Screenwriter** 重新设计 beats，而非让 Author 在错误的 beats 上反复修改。

```python
# novel_factory/workflow/conditions.py (新增)
def route_to_screenwriter_redesign(state: FactoryState) -> str:
    """v6.10.9: 当核心循环设计缺陷被检测到时，路由到 Screenwriter 重新设计"""
    review = state.get("last_review")
    if not review:
        return "author"
    
    # 检测是否是 beats 设计层面的问题
    beats = state.get("scene_beats", [])
    has_reward_beat = any(b.get("is_reward_beat") for b in beats)
    
    if has_reward_beat and "核心循环漂移" in str(review.get("issues", [])):
        # beats 设计了核心循环但 Author 没写出来 → Author 问题
        return "author"
    
    if not has_reward_beat and "核心循环漂移" in str(review.get("issues", [])):
        # beats 根本没设计核心循环 → Screenwriter 问题
        return "screenwriter_redesign"
    
    return "author"
```

### 5. 数据模型变更汇总

| 文件 | 变更 | 说明 |
|------|------|------|
| `novel_factory/models/schemas.py` | 新增 `CoreLoopDesign`、`DialogueSlot`，修改 `SceneBeat`、`ChapterInstruction` | 核心数据结构 |
| `novel_factory/agents/planner.py` | 系统提示增强 + `core_loop` 字段输出 | 前置约束 |
| `novel_factory/agents/screenwriter.py` | 系统提示增强 + `is_reward_beat`/`dialogue_slots`/`character_states` | 事实锁感知 + 对白设计 |
| `novel_factory/agents/author.py` | 系统提示增强 + 识别新字段 | 按约束写作 |
| `novel_factory/agents/editor.py` | 检测逻辑调整 + 新增 `screenwriter_redesign` 路由 | 对齐前置约束 |
| `novel_factory/workflow/conditions.py` | 新增 `route_to_screenwriter_redesign` | 路由逻辑 |
| `novel_factory/workflow/graph.py` | 新增 `screenwriter_redesign` 节点 | 工作流扩展 |

### 6. 回退兼容性

- 所有新增字段有默认值，旧数据不触发异常
- `is_reward_beat` 默认为 `false`，旧 beats 走原有逻辑
- Editor 的"核心循环漂移"检测保留，作为兜底

---

## 预期效果

| 问题 | v6.10.8 状态 | v6.10.9 预期 |
|------|-------------|--------------|
| 核心循环漂移 | Editor 事后检测，Author 反复修改无果 | Planner 事前约束，Screenwriter 明确标记 |
| 事实一致性矛盾 | Screenwriter 不读前章状态 | Screenwriter 读取 fact_locks 并写入 character_states |
| 对白占比低 | Author 缺乏对白设计指导 | Screenwriter 预留 dialogue_slots，Author 优先填充 |
| 章末钩子薄弱 | Planner 只写 ending_hook 字符串 | ending_hook 必须包含具体威胁或行动指向 |
| 返修效率低 | 3 轮返修后仍失败 | 设计缺陷早发现，路由到 Screenwriter 重新设计而非 Author 死磕 |

---

## 实施计划

| 阶段 | 任务 | 预估工作量 |
|------|------|-----------|
| 1 | 数据模型变更（schemas.py） | 1h |
| 2 | Planner 系统提示增强 + core_loop 输出 | 2h |
| 3 | Screenwriter 系统提示增强 + 新字段输出 | 2h |
| 4 | Author 系统提示增强 | 1h |
| 5 | Editor 检测逻辑调整 + 新路由 | 3h |
| 6 | Workflow graph 扩展 | 2h |
| 7 | 测试 + 回归 | 4h |
| **总计** | | **15h** |

---

## 风险与替代方案

| 风险 | 缓解措施 |
|------|----------|
| Planner 增加 core_loop 后输出 token 增加 | 压缩其他字段长度，或提升 max_tokens |
| Screenwriter 的 dialogue_slots 限制 Author 创作自由 | `key_line` 可为空，只约束"必须有冲突"不约束具体内容 |
| 新增路由增加 workflow 复杂度 | `screenwriter_redesign` 只在检测到设计缺陷时触发，正常路径不变 |
| 向后兼容旧项目 | 所有新增字段有默认值，旧数据自动降级到原有行为 |

---

## 附录：Chapter 16 如果用 v6.10.9 会怎么设计

### Planner 输出（v6.10.9）

```yaml
objective: "魂源统帅清零的陆恒被迫成为血池新核心，必须在72小时内掌握泵血能力拯救陆璃和苏晚棠"
chapter_goal: "陆恒完成首次泵血，产生可感知的微型胜利"

key_events:
  - "陆恒接受新核身份，感知血池系统结构"
  - "陆恒首次尝试泵血，成功引导魂源至苏晚棠"  # reward_event_index=2
  - "陆恒发现陆璃有微弱反应，确认泵血有效"

core_loop:
  reward_event_index: 2
  reward_type: "ability"
  reward_evidence: "苏晚棠的魂源泄露停止，生命体征稳定；陆恒感受到系统控制权从被动变为主动"
  protagonist_decision: "陆恒在魂源冲击剧痛下坚持引导，选择先救苏晚棠而非自保"

dialogue_target_ratio: 0.15

fact_locks:
  - "陆璃：无呼吸，胸口无起伏，被LH-0427-F金属环锁于血池舱金属床，连接多根输液管，无意识"
  - "苏晚棠：魂源持续泄露，处于濒死状态"
  - "陆恒：魂源=0，统帅=0，神军沉寂"
```

### Screenwriter 输出（v6.10.9）

```yaml
scene_beats:
  - sequence: 1
    scene_goal: "陆恒在血池舱中醒来，感知系统逆转"
    conflict: "零魂源者被迫承受系统核心压力"
    is_reward_beat: false
    character_states:
      陆恒: "清醒，剧痛，零魂源"
      陆璃: "无意识，锁死于金属床"
    dialogue_slots: []

  - sequence: 2
    scene_goal: "陆恒首次泵血，引导魂源拯救苏晚棠"
    conflict: "外来魂源狂暴冲击 vs 陆恒意志力"
    turn: "从被动承受转为主动引导"
    hook: "苏晚棠生命体征首次稳定"
    is_reward_beat: true
    character_states:
      陆恒: "清醒，剧痛但坚持"
      苏晚棠: "濒死，魂源泄露中"
    dialogue_slots:
      - speakers: [陆恒, 苏晚棠]
        conflict_type: "信息差"
        must_convey: "苏晚棠在昏迷中无意识地喊了一声'陆恒'，让陆恒确认泵血有效"

  - sequence: 3
    scene_goal: "陆恒发现陆璃手指微动，系统提示72小时倒计时"
    conflict: "时间压力 vs 不确定性"
    hook: "加密遗言揭示第二轮选核威胁"
    is_reward_beat: false
    character_states:
      陆恒: "疲惫但坚定"
      陆璃: "无意识，但输液管有微弱逆流反应"
    dialogue_slots:
      - speakers: [陆恒, 系统提示]
        conflict_type: "立场对立"
        must_convey: "系统冷冰冰地播报'新核负债率47%，72小时内未达标将启动第二轮选核'"
```

---

*文档版本：v6.10.9-draft-1*
*作者：Codex Agent*
*日期：2026-06-18*
