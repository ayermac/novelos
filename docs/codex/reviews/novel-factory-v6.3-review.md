# v6.3 Creator Onboarding Closure Review

## 总体 verdict：PASS（v6.3.2 回归干净）

## Review 检查项

### 1. 创建后不落点 workflow
- [x] `ProjectOverviewModule.handlePrimaryAction` 中 `generate_chapter` 不再带 `auto_generate=1`
- [x] `ProjectDetail` 中 `auto_generate` 自动触发 effect 已移除
- [x] `Onboarding` 成功页跳转 `module=overview`（已有行为，未改）

### 2. Genesis 不重复要求 title/genre
- [x] `GenesisModule` 中 title/genre 从 project prop 继承，显示为只读上下文
- [x] premise 改为可选，validateForm 不再检查 premise 非空

### 3. "10章"概念清晰
- [x] "首批规划章数" label 已存在
- [x] helper 文案解释"用于生成前 N 章章节指令，后续可继续扩展"
- [x] 空状态文案解释"不代表整本书总章数"

### 4. 一键 AI 生成创世设定
- [x] GenesisModule 中 premise 留空即可生成
- [x] 表单中 title/genre 从项目继承，无需重复填写

### 5. 第一章生成前 guard
- [x] `_run_guards.py` 新增 Guard 4 `CONTEXT_INCOMPLETE`
- [x] 检查 approved genesis + world + characters + outlines + instructions
- [x] 缺失时返回明确的用户可读错误
- [x] `production-next` 返回 `ready_for_chapter_1` 字段

### 6. 章节标题一致性
- [x] `onboarding.py` 默认标题改为 `第 N 章（待命名）`
- [x] 避免无意义默认标题

### 7. 代码质量
- [x] 前端 typecheck 通过
- [x] 前端 lint 通过（max-warnings 0）
- [x] 前端 build 通过
- [x] 前端 vitest 169/169 通过
- [x] desktop typecheck/build 通过
- [x] Python smoke 13/13 通过
- [x] 新增测试 6/6 通过
- [x] **backend full suite 1980 passed, 0 failed**

### 8. 文档
- [x] `docs/codex/README.md` 已更新
- [x] `docs/codex/planning/novel-factory-cross-platform-desktop-client-plan.md` 已更新
- [x] 新增 spec、completion report、review

## Review Findings 与修复

### v6.3.1 修复

| Finding | 根因 | 修复 |
|---|---|---|
| premise 前后端不一致 | 后端 validateForm 检查 premise 非空，但前端已改为可选 | 后端同步允许空 premise，更新测试覆盖 |
| production-next / run guard readiness 不一致 | `ready_for_chapter_1` 与 `_run_guards` 的检查逻辑不统一 | v6.3.1 统一为 approved genesis + world + characters + outlines + instruction |

### v6.3.2 修复

| Finding | 根因 | 修复 |
|---|---|---|
| 旧 `auto_generate` 测试失败 | v6.3 移除 `auto_generate=1`，但静态测试仍断言包含该参数 | 更新 `test_v553_autonomous_production_loop.py` 断言为不包含 `auto_generate=1` |
| 空 premise 测试覆盖不完整 | 空 premise 测试仍传了非空 `description` | 将 `description` 改为空字符串 `""` |
| CONTEXT_INCOMPLETE guard 文案误导 | 旧文案"请先完成创世设定审核"暗示 genesis 存在即可，未强调"批准" | 更新为"请先完成并批准创世设定，再补齐项目资料后生成章节" |
| workflow stub/fixture 回归失败（1 failed） | v6.0 引入的 Screenwriter stub 缺少 `turn`/`plot_refs`；`seed_context_for_chapter` 未创建 approved genesis 和 instruction | `stub_provider.py` 补齐字段；`conftest.py` 添加 approved genesis run 和 instruction 创建，并将 `key_events` 对齐 stub author 的 `implemented_events` |

## 安全继续开发：是
