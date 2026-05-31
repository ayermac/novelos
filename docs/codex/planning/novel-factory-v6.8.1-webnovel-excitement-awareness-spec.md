# v6.8.1 — Webnovel Excitement Awareness

**Status**: Planned
**Date**: 2026-05-30
**Previous**: v6.8.0 Skillized Quality Gates

---

## 1. Problem Statement

系统把所有小说都当作"严肃文学"处理，没有"爽文"感知能力。导致：

- **开局无钩子**：第一章花大量篇幅铺陈压抑，没有在前 200 字抓住读者
- **爽点权重太低**：Editor 爽点维度只占 15/100 分，通过决策中爽点不足不影响通过
- **无风格检测**：即使项目描述包含"逆袭"、"打脸"等爽文关键词，系统也不会调整生成策略
- **无开局钩子检查**：只检查 `ending_hook`（章末钩子），不检查开局吸引力
- **无爽点分布检测**：只检查章末悬念，不检查全文爽点密度

**根因**：系统缺乏"风格感知"层 — 不区分爽文和严肃文学，所有 prompt 和 quality gate 使用同一套策略。

## 2. Goal

为系统增加"风格感知"能力，让生成策略和质量检查根据小说风格（爽文/严肃文学/悬疑等）自动调整。

### Non-Goals

- **不重写 LLM prompt** — 在现有 prompt 基础上注入风格指令，不替换
- **不改变 Skill manifest 架构** — 使用现有 Skill 体系
- **不针对特定小说** — 通用风格检测，不硬编码

## 3. Architecture

### 3.1 Style Detection Layer

**新增模块**: `novel_factory/quality/style_detector.py`

从项目元数据（title、premise、genre、world_settings）自动检测风格标签：

```python
@dataclass
class StyleProfile:
    primary_style: str  # "webnovel_excitement" | "serious_literature" | "suspense" | "romance" | "general"
    excitement_level: str  # "high" | "medium" | "low"
    opening_hook_required: bool
    excitement_density_target: str  # "every_500_chars" | "every_1000_chars" | "chapter_end_only"
    pacing_preference: str  # "fast" | "moderate" | "slow"
    keywords_detected: list[str]  # ["逆袭", "打脸", "金手指"]
```

**检测规则**（纯确定性，无 LLM）：
- 逆袭/打脸/金手指/开局/爽文/升级/碾压 → `webnovel_excitement`, `high`
- 悬疑/推理/烧脑/反转 → `suspense`, `medium`
- 爱情/恋爱/甜宠/虐恋 → `romance`, `medium`
- 其他 → `general`, `low`

**调用时机**：
- Genesis 阶段：首次检测，存入 project metadata
- Planner 阶段：读取 style profile，注入 prompt
- Screenwriter/Author/Editor：读取 style profile，调整策略

### 3.2 Style-Aware Prompt Injection

**修改模块**: `novel_factory/agents/planner.py`, `screenwriter.py`, `author.py`

在现有 prompt 末尾注入风格指令：

**Planner prompt 注入**（当 `style.excitement_level == "high"`）：
```
【风格指令 — 爽文】
- 开局必须在前 200 字内建立"逆袭预期"：让读者看到主角的潜力、资源或机遇
- 压抑阶段不超过全章 30%，必须穿插"小爽点"（被认可、小胜利、技能展示）
- 章末钩子必须指向"即将翻盘"而非"更多压抑"
- 每章至少一个"打脸"或"逆袭"爽点
```

**Screenwriter prompt 注入**（当 `style.excitement_level == "high"`）：
```
【风格指令 — 爽文节奏】
- 第一个 beat 必须包含"钩子"或"逆袭预期"
- 每 2 个 beat 至少有一个"爽点 beat"（打脸/认可/胜利/技能展示）
- 压抑 beat 和爽点 beat 交替，避免连续 3 个压抑 beat
```

**Author prompt 注入**（当 `style.excitement_level == "high"`）：
```
【风格指令 — 爽文写作】
- 开局 200 字必须有"钩子"：悬念、冲突、或暗示即将发生的事
- 压抑段落必须穿插"微爽点"：角色的小机智、小胜利、被认可
- 避免连续 500 字以上的纯压抑叙述
- 打脸场景要写得"爽"：对比鲜明、反应夸张、旁观者震惊
```

### 3.3 Opening Hook Checker Skill

**新增 Skill**: `opening-hook-checker`

**输入**: `{content, style_profile}`
**检查**:
- 前 200 字是否包含：悬念、冲突、反转、金手指暗示、逆袭预期
- 前 200 字是否全是压抑铺陈（无钩子）
- 开局是否有"钩子句"（最后一句引发好奇）

