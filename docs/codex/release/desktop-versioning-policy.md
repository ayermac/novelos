# Novelos 桌面客户端版本规则

本文档定义桌面客户端各版本号的来源、同步规则和发布标识约定。

---

## 版本号来源

桌面客户端涉及以下版本号位置：

| 位置 | 文件/接口 | 当前示例 |
|---|---|---|
| Desktop package | `desktop/package.json` → `version` | `6.8.0-m6` |
| Desktop package lock | `desktop/package-lock.json` → `version` | 应与 `package.json` 一致 |
| Runtime API | `/api/desktop/runtime-info` → `version` | 后端返回 `5.3.0`（novel-factory 包版本） |
| 文档标识 | `docs/codex/README.md` 当前进度 | `v6.2.5 Desktop Release Readiness Checklist` |

---

## 同步规则

### 必须同步的版本号

1. **`desktop/package.json` 与 `desktop/package-lock.json`**
   - 每次修改 `package.json` 的 `version` 后，必须运行：
     ```bash
     cd desktop && npm install
     ```
   - 这会自动更新 `package-lock.json` 中的 `version` 字段。
   - **两者必须始终一致**。

2. **`desktop/package.json` version 与文档标识**
   - 当 `package.json` 的 `version` 发生里程碑变更时（如从 `6.8.0-m5` 到 `6.8.0-m6`），同步更新：
     - `docs/codex/README.md` 中的"当前桌面客户端基线"。
     - `docs/codex/planning/novel-factory-cross-platform-desktop-client-plan.md` 中对应里程碑的状态。

### 不需要同步的版本号

- **后端 `/api/desktop/runtime-info` 的 `version`**：这是 `novel-factory` Python 包的版本，与桌面客户端版本独立演进。桌面版本可能领先或落后于后端版本，这是正常状态。

---

## 版本号语义

桌面客户端采用 `MAJOR.MINOR.PATCH[-prerelease]` 格式：

```text
6.8.0-m6
│ │ │ │
│ │ │ └── 预发布/里程碑标识（可选）
│ │ └──── 补丁版本（bugfix、小修复）
│ └────── 次要版本（功能迭代）
└──────── 主版本（重大架构变更）
```

### 里程碑标识约定

| 标识 | 含义 | 示例 |
|---|---|---|
| `-m0` | 技术验证（M0 Proof of Concept） | `6.5.0-m0` |
| `-m1` | Sidecar 冻结 | `6.5.0-m1` |
| `-m2` | Electron 打包 | `6.6.0-m2` |
| `-m3` | 数据目录与配置 | `6.7.0-m3` |
| `-m4` | API Key 安全 | `6.7.0-m4` |
| `-m5` | 稳定性与恢复 | `6.7.0-m5` |
| `-m6` | 发布诊断与清单 | `6.8.0-m6` |
| 无后缀 | 正式发布候选（RC）或稳定版 | `6.8.0` |

### 版本变更触发条件

| 变更类型 | 版本位 | 示例 |
|---|---|---|
| 里程碑完成 | 更新 milestone 后缀或 minor | `6.8.0-m6` → `6.9.0-m0` |
| 新功能加入 | 更新 minor | `6.8.0` → `6.9.0` |
| Bugfix / 安全修复 | 更新 patch | `6.8.0` → `6.8.1` |
| 重大架构重构 | 更新 major | `6.8.0` → `7.0.0` |

---

## Release Tag 命名建议

Git tag 用于标记发布点：

```text
desktop-v<version>-<platform>
```

示例：

```text
desktop-v6.8.0-m6-darwin-arm64
desktop-v6.8.0-darwin-arm64
desktop-v6.8.0-darwin-x64
```

**规则：**
- 带 `-mN` 后缀的 tag 代表**开发里程碑**，不对外分发。
- 不带后缀的 tag 代表**正式发布候选**，可用于内测或公开下载。
- tag 必须打在包含 `verification-report.json` 和 `release-manifest.json` 的 commit 上。

---

## Commit Hash 进入产物

### verification-report.json

`packaging/scripts/verify-desktop-mac.sh` 在成功或失败时都会写入：

```json
{
  "commit": "<full-sha>",
  "branch": "<branch-name>"
}
```

### release-manifest.json

`packaging/scripts/write-desktop-release-manifest.sh` 写入：

```json
{
  "commit": "<full-sha>",
  "branch": "<branch-name>"
}
```

**规则：**
- 使用 `git rev-parse HEAD` 获取完整 SHA，不用缩写。
- 使用 `git rev-parse --abbrev-ref HEAD` 获取分支名。
- 如果工作区不干净（`git status --porcelain` 有输出），在 `branch` 字段追加 `-dirty`，如 `codex-v6.2-desktop-m0-poc-dirty`。

---

## 哪些版本号代表开发里程碑，哪些代表正式发布候选

| 类型 | 标识 | 使用场景 | 可否分发 |
|---|---|---|---|
| 开发里程碑 | `-m0` 到 `-m6` | 内部技术验证、功能阶段性验收 | 不推荐 |
| RC（Release Candidate） | `-rc1`, `-rc2` | 发布前最后一轮测试 | 内测范围 |
| 稳定版 | 无后缀 | 对外公开分发 | 可以 |

---

## 版本变更检查清单

当需要提升桌面客户端版本号时，按以下顺序操作：

1. [ ] 修改 `desktop/package.json` 的 `version` 字段。
2. [ ] 运行 `cd desktop && npm install` 更新 `package-lock.json`。
3. [ ] 运行 `cd desktop && npm run typecheck && npm run build` 确认无编译错误。
4. [ ] 更新 `docs/codex/README.md` 中的当前基线描述。
5. [ ] 更新 `docs/codex/planning/novel-factory-cross-platform-desktop-client-plan.md` 中对应里程碑状态。
6. [ ] 运行完整验证：`bash packaging/scripts/verify-desktop-mac.sh`。
7. [ ] 生成 manifest：`bash packaging/scripts/write-desktop-release-manifest.sh`。
8. [ ] 提交 commit，message 包含版本号，如 `chore(desktop): bump version to 6.9.0-m0`。
9. [ ] 打 tag（如适用）：`git tag desktop-v6.9.0-m0-darwin-arm64`。

---

## 相关文档

- [desktop-release-checklist.md](desktop-release-checklist.md) — 发布前检查清单
- [desktop/README.md](../../../desktop/README.md) — 桌面客户端技术文档
