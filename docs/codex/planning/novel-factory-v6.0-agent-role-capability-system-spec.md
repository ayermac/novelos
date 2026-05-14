# Novelos v6.0 Agent Role Capability System 规格

## 状态

- 类型：完整能力闭环规格
- 状态：planned
- 基线：v5.9.3 Agent Skill Expansion
- 产品目标：把 Novelos 从“按阶段调用 LLM 的流水线”升级为“有角色目标、工具、记忆、自检、协作和评测的 AI 创作团队”
- 技术目标：建立 Agent Role Profile、Capability Pack、Agent Memory、Self-check Loop、Collaboration Contract、Evaluation Harness、AgentOps UI 的统一体系
- 版本性质：大版本，不再按小功能拆分；实现后应形成可用、好用、可维护、可验收的完整 Agent 角色能力系统

## 背景

v5.9.3 已经解决了一个关键断层：Skill 不再只服务 Polisher/Editor，而是接入了 Planner、Screenwriter、Author、MemoryCurator 等核心 Agent。

但当前系统仍然存在更深的问题：

```text
Agent 有角色名，但角色专业能力还不够厚。
```

当前 Agent 更像阶段函数：

```text
构造上下文 -> 调 LLM -> schema 校验 -> 保存结果
```

真正生产级的创作 Agent 应该是：

```text
明确角色目标 -> 读取角色记忆和项目策略 -> 使用专属工具/Skill -> 生成 -> 自检 -> 局部修复 -> 协作反馈 -> 记录决策 -> 进入评测
```

因此，v6.0 不再规划为“再加几个 Skill”或“再补一个 Prompt 系统”，而是一次性完成 Agent 角色能力系统。

补充判断：Novelos 当前确实更接近 Workflow 系统，而不是真正的 Agent 系统。v6.0 的目标不是抛弃 Workflow，而是在稳定专业流程上增加 **bounded autonomy**：

```text
Workflow 负责专业生产边界和状态安全；
Agent 负责感知、规划、决策、工具调用、反思和局部修复；
Human-in-the-loop 负责最终控制和高风险决策。
```

## 设计原则

1. **按完整能力闭环规划，不按小功能碎片迭代。**
2. Agent 是角色，不是函数；Skill 是工具箱，不是孤立插件。
3. 每个 Agent 必须有目标函数、失败标准、可用工具、可观测决策和评测集。
4. 默认能力应可用于真实创作流程，不只通过单元测试。
5. 所有新增 LLM 调用必须有成本预算、降级策略和可观测记录。
6. 人工创作者拥有最终控制权；Agent 自主性必须可解释、可撤销。
7. 不追求企业多租户；优先服务个人创作者的长篇生产稳定性和质量。
8. 自主性必须有边界。Agent 可以建议、局部修复、请求补充资料、拒绝不合理任务，但不能绕过状态机、发布门禁和人工确认。

## 非目标

- 不做多租户、企业权限、组织管理。
- 不做外部 Skill 市场。
- 不引入复杂微服务架构。
- 不要求所有 Agent 一次性达到“完美写手”水平，但必须形成可持续增强的角色能力底座。
- 不把 Agent 主流程全部拆成 Skill；Agent 仍负责阶段性主决策。
- 不把 UI 做成运维后台；AgentOps UI 必须服务作者理解和改进创作流程。

## 当前差距

### 1. Agent 目标函数不足

当前 Agent 有 prompt 职责，但没有工程化目标函数。

示例：

- Planner 应优化主线推进、节奏、伏笔债务、章节目标清晰度。
- Screenwriter 应优化场景功能、冲突强度、转折密度、情绪曲线。
- Author 应优化事件落地、人物口吻、动作化叙事、爽点密度、章末牵引。
- Editor 应优化商业读感、弃读点、逻辑风险、返修可执行性。
- MemoryCurator 应优化长期事实一致性、记忆去重、设定冲突预警。

### 2. Agent 工具箱不足

v5.9.3 有最小 Skill，但还不是完整工具箱。

缺少：

- 角色专属工具；
- 项目类型差异化规则；
- 局部修复工具；
- 角色间协作工具；
- 评测工具。

### 3. Agent 没有长期角色记忆

当前上下文主要来自项目资料和章节状态。Agent 自身没有长期记忆：

