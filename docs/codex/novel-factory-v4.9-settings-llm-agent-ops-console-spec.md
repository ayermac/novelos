# v4.9: Settings / LLM / Agent Ops Console

## 背景

v3.1 实现了 LLM Profiles 和 Agent Routing，v3.9 实现了 LLM Model Catalog 和 Agent Recommendation。v4.3-v4.8 构建了完整的 Web UI 验收控制台。

但用户目前在 Web UI 中无法直观查看：
- 当前 LLM 配置状态
- Agent 路由配置
- 模型推荐结果
- Skill / QualityHub 状态
- 配置诊断结果

v4.9 新增 Settings / LLM / Agent Ops Console，让用户可以在 Web UI 中一站式查看所有配置和诊断信息。

## 产品定位

本版本继续服务于个人小说生产系统：

- 单个作者
- 本地浏览器控制台
- SQLite 本地数据库
- Web 作为主要验收入口
- Settings 页面作为配置和诊断中心

不做团队协作，不做多用户，不做权限系统。

## 目标

- 新增 `/settings` 路由展示配置和诊断信息
- 展示当前 llm_mode / runtime mode
- 展示 default_llm 和 LLM profiles 列表
- 展示每个 profile 的配置状态（provider、model、base_url_env、api_key_env）
- 展示 Agent 到 profile 的 routing
- 展示未配置 Agent 的 fallback 状态
- 展示 v3.9 model catalog / recommendation 结果
- 展示 Skill / QualityHub / Agent registry 的只读状态
- 展示配置诊断摘要
- 所有敏感信息必须 mask（API key、secret）
- 页面可读、可操作，不展示 raw JSON
- 页面以 read-model 展示为主，不新增生产写入逻辑

## 范围

### Runtime Mode

- 当前 llm_mode（stub / real）
- 当前 runtime 状态（是否初始化、是否可用）

### LLM Profiles

- default_llm 配置
- LLM profiles 列表
- 每个profile 显示：
  - name
  - provider
  - model
  - base_url_env（是否配置）
  - api_key_env（是否配置，不显示真实值）
  - 配置状态（完整 / 缺失 key / 缺失 base_url）

### Agent Routing

- Agent 到 profile 的映射
- 未配置 Agent 的 fallback 状态
- Agent 列表及其当前路由

### Model Recommendations

- v3.9 catalog 加载状态
- 每个 Agent 的推荐模型（Top 3）
- 推荐配置草案预览

### Skill / QualityHub Status

- Skill registry 状态
- 已加载 Skill 列表
- QualityHub 配置状态
- Agent registry 状态

### Diagnostics

- 配置验证结果
- 缺失配置警告
- 错误信息（不包含 traceback）

## 技术设计

- 复用现有 `/config` 路由或新增 `/settings` 路由
- route 层构建轻量 read model，不新增数据库表
- 优先使用现有 LLMRouter、Catalog、Recommender
- 查询失败时局部降级为空状态，页面整体仍可显示
- 页面不展示 raw JSON
- 所有敏感信息使用 `mask_secret()` 处理

## 测试计划

新增 `tests/test_v49_settings_llm_agent_ops_console.py`，覆盖：

1. GET /settings 返回 200
2. 页面展示 LLM profiles
3. 页面展示 agent routing
4. 页面展示 model recommendations
5. 页面展示 diagnostics
6. 缺配置时显示可读 warning
7. 页面不包含 API key / secret / traceback
8. 页面不展示 raw JSON
9. 不写入数据库
10. 不修改 .env/config
11. 不触发真实 LLM 调用
12. acceptance matrix 包含 settings_ops 且测试文件路径真实存在

必须继续通过：

