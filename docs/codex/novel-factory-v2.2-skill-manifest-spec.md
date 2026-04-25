# v2.2 Skill Manifest 化开发规范

## Summary

v2.2 的目标是把 v2.1 的内置 Python Skill 升级为带有 manifest 契约的能力单元。

v2.1 已经完成：

- `QualityHub`
- `SkillRegistry`
- `HumanizerZhSkill`
- `AIStyleDetectorSkill`
- `NarrativeQualityScorer`
- `quality_reports`
- `skill_runs`
- `novelos skills ...`
- `novelos quality ...`

v2.2 不继续扩展质量算法本身，而是补齐 Skill 的元数据、权限、schema、适用 Agent、适用阶段和失败策略，让后续 v2.3 Skill Package 化、v2.4 通用 Agent Skill Registry 有稳定基础。

## Current Baseline

当前基线：

- v2.1 已通过验收。
- 全量测试基线为 `359/359`。
- v2.2 开发必须保证旧测试不回归，新增测试后总数必须大于 `359`。

## Goals

v2.2 要完成：

- 新增 Skill manifest 数据模型。
- 为所有内置 Skill 提供 manifest。
- SkillRegistry 支持读取、校验和展示 manifest。
- manifest 声明 Skill 的输入、输出、配置、权限、适用 Agent 和阶段。
- Agent 执行 Skill 前校验 manifest 权限和挂载阶段。
- CLI 可查看 manifest 详情。
- 保持 v2.1 的 `skills.yaml` 兼容。

## Non Goals

v2.2 不做：

- 外部 Skill 热加载。
- 网络下载 Skill。
- Skill marketplace。
- 沙箱执行。
- Skill 包目录结构强制迁移。
- 所有 Agent 的完整通用 Skill 挂载。
- 多模型 Provider fallback。
- Web UI / Web API。

## Key Principle

v2.2 的核心不是“让 Skill 更自由”，而是“让 Skill 更可控”。

manifest 必须回答这些问题：

- 这个 Skill 是谁？
- 它能在哪些 Agent 和阶段运行？
- 它需要什么输入？
- 它会产生什么输出？
- 它允许做什么副作用？
- 失败时是否阻断流程？
- 它的配置项是否合法？

## Proposed Files

新增或修改：

- `novel_factory/models/skill_manifest.py`
- `novel_factory/skills/manifest.py`
- `novel_factory/skills/registry.py`
- `novel_factory/config/skills.yaml`
- `novel_factory/config/skills/manifest/humanizer-zh.yaml`
- `novel_factory/config/skills/manifest/ai-style-detector.yaml`
- `novel_factory/config/skills/manifest/narrative-quality.yaml`
- `novel_factory/cli.py`
- `tests/test_skill_manifest.py`
- `tests/test_skill_permissions.py`
- `tests/test_v2_2_cli.py`

如果实现者认为目录名需要调整，可以调整，但必须保持含义清晰。

## Manifest Schema

新增 `SkillManifest` Pydantic 模型。

建议字段：

```python
class SkillManifest(BaseModel):
    id: str
    name: str
    version: str
    kind: Literal["transform", "validator", "context", "report"]
    class_name: str
    module: str | None = None
    description: str = ""
    enabled: bool = True
    builtin: bool = True
    allowed_agents: list[str]
    allowed_stages: list[str]
    permissions: SkillPermissions
    input_schema: dict
    output_schema: dict
    config_schema: dict
    default_config: dict = {}
    failure_policy: FailurePolicy
```

权限模型：

```python
class SkillPermissions(BaseModel):
    read_context: bool = False
    read_chapter: bool = False
    transform_text: bool = False
    validate_text: bool = False
    write_quality_report: bool = False
    write_skill_run: bool = True
    write_chapter_content: bool = False
    update_chapter_status: bool = False
    send_agent_message: bool = False
    call_llm: bool = False
    call_network: bool = False
```

失败策略：

```python
class FailurePolicy(BaseModel):
    on_error: Literal["block", "warn", "skip"]
    max_retries: int = 0
    timeout_seconds: int | None = None
    blocking_threshold: float | None = None
```

v2.2 必须默认禁止：

- `write_chapter_content`
- `update_chapter_status`
- `call_network`

除非 manifest 显式声明且 SkillRegistry 允许。

## Built-in Manifest Requirements

### humanizer-zh

要求：

- `kind: transform`
- `allowed_agents: ["polisher"]`
- `allowed_stages: ["after_llm"]`
- `permissions.transform_text: true`
- `permissions.write_skill_run: true`
- `permissions.write_chapter_content: false`
- `failure_policy.on_error: "block"`

输入 schema 至少包含：

- `text`
- `fact_lock`

输出 schema 至少包含：

- `humanized_text`
- `changes`
- `risk_level`

### ai-style-detector

要求：

- `kind: validator`
- `allowed_agents: ["polisher", "editor", "qualityhub"]`
- `allowed_stages: ["before_save", "before_review", "final_gate", "manual"]`
- `permissions.validate_text: true`
- `failure_policy.on_error: "block"` when used by Polisher
- 可在 manifest 默认策略中写 `block`，后续 v2.4 再做 per-agent override。

输入 schema 至少包含：

- `text`
- `content`

输出 schema 至少包含：

- `ai_trace_score`
- `risk_level`
- `blocking`
- `issues`
- `suggestions`

### narrative-quality

要求：

- `kind: validator`
- `allowed_agents: ["editor", "qualityhub"]`
- `allowed_stages: ["before_review", "final_gate", "manual"]`
- `permissions.validate_text: true`
- `failure_policy.on_error: "block"`

