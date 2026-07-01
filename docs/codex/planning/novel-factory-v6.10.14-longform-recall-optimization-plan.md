# Novelos v6.10.14 长篇数据召回优化计划

> **版本**: v6.10.14
> **主题**: 长篇数据召回优化 — 量化召回瓶颈，提升召回率与准确性，修复上下文裁剪缺陷
> **状态**: Released
> **创建日期**: 2026-06-30
> **依赖版本**: v6.10.13 (Architecture Hardening) / v6.10.7 (Core Loop Evidence Governance)
> **基线版本**: v6.10.13（`__version__ = "6.10.13"`，2616/2616 pytest passing）

---

## 0. 文档目的与边界

本文档是 v6.10.14 的**版本规划与归档文档**，覆盖三项任务：

1. 长篇数据召回性能瓶颈分析与召回率/准确性提升方案
2. 现有流程缺陷全面排查（含此前已发现问题）与修复策略
3. 上述任务的优先级、预期目标与可追溯记录

**边界**：本文档仅做规划。代码实现、测试编写、版本号 bump 在用户确认后另行执行（见 §9 执行清单）。

---

## 1. 背景与动机

### 1.1 v6.10.13 的基础

v6.10.13 已引入"借鉴 ainovel-cli 设计模式"的架构强化（FlowRouter、StopGuard、Reminder 等），但**长篇数据召回**这一具体主题尚未系统治理。随着项目进入 100+ 章长篇场景，前期数据召回问题逐渐暴露：

- 第 5 章埋设的道具/伏笔，到第 67 章时上下文里可能已无踪影
- 数值状态（剩余次数、等级、余额）在长篇下可能被裁剪丢失
- 全量加载的事实账本随章数单调膨胀，挤占有限上下文预算

### 1.2 关键事实校正

前期分析曾引用 `context/builder.py` 的 `DEFAULT_TOKEN_BUDGET = 4000`，经核实该文件为**遗留旧代码**，生产路径实际使用 `agent_runtime/context_builder.py`，预算为 `_MAX_CONTEXT_CHARS = 14000`（约 21000 token）。本文档所有瓶颈分析均以生产路径为准。

### 1.3 设计目标

1. **召回率**：长篇（100+ 章）下，与当前章相关的事实/伏笔/数值状态 100% 进入上下文，不被预算裁剪丢失
2. **召回准确性**：从"全量加载 + 优先级裁剪"转向"相关性筛选 + mandatory 保护"，减少无关信息噪音
3. **确定性优先**：召回逻辑尽量用纯代码派生（账龄、相关性匹配），不依赖 LLM
4. **零破坏**：不改变 LangGraph 工作流结构与 `AgentContextBuilder` 对外接口，保持 2616 测试基线

---

## 2. 长篇召回性能瓶颈分析

### 2.1 生产路径确认

| 文件 | 角色 | 预算 |
|------|------|------|
| `context/builder.py` | 遗留旧代码，几乎无生产调用 | 4000 token |
| `agent_runtime/context_builder.py` | **生产路径**，所有 agent 使用 | 默认 14000 字符 |

核心入口：`format_context_bundle_for_prompt(bundle, agent_name, max_chars=14000)`（context_builder.py:1512）

> **重要校正**：`14000` 仅为函数默认值。生产中各 agent 调用时均显式覆盖该参数，实际预算如下表。瓶颈评估须以各 agent 实际预算为准（最紧为 author 主路径的 **8000** 字符、editor 精简路径的 **6000** 字符）。

| Agent | 实际 max_chars | 调用位置 |
|-------|---------------|----------|
| planner | 12000 | planner.py:140 |
| screenwriter | 12000 | screenwriter.py:102 |
| author（主路径） | 8000 | author.py:3042 |
| author（另一路径） | 见 author.py:196 | author.py:196 |
| polisher | 见 polisher.py:220 | polisher.py:220 |
| editor（主路径） | 12000 | editor.py:248 |
| editor（精简路径） | 6000 | editor.py:357 |

### 2.2 瓶颈清单

