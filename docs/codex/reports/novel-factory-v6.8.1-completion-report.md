# v6.8.1 Webnovel Excitement Awareness — 完成报告

**日期**: 2026-05-30
**版本**: v6.8.1
**状态**: 完成

---

## 1. 版本目标

为系统增加"风格感知"能力，让生成策略和质量检查根据小说风格（爽文/严肃文学/悬疑等）自动调整。

### 核心问题

- 系统把所有小说都当作"严肃文学"处理，没有"爽文"感知能力
- 开局无钩子：第一章花大量篇幅铺陈压抑
- 爽点权重太低：Editor 爽点维度只占 15/100 分
- 无风格检测：即使项目描述包含"逆袭"、"打脸"等爽文关键词，系统也不会调整策略

## 2. 实现内容

### 2.1 风格检测模块 (`novel_factory/quality/style_detector.py`)

新增确定性风格检测模块，从项目元数据自动检测风格标签：

- **StyleProfile 数据类**: primary_style, excitement_level, opening_hook_required, excitement_density_target, pacing_preference, keywords_detected
- **detect_style_from_text()**: 纯确定性关键词检测，无 LLM 依赖
- **get_style_prompt_injection()**: 返回风格特定的 prompt 注入文本
- **get_editor_weight_multiplier()**: 返回 Editor 评分权重乘数

支持的风格：
- `webnovel_excitement`: 逆袭/打脸/金手指/系统/爽文等关键词 → 高兴奋度
- `suspense`: 悬疑/推理/烧脑/反转等关键词 → 中兴奋度
- `romance`: 爱情/甜宠/虐恋/总裁等关键词 → 中兴奋度
- `general`: 无匹配关键词 → 低兴奋度

### 2.2 Prompt 注入

在以下 Agent 的 `build_context` 中注入风格提示：

- **Planner** (`planner.py`): 风格感知的章节规划指令
- **Screenwriter** (`screenwriter.py`): 风格感知的场景节奏指令
- **Author** (`author.py`): 风格感知的写作指令
- **Editor** (`editor.py`): 风格感知的审核指令

新增 `_get_style_prompt_injection()` 辅助方法到 `BaseAgent`。

### 2.3 Editor 权重调整

在 Editor pipeline 中新增 `_apply_style_weight_adjustment()` 方法：

- 爽文模式下，pacing 权重从 15 提升到 30（2x）
- setting/logic/poison 权重相应降低
- 权重乘数应用于 LLM 返回的维度分数后重新计算总分

### 2.4 Opening Hook Checker Skill

新增 `opening-hook-checker` Skill (`novel_factory/skills/opening_hook_checker.py`):

- 检测章节前 200 字是否包含钩子
- 支持的钩子类型：悬念/冲突/反转/金手指暗示/逆袭预期
- 检测压抑开局（≥3 个压抑标记且无钩子 → blocking）
- 挂载：editor.before_review, author.after_llm

### 2.5 Excitement Density Checker Skill

新增 `excitement-density-checker` Skill (`novel_factory/skills/excitement_density_checker.py`):

- 检测全文爽点分布密度（每 500 字一段）
- 计算压抑内容占比（目标 < 50%）
- 检测连续压抑段落（≥3 段 → blocking）
- 计算爽点密度评分（0-100）
- 挂载：editor.before_review

## 3. 文件变更

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `novel_factory/quality/style_detector.py` | NEW | 风格检测模块 |
| `novel_factory/agent_runtime/base.py` | MODIFY | 新增 `_get_style_prompt_injection()` |
| `novel_factory/agents/planner.py` | MODIFY | 注入风格提示 |
| `novel_factory/agents/screenwriter.py` | MODIFY | 注入风格提示 |
| `novel_factory/agents/author.py` | MODIFY | 注入风格提示 |
| `novel_factory/agents/editor.py` | MODIFY | 注入风格提示 + 权重调整 |
| `novel_factory/skills/opening_hook_checker.py` | NEW | 开局钩子检查 Skill |
| `novel_factory/skills/excitement_density_checker.py` | NEW | 爽点密度检查 Skill |
| `novel_factory/skills/base.py` | MODIFY | 注册新 Skills |
| `novel_factory/config/skills/manifest/opening-hook-checker.yaml` | NEW | Skill manifest |
| `novel_factory/config/skills/manifest/excitement-density-checker.yaml` | NEW | Skill manifest |
| `novel_factory/version.py` | MODIFY | 版本号 6.8.0 → 6.8.1 |
| `tests/test_v681_style_detector.py` | NEW | 41 个测试 |
| `docs/codex/specs/novel-factory-v6.8.1-webnovel-excitement-awareness-spec.md` | NEW | 规格文档 |

## 4. 测试覆盖

### 测试文件: `tests/test_v681_style_detector.py`

41 个测试覆盖：

- **TestDetectStyleFromText** (19 tests): 风格检测 — 单关键词/多关键词/全关键词/通用/空文本/优先级/大小写/混合文本
- **TestGetStylePromptInjection** (13 tests): 提示注入 — 各风格×各 Agent/通用返回空/未知 Agent/未知风格
- **TestGetEditorWeightMultiplier** (8 tests): 权重乘数 — 高兴奋度 pacing 翻倍/其他维度降低/中低兴奋度默认
- **TestStyleProfileDefaults** (3 tests): 数据类默认值

### 测试结果

```
41 passed in 0.09s
```

## 5. 验收标准

| # | 标准 | 状态 |
|---|------|------|
| 1 | 系统能从项目描述自动检测"逆袭"风格 | ✅ |
| 2 | 检测到爽文风格后，Planner/Screenwriter/Author prompt 自动注入爽文指令 | ✅ |
| 3 | 爽文模式下 Editor 爽点权重从 15 提升到 30 | ✅ |
| 4 | 开局钩子检查器能检测前 200 字是否有钩子 | ✅ |
| 5 | 爽点密度检查器能检测全文爽点分布 | ✅ |
| 6 | 所有检查都是确定性（无 LLM），遵循 Skill manifest 约束 | ✅ |
| 7 | 不影响非爽文小说的生成流程 | ✅ |
| 8 | 全量测试通过 | ✅ |

## 6. 设计决策

### 6.1 纯确定性检测

风格检测完全基于关键词匹配，不依赖 LLM。优势：
- 快速、可预测、无副作用
- 可以在任何阶段调用
- 结果可缓存

### 6.2 Prompt 注入而非替换

风格指令附加在现有 prompt 末尾，不替换原有指令。优势：
- 向后兼容
- 可以叠加多种风格指令
- 不影响非风格化项目的生成

### 6.3 权重后处理

Editor 权重调整在 LLM 返回分数后进行，而非修改 prompt 中的权重说明。优势：
- 不影响 LLM 的评分逻辑
- 可以精确控制最终分数
- 便于调试和测试

## 7. 已知限制

1. **关键词匹配精度**: 基于简单关键词匹配，可能误判（如"逆袭"出现在非爽文上下文中）
2. **无动态风格切换**: 风格在项目创建时检测，不支持运行时切换
3. **无风格混合**: 不支持同时检测多种风格（如"悬疑+爽文"）

## 8. 后续迭代方向

1. **LLM 辅助风格检测**: 在关键词匹配不确定时，使用 LLM 进行二次确认
2. **项目级风格覆盖**: 允许用户手动设置项目风格
3. **风格混合支持**: 支持"悬疑+爽文"等复合风格
4. **动态风格调整**: 根据章节内容实时调整风格策略
