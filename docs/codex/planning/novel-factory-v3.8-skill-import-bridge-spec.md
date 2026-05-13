# v3.8 Skill Import Bridge 开发规范

## Summary

v3.8 的目标是在 v2.1-v2.3 已有 Skill 系统之上，新增一个安全的“外部 Agent Skill 导入桥”。

它解决的问题是：

- skills.sh / Codex / Claude Code / Cursor 等生态里有大量 `SKILL.md` 形式的 Agent Skill。
- 这些 Skill 对开发 Agent 很有用，但不能直接作为 novel_factory 运行时 Skill 执行。
- novel_factory 当前运行时 Skill 需要 manifest、handler、权限、fixtures 和 package 化结构。

v3.8 不做外部 Skill 热加载，也不允许任意远程代码执行。它只做“导入、转换、校验、生成草案包”，让外部 Skill 先变成项目内受控的 Skill Package，再由人工 review 后启用。

核心流程：

```text
skills import-source -> 读取本地 skills.sh/Codex Skill 目录
skills import-plan   -> 生成转换计划，不写入运行时配置
skills import-apply  -> 生成 novel_factory/skill_packages/<id> 草案
skills validate      -> 校验 manifest / handler / fixtures
skills test          -> 运行 fixtures
人工 review          -> 手动决定是否挂载到 agents/stages
```

## Why Now

v2.1-v2.3 已经实现：

- SkillRegistry。
- Skill Manifest。
- Skill Package。
- handler / rules / prompts / fixtures。
- `skills validate` / `skills test`。

但这些能力只服务于项目内置 Skill。用户现在希望把 skills.sh 上的 Skill 复用到小说工厂中，尤其是：

- AI 去味。
- 风格检查。
- 内容审核。
- 写作提示。
- 安全扫描。
- 文档导出。

直接运行外部 Skill 风险太高。v3.8 的目标是提供一条受控转换路径。

## Goals

v3.8 必须实现：

- 读取本地外部 Skill 目录。
- 识别 `SKILL.md` frontmatter。
- 提取 skill name / description。
- 识别 `scripts/`、`references/`、`assets/`、`rules/`、`prompts/` 等资源。
- 生成 import plan。
- 生成 novel_factory Skill Package 草案。
- 生成 manifest 草案。
- 生成 handler stub。
- 生成 fixtures stub。
- 默认不自动挂载到任何 Agent。
- 默认不启用 imported Skill。
- 支持 dry-run。
- 支持 JSON envelope。
- 支持安全校验报告。

## Non-Goals

v3.8 不做：

- 从 skills.sh 直接联网下载。
- 调用 `npx skills add`。
- 任意 GitHub repo clone。
- 外部 Skill 热加载。
- 外部脚本自动执行。
- marketplace。
- 沙箱执行器。
- 自动启用 imported Skill。
- 自动挂载到 Polisher / Editor / Author。
- 自动修改 `skills.yaml` 的 agent_skills。
- Web UI / FastAPI。
- Redis / Celery / Kafka。
- PostgreSQL。

如需联网下载或 marketplace，必须另开 v4+ 版本，并先完成安全模型。

## Source Skill Shape

v3.8 支持本地目录输入：

```text
some-skill/
├── SKILL.md
├── scripts/
├── references/
├── assets/
├── rules/
├── prompts/
└── examples/
```

最小要求：

```text
some-skill/
└── SKILL.md
```

`SKILL.md` 必须包含 YAML frontmatter：

```yaml
---
name: humanizer-zh
description: 去除中文文本中的 AI 味...
---
```

## Target Package Shape

导入后生成：

```text
novel_factory/skill_packages/<skill_id>/
├── manifest.yaml
├── handler.py
├── prompts/
│   └── imported_skill.md
├── references/
│   └── ...
├── rules/
│   └── ...
├── tests/
│   └── fixtures.yaml
└── README.md
```

### manifest.yaml

必须包含：

```yaml
id: imported-humanizer-zh
name: Imported Humanizer ZH
version: 0.1.0
kind: imported_instruction
class_name: ImportedInstructionSkill
package:
  source: local
  imported_from: /absolute/path/to/source
  imported_at: "2026-04-25T00:00:00"
permissions:
  transform_text: false
  validate_text: false
  read_context: true
  write_files: false
allowed_agents:
  - manual
allowed_stages:
  - manual
failure_policy:
  block_on_error: false
  retry_count: 0
```

默认策略：

- `allowed_agents: ["manual"]`
- `allowed_stages: ["manual"]`
- 所有危险权限默认 `false`
- 不进入主生产链路

### handler.py

默认生成只读 instruction handler：

```python
class ImportedInstructionSkill(ContextSkill):
    ...
```

它可以返回：

- skill instructions。
- prompt fragments。
- references summary。

不得默认执行外部 scripts。

## Import Modes

### 1. instruction-only

适用于只有 `SKILL.md` 的 Skill。

转换：

- `SKILL.md` body -> `prompts/imported_skill.md`
- frontmatter -> `manifest.yaml`
- handler -> `ImportedInstructionSkill`
- fixtures -> empty smoke fixture

### 2. prompt-pack

适用于含 prompts / references 的 Skill。

转换：

- `prompts/` 原样复制。
- `references/` 原样复制。
- `SKILL.md` body 作为主 prompt。
- handler 返回 prompt/context。

### 3. rule-pack

适用于含 rules 的 Skill。

转换：

- `rules/` 原样复制。
- handler stub 不自动解释规则。
- 生成 TODO 提示：需人工实现规则解析。

### 4. script-pack

适用于含 scripts 的 Skill。

v3.8 只复制 scripts，不执行 scripts。

