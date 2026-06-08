# v6.10.1 Skill 工程化标准化规划

## 版本目标

v6.10.0 已经引入双层 Skill 架构：

- **Knowledge Skill**：Markdown 写作知识，面向 LLM prompt 注入或 function calling 咨询。
- **Code Skill**：Python 执行器，面向确定性校验、转换、门禁和运行时审计。

v6.10.1 的目标不是继续堆新 Skill，而是把双层体系工程化，解决“知识库 Skill 和 Code Skill 共存但治理不一致”的问题，让设置页、配置文件、运行日志、项目覆盖和测试标准都能明确区分并稳定维护两类 Skill。

最终状态：

```text
Skill System
├── Knowledge Skills
│   ├── 内容：Markdown 写作知识
│   ├── 管理：知识库 Skill 面板
│   ├── 运行：prompt 注入 / agentic tool calling
│   └── 审计：记录注入/调用的 skill_id、version、token_count、selection_reason
└── Code Skills
    ├── 内容：Python validator / transform / guard
    ├── 管理：Code Skill 挂载矩阵
    ├── 运行：Agent stage hooks / QualityHub / QualityGate
    └── 审计：skill_runs、manifest、failure_policy、测试结果
```

## 背景问题

### 1. 设置页只维护 Code Skill

当前 `Settings > Skill 管理` 主要接入 `/skills`、`/skills/config`、`/skills/agent-matrix` 等 Code Skill API，展示的是启用、挂载、测试和 Review/Test。

Knowledge Skill 虽已有 `/knowledge-skills` CRUD API，但尚未作为设置页的一等入口呈现，导致用户能看到 Code Skill 的挂载链路，却看不到 LLM 写作知识库的启用、适用范围和注入策略。

### 2. Knowledge Skill 治理弱于 Code Skill

Code Skill 已有：

- `novel_factory/config/skills.yaml`
- manifest YAML
- `enabled`
- `agent_skills`
- `failure_policy`
- `skill_runs`
- 运行测试接口

Knowledge Skill 当前主要依赖：

- `novel_factory/skills/knowledge/_index.yaml`
- 每个知识目录的 `meta.yaml`
- `SKILL.md`
- `applicable_agents`
- `applicable_genres`

缺口：

- 没有 `enabled`。
- 没有 `priority`。
- 没有 token budget。
- 没有 injection mode。
- 没有统一审计记录。
- 没有项目级覆盖闭环。

### 3. 同名 Skill 存在语义混淆

例如：

- `show-dont-tell` 可以是 Knowledge Skill：告诉 LLM 如何展示而非讲述。
- `show-dont-tell` 也可以是 Code Skill：检测直白心理说明。

同名本身可以接受，但 UI、日志、API、项目覆盖里必须显示命名空间，否则排障时无法判断“哪个 Skill 生效了”。

### 4. prompt 注入粒度偏粗

非 agentic 模式下，当前逻辑会将适配 Agent 和 Genre 的知识拼接进 prompt。这个机制简单可靠，但长期会带来：

- token 膨胀；
- 知识互相稀释；
- 运行日志无法解释“为什么本章注入这些知识”；
- 内容问题无法反向驱动知识选择。

## 设计原则

1. **不合并两类 Skill**  
   Knowledge Skill 和 Code Skill 保持不同生命周期。前者维护“怎么写”，后者维护“怎么判定/怎么执行”。

2. **命名空间强制可见**  
   所有 UI 和日志都必须区分 `knowledge:<id>` 与 `code:<id>`。

3. **LLM 设置管策略，Skill 管理管资产**  
   `LLM 配置` 只管理 Knowledge Skill 的调用方式和 agentic 策略；`Skill 管理` 管知识内容、适用范围、Code Skill 挂载与测试。

4. **项目覆盖不改全局资产**  
   项目级启停、优先级和 token budget 写入项目覆盖层，不直接改内置知识文件。

