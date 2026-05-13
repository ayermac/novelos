# v5.0 Implemented Features & WebUI Acceptance Spec

## 背景

v1-v4.9 已完成小说内容生产工厂的核心功能开发，涵盖章节生产、多 Agent 扩展、批次生产、队列管理、连载计划、审核工作台、风格系统、Web UI 验收控制台和配置控制台。v5.0 是对已实现功能的整体验收和 WebUI 验收，不新增大功能，重点确保：

1. 每个已声明 `pass` 的 capability 真实可验证
2. WebUI 核心链路覆盖完整
3. 安全检查（无 API key/secret/traceback 泄露）
4. 文档一致性

## 目标

- 对 v1-v4.9 已实现能力做整体验收
- 确认每个 pass capability 的 web_route、success_test、safety_check 真实有效
- 新增 v5.0 整体验收测试
- 验证 WebUI 核心链路 12 个路径
- 验证安全：不泄露 API key、secret、traceback、raw JSON
- 验证文档一致性

## 范围

### 1. Acceptance Matrix 梳理

基于 `novel_factory/web/acceptance_matrix.py` 梳理 16 个已实现 capability：

| capability_id | label | web_route | success_test | status |
|---|---|---|---|---|
| onboarding | Onboarding | /onboarding | test_v45_onboarding.py | pass |
| run_chapter | Run Chapter | /run/chapter | test_v43_web_routes.py | pass |
| project_workspace | Project Workspace | /projects/{id} | test_v47_project_workspace.py | pass |
| batch | Batch Production | /batch | test_batch_production.py | pass |
| queue | Production Queue | /queue | test_v34_production_queue.py | pass |
| serial | Serial Plan | /serial | test_v36_semi_auto_serial_mode.py | pass |
| review | Review Workbench | /review | test_v37_review_workbench.py | pass |
| style_bible | Style Bible | /style | test_v40_style_bible_cli.py | pass |
| style_gate | Style Gate | /style | test_v41_style_gate.py | pass |
| style_samples | Style Samples | /style | test_v42_style_sample_repository.py | pass |
| style_proposals | Style Proposals | /style | test_v41_style_evolution.py | pass |
| config | Config / Diagnostics | /config | test_v43_web_routes.py | pass |
| first_run | First Run Guided Workflow | /onboarding | test_v46_first_run_guided_workflow.py | pass |
| acceptance_matrix | Acceptance Matrix | /acceptance | test_v48_web_acceptance_matrix.py | pass |
| settings_ops | Settings / LLM / Agent Ops | /settings | test_v49_settings_llm_agent_ops_console.py | pass |
| v50_acceptance | v5.0 Feature Acceptance | /acceptance | test_v50_implemented_features_webui_acceptance.py | pass |

### 2. 验证规则

对每个 `pass` capability 验证：
- web_route 存在并返回可读页面（HTTP 200）
- success_test 文件真实存在
- failure_test 文件真实存在（如有）
- db_assertion 标注真实可信
- safety_check 有对应测试或说明

### 3. WebUI 核心链路覆盖

| 路径 | 对应功能 | 验证项 |
|---|---|---|
| / | Dashboard | 系统状态、最近运行 |
| /projects | 项目列表 | 项目概览 |
| /onboarding | Onboarding | 项目创建 |
| /run/chapter | Run Chapter | 单章运行 |
| /batch | Batch | 批次生产 |
| /queue | Queue | 队列管理 |
| /serial | Serial | 连载计划 |
| /review | Review | 审核工作台 |
| /style | Style | 风格系统 |
| /config | Config | 配置查看 |
| /acceptance | Acceptance Matrix | 验收矩阵 |
| /settings | Settings/LLM/Agent Ops | 配置控制台 |

### 4. 安全验证

- 不泄露 API key（sk- 等模式）
- 不泄露 secret
- 不显示 traceback
- 不展示 raw JSON（acceptance matrix 除外，展示结构化数据）
- stub mode 不触发真实 LLM

### 5. 文档一致性验证

- README 当前版本
- roadmap v5.0 状态
- v5.0 spec 验收结果
- acceptance matrix 状态