| 编号 | 瓶颈 | 位置 | 量化影响 | 根因 |
|------|------|------|----------|------|
| **B1** | **story_facts 全量加载（3 处）** | context_builder.py:242 / :396 / :774 三处均调用 `list_story_facts(status="active")` 全量加载 | 200 章后数百条事实全量读入后分别进入 timeline / numeric_state / story_facts bucket，单 bucket 膨胀到数千字符 | 无相关性筛选，全量返回（:396 有 `[:10]` 截断、:242 按 fact_type 过滤，但仍为全量读入后再过滤） |
| **B2** | **break 一刀切裁剪** | context_builder.py:1577-1583 | 某高优先级 bucket 占满预算后，**后续所有 bucket 整块丢弃**，而非每 bucket 内部裁剪 | `break` 语义过激 |
| **B3** | **numeric_state 非强制保留** | context_builder.py:1536 (排序第 5 位) + :1583 break | story_facts(第4) 膨胀时，numeric_state(第5) 整块丢失 → Writer 不知"玉符剩余几次" | 关键数值未标 mandatory |
| **B4** | **无账龄检测** | 全局缺失 | 久未推进的伏笔/事实永久沉底遗忘（ainovel-cli 有 30 章账龄回填，novelos 缺失） | 无"久未推进"派生逻辑 |
| **B5** | **无相关性召回** | context_builder.py:774 全量 | Writer 拿到大量无关事实，挤占预算且增加噪音 | 未按当前章 `required_events`/实体筛选 |
| **B6** | **无 Pull 通道** | 全局缺失 | Writer 拿到上下文后无任何检索能力，缺信息只能将就 | 纯 push 模式 |
| **B7** | **story_facts 未注入校验集** | continuity_checker.py:160 `_build_context`：章节/状态卡/指令按 `[from,to]` 范围加载，伏笔已全局加载（:201 `get_pending_plots`），但 **story_facts 完全未加载** | 写作上下文中注入的事实不在校验视野内，主角"失去左臂后仍双手握剑"类矛盾无法被检出 | story_facts 未注入校验集 |
| **B8** | **预算固定不自适应** | context_builder.py:28 `_MAX_CONTEXT_CHARS = 14000` | 长篇与短篇用同一预算，长篇偏紧、短篇偏松 | 未按章数动态调整 |

### 2.3 量化预估（200 章长篇场景）

假设 200 章累积：角色 20、道具/资源 15、关系 30、伏笔 40、numeric_state 25、其他事实 50 → active story_facts 约 180 条。

- 当前行为：180 条全量进入 `story_facts` bucket，去重后仍可能 80+ 条 × ~50 字符 ≈ 4000 字符
  - 占 author 实际预算（8000 字符）的 **50%**；占 editor 精简路径（6000 字符）的 **67%**
  - （此前按默认 14000 估算为 28%，严重低估实际压力）
- 一旦叠加 `hard_constraints`、`revision_feedback`、`timeline_constraints`、`plot_obligations`、`character_states` 等膨胀，在 author 8000 预算下极易触发 B2 break，`numeric_state_constraints`（第5位）及后续 bucket 被整块丢弃
- 实际后果：第 67 章写作时，玉符剩余次数不在上下文 → Writer 可能写错使用次数

---

## 3. 召回率与准确性提升方案

### 3.1 方案矩阵

| 方案 | 解决瓶颈 | 优先级 | 改动范围 | 预期收益 |
|------|----------|--------|----------|----------|
| **S1 mandatory bucket 保护** | B2, B3 | P0 | context_builder.py 裁剪逻辑 | 关键事实永不丢失 |
| **S2 story_facts 相关性筛选** | B1, B5 | P0 | `_story_facts_context` + 新增筛选函数 | 账本 bucket 从全量降到相关性子集 |
| **S3 per-bucket 内部裁剪** | B2 | P0 | 裁剪循环改 break 为 continue | 后续 bucket 不被误伤 |
| **S4 账龄检测器** | B4 | P1 | 新建 `context/aging.py` + 注入 | 久挂事实强制提醒 |
| **S5 Pull 召回通道** | B6 | P1 | 新建 `context/recall_channel.py` | Writer 可按需检索历史事实链 |
| **S6 continuity 全量校验集** | B7 | P1 | continuity_checker `_build_context` | 校验覆盖面 ⊇ 写作集 |
| **S7 自适应预算** | B8 | P2 | `_MAX_CONTEXT_CHARS` 动态化 | 长篇放宽预算 |
| **S8 索引脊柱** | B5 补充 | P2 | 新增轻量索引视图分片 | 解决"未知的未知" |

