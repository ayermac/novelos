# v2.1 QualityHub 与 Skill 插件化质量中枢开发规范

## 目标

v2.1 的目标是把系统的质量把关能力从分散在 Polisher、Editor、validators 里的局部规则，升级为可配置、可追踪、可扩展的内容质量中枢。

v2 已经完成旁路 Agent 扩展：Scout、Secretary、ContinuityChecker、Architect。v2.1 不继续增加新生产 Agent，而是围绕“内容质量”建立统一的 QualityHub 和 Skill 插件机制。

本轮重点：

- 新增 QualityHub。
- 新增 SkillRegistry。
- 新增 BaseSkill / TransformSkill / ValidatorSkill / ContextSkill / ReportSkill 协议。
- 新增 `skills.yaml`。
- Polisher 可配置挂载 HumanizerSkill。
- Editor 可配置挂载 AIStyleDetectorSkill。
- QualityHub 汇总 death_penalty、fact_lock、state/plot verifier、AIStyleDetector、NarrativeQualityScorer。
- 每章生成结构化 quality report。
- 质量结果可追踪、可查询、可反哺 learned_patterns。

## 当前前置条件

必须基于以下状态开发：

- v1-v1.4 已通过。
- v2 多 Agent sidecar 扩展已通过。
- 当前全量测试应为 `321/321` 或更多。
- 不允许破坏 v1-v2 任何验收测试。

## 版本定位

v2.1 是质量中枢与 Skill 插件底座版本，不是 Web UI 版本，也不是多模型治理版本。

核心思想：

```text
Agent 负责角色职责
Skill 负责专项能力
QualityHub 负责汇总、评分、放行和返修建议
```

推荐流程：

```text
Author draft
  -> QualityHub.precheck(draft)
  -> Polisher + configured transform skills
  -> QualityHub.post_polish_check(polished)
  -> Editor + configured validator skills
  -> QualityHub.final_gate()
  -> pass/revision/blocking
```

实现上不强制新增 LangGraph 节点，可以先作为 Agent 内部服务和 CLI 命令落地。

## 本轮允许实现

允许修改：

- `novel_factory/agents/author.py`
- `novel_factory/agents/polisher.py`
- `novel_factory/agents/editor.py`
- `novel_factory/context/builder.py`
- `novel_factory/db/repository.py`
- `novel_factory/db/connection.py`
- `novel_factory/db/migrations/*`
- `novel_factory/config/*`
- `novel_factory/models/*`
- `novel_factory/validators/*`
- `novel_factory/cli.py`
- `tests/*`
- `docs/codex/*`

允许新增：

- `novel_factory/quality/hub.py`
- `novel_factory/quality/scorer.py`
- `novel_factory/quality/report.py`
- `novel_factory/skills/base.py`
- `novel_factory/skills/registry.py`
- `novel_factory/skills/humanizer_zh.py`
- `novel_factory/skills/ai_style_detector.py`
- `novel_factory/skills/narrative_quality.py`
- `novel_factory/config/skills.yaml`
- `novel_factory/db/migrations/006_v2_1_qualityhub.sql`
- `tests/test_qualityhub.py`
- `tests/test_skills.py`
- `tests/test_skill_config.py`
- `tests/test_v2_1_cli.py`

## 本轮禁止实现

- 不新增 Web UI。
- 不新增 Web API / FastAPI。
- 不新增多 Provider fallback。
- 不新增 Agent 级模型路由。
- 不新增 token 成本统计。
- 不引入 Celery / Redis / Kafka。
- 不引入 PostgreSQL。
- 不引入 SQLModel 全量 ORM。
- 不改变章节状态枚举。
- 不改变主链路顺序。
- 不让 Skill 绕过 fact_lock。
- 不让 HumanizerSkill 改剧情事实、伏笔、状态卡关键事实。
- 不让 Architect 自动应用 QualityHub 建议。

## 技术栈选型

| 模块 | 选型 | 说明 |
| --- | --- | --- |
| Skill 配置 | `skills.yaml` | 显式配置启用、禁用、阈值和挂载 Agent |
| Skill 加载 | 白名单 registry | v2.1 不做任意动态 import，避免安全风险 |
| 质量汇总 | QualityHub service | 统一评分和质量报告 |
| 存储 | SQLite + Repository | 延续现有模式 |
| 输出模型 | Pydantic | 所有 Skill 输出必须结构化 |
| CLI | argparse | 延续 v1.4/v2 |

不做任意外部插件加载。v2.1 的“插件化”是仓库内 Skill 模块 + 配置挂载，不是从网络或任意路径热加载。

## Skill 协议

### S1：BaseSkill

必须定义统一基类：

```python
class BaseSkill:
    skill_id: str
    skill_type: str

    def __init__(self, config: dict | None = None) -> None:
        ...

    def run(self, payload: dict) -> dict:
        ...
```

