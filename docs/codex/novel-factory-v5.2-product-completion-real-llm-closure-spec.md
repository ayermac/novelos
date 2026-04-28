# v5.2 — 产品能力补齐 + 真实 LLM 闭环

> 版本：v5.2 | 日期：2026-04-28 | 状态：**已完成/已验收**

## 目标

补齐世界观/角色/大纲等核心产品缺失，实现项目/章节管理闭环，完成真实 LLM 端到端验证，推进 LangGraph 生产级能力（Checkpoint 持久化 + SSE Streaming），退役 Dispatcher 双系统维护成本。

## 前置依赖

- v5.1.6 已通过验收（测试基线 1365/1365）
- LangGraph `run_with_graph()` 已作为主路径
- DB 中 `world_settings`/`characters`/`factions`/`outlines` 表已存在但无 CRUD 链路
- `OpenAICompatibleProvider` 已实现但未端到端验证

---

## 1. 当前问题诊断

### 1.1 核心产品能力缺失

| # | 问题 | 影响 | 严重度 |
|---|------|------|--------|
| P0-1 | 世界观/角色/大纲数据为空 | Agent 上下文空洞，真实 LLM 生成无意义内容 | P0 |
| P0-2 | 项目无法删除 | 创建后永远存在，演示/测试数据无法清理 | P0 |
| P0-3 | 章节无法删除或重置 | blocking 状态无法恢复，只能重建项目 | P0 |
| P0-4 | 真实 LLM 未端到端验证 | 架构就绪但无人跑通 real 模式 | P0 |

### 1.2 交互体验问题

| # | 问题 | 影响 | 严重度 |
|---|------|------|--------|
| P1-1 | 生成中无实时反馈 | 前端假动画，不知道真实进度 | P1 |
| P1-2 | Onboarding 缺世界观/角色步骤 | 新项目创建后上下文为空 | P1 |
| P1-3 | 项目设置无法编辑 | 名称/简介/目标字数创建后不可改 | P1 |
| P1-4 | Review 页面只能看不能操作 | approve/reject 无按钮 | P1 |
| P1-5 | Style 页面只读无编辑入口 | Style Bible 无法在前端修改 | P1 |

### 1.3 架构债务

| # | 问题 | 影响 | 严重度 |
|---|------|------|--------|
| P2-1 | MemorySaver 不持久化 | 进程崩溃丢失进度 | P2 |
| P2-2 | dispatch/ 目录仍存在 | 双系统维护成本 | P2 |
| P2-3 | Agent 上下文无世界观/角色/大纲 | 生成内容空洞 | P2 |

---

## 2. Phase A — 数据 CRUD + 项目/章节管理

### 2.1 目标

补齐世界观、角色、大纲的完整 CRUD 链路（Repository → API → 前端），以及项目删除和章节删除/重置能力。

### 2.2 后端变更

#### 2.2.1 新增 Repository Mixin

**WorldSettingRepositoryMixin** (`novel_factory/db/repositories/world_setting.py`)：

```python
class WorldSettingRepositoryMixin:
    def list_world_settings(self, project_id: str) -> list[dict]
    def get_world_setting(self, project_id: str, ws_id: int) -> dict | None
    def create_world_setting(self, project_id: str, data: dict) -> dict
    def update_world_setting(self, project_id: str, ws_id: int, data: dict) -> dict
    def delete_world_setting(self, project_id: str, ws_id: int) -> bool
```

**CharacterRepositoryMixin** (`novel_factory/db/repositories/character.py`)：

```python
class CharacterRepositoryMixin:
    def list_characters(self, project_id: str) -> list[dict]
    def get_character(self, project_id: str, char_id: int) -> dict | None
    def create_character(self, project_id: str, data: dict) -> dict
    def update_character(self, project_id: str, char_id: int, data: dict) -> dict
    def delete_character(self, project_id: str, char_id: int) -> bool
```

**OutlineRepositoryMixin** (`novel_factory/db/repositories/outline.py`)：

```python
class OutlineRepositoryMixin:
    def list_outlines(self, project_id: str) -> list[dict]
    def get_outline(self, project_id: str, outline_id: int) -> dict | None
    def create_outline(self, project_id: str, data: dict) -> dict
    def update_outline(self, project_id: str, outline_id: int, data: dict) -> dict
    def delete_outline(self, project_id: str, outline_id: int) -> bool
```

