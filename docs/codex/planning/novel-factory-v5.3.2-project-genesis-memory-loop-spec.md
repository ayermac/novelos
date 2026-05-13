# Novel Factory v5.3.2 Project Genesis & Memory Loop Spec

状态：规划中

上游依赖：

- v5.3.0 Trusted Generation Chain
- v5.3.1 Project-Level Author Workspace

目标：把 WebUI 从“项目资料 CRUD + 章节生成”升级为真正的长篇小说创作系统。系统应能从一句创意生成项目骨架，并在后续章节生产中持续维护世界观、角色、大纲、势力、伏笔、章节指令和事实连续性，而不是把这些维护工作全部交给用户手填。

## 背景

当前 v5.3.1 已经把 `world_settings / characters / outlines / factions / plot_holes / instructions` 做成项目级模块，并用 Context Readiness Gate 阻止空项目生成章节。

但从真人作者角度看，仍有两个核心断点：

1. 新项目缺少“自动搭骨架”能力。用户只输入书名或一句创意后，系统要求用户手填世界观、主角、大纲、章节指令，体验像数据库管理。
2. 后续章节生成不会反向维护项目资料。新角色、新地点、新势力、伏笔、关系变化、道具、倒计时、修为、伤势、目标进度等不会自动沉淀，长篇连续性无法真正建立。

v5.3.2 要补的是“创作记忆循环”，不是再加几个表单。

## 产品原则

- AI 负责生成草案和维护建议，用户拥有最终确认权。
- 项目资料不是静态设定表，而是可演进的作者记忆系统。
- 所有自动维护必须可审阅、可追踪、可撤销。
- 章节生成前读取项目记忆，章节生成后反写项目记忆。
- 真实模式下，关键记忆变更和事实冲突必须进入发布前门禁。
- Stub 模式可以生成确定性示例，但必须标注为演示内容。

## 范围

### 1. Project Genesis：项目创世

新增“生成项目设定”流程，从一句创意生成项目圣经草案。

输入：

- 项目名称
- 类型
- 一句话创意或故事简介
- 篇幅目标
- 目标读者
- 风格偏好
- 可选约束：人称、节奏、禁忌、主角类型、题材边界

输出草案：

- `projects.description`
- 核心卖点和长期叙事承诺
- `world_settings`
- `characters`
- `factions`
- `outlines`
- `plot_holes`
- 前 10 章 `instructions`
- 风格指南初稿
- 初始事实账本草案，包括主角状态、关键道具、主线目标、时间线锚点

要求：

- 生成结果先进入草案，不直接覆盖已批准资料。
- 用户可以逐项接受、编辑、忽略。
- 批准后批量写入正式表。
- 已存在项目资料时，Genesis 必须生成 merge patch，而不是清空重写。

建议新增 API：

- `POST /api/genesis/generate`
- `GET /api/projects/{project_id}/genesis/latest`
- `POST /api/genesis/approve`
- `POST /api/genesis/reject`

API 设计约束：

- 动作型 `POST` 的业务参数必须放 request body，不继续把 `project_id / run_id / batch_id / item_id / chapter_number` 塞进 path。
- 资源读取型 `GET` 可以继续使用 path 定位资源，例如 `GET /api/projects/{project_id}/genesis/latest`。
- 如果 v5.3.2 开发中已经实现了 path-style `POST`，先保留兼容路由，但必须新增 body-style canonical route，并让前端改用 canonical route。
- 旧接口迁移不得阻塞 v5.3.2 主功能验收。

示例：

```json
POST /api/genesis/generate
{
  "project_id": "novel_26pu",
  "idea": "一个凡人少年在宗门边缘发现旧时代修真体系的漏洞",
  "genre": "修仙",
  "target_words": 1500000,
  "total_chapters_planned": 500
}
```

建议新增表：