### 3.2 S1 + S3：mandatory 保护与 per-bucket 裁剪（P0，最高优先级）

**目标**：消除 B2 break 误伤，保证 numeric_state/timeline/hard_constraints 永不丢失。

**设计**：

> **mandatory 集合说明**：`hard_constraints` / `numeric_state_constraints` / `timeline_constraints` 列为 mandatory（关键约束丢失即致内容矛盾）。`revision_feedback`（第 2 位）虽重要，但排序靠前、通常先于 story_facts 写入，不会触发裁剪；且其内容多由 Editor 明确指令构成，体积可控，故不列入强塞集合——若 revision 阶段反馈超长，应在上游做反馈条目去重/精简，而非在裁剪层强塞。

```python
# agent_runtime/context_builder.py — format_context_bundle_for_prompt 改造

# header → 机器友好 key 的映射（与 ordered_buckets 配套，按索引对齐）
BUCKET_KEYS = [
    "hard_constraints",
    "revision_feedback",
    "timeline_constraints",
    "story_facts",
    "numeric_state_constraints",
    "plot_obligations",
    "trusted_memory",
    "character_states",
    "story_contract_context",
    "core_loop_context",
    "scene_beats",
    "style_context",
    "advisory_context",
    "chapter_inheritance",
    "project_context",
]

# 不可裁剪的 bucket（即使超预算也强塞）
MANDATORY_BUCKETS = {
    "hard_constraints",
    "numeric_state_constraints",
    "timeline_constraints",
}

for idx, (header, items) in enumerate(ordered_buckets):
    if not items:
        continue
    bucket_name = BUCKET_KEYS[idx]
    # ... 组装 block_lines / block（同既有逻辑）...
    block_len = len(block)

    if total_len + block_len > max_chars:
        if bucket_name in MANDATORY_BUCKETS:
            # mandatory：即使超预算也强塞，宁可整体超不可丢
            parts.append(block)
            total_len += block_len
            continue  # 继续处理后续 bucket

        # 非 mandatory：bucket 内部按行裁剪到剩余空间
        remaining = max_chars - total_len - len(header) - 50
        if remaining > 200:
            truncated = True
            # 按行累加而非字符切片，避免截断在 UTF-8 多字节/行中间产生乱码
            kept: list[str] = [header]
            used = len(header) + 1
            for line in block_lines[1:]:
                if used + len(line) + 1 > remaining:
                    break
                kept.append(line)
                used += len(line) + 1
            kept.append("...(已截断)")
            parts.append("\n".join(kept))
            total_len = max_chars
        # 关键修正：不 break，continue 让后续 mandatory bucket 仍有机会写入
        continue
    else:
        parts.append(block)
        total_len += block_len
```

> **关键修正**：原草案此处为 `break`，会导致 story_facts（第 4 位，非 mandatory）触发截断后直接退出循环，跳过第 5 位的 `numeric_state_constraints`（mandatory），与 S1 目标自相矛盾。必须改为 `continue`。

**预期目标**：长篇下 `numeric_state_constraints` 100% 进入上下文，不再因 `story_facts` 膨胀而丢失。

### 3.3 S2：story_facts 相关性筛选（P0）

**目标**：从全量加载转向按当前章相关性召回，解决 B1/B5。

**设计**：

