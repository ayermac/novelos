# v4.4: Web Review UX Hardening

## 背景

v4.3 提供了 Web UI Acceptance Console MVP，可以通过浏览器操作主要功能。但 v4.3 仍偏"能用"，部分页面依赖手动输入 ID、展示原始 JSON 较多、操作后的状态反馈不够直观。

v4.4 聚焦 Web UX 硬化，让个人作者可以更自然地完成整体验收：查看 Review Pack、审核 Batch、管理 Queue/Serial、处理 Style Proposals，而不需要频繁回到 CLI 或手动复制 ID。

## 产品定位

本版本仍然服务于**个人小说生产系统**：

- 单个作者
- 本地浏览器控制台
- SQLite 本地数据库
- CLI 与 Web 双入口

不做团队协作，不做多用户，不做权限系统。

## 目标

- 把 Review 页面从原始 JSON 展示升级为卡片化/分区展示
- Batch 页面展示 run 列表和行内 review 操作
- Queue 页面按状态分组并提供合法操作按钮
- Serial 页面展示计划进度和常用操作
- Style 页面展示 gate config、samples、pending proposals，并支持行内 approve/reject
- 统一 result/error panel
- 所有新增 POST 测试验证真实 DB 状态变化

## 范围

### Review 页面

- 支持 review pack 的可读展示
- 展示 summary、decision_hint、chapters、quality issues、continuity gate、queue status、timeline
- decision_hint 以状态形式展示：
  - approve_allowed
  - needs_revision
  - blocked

### Batch 页面

- 展示最近 production_runs
- 展示 run_id、project_id、chapter range、status、completed/total、blocked_chapter
- awaiting_review run 提供 approve/request_changes/reject 表单
- POST 后刷新 run/items 状态

### Queue 页面

- 按 status 分组：
  - pending
  - running
  - failed
  - timeout
  - paused
  - completed
- 展示 queue_id、project_id、chapter range、status、attempt_count、production_run_id
- 合法操作：
  - pause
  - resume
  - retry
  - recover

### Serial 页面

- 展示 serial plans 列表
- 展示 current_chapter、target_chapter、batch_size、status、current_queue_id/current_run_id
- 提供 enqueue-next、advance、pause、resume、cancel 操作

### Style 页面

- 展示当前 Style Gate 配置
- 展示 Style Samples 列表
- 展示 pending Style Evolution Proposals
- 支持行内 approve/reject，不需要用户手动复制 proposal_id

### 统一结果体验

- 成功显示 success panel
- 失败显示 error panel
- 错误不显示 traceback
- 错误不泄露 API key
- POST 失败后仍保留页面上下文

## 关键修复

- `batch review/status` 页面刷新 items 时必须调用 `repo.get_production_run_items()`，不能调用不存在的 `list_production_run_items()`
- success panel 测试必须验证真实业务成功，不能只匹配 CSS 类名
- Style proposals 必须可在页面上看到并行内决策

## 测试计划

新增 `tests/test_v44_web_ux.py`，覆盖：

1. Batch 页面展示 production runs
2. Batch review POST 改变 production_run status
3. Batch review 页面不出现不存在方法错误
4. Queue 页面展示 queue items
5. Queue retry 将 failed item 改为 pending
6. Queue pause/resume 改变 item status
7. Serial 页面展示 serial plans
8. Serial enqueue-next 创建并关联 queue item
9. Style inline approve 将 proposal 改为 approved
10. Style inline reject 将 proposal 改为 rejected
11. 错误页面不包含 traceback
12. success panel 对应真实 DB 成功状态
13. error panel 可显示失败状态

必须继续通过：

```bash
python3 -m pytest tests/test_v43_web_app.py tests/test_v43_web_routes.py tests/test_v43_web_cli.py tests/test_v44_web_ux.py -q
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
- 不绕过 Dispatcher/Repository
- 不自动 approve
- 不自动 publish
- 不提交本地 config/acceptance.yaml、stderr.txt 或真实密钥

## 验收结果

- v4.3 + v4.4 Web 测试: 38 passed
- 文件大小策略: 65 passed
- 全量测试基线: 1213 passed
- tag: `v4.4-web-review-ux-hardening`

