# Novel Factory v6.10.2 Skill Consolidation & Governance Plan

## 背景

v6.10.0 引入 Knowledge Skill 后，系统形成两层 Skill：

- **Code Skill**：Python 可执行能力，用于确定性检测、打分、阻断、返修路由、自动修复和结构化诊断。
- **Knowledge Skill**：Markdown 写作知识，用于提示词注入、LLM 工具调用、写作规范和修复建议。

当前问题不是“是否重复”，而是缺少清晰的工程边界：部分 Code Skill 与 Knowledge Skill 主题相同，但职责未显式绑定；部分 Skill 同时承担门禁、建议、写作指导，导致配置复杂、运行成本高、问题定位困难。

## v6.10.2 目标

1. 建立 Skill 分层标准：明确哪些必须是 Code，哪些应是 Knowledge，哪些采用混合模式。
2. 梳理所有现有 Skill：标记保留、整合、降级、禁用或移除候选。
3. 降低工作流不稳定性：减少重复检查、降低误阻断、让返修原因更可执行。
4. 为页面配置能力打基础：让 Code Skill 与 Knowledge Skill 都能被统一展示、编辑、启停和审计。

## 非目标

- 不把所有 Python Skill 迁移为 Knowledge Skill。
- 不删除仍承担生产门禁职责的 Code Skill。
- 不在本版本重做完整 Skill Marketplace 或外部插件系统。
- 不引入 LLM 判断替代确定性门禁。

## 分层规则

### 必须保留为 Code Skill

满足任一条件即保留为 Code Skill：

- 需要稳定 pass/fail、score、blocking issue。
- 影响返修路由、质量门禁、发布状态。
- 需要读取结构化状态、章节事实、上下文、历史章节或配置阈值。
- 需要可回归测试、可重放、可观测。
- 需要输出结构化诊断或自动修复建议。

### 应迁移为 Knowledge Skill

满足以下条件则优先迁移为 Knowledge Skill：

- 主要是写作方法、示例、风格建议。
- 没有明确硬阈值。
- 不应单独阻断工作流。
- 更适合在 Author/Polisher/Editor 提示词中作为指导材料。

### 混合模式

主题相同但职责不同的 Skill 应采用混合模式：

- Knowledge Skill 负责“如何写、如何修”。
- Code Skill 负责“是否达标、哪里失败、是否阻断”。
- Code Skill manifest 增加 `knowledge_skill_ids`，让诊断结果能引用对应修复指南。

## 当前 Skill 审计结论

### Code Skill

| Skill | 当前用途 | 结论 | v6.10.2 动作 |
| --- | --- | --- | --- |
| `chapter-objective-checker` | Planner 目标结构校验 | 保留 Code | 归入结构契约类，不转 Knowledge |
| `scene-conflict-checker` | Screenwriter beat 完整性 | 保留 Code | 归入结构契约类 |
| `event-coverage-checker` | Author 必需事件覆盖 | 保留 Code | 归入事实/任务契约类 |
| `memory-patch-validator` | Memory patch 结构校验 | 保留 Code | 归入结构契约类 |
| `word-count-gate` | 字数上下界 | 保留 Code | 只允许阈值配置化 |
| `fact-lock` | 润色事实保留 | 保留 Code | 提升为强门禁，避免 Polisher 改坏事实 |
| `continuity-gate` | 时间回退、跨章锚点、标题质量、事件重播 | 保留 Code | 与 `chapter-seam` 做边界拆分，降低重复阻断 |
| `chapter-seam` | 章节开头时间/地点/钩子衔接 | 保留 Code | 聚焦章间首段衔接，移除泛连续性职责 |
| `death-penalty` | AI 死刑词检测 | 保留 Code + Knowledge 绑定 | 检测保留；修复策略绑定 `ai-style-avoidance` |
| `ai-style-detector` | AI 味评分 | 保留 Code + Knowledge 绑定 | 与 `humanizer-zh`、`death-penalty` 明确边界 |
| `humanizer-zh` | 中文去 AI 味转换 | 保留 Code，但降为可选 Transform | 禁止无事实保护地改写正文 |
| `show-dont-tell` | 直白情绪/心理解释检测 | 混合 | 检测保留；技巧迁入 `show-dont-tell` Knowledge |
| `dialogue-naturalness` | 对白自然度检测 | 混合 | 检测保留；修复策略绑定 `dialogue-naturalness` Knowledge |
| `scene-texture` | 动作/环境/感官线索不足 | 混合/合并候选 | 与 `scene-sensory` Knowledge 绑定；弱化为 advisory |
| `info-dump-detector` | 设定灌输检测 | 保留 Code + Knowledge 绑定 | 绑定 `worldbuilding`，默认 advisory，严重才阻断 |
| `excitement-density-checker` | 爽点密度与压抑段落 | 混合 | 检测保留；绑定 `webnovel-excitement` |
| `opening-hook-checker` | 首章开局钩子 | 保留 Code | 仅第 1 章默认启用，非首章禁用 |
| `commercial-viability-check` | 商业可行性综合检查 | 整合候选 | 拆出硬指标，其余降为 Knowledge/advisory |
| `pacing-profile-check` | 节奏配置检查 | 混合 | 绑定 `pacing-rhythm`，避免与 `excitement-density-checker` 重复扣分 |
| `character-voice-check` | 角色口吻一致性 | 混合 | 绑定 `character-building`，低置信度不阻断 |
| `style-bible-checker` | Style Bible 合规 | 保留 Code | 绑定 `style-consistency`，仅项目有 style bible 时启用 |
| `foreshadowing-debt` | 伏笔债务检查 | 保留 Code | 绑定 `foreshadowing-management`，区分提醒与阻断 |
| `mystery-integrity-check` | 悬疑完整性 | 保留但默认关闭 | 仅 genre 命中悬疑/推理/惊悚时启用 |
| `narrative-quality` | 综合叙事质量评分 | 整合候选 | 不再作为硬门禁；作为聚合分或 QualityHub 输出 |

