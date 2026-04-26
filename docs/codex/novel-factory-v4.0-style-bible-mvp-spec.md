# Novel Factory v4.0: Style Bible MVP 规格

## 版本目标

支持项目级 Style Bible，让不同平台/受众使用不同的写作风格配置，并集成到 Agent 上下文和质检流程。

核心约束：
- 不模仿任何作者风格
- 不调用 LLM 做风格检查
- 不联网
- 不自动重写
- 默认不阻塞主生产流
- 所有 CLI 输出使用 `{ok, error, data}` 信封

## 数据模型

### StyleBible（Pydantic）

```python
class StyleBible(BaseModel):
    project_id: str = ""
    name: str = "Default Style Bible"
    genre: str = ""
    target_platform: str = ""
    target_audience: str = ""
    version: str = "1.0.0"

    # 抽象风格维度
    pacing: Pacing = Pacing.BALANCED
    pov: POV = POV.THIRD_PERSON_LIMITED
    emotional_intensity: EmotionalIntensity = EmotionalIntensity.MEDIUM
    tone_keywords: list[str] = []
    prose_style: str = ""
    dialogue_style: str = ""

    # 规则集
    forbidden_expressions: list[ForbiddenExpression] = []
    preferred_expressions: list[PreferredExpression] = []
    ai_trace_avoidance: AITraceAvoidance = AITraceAvoidance()
    sentence_rules: list[StyleRule] = []
    paragraph_rules: list[StyleRule] = []
    chapter_opening_rules: list[StyleRule] = []
    chapter_ending_rules: list[StyleRule] = []
```

### 枚举

- `Pacing`: slow, balanced, fast
- `POV`: first_person, second_person, third_person_limited, third_person_omniscient
- `EmotionalIntensity`: low, medium, high

### 辅助模型

- `ForbiddenExpression(pattern, reason, severity)` — severity: blocking/warning
- `PreferredExpression(pattern, context)`
- `StyleRule(description, severity)` — severity: blocking/warning
- `AITraceAvoidance(avoid_patterns, prefer_patterns)`
- `StyleCheckIssue(rule_type, severity, description, location, suggestion)`
- `StyleCheckReport(total_issues, blocking_issues, warning_issues, issues, score)`

### 核心方法

- `to_storage_dict()` / `from_storage_dict()` — 序列化/反序列化
- `summary_for_context(token_budget)` — 生成摘要
- `rules_for_agent(agent_id)` — 按 agent 返回不同规则子集

## 数据库

### 迁移 012_v4_0_style_bible.sql

```sql
CREATE TABLE IF NOT EXISTS style_bibles (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    genre TEXT,
    target_platform TEXT,
    target_audience TEXT,
    bible_json TEXT NOT NULL DEFAULT '{}',
    version TEXT NOT NULL DEFAULT '1.0.0',
    created_at TEXT NOT NULL DEFAULT (datetime('now', '+8 hours')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    UNIQUE(project_id)
);
```

- `connection.py` 添加 `_is_migration_applied_by_schema()` 对 012 的检测
- `PRAGMA foreign_keys=ON` 已启用

### Repository Mixin

`StyleBibleRepositoryMixin` 提供：
- `save_style_bible(project_id, bible_dict)` → bible_id
- `get_style_bible(project_id)` → dict | None
- `update_style_bible(project_id, bible_dict)` → bool
- `delete_style_bible(project_id)` → bool
- `list_style_bibles()` → list[dict]

写入操作检查 `cursor.rowcount`，失败时 raise。
`save_style_bible` 重复时 raise `ValueError`。

## 模板系统

5 套预设模板（`config/style_bible_templates.yaml`）：

1. `default_web_serial` — 网文默认风格
2. `urban_fantasy_fast` — 都市快节奏
3. `xianxia_progression` — 仙侠升级流
4. `romance_emotional` — 言情情感
5. `mystery_suspense` — 悬疑推理

模板只含抽象风格维度，不含作者参考。

模板操作（`style_bible/templates.py`）：
- `load_style_bible_template(template_id)`
- `list_templates()`
- `create_style_bible_from_template(project_id, template_id, overrides)`
- `validate_style_bible(bible)` — 检查无作者模仿引用
- `merge_style_bible(base, overrides)`

## ContextBuilder 集成

- PRIORITY dict 添加 `'style_bible': 3`（与 plot_verification 同级）
- `_collect_author_fragments()` 添加 `_get_style_bible_context(project_id, 'author')`
- `_collect_editor_fragments()` 添加 `_get_style_bible_context(project_id, 'editor')`
- `_collect_planner_fragments()` 添加 `_get_style_bible_context(project_id, 'planner')`
- `_get_style_bible_context()` 无 Style Bible 时静默返回 None，不影响旧行为
- 所有异常被 try/except 吞掉，永不中断现有流程

## StyleBibleChecker Skill

- 继承 `ValidatorSkill`
- `skill_id = "style-bible-checker"`
- 输入：`text` + `style_bible`（dict）
- 不调 LLM、不联网

检查项：
1. 禁用表达检测（forbidden_expressions）
2. 偏好表达检查（preferred_expressions）
3. 基调关键词（informational only）
4. 长句检测（>80 字无标点断句）
5. 长段落检测（>500 字无空行）
6. 章节开篇/结尾规则
7. AI 味表达检测（ai_trace_avoidance.avoid_patterns）

评分：100 - blocking×10 - warning×3，最低 0

## QualityHub 集成

- `check_draft()` 中在 state_verifier 后运行 `_run_style_bible_check()`
- v4.0 MVP 中 Style Bible blocking issues 仅作为 warning，不阻塞发布
- 结果添加到 `skill_results` 和 `quality_dimensions`

## CLI 命令

| 命令 | 说明 |
|------|------|
| `style templates --json` | 列出可用模板 |
| `style init --project-id ID --template TPL [--set k=v] --json` | 创建 Style Bible |
| `style show --project-id ID --json` | 展示 Style Bible |
| `style update --project-id ID --set k=v --json` | 更新字段 |
| `style check --project-id ID --chapter N --json` | 检查章节风格合规 |
| `style delete --project-id ID --json` | 删除 Style Bible |

`style init` 自动在 projects 表中创建不存在的 project（FK 约束）。

## 测试覆盖

| 测试文件 | 覆盖内容 |
|----------|----------|
| `test_v40_style_bible_models.py` | 模型默认值、序列化、上下文生成、作者引用检查 |
| `test_v40_style_bible_repository.py` | CRUD、FK 约束、rowcount 检查、migration 幂等 |
| `test_v40_style_bible_context.py` | Loader 函数、ContextBuilder 集成 |
| `test_v40_style_bible_skill.py` | 禁用表达检测、AI 味检测、长句/长段落、评分、边界 |
| `test_v40_style_bible_cli.py` | CLI 命令、错误信封、无 traceback、v3.x 回归 |
| `test_file_size_policy.py` | style_bible 目录文件体积策略 |

## 禁止范围

- 不模仿任何作者风格
- 不调用 LLM 做风格检查
- 不联网获取风格规则
- 不自动重写已发布内容
- Style Bible 问题默认不阻塞主生产流（v4.0 MVP）
- 不新增 Web UI / FastAPI
- 不修改主 Agent 编排顺序

## 验收状态

测试基线：**1015 passed, 2 skipped**

- 全量测试通过
- 所有 CLI 输出稳定 `{ok, error, data}` 信封
- Style Bible 成功注入 Planner/Author/Editor 上下文
- QualityHub 检查不阻塞发布
- Repository 写入有 rowcount 检查
- Migration 012 幂等
- 无作者模仿引用
- 无 API key 泄露