- 过去常犯的问题；
- 本项目的偏好；
- 用户对该 Agent 的反馈；
- 其他 Agent 对它的质量评价；
- 它自己的策略版本变化。

### 4. 缺少自检和局部修复循环

当前多数节点是一次生成。失败后通常回到大节点重跑。

应支持：

- 生成后自检；
- 只修复缺失事件；
- 只重写一个 scene beat；
- 只补一段人物口吻；
- 只重抽一类记忆；
- 复查上次失败项。

### 5. Agent 间协作协议不足

当前是流水线传递，不是真协作。

应定义：

- Planner 给 Screenwriter 的交付标准；
- Screenwriter 给 Author 的可执行标准；
- Author 对 Planner/Screenwriter 的反馈通道；
- Editor 的问题归因和返修目标；
- MemoryCurator 对 Planner 的设定变化提醒。

### 6. Agent 可观测性不足

v5.8 已有 workflow timeline，但 Agent 内部决策仍不够透明。

应记录：

- 关键输入摘要；
- 使用了哪些 Skill/工具；
- 触发了哪些自检；
- 发现了什么问题；
- 为什么继续/阻塞/返修；
- 成本、耗时、token；
- 生成物和修复链路。

### 7. Agent 评测体系不足

功能测试不能证明 Agent 真的变强。需要 eval：

- Planner eval；
- Screenwriter eval；
- Author eval；
- Editor eval；
- MemoryCurator eval；
- 端到端创作流程 eval。

### 8. Agent 自主性不足

当前状态转换是硬编码的：

```text
planned -> scripted -> drafted -> polished -> review
```

这保证了稳定性，但 Agent 缺少自主判断能力：

- 不能拒绝不合理任务；
- 不能在中间结果不够好时调整策略；
- 不能主动请求补充世界观/角色信息；
- 不能提出“需要回到 Planner/Screenwriter”的理由；
- 不能把异常情况升级为具体的人类决策问题。

v6.0 需要补的是 **有边界的自主决策**，不是完全自由的 Agent Loop。

### 9. 工具系统不足

当前工具主要是：

```text
Repository read/write
LLMProvider
SkillRegistry
```

对于创作 Agent 来说还不够。需要一个受控工具层：

- 项目资料查询工具；
- 章节/版本/diff 工具；
- 伏笔债务查询工具；
- Agent Memory 工具；
- Genre Strategy 查询工具；
- Web/reference search 工具；
- 文件导入工具；
- 局部改写工具；
- Eval 执行工具。

外部工具如搜索、文件、bash/API 必须显式授权、审计和限制，不能默认给 Agent 无限环境权限。

## 完整能力目标

v6.0 完成后，系统应具备：

```text
Agent Role Profile
Agent Capability Pack
Agent Memory
Bounded Autonomy Policy
Agent Tool Runtime
Self-check and Local Repair Loop
Agent Collaboration Contract
Agent Decision Trace
Agent Evaluation Harness
AgentOps Role Console
```

这些能力必须在真实章节生成流程中闭环，而不是只存在于配置或文档。

## 核心交付

### 1. Agent Role Profile

新增角色定义层：

```text
novel_factory/agents/roles/
```

建议文件：

```text
planner.yaml
screenwriter.yaml
author.yaml
polisher.yaml
editor.yaml
memory_curator.yaml
publisher.yaml
```

每个 Role Profile 必须包含：

```yaml
agent_id:
display_name:
mission:
success_criteria:
failure_criteria:
primary_inputs:
primary_outputs:
owned_artifacts:
decision_authority:
cannot_do:
collaboration_contracts:
default_capability_packs:
eval_dimensions:
cost_budget:
trace_policy:
```

最低角色目标：

| Agent | Mission |
| --- | --- |
| planner | 将长篇目标、当前状态、伏笔债务转化为可执行章节指令 |
| screenwriter | 将章节指令转化为有目标、冲突、转折和钩子的场景计划 |
| author | 将场景计划写成符合项目风格、事件覆盖完整、可读的正文 |
| polisher | 在不破坏事实和事件的前提下提升表达质量和风格自然度 |
| editor | 以责编视角发现逻辑、节奏、商业读感和文本质量问题，并生成可执行返修单 |
| memory_curator | 从已审章节抽取、去重、校验和排队记忆更新 |
| publisher | 在状态和人工确认满足条件后发布并锁定版本 |