输入 schema 至少包含：

- `text`

输出 schema 至少包含：

- `scores`
- `issues`
- `suggestions`
- `grade`

## Registry Behavior

SkillRegistry 必须支持：

- 加载 manifest。
- 校验 manifest 字段。
- 校验 class 在白名单内。
- 校验 `skills.yaml` 中配置的 skill id 是否有 manifest。
- 校验 agent/stage 是否被 manifest 允许。
- 校验 disabled skill 不执行。
- 提供 `get_manifest(skill_id)`。
- `list_skills()` 返回 manifest 摘要。
- `run_skill()` 执行前做 manifest 校验。
- `run_skills_for_agent()` 过滤不允许的 agent/stage。

建议新增错误：

- `SkillManifestError`
- `SkillPermissionError`
- `SkillStageNotAllowedError`

错误必须返回 JSON envelope，而不是抛到 CLI 顶层。

## Compatibility with skills.yaml

v2.1 的 `skills.yaml` 不能直接废弃。

v2.2 兼容策略：

```yaml
skills:
  humanizer-zh:
    enabled: true
    manifest: config/skills/manifest/humanizer-zh.yaml
    config:
      preserve_facts: true

agent_skills:
  polisher:
    after_llm:
      - humanizer-zh
```

允许短期兼容旧字段：

```yaml
class: HumanizerZhSkill
type: transform
```

但如果同时存在 manifest，以 manifest 为准。

## CLI

保留 v2.1 命令：

```bash
novelos skills list --json
novelos skills run humanizer-zh --text "..." --json
```

新增：

```bash
novelos skills show humanizer-zh --json
novelos skills validate --json
```

要求：

- `skills show` 输出完整 manifest。
- `skills validate` 校验全部 manifest 和 `skills.yaml` 的一致性。
- JSON 输出统一 `{ok, error, data}`。
- unknown skill 返回非 0 exit code。
- manifest 不合法返回非 0 exit code。

## Permission Rules

v2.2 必须硬性保证：

- Transform skill 不能更新章节状态。
- Validator skill 不能改正文。
- Report skill 不能改章节正文。
- Context skill 不能写数据库，除非 manifest 明确允许。
- 所有 Skill 默认不能调用网络。
- 所有 Skill 默认不能调用 LLM。

如果 Skill 实现试图做权限外操作，v2.2 可以先通过执行前约束阻止，不要求完整运行时沙箱。

最低要求：

- Registry 不允许未授权 agent/stage 执行 Skill。
- Registry 不允许未授权 kind 写入不该写的内容。
- Agent 不得绕过 Registry 直接执行 Skill。

## Agent Integration

v2.2 不要求所有 Agent 全面 Skill 化。

必须保证：

- Polisher 执行 Skill 前校验 manifest。
- Editor 执行 Skill 前校验 manifest。
- QualityHub 执行 Skill 前校验 manifest。
- 手动 CLI `skills run` 使用 `manual` stage。

如果 manifest 不允许：

- 返回 `ok=false`。
- 写入 skill_runs 失败记录。
- 不推进章节状态。

## Database

v2.2 不强制新增 migration。

如果需要记录 manifest 版本，可新增字段或扩展 `skill_runs.output_json`。

最低要求：

- `skill_runs` 记录 `manifest_version` 或在 `output_json` 中包含 manifest metadata。
- 不破坏 v2.1 migration。

## Tests

新增测试文件建议：

- `tests/test_skill_manifest.py`
- `tests/test_skill_permissions.py`
- `tests/test_v2_2_cli.py`

必须覆盖：

- manifest 文件可加载。
- manifest 必填字段缺失时报错。
- unknown manifest skill 报清晰错误。
- disabled skill 不执行。
- agent/stage 不允许时拒绝执行。
- Polisher 只能执行 allowed stage 的 humanizer。
- Editor 不能执行只允许 Polisher 的 humanizer。
- CLI `skills show humanizer-zh --json`。
- CLI `skills validate --json`。
- `skills run humanizer-zh --text ... --json` 仍可用。
- `skills run` 不允许未声明 manual stage 的 Skill。
- 旧 v2.1 tests 保持通过。

测试数量必须大于 `359`。

## Acceptance

v2.2 通过必须同时满足：

- 全量测试通过。
- 新增 v2.2 专项测试。
- 所有内置 Skill 有 manifest。
- manifest 校验可运行。
- `skills show` 可显示 manifest。
- `skills validate` 可校验全部 manifest。
- Polisher / Editor / QualityHub 执行 Skill 前校验 agent/stage 权限。
- 未授权 Skill 不得执行。
- 旧 v2.1 CLI 仍可运行。
- 不引入 v2.2 禁止范围能力。

## Implementation Order

建议顺序：

1. 新增 `SkillManifest` / `SkillPermissions` / `FailurePolicy` 模型。
2. 新增 manifest 加载器。
3. 为三个内置 Skill 编写 manifest。
4. 改造 `skills.yaml`，指向 manifest。
5. 改造 SkillRegistry。
6. 接入 Polisher / Editor / QualityHub。
7. 新增 `skills show` / `skills validate`。
8. 补测试。
9. 跑全量测试。

## Forbidden Scope

以下内容不要在 v2.2 做：

- 外部 Skill 目录扫描。
- 任意 import path 加载。
- 网络 Skill 下载。
- Skill marketplace。
- 沙箱执行器。
- Web UI。
- FastAPI。
- 多模型 fallback。
- Redis / Celery / Kafka。
- PostgreSQL。
- 大规模重写现有 Agent。
