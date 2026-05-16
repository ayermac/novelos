# v6.4.3 Polisher Anti-AI Rewrite Skills — Completion Report

## 目标

新增可复用的 deterministic anti-AI quality skills，并接入 QualityHub diagnosis 与 Polisher self-check warnings。不改变 workflow 拓扑，不新增 hard gate，不自动改写正文。

## 实现范围

### 1. 新增 4 个 ValidatorSkill

| Skill | ID | 检测内容 | 输出 |
|---|---|---|---|
| ShowDontTellValidator | `show-dont-tell` | 直白情绪/心理表达（排除对白）、总结句 | score, straight_emotion_count, summary_count, findings |
| InfoDumpDetector | `info-dump-detector` | 设定旁白、解释性短语、纯说明段落 | score, lore_count, explain_count, dump_paragraphs, findings |
| SceneTextureChecker | `scene-texture` | 感官细节密度、动作动词密度 | score, sensory_per_1000, action_per_1000, bare_paragraphs, findings |
| DialogueNaturalnessChecker | `dialogue-naturalness` | 对白占比、口语化标记、功能性对白 | score, dialogue_ratio, colloquial_ratio, functional_ratio, findings |

所有 skill：
- 继承 `ValidatorSkill`
- Deterministic，不调用 LLM
- Evidence 为小结构，不包含长正文
- 统一返回 `{ok, error, data}` envelope

### 2. Skill 注册

- `skills/base.py`: 新增到 `BUILTIN_SKILLS` 和 `_get_skill_class`
- `config/skills.yaml`: 新增 skill 配置（enabled，不挂载到 agent stage）

### 3. QualityHub.diagnose 接入

- `show_dont_tell` 维度改用 `ShowDontTellValidator`
- `info_dump` 维度改用 `InfoDumpDetector`
- `scene_immersion` 维度改用 `SceneTextureChecker`
- `dialogue_naturalness` 维度改用 `DialogueNaturalnessChecker`
- 保持 API 结构兼容：findings 包含 code/severity/message/evidence/suggestion
- Skill 不可用时回退到 dimension=100

### 4. Polisher._run_polisher_warnings 复用

- 优先通过 `skill_registry.run_skill()` 调用 4 个新 skill
- 结果转换为 Polisher warning 格式
- `warned_codes` 集合去重，避免 fallback heuristic 重复
- 防御性类型检查（兼容 mock 测试）
- Skill 不可用时回退到内置 heuristic
- Warnings 仍不影响 passed/repair_needed/workflow 路由

### 5. 测试

新增 `tests/test_v64_antiai_skills.py`（16 个测试）：
- ShowDontTellValidator: 检测直白情绪、排除对白、good text 高分、evidence 大小限制
- InfoDumpDetector: 检测 lore dump、good text 高分、evidence 大小限制
- SceneTextureChecker: low/good 对比
- DialogueNaturalnessChecker: low/good 对比
- QualityHub 集成: dimensions 存在、AI-heavy 低分、good text 高分、API 结构兼容
- Polisher 集成: warnings 触发、不阻断 workflow

### 6. 回归修复

- `test_v64_quality_diagnosis.py`: 更新 `INFO_DUMP_DETECTED` → `any("INFO_DUMP" in c)`，适配新 skill code 格式

## 修改文件

| 文件 | 改动 |
|------|------|
| `novel_factory/skills/show_dont_tell_validator.py` | 新增 |
| `novel_factory/skills/info_dump_detector.py` | 新增 |
| `novel_factory/skills/scene_texture_checker.py` | 新增 |
| `novel_factory/skills/dialogue_naturalness_checker.py` | 新增 |
| `novel_factory/skills/base.py` | 注册 4 个新 skill 类 |
| `novel_factory/config/skills.yaml` | 注册 4 个新 skill 配置 |
| `novel_factory/quality/hub.py` | diagnose() 接入 4 个新 skill |
| `novel_factory/agents/polisher.py` | _run_polisher_warnings() 复用 skill，防御 mock |
| `tests/test_v64_antiai_skills.py` | 新增 16 个测试 |
| `tests/test_v64_quality_diagnosis.py` | 更新 code 断言适配新格式 |
| `docs/codex/planning/novel-factory-v6.4-chapter-quality-closure-spec.md` | 更新 v6.4.3 状态 |

## 验证结果

- `pytest tests/test_v64_antiai_skills.py -q`：**16 passed**
- `pytest tests/test_v64_quality_diagnosis.py tests/test_v64_polisher_scene_texture.py tests/test_v64_author_drafting_contract.py tests/test_v64_antiai_skills.py -q`：**65 passed**
- `python3 scripts/verify.py smoke`：**通过**
- `pytest -q`（backend 全量）：**2045 passed, 0 failed**

## 已知限制

1. **Deterministic heuristic**：所有 skill 基于正则和统计，可能对特定文体有误报或漏报
2. **InfoDumpDetector 的 exposition paragraph 检测较粗**：仅检测 3+ 连续无动作句，未深入语义分析
3. **SceneTextureChecker 的感官词列表固定**：未按 genre 定制
4. **DialogueNaturalnessChecker 未检测角色声音区分**：仅做单章统计，不做跨章一致性
5. **未挂载到 skill hooks**：4 个 skill 由 QualityHub/Polisher 直接调用，不通过 `run_agent_skills` 管道，因此不占用 agent stage 执行时间