### 2. Agent Capability Pack

Skill 需要升级为能力包，不是散落函数。

目录规范：

```text
novel_factory/skill_packages/<capability_id>/
  manifest.yaml
  handler.py
  README.md
  rules/
  prompts/
  tests/fixtures.yaml
  eval/
```

本版本必须把 v5.9.3 新增的内置 Skill package 化：

```text
chapter_objective_checker
scene_conflict_checker
event_coverage_checker
memory_patch_validator
```

并补齐更多角色能力包。

#### Planner Capability Pack

必须包含：

- `chapter_objective_checker`
- `foreshadowing_debt_planner`
- `pacing_plan_checker`
- `arc_continuity_checker`

能力要求：

1. 检查章节目标是否具体。
2. 检查伏笔是否合理埋设/兑现。
3. 检查本章目标是否过载或过空。
4. 检查与当前弧线、大纲、上一章状态是否矛盾。

#### Screenwriter Capability Pack

必须包含：

- `scene_conflict_checker`
- `scene_function_classifier`
- `hook_strength_checker`
- `emotion_curve_checker`

能力要求：

1. 每个 scene beat 必须有目标、冲突、转折、钩子。
2. 每场必须有功能分类：推进主线/揭示信息/人物关系/战斗爽点/过渡。
3. 检查章内情绪曲线是否单调。
4. 检查章末钩子是否足够牵引。

#### Author Capability Pack

必须包含：

- `event_coverage_checker`
- `character_voice_checker`
- `show_dont_tell_checker`
- `webnovel_payoff_checker`
- `local_rewrite_tool`

能力要求：

1. 检查正文覆盖 required_events。
2. 检查人物口吻是否与角色卡一致。
3. 检查是否大量抽象概述。
4. 检查爽点/冲突升级/章末牵引。
5. 支持局部修复，不默认整章重跑。

#### Polisher Capability Pack

必须包含：

- `humanizer_zh`
- `ai_style_detector`
- `rhythm_polisher`
- `style_bible_checker`
- `fact_lock_guard`

能力要求：

1. 润色不能改变事实。
2. 去 AI 味不能破坏角色口吻。
3. 润色结果必须通过事实锁。
4. 风格检查必须引用项目 Style Bible。

#### Editor Capability Pack

必须包含：

- `narrative_quality`
- `commercial_readability_checker`
- `dropoff_risk_checker`
- `logic_consistency_checker`
- `revision_brief_generator`

能力要求：

1. 不只打分，要生成可执行返修单。
2. 问题必须归因到 Planner/Screenwriter/Author/Polisher/Memory。
3. 区分阻塞问题和建议问题。
4. 对局部修复给出目标段落/场景。

#### MemoryCurator Capability Pack

必须包含：

- `memory_patch_validator`
- `fact_dedup_checker`
- `fact_conflict_checker`
- `plot_status_transition_checker`
- `memory_importance_ranker`

能力要求：

1. patch 结构必须合法。
2. 避免重复事实。
3. 发现设定冲突。
4. 校验伏笔状态合法跳转。
5. 为记忆更新打重要性和人工审核优先级。

### 3. Agent Memory

新增 Agent 角色记忆，不等同于小说世界观记忆。

建议数据库表：

```text
agent_memories
agent_memory_events
agent_feedback
```

最小字段：

```text
id
project_id
agent_id
memory_type
key
value_json
confidence
source_run_id
source_chapter_number
created_at
updated_at
```

记忆类型：

| memory_type | 示例 |
| --- | --- |
| project_preference | 本项目偏好强章末钩子 |
| recurring_issue | Author 经常遗漏事件覆盖 |
| user_feedback | 用户认为 Polisher 太书面化 |
| agent_feedback | Editor 指出 Screenwriter 冲突不足 |
| strategy_note | Planner 应优先回收 P003 伏笔 |

要求：

1. Agent Memory 必须可查看、可禁用、可清理。
2. 不能自动污染世界观资料。
3. Agent Memory 注入 prompt 时必须可解释。
4. 每条记忆必须有来源和置信度。