返回统一 envelope：

```json
{
  "ok": true,
  "error": null,
  "data": {}
}
```

### S2：TransformSkill

用于文本改写，例如 Humanizer。

输入：

```json
{
  "content": "...",
  "context": {},
  "fact_lock": []
}
```

输出：

```json
{
  "content": "...",
  "changes": [],
  "risk": "none|low|medium|high"
}
```

要求：

- 必须保留 fact_lock。
- 如果风险不是 `none/low`，Polisher 不得保存结果。
- 必须返回修改摘要。

### S3：ValidatorSkill

用于质量检测，例如 AIStyleDetector。

输入：

```json
{
  "content": "...",
  "context": {}
}
```

输出：

```json
{
  "score": 0,
  "issues": [],
  "warnings": [],
  "suggestions": [],
  "blocking": false
}
```

### S4：ContextSkill

用于构建上下文片段，例如 platform-style-guide。

输出：

```json
{
  "fragment_name": "platform_style",
  "content": "...",
  "priority": 6,
  "mandatory": false
}
```

### S5：ReportSkill

用于质量趋势报告、章节质量摘要。

输出写入 reports 或 quality_reports。

## 必修 Skill

### Q1：HumanizerZhSkill

目标：中文 AI 去味，供 Polisher 使用。

检测并修复：

- 模板化连接词。
- 空泛心理描写。
- 夸张但无信息量的情绪词。
- 三段式排比。
- 高频套话。
- 机械解释。
- 同质句式重复。

要求：

- 输入原文和 fact_lock。
- 输出 humanized content。
- 不改变剧情事实。
- 不删除伏笔编号。
- 不改变状态卡数值。
- 如果无法安全改写，返回 `ok=false` 或 `risk=high`。

验收：

- 能降低 AI 味评分。
- 删除伏笔编号时失败。
- 改变关键事件时失败。
- Polisher 可通过配置启用/禁用该 Skill。

### Q2：AIStyleDetectorSkill

目标：检测 AI 味，供 Editor 和 QualityHub 使用。

评分维度：

- `template_phrase_score`
- `connector_density_score`
- `vague_emotion_score`
- `sentence_repetition_score`
- `over_explanation_score`
- `overall_ai_trace_score`

要求：

- 输出 0-100 分，分数越高 AI 味越重。
- 超过 fail_threshold 时 blocking 或强退 Polisher。
- issue 必须包含命中的片段和原因。

验收：

- 检测模板句。
- 检测连接词过密。
- 检测同质句式重复。
- clean text 分数较低。

### Q3：NarrativeQualityScorer

目标：评价章节叙事质量。

评分维度：

- 冲突强度。
- 钩子强度。
- 信息密度。
- 节奏控制。
- 对话自然度。
- 场景沉浸感。
- 人物动机清晰度。

要求：

- v2.1 可先用规则 + 简单启发式，不要求完美 NLP。
- 输出结构化分数和建议。
- 不直接决定发布，只提供 QualityHub 汇总依据。

验收：

- 缺少冲突时降低冲突分。
- 无章末钩子时降低钩子分。
- 对话极少时给出建议。

## QualityHub

### H1：统一质量检查入口

新增：

```python
class QualityHub:
    def check_draft(self, project_id: str, chapter_number: int, content: str) -> dict:
        ...

    def check_polished(self, project_id: str, chapter_number: int, original: str, polished: str) -> dict:
        ...

    def final_gate(self, project_id: str, chapter_number: int) -> dict:
        ...
```

QualityHub 汇总：

- death_penalty。
- fact_lock。
- state_verifier。
- plot_verifier。
- AIStyleDetectorSkill。
- NarrativeQualityScorer。
- Editor review。

输出：

```json
{
  "ok": true,
  "error": null,
  "data": {
    "overall_score": 86,
    "pass": true,
    "revision_target": null,
    "blocking_issues": [],
    "warnings": [],
    "skill_results": [],
    "quality_dimensions": {}
  }
}
```

### H2：质量门禁规则

必须支持：

- critical death penalty：强退。
- fact_lock 失败：强退 Polisher。
- AI trace score 超阈值：退回 Polisher。
- state/plot 严重冲突：退回 Author。
- overall_score 低于阈值：退回 Editor/Author/Polisher。

阈值来自 `skills.yaml` 或 quality config。

### H3：质量报告归档

每次 QualityHub 检查必须可写入 `quality_reports`。

建议字段：

```text
id
project_id
chapter_number
stage
overall_score
pass
revision_target
blocking_issues_json
warnings_json
skill_results_json
quality_dimensions_json
created_at
```

## 配置要求

新增 `novel_factory/config/skills.yaml`：

