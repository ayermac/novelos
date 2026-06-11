# Novel Factory v6.10.4 Style Management Hardening Plan

## 背景

v6.10.3 之后，章节工作流的运行稳定性和记忆链路已经明显改善。当前暴露出的新问题集中在“风格管理”：

- 项目工作台里可以初始化“风格指南”，但点击“编辑”只跳到全局 `/style` 页面。
- 全局 `/style` 页面只是统计和列表，操作列显示“已建立”，没有真正编辑入口。
- 初始化 API 写入的 JSON 与 `StyleBible` Pydantic 模型不一致，导致后续 prompt 注入字段可能为空。
- 真实 LLM 的 Author 纯正文路径会重建 compact context，当前没有把 Style Bible 放进去，风格配置即使存在也可能不进入真实正文生成请求。

v6.10.4 的目标是：**把风格管理从“存在记录”升级为“用户可维护、系统可消费、生成链路真正生效”的项目级创作控制能力。**

## 审计结论

### 1. 数据模型与初始化不一致

Canonical 模型是 `StyleBible`：

- `tone_keywords`
- `pacing`
- `pov`
- `dialogue_style`
- `prose_style`
- `tension_style`
- `humor_style`
- `emotional_intensity`
- `forbidden_expressions`
- `preferred_expressions`
- `sentence_rules`
- `paragraph_rules`
- `chapter_opening_rules`
- `chapter_ending_rules`
- `ai_trace_avoidance`

但 `POST /api/style/init` 当前写入的是：

- `voice`
- `narrative`
- `prose`
- `project_name`
- `generated_from_reference`

这些字段不是 `StyleBible.rules_for_agent()` 的主要消费字段。结果是：页面显示“已建立”，但 Author/Polisher/Editor 实际可用风格指令可能很少。

### 2. 页面交互不是编辑

当前项目页：

- 无风格记录时：显示“初始化风格指南”。
- 有风格记录时：显示“编辑”。
- “编辑”实际跳转 `/style`。

当前全局 `/style`：

- 展示总项目、风格圣经数、风格门禁数。
- 风格圣经表格只显示项目、状态、版本、更新时间。
- 操作列固定显示“已建立”，没有编辑、查看详情、启用门禁等动作。

这会让用户以为“编辑失效”。

### 3. API 缺少详情与结构化更新

现有能力：

- `GET /api/style/console`
- `POST /api/style/init`
- `PUT /api/style/bible`

缺口：

- 缺少 `GET /api/style/bible/{project_id}` 详情接口。
- `PUT /api/style/bible` 只接受 JSON 字符串 `content`，不适合页面表单。
- 没有 canonical normalization，旧格式、初始化格式、页面格式容易分叉。
- 没有明确状态语义，页面只能显示 `unknown / 待确认`。

### 4. 真实 Author 请求可能没有风格约束

Author 常规 `build_context()` 会注入 Style Bible，但真实 LLM 长文生成走 `plain_text_primary`：

- `_try_plain_text_draft()`
- `_try_segmented_plain_text_draft()`
- `_build_plain_text_context()`

`_build_plain_text_context()` 会重建 compact context。当前 `AgentContextBuilder` 没有 Style Bible bucket，`_build_plain_text_context()` 也没有重新追加 Style Bible，所以真实正文生成路径可能丢失风格约束。

这比 UI 问题更关键：即使用户维护了风格，真实创作也可能没有遵循。

### 5. Style Gate 与 Style Checker 已有基础，但缺少产品化入口

已有能力：

- `StyleBibleCheckerSkill` 可做确定性风格检查。
- `StyleGateConfig` 支持 `off / warn / block`。
- `QualityHub` 可在 draft/polished/final_gate 阶段运行风格检查。

缺口：

- 页面没有门禁配置入口。
- 用户无法看到本项目风格检查结果。
- 默认启用策略不清晰。
- 风格问题不应贸然变成 blocking，否则会再次增加创作阻塞率。

## 目标

1. 风格初始化生成 canonical `StyleBible`，而不是松散 JSON。
2. 项目页“编辑”真正进入当前项目风格编辑。
3. 全局 `/style` 支持查看、编辑、初始化、门禁状态管理。
4. 真实 Author 纯正文路径必须注入 Style Bible。
5. Style Checker/Gate 保持默认低阻塞：先警告、可诊断、可配置，不默认阻断创作。

## 非目标

- 不做复杂 LLM 风格分析器。
- 不做“模仿某作者风格”功能。
- 不把风格门禁默认设为 blocking。
- 不重写整个 Style 系统表结构。
- 不在本版本做风格样本自动学习闭环，只保留后续扩展点。