5. **运行证据必须可追溯**  
   每次章节生产必须能回答：注入了哪些知识？为什么注入？注入了多少 token？模型是否主动调用过知识 Tool？

6. **先工程标准，再新增知识**  
   v6.10.1 不以新增大量知识 Skill 为目标，重点是建立治理、审计、测试和 UI 规范。

## 目标范围

### A. Knowledge Skill 元数据标准

扩展 `meta.yaml` 支持以下字段：

```yaml
skill_id: show-dont-tell
namespace: knowledge
name: 展示而非讲述指南
description: 用动作、细节、对白代替直白心理说明
enabled: true
priority: 50
token_budget: 1200
injection_mode: auto        # auto | always | agentic_only | disabled
tags:
  - writing
  - prose
applicable_agents:
  - author
  - polisher
  - editor
applicable_genres:
  - urban
  - system
version: "1.1"
source: builtin             # builtin | user | project
```

兼容规则：

- 旧 `meta.yaml` 缺少字段时必须自动补默认值。
- `enabled` 默认 `true`。
- `priority` 默认 `50`。
- `token_budget` 默认由系统配置决定。
- `injection_mode` 默认 `auto`。
- `namespace` 缺省时视为 `knowledge`。

### B. KnowledgeManager 选择策略

新增 Knowledge Skill 选择器，替代简单“适配 agent 就全量注入”。

输入：

- `agent_id`
- `genre`
- `chapter_number`
- `revision_context`
- `quality_findings`
- `project_overrides`
- `token_budget`

输出：

```python
{
    "skills": [...],
    "selection_reason": {
        "show-dont-tell": ["agent_match", "quality_signal:STRAIGHT_EMOTION"],
        "dialogue-naturalness": ["agent_match", "quality_signal:LOW_COLLOQUIAL_MARKERS"],
    },
    "estimated_tokens": 1830,
}
```

选择规则：

1. 禁用的 Knowledge Skill 不参与。
2. `always` 优先注入，但仍受硬 token cap 约束。
3. `agentic_only` 不进入 prompt 注入，只暴露为 tool。
4. `auto` 根据 Agent、Genre、质量信号和章节任务选择。
5. 同类知识超过预算时按 `priority`、质量信号命中、最近失败问题排序。

### C. LLM 设置中的知识调用策略

在 `Settings > LLM 配置` 增加“知识调用策略”区域：

- 全局 Knowledge Skill 开关。
- 全局 prompt 注入 token budget。
- 全局 agentic tool calling 开关。
- per-agent `agentic_mode`。
- per-agent `max_tool_rounds`。
- per-agent `knowledge_token_budget`。
- 模式说明：
  - `prompt_injection`：稳定、可控、成本较高。
  - `agentic_tools`：按需咨询、可解释，但依赖模型 tool calling 能力。
  - `hybrid`：关键知识注入，补充知识用 tools。

配置建议：

```yaml
knowledge:
  enabled: true
  default_injection_mode: auto
  default_token_budget: 2400
  agents:
    planner:
      token_budget: 1800
      agentic_mode: false
    author:
      token_budget: 3000
      agentic_mode: false
    editor:
      token_budget: 2000
      agentic_mode: true
      max_tool_rounds: 3
```

### D. Skill 管理中的双层 UI

`Settings > Skill 管理` 拆成两个平级工作台：

```text
Skill 管理
├── Code Skills
│   ├── 能力库
│   ├── Agent 挂载矩阵
│   ├── Review/Test
│   └── 目录
└── Knowledge Skills
    ├── 知识库目录
    ├── Agent/Genre 适配矩阵
    ├── 注入预览
    ├── 编辑器
    └── 运行审计
```

Knowledge Skill 面板能力：

- 列出所有知识。
- 按 Agent、Genre、Tag 过滤。
- 编辑 `SKILL.md` 和 `meta.yaml`。
- 启用/禁用单个知识。
- 调整优先级和 token budget。
- 查看某个 Agent 在某个 Genre 下会选中的知识。
- 预览最终注入 prompt。
- 查看最近章节实际注入/调用记录。

