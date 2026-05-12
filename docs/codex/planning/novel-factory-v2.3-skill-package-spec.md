# v2.3 Skill Package 化开发规范

## Summary

v2.3 的目标是把 v2.2 的 manifest + Python class 形态，升级为更易维护的 Skill Package 结构。

v2.2 已经完成：

- Skill manifest。
- 权限声明。
- 输入输出 schema。
- 适用 Agent / Stage 校验。
- `skills show`。
- `skills validate`。

v2.3 不做外部热加载，不做 marketplace，不做沙箱。它只把仓库内内置 Skill 整理成目录包，让每个 Skill 拥有自己的 manifest、handler、prompts、rules 和 fixtures。

## Current Baseline

当前基线：

- v2.2 已通过验收。
- 全量测试基线为 `409/409`。
- v2.3 开发必须保证旧测试不回归，新增测试后总数必须大于 `409`。

## Goals

v2.3 要完成：

- 定义 Skill Package 目录规范。
- 将 3 个内置 Skill 迁移或镜像为 package。
- SkillRegistry 支持从 package 加载 manifest 和 handler。
- 保持 v2.2 manifest 兼容。
- 为 Skill 增加自测 fixtures。
- 新增 Skill 自测 CLI。
- 不破坏 v2.1/v2.2 的 `novelos skills ...` 命令。

## Non Goals

v2.3 不做：

- 外部目录扫描。
- 任意 import path 加载。
- 网络下载 Skill。
- Skill marketplace。
- 沙箱执行。
- 全 Agent 通用挂载点扩展。
- Web UI / Web API。
- 多模型 fallback。

## Package Structure

建议新增目录：

```text
novel_factory/skill_packages/
  humanizer_zh/
    manifest.yaml
    handler.py
    prompts/
      system.md
      rewrite.md
    rules/
      replacements.yaml
      protected_patterns.yaml
    tests/
      fixtures.yaml
    README.md
  ai_style_detector/
    manifest.yaml
    handler.py
    rules/
      ai_patterns.yaml
    tests/
      fixtures.yaml
    README.md
  narrative_quality/
    manifest.yaml
    handler.py
    rules/
      scoring_rules.yaml
    tests/
      fixtures.yaml
    README.md
```

目录名建议使用 Python package 兼容命名，例如：

- `humanizer_zh`
- `ai_style_detector`
- `narrative_quality`

Skill ID 仍保持：

- `humanizer-zh`
- `ai-style-detector`
- `narrative-quality`

## Manifest Changes

v2.3 manifest 在 v2.2 基础上新增 package 字段：

```yaml
package:
  name: humanizer_zh
  handler: handler.py
  entry_class: HumanizerZhSkill
  prompts_dir: prompts
  rules_dir: rules
  fixtures: tests/fixtures.yaml
```

要求：

- 旧 v2.2 manifest 仍可加载。
- 如果 manifest 包含 `package` 字段，Registry 优先从 package 加载。
- 如果没有 `package` 字段，走 v2.2 兼容路径。
- handler 必须仍然在仓库内白名单包下。
- 不允许 manifest 指向仓库外路径。

## Handler Requirements

每个 package 的 `handler.py` 必须：

- 导出对应 Skill class。
- 继承 v2.1/v2.2 的 Skill 基类。
- 保持 `run(payload) -> {ok, error, data}` envelope。
- 不直接写章节内容。
- 不直接更新章节状态。
- 不直接调用网络。
- 不直接调用 LLM。

v2.3 可以复用原有实现，避免大规模重写。

允许方式：

```python
from novel_factory.skills.humanizer_zh import HumanizerZhSkill
```

或者把实现迁入 package handler。

推荐渐进迁移：

1. 先让 package handler re-export 原有 class。
2. 测试通过后，再逐步把 rules/prompts 外置。

## Rules and Prompts

v2.3 的重点是形成结构，不要求重写算法。

最低要求：

- `humanizer_zh/rules/replacements.yaml` 包含至少一组替换规则。
- `humanizer_zh/rules/protected_patterns.yaml` 包含事实保护模式说明。
- `ai_style_detector/rules/ai_patterns.yaml` 包含模板句、连接词、空泛情绪等规则。
- `narrative_quality/rules/scoring_rules.yaml` 包含评分维度和阈值。