### 4. Bounded Autonomy Policy

新增自主性策略层：

```text
novel_factory/agents/autonomy.py
novel_factory/config/agent_autonomy.yaml
```

策略目标：让 Agent 能自主判断下一步，但不破坏工作流安全边界。

Agent 可做的自主决策：

| Decision | 示例 |
| --- | --- |
| continue | 当前输出通过自检，继续下一阶段 |
| local_repair | 当前问题局部可修，先修复再保存 |
| request_context | 缺少角色/世界观/大纲，向用户或资料库请求补充 |
| reroute | 问题属于上游，建议返回 Planner/Screenwriter |
| refuse | 任务违反约束、事实锁或发布门禁，拒绝执行 |
| ask_human | 不确定性高，进入人工确认 |

每个决策必须包含：

```json
{
  "decision": "local_repair",
  "reason": "正文遗漏 required_events 中的夺回账册",
  "confidence": 0.82,
  "risk": "low",
  "allowed_by_policy": true,
  "next_action": "repair_author_event_coverage"
}
```

硬约束：

1. Agent 不能绕过 `reviewed -> awaiting_publish/published` 发布门禁。
2. Agent 不能在未授权情况下调用外部网络、文件、bash。
3. Agent 不能自行删除项目、章节或版本。
4. Agent 不能无限循环 repair；默认最多一次。
5. 高风险决策必须 Human-in-the-loop。

### 5. Agent Tool Runtime

新增受控工具运行时：

```text
novel_factory/tools/
  base.py
  registry.py
  project_tools.py
  chapter_tools.py
  memory_tools.py
  search_tools.py
  file_tools.py
  eval_tools.py
```

工具类型：

| Tool | 默认权限 | 用途 |
| --- | --- | --- |
| `project_context.query` | allow | 查询角色、世界观、伏笔、事实 |
| `chapter.version_diff` | allow | 对比版本和局部变化 |
| `foreshadowing.debt_report` | allow | 生成伏笔债务报告 |
| `agent_memory.query/write` | allow with trace | 查询/写入 Agent 记忆 |
| `local_rewrite.apply` | allow with versioning | 局部修复正文 |
| `web_search.query` | opt-in | 查外部资料 |
| `file.import_reference` | opt-in | 导入本地资料 |
| `http.request` | deny by default | 外部 API |
| `bash.run` | deny by default | shell 命令，只允许开发/诊断场景 |

每个工具必须有：

```yaml
tool_id:
description:
input_schema:
output_schema:
permissions:
allowed_agents:
audit_policy:
cost_policy:
failure_policy:
```

工具调用必须写入 Agent Decision Trace。

### 6. Self-check and Local Repair Loop

每个创作 Agent 必须支持：

```text
generate -> self_check -> local_repair -> final_check -> save
```

最低要求：

| Agent | Self-check | Local Repair |
| --- | --- | --- |
| planner | objective /伏笔/节奏检查 | 补目标、补约束、调整伏笔 |
| screenwriter | scene beat 完整性检查 | 重写单个 scene beat |
| author | 事件覆盖、口吻、字数、钩子检查 | 补事件、重写段落、扩写/压缩 |
| polisher | 事实锁、风格、AI 味检查 | 局部润色，不改事实 |
| editor | 问题归因、返修目标检查 | 生成更具体返修单 |
| memory_curator | patch 合法性和冲突检查 | 丢弃低置信 patch、拆分 patch |

约束：

1. 最多一次自动 local repair，避免无限循环。
2. 所有 repair 必须记录 before/after。
3. repair 失败不能静默吞掉。
4. 真实 LLM 模式下 repair 必须纳入 token 预算。

### 7. Agent Collaboration Contract

新增协作契约：

```text
novel_factory/agents/contracts/
```

每个 contract 定义：

```yaml
from_agent:
to_agent:
handoff_artifact:
required_fields:
quality_bar:
feedback_channel:
failure_escalation:
```

必须覆盖：

| Contract | 目标 |
| --- | --- |
| planner -> screenwriter | 章节指令必须能拆成场景 |
| screenwriter -> author | scene beats 必须可写正文 |
| author -> polisher | 正文必须结构完整且事件覆盖 |
| polisher -> editor | 润色不能改变事实 |
| editor -> planner/screenwriter/author/polisher | 返修单必须明确归因 |
| memory_curator -> planner | 记忆变化影响后续规划时提醒 Planner |

