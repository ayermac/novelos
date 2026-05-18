# Novelos v5.9.3 Agent Skill Expansion 规格

## 状态

- 类型：可执行规划规格
- 状态：planned
- 基线：v5.9.2 UI Controls Standardization
- 产品目标：把 Skill 从“润色/审核插件”升级为覆盖完整创作链路的 Agent 能力层
- 技术目标：为 Planner、Screenwriter、Author、MemoryCurator 接入可配置 Skill stage，并补齐第一批创作型 Skill
- 版本性质：小版本，优先补能力模型和执行挂载，不做大规模 UI 重构

## 背景

当前 Skill Console 已经能展示 Skill、启用/禁用、Agent x Stage 挂载矩阵、测试和安全审查，但底层能力仍不完整：

1. `novel_factory/config/skills.yaml` 只注册了 4 个 Skill：
   - `humanizer-zh`
   - `ai-style-detector`
   - `narrative-quality`
   - `style-bible-checker`
2. 生产执行链路里真正调用 `run_skills_for_agent(...)` 的只有：
   - `polisher.after_llm`
   - `editor.before_review`
3. `planner`、`screenwriter`、`author`、`memory_curator` 虽然在 Skill Console 的矩阵中有 stage 定义，但 Agent 代码没有执行对应 Skill。
4. 现有 Skill 偏“质量检测/润色”，缺少“规划、场景、正文、记忆抽取”阶段的创作能力。

这导致用户看到的 Skill Console 像一个能力平台，但真实系统里 Skill 只覆盖了后半段，无法回答“为什么 Planner/Author 不需要 Skill”这种产品问题。

本版本要修正这个能力模型：不是所有逻辑都要 Skill 化，但每个核心创作 Agent 至少要有明确的 Skill 插槽、执行时机、输入输出契约和默认能力。

## 产品判断

Skill 不应该替代 Agent。Agent 仍负责主要创作决策和 LLM 调用，Skill 负责可插拔、可复用、可测试的局部能力：

| 层级 | 职责 | 示例 |
| --- | --- | --- |
| Agent | 完成一个生产阶段的核心任务 | Planner 生成章节指令，Author 写正文 |
| Skill | 在 Agent 前后增强、校验或转换局部能力 | 伏笔调度检查、场景冲突检查、人物口吻检查 |
| Validator | 不改内容，只给通过/风险/建议 | narrative-quality、plot-coverage-checker |
| Transformer | 改写或增强内容 | humanizer-zh、hook-enhancer |
| Context Skill | 生成可注入上下文片段 | character-voice-card、foreshadowing-brief |
| Extractor | 从内容中抽取结构化事实 | memory-fact-extractor |

因此，`planner/screenwriter/author/memory_curator` 不是“不需要 Skill”，而是当前还没完成“Skill 化插槽”。

## 非目标

- 不把所有 Agent 逻辑重写成 Skill。
- 不改变主工作流节点顺序。
- 不新增复杂多租户权限。
- 不引入外部 Skill 市场或远程执行。
- 不在本版本做 RAG、长上下文记忆治理或 MCP 工具调用。
- 不大改 Skill Console UI，仅做必要展示文案和矩阵解释补强。

## 当前代码事实

已存在但未充分利用：

```text
novel_factory/api/routes/skills.py
KNOWN_AGENT_STAGES = {
  planner: before_llm / after_llm / before_save
  screenwriter: before_llm / after_llm / before_save
  author: before_llm / after_llm / before_save
  polisher: after_llm / before_save
  editor: before_review
  memory_curator: before_extract / after_extract / before_save
}
```

已执行 Skill 的 Agent：

```text
polisher.after_llm
editor.before_review
```

未执行 Skill 的 Agent：

```text
planner
screenwriter
author
memory_curator
```

## 核心交付

### 1. 建立 Agent Skill 执行协议

新增或抽取一个通用 helper，避免每个 Agent 手写重复逻辑：

```text
novel_factory/agents/skill_hooks.py
```

建议接口：

```python
def run_agent_skills(
    *,
    repo,
    skill_registry,
    project_id: str,
    chapter_number: int,
    agent: str,
    stage: str,
    payload: dict,
    project_overrides: dict | None = None,
    skill_type_hint: str | None = None,
    fail_closed_ids: set[str] | None = None,
) -> AgentSkillHookResult:
    ...
```

最低要求：

1. 统一调用 `skill_registry.run_skills_for_agent(...)`。
2. 统一保存 `skill_runs`。
3. 统一处理失败：
   - 默认 soft fail：记录 warning，不阻塞主流程。
   - 明确配置的 critical/fail_closed Skill 才阻塞。
4. 返回结构化结果：
   - `ok`
   - `errors`
   - `warnings`
   - `transforms`
   - `context_fragments`
   - `validation_issues`
