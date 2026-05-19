# v6.6.15 Release Readiness & Desktop Packaging Closure - Completion Report

**Version**: 6.6.15
**Date**: 2026-05-19
**Status**: Completed

## 执行摘要

v6.6.15 完成了发布前收口工作，统一版本号、验证迁移健康、确认桌面打包链路，新增 stub 全链路冒烟测试。

## 完成项

### 1. 版本统一

| 文件 | 旧版本 | 新版本 |
|------|--------|--------|
| `novel_factory/version.py` | 6.6.14 | 6.6.15 |
| `frontend/package.json` | 6.6.14 | 6.6.15 |
| `desktop/package.json` | 6.8.0-m6 | 6.6.15 |

- `docs/superpowers/` 确认不在 git 中

### 2. 迁移健康

- 现有 `check_migration_health` / `check_table_integrity` 功能完整
- 新增 smoke 测试：空库 init、重复 init、覆盖率、核心表

### 3. 桌面打包

- 版本号统一
- 构建脚本增加版本号显示和 `--dir`/`--dmg` 说明
- 新增打包脚本静态检查测试

### 4. Stub 全链路 Smoke Test

- init_db → seed → run chapter 1 → 状态验证
- Chapter 2 planner audit（显式补第 2 章且不预置 instruction，确保 Planner 运行）
- Workflow timeline node semantics（通过 API 检查 node_status/domain_status/severity）
- 全部 stub 模式，无真实 LLM 调用

### 5. 文档

- `docs/codex/specs/novel-factory-v6.6.15-release-readiness-spec.md`
- `docs/codex/reports/novel-factory-v6.6.15-completion-report.md`
- `docs/codex/reviews/novel-factory-v6.6.15-review.md`
- `CHANGELOG.md` 更新

## 变更文件清单

| 文件 | 类型 |
|------|------|
| `novel_factory/version.py` | 修改 |
| `frontend/package.json` | 修改 |
| `desktop/package.json` | 修改 |
| `packaging/scripts/build-desktop-mac.sh` | 修改 |
| `CHANGELOG.md` | 修改 |
| `tests/test_v6615_release_readiness.py` | 新增 |
| `docs/codex/specs/novel-factory-v6.6.15-release-readiness-spec.md` | 新增 |
| `docs/codex/reports/novel-factory-v6.6.15-completion-report.md` | 新增 |
| `docs/codex/reviews/novel-factory-v6.6.15-review.md` | 新增 |

## 测试结果

```
tests/test_v6615_release_readiness.py — 27 passed
  TestVersionUniformity — 6 passed
  TestFreshDbMigrationHealth — 2 passed
  TestInitDbIdempotency — 2 passed
  TestRegistryCoverage — 2 passed
  TestCriticalTableIntegrity — 2 passed
  TestPackagingScriptExistence — 4 passed
  TestStubFullChainSmoke — 4 passed
  TestDocumentationExists — 3 passed
  TestNoLeaksOrRegressions — 2 passed
```

## 打包命令

```bash
# 构建本地 app
bash packaging/scripts/build-desktop-mac.sh --dir
# 输出：desktop/release/mac-arm64/Novelos.app

# 构建 DMG
bash packaging/scripts/build-desktop-mac.sh --dmg
# 输出：desktop/release/Novelos-*.dmg

# 跳过 sidecar（复用已有）
bash packaging/scripts/build-desktop-mac.sh --dir --skip-sidecar
```

## 发现并修复的问题

1. `desktop/package.json` 版本号为 `6.8.0-m6`，不符合统一版本规范 → 修正为 `6.6.15`
2. 构建脚本缺少版本号输出 → 新增版本号显示
3. Release smoke 测试存在假绿风险：
   - run detail 只断言 CLI `runs` 输出非空
   - chapter 2 不存在时 CLI payload `ok=false` 仍会被旧测试放过
   - workflow timeline 只查 raw DB event status，没有查 API contract 字段
   → 已改为真实 API 断言，并让第 2 章触发 Planner audit。

## 未解决风险

1. `plot_holes` compliance 可延期到 v6.6.16
2. 低风险 UI 体验优化记录到 v6.6.16
3. Electron DMG 全量构建未在 CI 中执行（耗时较长）

## v6.6.16 建议

1. `plot_holes` compliance 实现
2. 低风险 UI 体验优化
3. 长时运行稳定性测试
4. 打包 DMG 签名/公证流程验证