## P0 交付范围

### 1. Canonical Style Bible 初始化

修改 `POST /api/style/init`：

- 默认使用 `style_bible_templates.yaml` 的 `default_web_serial` 或按项目 `genre` 选择模板。
- 保存前统一经过 `StyleBible(**data).to_storage_dict()`。
- `name` 默认使用模板名称或“{项目名} 风格指南”。
- `project_id` 必须写入 bible JSON。
- `status` 不再使用隐式 `unknown`，API 层返回标准状态：
  - `draft`：新建但用户未确认。
  - `active`：已保存并用于创作。
  - `needs_review`：由样本或 AI 生成，等待用户确认。

兼容旧记录：

- 增加 normalization 函数，将旧格式 `voice/narrative/prose` 映射到 canonical 字段。
- 读取和更新时都走 normalization，避免旧数据导致页面或注入失败。

### 2. Style Bible 详情 API

新增：

- `GET /api/style/bible/{project_id}`
- `PUT /api/style/bible/{project_id}`

返回结构：

```json
{
  "project_id": "novel_3ryj",
  "project_name": "开局签到就无敌",
  "status": "active",
  "version": "1.0.0",
  "bible": {
    "tone_keywords": ["爽感", "升级"],
    "pacing": "fast",
    "pov": "third_person_limited",
    "dialogue_style": "口语化",
    "prose_style": "紧凑叙事",
    "forbidden_expressions": [],
    "preferred_expressions": [],
    "sentence_rules": [],
    "paragraph_rules": [],
    "chapter_opening_rules": [],
    "chapter_ending_rules": [],
    "ai_trace_avoidance": {
      "avoid_patterns": [],
      "prefer_patterns": [],
      "notes": ""
    }
  },
  "gate_config": {
    "enabled": false,
    "mode": "warn",
    "blocking_threshold": 70,
    "revision_target": "polisher",
    "apply_stages": ["polished", "final_gate"]
  }
}
```

保留旧 `PUT /api/style/bible` 兼容，但内部转调用新更新逻辑。

### 3. 项目页风格编辑入口

修改 `StyleGuideModule`：

- “编辑”链接改为 `/style?project_id={projectId}` 或 `/projects/{projectId}?module=style&edit=1`。
- 状态显示统一：
  - `draft` → 草稿
  - `active` → 已启用
  - `needs_review` → 待确认
  - unknown/空 → 已建立
- 初始化成功后直接进入编辑态或显示“去完善风格”。

### 4. 全局 Style 页面支持编辑

修改 `/style` 页面：

- 从 URL query 读取 `project_id`，自动定位项目。
- 风格圣经表格操作列提供：
  - 查看
  - 编辑
  - 配置门禁
- 编辑表单采用结构化字段，不要求用户写 JSON：
  - 基调关键词
  - 节奏
  - 视角
  - 对白风格
  - 行文风格
  - 张力风格
  - 幽默风格
  - 情感强度
  - 禁用表达列表
  - 推荐表达列表
  - 句式规则
  - 段落规则
  - 开头/结尾规则
  - AI 痕迹规避

表单保存后调用新 `PUT /api/style/bible/{project_id}`。

### 5. Author 真实路径注入修复

统一 `AgentContextBuilder`：

- 增加 `style_context: list[ContextItem]` 或把 Style Bible 放入 advisory context 的固定 bucket。
- `format_context_bundle_for_prompt()` 明确输出 `【风格规范 / Style Bible】`。
- `build_for_author()`、`build_for_polisher()`、`build_for_editor()`、`build_for_planner()` 均可消费。

修复 `_build_plain_text_context()`：

- 真实 `plain_text_primary` 和 segmented 生成必须包含 Style Bible。
- 不再出现“普通 JSON 路径有风格、真实纯正文路径无风格”的不一致。

### 6. Style Gate 默认策略

本版本默认策略：

- 默认 `enabled=false` 或 `enabled=true + mode=warn`，但不得默认 block。
- 页面允许用户启用门禁。
- 门禁结果展示在运行详情/质量诊断中。
- blocking 只在用户明确设置 `mode=block` 后生效。

## P1 交付范围

### 1. 风格效果可观测

在 Run Detail / Project Detail 展示：

- 本章是否加载 Style Bible。
- 注入到了哪些 agent。
- Style Checker 分数。
- 风格 warning 数。
- 是否触发 Style Gate。