### 8. Agent Decision Trace

扩展 v5.8 timeline，新增 Agent 内部决策记录。

建议数据结构：

```text
agent_decision_traces
```

字段：

```text
id
run_id
project_id
chapter_number
agent_id
stage
decision_type
input_summary
tool_results_json
skill_results_json
self_check_json
repair_actions_json
decision
reason
token_count
latency_ms
created_at
```

UI 中应展示：

1. Agent 本次看到了什么关键上下文。
2. 使用了哪些 Capability Pack。
3. 发现了哪些问题。
4. 是否做了局部修复。
5. 为什么进入下一阶段或阻塞。

### 9. Agent Evaluation Harness

新增评测目录：

```text
evals/agents/
  planner/
  screenwriter/
  author/
  polisher/
  editor/
  memory_curator/
  e2e/
```

每个 eval case 包含：

```yaml
id:
agent_id:
input_fixture:
expected_behavior:
rubric:
must_pass:
should_warn:
regression_tags:
```

最低评测项：

| Agent | Eval |
| --- | --- |
| planner | 目标具体性、伏笔债务处理、节奏不过载 |
| screenwriter | scene beat 完整性、冲突/转折/钩子 |
| author | 事件覆盖、人物口吻、动作化叙事、章末钩子 |
| polisher | 不改事实、去 AI 味、风格一致 |
| editor | 能发现已知缺陷、能生成可执行返修单 |
| memory_curator | 抽取准确率、去重、冲突检测 |
| e2e | 一章生成后所有角色 trace 和 skill_runs 完整 |

新增命令：

```bash
python3 scripts/eval_agents.py planner
python3 scripts/eval_agents.py all
```

### 10. Project Genre Strategy

Agent 能力必须受项目类型策略影响。

新增：

```text
novel_factory/config/genre_strategies/
```

最小策略：

```text
urban_xianxia.yaml
mystery.yaml
romance.yaml
fantasy.yaml
general.yaml
```

策略字段：

```yaml
genre:
reader_promise:
pacing_profile:
chapter_hook_style:
must_have_tropes:
avoid_patterns:
editor_rubric_weights:
planner_bias:
author_style_bias:
```

要求：

1. 项目创建后应能选择或调整策略。
2. Agent Role Profile 加载项目策略。
3. Editor 评分权重受 genre strategy 影响。
4. Strategy 注入必须在 trace 中可见。

### 11. AgentOps Role Console

WebUI 新增或增强 Agent 能力视图，不做运维化堆表。

入口建议：

```text
Settings -> Agent 能力
Project -> AgentOps / 能力诊断
```

必须展示：

1. 每个 Agent 的角色目标。
2. 已启用 Capability Packs。
3. 最近运行质量趋势。
4. 最近常见失败原因。
5. Agent Memory 摘要。
6. 当前项目 genre strategy。
7. 最近一次章节生成的 Agent Decision Trace。
8. Eval 通过情况。

交互要求：

1. 创作者能看懂，不显示大量内部 raw JSON。
2. 技术细节可展开。
3. 支持“为什么这章失败/为什么返修”的解释链。
4. 支持按 Agent 过滤。

### 12. Pi / External Agent Loop Integration

Pi 这类 Agent Loop 可以强化 Novelos，但不建议完全迁移或替换主系统。

推荐采用混合模式：

```text
Pi / External Agent Supervisor
        |
        | HTTP/RPC tools
        v
Novelos Professional Agent APIs
        |
        v
Workflow + Repository + Skill/Capability + Trace
```

定位：

- Novelos 负责专业小说生产、状态安全、版本、记忆、评测。
- Pi 负责对话式上层编排、外部工具扩展、探索性任务和开发/诊断自动化。

不推荐：

1. 不推荐把 Novelos LLMProvider 简单替换为 Pi；这样拿不到 Agent Loop 价值。
2. 不推荐完全迁移到 Pi；成本高且会丢掉 Novelos 已有的专业领域模型。
3. 不推荐让 Pi 直接改数据库；必须通过 Novelos API/工具。

建议新增：

