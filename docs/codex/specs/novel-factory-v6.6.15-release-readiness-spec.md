# v6.6.15 Release Readiness & Desktop Packaging Closure

**Version**: 6.6.15
**Status**: Completed
**Date**: 2026-05-19

## 概述

v6.6.15 是发布前收口版本，不做新功能，专注于版本统一、迁移健康、桌面打包链路和 stub 真实链路冒烟测试。

## 核心原则

1. 不改 LangGraph 主拓扑
2. 不引入新业务功能
3. 不做大规模 UI 改版
4. 不提交 `docs/superpowers/` 临时计划目录
5. 不删除用户数据
6. 所有改动以发布可用性、诊断、文档、打包链路为中心
7. 高风险 bug 可修，低风险体验优化记录到 v6.6.16

## 实施内容

### Task 1 — 版本与发布元数据

| 文件 | 变更 |
|------|------|
| `novel_factory/version.py` | `6.6.14` → `6.6.15` |
| `frontend/package.json` | `6.6.14` → `6.6.15` |
| `desktop/package.json` | `6.8.0-m6` → `6.6.15` |
| `CHANGELOG.md` | 新增 v6.6.15 条目 |
| `packaging/scripts/build-desktop-mac.sh` | 新增版本号显示 |

所有版本来源统一为 `6.6.15`：
- `novel_factory/version.py`
- `frontend/package.json`
- `desktop/package.json`
- FastAPI app metadata（自动关联 `get_version()`）
- `/api/health`（自动关联）
- CLI `--version`（自动关联）
- 桌面构建脚本

### Task 2 — 迁移与数据库健康

现有能力无需新建：
- `migration_registry.py` 已有 `check_migration_health()` 和 `check_table_integrity()`
- `test_v669_migration_integrity.py` 已有 70+ 个迁移测试
- `test_init_db_idempotency.py` 已有幂等性测试

v6.6.15 新增：
- `test_v6615_release_readiness.py` 中的冒烟测试覆盖：
  1. 新空库 init_db 后 migration health clean
  2. 重复 init_db 幂等
  3. registry coverage >= 1.0
  4. 核心表存在

### Task 3 — 桌面打包链路

| 文件 | 变更 |
|------|------|
| `desktop/package.json` | 版本号统一至 `6.6.15` |
| `packaging/scripts/build-desktop-mac.sh` | 新增版本号显示、`--dir`/`--dmg` 说明 |

打包命令说明：

```bash
# 构建本地 .app（开发验证）
bash packaging/scripts/build-desktop-mac.sh --dir
# 输出：desktop/release/mac-arm64/Novelos.app

# 构建 .app + DMG 安装包
bash packaging/scripts/build-desktop-mac.sh --dmg
# 输出：desktop/release/Novelos-*.dmg

# 跳过 sidecar 构建（复用已有）
bash packaging/scripts/build-desktop-mac.sh --dir --skip-sidecar
```

### Task 4 — Stub 真实链路 Smoke Test

`test_v6615_release_readiness.py::TestStubFullChainSmoke` 覆盖：

1. 初始化 DB → 创建项目 → 补齐上下文
2. 运行第 1 章生成 → 检查章节状态到 reviewed/awaiting_publish/published
3. 检查 run detail 返回数据
4. 运行第 2 章 → 确认 Planner audit 存在
5. 检查 workflow timeline node semantics

所有测试使用临时 SQLite 数据库和 stub LLM，无真实 LLM 调用。

### Task 5 — 文档

新增文档：
- `docs/codex/specs/novel-factory-v6.6.15-release-readiness-spec.md`
- `docs/codex/reports/novel-factory-v6.6.15-completion-report.md`
- `docs/codex/reviews/novel-factory-v6.6.15-review.md`

更新文档：
- `CHANGELOG.md` — 新增 v6.6.15 条目

## 打包命令

```bash
# 构建本地 app
bash packaging/scripts/build-desktop-mac.sh --dir

# 构建 DMG
bash packaging/scripts/build-desktop-mac.sh --dmg
```

- `--dir`：构建 `desktop/release/mac-arm64/Novelos.app`（用于本地开发验证）
- `--dmg`：构建 .app + DMG 安装包

## Smoke Test 覆盖范围

| 测试 | 覆盖内容 |
|------|---------|
| TestVersionUniformity | 版本号统一检查 |
| TestFreshDbMigrationHealth | 空库 init 健康 |
| TestInitDbIdempotency | 重复 init |
| TestRegistryCoverage | 注册表覆盖 |
| TestCriticalTableIntegrity | 核心表存在 |
| TestPackagingScriptExistence | 打包脚本存在 |
| TestStubFullChainSmoke | Stub 全链路 |
| TestNoLeaksOrRegressions | 无敏感泄露 |

## 已知未解决风险

1. `plot_holes` compliance 可延期到 v6.6.16
2. 低风险 UI 体验优化记录到 v6.6.16
3. 桌面全量 DMG 构建耗时较长，建议在 CI/CD 中执行

## v6.6.16 Burn-in 建议

1. `plot_holes` compliance 实现
2. 低风险 UI 体验优化
3. 长时运行稳定性测试
4. 打包 DMG 签名/公证流程验证
