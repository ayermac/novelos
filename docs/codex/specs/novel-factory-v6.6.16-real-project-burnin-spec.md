# v6.6.16 Real Project Burn-in & Regression Closure

**Version**: 6.6.16  
**Status**: Completed  
**Date**: 2026-05-20

## 概述

v6.6.16 使用真实项目数据（异常修正员）进行 burn-in，覆盖"创世 → 章节 → 记忆 → 发布 → 下一章继承"全链路，并修复发现的问题。

## 新增内容

### Burn-in Fixture

`tests/fixtures/burnin_project.py`

以《异常修正员》为主题的完整项目 fixture：
- 世界设定: 4 条（异常等级、修正员编制、平行现实、技术设定）
- 角色: 6 名（郑行舟、李墨言、宋晚晴、魏延昭、郑行雨、许正阳）
- 势力: 2 个（ACB 深市分局、白塔组织）
- 大纲: 3 章
- 伏笔: 4 条
- 章指令: 第 1-3 章
- 已批准创世设定

### Burn-in 测试

`tests/test_v6616_real_project_burnin.py` — 29 个测试：

| 测试类 | 测试数 | 覆盖 |
|--------|--------|------|
| TestBurninFixtureIntegrity | 4 | 项目创建、context 就绪、伏笔存在、章存在 |
| TestChapter1StubGeneration | 3 | 生成到合法终态、domain_result 存在、无假绿 |
| TestRunDetailObservability | 2 | runs 列表、run detail contract |
| TestMemoryStatusMapping | 2 | memory status 可用、无 trusted 时不误报 |
| TestMemoryBackfillAPI | 3 | backfill 成功和错误路径 domain_result |
| TestWorkflowTimelineNodes | 2 | node events 存在、memory_curator 无假绿 |
| TestPublishGuard | 3 | 状态检查、错误 domain_result、内容不丢失 |
| TestChapter2ContextInheritance | 3 | batch_status 非 not_applicable、run detail audit、planner context |
| TestPlotHoleObservability | 1 | 伏笔可观测 |
| TestNoSensitiveLeak | 3 | 无密钥泄露到 stdout/stderr/artifacts |
| TestVersionIsV6616 | 2 | 版本号统一 |
| TestManualBurninScript | 1 | 手动 burn-in 脚本真实跑 fixture |

### 手动 Burn-in 脚本

`scripts/burnin_real_project.py`:

```bash
# Stub mode (默认)
python scripts/burnin_real_project.py

# Real mode (需要 API key)
python scripts/burnin_real_project.py --real-mode

# 指定 config
python scripts/burnin_real_project.py --config config/local.yaml --real-mode
```

## 发现并修复的 Bug

### 1. CLI run-chapter 不输出 domain_result

**问题**: `cmd_run_chapter` 直接返回 `run_with_graph` 的原始结果，没有 domain_result 字段。
**修复**: 新增 `_build_cli_domain_result()` 函数，在 CLI 输出中嵌入与 API 一致的 domain_result。
**测试**: `test_chapter1_has_domain_result` 验证 CLI 输出包含 domain_result。

### 2. Burn-in fixture 缺少 genesis run

**问题**: fixture 没有 approved genesis run，导致 chapter run 被 CONTEXT_INCOMPLETE gate 拦截。
**修复**: 在 fixture 的 project 创建后添加 approved genesis run 记录。

### 3. Faction 表无 status 列

**问题**: 原 fixture 代码假设 factions 表有 status 列。
**修复**: 移除 INSERT 中的 status 字段。

### 4. 手动 burn-in 脚本假绿

**问题**: 初版脚本使用 demo seed、CLI 参数顺序错误时继续执行，并且没有对 run/chapter 结果做硬断言。
**修复**: 改为直接初始化真实 fixture，再通过 CLI/API 逐步断言。失败时退出非 0。

### 5. 预置章节指令跳过 Planner 导致审计缺失

**问题**: 预置 instruction 的章节会直接进入 Screenwriter，Planner 不会写 `memory_context_audit`。
**修复**: Screenwriter 前补写缺失的 `memory_context_audit`，并用 `built_at_node` 标识来源。

### 6. API 错误路径缺少 domain_result

**问题**: memory backfill / publish 的错误路径没有统一 contract。
**修复**: 为 blocked/failed 错误响应补齐 `error.details.domain_result`。

## 验证结果

```
tests/ -q:              2596 passed
test_v6616:              29 passed
frontend typecheck:      passed
frontend lint:           passed
frontend build:          passed
git diff --check:        clean
docs/superpowers/:       excluded from git
```

## 已知未解决风险

1. `plot_holes` compliance 仍延期到 v6.6.17
2. 低风险 UX 优化延期
3. CI/CD 中 DMG 全量构建未启用
