# v6.3 Creator Onboarding Closure 规格

## 目标

修复 Novelos 从 0 创建小说到生成第一章的真实用户体验。当前项目创建后容易直接跳到章节 workflow，创世设定/世界观/角色/大纲/章节规划没有形成清晰闭环。本版本要让用户创建小说后自然进入创作准备流程，并支持"全部交给 AI 生成"。

## 核心问题

1. 创建小说后不应直接进入第 1 章 workflow。
2. 项目标题和类型已在创建时填写，后续创世设定不应重复要求。
3. "章节数/10章"等概念用户不理解，需要明确表达为"首批规划范围"。
4. 用户应可以什么都不填，直接让 AI 生成创世设定。
5. 第一章生成前必须有上下文 ready 检查。
6. 章节标题、正文标题、章节状态、质量状态必须一致。

## 实现范围

### 1. 创建后落点调整

- 新项目创建成功后，默认进入 `module=overview`（准备工作台）。
- 不再在 URL 中自动带 `chapter=1&view=workflow&auto_generate=1`。
- Onboarding 成功页文字已更新，明确建议先完成创世设定再生成章节。

### 2. 章节运行 Guard 增强

- `_run_guards.py` 新增 Guard 4 `CONTEXT_INCOMPLETE`。
- 检查项目是否有 approved genesis + world_settings + characters + outlines + instructions。
- 任一缺失则阻止章节 workflow 启动，返回明确的用户可读错误。

### 3. production-next health 增强

- `_build_health` 新增 `ready_for_chapter_1` 布尔字段。
- 当且仅当所有必要上下文齐全时为 `true`。

### 4. GenesisModule 体验优化

- `premise` 改为可选字段，允许留空让 AI 自动推断。
- 已继承的项目基础信息继续显示为只读上下文。
- "首批规划章数/字数" helper 文案保持，解释这只是首批范围。

### 5. ProjectOverview 主动作调整

- `generate_chapter` 不再导航到 `auto_generate=1`。
- 改为只导航到章节内容页，让用户手动点击"生成"。
- `auto_generate` URL 参数的自动触发 effect 已移除。

### 6. 默认章节标题改进

- 创建章节时默认标题从 `第 N 章` 改为 `第 N 章（待命名）`。

## 非目标

- 不做营销 landing page。
- 不做大卡片堆叠式 UI。
- 不改动创作主流程 Agent 节点。
- 不改后端数据库 schema。

## 接口变更

### 新增/修改字段

| 接口 | 字段 | 类型 | 说明 |
|---|---|---|---|
| `GET /projects/{id}/production-next` | `health.ready_for_chapter_1` | boolean | 上下文是否 ready |
| `POST /run/chapter` 错误 | `code: CONTEXT_INCOMPLETE` | string | 上下文不完整 |

## 测试策略

- `tests/test_v63_creator_onboarding.py`：覆盖 guard、health、标题默认值。
- 更新 `tests/test_v5515_production_readiness.py`：适配 guard 后的上下文要求。