```text
novel_factory/api/routes/agent_tools.py
integrations/pi/
  README.md
  tools.ts
  extension.ts
```

暴露给 Pi 的工具：

| Tool | 能力 |
| --- | --- |
| `novelos_get_project_status` | 查看项目/章节/运行状态 |
| `novelos_plan_chapter` | 调用 Planner 生成/修复章节计划 |
| `novelos_design_scenes` | 调用 Screenwriter 生成/修复场景 |
| `novelos_write_chapter` | 调用 Author 生成/局部修复正文 |
| `novelos_review_chapter` | 调用 Editor 审核 |
| `novelos_query_memory` | 查询事实/角色/伏笔/Agent Memory |
| `novelos_get_trace` | 获取 Agent 决策链 |

Pi 集成验收：

1. Pi 可以通过工具读取项目状态。
2. Pi 可以发起一个受控章节生产建议，但不能绕过 Novelos 工作流。
3. Pi 的每次调用在 Novelos 中有 audit trace。
4. Pi 无权直接发布、删除、覆盖版本。
5. Pi 集成是可选功能，Novelos 本身不依赖 Pi 才能运行。

### 13. Migration and Backward Compatibility

本版本会引入新表和新配置，但必须兼容旧项目：

1. 没有 Agent Memory 的项目正常运行。
2. 没有 Genre Strategy 的项目使用 `general`。
3. 老 Skill 继续运行。
4. v5.9.3 的 4 个内置 Skill 迁移为 package 后，旧配置仍能解析。
5. Project-specific skill overrides 不丢失。
6. 旧 workflow timeline 不破坏。

## 技术架构建议

```text
novel_factory/
  agents/
    roles/
    contracts/
    autonomy.py
    capability_runtime.py
    self_check.py
    decision_trace.py
  tools/
    registry.py
    project_tools.py
    chapter_tools.py
    memory_tools.py
    search_tools.py
    eval_tools.py
  skill_packages/
    chapter_objective_checker/
    scene_conflict_checker/
    event_coverage_checker/
    memory_patch_validator/
    ...
  evals/
    agents/
  config/
    genre_strategies/
  api/routes/
    agent_ops.py
    agent_memory.py
    agent_tools.py
  integrations/
    pi/
```

## 实施阶段

虽然是一个完整版本，但实施可以分阶段提交。阶段只是执行顺序，不是拆成多个产品版本。

### Phase 1: Role Profile and Capability Package Foundation

1. 新增 Agent Role Profile 加载器。
2. 新增 Capability Pack 规范。
3. 将 v5.9.3 的 4 个内置 Skill 迁移为 package。
4. 确保 Skill Console 不再让用户困惑“为什么有的 Skill 不在 packages 里”。

### Phase 2: Role-specific Capability Packs

1. 补齐 Planner、Screenwriter、Author、Polisher、Editor、MemoryCurator 的默认能力包。
2. 所有新增能力默认 rule-based；需要 LLM 的默认关闭或成本受控。
3. 所有能力有 manifest、fixtures、README、tests。

### Phase 3: Agent Memory and Genre Strategy

1. 新增 Agent Memory 表、repository、API。
2. 新增 Genre Strategy 配置。
3. 在 Agent prompt/context 中注入可解释的角色记忆和类型策略。
4. UI 可查看和清理 Agent Memory。

### Phase 4: Bounded Autonomy and Tool Runtime

1. 新增 Agent autonomy policy。
2. 新增受控工具 registry。
3. 为核心 Agent 接入项目资料、章节版本、记忆、伏笔债务等内部工具。
4. 外部搜索/文件/http/bash 默认关闭，必须配置授权。

### Phase 5: Self-check and Local Repair

1. 为核心 Agent 接入 self_check。
2. 为 Author/Screenwriter/MemoryCurator 优先实现局部修复。
3. 记录 repair trace。
4. 限制 repair 次数和成本。

### Phase 6: Collaboration Contract and Revision Routing

1. 定义 handoff artifact 质量标准。
2. Editor 返修单必须归因到具体 Agent。
3. MemoryCurator 对 Planner 产生设定变化提醒。
4. 局部返修优先于整章重跑。

### Phase 7: Decision Trace and AgentOps UI