```yaml
skills:
  humanizer-zh:
    type: transform
    enabled: true
    class: HumanizerZhSkill
    config:
      preserve_facts: true
      max_change_ratio: 0.35
      fail_on_fact_risk: true

  ai-style-detector:
    type: validator
    enabled: true
    class: AIStyleDetectorSkill
    config:
      warn_threshold: 45
      fail_threshold: 70

  narrative-quality:
    type: validator
    enabled: true
    class: NarrativeQualityScorer
    config:
      pass_score: 75

agent_skills:
  polisher:
    after_llm:
      - humanizer-zh
    before_save:
      - ai-style-detector

  editor:
    before_review:
      - ai-style-detector
      - narrative-quality
```

要求：

- SkillRegistry 读取 `skills.yaml`。
- disabled skill 不运行。
- 未知 skill 必须报清晰错误。
- agent hook 不存在时不得崩溃，应忽略或 warning。

## Agent 集成

### Polisher 集成

Polisher 流程：

```text
LLM polish
  -> HumanizerZhSkill after_llm
  -> fact_lock check
  -> AIStyleDetector before_save
  -> save content/version/artifact
```

要求：

- Humanizer 失败不得保存。
- AIStyleDetector 超 fail_threshold 不得保存。
- fact_lock 仍然是硬门禁，优先级高于 humanizer。
- 所有 skill result 写入 artifact 或 quality_reports。

### Editor 集成

Editor 流程：

```text
load content
  -> AIStyleDetector
  -> NarrativeQualityScorer
  -> existing Editor LLM review
  -> QualityHub final_gate
```

要求：

- AI 味过高时 revision_target=polisher。
- 叙事质量低但事实正确时 revision_target=author。
- critical 规则仍然强退。

## CLI 要求

新增：

```bash
novelos quality check --project-id demo --chapter 1 --stage polished --json
novelos quality report --project-id demo --chapter 1 --json
novelos skills list --json
novelos skills run humanizer-zh --text "..." --json
novelos skills run ai-style-detector --text "..." --json
```

要求：

- JSON 输出符合 `{ ok, error, data }`。
- skills list 不显示敏感信息。
- skills run 用于本地调试，不写章节正文。
- quality check 可以写 quality_reports。

## 数据库与迁移

允许新增：

- `006_v2_1_qualityhub.sql`

建议新增表：

```sql
quality_reports
skill_runs
```

要求：

- migration 幂等。
- `_is_migration_applied_by_schema()` 支持 006。
- Skill 运行记录可查询。

## 测试要求

必须新增或补充：

- `tests/test_qualityhub.py`
- `tests/test_skills.py`
- `tests/test_skill_config.py`
- `tests/test_v2_1_cli.py`

最低测试覆盖：

- SkillRegistry 加载 skills.yaml。
- disabled skill 不运行。
- unknown skill 报清晰错误。
- HumanizerZhSkill 降低 AI 味。
- HumanizerZhSkill 不改变 fact_lock。
- AIStyleDetector 检测模板句。
- AIStyleDetector clean text 低分。
- NarrativeQualityScorer 检测缺冲突/缺钩子。
- QualityHub 汇总多个 skill 结果。
- QualityHub critical death penalty 强退。
- QualityHub fact_lock 失败强退。
- QualityHub AI trace 超阈值退 Polisher。
- Polisher 按配置调用 Humanizer。
- Editor 按配置调用 AIStyleDetector。
- quality_reports 写入。
- skill_runs 写入。
- CLI `skills list --json`。
- CLI `skills run humanizer-zh --json`。
- CLI `quality check --json`。
- migration 006 幂等。

全量测试必须通过，测试数应大于 v2 的 `321`。

## 验收标准

v2.1 通过必须同时满足：

- 全量测试通过。
- QualityHub 可独立运行。
- Polisher 可配置启用 HumanizerSkill。
- Editor 可配置启用 AIStyleDetectorSkill。
- fact_lock 仍是硬门禁，没有被 Skill 绕过。
- 每章质量报告可保存和查询。
- Skill 配置可启用/禁用。
- CLI 可查看和运行 Skill。
- 不引入 v2.1 禁止范围能力。

## 给开发 Agent 的执行顺序

建议按以下顺序开发：

1. 新增 `skills.yaml`。
2. 新增 Skill 基类和 Registry。
3. 实现 AIStyleDetectorSkill。
4. 实现 HumanizerZhSkill。
5. 实现 NarrativeQualityScorer。
6. 新增 QualityHub。
7. 新增 006 migration 和 Repository 方法。
8. Polisher 接入 Humanizer + AIStyleDetector。
9. Editor 接入 AIStyleDetector + NarrativeQualityScorer。
10. 新增 CLI。
11. 补齐测试。
12. 全量测试和真实 CLI 验证。

## 非目标

以下内容不要在 v2.1 做：

- Web UI。
- REST API。
- 多模型 fallback。
- token 成本统计。
- Agent 级模型路由。
- 外部 Skill 热加载。
- 从网络下载 Skill。
- 自动修改 prompt / 规则 / schema。