**输出**: `{passed, hook_type, hook_strength, issues}`

**挂载**: `editor.before_review`, `author.after_llm`

### 3.4 Excitement Density Checker Skill

**新增 Skill**: `excitement-density-checker`

**输入**: `{content, style_profile}`
**检查**:
- 全文爽点分布（每 500/1000 字是否有爽点）
- 压抑段落占比（不超过 style 定义的阈值）
- 爽点类型分布（打脸/认可/胜利/技能展示是否多样）

**输出**: `{passed, density_score, excitement_map, issues}`

**挂载**: `editor.before_review`

### 3.5 Editor Excitement Weight Adjustment

**修改模块**: `novel_factory/agents/editor.py`

根据 `style_profile.excitement_level` 动态调整 Editor 评分权重：

| 维度 | 默认权重 | 爽文权重 |
|------|---------|---------|
| 设定一致性 | 25 | 20 |
| 逻辑漏洞 | 25 | 20 |
| 毒点检测 | 20 | 15 |
| 文字质量 | 15 | 15 |
| 爽点钩子 | 15 | **30** |

爽文模式下，爽点权重从 15% 提升到 30%。

### 3.6 Genesis Style Detection

**修改模块**: `novel_factory/quality/genesis_quality_gate.py`

在 genesis 阶段自动检测风格并存入 project metadata：

```python
def detect_style_from_genesis(genesis_content: str, title: str, genre: str) -> StyleProfile:
    """从创世草案检测风格标签。"""
    text = f"{title} {genre} {genesis_content}"
    # 检测爽文关键词
    excitement_keywords = ["逆袭", "打脸", "金手指", "升级", "碾压", "爽文", "开局"]
    found = [kw for kw in excitement_keywords if kw in text]
    if found:
        return StyleProfile(
            primary_style="webnovel_excitement",
            excitement_level="high",
            opening_hook_required=True,
            excitement_density_target="every_500_chars",
            pacing_preference="fast",
            keywords_detected=found,
        )
    # ... 其他风格检测
```

## 4. Skills to Create

| Skill | 类型 | 挂载 | 优先级 |
|-------|------|------|--------|
| `opening-hook-checker` | validator | editor.before_review, author.after_llm | P1 |
| `excitement-density-checker` | validator | editor.before_review | P2 |

## 5. Files to Modify

| 文件 | 改动 |
|------|------|
| `novel_factory/quality/style_detector.py` | NEW — 风格检测模块 |
| `novel_factory/agents/planner.py` | 注入风格指令到 prompt |
| `novel_factory/agents/screenwriter.py` | 注入风格指令到 prompt |
| `novel_factory/agents/author.py` | 注入风格指令到 prompt |
| `novel_factory/agents/editor.py` | 动态调整评分权重 |
| `novel_factory/quality/genesis_quality_gate.py` | 创世阶段风格检测 |
| `novel_factory/skills/opening_hook_checker.py` | NEW — 开局钩子检查 |
| `novel_factory/skills/excitement_density_checker.py` | NEW — 爽点密度检查 |
| `novel_factory/config/skills/manifest/opening-hook-checker.yaml` | NEW |
| `novel_factory/config/skills/manifest/excitement-density-checker.yaml` | NEW |
| `novel_factory/skills/base.py` | 注册新 Skills |
| `novel_factory/config/skills.yaml` | 注册新 Skills |

## 6. Testing Strategy

| 测试 | 覆盖 |
|------|------|
| `tests/test_v681_style_detector.py` | 风格检测：逆袭/打脸/悬疑/爱情/通用 |
| `tests/test_v681_opening_hook.py` | 开局钩子：有钩子通过、无钩子失败、压抑开局失败 |
| `tests/test_v681_excitement_density.py` | 爽点密度：分布合理通过、连续压抑失败 |
| `tests/test_v681_editor_weight.py` | Editor 权重：爽文模式下爽点权重 30 |

## 7. Acceptance Criteria

| # | 标准 |
|---|------|
| 1 | 系统能从项目描述自动检测"逆袭"风格 |
| 2 | 检测到爽文风格后，Planner/Screenwriter/Author prompt 自动注入爽文指令 |
| 3 | 爽文模式下 Editor 爽点权重从 15 提升到 30 |
| 4 | 开局钩子检查器能检测前 200 字是否有钩子 |
| 5 | 爽点密度检查器能检测全文爽点分布 |
| 6 | 所有检查都是确定性（无 LLM），遵循 Skill manifest 约束 |
| 7 | 不影响非爽文小说的生成流程 |
| 8 | 全量测试通过 |