### Knowledge Skill

| Skill | 当前定位 | 结论 | v6.10.2 动作 |
| --- | --- | --- | --- |
| `webnovel-excitement` | 爽文节奏、钩子、付费点 | 保留 | 绑定爽点、商业、开局钩子类 Code Skill |
| `character-building` | 角色塑造、口吻、成长弧 | 保留 | 绑定 `character-voice-check` |
| `dialogue-naturalness` | 对白写作规范 | 保留 | 绑定 `dialogue-naturalness` Code Skill |
| `pacing-rhythm` | 叙事节奏规范 | 保留 | 绑定 `pacing-profile-check` |
| `ai-style-avoidance` | AI 痕迹规避 | 保留 | 绑定 `ai-style-detector`、`death-penalty`、`humanizer-zh` |
| `show-dont-tell` | 展示而非讲述技巧 | 保留 | 绑定 `show-dont-tell` Code Skill |
| `scene-sensory` | 五感与场景描写 | 保留/整合候选 | 与 `scene-texture` 形成一对一混合模式 |
| `foreshadowing-management` | 伏笔埋设与回收 | 保留 | 绑定 `foreshadowing-debt` |
| `worldbuilding` | 世界观展示 | 保留 | 绑定 `info-dump-detector`，避免设定灌输 |
| `style-consistency` | 风格一致性 | 保留 | 绑定 `style-bible-checker` |
| `genre-suspense` | 悬疑类型规范 | 保留但按题材启用 | 绑定 `mystery-integrity-check` |

## 需要整合的重复区

### AI 味治理

现状：

- `ai-style-detector` 检测 AI 味。
- `death-penalty` 检测死刑词。
- `humanizer-zh` 执行改写。
- `ai-style-avoidance` 提供知识。

v6.10.2 方案：

- 保留三个 Code Skill，但重新定义顺序：`death-penalty` 精准红线，`ai-style-detector` 综合评分，`humanizer-zh` 仅作为可控 transform。
- `humanizer-zh` 默认不直接扩大正文，只修复命中的局部片段。
- 三者统一引用 `ai-style-avoidance` 作为修复知识源。

### 章间连续性治理

现状：

- `continuity-gate` 与 `chapter-seam` 都可能报章间衔接问题。

v6.10.2 方案：

- `chapter-seam` 只检查本章开头是否承接上一章末尾的时间、地点、钩子。
- `continuity-gate` 检查章内时间回退、事件重播、标题脱节、关键状态丢失。
- 两者合并诊断展示，避免同一问题重复计为多个 blocking issue。

### 网文质量治理

现状：

- `opening-hook-checker`、`excitement-density-checker`、`commercial-viability-check`、`narrative-quality` 存在指标重叠。

v6.10.2 方案：

- `opening-hook-checker` 仅服务第 1 章。
- `excitement-density-checker` 负责章节内爽点分布。
- `commercial-viability-check` 拆成 advisory，不直接阻断。
- `narrative-quality` 作为聚合分，不再单独制造返修目标。

### 文字表现治理

现状：

- `show-dont-tell`、`scene-texture`、`dialogue-naturalness`、`info-dump-detector` 会同时给出风格类建议。

v6.10.2 方案：

- 默认作为 advisory。
- 只有达到高置信度或连续多章失败时升级为 blocking。
- 每个诊断必须给出可执行局部修复建议，不允许只输出泛泛评价。

## 删除/禁用候选

第一阶段不物理删除代码，先禁用或降级，避免破坏历史项目：

