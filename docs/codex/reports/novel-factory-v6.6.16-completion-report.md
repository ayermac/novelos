# v6.6.16 Real Project Burn-in & Regression Closure - Completion Report

**Version**: 6.6.16  
**Date**: 2026-05-20  
**Status**: Completed

## 执行摘要

使用真实项目数据（异常修正员）完成全链路 burn-in，修复 CLI domain_result 缺失等问题。

## 修改文件清单

| 文件 | 变更 |
|------|------|
| `novel_factory/version.py` | `6.6.15` → `6.6.16` |
| `frontend/package.json` | `6.6.15` → `6.6.16` |
| `desktop/package.json` | `6.6.15` → `6.6.16` |
| `novel_factory/cli_app/commands/core.py` | 新增 CLI domain_result helper |
| `novel_factory/api/routes/run.py` | 补齐 publish 错误路径 domain_result |
| `novel_factory/api/routes/runs.py` | 补齐 memory backfill 错误路径 domain_result |
| `novel_factory/workflow/nodes.py` | 预置指令跳过 Planner 时补写 memory_context_audit |
| `CHANGELOG.md` | 新增 v6.6.16 条目 |
| `tests/fixtures/__init__.py` | 新增 |
| `tests/fixtures/burnin_project.py` | 新增 异常修正员 fixture |
| `tests/test_v6616_real_project_burnin.py` | 新增 29 个 burn-in 测试 |
| `scripts/burnin_real_project.py` | 新增 手动 burn-in 脚本 |
| `docs/codex/specs/novel-factory-v6.6.16-real-project-burnin-spec.md` | 新增 |
| `docs/codex/reports/novel-factory-v6.6.16-completion-report.md` | 新增 |
| `docs/codex/reviews/novel-factory-v6.6.16-review.md` | 新增 |

## Burn-in 链路实际跑通步骤

1. init_db + seed_burnin_project fixture 初始化
2. Chapter 1 进入 `published` 终态
3. domain_result 输出 `success`
4. memory_status 为 `trusted` 或其他明确状态，不允许无可信批次时误报 trusted
5. publish guard 正常工作
6. Chapter 2 生成成功，memory_context_audit 存在且不是 `not_applicable`
7. workflow timeline node events 记录完整
8. 无敏感信息泄露

## 发现并修复的问题

1. **CLI domain_result 缺失** — `cmd_run_chapter` 不输出 domain_result → 新增 `_build_cli_domain_result()`
2. **Fixture genesis 缺失** — 无 approved genesis → 添加 genesis run 记录
3. **Faction 表 schema** — status 列不存在 → 移除该字段
4. **手动 burn-in 脚本假绿** — 旧脚本使用 demo seed、命令参数顺序错误且没有硬失败 → 改为直接初始化真实 fixture，并逐步断言 CLI/API 链路
5. **API 错误语义缺口** — memory backfill / publish 的错误路径缺少 `domain_result` → 补齐 blocked/failed contract
6. **预置指令跳过 Planner 导致审计消失** — Chapter 2 已有 instruction 时直接进入 Screenwriter，Planner 不会写 `memory_context_audit` → 在 Screenwriter 前补写审计 artifact

## 未解决风险

1. `plot_holes` compliance 延期到 v6.6.17
2. 低风险 UX 优化延期
3. Electron DMG 全量构建未在 CI 中执行

## 验证结果

```
pytest tests/ -q:             2596 passed
test_v6615_release:           27 passed
test_v6616_burnin:            29 passed
frontend typecheck:           passed
frontend lint:                passed
frontend build:               passed
git diff --check:             clean
docs/superpowers/:            not in git
```
