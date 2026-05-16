# v6.4 Chapter Generation Quality Closure 规格

## 目标

解决当前生成章节"AI 味重"的核心问题。优先提升正文可读性、人物对白自然度、场景颗粒度、叙事节奏和风格一致性。本版本不引入新模型、不改动 workflow 拓扑、不增加新 Agent 角色，只在现有 Author → Polisher → Editor 管道内通过 prompt 增强、validator 补充和 skill 升级来提升输出质量。

## "AI 味重"可执行问题清单

| # | 问题 | 当前覆盖 | v6.4 处理策略 | 优先级 |
|---|------|----------|---------------|--------|
| 1 | **过度总结/说教** | death_penalty 有"哲理感慨"；ai detector 有"过度解释" | 新增"章末总结性说教"检测规则；Author prompt 增加"禁止章末归纳人生道理" | P1 |
| 2 | **情绪直白说明** | death_penalty 有典型 AI 表情；ai detector 有"空泛情绪" | 新增 `show_dont_tell_validator`：检测"感到/觉得/意识到/明白"等直白情绪词 | P1 |
| 3 | **缺少动作/感官细节** | **未覆盖** | Author prompt 增加感官细节指令；新增 `scene_texture_checker`：检测场景段落中感官/动作词密度 | P1 |
| 4 | **对白功能化（无人物声音）** | narrative quality 有对话比例，但无声音区分 | 新增 `dialogue_naturalizer`：检测对白是否缺少口语化标记、是否所有角色使用同一语调 | P2 |
| 5 | **段落节奏单一** | narrative quality 有 pacing_control（std_dev 粗粒度） | 增强 pacing 检测：段落长度分布、长短句交替；Polisher prompt 增加节奏改写指令 | P2 |
| 6 | **人物声音不区分** | **未覆盖** | Author build_context 注入角色语言特征；新增 heuristic warning（非 blocker） | P3 |
| 7 | **伏笔/设定只解释不戏剧化** | **未覆盖** | Author prompt 增加"设定通过动作/对话展现，禁止旁白解释"；新增 `info_dump_detector` | P2 |
| 8 | **场景缺少冲突推进** | narrative quality 有 conflict_intensity（关键词密度） | 增强 scene beats 中 conflict/turn 在 prompt 中的权重；新增 `scene_conflict_checker` | P2 |

## 版本拆分

### v6.4.0 Quality Diagnosis Baseline

**目标**：建立可观测基线，不改 Agent 行为，只增加诊断报告和事件。

**状态**：已实现

**改动**：
1. **QualityHub 新增 `diagnose` 方法**：聚合 death_penalty、ai-style-detector、narrative-quality、show_dont_tell（正则基线）、info_dump（正则基线）的所有维度，输出统一 JSON 诊断报告
2. **Execution Event 增强**：新增 `EVENT_QUALITY_DIAGNOSED = "quality_diagnosed"` 常量，供后续版本接入 workflow 事件记录
3. **新增 API**：`GET /api/projects/{project_id}/chapters/{chapter_number}/quality-diagnosis` 返回当前章节质量诊断快照
4. **Frontend**：在章节详情页正文下方新增"质量诊断"折叠面板，展示 overall_score、维度分数条、metrics、findings

**验收**：
- stub 模式跑完整 workflow 不阻断
- API 返回的 diagnosis JSON 包含所有已知维度
- frontend typecheck/lint/build/vitest 通过
- backend smoke 通过
- backend full suite 1990 passed

**依赖**：无（纯观测层）

---

### v6.4.1 Author Prompt / Drafting Contract

**目标**：从源头减少 AI 味，增强初稿质量。

**状态**：已实现

**改动**：
1. **Author SYSTEM_PROMPT 增强**：
   - 新增"Drafting Contract（v6.4.1）"段落：禁止剧情摘要/设定说明/章节梗概；以场景为单位推进
   - 新增"Show, Don't Tell 铁律"：禁止"感到/觉得/意识到/明白/心中暗想"等直白情绪词；情绪必须通过动作、神态、对话展现
   - 新增"感官细节要求"：每个场景至少包含 1 种视觉 + 1 种听觉/触觉/嗅觉细节
   - 新增"对白人物化"：对白必须有角色目的、潜台词或冲突；禁止所有角色使用同一套礼貌/书面语
   - 新增"设定戏剧化"：世界观和设定必须通过角色的动作、对话或场景细节展现，禁止旁白式解释
   - 新增"章末禁止说教"：章节结尾禁止归纳人生道理、总结本章意义、发表作者评论