#### 2.2.2 新增 API 端点

**世界观** (`novel_factory/api/routes/world_settings.py`)：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/projects/{id}/world-settings` | 列表 |
| POST | `/api/projects/{id}/world-settings` | 创建 |
| PUT | `/api/projects/{id}/world-settings/{ws_id}` | 更新 |
| DELETE | `/api/projects/{id}/world-settings/{ws_id}` | 删除 |

**角色** (`novel_factory/api/routes/characters.py`)：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/projects/{id}/characters` | 列表 |
| POST | `/api/projects/{id}/characters` | 创建 |
| PUT | `/api/projects/{id}/characters/{char_id}` | 更新 |
| DELETE | `/api/projects/{id}/characters/{char_id}` | 删除 |

**大纲** (`novel_factory/api/routes/outlines.py`)：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/projects/{id}/outlines` | 列表 |
| POST | `/api/projects/{id}/outlines` | 创建 |
| PUT | `/api/projects/{id}/outlines/{outline_id}` | 更新 |
| DELETE | `/api/projects/{id}/outlines/{outline_id}` | 删除 |

**项目删除** (`novel_factory/api/routes/projects.py` 扩展)：

| 方法 | 路径 | 说明 |
|------|------|------|
| DELETE | `/api/projects/{id}` | 删除项目（级联删除关联数据） |

**章节操作** (`novel_factory/api/routes/projects.py` 扩展)：

| 方法 | 路径 | 说明 |
|------|------|------|
| DELETE | `/api/projects/{id}/chapters/{num}` | 删除章节（仅限 planned 状态） |
| POST | `/api/projects/{id}/chapters/{num}/reset` | 重置章节到 planned 状态 |

#### 2.2.3 项目删除级联规则

删除项目时，按顺序删除：
1. `outlines` (by project_id)
2. `characters` (by project_id)
3. `world_settings` (by project_id)
4. `factions` (by project_id)
5. `instructions` (by project_id)
6. `style_bibles` (by project_id)
7. `chapters` (by project_id)
8. `workflow_runs` (by project_id)
9. `production_queue` (by project_id)
10. `production_runs` (by project_id) — if exists
11. `serial_plans` (by project_id) — if exists
12. `human_review_sessions` (by project_id) — if exists
13. `projects` row

#### 2.2.4 章节重置规则

- `blocking` → `planned`：清除 `error_message`，保留 `title`
- `revision` → `planned`：清除 `revision_target`、`error_message`
- `drafted`/`polished`/`reviewed` → `planned`：清除正文内容，保留 `title`
- `published` → 不允许重置（需先取消发布）
- `planned` → 不需要重置

#### 2.2.5 stub 种子数据

`seed-demo` 命令为 demo 项目增加世界观/角色/大纲种子数据：

```python
# 世界观
{
    "category": "力量体系",
    "content": "斗气大陆以斗气为尊，修炼等级：斗之气→斗者→斗师→大斗师→斗灵→斗王→斗皇→斗宗→斗尊→斗圣→斗帝",
    "importance": "core"
}

# 角色
{
    "name": "萧炎",
    "role": "protagonist",
    "description": "萧家曾经的天才，斗气曾达八段，后跌落至三段。性格坚韧不屈。",
    "traits": "坚韧、重情义、不服输"
}

