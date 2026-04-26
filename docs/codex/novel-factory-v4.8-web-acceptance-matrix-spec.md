# v4.8: Web Acceptance Matrix & Parity Hardening

## 背景

v4.3-v4.7 已经构建了完整的 Web UI 验收控制台，覆盖 Onboarding、Run Chapter、Batch、Queue、Serial、Review、Style 等核心能力。每个版本都有对应的测试文件和验收标准。

但目前缺少一个全局视图来展示：
- 哪些能力已经实现
- 哪些能力有 Web 路由
- 哪些能力有 CLI 命令
- 哪些能力有测试覆盖（成功/失败）
- 哪些能力有 DB 验证
- 哪些能力有安全检查（无 API key/traceback 泄露）
- 整体验收状态（pass/partial/missing）

v4.8 新增 Web Acceptance Matrix，让开发者和用户可以一目了然地看到系统的验收覆盖情况。

## 产品定位

本版本继续服务于个人小说生产系统：

- 单个作者
- 本地浏览器控制台
- SQLite 本地数据库
- Web 作为主要验收入口
- Acceptance Matrix 作为验收状态总览

不做团队协作，不做多用户，不做权限系统。

## 目标

- 新增 `/acceptance` 路由展示验收矩阵
- 集中定义所有能力及其验收状态
- 展示 Web route、CLI command、测试覆盖、DB 验证、安全检查
- 页面以 read-model 展示为主，不新增生产写入逻辑
- 不执行 pytest 或 shell 命令
- 不泄露 API key、secret、traceback

## 范围

### Acceptance Matrix 数据结构

每个能力包含：

- `capability_id`: 唯一标识符
- `label`: 人类可读名称
- `web_route`: Web 路由（如 `/onboarding`）
- `cli_command`: CLI 命令（如 `novelos run-chapter`）
- `success_test`: 成功路径测试文件
- `failure_test`: 失败路径测试文件
- `db_assertion`: 是否有 DB 状态验证
- `safety_check`: 是否有安全检查（无 API key/traceback 泄露）
- `status`: 验收状态（pass/partial/missing）
- `notes`: 备注说明

### 覆盖的能力

至少覆盖：

1. Onboarding (v4.5)
2. Run Chapter (v4.3)
3. Project Workspace (v4.7)
4. Batch Production (v3.0)
5. Production Queue (v3.4)
6. Serial Plan (v3.6)
7. Review Workbench (v3.7)
8. Style Bible (v4.0)
9. Style Gate (v4.1)
10. Style Samples (v4.2)
11. Style Proposals (v4.1)
12. Config / Diagnostics (v4.3)
13. First Run Guided Workflow (v4.6)
14. Acceptance Matrix (v4.8)

### 页面展示

- 顶部摘要卡片：总能力数、通过数、部分通过数、缺失数、通过率
- 覆盖统计：Web 路由数、CLI 命令数、测试覆盖数、DB 验证数、安全检查数
- 能力详情表格：每行一个能力，展示所有字段
- 状态颜色编码：pass=绿色、partial=黄色、missing=红色
- 不展示 raw JSON

### 技术实现

- 新增 `novel_factory/web/acceptance_matrix.py` 集中定义能力
- 新增 `novel_factory/web/routes/acceptance.py` Web 路由
- 新增 `novel_factory/web/templates/acceptance.html` 模板
- 更新 `novel_factory/web/app.py` 注册路由
- 更新 `novel_factory/web/templates/base.html` 添加导航入口

## 测试计划

新增 `tests/test_v48_web_acceptance_matrix.py`，覆盖：

1. GET /acceptance 返回 200
2. 页面包含所有核心能力
3. 页面包含 pass/partial/missing 状态
4. 页面展示 Web route 和测试覆盖信息
5. 页面不包含 Traceback/API key/secret
6. acceptance matrix 定义来自集中 Python 数据结构，不只是在模板硬编码
7. 每个 capability_id 唯一
8. 每个 capability 至少有 label/web_route/status
9. status 只能是 pass/partial/missing
10. 页面有摘要统计
11. 页面不展示 raw JSON
12. 不执行 pytest 或 shell 命令
13. 不写入数据库
14. 不触发生产逻辑

必须继续通过：

```bash
python3 -m pytest tests/test_v48_web_acceptance_matrix.py -q
python3 -m pytest tests/test_v43_web_app.py tests/test_v43_web_routes.py tests/test_v43_web_cli.py tests/test_v44_web_ux.py tests/test_v45_onboarding.py tests/test_v46_first_run_guided_workflow.py tests/test_v47_project_workspace.py tests/test_v48_web_acceptance_matrix.py -q
python3 -m pytest tests/test_file_size_policy.py -q
python3 -m pytest -q
```