## 测试计划

新增 `tests/test_v50_implemented_features_webui_acceptance.py`，包含 7 个测试类：

1. `TestWebUICorePaths` - 12 个 WebUI 核心路径测试
2. `TestAcceptanceMatrixIntegrity` - 9 个验收矩阵完整性测试
3. `TestSafetyAcrossPages` - 5 个跨页面安全测试
4. `TestNavigationConsistency` - 2 个导航一致性测试
5. `TestDocumentationConsistency` - 3 个文档一致性测试
6. `TestCapabilityWebRouteVerification` - 11 个 capability 路由验证测试
7. `TestCrossPageDataConsistency` - 3 个跨页面数据一致性测试

必须继续通过：

```bash
python3 -m pytest tests/test_v50_implemented_features_webui_acceptance.py -q
python3 -m pytest tests/test_v43_web_app.py tests/test_v43_web_routes.py tests/test_v44_web_ux.py tests/test_v45_onboarding.py tests/test_v46_first_run_guided_workflow.py tests/test_v47_project_workspace.py tests/test_v48_web_acceptance_matrix.py tests/test_v49_settings_llm_agent_ops_console.py tests/test_v50_implemented_features_webui_acceptance.py -q
python3 -m pytest tests/test_file_size_policy.py -q
python3 -m pytest -q
```

## 禁止范围

- 不新增真实生产功能
- 不自动 approve/publish
- 不新增真实 LLM 调用测试
- 不写 .env
- 不提交 config/acceptance.yaml、stderr.txt、真实密钥
- 不引入登录/权限/多用户
- 不引入 WebSocket/Redis/Celery/后台 worker
- 不做 provider health check、fallback、token cost 统计

## 验收标准

1. v5.0 专项测试全部通过
2. WebUI 组合测试全部通过
3. 文件体积策略通过
4. 全量测试通过
5. 16 个 capability 全部为 pass，无 partial 或 missing
6. 所有 success_test 文件真实存在
7. 所有 web_route 返回 200
8. 无 API key/secret/traceback 泄露
9. 文档一致性验证通过

## 验收结果

**状态：已通过验收**

测试基线：1386/1386 通过

验收覆盖清单：

1. ✅ v5.0 专项测试：45/45 通过
2. ✅ WebUI 组合测试：208/208 通过
3. ✅ 文件体积策略：通过
4. ✅ 全量测试：1386/1386 通过

Pass 能力清单（16/16，100%）：

| capability_id | label | web_route | status |
|---|---|---|---|
| onboarding | Onboarding | /onboarding | pass |
| run_chapter | Run Chapter | /run | pass |
| project_workspace | Project Workspace | /projects/{id} | pass |
| batch | Batch Production | /batch | pass |
| queue | Production Queue | /queue | pass |
| serial | Serial Plan | /serial | pass |
| review | Review Workbench | /review | pass |
| style_bible | Style Bible | /style | pass |
| style_gate | Style Gate | /style | pass |
| style_samples | Style Samples | /style | pass |
| style_proposals | Style Proposals | /style | pass |
| config | Config / Diagnostics | /config | pass |
| first_run | First Run Guided Workflow | /onboarding | pass |
| acceptance_matrix | Acceptance Matrix | /acceptance | pass |
| settings_ops | Settings / LLM / Agent Ops | /settings | pass |
| v50_acceptance | v5.0 Feature Acceptance | /acceptance | pass |

安全检查结果：

- ✅ 无 API key 泄露（sk- 模式未出现在任何页面）
- ✅ 无 secret 泄露
- ✅ 无 traceback 显示
- ✅ 无 raw JSON 展示（Content-Type 均为 text/html）
- ✅ stub mode 不触发真实 LLM

文档更新结果：

- ✅ README.md 更新当前版本为 v5.0
- ✅ roadmap.md 新增 v5.0 段落
- ✅ v5.0 spec 验收结果填写
- ✅ acceptance matrix 状态一致（16 pass / 0 partial / 0 missing）

未完成项或风险：无
