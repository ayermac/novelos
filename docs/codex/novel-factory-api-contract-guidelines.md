# Novel Factory API Contract Guidelines

状态：规划中

适用范围：WebUI、CLI、自动化测试、后续 v5.3.2+ 新增 API。

目标：统一 Novel Factory API 风格，避免资源路径、动作命令、业务参数混用。新接口应易于前端封装、CLI 复用、审计记录、批量操作和后续兼容迁移。

## 核心原则

### 1. Resource API 和 Action API 分开设计

Resource API 表示“访问或修改某个资源”：

```http
GET    /api/projects/{project_id}
GET    /api/projects/{project_id}/characters
POST   /api/projects/{project_id}/characters
PUT    /api/projects/{project_id}/characters/{character_id}
DELETE /api/projects/{project_id}/characters/{character_id}
```

Action API 表示“执行一个动作、工作流或命令”：

```http
POST /api/run/chapter
POST /api/publish/chapter
POST /api/genesis/generate
POST /api/memory/apply
POST /api/chapters/reset
```

两者不要混用。动作 API 不应伪装成资源子路径。

### 2. GET 可以使用 path 和 query

GET 用于读取资源或查询列表。资源定位信息可以放 path，筛选、分页、排序可以放 query。

合理：

```http
GET /api/projects/{project_id}/characters
GET /api/projects/{project_id}/characters?include_inactive=true
GET /api/projects/{project_id}/memory-updates?status=pending
GET /api/projects/{project_id}/facts?type=inventory&status=active
```

GET 不应有 request body。

### 3. 创建子资源时，父资源 ID 可以在 path，创建内容必须在 body

合理：

```http
POST /api/projects/{project_id}/characters
{
  "name": "林默",
  "role": "protagonist",
  "description": "外门杂役，擅长观察规则漏洞"
}
```

这里 `project_id` 是父资源路径，角色内容在 body。

### 4. 动作型 POST 的业务参数必须在 body

动作型 POST 不要继续把 `project_id / chapter_number / run_id / batch_id / item_id` 塞进 path。它们是命令参数，应进入 request body。

推荐：

```http
POST /api/chapters/reset
{
  "project_id": "novel_26pu",
  "chapter_number": 3,
  "reason": "重跑章节"
}
```

不推荐作为新接口：

```http
POST /api/projects/{project_id}/chapters/{chapter_number}/reset
```

如果旧接口已存在，可以保留兼容，但新增 canonical route 应使用 body。

### 5. PUT/PATCH 更新字段放 body

资源 ID 可以在 path，更新内容必须在 body。

```http
PUT /api/projects/{project_id}/characters/{character_id}
{
  "description": "已进入内门",
  "status": "active"
}
```

### 6. DELETE 只适合简单资源删除

简单删除可以使用 DELETE path：

```http
DELETE /api/projects/{project_id}/characters/{character_id}
```

如果删除需要原因、审计、批量、确认、软删除策略，应改用 Action API：

```http
POST /api/characters/delete
{
  "project_id": "novel_26pu",
  "character_id": 12,
  "reason": "重复角色合并"
}
```

### 7. 所有 API 使用统一 Envelope

成功：

```json
{
  "ok": true,
  "error": null,
  "data": {}
}
```

失败：

```json
{
  "ok": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "角色名称不能为空",
    "details": {}
  },
  "data": null
}
```

前端和 CLI 不应解析 FastAPI 默认错误格式作为业务错误。

## 命名规范

### 路径命名

- 使用小写 kebab-case。
- 集合名用复数。
- 动作用动词。
- 避免混合 camelCase、snake_case。

推荐：

```http
/api/world-settings
/api/plot-holes
/api/memory-updates
/api/story-facts
```

不推荐：

```http
/api/worldSettings
/api/plot_holes
```

### Body 字段命名

Request/response JSON 字段继续使用 snake_case，与 Python/Pydantic/SQLite 字段保持一致。

```json
{
  "project_id": "novel_26pu",
  "chapter_number": 3,
  "target_words": 3000
}
```

## Canonical Routes

### 当前合理接口

这些接口风格可以保留：

```http
POST /api/run/chapter
POST /api/publish/chapter
POST /api/onboarding/projects
POST /api/review/approve
POST /api/review/reject
POST /api/config/plan
POST /api/settings/validate
```

### 资源 CRUD 保留 path-style

这些属于资源型接口，path-style 合理：