2. **Author `build_context` 增强**：
   - 注入"去AI味写作指南"（硬编码 7 条规则）：禁止直白情绪动词、内心独白模板、设定旁白、解释句式；要求感官细节、对白冲突、悬念结尾
   - 保留 style_bible 和 memory 现有行为，不破坏兼容

3. **Author `_build_plain_text_context` / `_try_plain_text_draft` 增强**（real mode）：
   - 纯正文系统提示增加 drafting contract 约束
   - compact context 增加"写作约束"段落

4. **Author self-check 增强**（v6.4.1 warning heuristic，不 hard fail）：
   - `show_dont_tell`：检测直白情绪词密度，超过 5/千字 emit warning
   - `sensory_detail`：检测感官词密度，低于 3/千字 emit warning
   - `prose_like`：检测摘要式表达（"本章/首先/然后/最后/综上所述"），超过 3 处 emit warning
   - `dialogue`：检测对白占比，低于 5% emit warning
   - 所有新增 heuristic 只输出 warning，不加入 issues，不影响 passed/repairable 判定

5. **Stub provider 适配**：
   - 修改 `_STORY_TEMPLATES` 中 ch1/ch2/ch3 的直白内心描写（"心中一凛/心中涌起/心中一动"等）为动作描写（"背脊一紧/喉头发紧/目光一顿"等）
   - 确保 stub content 不触发 critical death penalty

**验收**：
- SYSTEM_PROMPT 和 build_context 包含 drafting contract 关键约束
- self-check 对 AI 味文本 emit warning，对正常文本无 warning
- key_events 缺失时仍 hard fail
- backend full suite 通过
- backend smoke 通过

**依赖**：v6.4.0（需要 quality diagnosis 基线来观测效果）

---

### v6.4.2 Dialogue and Scene Texture Pass

**目标**：Polisher 专项提升对白和场景质感。

**状态**：已实现

**改动**：
1. **Polisher SYSTEM_PROMPT 增强**：
   - 新增"职责边界"段落：明确保留剧情事实、关键事件、伏笔和角色动机，不得改写剧情走向
   - 新增"对白自然化"：将功能化对白改为口语化；增加语气词、省略、打断、反问；让不同角色的对白在句式长度、用词习惯上有差异
   - 新增"场景质感增强"：在场景描写中补充感官细节（光影、声音、温度、气味）；将抽象描述改为具体动作
   - 新增"节奏调整"：打破均匀段落，在紧张场景使用短句/短段，在描写场景使用长句但避免超长句（>40字）
   - 新增"去AI味"：删减总结句（"综上所述/总之/简单来说"）、直白心理解释和宏大空泛判断

2. **Polisher `build_context` 增强**（v6.4.2）：
   - 在 ContextBuilder 输出后追加"润色写作提醒"段落
   - 将 v6.4.0 quality diagnosis 的维度（对白自然度、场景质感、节奏变化、Show-Don't-Tell）转化为写作提醒注入 prompt
   - 不调用 API、不触发 LLM 以外流程

3. **Polisher deterministic self-check warnings**（v6.4.2，不影响路由）：
   - `dialogue_naturalness_low`：对白占比 < 5% 或口语化标记不足时 emit warning
   - `scene_texture_low`：感官细节密度 < 3/千字时 emit warning
   - `excessive_explanation`：直白情绪词密度 > 5/千字或存在总结句时 emit warning
   - `pacing_too_uniform`：段落长度变异系数 < 0.25 时 emit warning
   - warnings 通过 execution events 上报，不影响 passed/repair_needed/workflow 路由

4. **Stub provider 最小调整**：
   - Polisher stub 的 `changed_scope` 增加 `dialogue` 和 `scene_texture`
   - `summary` 从"微调表达"改为更具体的"优化句式节奏，调整对白语气，补充场景细节"