```python
# agent_runtime/context_builder.py — _story_facts_context 改造

def _story_facts_context(self, project_id, chapter_number, brief=None):
    facts = self.repo.list_story_facts(project_id, status="active")
    # 1. 既有去重逻辑保留（v6.10.11）
    latest_facts = self._dedup_latest(facts, chapter_number)

    # 2. 新增：相关性筛选
    #    - numeric_state 类：全留（关键数值不可丢）
    #    - 其他类：仅保留与本章 brief 实体/关键词相关的
    relevant = self._filter_relevant_facts(latest_facts, brief, chapter_number)
    return self._to_context_items(relevant)

def _filter_relevant_facts(self, facts, brief, chapter_number):
    if brief is None:
        return facts  # 无 brief 时回退全量，保证不退化
    entities = self._extract_entities(brief)  # required_events + 角色名匹配
    result = []
    for f in facts:
        fact_type = f.get("fact_type", "")
        if fact_type == "numeric_state":
            result.append(f)           # 数值状态全留
        elif f.get("subject") in entities:
            result.append(f)           # 相关实体留
        elif self._age(f, chapter_number) >= AGING_THRESHOLD:
            result.append(f)           # 账龄超阈值留（与 S4 联动）
    return result
```

**预期目标**：200 章场景下 `story_facts` bucket 从 80+ 条降到 15-20 条，token 占用降 70%+。

**brief 传入链路（重要）**：当前 `_story_facts_context(self, project_id, chapter_number)` 签名无 brief，被 5 处 `build_*_context` 方法调用（context_builder.py:1334/1373/1407/1441/1476）。S2 改造需：

1. 新增可选参数 `brief: dict | None = None`，保持向后兼容（无 brief 时回退全量，见 F9）
2. brief 数据源：从 `repo.get_instruction(project_id, chapter_number)` 读取本章写作指令，取 `required_events` / `key_events` / `objective` 字段
3. 5 个 `build_*_context` 方法各自通过 `self._load_brief(project_id, chapter_number)` 获取 brief 后传入；`_load_brief` 做一次缓存避免重复查询
4. `AgentContextBuilder` 对外接口（`build_context_for_agent` 等）不变，brief 在内部派生

**实体提取策略（`_extract_entities`）**：

- 主源：brief 的 `required_events` / `key_events` 列表，按中文分词提取名词性实体
- 辅源：`repo.get_characters(project_id)` 的角色名列表，做**全名边界匹配**（正则 `(?<![\u4e00-\u9fa5])name(?![\u4e00-\u9fa5])`），避免"张三"误匹配"张三丰"
- 匹配维度：fact 的 `subject` 字段命中实体，或 `value_json` 包含实体关键词
- 无 brief 时返回空集合 → `_filter_relevant_facts` 回退全量（保证不退化）

### 3.4 S4：账龄检测器（P1）

**目标**：补 B4，借鉴 ainovel-cli `foreshadowAgingChapters` 思路，纯代码派生。

**设计**：新建 `context/aging.py`，提供 `detect_aging_facts` / `detect_aging_plots`，在 ContextBuilder 注入 `aging_warnings` 分片（P3 优先级）。

- numeric_state 超 15 章未变 → 告警
- 伏笔无 planned_resolve 且超 20 章，或 planned_resolve 已过未兑现 → 告警
- 最多 5 条，按"最久未动"排序

**预期目标**：久挂伏笔/事实不再被静默遗忘，强制进入 Writer 视野。

### 3.5 S5：Pull 召回通道（P1）

**目标**：补 B6，把召回从"纯 push"变成"push + pull"。

**设计**：新建 `context/recall_channel.py`，提供结构化检索（entity / fact_type / keyword / plot_code / chapter_range）。注入方式采用**预判式 Pull**（从 brief 提取实体，主动召回其事实链），不做 tool-calling（避免改动 `BaseAgent._invoke_json` 单次调用模型）。

**预期目标**：Writer 写到"主角掏出玉符"时，上下文已备好玉符的剩余次数 + 变化链，不再依赖 Memory Curator 是否漏提。

### 3.6 S6：continuity 全量校验集（P1）

**目标**：补 B7，让校验集 ⊇ 写作集。

