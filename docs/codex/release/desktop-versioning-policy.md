# Novelos 桌面客户端版本规则

本文档补充桌面产物的标识与打包约定。产品级版本的唯一规范见 [version-policy.md](version-policy.md)。

## 版本号来源

桌面客户端不再独立演进产品版本。以下位置必须使用 `novel_factory/version.py` 的 `__version__`：

| 位置 | 文件/接口 | 规则 |
|---|---|---|
| Runtime source | `novel_factory/version.py` → `__version__` | 唯一真相源 |
| Desktop package | `desktop/package.json` → `version` | 必须等于 runtime |
| Desktop package lock | `desktop/package-lock.json` 根和 `packages[""]` → `version` | 必须等于 package 与 runtime |
| Runtime API | `/api/desktop/runtime-info` → `version` | 必须等于 runtime |

历史文档中的 `-mN` 桌面里程碑版本只代表当时的内部打包阶段，不再作为当前版本策略。

## 同步与验证

版本提升时按以下顺序操作：

1. 先修改 `novel_factory/version.py`。
2. 将相同的 `MAJOR.MINOR.PATCH` 值同步到 `pyproject.toml`、`uv.lock`、frontend、desktop 及两个 npm lockfile。
3. 在 `CHANGELOG.md` 添加目标版本标题。
4. 运行 `python3 scripts/release_preflight.py`。
5. 发布证据只使用 `python3 scripts/verify.py release`。

不要只运行 `npm install` 后假定版本已经对齐；preflight 会同时检查 package-lock 顶层版本和 `packages[""]` 根包版本。

## 版本号语义

正式产品版本采用纯 `MAJOR.MINOR.PATCH`：

```text
6.11.02
│ │  │
│ │  └── 补丁与发布完整性修复
│ └───── 次版本功能与架构演进
└─────── 主版本兼容性边界
```

开发里程碑、RC 状态和渠道信息应写入 changelog、release manifest 或 tag，不写入产品 runtime 版本。

## Release Tag 命名

产品发布点使用：

```text
v<version>
```

平台构建产物需要独立标识时，可追加平台：

```text
desktop-v<version>-<platform>
```

例如：

```text
v6.11.02
desktop-v6.11.02-darwin-arm64
desktop-v6.11.02-darwin-x64
```

tag 必须指向已经通过 release gate、并包含 `verification-report.json` 和 `release-manifest.json` 的提交。

## Commit Hash 进入产物

`packaging/scripts/verify-desktop-mac.sh` 和 `packaging/scripts/write-desktop-release-manifest.sh` 应记录：

```json
{
  "commit": "<full-sha>",
  "branch": "<branch-name>"
}
```

- 使用 `git rev-parse HEAD` 获取完整 SHA。
- 使用 `git rev-parse --abbrev-ref HEAD` 获取分支名。
- 工作区不干净时，在 manifest 中显式记录 dirty 状态；不得把 dirty 构建描述为正式发布证据。

## 桌面版本变更检查清单

1. [ ] runtime、Python package、frontend、desktop 与 lockfile 版本完全一致。
2. [ ] `python3 scripts/release_preflight.py` 通过。
3. [ ] `cd desktop && npm run typecheck && npm run build` 通过。
4. [ ] `bash packaging/scripts/verify-desktop-mac.sh` 通过。
5. [ ] `bash packaging/scripts/write-desktop-release-manifest.sh` 生成 manifest。
6. [ ] `python3 scripts/verify.py release` 通过。
7. [ ] 工作区与提交 SHA 满足发布要求后再创建 tag。

## 相关文档

- [version-policy.md](version-policy.md) — 产品统一版本策略
- [desktop-release-checklist.md](desktop-release-checklist.md) — 桌面发布前检查清单
- [desktop/README.md](../../../desktop/README.md) — 桌面客户端技术文档