## 禁止范围

- 不新增生产写入逻辑
- 不自动运行章节生产
- 不自动 approve
- 不自动 publish
- 不执行 pytest 或 shell 命令
- 不实现登录/注册
- 不实现用户/角色/权限/RBAC/OAuth/session
- 不实现多用户协作
- 不引入 WebSocket
- 不引入 daemon/cron/background worker
- 不引入 Redis/Celery/Kafka/PostgreSQL
- 不新增真实 LLM 调用测试
- 不绕过 Dispatcher/Repository
- 不提交本地 `config/acceptance.yaml`、`stderr.txt` 或真实密钥
- 不展示 raw JSON

## 开发顺序

1. 创建 `novel_factory/web/acceptance_matrix.py` 定义能力列表
2. 创建 `novel_factory/web/routes/acceptance.py` Web 路由
3. 创建 `novel_factory/web/templates/acceptance.html` 模板
4. 更新 `novel_factory/web/app.py` 注册路由
5. 更新 `novel_factory/web/templates/base.html` 添加导航
6. 补充 v4.8 测试
7. 跑 Web 组合测试、文件体积策略和全量测试

## 验收结果

**状态：已通过最终验收**

测试基线：1312/1312 通过

实现要点：
1. ✅ 新增 acceptance_matrix.py 集中定义能力（14 个能力）
2. ✅ 新增 /acceptance 路由
3. ✅ 新增 acceptance.html 模板
4. ✅ 更新 app.py 注册路由
5. ✅ 更新 base.html 添加导航
6. ✅ 新增 test_v48_web_acceptance_matrix.py 测试（29 个测试用例）
7. ✅ 页面展示所有核心能力
8. ✅ 页面展示摘要统计
9. ✅ 页面不展示 raw JSON
10. ✅ 不泄露 API key/secret/traceback
11. ✅ 不执行 pytest 或 shell 命令
12. ✅ 所有测试文件路径真实存在
13. ✅ status=pass 的能力有完整覆盖要求

修复记录（Review 后）：
- [P2] 修复测试文件路径：将所有 success_test/failure_test 改为真实存在的测试文件
  - batch: test_batch_production.py + test_v44_web_ux.py
  - queue: test_v34_production_queue.py + test_v35_queue_runtime_hardening.py
  - serial: test_v36_semi_auto_serial_mode.py + test_v44_web_ux.py
  - review: test_v37_review_workbench.py + test_v44_web_ux.py
  - style_bible: test_v40_style_bible_cli.py + test_v40_style_bible_repository.py
  - style_gate: test_v41_style_gate.py + test_v41_style_cli.py
  - style_samples: test_v42_style_sample_repository.py + test_v42_style_sample_cli.py
  - style_proposals: test_v41_style_evolution.py + test_v41_style_cli.py
- [P2] 新增测试验证：
  - 每个非空 success_test/failure_test 必须能在 tests/ 下找到
  - status=pass 的 capability 必须至少有 web_route、success_test、failure_test、safety_check
  - db_assertion=False 且 status=pass 时，notes 必须说明原因

修改文件：
- novel_factory/web/app.py：注册 acceptance 路由
- novel_factory/web/templates/base.html：添加 Acceptance 导航
- novel_factory/web/acceptance_matrix.py：修复测试文件路径，增加 notes 说明

新增文件：
- novel_factory/web/acceptance_matrix.py：能力定义（14 个能力）
- novel_factory/web/routes/acceptance.py：Web 路由
- novel_factory/web/templates/acceptance.html：模板
- tests/test_v48_web_acceptance_matrix.py：测试（29 个测试用例）
- docs/codex/novel-factory-v4.8-web-acceptance-matrix-spec.md：规格文档

遵守禁止范围：
- ✅ 不新增生产写入逻辑
- ✅ 不自动运行章节生产
- ✅ 不自动 approve/publish
- ✅ 不实现登录/注册/权限
- ✅ 不引入 WebSocket/Redis/Celery
- ✅ 不新增真实 LLM 调用测试
- ✅ 不提交 config/acceptance.yaml 或真实密钥
- ✅ 不执行 pytest 或 shell 命令

能力清单：
- ✅ onboarding: 通过
- ✅ run_chapter: 通过
- ✅ project_workspace: 通过
- ✅ batch: 通过
- ✅ queue: 通过
- ✅ serial: 通过
- ✅ review: 通过
- ✅ style_bible: 通过
- ✅ style_gate: 通过
- ✅ style_samples: 通过
- ✅ style_proposals: 通过
- ✅ config: 通过
- ✅ first_run: 通过
- ✅ acceptance_matrix: 通过

partial/missing 能力清单：
- 无（所有 14 个能力均为 pass 状态）

未完成项或风险：
- 无