**设计**：`continuity_checker._build_context` 末尾追加全量 active story_facts 作为"校验用账本"，并在 system prompt 增加"主动扫描未注入事实的矛盾"职责。

**预期目标**：堵住"未注入就不校验"的漏洞，如主角失去左臂后仍写"双手握剑"能被检出。

### 3.7 S7 + S8：自适应预算与索引脊柱（P2，后置）

- **S7**：`_MAX_CONTEXT_CHARS` 按 `total_chapters` 动态化（>100 章 → 20000）。**注意**：仅改默认值不够——各 agent 调用点（planner.py:140 / screenwriter.py:102 / author.py:3042 / editor.py:248,357 等）均显式传 `max_chars`，须同步改为读取动态预算或移除显式覆盖，否则改动不生效
- **S8**：新增轻量索引视图分片（仅 fact_key/type/章节，~几十字节/条），让 Writer 知道"存在哪些线"，细节走 Pull

**预期目标**：长篇预算自适应；解决"未知的未知"。

---

## 4. 流程缺陷全面排查清单

### 4.1 此前已发现问题（来源于前序分析，归档确认）

| 编号 | 缺陷 | 位置 | 严重度 | 状态 |
|------|------|------|--------|------|
| **F1** | break 一刀切裁剪误伤后续 bucket | context_builder.py:1583 | High | = B2/S1 |
| **F2** | numeric_state 可被裁剪丢失 | context_builder.py:1536 | High | = B3/S1 |
| **F3** | story_facts 全量加载无筛选 | context_builder.py:774 | High | = B1/S2 |
| **F4** | 无账龄检测，久挂事实遗忘 | 全局缺失 | Medium | = B4/S4 |
| **F5** | continuity 校验集 = 写作集 | continuity_checker.py:160 | Medium | = B7/S6 |
| **F6** | 无 Pull 检索通道 | 全局缺失 | Medium | = B6/S5 |

### 4.2 本次新增排查发现

| 编号 | 缺陷 | 位置 | 严重度 | 修复策略 |
|------|------|------|--------|----------|
| **F7** | 预算固定不自适应章数 | context_builder.py:28 | Low | S7 动态化 |
| **F8** | story_facts value 截断 200 字符硬编码 | context_builder.py:795 | **High** | 改为按 fact_type 差异化截断；**numeric_state 类豁免截断**（与 S1 mandatory 保护同阶段实施，否则强塞的 numeric_state 内容仍被截断致残缺） |
| **F9** | `_filter_relevant_facts` 无 brief 时回退全量，长篇仍可能膨胀 | S2 新逻辑 | Low | 回退路径叠加 S4 账龄兜底 |
| **F10** | mandatory bucket 强塞可能整体超预算 | S1 新逻辑 | Low | 加 `total_overflow` 告警日志，不阻断 |
| **F11** | Pull 预判式注入可能召回过多 | S5 新逻辑 | Low | 硬上限 10 条 + token 预算隔离 |
| **F12** | 索引脊柱分片可能与 story_facts bucket 重复 | S8 新逻辑 | Low | 索引仅元数据，与 story_facts value 互补不重复 |

### 4.3 非召回类流程缺陷（顺带排查）

| 编号 | 缺陷 | 位置 | 严重度 | 修复策略 |
|------|------|------|--------|----------|
| **F13** | `context/builder.py` 遗留旧代码未清理 | context/builder.py 全文 | Low | 标注 deprecated 或删除，避免后续误用（本次分析曾误引用） |
| **F14** | `numeric_state_constraints_from_facts` 硬限 `[:10]` | context_builder.py:402 | Low | 与 S2 联动，相关筛选后可放宽上限 |
| **F15** | `format_context_bundle_for_prompt` docstring 与实际 `ordered_buckets` 不一致 | context_builder.py:1519-1547 | Low | docstring 缺列 `numeric_state_constraints`/`story_contract_context`/`core_loop_context`/`scene_beats`/`style_context`，且 `plot_obligations` 优先级标错；修正 docstring 与代码对齐，避免后续维护误判 |

---

## 5. 优先级与执行阶段