| 候选 | 处理方式 | 原因 |
| --- | --- | --- |
| `narrative-quality` 硬门禁 | 降级为聚合评分 | 综合分不可解释，容易与专项 Skill 重复 |
| `commercial-viability-check` 硬门禁 | 降级为 advisory | 商业性判断主观，适合建议而非阻断 |
| 非首章 `opening-hook-checker` | 运行时跳过 | 已有 positional rule，应配置显式化 |
| 非悬疑项目 `mystery-integrity-check` | 保持禁用 | 已有 genre rule，应在 UI 中解释 |
| 低置信度 `scene-texture` 阻断 | 降级 advisory | 画面感不足不应频繁阻断生产 |

物理删除条件：

- 连续两个小版本无运行引用。
- 无测试覆盖依赖。
- 无历史任务恢复依赖。
- 已有替代 Skill 覆盖同等诊断能力。

## 配置模型调整

### Code Skill Manifest 增补字段

建议新增：

```yaml
layer: code
category: continuity | facts | structure | prose | commercial | style | transform
severity_default: blocking | advisory | disabled
knowledge_skill_ids:
  - ai-style-avoidance
dedupe_group: ai_style | continuity | webnovel_quality | prose_quality
runtime_scope:
  agents:
    - author
    - polisher
    - editor
  chapters: all | first_only | genre_only
```

### Knowledge Skill Metadata 增补字段

建议新增：

```yaml
layer: knowledge
category: prose | genre | character | pacing | style
paired_code_skill_ids:
  - dialogue-naturalness
default_agents:
  - author
  - polisher
  - editor
editable: true
token_budget: 1200
```

## 页面能力规划

v6.10.2 至少支持只读治理视图，编辑能力可分阶段上线：

1. Skill 总览：Code/Knowledge 分层、启用状态、运行 agent、严重级别。
2. 绑定关系：显示 Code Skill 对应的 Knowledge Skill。
3. 项目覆盖：项目级启停、阈值、token budget。
4. 安全编辑：Knowledge Skill 内容可编辑，Code Skill 仅允许配置项编辑，不允许页面改 Python。
5. 审计记录：记录谁修改了 Skill 配置、修改前后 diff、影响范围。

## 实施步骤

### Phase 1：治理元数据

- 给所有 Code Skill manifest 增加 layer/category/severity/dedupe_group/knowledge_skill_ids。
- 给 Knowledge Skill meta 增加 paired_code_skill_ids/default_agents/editable/token_budget。
- 增加元数据一致性测试：不存在孤儿绑定、重复 dedupe group 必须可解释。

### Phase 2：运行时去重

- Editor 聚合诊断时按 dedupe_group 合并重复 blocking issue。
- `chapter-seam` 与 `continuity-gate` 输出统一 continuity 类问题。
- prose 类低置信度问题默认 advisory。

### Phase 3：门禁降噪

- `narrative-quality` 改为聚合评分，不直接阻断。
- `commercial-viability-check` 默认 advisory。
- `scene-texture` 默认 advisory，高置信度才阻断。
- `opening-hook-checker` 显式 first_only。

### Phase 4：Knowledge 绑定注入

- 当 Code Skill 失败时，返修 prompt 自动注入绑定的 Knowledge Skill 摘要。
- 审核报告展示“失败规则 + 修复知识源 + 局部建议”。
- Author/Polisher 返修时优先加载相关 Knowledge，而不是加载全量知识。

### Phase 5：配置页面基础

- 新增 Skill governance API：列出 Skill、绑定关系、项目覆盖配置。
- 前端新增 Skill 治理视图。
- Knowledge Skill 支持页面编辑草稿、保存、回滚。

## 验收标准

- 所有 Skill 都有明确 layer/category/severity。
- 所有混合 Skill 都有双向绑定：Code manifest ↔ Knowledge meta。
- Editor 同一根因不再生成多个 blocking issue。
- 普通章节生产中，prose 类问题不会单独导致最大返修耗尽。
- Author/Polisher 返修 prompt 能按失败 Skill 精准注入对应 Knowledge。
- `python3 -m pytest -q` 通过。
- 前端 typecheck/build/lint 通过。

## 风险与控制

| 风险 | 控制 |
| --- | --- |
| 误删 Skill 破坏旧项目恢复 | 先禁用/降级，不直接物理删除 |
| Knowledge 替代 Code 导致质量门禁失效 | 硬门禁只保留在 Code Skill |
| Skill 数量仍然多 | 通过 dedupe_group 和 UI 分类降低认知负担 |
| 返修 prompt 过长 | 只注入失败 Skill 绑定知识摘要 |
| 主观质量指标阻断生产 | 主观类默认 advisory，连续失败再升级 |

## 建议版本边界

v6.10.2 应优先交付：

1. Skill 元数据标准。
2. Code/Knowledge 双向绑定。
3. Editor 诊断去重。
4. 主观类 Skill 降级。
5. 返修时精准注入 Knowledge。

Knowledge Skill 页面编辑可作为 v6.10.2 后半段或 v6.10.3，如果工作流稳定性仍未达标，应优先让生产链路稳定。