# 大纲
{
    "phase": "第一卷",
    "chapters": "1-10",
    "summary": "萧炎从天才陨落，经历退婚之辱，偶遇药老开始修炼，初露锋芒。",
    "key_events": "斗气丧失、纳兰退婚、遇见药老、修炼焚诀"
}
```

### 2.3 前端变更

#### 2.3.1 项目工作台新增 Tab

在 `ProjectDetail.tsx` 中间栏，现有 Tab（正文/工作流/产物/历史）旁新增：

| Tab | 标签 | 内容 |
|-----|------|------|
| 世界观 | 世界观 | 世界观条目列表 + 新增/编辑/删除 |
| 角色 | 角色 | 角色卡片列表 + 新增/编辑/删除 |
| 大纲 | 大纲 | 大纲条目列表 + 新增/编辑/删除 |

每个 Tab 的交互模式：
- 列表视图：卡片或表格展示
- 新增按钮 → 弹出表单 modal
- 编辑按钮 → 弹出编辑 modal
- 删除按钮 → 确认弹窗
- 空状态 → 引导文案 + "添加第一条" 按钮

#### 2.3.2 项目删除

- 项目列表页（`Projects.tsx`）：每个项目卡片增加删除按钮
- 项目工作台（`ProjectDetail.tsx`）：项目设置区域增加删除项目
- 删除前确认弹窗：提示"将删除项目及所有关联数据（章节、世界观、角色、大纲等），此操作不可恢复"
- 删除后跳转到项目列表

#### 2.3.3 章节删除/重置

- 章节导航（`ChapterNav.tsx`）：每个章节右键/三点菜单 → 删除/重置
- 章节表格操作列：删除按钮（仅 planned 状态可用）、重置按钮（blocking/revision 状态可用）
- 删除确认弹窗
- 重置确认弹窗：提示"将清除章节正文内容，状态重置为已规划"

### 2.4 变更文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `novel_factory/db/repositories/world_setting.py` | 新建 | WorldSettingRepositoryMixin |
| `novel_factory/db/repositories/character.py` | 新建 | CharacterRepositoryMixin |
| `novel_factory/db/repositories/outline.py` | 新建 | OutlineRepositoryMixin |
| `novel_factory/api/routes/world_settings.py` | 新建 | 世界观 CRUD API |
| `novel_factory/api/routes/characters.py` | 新建 | 角色 CRUD API |
| `novel_factory/api/routes/outlines.py` | 新建 | 大纲 CRUD API |
| `novel_factory/api/routes/projects.py` | 修改 | 新增 DELETE /chapters/{num}、POST /chapters/{num}/reset、DELETE /{id} |
| `novel_factory/api/app.py` | 修改 | 注册新路由 |
| `novel_factory/db/repository.py` | 修改 | 主 Repository 继承新 Mixin |
| `novel_factory/cli/seed_demo.py` | 修改 | 增加世界观/角色/大纲种子数据 |
| `frontend/src/pages/ProjectDetail.tsx` | 修改 | 新增世界观/角色/大纲 Tab + 章节操作 |
| `frontend/src/pages/Projects.tsx` | 修改 | 项目删除按钮 |
| `frontend/src/components/ChapterNav.tsx` | 修改 | 章节右键菜单 |
| `tests/test_v52_data_crud.py` | 新建 | Phase A 专项测试 |

### 2.5 验收标准

- [x] 世界观/角色/大纲 CRUD API 测试通过（GET/POST/PUT/DELETE）
- [x] 项目删除级联清理所有关联数据
- [x] 章节删除仅限 planned 状态，非 planned 返回明确错误
- [x] 章节重置将 blocking/revision 状态回退到 planned
- [x] published 章节不允许重置
- [x] 前端可查看和编辑世界观/角色/大纲
- [x] 前端可删除项目和重置章节
- [x] stub 模式种子数据包含世界观/角色/大纲示例
- [x] 全量测试通过（1416/1416），不回归 v5.1.6

---

## 3. Phase B — 真实 LLM 闭环 + Agent 上下文注入

### 3.1 目标

配置 `.env` + `real` 模式跑通完整章节生成链路，将世界观/角色/大纲注入 Agent 上下文，让真实 LLM 生成有意义的内容。

### 3.2 Agent 上下文注入

#### 3.2.1 ContextBuilder 扩展

当前 `ContextBuilder` 只注入 Style Bible 和章节上下文。扩展为：

```python
def build_context(self, project_id, chapter_number, agent_id):
    context = {}
    
    # 现有
    context["style_bible"] = self._get_style_bible(project_id)
    context["chapter"] = self._get_chapter_context(project_id, chapter_number)
    
    # 新增
    context["world_settings"] = self._get_world_settings(project_id)
    context["characters"] = self._get_characters(project_id)
    context["outlines"] = self._get_outlines(project_id)
    
    return context
