# v5.1 Frontend Separation & API Backend 规格

## 目标

废弃 Jinja WebUI，实现前后端分离架构，为后续扩展和部署灵活性打下基础。

## 背景

v5.0.1 完成了 WebUI 的产品化和中文化，但仍然是基于 Jinja 模板的单体应用。为了：
- 支持独立的前端部署和开发
- 提供标准化的 JSON API 接口
- 为移动端、桌面端等客户端预留空间
- 提升开发体验和部署灵活性

决定在 v5.1 实现前后端分离。

## 核心变更

### 1. 删除/弃用 Jinja WebUI

**删除内容：**
- `novel_factory/web/templates/` - 所有 Jinja 模板
- `novel_factory/web/static/` - 静态资源（已迁移到前端）
- `novel_factory/web/routes/` - HTML 路由
- `novel_factory/web/app.py` - Web 应用工厂
- `novel_factory/web/deps.py` - Jinja 依赖
- `novel_factory/web/acceptance_matrix.py` - 旧的验收矩阵
- `novel_factory/cli_app/commands/web.py` - CLI web 命令

**保留内容：**
- `novel_factory/web/design/` - 设计原型参考
- `novel_factory/web/__init__.py` - 模块说明

### 2. FastAPI JSON API Backend

**目录结构：**
```
novel_factory/api/
├── __init__.py
├── api_app.py              # FastAPI 应用工厂
├── envelope.py             # 信封响应模型
├── deps.py                 # 依赖注入
├── acceptance.py           # v5.1 验收矩阵
└── routes/
    ├── health.py           # GET /api/health
    ├── dashboard.py        # GET /api/dashboard
    ├── projects.py         # 项目 CRUD
    ├── onboarding.py       # POST /api/onboarding/projects
    ├── run.py              # POST /api/run/chapter
    ├── review.py           # 审核相关
    ├── style.py            # GET /api/style/console
    ├── settings.py         # GET /api/settings, POST /api/config/plan
    └── acceptance.py       # GET /api/acceptance
```

**信封格式：**
```json
{
  "ok": true,
  "error": null,
  "data": { ... }
}
```

**错误格式：**
```json
{
  "ok": false,
  "error": {
    "code": "PROJECT_NOT_FOUND",
    "message": "项目 'xxx' 不存在"
  },
  "data": null
}
```

**标准错误码：**
- `PROJECT_NOT_FOUND` - 项目不存在
- `CHAPTER_NOT_FOUND` - 章节不存在
- `VALIDATION_ERROR` - 输入验证失败
- `INTERNAL_ERROR` - 内部错误

**安全要求：**
- 不暴露 traceback 到响应中
- 不暴露 API key/secret 到前端
- 全局异常处理器返回 JSON 错误信封

### 3. React + Vite + TypeScript Frontend

**目录结构：**
```
frontend/
├── package.json
├── tsconfig.json
├── vite.config.ts
├── index.html
└── src/
    ├── main.tsx
    ├── index.css
    ├── App.tsx
    ├── lib/
    │   └── api.ts          # API 客户端
    ├── components/
    │   └── Layout.tsx      # 左侧导航布局
    └── pages/
        ├── Dashboard.tsx
        ├── Projects.tsx
        ├── ProjectDetail.tsx
        ├── Onboarding.tsx
        ├── Run.tsx
        ├── Review.tsx
        ├── Style.tsx
        ├── Settings.tsx
        └── Acceptance.tsx
```

**技术栈：**
- React 18
- React Router 6
- Lucide React（图标）
- Vite 5
- TypeScript 5
- Vitest（测试）

**设计系统：**
- 基于 v5.0.1 设计规范
- 左侧导航 + 主内容区布局
- CSS 变量定义设计 token
- 中文界面

**页面路由：**
- `/` - 总览（Dashboard）
- `/projects` - 项目列表
- `/projects/:id` - 项目详情
- `/onboarding` - 创建项目
- `/run` - 运行章节
- `/review` - 审核
- `/style` - 风格
- `/settings` - 配置
- `/acceptance` - 验收

### 4. API 和 CLI 共享核心服务

**原则：**
- API 不通过 shell 调用 CLI
- 两者共享 Repository、Dispatcher、Agents
- API 使用依赖注入获取服务实例

**实现：**
```python
# novel_factory/api/deps.py
def get_repo(request: Request) -> Repository:
    """Get repository from app state."""
    ...

def get_dispatcher(request: Request, llm_mode: str = "stub") -> ChapterDispatcher:
    """Build dispatcher for API."""
    ...
```

