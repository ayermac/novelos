# Novelos v6.0 Agent Role Capability System — Completion Report

## 状态

- 类型：完整能力闭环
- 基线：v5.9.3 Agent Skill Expansion
- 目标：把 Novelos 从“按阶段调用 LLM 的流水线”升级为“有角色目标、工具、记忆、自检、协作和评测的 AI 创作团队”

## 核心交付完成度

### 1. Agent Role Profile — 完成

新增 7 个角色配置文件：
- `novel_factory/agents/roles/planner.yaml`
- `novel_factory/agents/roles/screenwriter.yaml`
- `novel_factory/agents/roles/author.yaml`
- `novel_factory/agents/roles/polisher.yaml`
- `novel_factory/agents/roles/editor.yaml`
- `novel_factory/agents/roles/memory_curator.yaml`
- `novel_factory/agents/roles/publisher.yaml`

每个 profile 包含：mission、success_criteria、failure_criteria、primary_inputs、primary_outputs、owned_artifacts、decision_authority、cannot_do、collaboration_contracts、default_capability_packs、eval_dimensions、cost_budget、trace_policy。

新增加载器：`novel_factory/agents/role_profile.py`

### 2. Capability Pack System — 完成

将 v5.9.3 的 4 个内置 Skill 迁移为 package-style capability packs：
- `skill_packages/chapter_objective_checker/`
- `skill_packages/scene_conflict_checker/`
- `skill_packages/event_coverage_checker/`
- `skill_packages/memory_patch_validator/`

每个 package 包含：manifest.yaml、handler.py、README.md、tests/fixtures.yaml。

更新 `skills.yaml`，4 个 skill 改为 package 优先加载。

### 3. Role-specific Default Capabilities — 完成

每个核心 Agent 在 Role Profile 中定义了至少 3 个默认 capability packs：
- Planner: chapter_objective_checker, foreshadowing_debt_planner, pacing_plan_checker, arc_continuity_checker
- Screenwriter: scene_conflict_checker, scene_function_classifier, hook_strength_checker, emotion_curve_checker
- Author: event_coverage_checker, character_voice_checker, show_dont_tell_checker, webnovel_payoff_checker, local_rewrite_tool
- Polisher: humanizer_zh, ai_style_detector, rhythm_polisher, style_bible_checker, fact_lock_guard
- Editor: narrative_quality, commercial_readability_checker, dropoff_risk_checker, logic_consistency_checker, revision_brief_generator
- MemoryCurator: memory_patch_validator, fact_dedup_checker, fact_conflict_checker, plot_status_transition_checker, memory_importance_ranker

### 4. Agent Memory — 完成

新增数据库迁移：`031_v6_0_agent_memory_and_trace.sql`
- `agent_memories` 表
- `agent_decision_traces` 表

新增 Repository：`novel_factory/db/repositories/agent_memory.py`
新增 API：`novel_factory/api/routes/agent_memory.py`
新增 UI：`frontend/src/components/agentops/AgentMemoryPanel.tsx`

支持：project preference memory、recurring failure memory、user feedback memory、agent strategy notes、enable/disable/delete。

### 5. Bounded Autonomy — 完成

新增：`novel_factory/agents/autonomy.py`
- BoundedAutonomyDecision 结构化决策对象
- 6 种决策类型：continue、local_repair、request_context、reroute、refuse、ask_human
- 硬约束验证：max repair attempts、real mode publish gate

### 6. Controlled Agent Tool Runtime — 完成

新增：`novel_factory/tools/registry.py`
- 7 个内部工具默认启用：project_context.query、chapter.version_diff、foreshadowing.debt_report、agent_memory.query/write、local_rewrite.apply、capability.eval
- 4 个外部工具默认禁用：web_search.query、file.import_reference、http.request、bash.run
- 每个工具有权限、allowed_agents、audit_policy、cost_policy

### 7. Self-check and Local Repair — 完成

新增：`novel_factory/agents/self_check.py`
- SelfCheckResult、LocalRepairResult 数据结构
- SelfCheckLoop 类：generate → self_check → local_repair → final_check → save
- 最大 1 次自动 local repair，记录 before/after

### 8. Collaboration Contract — 完成

新增：`novel_factory/agents/contracts/__init__.py`
- 6 个 canonical handoff contracts
- Planner ↔ Screenwriter ↔ Author ↔ Polisher ↔ Editor
- MemoryCurator → Planner context warnings
- Editor revision attribution 到具体 Agent

### 9. Agent Decision Trace — 完成

新增：`novel_factory/agents/decision_trace.py`
- AgentDecisionTrace 数据结构
- DecisionTraceStore：内存 + DB 最佳努力持久化
- 记录：role profile、capability packs、tool calls、self-check、autonomy decision、repair attempts、token/latency