5. 所有 hook 执行必须 best-effort，不允许一个非关键 Skill 把整章流程打死。

### 2. Planner 接入 Skill 插槽

目标：让章节规划具备可插拔的“前置上下文”和“规划质量检查”。

接入点：

```text
planner.before_llm
planner.after_llm
planner.before_save
```

推荐默认 Skill：

| Skill ID | 类型 | Stage | 作用 |
| --- | --- | --- | --- |
| `foreshadowing-planner` | context/validator | before_llm / before_save | 汇总待埋/待兑现伏笔，检查规划是否遗漏 |
| `chapter-objective-checker` | validator | after_llm | 检查 objective 是否具体、可执行、承接上一章状态 |
| `pacing-planner` | validator | after_llm | 检查章节目标是否过载或过空 |

本版本最低实现：

- 至少新增 `chapter-objective-checker`。
- Planner 在保存 instruction 前运行 `after_llm` 或 `before_save` 校验。
- 校验失败不直接阻塞，先写入 `skill_runs` 和 artifact warning；只有明显 schema/空目标才阻塞。

### 3. Screenwriter 接入 Skill 插槽

目标：让场景拆解能被检查，而不是只相信 LLM 输出。

接入点：

```text
screenwriter.before_llm
screenwriter.after_llm
screenwriter.before_save
```

推荐默认 Skill：

| Skill ID | 类型 | Stage | 作用 |
| --- | --- | --- | --- |
| `scene-conflict-checker` | validator | after_llm | 检查每个 scene beat 是否有目标、冲突、转折 |
| `hook-strength-checker` | validator | after_llm | 检查场景钩子和章末钩子强度 |
| `plot-ref-checker` | validator | before_save | 检查 scene beat 是否覆盖 planner 指定伏笔 |

本版本最低实现：

- 至少新增 `scene-conflict-checker`。
- Screenwriter 保存 scene beats 前执行校验。
- 校验结果写入 `skill_runs`，并在 workflow timeline message 中可追踪。

### 4. Author 接入 Skill 插槽

目标：把正文创作阶段的“事件覆盖、人物口吻、爽点密度、禁忌检查”变成可配置能力。

接入点：

```text
author.before_llm
author.after_llm
author.before_save
```

推荐默认 Skill：

| Skill ID | 类型 | Stage | 作用 |
| --- | --- | --- | --- |
| `event-coverage-checker` | validator | after_llm / before_save | 检查正文是否覆盖 required_events |
| `character-voice-checker` | validator/context | before_llm / after_llm | 注入角色口吻卡，检查人物说话是否跑偏 |
| `webnovel-payoff-checker` | validator | after_llm | 检查爽点、冲突升级、章末钩子是否足够 |
| `death-penalty-guard` | validator | before_save | 将现有死刑词校验 Skill 化或桥接展示 |

本版本最低实现：

- 至少新增 `event-coverage-checker`。
- Author 在已有字数质量门、死刑词、伏笔覆盖检查之外，增加 Skill hook。
- 不能把 Author 的核心写作改成 Skill；Skill 只增强和校验。
- 对真实 LLM 模式下的长文输出要保守，Skill 不能显著增加 token 成本。

### 5. MemoryCurator 接入 Skill 插槽

目标：让记忆抽取结果可校验，减少错误写入资料库。

接入点：

```text
memory_curator.before_extract
memory_curator.after_extract
memory_curator.before_save
```

推荐默认 Skill：

| Skill ID | 类型 | Stage | 作用 |
| --- | --- | --- | --- |
| `memory-patch-validator` | validator | after_extract / before_save | 检查 patch target_table/operation/data 是否合理 |
| `fact-dedup-checker` | validator | before_save | 检查 story_facts 是否重复或冲突 |
| `plot-status-transition-checker` | validator | before_save | 检查伏笔状态是否非法跳转 |

本版本最低实现：

- 至少新增 `memory-patch-validator`。
- MemoryCurator 在写入 memory batch 前运行 Skill。
- 严禁 Skill 自动把低置信度 patch 写入主资料表；仍然进入人工审核/批次确认链路。

### 6. Skill 配置扩展

更新：

```text
novel_factory/config/skills.yaml
```

目标从 4 个扩展到至少 8 个：

```yaml
skills:
  chapter-objective-checker:
    enabled: true
    type: validator
    class: ChapterObjectiveCheckerSkill

  scene-conflict-checker:
    enabled: true
    type: validator
    class: SceneConflictCheckerSkill

  event-coverage-checker:
    enabled: true
    type: validator
    class: EventCoverageCheckerSkill

  memory-patch-validator:
    enabled: true
    type: validator
    class: MemoryPatchValidatorSkill
```

默认挂载：