## API 端点规格

### GET /api/health

**响应：**
```json
{
  "ok": true,
  "error": null,
  "data": {
    "status": "healthy",
    "version": "5.1.0",
    "llm_mode": "stub"
  }
}
```

### GET /api/dashboard

**响应：**
```json
{
  "ok": true,
  "error": null,
  "data": {
    "project_count": 5,
    "recent_runs": [...],
    "queue_count": 3,
    "review_count": 2
  }
}
```

### POST /api/onboarding/projects

**请求：**
```json
{
  "project_id": "my-novel",
  "name": "我的小说",
  "genre": "玄幻",
  "initial_chapter_count": 10
}
```

**响应：**
```json
{
  "ok": true,
  "error": null,
  "data": {
    "project": {...},
    "chapters": [...]
  }
}
```

### POST /api/run/chapter

**请求：**
```json
{
  "project_id": "my-novel",
  "chapter": 1,
  "llm_mode": "stub"
}
```

**响应：**
```json
{
  "ok": true,
  "error": null,
  "data": {
    "run_id": "uuid",
    "project_id": "my-novel",
    "chapter": 1,
    "status": "completed",
    "llm_mode": "stub",
    "message": "章节生成完成"
  }
}
```

## 测试要求

### API 后端测试（tests/test_v51_api_backend.py）

1. **信封格式测试**
   - health 端点返回正确信封格式
   - dashboard 端点返回正确信封格式
   - projects 端点返回正确信封格式

2. **错误处理测试**
   - 项目不存在返回错误信封
   - 错误响应不包含 traceback

3. **API 安全测试**
   - settings 端点不返回 API key 值
   - health 端点不返回密钥
   - stub 模式安全（无真实 LLM 调用）

4. **运行章节测试**
   - 创建项目成功
   - stub 模式运行章节成功

5. **CRUD 操作测试**
   - 创建项目
   - 列出项目
   - 获取项目工作台

6. **配置草案测试**
   - 生成配置草案
   - 不使用真实 API key

### 前端测试（tests/test_v51_frontend_build.py）

1. **文件结构测试**
   - frontend 目录存在
   - package.json 存在
   - tsconfig.json 存在
   - vite.config.ts 存在
   - src 目录存在
   - main.tsx 存在
   - App.tsx 存在
   - index.css 存在

2. **中文标签测试**
   - Layout 组件有中文导航
   - Dashboard 页面有中文标签
   - Projects 页面有中文标签
   - Onboarding 页面有中文标签
   - Review 页面有中文标签
   - Settings 页面有中文标签

3. **构建配置测试**
   - package.json 有正确的名称和版本
   - package.json 有 React 依赖
   - package.json 有开发依赖
   - index.html 有中文 lang
   - index.html 有中文标题

## 禁止事项

- 不引入登录/多用户/权限系统
- 不引入 Redis/Celery/WebSocket
- 不新增真实 LLM 调用测试
- 不提交 config/acceptance.yaml
- 不提交 stderr.txt
- 不提交真实 API key
- API 不返回 API key 到前端

## 验收标准

- [x] API 信封格式测试通过
- [x] API 错误处理测试通过
- [x] API 安全测试通过
- [x] Stub 模式运行章节测试通过
- [x] CRUD 操作测试通过
- [x] 配置草案生成测试通过
- [x] 前端文件结构测试通过
- [x] 前端中文标签测试通过
- [x] 前端构建配置测试通过
- [x] 全量测试通过（1218/1218）

## 部署说明

### 启动 API 后端

```bash
# 使用 CLI 启动 API 服务
novelos api --host 127.0.0.1 --port 8765 --llm-mode stub

# 或使用环境变量
export NF_DB_PATH=/path/to/novel.db
export NF_CONFIG_PATH=/path/to/config.yaml
export NF_LLM_MODE=stub
novelos api
```

### 启动前端开发服务器

```bash
cd frontend
npm install
npm run dev
```

前端开发服务器会自动代理 `/api` 请求到 `http://localhost:8765`。

### 构建前端生产版本

```bash
cd frontend
npm run build
```

构建产物在 `frontend/dist/` 目录，可以部署到任何静态文件服务器。

## 后续规划

v5.2+ 将在 v5.1 的基础上：
- 支持多模型路由
- 生产治理能力
- 可观测性增强
- 数据备份与恢复