### E. 运行审计事件

新增结构化事件：

```text
knowledge_selected
knowledge_injected
knowledge_agentic
knowledge_tool_result
knowledge_budget_trimmed
```

`knowledge_injected` payload 必须包含：

```json
{
  "agent": "author",
  "genre": "system",
  "skill_ids": ["knowledge:webnovel-excitement", "knowledge:dialogue-naturalness"],
  "versions": {"webnovel-excitement": "1.1"},
  "estimated_tokens": 2140,
  "token_budget": 3000,
  "selection_reason": {
    "dialogue-naturalness": ["agent_match", "quality_signal:LOW_COLLOQUIAL_MARKERS"]
  }
}
```

### F. 项目级覆盖

扩展项目覆盖结构：

```json
{
  "skills": {
    "code:death-penalty": {
      "enabled": true
    }
  },
  "agent_skills": {
    "author": {
      "after_llm": ["death-penalty"]
    }
  },
  "knowledge_skills": {
    "enabled": ["webnovel-excitement", "dialogue-naturalness"],
    "disabled": ["genre-suspense"],
    "overrides": {
      "webnovel-excitement": {
        "priority": 90,
        "token_budget": 1600,
        "injection_mode": "always"
      }
    }
  }
}
```

实现要求：

- `KnowledgeManager.get_for_agent()` 必须接收并应用项目覆盖。
- Agent 获取知识上下文时必须传入项目覆盖。
- UI 必须提示“这是项目覆盖，不会改写全局内置知识”。

### G. 命名空间规范

内部 ID 仍保留原始 `skill_id`，但跨层展示和 API 输出必须增加：

```json
{
  "namespace": "knowledge",
  "qualified_id": "knowledge:dialogue-naturalness",
  "skill_id": "dialogue-naturalness"
}
```

Code Skill 对应：

```json
{
  "namespace": "code",
  "qualified_id": "code:dialogue-naturalness",
  "skill_id": "dialogue-naturalness"
}
```

要求：

- Timeline 展示 qualified id。
- Settings 列表展示 namespace badge。
- Project overrides 接受 qualified id；旧 unqualified id 兼容为 Code Skill，Knowledge 覆盖必须显式放在 `knowledge_skills`。

### H. 契约测试标准

Code Skill 每个新增或修改必须覆盖：

- manifest 可加载；
- registry 可实例化；
- `run()` 返回标准 envelope；
- agent/stage allowed 校验；
- failure_policy 行为；
- 至少一个失败样例。

Knowledge Skill 每个新增或修改必须覆盖：

- `_index.yaml` 引用存在；
- `meta.yaml` 字段合法；
- `SKILL.md` 非空；
- `applicable_agents` 均为合法 Agent；
- `applicable_genres` 均为系统支持 Genre 或空；
- token 估算不超过默认预算；
- 同名 Code Skill 存在时 UI/API qualified id 不冲突。

新增测试文件建议：

```text
tests/test_v6101_knowledge_skill_governance.py
tests/test_v6101_skill_namespace_contract.py
tests/test_v6101_knowledge_selection.py
frontend/src/components/settings/__tests__/KnowledgeSkillPanel.test.tsx
```

## 非目标

- 不新增大批量写作知识。
- 不重写 Code Skill Registry。
- 不把 Knowledge Skill 强行挂进 `agent_skills` 矩阵。
- 不默认开启所有 Agent 的 function calling。
- 不引入向量库/RAG 检索。
- 不把项目覆盖写回内置 `meta.yaml`。

## 实施阶段

### Phase 1: 后端治理模型

- 扩展 Knowledge Skill meta 默认字段。
- 增加 qualified id 输出。
- 增加 Knowledge selection service。
- 接入项目覆盖。
- 增加 Knowledge 审计事件 payload。
- 补充后端契约测试。

验收：