### 2. 初始化模板选择

初始化时根据项目类型推荐模板：

- 都市/系统/签到 → `urban_fantasy_fast` 或 `default_web_serial`
- 悬疑 → `mystery_suspense`
- 仙侠/修真 → `xianxia_progression`
- 言情 → `romance_emotional`

用户可手动切换模板。

### 3. 旧数据迁移诊断

新增诊断：

- 检查 `style_bibles.bible_json` 是否符合 canonical schema。
- 发现旧格式时提示“需要升级风格配置”。
- 可在读取时自动 normalization，也可提供一次性修复按钮。

## P2 后续方向

- 风格样本导入后生成 Style Bible 修改建议。
- 每章风格趋势记录：对白比例、说明腔比例、禁用表达次数、风格分数。
- 与 Knowledge Skill 合并视图：区分“项目专属风格”和“通用写作规范”。
- 支持章节级风格覆盖，但默认不得污染项目级 Style Bible。

## 实施步骤

### Step 1：后端 canonical 化

修改：

- `novel_factory/api/routes/style.py`
- `novel_factory/style_bible/templates.py`
- `novel_factory/models/style_bible.py`
- `novel_factory/db/repositories/style_bible.py`

新增：

- `novel_factory/style_bible/normalizer.py`

验收：

- 初始化后 `get_style_bible()` 返回的 `bible` 可被 `StyleBible.from_storage_dict()` 解析。
- 初始化记录能通过 `rules_for_agent("author")` 生成非空写作指引。

### Step 2：API 详情与更新

修改：

- `novel_factory/api/routes/style.py`

验收：

- `GET /api/style/bible/{project_id}` 返回完整 bible 和 gate_config。
- `PUT /api/style/bible/{project_id}` 支持结构化 JSON。
- 旧 `PUT /api/style/bible` 继续兼容。

### Step 3：前端编辑体验

修改：

- `frontend/src/components/project/StyleGuideModule.tsx`
- `frontend/src/pages/Style.tsx`

可新增：

- `frontend/src/components/style/StyleBibleEditor.tsx`
- `frontend/src/components/style/StyleGateEditor.tsx`

验收：

- 项目页“编辑”可以定位到当前项目风格。
- 用户无需写 JSON 即可维护风格字段。
- 保存后回到项目页，状态与更新时间刷新。

### Step 4：真实生成链路注入修复

修改：

- `novel_factory/agent_runtime/context_builder.py`
- `novel_factory/agents/author.py`
- 必要时同步 `planner/screenwriter/polisher/editor` 的风格注入路径，避免重复注入或遗漏。

验收：

- real mode `plain_text_primary` 请求中包含 Style Bible。
- segmented 生成每段请求中包含 Style Bible。
- 日志/trace 可显示 style context 已注入。

### Step 5：检查与回归

新增/更新测试：

- `tests/test_v6104_style_management.py`
- `frontend/src/pages/__tests__/Style.test.tsx`
- `frontend/src/components/project/__tests__/StyleGuideModule.test.tsx`

建议验证：

```bash
python3 -m pytest tests/test_v40_style_bible_models.py tests/test_v40_style_bible_context.py tests/test_v40_style_bible_skill.py tests/test_v6104_style_management.py -q
cd frontend && npm run typecheck && npm run test -- Style
```

## 验收标准

1. 初始化后的 Style Bible 是 canonical schema。
2. 项目页“编辑”不再跳到无操作的只读列表。
3. 全局 `/style` 可以查看并编辑当前项目风格。
4. 真实 Author 纯正文请求包含风格上下文。
5. Style Gate 默认不增加阻塞率。
6. 旧数据不会导致页面崩溃或风格注入异常。

## 风险与约束

- 风格规则过强会影响章节稳定性，因此 v6.10.4 默认不启用 blocking。
- Style Bible 与 Knowledge Skill 有重叠，但边界不同：
  - Style Bible：项目级、可编辑、长期一致性。
  - Knowledge Skill：通用写作方法论、跨项目复用。
- 真实路径 prompt 预算有限，风格上下文必须摘要化，不能把完整大 JSON 塞给 LLM。
- 旧记录可能包含非 canonical 字段，必须兼容读取，不能要求用户手动清库。

## 完成后需要更新的文档

- `README.md`：补充风格管理入口与用途。
- `docs/codex/README.md`：补充 v6.10.4 风格管理能力。
- `docs/codex/planning/novel-factory-version-planning-index.md`：登记 v6.10.4。
- 如实现 API 变更，补充对应接口说明。