1. 扩展 trace 持久化。
2. WebUI 展示 Agent role、capability、memory、trace。
3. 工作流页面能解释每个 Agent 做了什么、为什么这么做。

### Phase 8: Pi Integration and External Supervisor Bridge

1. 定义 Novelos Agent Tool API。
2. 提供 Pi extension/tool 示例。
3. 确保外部 Agent 只能通过受控 API 调用。
4. 记录 audit trace。

### Phase 9: Evaluation Harness and Real Project Acceptance

1. 建立 eval fixtures。
2. 增加 `scripts/eval_agents.py`。
3. 对真实 LLM 新项目跑人工创作流程验收。
4. 输出 completion report 和 review。

## 验收标准

### 角色能力验收

1. 每个核心 Agent 有 Role Profile。
2. 每个核心 Agent 至少有 3 个默认 Capability Pack。
3. 每个核心 Agent 有 success/failure criteria。
4. 每个核心 Agent 有 eval dimensions。

### Skill/Capability 验收

1. 所有默认能力都是 package 形态。
2. 每个 package 有 manifest、handler、README、fixtures。
3. Skill Console 显示 package 来源、版本、目标 Agent/Stage。
4. 不再出现“新增内置 Skill 不在 skill_packages 里”的组织混乱。

### 运行时验收

1. 真实 LangGraph runner 中每个核心 Agent 会加载 role profile。
2. 每个核心 Agent 会执行默认 capability packs。
3. Agent Memory 和 Genre Strategy 注入 trace 可见。
4. Self-check 和 local repair 有记录。
5. Editor 返修单可归因到具体 Agent。
6. Agent 能输出 bounded autonomy decision，并受 policy 约束。
7. 工具调用写入 trace，外部工具默认不可用。

### AgentOps UI 验收

1. 用户能看到每个 Agent 的角色目标和启用能力。
2. 用户能看到最近一次运行的 Agent 决策链。
3. 用户能看到 Agent Memory 摘要和来源。
4. 用户能看懂失败原因，不需要读 raw JSON。
5. 用户可以禁用/清理某条 Agent Memory。

### Eval 验收

1. `scripts/eval_agents.py all` 可运行。
2. 每个核心 Agent 至少 5 个 eval case。
3. E2E eval 覆盖一章完整生成。
4. 真实项目验收覆盖至少 1 个新小说项目、真实 LLM、人工创作流程。

### Pi 集成验收

1. `integrations/pi/` 提供可运行的工具定义或明确的接入说明。
2. Pi 可以读取项目状态和 trace。
3. Pi 可以建议/触发受控生产动作。
4. Pi 不能直接发布、删除、覆盖版本。
5. Novelos 在不安装 Pi 的情况下仍能完整运行。

### 回归验收

必须通过：

```bash
python3 scripts/verify.py smoke
python3 -m pytest tests/test_skill_config.py tests/test_skills.py tests/test_skills_api.py tests/test_agents.py -q
python3 -m pytest tests/test_v516_langgraph_activation.py tests/test_v58_workflow_observability.py -q
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm run build
cd frontend && npm run test -- --run
```

新增：

```bash
python3 scripts/eval_agents.py all
```

## 真实项目验收

不能只用 stub mode。

验收方式：

1. 创建一个全新小说项目，不使用历史项目。
2. 使用线上真实 LLM。
3. 模拟人工创作流程：
   - 创建项目；
   - 设定 genre strategy；
   - 生成第 1 章；
   - 查看 Agent trace；
   - 人工编辑；
   - 触发局部修复；
   - 审核；
   - 应用/拒绝 Memory patch；
   - 继续第 2 章。
4. 记录所有问题和修复。

验收关注：

- Agent 是否像角色；
- 返修是否可理解；
- Memory 是否可信；
- UI 是否能解释系统行为；
- 成本是否可控；
- 是否出现黑盒卡住。

## 风险

1. **范围过大风险**
   这是大版本，但必须完整规划。执行可阶段化，产品版本不能碎片化。

2. **LLM 成本风险**
   默认能力应优先 rule-based。LLM-based 能力必须有预算和开关。

3. **过度自动化风险**
   Agent Memory 和 local repair 不应绕过人工控制。

4. **外部工具风险**
   搜索、文件、HTTP、bash 必须默认关闭，配置授权后才能使用。

