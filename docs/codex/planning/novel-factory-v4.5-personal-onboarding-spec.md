# v4.5: Personal Novel Project Onboarding

## 背景

v4.3 和 v4.4 已经提供本地 Web 验收控制台和 Review UX 硬化能力，但个人作者仍需要先通过 CLI 或手工数据库准备项目、章节、Style Bible 和可选连载计划。

v4.5 聚焦“从 0 创建小说项目”的入口体验，让作者可以在 Web UI 中一次性创建项目基础信息、初始章节、首章目标、世界观、主角、Style Bible 和可选 Serial Plan。

## 产品定位

本版本继续服务于个人小说生产系统：

- 单个作者
- 本地浏览器控制台
- SQLite 本地数据库
- Web 作为主要验收入口
- CLI 能力保持兼容

不做团队协作，不做多用户，不做权限系统。

## 目标

- 新增 Web Onboarding 页面，用表单创建新小说项目
- 创建项目时自动创建初始 planned 章节
- 可选创建首章 instruction、世界观设定、主角记录
- 使用 v4.0 Style Bible 模板系统初始化 Style Bible
- 可选创建 Serial Plan
- 创建流程具备事务性，失败时不留下半成品数据
- 成功页给出自然的下一步入口
- 补充 v4.5 Web 测试覆盖真实数据库状态变化

## 范围

### Web 入口

- Dashboard 显示 Onboarding 入口
- Projects 页面显示创建新小说项目入口
- 新增 `/onboarding` 表单页面
- 新增 `/onboarding/project` 提交入口
- 成功后展示 `/onboarding` success 页面

### 表单字段

- project_id
- name
- genre
- description
- total_chapters_planned
- target_words
- start_chapter
- initial_chapter_count
- style_template
- opening_objective
- world_setting
- main_character_name
- main_character_role
- main_character_description
- create_serial_plan
- serial_batch_size

### 创建行为

- 创建 `projects` 记录，状态为 active
- 从 `start_chapter` 开始创建 `initial_chapter_count` 个 planned 章节
- 如果填写 `opening_objective`，创建首章 instruction
- 如果填写 `world_setting`，创建基础 world setting
- 如果填写 `main_character_name`，创建主角/角色记录
- 使用 `list_templates()` 与 `load_style_bible_template()` 读取 v4.0 Style Bible 模板
- 默认模板为 `default_web_serial`
- 根据模板创建 `style_bibles` 记录
- 如果勾选 `create_serial_plan`，创建 Serial Plan

### 校验规则

- project_id 不允许重复
- `initial_chapter_count >= 1`
- `start_chapter >= 1`
- `total_chapters_planned >= start_chapter + initial_chapter_count - 1`
- `style_template` 必须来自 v4.0 Style Bible 模板系统
- 数据库冲突必须返回可读错误，不显示 traceback

### 事务规则

- 项目、章节、instruction、world setting、character、Style Bible、Serial Plan 必须在同一事务中创建
- 任一步失败必须 rollback
- 失败后不能留下部分创建的项目或关联数据

### 成功页

成功页必须提供后续入口：

- Run Chapter
- Batch Production
- Serial Plan（创建时展示）
- Queue（创建 Serial Plan 时展示）
- Style Bible
- Review
- 项目详情
- 创建另一个项目
- 项目列表

## 测试计划

新增 `tests/test_v45_onboarding.py`，覆盖：

1. Onboarding 页面可加载
2. 页面展示 v4.0 Style Bible 模板
3. 最小项目创建成功
4. 完整字段项目创建成功
5. 自定义起始章节创建成功
6. 重复 project_id 被拒绝
7. 非法章节范围被拒绝
8. `total_chapters_planned` 小于初始章节范围时被拒绝
9. 非法 style_template 被拒绝
10. Style Bible 使用 v4.0 模板字段
11. 创建 Serial Plan 时成功页展示 Serial Plan 入口
12. 成功页展示 Run Chapter 入口
13. 事务失败时不留下半成品数据
14. Dashboard 和 Projects 页面展示 Onboarding 入口

必须继续通过：

```bash
python3 -m pytest tests/test_v45_onboarding.py -q
python3 -m pytest tests/test_v43_web_app.py tests/test_v43_web_routes.py tests/test_v43_web_cli.py tests/test_v44_web_ux.py tests/test_v45_onboarding.py -q
python3 -m pytest tests/test_file_size_policy.py -q
python3 -m pytest -q
```

## 禁止范围

- 不实现登录/注册
- 不实现用户/角色/权限/RBAC/OAuth/session
- 不实现多用户协作
- 不引入 WebSocket
- 不引入 daemon/cron/background worker
- 不引入 Redis/Celery/Kafka/PostgreSQL
- 不新增真实 LLM 调用测试
- 不自动运行章节生产
- 不自动 approve
- 不自动 publish
- 不绕过 v4.0 Style Bible 模板系统
- 不提交本地 `config/acceptance.yaml`、`stderr.txt` 或真实密钥

## 验收结果

- v4.5 Onboarding 测试: 21 passed
- Web 测试: 59 passed
- 文件体积策略: 65 passed
- 全量测试基线: 1234 passed
- tag: `v4.5-personal-onboarding`