```yaml
agent_skills:
  planner:
    after_llm:
      - chapter-objective-checker

  screenwriter:
    after_llm:
      - scene-conflict-checker

  author:
    after_llm:
      - event-coverage-checker

  memory_curator:
    after_extract:
      - memory-patch-validator

  polisher:
    after_llm:
      - humanizer-zh
    before_save:
      - ai-style-detector

  editor:
    before_review:
      - ai-style-detector
      - narrative-quality
      - style-bible-checker
```

### 7. Skill Manifest 与 Safety Review

每个新增 Skill 必须有 manifest：

```text
novel_factory/config/skills/manifest/*.yaml
```

最低字段：

```yaml
id:
name:
version:
type:
class_name:
description:
allowed_targets:
permissions:
failure_policy:
input_schema:
output_schema:
```

要求：

1. 新增 Skill 不能再出现 “has no manifest (v2.1 compatibility)”。
2. Skill Console 的“风险/缺失”不应把新增 Skill 当成 legacy。
3. `allowed_targets` 必须限制到合理 Agent/Stage，不能默认全开放。

### 8. WebUI 最小补强

不做大 UI 重构，只补两个点：

1. Skill Console 总览显示：
   - 当前能力覆盖率：已接入 Agent 数 / 核心 Agent 数；
   - 未接入核心 Agent 清单；
   - legacy Skill 清单；
   - 新增 Skill 的目标 Agent/Stage。
2. Agent 编排矩阵中增加帮助文案：
   - `before_llm`: 生成前上下文增强；
   - `after_llm`: 生成后校验/改写；
   - `before_save`: 入库前最终闸门；
   - `before_extract/after_extract`: 记忆抽取前后；
   - `before_review`: 审稿前质量检查。

## 文件范围

允许修改：

```text
novel_factory/agents/skill_hooks.py
novel_factory/agents/planner.py
novel_factory/agents/screenwriter.py
novel_factory/agents/author.py
novel_factory/agents/memory_curator.py
novel_factory/agents/polisher.py
novel_factory/agents/editor.py
novel_factory/skills/base.py
novel_factory/skills/*.py
novel_factory/config/skills.yaml
novel_factory/config/skills/manifest/*.yaml
novel_factory/api/routes/skills.py
frontend/src/components/settings/SkillVisibilityPanel.tsx
frontend/src/components/settings/SkillVisibilityPanel.css
tests/test_skill_config.py
tests/test_skills.py
tests/test_agents.py
tests/test_skills_api.py
frontend/src/components/settings/__tests__/SkillVisibilityPanel.test.tsx
docs/codex/reports/*
docs/codex/reviews/*
```

不建议修改：

```text
novel_factory/workflow/graph.py
novel_factory/workflow/runner.py
novel_factory/db/migrations/*
frontend/src/components/project/AuthorWorkbench*
frontend/src/pages/ProjectDetail.tsx
```

除非实现中证明必须修改，否则本版本不碰主工作流结构和数据库结构。

## 实施顺序

### Phase 1: 执行协议

1. 新增 `agents/skill_hooks.py`。
2. 抽取 Polisher/Editor 中重复的 Skill 执行和 `skill_runs` 保存逻辑。
3. 保持 Polisher/Editor 行为不变，先用测试锁住。

### Phase 2: 新增 4 个最小创作 Skill

1. `ChapterObjectiveCheckerSkill`
2. `SceneConflictCheckerSkill`
3. `EventCoverageCheckerSkill`
4. `MemoryPatchValidatorSkill`

优先做 deterministic/rule-based，不依赖额外 LLM 调用。

### Phase 3: 接入 4 个核心 Agent

1. Planner 接 `after_llm`。
2. Screenwriter 接 `after_llm`。
3. Author 接 `after_llm`。
4. MemoryCurator 接 `after_extract`。

### Phase 4: 配置与 WebUI

1. 更新 `skills.yaml` 默认挂载。
2. 新增 manifest。
3. Skill Console 显示核心 Agent 覆盖情况和 stage 说明。

### Phase 5: 验收与文档

1. 后端测试覆盖新增 Skill、挂载、Agent 执行。
2. 前端测试覆盖 Skill Console 新增信息。
3. 写 completion report 和 review。

## 验收标准

### 后端验收

1. `/api/skills` 返回至少 8 个 Skill。
2. `/api/skills/config` 中 `planner/screenwriter/author/memory_curator` 至少各有 1 个默认挂载。
3. Planner 执行时产生 `chapter-objective-checker` 的 `skill_runs`。
4. Screenwriter 执行时产生 `scene-conflict-checker` 的 `skill_runs`。
5. Author 执行时产生 `event-coverage-checker` 的 `skill_runs`。
6. MemoryCurator 执行时产生 `memory-patch-validator` 的 `skill_runs`。
7. 新增 Skill 全部有 manifest，不显示 legacy/no manifest 风险。
8. 非关键 Skill 失败不应导致章节流程直接崩溃。
9. 明确配置为 critical 的 Skill 失败才允许阻塞。