5. **Pi 依赖风险**
   Pi 集成只能作为可选上层 Supervisor，不能成为 Novelos 核心运行依赖。

6. **评测空转风险**
   Eval 必须能发现真实缺陷，不能只验证 schema。

7. **UI 运维化风险**
   AgentOps UI 不能变成工程日志墙，必须为创作者解释问题。

## 完成后的预期

v6.0 完成后，Novelos 的核心体验应从：

```text
点按钮生成章节，失败后看日志和重跑
```

升级为：

```text
一个可解释、可修复、可评测、可成长的 AI 创作团队协助作者推进长篇小说
```

用户应能明确感受到：

- Planner 像总编；
- Screenwriter 像编剧；
- Author 像写手；
- Polisher 像文字编辑；
- Editor 像责编；
- MemoryCurator 像设定管理员；
- 系统知道自己为什么这么做，也知道失败后怎么局部修。

## Development Prompt for Implementation Agent

Task: Implement v6.0 Agent Role Capability System.

This is a complete capability release. Do not split it into tiny product versions. You may execute in phases, but the delivered scope must form one coherent Agent role capability system.

Read first:

- `docs/codex/planning/novel-factory-v6.0-agent-role-capability-system-spec.md`
- `docs/codex/planning/novel-factory-v5.9.3-agent-skill-expansion-spec.md`
- `novel_factory/config/skills.yaml`
- `novel_factory/agents/*`
- `novel_factory/skills/registry.py`
- `novel_factory/skill_packages/*`
- `novel_factory/workflow/graph.py`
- `novel_factory/workflow/nodes.py`
- `frontend/src/components/settings/SkillVisibilityPanel.tsx`
- `frontend/src/components/project/AuthorWritingSurface.tsx`

Implement the full v6.0 capability:

1. Add Agent Role Profiles for planner, screenwriter, author, polisher, editor, memory_curator, publisher.
2. Add Role Profile loader and make runtime Agents consume profiles.
3. Convert the four v5.9.3 built-in Skills into package-style Capability Packs:
   - chapter_objective_checker
   - scene_conflict_checker
   - event_coverage_checker
   - memory_patch_validator
4. Add role-specific capability packs listed in the spec, with manifest, handler, README, fixtures, and tests.
5. Add Agent Memory storage, repository, API, and UI.
6. Add bounded autonomy policy and decision objects.
7. Add controlled Agent Tool Runtime with internal tools enabled and external tools opt-in.
8. Add Genre Strategy config and inject it into Agent context with trace visibility.
9. Add self-check and local repair loop for core creative Agents.
10. Add collaboration contracts and use them for handoff validation and Editor revision attribution.
11. Add Agent Decision Trace persistence and UI.
12. Add optional Pi/external Agent supervisor bridge through controlled Novelos API tools.
13. Add AgentOps Role Console showing role goals, capability packs, memory, trace, eval status, and recent failure reasons.
14. Add Agent eval harness and fixtures.
15. Run a real-project acceptance flow with a new project and real LLM, then document findings.

Constraints:

- Do not implement only one thin slice and call it complete.
- Do not leave new Skills outside `skill_packages/`.
- Do not add uncontrolled LLM calls.
- Do not add uncontrolled external tools. Search/file/http/bash must be opt-in and audited.
- Do not make Pi a hard dependency.
- Do not break v5.9.3 Skill runtime or project-specific overrides.
- Do not turn AgentOps UI into raw JSON/log dump.
- Preserve existing workflow order unless the spec explicitly requires a contract/trace insertion that does not alter user-visible chapter state transitions.

Required validation:

```bash
python3 scripts/verify.py smoke
python3 -m pytest tests/test_skill_config.py tests/test_skills.py tests/test_skills_api.py tests/test_agents.py -q
python3 -m pytest tests/test_v516_langgraph_activation.py tests/test_v58_workflow_observability.py -q
python3 scripts/eval_agents.py all
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm run build
cd frontend && npm run test -- --run
```

Deliver:

- Code changes.
- Database migrations if needed.
- Capability packages.
- Agent role profiles.
- AgentOps UI.
- Eval harness.
- Tests.
- Real LLM acceptance report.
- Completion report.
- Review report.