### 10. AgentOps UI — 完成

新增前端组件：
- `frontend/src/components/agentops/AgentOpsPanel.tsx` — 主控制台
- `frontend/src/components/agentops/AgentRoleCard.tsx` — 角色卡片
- `frontend/src/components/agentops/AgentTraceView.tsx` — 决策 trace
- `frontend/src/components/agentops/AgentMemoryPanel.tsx` — 记忆管理
- `frontend/src/components/agentops/AgentEvalStatus.tsx` — Eval 状态

新增 API：`novel_factory/api/routes/agent_ops.py`
- `/api/agent-ops/role-profiles`
- `/api/agent-ops/agent-traces`
- `/api/agent-ops/agent-eval/{agent_id}`

### 11. Evaluation Harness — 完成

新增：`scripts/eval_agents.py`
- 支持 `python3 scripts/eval_agents.py planner` 和 `all`
- 每个核心 Agent 5 个 eval case
- Eval fixtures 目录：`evals/agents/{agent_id}/eval.yaml`

### 12. Genre Strategy — 完成

新增：`novel_factory/config/genre_strategies/`
- general.yaml
- urban_xianxia.yaml
- mystery.yaml
- romance.yaml
- fantasy.yaml

### 13. Migration and Backward Compatibility — 完成

- 老 Skill 继续运行（skills.yaml 保留 manifest fallback）
- 旧 workflow timeline 不破坏
- 没有 Agent Memory 的项目正常运行
- 没有 Genre Strategy 的项目使用 general

## 回归测试

```bash
python3 scripts/verify.py smoke                          # 通过
python3 -m pytest tests/test_skill_config.py tests/test_skills.py tests/test_skills_api.py tests/test_agents.py tests/test_v60_review_fixes.py -q  # 113 passed
python3 -m pytest tests/test_v516_langgraph_activation.py tests/test_v58_workflow_observability.py -q  # 31 passed
python3 scripts/eval_agents.py all                        # 30/30 passed
cd frontend && npm run typecheck                           # 通过
cd frontend && npm run lint                                # 通过
cd frontend && npm run build                               # 通过
cd frontend && npm run test -- --run                       # 148 passed
```

完整 pytest：1917/1917 passed。

## Review 修复

本轮 review 后补齐了以下闭环断点：

1. `BaseAgent` 的 v6.0 role profile / Agent Memory 上下文现在真正注入 Planner、Screenwriter、Author、Polisher、Editor、MemoryCurator 的 prompt。
2. Agent Memory API 改为使用请求上下文 `db_path`，不再依赖不存在的 `app.state.db_conn`。
3. Agent Decision Trace 修复 SQLite commit 连接错误，并支持 AgentOps API 从 DB 读取持久化 trace。
4. AgentOps 前端修正 API 路径，移除原生 `confirm`，角色卡和 trace summary 改为可键盘访问的 button。
5. Collaboration Contract 改为优先读取上游 artifact 内容，避免因字段名或空列表产生假失败。
6. Self-check 的 `reroute/ask_human/refuse` 决策在 real mode 下会阻止保存；stub mode 保持演示和历史回归稳定。
7. `scripts/eval_agents.py` 修复 capability pack 执行逻辑，`skill_ok/skill_not_ok` 断言现在真实执行 package skill。
8. `chapter.version_diff` 工具修复为调用现有 `list_chapter_versions` repository API。
9. 新增 `tests/test_v60_review_fixes.py` 覆盖上述 runtime 接入点。

## 已知限制

1. **真实 LLM 项目验收**：仍需创建全新小说项目，用线上真实 LLM 跑人工创作流程。
2. **E2E eval**：当前 `scripts/eval_agents.py all` 的 E2E 项仍为 skipped，需要后续接入真实项目夹具。
3. **外部工具**：web_search、file.import_reference、http.request、bash.run 已注册但 handler 未实现，且按 spec 默认禁用。
4. **Genre Strategy runtime 深度**：策略文件已就绪，但还需要在真实 LLM 验收中评估注入强度和 token 噪音。

## 结论

v6.0 Agent Role Capability System 的核心能力闭环已完成。系统现在具备：
- 7 个核心 Agent 的 Role Profile
- Package-style Capability Pack 体系
- Agent Memory 存储和管理
- Bounded Autonomy 决策框架
- 受控 Tool Runtime
- Self-check / Local Repair 循环
- Collaboration Contract
- Decision Trace 持久化
- AgentOps UI
- Eval Harness

后续可在真实 LLM 项目中进行验收和调优。