```bash
python3 -m pytest tests/test_v49_settings_llm_agent_ops_console.py -q
python3 -m pytest tests/test_v43_web_app.py tests/test_v43_web_routes.py tests/test_v43_web_cli.py tests/test_v44_web_ux.py tests/test_v45_onboarding.py tests/test_v46_first_run_guided_workflow.py tests/test_v47_project_workspace.py tests/test_v48_web_acceptance_matrix.py tests/test_v49_settings_llm_agent_ops_console.py -q
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
- 不展示 raw JSON
- 不泄露 API key、secret、traceback
- 不写入 .env 或真实 config

## 开发顺序

1. 创建 `novel_factory/web/routes/settings.py` Web 路由
2. 创建 `novel_factory/web/templates/settings.html` 模板
3. 更新 `novel_factory/web/app.py` 注册路由
4. 更新 `novel_factory/web/templates/base.html` 添加导航
5. 更新 `novel_factory/web/acceptance_matrix.py` 添加 settings_ops
6. 补充 v4.9 测试
7. 跑 Web 组合测试、文件体积策略和全量测试
8. 更新文档

## 验收结果

**状态：已通过最终验收（含 P2 修复）**

测试基线：1341/1341 通过

实现要点：
1. ✅ 新增 /settings 路由
2. ✅ 新增 settings.html 模板
3. ✅ 更新 app.py 注册路由
4. ✅ 更新 base.html 添加导航
5. ✅ 新增 test_v49_settings_llm_agent_ops_console.py 测试（29 个测试用例）
6. ✅ 页面展示 LLM profiles 和 agent routing
7. ✅ 页面展示 model recommendations
8. ✅ 页面展示 diagnostics
9. ✅ 页面不展示 raw JSON
10. ✅ 不泄露 API key/secret/traceback
11. ✅ 不写入数据库或 .env
12. ✅ acceptance matrix 包含 settings_ops 且测试文件路径真实存在

P2 修复（v4.9 review 返工）：
1. ✅ 修复 LLM profile 状态判断：使用 resolved value 而非 env var 名称
2. ✅ 修复 Diagnostics 校验：检查 default_llm 和 agent_llm 引用有效性
3. ✅ 新增坏配置测试：7 个测试用例覆盖缺失配置、无效引用、env var 缺失等场景
4. ✅ real mode 下缺失 env var 显示 error，stub mode 下显示 warning
5. ✅ Agent Routing 表标记 invalid/missing profile 状态
6. ✅ 页面显示 env var 名称和 configured/missing 状态，不显示实际值

修改文件：
- novel_factory/web/app.py：注册 settings 路由
- novel_factory/web/templates/base.html：添加 Settings 导航
- novel_factory/web/acceptance_matrix.py：添加 settings_ops capability

新增文件：
- novel_factory/web/routes/settings.py：Web 路由（284 行）
- novel_factory/web/templates/settings.html：模板（366 行）
- tests/test_v49_settings_llm_agent_ops_console.py：测试（22 个测试用例）
- docs/codex/novel-factory-v4.9-settings-llm-agent-ops-console-spec.md：规格文档

遵守禁止范围：
- ✅ 不新增生产写入逻辑
- ✅ 不自动运行章节生产
- ✅ 不自动 approve/publish
- ✅ 不实现登录/注册/权限
- ✅ 不引入 WebSocket/Redis/Celery
- ✅ 不新增真实 LLM 调用测试
- ✅ 不提交 config/acceptance.yaml 或真实密钥
- ✅ 不泄露 API key/secret/traceback
- ✅ 不写入 .env 或真实 config

功能清单：
- ✅ Runtime Mode 展示（llm_mode、default_llm）
- ✅ LLM Profiles 展示（name、provider、model、base_url_env、api_key_env、status）
- ✅ Agent Routing 展示（agent、route、fallback 状态）
- ✅ Model Recommendations 展示（catalog status、每个 agent 的 Top 3 推荐）
- ✅ Skill / QualityHub Status 展示（skills 列表、qualityhub_status、agent_registry_status）
- ✅ Diagnostics 展示（errors、warnings）

partial/missing 能力清单：
- 无（所有功能均已实现）

未完成项或风险：
- 无