### 前端验收

1. Skill Console 不再只显示 4 个 Skill。
2. 总览能看出核心 Agent Skill 覆盖情况。
3. Agent 编排矩阵中 planner/screenwriter/author/memory_curator 有默认挂载。
4. stage 文案不再只有内部英文，用户能理解每个阶段含义。
5. legacy/no manifest 只出现在真正缺 manifest 的 Skill 上。

### 回归验收

必须通过：

```bash
python3 scripts/verify.py smoke
python3 -m pytest tests/test_skill_config.py tests/test_skills.py tests/test_skills_api.py tests/test_agents.py -q
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm run test -- --run
```

如果修改了 Polisher/Editor 行为，还要跑：

```bash
python3 -m pytest tests/test_v40_style_bible_skill.py tests/test_skill_package.py -q
```

## 风险与约束

1. **过度 Skill 化风险**  
   不要把 Agent 主流程拆碎。Skill 只做增强/校验/转换/抽取，不接管核心生成。

2. **真实 LLM 成本风险**  
   新增 Skill 默认必须 rule-based，不新增 LLM 调用。需要 LLM 的 Skill 必须显式配置并默认关闭。

3. **流程阻塞风险**  
   创作阶段的 Skill 默认 soft fail。只有安全、事实、硬质量门才能 fail closed。

4. **UI 误导风险**  
   如果某个 Agent/Stage 只是可配置但代码没有执行，UI 必须显示“未接入运行时”。本版本目标是消除这种不一致。

5. **Manifest 漂移风险**  
   新增 Skill 必须同时更新 config、manifest、测试 fixtures，避免再次出现 legacy/no manifest。

## 完成后的预期效果

用户在 Skill Console 中应能看到：

```text
可用 Skill: 8+
核心 Agent 覆盖: planner / screenwriter / author / polisher / editor / memory_curator
每个 Agent 至少有一个真实执行的默认 Skill
每个 Skill 有清晰用途、目标阶段、安全状态和测试入口
```

创作流程应从：

```text
LLM 生成 → 少量后置质量检查
```

升级为：

```text
Agent 生成 → 阶段化 Skill 增强/校验 → 结构化记录 → 可视化编排
```

## Development Prompt for Implementation Agent

Task: Implement v5.9.3 Agent Skill Expansion.

Read first:

- `docs/codex/planning/novel-factory-v5.9.3-agent-skill-expansion-spec.md`
- `novel_factory/config/skills.yaml`
- `novel_factory/api/routes/skills.py`
- `novel_factory/skills/registry.py`
- `novel_factory/agents/planner.py`
- `novel_factory/agents/screenwriter.py`
- `novel_factory/agents/author.py`
- `novel_factory/agents/polisher.py`
- `novel_factory/agents/editor.py`
- `novel_factory/agents/memory_curator.py`

Implement:

1. Add a shared Agent Skill hook helper to centralize `run_skills_for_agent` execution and `skill_runs` persistence.
2. Preserve existing Polisher and Editor behavior while migrating them to the helper where safe.
3. Add four deterministic rule-based Skills:
   - `chapter-objective-checker`
   - `scene-conflict-checker`
   - `event-coverage-checker`
   - `memory-patch-validator`
4. Add manifests for all four new Skills.
5. Update `skills.yaml` so planner, screenwriter, author, and memory_curator each have at least one default mounted Skill.
6. Wire runtime execution:
   - Planner: `after_llm`
   - Screenwriter: `after_llm`
   - Author: `after_llm`
   - MemoryCurator: `after_extract`
7. Update Skill Console minimally to show core Agent coverage and stage explanations.
8. Add/update tests proving the new Skills are listed, mounted, executed, and recorded.

Constraints:

- Do not change workflow graph order.
- Do not add database migrations unless absolutely necessary.
- Do not add LLM calls inside new Skills.
- Default new Skills should soft-fail unless the spec explicitly says otherwise.
- Do not regress existing 4 Skills.
- Avoid broad UI redesign; only adjust Skill Console text/coverage indicators.

Validation:

```bash
python3 scripts/verify.py smoke
python3 -m pytest tests/test_skill_config.py tests/test_skills.py tests/test_skills_api.py tests/test_agents.py -q
python3 -m pytest tests/test_v40_style_bible_skill.py tests/test_skill_package.py -q
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm run test -- --run
```

Deliver:

- Code changes.
- Tests.
- Completion report under `docs/codex/reports/`.
- Review notes under `docs/codex/reviews/`.