manifest 中必须标记：

```yaml
has_scripts: true
scripts_enabled: false
```

CLI 必须输出 warning：

```text
Imported skill contains scripts. Scripts are copied but disabled.
```

## CLI Design

新增命令：

```bash
novelos skills import-plan --source /path/to/skill --json
novelos skills import-apply --source /path/to/skill --skill-id imported-humanizer --json
novelos skills import-validate --skill-id imported-humanizer --json
```

### skills import-plan

只读取，不写文件。

返回：

```json
{
  "ok": true,
  "error": null,
  "data": {
    "source": "/path/to/skill",
    "detected": {
      "name": "humanizer-zh",
      "description": "...",
      "has_scripts": false,
      "has_references": true,
      "has_assets": false
    },
    "target": {
      "skill_id": "imported-humanizer-zh",
      "kind": "imported_instruction"
    },
    "warnings": []
  }
}
```

### skills import-apply

生成 package 草案。

要求：

- 目标目录已存在时失败，除非 `--force`。
- 默认不修改 `skills.yaml`。
- 默认不挂载到任何 Agent。
- 写入 manifest / handler / fixtures 后，自动调用 Registry validate。

### skills import-validate

校验 imported package：

- manifest 合法。
- handler 可加载。
- handler 是 BaseSkill 子类。
- fixtures 存在。
- scripts disabled。
- 不含路径逃逸。

## Security Rules

必须阻断：

- source 不存在。
- source 不是目录。
- 缺少 `SKILL.md`。
- `SKILL.md` 无 frontmatter。
- skill id 非法。
- 目标路径逃逸 `../`。
- 绝对路径写入 package root 之外。
- symlink 指向 package root 外部。
- scripts 自动执行。
- manifest 请求非 manual agent/stage。
- imported Skill 默认带 transform/write 权限。

必须 warning：

- source 包含 scripts。
- source 包含大文件。
- source 包含二进制 assets。
- source 描述过长。
- 没有 fixtures。

## Registry Integration

v3.8 不改变 v2.3 的核心安全边界：

- Registry 仍只能从 `novel_factory/skill_packages/` 加载 package。
- 配置了 package 的 Skill 必须从 package handler 加载。
- package handler 加载失败不得 fallback legacy class。
- 外部 source 不参与运行时加载。

导入后的 Skill 只有在以下条件都满足时才能运行：

1. package 已生成到 `novel_factory/skill_packages/<id>`。
2. manifest validate 通过。
3. handler validate 通过。
4. fixtures test 通过。
5. 人工修改 `skills.yaml` 或明确配置后才进入 agent stage。

## Data / Migration

v3.8 默认不新增数据库 migration。

import history 不落库，写入 package manifest：

```yaml
import:
  source_type: local_directory
  source_path: /absolute/path
  imported_at: "..."
  importer_version: "v3.8"
```

## Test Plan

新增测试：

```text
tests/test_v38_skill_import_bridge.py
```

必须覆盖：

1. import-plan 读取合法 SKILL.md。
2. import-plan 缺 SKILL.md 返回 envelope。
3. import-plan 无 frontmatter 返回 envelope。
4. import-plan 检测 scripts 并 warning。
5. import-apply 生成 package 目录。
6. import-apply 生成 manifest.yaml。
7. import-apply 生成 handler.py。
8. import-apply 生成 fixtures.yaml。
9. 目标目录已存在且未 `--force` 时失败。
10. `--force` 可覆盖 imported package。
11. 非法 skill id 被拒绝。
12. 路径逃逸被拒绝。
13. symlink escape 被拒绝。
14. generated manifest 默认 manual/manual。
15. generated manifest 默认 scripts disabled。
16. Registry 可 validate imported package。
17. Registry 可 run manual imported skill。
18. imported skill 不会自动挂载到 Polisher/Editor。
19. `skills import-validate` JSON envelope 稳定。
20. 全量测试通过。

## CLI Real Verification

开发完成后必须真实执行：

```bash
tmpdir=$(mktemp -d)
mkdir -p "$tmpdir/demo-skill"
cat > "$tmpdir/demo-skill/SKILL.md" <<'EOF'
---
name: demo-skill
description: Demo imported instruction skill.
---

Use this skill as a read-only instruction.
EOF

python3 -m novel_factory.cli skills import-plan --source "$tmpdir/demo-skill" --json
python3 -m novel_factory.cli skills import-apply --source "$tmpdir/demo-skill" --skill-id imported-demo-skill --json
python3 -m novel_factory.cli skills import-validate --skill-id imported-demo-skill --json
python3 -m novel_factory.cli skills show imported-demo-skill --json
python3 -m novel_factory.cli skills test imported-demo-skill --json
```

所有输出必须：

- 无 traceback。
- 使用 `{ok,error,data}`。
- 不执行 source scripts。

## Acceptance Criteria

v3.8 通过标准：

- 新增专项测试不少于 20 个。
- 全量测试通过。
- 能从本地 Skill 目录生成受控 package 草案。
- 不联网。
- 不执行外部 scripts。
- 不自动挂载到生产 Agent。
- generated package 可被 `skills validate` / `skills test` 检查。
- 所有 JSON 输出稳定 envelope。
- 未引入禁止范围能力。

## Developer Report Template

开发 Agent 完成后必须汇报：

```text
## v3.8 开发汇报

### 修改文件
- ...

### 新增文件
- ...

### 新增 migration
- 无 / 有，说明原因

### 新增 CLI 命令
- ...

### 新增测试
- ...

### 全量测试结果
- ...

### 真实 CLI 验证
- ...

### 是否遵守禁止范围
- ...

### 未完成项或风险
- ...
```