5. **HumanizerZhSkill / AIStyleDetector**：
   - v6.4.2 保持现有 skill 行为不变，不做额外增强（推迟到 v6.4.3 skill 层统一处理）

**验收**：
- SYSTEM_PROMPT 包含职责边界、对白自然化、场景质感、节奏变化、去AI味约束
- build_context 包含"润色写作提醒"段落
- self-check 对低质量文本 emit warning，对正常 stub 文本无 excessive_explanation / pacing_too_uniform warning
- warnings 不阻断 workflow，状态正常推进到 polished
- backend 全量测试通过

**依赖**：v6.4.1（Author prompt 先减少 AI 味输入，Polisher 才有更好的基础）

---

### v6.4.3 Polisher Anti-AI Rewrite Pass

**目标**：引入新的 deterministic skills，在 Polisher 阶段做更深层的质量检查。

**改动**：
1. **新增 `ShowDontTellValidator` Skill**（ValidatorSkill）：
   - 检测"感到/觉得/意识到/明白/知道/理解/察觉/发现"等直白情绪/认知动词
   - 检测"心中暗想/心道/暗道"等内心独白模板
   - 返回：`straight_emotion_count`、`sensory_action_replacement_suggestions`
   - 接入 Polisher `before_save` stage（validator 类型）

2. **新增 `DialogueNaturalizer` Skill**（ValidatorSkill）：
   - 检测对白是否缺少口语化标记（啊、呢、吧、嘛、哦、呀、哈）
   - 检测对白是否过于完整/书面（所有句子都有主谓宾）
   - 检测不同角色对白是否长度/句式过于相似
   - 返回：`dialogue_naturalness_score`、`character_voice_diversity_score`、`issues`
   - 接入 Polisher `before_save` stage

3. **新增 `SceneConflictChecker` Skill**（ValidatorSkill）：
   - 检测场景段落是否有明确的目标-冲突-转折结构
   - 通过 scene beats 与正文对齐来检查：beat 中的 `conflict` 是否在正文中体现为实际冲突而非旁白说明
   - 返回：`scene_structure_score`、`missing_conflict_beats`
   - 接入 Polisher `before_save` stage

4. **新增 `InfoDumpDetector` Skill**（ValidatorSkill）：
   - 检测设定旁白式解释："这个世界是一个..."、"在这个时代..."、"所谓 XX 是指..."
   - 检测连续 3 句以上纯信息性描述（无角色动作/对话）
   - 返回：`info_dump_paragraphs`、`suggestions`
   - 接入 Polisher `before_save` stage

5. **QualityHub `check_polished` 增强**：
   - 新增上述 4 个 skill 的调用和结果聚合
   - `overall_score` 计算纳入新维度

6. **Polisher skill hooks 配置更新**：
   - `fail_closed_ids` 中不加入新增 skills（它们是 heuristic，不 blocker）
   - 新增 skills 的结果通过 execution events 上报

**验收**：
- 各新增 skill 对已知 bad input 的单元测试通过
- QualityHub `check_polished` 返回结果包含新维度分数
- Polisher execution events 包含新增 skill 的 `skill_completed` 事件
- backend 全量测试通过

**依赖**：v6.4.2（prompt 层面的优化先做，skill 层做补充检测）

---

### v6.4.4 Editor Quality Gates and Tests

**目标**：让 Editor 的审核更精准地捕捉 AI 味问题，并建立可持续的测试基线。

**改动**：
1. **Editor SYSTEM_PROMPT 增强**：
   - "文字质量"维度（15分）拆分为子维度：
     - AI 痕迹（5分）：检测模板句式、直白情绪、机械解释
     - 叙事质感（5分）：检测感官细节、动作描写、对白自然度
     - 节奏控制（5分）：检测段落单调、句子长度 uniformity
   - 新增"死刑红线"独立维度说明：发现"感到/觉得"式直白情绪 → 文字质量单项扣至 8 分以下
   - 新增 revision_target 规则：对白问题 → "polisher"；场景结构问题 → "author"；info dump → "author"

2. **Editor 五维评分权重调整**（可选）：
   - 当前：setting(25) logic(25) poison(20) text(15) pacing(15)
   - 建议保持不动，通过子维度细化 text 和 pacing 的评分标准