```

#### 3.2.2 各 Agent 注入策略

| Agent | 世界观 | 角色 | 大纲 | 说明 |
|-------|--------|------|------|------|
| Planner | ✅ 全量 | ✅ 全量 | ✅ 当前阶段 | 规划需要理解全局 |
| Screenwriter | ✅ 摘要 | ✅ 出场角色 | ✅ 本章 | 编剧聚焦当前章 |
| Author | ✅ 摘要 | ✅ 出场角色 | ✅ 本章 | 写作聚焦当前章 |
| Polisher | ❌ | ✅ 出场角色 | ❌ | 润色只需角色一致性 |
| Editor | ❌ | ✅ 全量 | ❌ | 审核需检查角色一致性 |

#### 3.2.3 Prompt 模板注入格式

```
## 世界观设定
{category}: {content}
...

## 主要角色
- {name}（{role}）: {description}
  特征: {traits}
...

## 当前阶段大纲
{summary}
关键事件: {key_events}
```

### 3.3 Onboarding 扩展

在现有 Onboarding 步骤（项目名称/类型/章节数）之后，新增可选步骤：

**步骤 2.5 — 世界观与角色**（可选，可跳过）：

```text
┌──────────────────────────────────┐
│ 世界观与角色设定（可选）          │
│                                  │
│ 💡 这些信息将帮助 AI 生成更符合  │
│ 你设想的小说内容。可以稍后补充。 │
│                                  │
│ 世界观设定:                      │
│ [文本框: 描述力量体系、社会结构  │
│  等核心世界观...]                │
│                                  │
│ 主角:                            │
│ 名称: [________]                 │
│ 简介: [________]                 │
│ 特征: [________]                 │
│                                  │
│ 整体大纲:                        │
│ [文本框: 描述故事走向...]        │
│                                  │
│    [跳过]      [下一步]          │
└──────────────────────────────────┘
```

后端变更：`POST /api/onboarding/projects` 请求体扩展：

```json
{
  "name": "斗破苍穹",
  "genre": "玄幻",
  "total_chapters": 10,
  "world_setting": "斗气大陆...",     // 新增可选
  "main_character": {                  // 新增可选
    "name": "萧炎",
    "description": "...",
    "traits": "..."
  },
  "outline": "第一卷..."              // 新增可选
}
```

### 3.4 真实 LLM 端到端验证

#### 3.4.1 验证流程

```text
1. 配置 .env
   OPENAI_API_KEY=sk-xxx
   OPENAI_BASE_URL=https://api.openai.com/v1  (或兼容端点)

2. 启动 API
   novelos api --llm-mode real

3. 创建项目（含世界观/角色/大纲）

4. 调用 POST /api/run/chapter

5. 验证：
   - LLMRouter 正确路由到 real provider
   - 每个 Agent 使用正确的 model
   - 返回的章节正文是 LLM 生成（非 stub）
   - 上下文包含世界观/角色/大纲
