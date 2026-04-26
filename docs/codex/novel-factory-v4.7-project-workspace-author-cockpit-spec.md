# v4.7: Project Workspace / Author Cockpit

## 背景

v4.5 已经支持个人作者通过 Web UI 创建小说项目，v4.6 已经打通创建后第一章运行、查看结果和进入审核的首次运行闭环。

但项目进入持续生产后，作者仍需要在 Dashboard、Projects、Run、Batch、Queue、Serial、Review、Style 等多个页面之间切换，才能判断当前项目的状态和下一步操作。

v4.7 聚焦项目级工作台，把一个项目的关键状态、待办和操作入口收束到 `/projects/{project_id}`，让作者进入项目后能直接知道“现在该做什么”。

## 产品定位

本版本继续服务于个人小说生产系统：

- 单个作者
- 本地浏览器控制台
- SQLite 本地数据库
- Web 作为主要验收入口
- 项目详情页作为作者日常工作台

不做团队协作，不做多用户，不做权限系统。

## 目标

- 将 `/projects/{project_id}` 升级为 Project Workspace / Author Cockpit
- 聚合项目基础信息、章节进度、最近运行、Review 待办、Queue、Serial、Style 状态
- 给出 Next Best Action，让作者知道下一步该运行、审核、处理阻塞还是调整风格
- 提供常用操作入口，减少跨页面寻找
- 页面以 read-model 聚合为主，不新增生产写入逻辑
- 测试必须验证真实数据库中的 run/queue/serial/style 数据出现在页面上

## 范围

### Project Overview

- project_id
- name
- genre
- status
- current_chapter
- total_chapters_planned
- target_words
- description

### Next Best Action

根据项目当前状态给出一个主建议：

- 有 blocking/requires_human 章节：优先处理阻塞或进入 Review
- 有 awaiting review：进入 Review Workbench
- 有 planned/scripted/drafted/polished 章节：继续 Run Chapter
- 有 queue failed/timeout：进入 Queue 处理
- 有 pending style proposals：进入 Style 页面处理
- 没有明显待办：进入 Batch 或 Serial 继续生产

### Chapter Progress

- 章节总数
- 按状态分组统计
- 最近若干章节列表
- 每章显示 chapter_number、title、status、word_count、updated_at
- 提供单章 Run / Review / Project detail 链接

### Recent Runs

- 最近 workflow_runs
- 显示 run_id、chapter_number、status、current_node、started_at、completed_at、error_message 摘要
- 失败 run 不显示 traceback

### Review Queue

- 展示可进入 Review Workbench 的入口
- 如有可识别的待审核章节或 review pack 信息，展示摘要
- 缺少 review 数据时显示空状态，不报错

### Production Queue

- 展示当前项目相关 queue items
- 按 pending/running/failed/timeout/paused/completed 简要分组
- 提供 Queue 页面入口
- 缺少 queue 数据时显示空状态，不报错

### Serial Plan

- 展示当前项目 serial plans
- 显示 status、start_chapter、target_chapter、current_chapter、batch_size、current_queue_id/current_run_id
- 提供 Serial 页面入口
- 缺少 serial plan 时显示空状态

### Style Health

- 展示 Style Bible 是否存在
- 展示 Style Gate 配置摘要
- 展示 pending Style Evolution Proposals 数量
- 展示 Style Samples 数量
- 提供 Style 页面入口
- 缺少 style 数据时显示初始化入口或空状态

### Quick Actions

- Run Chapter
- Batch Production
- Queue
- Serial
- Review
- Style
- Create Another Project

## 技术设计

- 优先复用现有 `/projects/{project_id}` 路由
- route 层构建轻量 read model，不新增数据库表
- 优先使用现有 Repository 方法
- 查询失败时局部降级为空状态，页面整体仍可显示
- 页面不展示 raw JSON
- POST 操作继续由既有 Run/Batch/Queue/Serial/Review/Style 页面处理

## 测试计划

新增 `tests/test_v47_project_workspace.py`，覆盖：

1. `/projects/{project_id}` 返回项目工作台
2. 页面展示项目基础信息
3. 页面展示章节进度和状态分组
4. 页面展示最近 workflow run
5. 页面展示 Review 入口
6. 页面展示 Queue 状态或空状态
7. 页面展示 Serial Plan 或空状态
8. 页面展示 Style Bible / Style Gate 状态或空状态
9. 页面展示 Quick Actions：Run Chapter、Batch、Review、Style
10. project 不存在时显示可读错误，不出现 traceback
11. 页面不包含 API key / secret
12. seeded DB 中的 run/queue/serial/style 数据能在页面出现

必须继续通过：

```bash
python3 -m pytest tests/test_v47_project_workspace.py -q
python3 -m pytest tests/test_v43_web_app.py tests/test_v43_web_routes.py tests/test_v43_web_cli.py tests/test_v44_web_ux.py tests/test_v45_onboarding.py tests/test_v46_first_run_guided_workflow.py tests/test_v47_project_workspace.py -q
python3 -m pytest tests/test_file_size_policy.py -q
python3 -m pytest -q
```

## 禁止范围

- 不新增生产写入逻辑
- 不自动运行章节生产
- 不自动 approve
- 不自动 publish
- 不实现登录/注册
- 不实现用户/角色/权限/RBAC/OAuth/session
- 不实现多用户协作
- 不引入 WebSocket
- 不引入 daemon/cron/background worker
- 不引入 Redis/Celery/Kafka/PostgreSQL
- 不新增真实 LLM 调用测试
- 不绕过 Dispatcher/Repository
- 不提交本地 `config/acceptance.yaml`、`stderr.txt` 或真实密钥

## 开发顺序

1. 梳理 `/projects/{project_id}` 当前 detail 页面和 route。
2. 增加 project workspace read model。
3. 改造 project detail 模板为工作台布局。
4. 补充 v4.7 测试，优先覆盖真实 DB 状态展示。
5. 跑 Web 组合测试、文件体积策略和全量测试。

