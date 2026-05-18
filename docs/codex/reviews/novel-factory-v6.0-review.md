# Novelos v6.0 Agent Role Capability System — Review

## 范围评估

### 已完成

1. Agent Role Profile（7 个角色 YAML + 加载器）
2. Capability Pack 迁移（4 个 v5.9.3 skill → package）
3. Role-specific 默认能力定义（每个 Agent ≥3 个）
4. Agent Memory 表 + Repository + API + UI
5. Bounded Autonomy Policy（决策对象 + 硬约束）
6. Tool Runtime Registry（8 内建 + 4 外部禁用）
7. Self-check / Local Repair Loop
8. Collaboration Contracts（6 个 canonical）
9. Decision Trace 持久化
10. AgentOps UI（5 个 React 组件）
11. Eval Harness（scripts/eval_agents.py + fixtures）
12. Genre Strategy 配置（5 个类型）

### 本轮 Review 修复

1. **v6 上下文空转**：核心 Agent 原本仍调用 `build_context()`，未注入 role profile 和 Agent Memory；已改为调用 `_build_v6_context()`。
2. **AgentOps API 断链**：前端路径和后端 prefix 不一致，trace API 也只读新建内存 store；已修正路径并从 DB 读取持久化 trace。
3. **Decision Trace 未提交**：`save_agent_decision_trace()` 使用两个 SQLite 连接导致 insert 未 commit；已改为同一连接执行和提交。
4. **Agent Memory API 断链**：接口依赖不存在的 `app.state.db_conn`；已改为使用标准 `get_repo(request)`。
5. **Self-check 只记录不生效**：`reroute/ask_human/refuse` 原本仍继续保存输出；已在 real mode 下阻止保存，stub mode 保持演示稳定。
6. **Contract 假失败**：handoff 校验没有读取真实上游 artifact，且空列表被当成缺失；已修正 artifact 读取和字段判定。
7. **Eval 空转**：eval case 的 `must_pass` 未触发 skill 执行，且未支持 `skill_not_ok`；已修复为真实运行 package skill。
8. **Tool Runtime 断点**：`chapter.version_diff` 调用不存在的 `repo.get_versions()`；已改为 `list_chapter_versions()`。
9. **AgentOps UI 基础交互**：移除原生 `confirm`，角色卡/trace summary 改为 button，保留键盘可访问性。

### 待后续增强

1. **真实 LLM 项目验收**：需要创建新小说项目，使用真实 LLM，完整走通创作流程。
2. **E2E eval**：当前 `scripts/eval_agents.py all` 的 E2E 项仍为 skipped。
3. **外部工具 handler 实现**：web_search、file 等工具仍按 spec 默认禁用，后续如启用必须补 handler、授权和审计。
4. **Genre Strategy runtime 调优**：策略文件已就绪，需通过真实 LLM 验收确定注入强度。

## 架构质量

### 优点

- 不引入外部 Agent 框架，保持 LangGraph 主干
- 所有新增能力都有结构化数据模型
- 外部工具默认禁用，安全性可控
- 向后兼容：老 Skill 继续运行，旧项目不受影响
- 前端类型安全，lint 通过

### 风险

- Agent Memory 和 Decision Trace 仍采用 best-effort 策略，但当前 DB 持久化和读取链路已通过回归测试。
- Self-check 已接入 Author、Screenwriter、MemoryCurator；真实 LLM 下会阻止不可修复输出保存。
- Eval 框架已能真实执行 capability package，但 E2E eval 仍需真实项目夹具。

## 建议

1. 在真实 LLM 项目中验证 Agent Memory 的可用性和可信度。
2. 补齐 E2E eval，使 `scripts/eval_agents.py all` 不再跳过端到端项目流程。
3. 逐步将 Genre Strategy 注入到各 Agent 的 prompt context 中，并观察 token 噪音。
4. 外部工具继续保持默认禁用；只有明确产品场景时再实现最小 handler。

## 回归结论

- 后端 pytest：1917/1917 passed
- `python3 scripts/verify.py smoke`：通过
- `python3 scripts/eval_agents.py all`：30/30 passed
- 前端 typecheck/lint/build/test：全部通过，vitest 148/148 passed
- build 仅保留既有 Vite chunk-size warning

推荐合并到主线，后续迭代继续增强 runtime 集成。