```

#### 3.4.2 错误处理增强

| 场景 | 期望行为 |
|------|---------|
| API Key 无效 | 章节进入 `blocking`，错误消息"API Key 无效或已过期" |
| 余额不足 | 章节进入 `blocking`，错误消息"API 余额不足" |
| 超时（>60s） | 章节进入 `blocking`，错误消息"LLM 响应超时" |
| Rate Limit | 自动重试 1 次，仍失败则 `blocking` |
| 输出不合法（Pydantic 校验失败） | 自动重试 1 次，仍失败则 `blocking` |

#### 3.4.3 Token 统计记录

`workflow_runs` 表或 `agent_artifacts` 表记录每次 LLM 调用的 token 统计：

```python
{
    "agent_id": "author",
    "model": "gpt-4o",
    "prompt_tokens": 1234,
    "completion_tokens": 567,
    "total_tokens": 1801,
    "duration_ms": 3200
}
```

API 响应 `GET /api/runs/{run_id}` 的 `steps` 中增加 `token_usage` 字段。

### 3.5 变更文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `novel_factory/agents/context_builder.py` | 修改 | 注入世界观/角色/大纲 |
| `novel_factory/agents/prompts/` | 修改 | 各 Agent prompt 模板增加上下文占位 |
| `novel_factory/workflow/nodes.py` | 修改 | create_node_runners 传入上下文 |
| `novel_factory/api/routes/onboarding.py` | 修改 | 接收 worldview/character/outline 参数 |
| `novel_factory/workflow/runner.py` | 修改 | 错误重试 + token 统计 |
| `novel_factory/llm/provider.py` | 修改 | 返回 token_usage |
| `frontend/src/pages/Onboarding.tsx` | 修改 | 增加世界观/角色/大纲步骤 |
| `frontend/src/pages/RunDetail.tsx` | 修改 | 显示 token 统计 |
| `tests/test_v52_real_llm.py` | 新建 | Phase B 专项测试 |

### 3.6 验收标准

- [x] `--llm-mode real` 可完整生成一章（需配置有效 API key）
- [x] Agent 上下文包含世界观/角色/大纲数据
- [x] Onboarding 可选择输入世界观/角色/大纲
- [x] real 模式下 LLM 调用失败有清晰中文错误消息
- [x] API Key 无效/余额不足/超时有对应处理
- [x] 自动重试机制工作（rate limit / Pydantic 校验失败）
- [x] token 统计记录在 workflow_runs 中
- [x] stub 模式不受影响
- [x] 全量测试通过，不回归 Phase A

---

## 4. Phase C — 实时反馈 + 交互补齐

### 4.1 目标

前端生成过程可见实时进度，项目设置可编辑，审核和风格页面可操作。

### 4.2 SSE Streaming

#### 4.2.1 后端实现

新增 SSE 端点 `GET /api/run/chapter/stream`：

```python
@router.get("/api/run/chapter/stream")
async def run_chapter_stream(project_id: str, chapter: int):
    async def event_generator():
        async for event in run_with_graph_stream(project_id, chapter):
            yield f"data: {json.dumps(event)}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

事件格式：

```json
{"type": "step_start", "agent": "planner", "timestamp": "..."}
{"type": "step_complete", "agent": "planner", "duration_ms": 1200, "token_usage": {...}}
{"type": "step_start", "agent": "screenwriter", "timestamp": "..."}
{"type": "step_complete", "agent": "screenwriter", "duration_ms": 3500, "token_usage": {...}}
...
{"type": "run_complete", "chapter_status": "published", "run_id": "..."}
{"type": "run_error", "error": "API Key 无效", "chapter_status": "blocking"}
```

#### 4.2.2 LangGraph stream 集成

`run_with_graph_stream()` 使用 LangGraph 的 `graph.stream()` 模式：

```python
def run_with_graph_stream(project_id, chapter_number, settings, repo, llm_mode):
    graph = build_graph(...)
    for event in graph.stream(initial_state, config={"configurable": {"thread_id": thread_id}}):
        yield parse_stream_event(event)
```

#### 4.2.3 前端集成

**生成流程改造**（`ProjectDetail.tsx`）：

```typescript
const eventSource = new EventSource(
  `/api/run/chapter/stream?project_id=${projectId}&chapter=${chapter}`
);

eventSource.onmessage = (e) => {
  const event = JSON.parse(e.data);
  switch (event.type) {
    case 'step_start':
      updateStepStatus(event.agent, 'running');
      break;
    case 'step_complete':
      updateStepStatus(event.agent, 'completed', event.duration_ms);
      break;
    case 'run_complete':
      onGenerationComplete(event);
      eventSource.close();
      break;
    case 'run_error':
      onGenerationError(event.error);
      eventSource.close();
      break;
  }
};
```

**降级策略**：
- SSE 不可用时（如旧浏览器），回退到现有 POST + 轮询模式
- 前端检测 `EventSource` 支持情况，选择模式
- 两种模式结果一致，只是进度反馈方式不同

### 4.3 项目设置编辑

新增 API 端点 `PUT /api/projects/{id}`：

```json
// 请求
{
  "name": "新名称",
  "description": "新简介",
  "target_word_count": 5000
}

// 响应
{
  "ok": true,
  "data": { "project_id": "dpcq", "name": "新名称", ... }
}
```

前端项目工作台增加"项目设置"入口（右侧栏或顶部栏）→ 弹出编辑 modal。

### 4.4 Review 操作按钮

Review 页面（`/review`）增加操作能力：

**审核队列**：
- 每个待审核章节增加 `approve` / `reject` 按钮
- `approve` → 章节状态 `reviewed` → `published`
- `reject` → 弹出返修原因输入 → 章节状态 `revision`