```http
GET  /api/projects/{project_id}/characters
POST /api/projects/{project_id}/characters
PUT  /api/projects/{project_id}/characters/{character_id}

GET  /api/projects/{project_id}/world-settings
POST /api/projects/{project_id}/world-settings
PUT  /api/projects/{project_id}/world-settings/{world_setting_id}

GET  /api/projects/{project_id}/outlines
POST /api/projects/{project_id}/outlines
PUT  /api/projects/{project_id}/outlines/{outline_id}
```

### 旧动作接口保留兼容但标记 deprecated

```http
POST /api/projects/{project_id}/chapters/{chapter_number}/reset
DELETE /api/projects/{project_id}/chapters/{chapter_number}
```

建议新增 canonical route：

```http
POST /api/chapters/reset
{
  "project_id": "novel_26pu",
  "chapter_number": 3,
  "reason": "重新生成"
}

POST /api/chapters/delete
{
  "project_id": "novel_26pu",
  "chapter_number": 3,
  "reason": "废弃章节槽位"
}
```

## v5.3.2 Genesis / Memory / Facts API 规范

### Genesis

```http
POST /api/genesis/generate
{
  "project_id": "novel_26pu",
  "idea": "一个凡人少年在宗门边缘发现旧时代修真体系的漏洞",
  "genre": "修仙",
  "target_words": 1500000,
  "total_chapters_planned": 500
}
```

```http
GET /api/projects/{project_id}/genesis/latest
```

```http
POST /api/genesis/approve
{
  "project_id": "novel_26pu",
  "run_id": "gen_123",
  "item_ids": ["world_1", "character_1", "outline_1"],
  "review_note": "批准第一版项目圣经"
}
```

```http
POST /api/genesis/reject
{
  "project_id": "novel_26pu",
  "run_id": "gen_123",
  "reason": "主角设定不符合预期"
}
```

### Memory Updates

```http
GET /api/projects/{project_id}/memory-updates?status=pending
GET /api/projects/{project_id}/memory-updates/{batch_id}
```

```http
POST /api/memory/apply
{
  "project_id": "novel_26pu",
  "batch_id": "mem_123",
  "item_ids": ["item_1", "item_2"],
  "review_note": "确认纳入项目设定"
}
```

```http
POST /api/memory/ignore
{
  "project_id": "novel_26pu",
  "item_id": "item_3",
  "reason": "AI 误判，本章没有新势力"
}
```

### Story Facts

```http
GET /api/projects/{project_id}/facts?status=active
GET /api/projects/{project_id}/facts/{fact_key}/history
```

人工修正事实应使用动作接口：

```http
POST /api/facts/correct
{
  "project_id": "novel_26pu",
  "fact_key": "character.linmo.cultivation_level",
  "new_value": {
    "level": "练气二层"
  },
  "reason": "第 3 章人工校正"
}
```

## 兼容迁移策略

1. 新增 canonical body-style route。
2. 保留旧 path-style route 一个版本周期。
3. 旧 route 内部调用同一 service/repository 方法，不复制逻辑。
4. 旧 route response 增加 deprecated hint。
5. 前端改用 canonical route。
6. 测试同时覆盖 canonical 和兼容 route。
7. 后续版本移除旧 route 前，需要 roadmap 明确标记。

## 测试要求

建议新增：

- `tests/test_api_contract.py`
- `tests/test_v532_api_contract.py`

必须覆盖：

- 新增 Action POST 有 Pydantic body schema。
- 前端新增动作调用不使用 path-style action route。
- 兼容 route 和 canonical route 调用同一业务结果。
- 错误响应统一 envelope。
- GET 不依赖 request body。
- Resource CRUD path-style 不被误判为违规。

## Review Checklist

开发或 review 新 API 时逐条检查：

- 这是资源接口还是动作接口？
- 如果是动作接口，业务参数是否都在 body？
- 是否存在旧 path-style route 需要兼容？
- 是否有 Pydantic request model？
- 是否返回统一 envelope？
- 前端是否通过 `frontend/src/lib/api.ts` 调用？
- CLI 是否可复用同一 API/Service 语义？
- 是否有 contract test？

## 非目标

- 不要求一次性重写所有旧 API。
- 不要求破坏现有前端调用。
- 不要求 REST 纯洁性高于产品交付。
- 不要求 DELETE 全部禁用；简单资源删除仍可使用 DELETE。

## 完成定义

当 API Contract 完成时：

- v5.3.2 新增动作接口全部使用 body-style canonical route。
- WebUI 新增动作调用全部使用 canonical route。
- 旧 path-style 动作接口有兼容和 deprecated 标记。
- Contract tests 能阻止后续新增不规范动作接口。
- 开发 agent 能从本文直接判断一个 API 应该如何设计。