3. **Editor `_fallback_rule_review` 增强**：
   - fallback 评分也纳入新增 death_penalty 规则（如直白情绪词）

4. **新增测试文件**：
   - `tests/test_v64_quality_diagnosis.py`：测试 QualityHub.diagnose 聚合逻辑
   - `tests/test_v64_show_dont_tell.py`：测试 ShowDontTellValidator 命中逻辑
   - `tests/test_v64_dialogue_naturalizer.py`：测试 DialogueNaturalizer 检测逻辑
   - `tests/test_v64_scene_conflict.py`：测试 SceneConflictChecker 结构检测
   - `tests/test_v64_info_dump.py`：测试 InfoDumpDetector 检测逻辑
   - `tests/test_v64_author_prompt.py`：测试 Author prompt 构建（context 是否包含新规则）
   - `tests/test_v64_polisher_rewrite.py`：测试 Polisher skill hooks 调用新 skills

5. **Real LLM 可选验收脚本**：
   - `scripts/verify_v64_real_llm.sh`：
     - 创建测试项目（genre=都市/玄幻）
     - 跑 1 章完整 real mode workflow
     - 验收标准（heuristic）：
       - ai_trace_score < 60
       - narrative_quality.overall_score > 55
       - death_penalty critical count = 0
       - dialogue_ratio > 0.10（narrative quality 数据）
       - show_dont_tell straight_emotion_count < 5（每千字）
     - 不检查具体措辞，只检查数值阈值

6. **Stub 稳定测试策略**：
   - 所有新增 skill 的单元测试使用 fixture 文本（`tests/fixtures/ai_heavy_chapter.txt`）
   - fixture 文本包含所有典型 AI 味表达（直白情绪、功能对白、info dump、模板句式）
   - 测试断言：skill 能检测到 fixture 中的问题
   - workflow 测试只断言节点通过、status 正确推进，不断言文本质量

**验收**：
- 新增测试文件全部通过
- fixture 文本 `tests/fixtures/ai_heavy_chapter.txt` 存在且被所有新增 skill 测试引用
- backend full suite 通过
- real LLM 验收脚本可独立运行（不纳入 CI）
- frontend 质量诊断面板展示新维度

**依赖**：v6.4.0 ~ v6.4.3（本阶段是验收和测试闭环）

---

## 改动分类矩阵

| 改动 | Prompt/Agent Contract | Deterministic Validator | UI/报告 | Schema | Config |
|------|----------------------|------------------------|---------|--------|--------|
| Author SYSTEM_PROMPT 增强 | ✅ | | | | |
| Author build_context 注入写作指南 | ✅ | | | | |
| Author self-check 新增 heuristic | ✅ | | | | |
| Polisher SYSTEM_PROMPT 增强 | ✅ | | | | |
| PolisherOutput 可选字段 | ✅ | | | ✅ | |
| ShowDontTellValidator Skill | | ✅ | | | |
| DialogueNaturalizer Skill | | ✅ | | | |
| SceneConflictChecker Skill | | ✅ | | | |
| InfoDumpDetector Skill | | ✅ | | | |
| HumanizerZhSkill 新增规则 | | ✅ | | | |
| AIStyleDetector 新增维度 | | ✅ | | | |
| death_penalty 新增规则 | | ✅ | | | |
| QualityHub.diagnose | | ✅ | | | |
| QualityHub 新维度聚合 | | ✅ | | | |
| Editor SYSTEM_PROMPT 增强 | ✅ | | | | |
| Editor fallback 评分 | ✅ | | | | |
| 质量诊断 API | | | ✅ | ✅ | |
| Frontend 质量诊断面板 | | | ✅ | | |
| Execution Event 增强 | | | ✅ | | |
| 新增测试文件 | ✅ | ✅ | | | |
| Real LLM 验收脚本 | | | | | ✅ |

## 测试和验收设计

### Stub 稳定测试

Stub 模式返回固定内容，无法测试"生成质量是否提升"。因此 stub 测试聚焦：