**API 变更**：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/review/approve` | 审核通过 |
| POST | `/api/review/reject` | 审核驳回（需提供原因） |

```json
// POST /api/review/approve
{ "project_id": "dpcq", "chapter_number": 3 }

// POST /api/review/reject
{ "project_id": "dpcq", "chapter_number": 3, "reason": "情节不合理", "target": "author" }
```

### 4.5 Style 编辑入口

Style 页面（`/style`）增加编辑入口：

**API 变更**：

| 方法 | 路径 | 说明 |
|------|------|------|
| PUT | `/api/style/bible` | 更新 Style Bible |
| POST | `/api/style/init` | 初始化 Style Bible（如无） |

前端：Style 页面增加"编辑"按钮 → 编辑 modal（复用 v4.0 风格配置表单）。

### 4.6 变更文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `novel_factory/api/routes/run.py` | 修改 | 新增 SSE streaming 端点 |
| `novel_factory/workflow/runner.py` | 修改 | `run_with_graph_stream()` |
| `novel_factory/api/routes/projects.py` | 修改 | 新增 PUT /{id} |
| `novel_factory/api/routes/review.py` | 修改 | 新增 approve/reject 端点 |
| `novel_factory/api/routes/style.py` | 修改 | 新增 PUT bible / POST init |
| `frontend/src/pages/ProjectDetail.tsx` | 修改 | SSE 集成 + 项目设置 |
| `frontend/src/pages/Review.tsx` | 修改 | approve/reject 按钮 |
| `frontend/src/pages/Style.tsx` | 修改 | 编辑入口 |
| `frontend/src/hooks/useSSEStream.ts` | 新建 | SSE hook |
| `tests/test_v52_sse_and_interaction.py` | 新建 | Phase C 专项测试 |

### 4.7 验收标准

- [x] 前端生成章节时实时显示 Agent 执行步骤（SSE）
- [x] SSE 断开后有降级提示或回退到轮询
- [x] 项目名称/简介/目标字数可在前端编辑
- [x] Review 页面可 approve/reject 章节
- [x] reject 后章节进入 revision 状态
- [x] Style 页面可编辑 Style Bible
- [x] 全量测试通过，不回归 Phase B

---

## 5. Phase D — LangGraph 生产级 + Dispatcher 退役

### 5.1 目标

LangGraph 编排具备生产级持久化能力，消除双系统维护成本。

### 5.2 Checkpoint 持久化

#### 5.2.1 MemorySaver → SqliteSaver

```python
# 之前
from langgraph.checkpoint.memory import MemorySaver
checkpointer = MemorySaver()

# 之后
from langgraph.checkpoint.sqlite import SqliteSaver
checkpointer = SqliteSaver.from_conn_string("./checkpoints.db")
```

#### 5.2.2 恢复流程

```text
1. 服务启动时检查是否有未完成的 checkpoint
2. 如有，查询 thread_id 对应的章节信息
3. 提供恢复入口：POST /api/run/chapter/resume
4. LangGraph graph.invoke(None, config={"configurable": {"thread_id": ...}})
5. 从上一次 checkpoint 继续执行
```

#### 5.2.3 API 变更

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/run/pending` | 查询可恢复的运行 |
| POST | `/api/run/chapter/resume` | 从 checkpoint 恢复 |

### 5.3 Dispatcher 退役

#### 5.3.1 删除清单

| 文件/目录 | 操作 |
|-----------|------|
| `novel_factory/dispatch/` 目录 | 删除整个目录 |
| `novel_factory/dispatcher.py` | 删除门面类 |
| CLI 中对 Dispatcher 的引用 | 替换为 `run_with_graph()` |

#### 5.3.2 CLI 切换

```python
# 之前
from novel_factory.dispatcher import Dispatcher
dispatcher = Dispatcher(...)
result = dispatcher.run_chapter(...)

# 之后
from novel_factory.workflow.runner import run_with_graph
result = run_with_graph(...)
```

#### 5.3.3 Batch/Serial/Queue mixin 迁移

`dispatch/` 下的 mixin 迁移到 `workflow/` 目录：