- 所有现有 Knowledge Skill 在不改 meta 的情况下继续加载。
- `/knowledge-skills` 返回 namespace、qualified_id、enabled、priority、token_budget、injection_mode。
- Author 注入知识时记录 skill_ids、versions、token_budget、selection_reason。
- 项目覆盖可以禁用某个 Knowledge Skill。

### Phase 2: LLM 设置策略 UI

- 在 LLM 配置页新增“知识调用策略”。
- 支持全局 Knowledge Skill 开关。
- 支持 per-agent agentic_mode、max_tool_rounds、token_budget。
- 写入 `config/local.yaml` 或桌面安全配置接口。

验收：

- 用户能在 UI 中看到每个 Agent 的知识调用策略。
- 修改策略后配置文件可持久化。
- 不写入 API key 等敏感字段。
- 重启提示符合现有 LLM 设置交互规范。

### Phase 3: Knowledge Skill 管理 UI

- 在 Skill 管理页增加 Knowledge Skills 分区。
- 接入 `/knowledge-skills` CRUD。
- 支持列表、详情、编辑、启停、适用 Agent/Genre 编辑。
- 支持注入预览。

验收：

- 用户可以查看和编辑 `SKILL.md`。
- 用户可以查看某个 Agent/Genre 下会选中的知识。
- Code Skill 和 Knowledge Skill 同名时 UI 不混淆。
- 现有 Code Skill 面板不回归。

### Phase 4: 运行审计闭环

- Timeline 展示 `knowledge_selected` 和 `knowledge_injected` 详情。
- RunDetail 展示知识注入清单。
- Artifact 中保存 Knowledge compact audit。
- 质量问题可反向关联推荐 Knowledge Skill。

验收：

- 章节运行后能看到“本章 Author 注入了哪些知识”。
- 能看到每条知识的 selection reason。
- agentic tool calling 时能看到 tool call 轮次和结果。
- 预算裁剪时有 `knowledge_budget_trimmed` 事件。

## 验收标准

v6.10.1 完成时必须满足：

1. Code Skill 与 Knowledge Skill 在 UI、API、日志中完全可区分。
2. Knowledge Skill 有启停、优先级、预算和注入模式。
3. LLM 设置能维护知识调用策略，而不是只维护模型路由。
4. Skill 管理能维护 Knowledge Skill 内容和适用范围。
5. 项目覆盖能影响 Knowledge Skill 选择，但不改写全局知识文件。
6. 每次章节生产可审计实际注入/调用的知识 Skill。
7. 所有 Knowledge Skill 和 Code Skill 均有契约测试覆盖。
8. 现有 v6.10.0 章节生产流程不回归。

## 风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| prompt 注入继续膨胀 | 成本上升，模型注意力稀释 | token budget + selection reason + priority |
| function calling 不稳定 | 生成延迟和失败率上升 | 默认不全局开启，仅 per-agent 试点 |
| 同名 Skill 混淆 | 排障困难 | namespace + qualified_id |
| 用户编辑内置知识导致升级冲突 | 内置资产污染 | builtin 只读或复制为 user/project 版本 |
| 项目覆盖结构复杂 | 使用门槛变高 | UI 表单化，保留 JSON 高级模式 |

## 推荐开发顺序

1. 后端 Knowledge meta 默认字段与 API 扩展。
2. Knowledge selection service 和审计事件。
3. 项目覆盖接入 Agent 知识注入路径。
4. LLM 设置新增知识调用策略。
5. Skill 管理新增 Knowledge Skills 分区。
6. Timeline/RunDetail 展示知识审计。
7. 契约测试与文档闭环。

## 与 v6.10.0 的关系

v6.10.0 解决“Knowledge Skill 能不能进入系统”的问题。

v6.10.1 解决“Knowledge Skill 如何被工程化维护”的问题。

因此 v6.10.1 是 v6.10.0 的治理增强版本，不改变双层 Skill 的基本方向，只补齐命名空间、配置、UI、审计、覆盖和测试标准。