1. **Prompt/Context 测试**：断言 Author/Polisher/Editor 的 build_context 输出包含新注入的规则文本
2. **Skill 命中测试**：使用 `tests/fixtures/ai_heavy_chapter.txt` 作为输入，断言各 validator skill 能检测到问题
3. **Workflow 推进测试**：断言 workflow 各节点正常推进，新增 execution events 被正确记录
4. **QualityHub 聚合测试**：断言 diagnose/check_polished 返回结果包含新维度字段
5. **Schema 兼容测试**：断言 PolisherOutput 可选字段不破坏现有解析

### Real LLM 可选验收

1. **独立脚本**：`scripts/verify_v64_real_llm.sh`
2. **验收项目**：使用固定 genre（都市职场或玄幻修仙），固定 premise，固定首批规划章数=3
3. **跑 1 章 workflow**，记录 quality diagnosis 结果
4. **通过标准**（heuristic，可调整）：
   | 指标 | 阈值 | 说明 |
   |------|------|------|
   | ai_trace_score | < 60 | 越低越好 |
   | narrative_quality.overall_score | > 55 | 中等偏上 |
   | death_penalty.critical_count | = 0 | 无致命红线 |
   | death_penalty.violation_count | <= 3 | 少量可接受 |
   | show_dont_tell.straight_emotion_count | < 5/千字 | 直白情绪词少 |
   | dialogue_naturalizer.naturalness_score | > 50 | 对白基本自然 |
   | scene_conflict_checker.structure_score | > 50 | 场景有冲突结构 |
5. **不纳入 CI**：real LLM 验收需要 API key，成本不可控，作为可选手动验证

### 避免脆弱文本精确匹配

- 所有测试使用数值阈值或字段存在性断言
- 不断言具体措辞（如"必须包含'攥紧拳头'"）
- 允许 real LLM 输出有合理波动
- fixture 文本只用于 skill 的命中测试，不用于 workflow 端到端测试

### Heuristic vs Hard Blocker

| 指标 | 类型 | 说明 |
|------|------|------|
| death_penalty critical | **Hard Blocker** | 触发即失败 |
| ai_trace_score > 70 | **Hard Blocker**（可配置） | 当前行为，保持 |
| narrative_quality < 30 | **Hard Blocker**（可配置） | 当前行为，保持 |
| show_dont_tell 密度高 | **Heuristic Warning** | 只上报，不 blocker |
| dialogue_naturalness < 50 | **Heuristic Warning** | 只上报，不 blocker |
| scene_structure < 50 | **Heuristic Warning** | 只上报，不 blocker |
| info_dump 检测到 | **Heuristic Warning** | 只上报，不 blocker |
| character_voice 不区分 | **Heuristic Warning** | 需要多章数据，v6.4 只做单章检测 |

## 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| Prompt 增强导致 real mode token 消耗增加 | 成本上升 | 新 prompt 规则尽量紧凑（<200字）；plain-text path 优先 |
| 新增 skill 误报率高 | 质量诊断不可信 | 所有新增 skill 初始为 heuristic（不 blocker）；跑 real LLM 验收后调参 |
| Polisher 改动幅度过大 | 事实锁定频繁触发 | HumanizerZh 新增规则只做标记不做自动替换；fact_lock 保持现有严格检查 |
| Editor 评分标准变化导致 regression | 旧项目 review 结果不一致 | Editor 子维度只影响 LLM 评分的 prompt 说明，不影响 schema 和数据库 |
| Stub 测试需要大量 fixture | 维护成本 | 使用单一 `ai_heavy_chapter.txt` fixture，所有 skill 共享 |

## 非目标

- 不引入新 LLM 模型或更换 provider
- 不增加新 Agent 角色（如专门的对白写手、场景描写师）
- 不改动 workflow 拓扑（不新增节点，不改路由）
- 不做跨章节人物声音一致性（需要 memory 增强，v6.5 再做）
- 不做 RAG 增强（参考样本风格匹配已有，不做扩展）
- 不改动数据库 schema（skill results 走现有 artifact/execution_event 表）

## 与 v6.5 的衔接

v6.4 解决"单章质量"问题后，v6.5 将解决"跨章一致性"：
- v6.4 中 `character_voice` 只做单章 heuristic warning
- v6.5 将引入跨章节角色声音 profile，让 Author 在创作时能根据角色历史对白风格生成
- v6.4 的 `scene_conflict_checker` 为 v6.5 的"情节结构 canonicalization"打基础