Prompt 文件可以先作为文档化资源，不要求当前 handler 读取。

## Fixtures

每个 Skill package 必须有 `tests/fixtures.yaml`。

建议结构：

```yaml
cases:
  - name: simple_case
    input:
      text: "然而，这是一个测试。"
    expect:
      ok: true
      contains:
        - humanized_text
```

fixtures 用于 Skill 自测 CLI。

## SkillRegistry Behavior

SkillRegistry 必须支持：

- 从 package manifest 加载 Skill。
- 校验 package path 在仓库允许目录内。
- 校验 handler 文件存在。
- 校验 fixtures 文件存在。
- `list_skills()` 返回 package 信息。
- `skills show` 输出 package 信息。
- `skills validate` 校验 package 结构。
- `run_skill()` 对 package skill 保持 v2.2 权限校验。

不允许：

- 从绝对路径加载 package。
- 从 `../` 路径逃逸。
- 从网络加载 package。
- 从任意 import path 加载非白名单 handler。

## skills.yaml

v2.3 推荐：

```yaml
skills:
  humanizer-zh:
    enabled: true
    package: skill_packages/humanizer_zh
    config:
      preserve_facts: true
```

兼容要求：

- `manifest: config/skills/manifest/...` 仍可用。
- 如果同时存在 `package` 和 `manifest`，优先 `package/manifest.yaml`。
- 旧 v2.2 CLI 不回归。

## CLI

保留：

```bash
novelos skills list --json
novelos skills show humanizer-zh --json
novelos skills validate --json
novelos skills run humanizer-zh --text "..." --json
```

新增：

```bash
novelos skills test humanizer-zh --json
novelos skills test --all --json
```

要求：

- `skills test humanizer-zh` 读取该 package 的 fixtures。
- `skills test --all` 跑所有 package fixtures。
- JSON 输出统一 `{ok, error, data}`。
- fixture 失败时 exit code 非 0。
- unknown skill exit code 非 0。

## Tests

新增测试文件建议：

- `tests/test_skill_package.py`
- `tests/test_skill_package_registry.py`
- `tests/test_v2_3_cli.py`

必须覆盖：

- 3 个内置 Skill package 目录存在。
- 每个 package 有 `manifest.yaml`。
- 每个 package 有 `handler.py`。
- 每个 package 有 fixtures。
- Registry 可从 package 读取 manifest。
- package path 不允许 `../` 逃逸。
- `skills validate --json` 校验 package 结构。
- `skills show humanizer-zh --json` 包含 package 字段。
- `skills run humanizer-zh --text ... --json` 仍可用。
- `skills test humanizer-zh --json` 可运行。
- `skills test --all --json` 可运行。
- fixture 失败时返回非 0。
- 旧 v2.2 tests 保持通过。

测试数量必须大于 `409`。

## Acceptance

v2.3 通过必须同时满足：

- 全量测试通过。
- 测试数量大于 `409`。
- 3 个内置 Skill 都有 package。
- package manifest 可校验。
- package fixtures 可运行。
- `skills test` CLI 可用。
- `skills show` 展示 package metadata。
- `skills validate` 校验 package 结构。
- 旧 v2.1/v2.2 CLI 仍可运行。
- 不引入 v2.3 禁止范围能力。

## Implementation Order

建议顺序：

1. 新增 `skill_packages/` 目录。
2. 为 3 个内置 Skill 建 package 骨架。
3. 复制或迁移 manifest 到 package 内。
4. 新增 handler re-export 原有 Skill class。
5. 新增 rules/prompts/fixtures。
6. 改造 SkillRegistry 支持 `package` 字段。
7. 改造 CLI `skills test`。
8. 补测试。
9. 跑全量测试。

## Forbidden Scope

以下内容不要在 v2.3 做：

- 外部 Skill 热加载。
- 任意目录扫描。
- 任意 import path。
- marketplace。
- 沙箱执行。
- 所有 Agent 通用挂载。
- Web UI / FastAPI。
- 多模型 fallback。
- Redis / Celery / Kafka。
- PostgreSQL。