```sql
CREATE TABLE genesis_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    status TEXT NOT NULL,
    input_json TEXT NOT NULL,
    draft_json TEXT,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 2. Memory Patch：项目资料更新建议

章节生产后新增 `memory_curator` 节点，负责从本章产物中提取项目资料变更建议。

输入：

- 本章 instruction
- scene beats
- 正文
- workflow agent artifacts
- 当前项目资料
- 当前事实账本

输出 memory patch：

- 新增/更新角色
- 新增/更新世界观规则
- 新增/更新势力
- 新增/更新大纲偏移
- 新增/解决/废弃伏笔
- 生成下一章或后续章节指令
- 新增/更新事实账本事件

Memory Patch 不直接写正式表。它先进入待确认队列：

```sql
CREATE TABLE memory_update_batches (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    chapter_number INTEGER,
    run_id TEXT,
    status TEXT DEFAULT 'pending',
    summary TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE memory_update_items (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    target_table TEXT NOT NULL,
    target_id TEXT,
    operation TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT NOT NULL,
    confidence REAL DEFAULT 0.8,
    evidence_text TEXT,
    rationale TEXT,
    status TEXT DEFAULT 'pending',
    applied_at DATETIME
);
```

支持操作：

- `create`
- `update`
- `resolve`
- `deprecate`
- `ignore`

建议新增 API：

- `GET /api/projects/{project_id}/memory-updates`
- `GET /api/projects/{project_id}/memory-updates/{batch_id}`
- `POST /api/memory/apply`
- `POST /api/memory/ignore`
- `PUT /api/projects/{project_id}/memory-updates/{item_id}`

示例：

```json
POST /api/memory/apply
{
  "project_id": "novel_26pu",
  "batch_id": "mem_123",
  "item_ids": ["item_1", "item_2"],
  "review_note": "确认纳入项目设定"
}
```

### 3. Fact Ledger：事实账本先行子集

完整 Fact Ledger 原计划在 v5.3.3，但 v5.3.2 必须先实现最小可用子集，否则“自动维护”无法解决跨章数值继承问题。

v5.3.2 先覆盖：

- 角色状态：伤势、能力、修为/等级、心理状态
- 道具和资源：获得、消耗、丢失、损坏
- 地点：当前位置、已到达地点、不可达地点
- 时间线：日期、倒计时、关键事件顺序
- 关系：信任、仇恨、阵营关系
- 伏笔状态：planted/resolved/abandoned

建议新增最小表：

```sql
CREATE TABLE story_facts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    fact_key TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    subject TEXT,
    attribute TEXT,
    value_json TEXT NOT NULL,
    unit TEXT,
    status TEXT DEFAULT 'active',
    source_chapter INTEGER,
    last_changed_chapter INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE story_fact_events (
    id TEXT PRIMARY KEY,
    fact_id TEXT,
    project_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    run_id TEXT,
    event_type TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT,
    evidence_text TEXT,
    rationale TEXT,
    validation_status TEXT DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 4. Workflow 集成

章节生成链路调整为：

```text
context_readiness
  -> planner
  -> screenwriter
  -> author
  -> polisher
  -> editor
  -> memory_curator
  -> continuity_gate
  -> awaiting_publish / blocking
```

规则：

- `planner` 必须读取项目资料和当前有效 facts。
- `screenwriter` 输出本章预期使用的角色、设定、伏笔、事实。
- `author` 输出观察到的事实变化。
- `polisher` 不得无意改变关键事实。
- `editor` 必须审核字数、指令覆盖、上下文、风格和连续性。
- `memory_curator` 生成 memory patch。
- `continuity_gate` 检查 memory patch 是否与既有事实冲突。
- 真实模式下，有高风险冲突时不得进入 `awaiting_publish`，必须进入 `blocking` 或待人工处理。
- Stub 模式生成确定性 patch，便于验收。

### 5. WebUI 信息架构

项目总览新增：

- “生成项目设定”主按钮。
- 上下文准备度卡片中，如果缺世界观/角色/指令，优先引导 Genesis，而不是只引导手填。
- “待确认记忆更新”入口。

项目级新增模块：

- `项目创世`：查看 genesis 输入、草案、批准状态。
- `记忆更新`：按批次查看待应用 memory patch。
- `事实账本`：查看当前 facts 和历史 events。

章节工作区新增：

- “本章记忆变更”Tab。
- “本章继承事实”区块。
- “连续性检查”区块。
- 发布前显示：是否有待确认记忆更新、是否有事实冲突。

### 6. CLI 对齐

WebUI 不能独有核心能力。CLI 需要新增：

- `novelos genesis generate PROJECT_ID`
- `novelos genesis show PROJECT_ID`
- `novelos genesis approve PROJECT_ID`
- `novelos memory list PROJECT_ID`
- `novelos memory apply PROJECT_ID BATCH_ID`
- `novelos facts list PROJECT_ID`
- `novelos facts history PROJECT_ID FACT_KEY`

章节生成 CLI 与 WebUI 使用同一套 workflow、memory patch、continuity gate。

## 分阶段实施

### Phase A：Genesis API + 草案数据模型

- 新增 `genesis_runs` 表和 repository。
- 新增 Genesis API。
- Stub/real LLM 都能生成结构化草案。
- 草案 approval 能写入 `projects / world_settings / characters / factions / outlines / plot_holes / instructions`。

验收：

- 空项目调用 Genesis 后，Context Readiness Gate 缺失项明显减少或通过。
- 已有资料不会被静默覆盖。

### Phase B：Genesis WebUI

- 项目总览增加“生成项目设定”入口。
- 新增 Genesis 草案审核页面。
- 缺失项 remediation 优先引导 Genesis。

验收：

- 新用户可以从一句创意进入项目骨架生成。
- 用户能逐项审阅并批准写库。

### Phase C：Memory Patch 基础链路

- 新增 `memory_update_batches/items`。
- workflow 加入 `memory_curator`。
- 章节生成后产出待确认 memory patch。
- Stub 模式可稳定生成示例 patch。

验收：

- 章节出现新角色时，会生成角色新增 patch。
- 章节埋下伏笔时，会生成 plot_hole patch。
- patch 不批准时，不写正式资料表。

### Phase D：Fact Ledger 最小闭环

- 新增 `story_facts/story_fact_events`。
- ContextBuilder 读取 active facts。
- Memory patch 可生成 fact events。
- Continuity gate 检查基础冲突。

验收：

- 前章获得的道具/伤势/地点能在后章上下文中继承。
- 明显冲突会阻止发布或要求人工确认。

### Phase E：WebUI Memory & Facts

- 新增“记忆更新”模块。
- 新增“事实账本”模块。
- 章节工作区展示本章继承事实、变更事实、冲突。

验收：

- 用户能看懂每章之后系统准备改哪些设定。
- 用户能接受、编辑、忽略 memory patch。
- 用户能追溯某个事实从哪章产生、哪章变化。

## 测试要求

新增测试文件建议：

- `tests/test_v532_project_genesis.py`
- `tests/test_v532_memory_loop.py`
- `tests/test_v532_fact_ledger.py`
- `tests/test_v532_frontend_contract.py`

必须覆盖：

- Genesis 草案生成、批准、拒绝。
- Genesis 不覆盖已批准资料。
- Context Gate 缺失项可通过 Genesis 补齐。
- Memory patch 生成后默认 pending。
- Apply patch 后目标表变化正确。
- Ignore patch 后目标表不变。
- Fact event 写入和 history 查询。
- Continuity gate 检出明显冲突。
- WebUI 不再让用户只能手填世界观/角色/大纲。

## 非目标

- 不要求一次实现完整专业级知识图谱。
- 不要求所有事实类型都自动准确抽取。
- 不要求 AI 自动发布记忆更新。
- 不要求替代人工编辑，人工确认仍是可信链路的一部分。

## 完成定义

v5.3.2 完成时，用户应该能完成这条主路径：

1. 创建项目，只输入一句创意。
2. 点击“生成项目设定”。
3. 审阅并批准项目圣经草案。
4. 生成章节。
5. 查看本章产生的记忆更新。
6. 批准/编辑/忽略记忆更新。
7. 在后续章节中看到角色、世界观、伏笔和事实被继承。

如果世界观、角色、大纲、伏笔、章节指令仍然主要依赖用户手动维护，v5.3.2 就不能算完成。