### 5.1 阶段划分

| 阶段 | 任务 | 优先级 | 依赖 | 预计改动 |
|------|------|--------|------|----------|
| **阶段 1** | S1 mandatory 保护 + S3 per-bucket 裁剪 | P0 | 无 | context_builder.py 裁剪逻辑 |
| **阶段 1** | S2 story_facts 相关性筛选 | P0 | 需 brief 传入链路 | context_builder.py `_story_facts_context` |
| **阶段 1** | F8 numeric_state 截断豁免 | P0 | 与 S1 同步 | context_builder.py:795 |
| **阶段 2** | S4 账龄检测器 | P1 | 无 | 新建 aging.py + 注入 |
| **阶段 2** | S5 Pull 召回通道 | P1 | S2 实体提取复用 | 新建 recall_channel.py |
| **阶段 2** | S6 continuity 全量校验集 | P1 | 无 | continuity_checker.py |
| **阶段 3** | S7 自适应预算 | P2 | S1 后评估 | context_builder.py |
| **阶段 3** | S8 索引脊柱 | P2 | S5 | 新增索引视图 |
| **阶段 3** | F13/F14/F15 清理 | P2 | 各自依赖 | 小修 |

### 5.2 优先级判定原则

- **P0**：直接导致长篇记忆丢失（B2/B3），必须先做
- **P1**：提升召回率/准确性的核心机制（账龄、Pull、校验集）
- **P2**：优化体验与清理，后置

---

## 6. 预期目标与验收标准

### 6.1 量化目标

| 指标 | 当前（v6.10.13） | 目标（v6.10.14） | 验收方式 |
|------|------------------|------------------|----------|
| 长篇 numeric_state 丢失率 | 200 章下可能丢失 | 0%（mandatory 保护） | 单元测试：budget 紧张时 numeric_state 仍在 |
| story_facts bucket token 占用 | 全量（随章数膨胀） | 相关性子集（降 70%+） | 单元测试：200 条事实筛选后 ≤20 条 |
| 久挂事实检测覆盖 | 0% | 100%（超阈值即告警） | 单元测试：账龄边界 |
| continuity 校验覆盖范围 | `[from,to]` 内 | 全量 active facts | 单元测试：范围外事实可被校验 |
| pytest 基线 | 2616 passing | ≥2616 passing | `pytest -q` |

### 6.2 质量目标

- 召回逻辑零 LLM 依赖（S2/S4 纯代码派生）
- `AgentContextBuilder` 对外接口不变（仅内部实现）
- LangGraph 工作流节点结构不变
- 新增逻辑 100% 单元测试覆盖

### 6.3 回归目标

- 现有 2616 测试全部通过
- 新增测试文件命名沿用 `test_v61014_*.py`（承接 v6.10.x 测试命名惯例，如 v6.10.13 → `test_v61013_*`；`test_v611_*` 已被 v6.1.1 占用，不可复用）
- 不引入新 migration（S2/S4/S5/S6 均复用现有 story_facts/plot_holes 表）

---

## 7. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| S2 相关性筛选误剔必要事实 | 中 | High | numeric_state 全留 + 账龄兜底 + 无 brief 回退全量 |
| S1 mandatory 强塞致整体超预算 | 低 | Medium | overflow 告警日志，监控但不阻断 |
| S5 Pull 召回噪音 | 中 | Low | 硬上限 10 条 + token 预算隔离 |
| 改裁剪逻辑破坏现有测试 | 中 | Medium | 阶段 1 完成后立即跑全量 pytest |
| brief 未传入导致 S2 退化 | 中 | Medium | 回退全量 + F9 兜底 |

---

## 8. 版本迭代记录

| 版本 | 日期 | 变更 | 状态 |
|------|------|------|------|
| v6.10.13 | 2026-06-23 | 架构强化（FlowRouter/StopGuard/Reminder），借鉴 ainovel-cli | Released |
| **v6.10.14** | **2026-06-30** | **长篇数据召回优化（本文档）** | **Draft（待评审）** |