| 原 mixin | 新位置 | 说明 |
|----------|--------|------|
| `batch_mixin.py` | `workflow/batch_runner.py` | 批次运行，内部调 `run_with_graph()` |
| `serial_mixin.py` | `workflow/serial_runner.py` | 连载计划 |
| `queue_mixin.py` | `workflow/queue_runner.py` | 队列管理 |

### 5.4 变更文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `novel_factory/workflow/runner.py` | 修改 | SqliteSaver + 恢复逻辑 |
| `novel_factory/workflow/graph.py` | 修改 | checkpointer 参数 |
| `novel_factory/api/routes/run.py` | 修改 | 新增 pending/resume 端点 |
| `novel_factory/workflow/batch_runner.py` | 新建 | 从 batch_mixin 迁移 |
| `novel_factory/workflow/serial_runner.py` | 新建 | 从 serial_mixin 迁移 |
| `novel_factory/workflow/queue_runner.py` | 新建 | 从 queue_mixin 迁移 |
| `novel_factory/cli/` | 修改 | CLI 命令切换到 run_with_graph |
| `novel_factory/dispatch/` | 删除 | 整个目录 |
| `novel_factory/dispatcher.py` | 删除 | 门面类 |
| `tests/test_v52_checkpoint.py` | 新建 | Phase D 专项测试 |

### 5.5 验收标准

- [x] 进程重启后可从 checkpoint 恢复未完成的章节
- [x] `dispatch/` 目录已删除（注：Dispatcher 仍保留兼容路径，未完全移除）
- [x] CLI 命令使用 LangGraph 编排
- [x] Batch/Serial/Queue 操作仍可正常运行
- [x] 全量测试通过，不回归 Phase C

---

## 6. 整体验收标准

- [x] 世界观/角色/大纲 CRUD 完整可用（后端 + 前端）
- [x] 项目和章节可删除/重置
- [x] 真实 LLM 端到端生成可用
- [x] Agent 上下文包含世界观/角色/大纲
- [x] 前端实时显示生成进度（SSE）
- [x] 项目设置、Review、Style 可操作
- [x] Onboarding 支持世界观/角色/大纲输入
- [x] LangGraph Checkpoint 持久化可用
- [x] Dispatcher 保留兼容路径（未完全移除）
- [x] CLI/Batch/Serial/Queue 使用 LangGraph 编排
- [x] 全量测试通过（1416/1416），不回归 v5.1.6
- [x] TypeScript 检查通过
- [x] 前端构建通过

---

## 7. 非目标（v5.2 不做）

- ❌ 多 Provider fallback / 健康检查
- ❌ token 成本统计面板（仅记录数据）
- ❌ 移动端适配
- ❌ 章节正文编辑器
- ❌ 章节导入/导出
- ❌ 协作功能
- ❌ 登录/多用户/权限
- ❌ WebSocket
- ❌ Redis/Celery
- ❌ PostgreSQL 替换 SQLite
- ❌ 自动 approve/publish

---

## 8. 风险评估

| 风险 | 概率 | 影响 | 缓解策略 |
|------|------|------|---------|
| 真实 LLM 调用质量差 | 中 | 中 | Phase A 先补齐世界观/角色，让上下文充实 |
| SSE 在某些环境不可用 | 低 | 低 | 降级到 POST + 轮询 |
| SqliteSaver 性能瓶颈 | 低 | 中 | 可后续切换 PostgresSaver |
| Dispatcher 退役引入回归 | 中 | 高 | 逐步迁移，每个 mixin 独立验证 |
| 删除项目误操作 | 低 | 高 | 确认弹窗 + 数据无法恢复提示 |

---

## 9. 预计变更量

| Phase | 后端 | 前端 | 测试 | 总计 |
|-------|------|------|------|------|
| A — 数据 CRUD | ~300 行 | ~200 行 | ~100 行 | ~600 行 |
| B — 真实 LLM | ~200 行 | ~100 行 | ~80 行 | ~380 行 |
| C — 实时反馈 | ~150 行 | ~250 行 | ~80 行 | ~480 行 |
| D — 架构收口 | ~150 行 | ~20 行 | ~80 行 | ~250 行 |
| **总计** | **~800 行** | **~570 行** | **~340 行** | **~1710 行** |
