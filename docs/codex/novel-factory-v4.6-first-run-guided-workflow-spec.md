# v4.6: First Run Guided Workflow

## 背景

v4.5 已经让个人作者可以通过 Web UI 从 0 创建小说项目，并初始化初始章节、首章目标、世界观、主角、Style Bible 和可选 Serial Plan。

但项目创建成功后，作者仍需要自己理解 Run Chapter、Review、Chapter 状态和错误处理之间的关系。v4.6 的目标是承接 Onboarding 成功页，把“创建项目”自然推进到“第一章可运行、可查看、可审核”的闭环。

## 产品定位

本版本继续服务于个人小说生产系统：

- 单个作者
- 本地浏览器控制台
- SQLite 本地数据库
- Web 作为主要验收入口
- stub 模式必须可完成完整验收

不做团队协作，不做多用户，不做权限系统。

## 目标

- 从 v4.5 Onboarding 成功页进入第一章 guided run
- Run Chapter 页面自动带入新项目的 project_id 和 chapter
- 运行成功后给出下一步入口：Review、Chapter 详情、Batch、Queue
- 运行失败时显示可操作错误和恢复入口
- 新项目首次运行闭环必须可用 stub 模式完成
- 测试必须验证真实数据库状态变化，不只断言 HTTP 200

## 范围

### Onboarding 成功页

- 增加“生成第一章”主操作
- 操作链接必须带 `project_id` 和 `chapter`
- 如果创建了 Serial Plan，保留 Serial/Queue 入口
- 成功页不自动触发生产，必须由用户明确点击

### Run Chapter 页面

- 支持从查询参数读取 `project_id` 和 `chapter`
- 表单自动预填项目和章节
- 对新项目显示适合首次运行的上下文信息
- 运行提交继续走现有 Dispatcher/Repository，不新增绕行逻辑

### 运行后结果

- 成功后显示章节状态、run_id 或可追踪信息
- 提供 Review Pack / Chapter / Project Detail 入口
- 如果章节进入 blocking/revision/requires_human，页面必须展示对应下一步
- 不显示原始 traceback
- 不泄露 API key 或 secret

### 错误与恢复

- 缺少 project_id/chapter 时显示表单级错误
- 项目不存在时显示可读错误，并给出返回 Onboarding/Projects 的入口
- 章节不存在时显示可读错误，并给出项目详情入口
- LLM real 模式缺 key 时显示配置修复入口
- stub 模式必须能完成验收，不依赖外部网络

## 测试计划

新增 `tests/test_v46_first_run_guided_workflow.py`，覆盖：

1. Onboarding 成功页包含第一章 guided run 链接
2. Run Chapter 页面可从 query params 预填 project_id/chapter
3. 新项目首章在 stub 模式下可从 Web 触发运行
4. 运行后章节状态和 workflow run 可追踪
5. 成功结果包含 Review 或 Chapter 后续入口
6. 项目不存在时返回可读错误
7. 章节不存在时返回可读错误
8. real 模式缺 key 时不泄露 secret/traceback
9. blocking/revision/requires_human 状态显示可操作下一步
10. Web 测试组合仍通过

必须继续通过：

```bash
python3 -m pytest tests/test_v46_first_run_guided_workflow.py -q
python3 -m pytest tests/test_v43_web_app.py tests/test_v43_web_routes.py tests/test_v43_web_cli.py tests/test_v44_web_ux.py tests/test_v45_onboarding.py tests/test_v46_first_run_guided_workflow.py -q
python3 -m pytest tests/test_file_size_policy.py -q
python3 -m pytest -q
```

## 禁止范围

- 不自动运行章节生产
- 不实现登录/注册
- 不实现用户/角色/权限/RBAC/OAuth/session
- 不实现多用户协作
- 不引入 WebSocket
- 不引入 daemon/cron/background worker
- 不引入 Redis/Celery/Kafka/PostgreSQL
- 不新增真实 LLM 调用测试
- 不绕过 Dispatcher/Repository
- 不自动 approve
- 不自动 publish
- 不提交本地 `config/acceptance.yaml`、`stderr.txt` 或真实密钥

## 开发顺序

1. 为 v4.5 成功页补 guided run 主入口。
2. 让 Run Chapter 页面支持 query params 预填。
3. 梳理 Run Chapter POST 后的成功/失败结果面板。
4. 补充 v4.6 测试，优先覆盖真实 DB 状态。
5. 跑 Web 组合测试、文件体积策略和全量测试。

## 验收结果

**状态：已通过验收**

测试基线：1254/1254 通过

实现要点：
1. ✅ Onboarding 成功页显示"生成第一章"主操作按钮
2. ✅ GET `/run` 支持 `project_id`、`chapter`、`llm_mode` 查询参数预填
3. ✅ POST `/run/chapter` 显示可读结果摘要（非原始 JSON）：
   - 项目 ID、章节、章节状态
   - Workflow Run ID、运行状态、错误信息
   - 执行步骤详情
   - 下一步操作入口（Review/Project Detail/Batch）
4. ✅ POST 成功和异常分支都传入 projects 参数，保留表单下拉选项
5. ✅ 错误路径显示可读错误信息，保留重试上下文
6. ✅ 测试验证真实数据库状态变化：
   - 章节状态必须离开 planned
   - Workflow run 必须创建且状态一致
   - 多次运行创建多个 workflow runs
7. ✅ 所有测试使用 stub 模式，无真实 LLM 调用

修复记录：
- [P2] 修复 POST /run/chapter 成功和异常分支缺少 projects 参数
- [P2] 修复 test_run_updates_chapter_status 恒真断言
- 补充测试验证 POST 后响应包含项目下拉选项