### 8.1 与 v6.10.13 的关系

v6.10.13 解决"流程决策确定性"（路由、停机、预算），v6.10.14 聚焦"数据召回确定性"——两者互补，共同构成长篇可靠性基础。v6.10.14 不依赖 v6.10.13 的新机制，可在 v6.10.13 基线上独立推进。

### 8.2 与 ainovel-cli 的对比定位

| 能力 | ainovel-cli | novelos v6.10.13 | novelos v6.10.14 目标 |
|------|-------------|-------------------|----------------------|
| 账龄回填 | ✅ 30 章 | ❌ | ✅ S4 |
| 相关性召回 | ✅ 四维度 | ❌ 全量 | ✅ S2 |
| mandatory 保护 | ✅ | ❌ break | ✅ S1 |
| Pull 通道 | ❌ | ❌ | ✅ S5（超越 ainovel-cli） |
| 全量校验集 | ❌ | ❌ | ✅ S6（超越 ainovel-cli） |

v6.10.14 的目标是：吸收 ainovel-cli 的账龄/相关性/mandatory 优势，同时用 Pull 通道和全量校验集形成超越。

---

## 9. 执行清单（待用户确认后启动）

> 以下为代码实现阶段任务，**本文档批准后**按顺序执行。

### 9.1 阶段 1（P0）
- [ ] S1: 改造 `format_context_bundle_for_prompt` 裁剪逻辑（mandatory + per-bucket）
- [ ] S3: break → continue 改造
- [ ] S2: `_story_facts_context` 加相关性筛选 + brief 传入链路
- [ ] 测试: `test_v61014_mandatory_bucket_protection.py`
- [ ] 测试: `test_v61014_story_facts_relevance_filter.py`
- [ ] 测试: `test_v61014_numeric_state_truncation_exempt.py`（F8）
- [ ] 回归: `pytest -q` 全量

### 9.2 阶段 2（P1）
- [ ] S4: 新建 `context/aging.py` + ContextBuilder 注入
- [ ] S5: 新建 `context/recall_channel.py` + author/planner 预判注入
- [ ] S6: `continuity_checker._build_context` 全量校验集
- [ ] 测试: `test_v61014_aging_detector.py` / `test_v61014_recall_channel.py` / `test_v61014_continuity_full_scope.py`
- [ ] 回归: `pytest -q` 全量

### 9.3 阶段 3（P2）
- [ ] S7: `_MAX_CONTEXT_CHARS` 自适应
- [ ] S8: 索引脊柱分片
- [ ] F13/F14/F15: 遗留代码清理 / 上限放宽 / docstring 对齐
- [ ] 测试 + 回归
- [ ] version.py bump → 6.10.14
- [ ] CHANGELOG.md 更新

### 9.4 文档与归档
- [ ] 本文档状态 Draft → Released（实施完成后）
- [ ] CHANGELOG.md 追加 v6.10.14 条目
- [ ] `docs/codex/reports/` 追加完成报告（实施后）

---

## 10. 附录：关键代码位置索引

| 关注点 | 文件 | 行号 |
|--------|------|------|
| 生产预算常量 | agent_runtime/context_builder.py | 28 (`_MAX_CONTEXT_CHARS = 14000`) |
| 裁剪主循环 | agent_runtime/context_builder.py | 1569-1590 (`format_context_bundle_for_prompt`) |
| bucket 排序 | agent_runtime/context_builder.py | 1525-1549 |
| story_facts 全量加载（3 处） | agent_runtime/context_builder.py | 242 / 396 / 774 |
| story_facts 去重 | agent_runtime/context_builder.py | 780-789 |
| value 截断 200 字符 | agent_runtime/context_builder.py | 795 |
| numeric_state 约束提取 | agent_runtime/context_builder.py | 384-431 |
| continuity 范围加载 | agents/continuity_checker.py | 160-221 |
| 遗留旧代码 | context/builder.py | 27 (`DEFAULT_TOKEN_BUDGET = 4000`) |
| 版本号 | novel_factory/version.py | `__version__ = "6.10.13"` |
