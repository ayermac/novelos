# v6.3 Creator Onboarding Closure 完成报告

## 总体 verdict：PASS

## 改动文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `novel_factory/api/routes/_run_guards.py` | 修改 | 新增 Guard 4 `CONTEXT_INCOMPLETE` |
| `novel_factory/api/routes/production.py` | 修改 | `health` 新增 `ready_for_chapter_1` |
| `novel_factory/api/routes/onboarding.py` | 修改 | 默认章节标题增加"待命名" |
| `frontend/src/components/project/GenesisModule.tsx` | 修改 | premise 改为可选 |
| `frontend/src/components/project/ProjectOverviewModule.tsx` | 修改 | `generate_chapter` 不再 `auto_generate=1` |
| `frontend/src/pages/ProjectDetail.tsx` | 修改 | 移除 `auto_generate` 自动触发 effect |
| `frontend/src/pages/Onboarding.tsx` | 未改 | 已有正确的 `module=overview` 跳转 |
| `tests/test_v63_creator_onboarding.py` | 新增 | 6 个测试覆盖 guard / health / 标题 |
| `tests/test_v5515_production_readiness.py` | 修改 | 适配 guard 后的上下文要求 |
| `docs/codex/README.md` | 修改 | 更新当前基线和下一步 |
| `docs/codex/planning/novel-factory-cross-platform-desktop-client-plan.md` | 修改 | v6.3 标记为已实现 |
| `docs/codex/planning/novel-factory-v6.3-creator-onboarding-closure-spec.md` | 新增 | 规格文档 |

## 用户流程变化

**Before：**
1. 创建项目 → 进入准备工作台
2. 点击"生成第 1 章" → 自动跳转到 workflow 并立即开始生成
3. 如果缺少 context，生成失败或输出质量差

**After：**
1. 创建项目 → 进入准备工作台
2. production-next 推荐"生成项目设定"
3. Genesis 中可留空 premise，一键生成
4. 批准后 production-next 推荐"补齐缺失资料"
5. 资料齐全后 `ready_for_chapter_1=true`
6. 点击"生成第 1 章" → 进入章节内容页（不自动开始）
7. 用户明确点击"生成"按钮才开始 workflow
8. 如果 context 不 ready，后端 guard 返回 `CONTEXT_INCOMPLETE`

## 测试结果

| 命令 | 结果 |
|---|---|
| `python3 scripts/verify.py smoke` | **13 passed** |
| `python3 -m pytest tests/test_v63_creator_onboarding.py -q` | **6 passed** |
| `cd frontend && npm run typecheck` | **通过** |
| `cd frontend && npm run lint` | **通过** |
| `cd frontend && npm run build` | **通过** |
| `cd frontend && npm run test -- --run` | **169 passed** |
| `cd desktop && npm run typecheck` | **通过** |
| `cd desktop && npm run build` | **通过** |

## 已知限制

- `ready_for_chapter_1` 在前端页面中尚未作为显式 UI 状态展示（仅通过 production-next 的 missing 列表间接表达）。
- "一键补齐缺失资料"按钮已存在（`handleAutoFill`），但没有单独的"一键生成创世设定"按钮（用户需进入 GenesisModule 点击生成）。
- 章节标题截断问题（如果 author agent 生成过长标题）未在本次修改中处理，因为标题由 LLM 生成，截断取决于具体模型输出。

## 安全继续开发：是
