# v4.3: Web UI Acceptance Console MVP

## 背景

截至 v4.2，Novel Factory 已具备单章生产、批量生产、队列、半自动连载、Review Workbench、Style Bible、Style Gate 和 Style Sample Analyzer 等能力，但主要入口仍是 CLI。CLI 对开发和自动化友好，但不适合作为个人作者的整体验收界面。

v4.3 新增本地 Web UI 验收控制台，让个人作者可以通过浏览器查看项目状态、运行章节、管理批次/队列/连载、查看 Review Workbench，并操作 Style Bible 相关能力。

## 产品定位

Novel Factory 是一个**个人小说生产系统**，面向单个作者的本地创作工作台。

v4.3 Web UI 是：

- 本地单用户验收控制台
- CLI / Dispatcher / Repository 能力的浏览器入口
- 个人作者用于操作和验收小说生产流程的工作台

v4.3 Web UI 不是：

- SaaS 后台
- 多用户协作平台
- 权限系统
- 团队工作流系统
- CMS/发布平台

## 目标

- 提供 `novelos web` 命令启动本地 Web UI
- 通过 FastAPI + Jinja2 + HTMX 提供轻量页面
- 复用现有 Dispatcher / Repository 业务规则
- 支持个人作者从浏览器执行主要验收操作
- 所有错误页面不泄露 traceback 或 API key
- 保持本地 SQLite、单用户、无后台 worker 的简单部署形态

## 范围

### Web App

- `novel_factory/web/app.py`: 创建 FastAPI app
- `novel_factory/web/deps.py`: 获取 DB、settings、dispatcher、模板渲染
- `novel_factory/web/routes/`: 页面路由模块
- `novel_factory/web/templates/`: Jinja2 模板
- `novel_factory/web/static/`: CSS / JS

### 页面

- Dashboard: 系统状态、最近 run、queue、samples、proposals
- Projects: 项目列表与项目详情
- Run: 单章运行
- Batch: 批量生产与人工审核
- Queue: 队列查看与操作
- Serial: 连载计划基础操作
- Review: review pack / chapter / timeline / diff / export
- Style: Style Bible / Gate / Samples / Proposals
- Config: 配置查看，API key 脱敏

### CLI

新增：

```bash
novelos web --host 127.0.0.1 --port 8765 --db-path ./novel_factory.db --llm-mode stub
```

默认 `--llm-mode stub`，方便本地验收。

## 关键设计

### 复用 Dispatcher

Web 路由不得重新实现主业务流程。需要运行章节、批次、队列、连载、review 等操作时，通过：

```python
build_dispatcher_for_web(request)
```

内部复用 CLI 的 `_build_dispatcher(repo, settings, mode)`，确保 LLMRouter、SkillRegistry、QualityHub 等路径不被绕过。

### 复用 Repository

只读展示和 Style 轻操作可以直接使用当前 Web DB 对应的 Repository。

禁止伪造 CLI `Namespace` 调用 CLI handler，因为这容易丢失当前 Web app 的 `db_path/config/llm_mode`。

### 错误处理

- 页面错误通过 `safe_error_message()` 显示
- 不输出 Python traceback
- 不输出 API key
- POST 失败时仍渲染页面上下文

### 打包资源

`pyproject.toml` 必须包含：

```toml
web/templates/**/*.html
web/static/**/*
```

保证安装后的 `novelos web` 可以找到模板和静态资源。

## 测试计划

1. `create_app()` 可创建 FastAPI app
2. app state 包含 db_path/config_path/llm_mode
3. `/` dashboard 返回 200 且无 traceback
4. `/projects` 返回 200
5. `/run` 返回 200
6. `POST /run/chapter` 使用 stub 跑通并改变章节状态
7. `/batch` 返回 200
8. `/queue` 返回 200
9. `/serial` 返回 200
10. `/review` 返回 200
11. `/style` 返回 200
12. `POST /style/init` 写入当前 Web DB
13. `POST /style/gate-set` 写入 `blocking_threshold`
14. `POST /style/proposal-decide` 将 approve/reject 映射为 approved/rejected
15. Style 页面展示 pending proposals
16. `/config` 不泄露 API key
17. 错误页面不包含 traceback
18. `novelos web --help` 可用
19. package-data 包含 templates/static
20. 全量测试通过
21. 文件大小策略通过

## 禁止范围

- 不实现登录/注册
- 不实现用户/角色/权限/RBAC/OAuth/session
- 不实现多用户协作、团队空间、租户隔离
- 不实现 WebSocket
- 不实现 daemon/cron/background worker
- 不引入 Redis/Celery/Kafka/PostgreSQL
- 不替换 SQLite
- 不新增真实 LLM 调用测试
- 不绕过 Dispatcher/Repository 业务规则
- 不自动 approve
- 不自动 publish
- 不暴露 API key
- 不提交本地 config/acceptance.yaml、stderr.txt 或真实密钥

## 验收结果

- v4.3 Web 测试: 26 passed
- 全量测试基线: 1201 passed
- tag: `v4.3-web-acceptance-console`

