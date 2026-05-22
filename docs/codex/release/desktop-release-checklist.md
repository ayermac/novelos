# Novelos 桌面客户端发布清单

本文档是 macOS 桌面客户端从源码到可运行 `.app` 的发布前必做检查清单。适用于本地打包验证和手动发布准备。

---

## 发布目标与非目标

### 目标

- 确认从干净源码可重复构建出可运行的 macOS `.app` 包。
- 确认首次启动流程、诊断导出、API key 脱敏等行为正确。
- 产出机器可读的 `verification-report.json` 和 `release-manifest.json`。
- 提供回滚、清理、重新打包的标准操作步骤。

### 非目标（v6.2.5 不做）

- macOS 代码签名（codesign）与公证（notarization）。
- 自动更新（auto-update）机制。
- Windows / Linux 打包验证。
- 向 Mac App Store 或公开下载页分发。

---

## 环境要求

| 组件 | 版本/要求 | 检查命令 |
|---|---|---|
| Node.js | 18+ | `node --version` |
| npm | 8+ | `npm --version` |
| Python | 3.9+ | `python3 --version` |
| PyInstaller | 已安装 | `pyinstaller --version` |
| macOS | 支持 arm64 / x64 | `uname -sm` |
| curl | 已安装 | `which curl` |
| lsof | 已安装 | `which lsof` |
| Git | 已安装 | `git --version` |

---

## 发布前 Git 状态检查

运行以下命令，确认工作区干净、分支正确：

```bash
cd /path/to/novelos
git status
git log --oneline -3
```

**Acceptance：**
- 无未提交的意外修改（只允许本版本预期的改动）。
- 分支名称符合当前版本（如 `codex-v6.2-desktop-m0-poc`）。
- 最近一次 commit message 与本次发布内容一致。

---

## 必跑验证命令

在 repo 根目录按顺序执行：

```bash
# 1. Desktop TypeScript
cd desktop && npm run typecheck

# 2. Desktop build
cd desktop && npm run build

# 3. Frontend typecheck
cd frontend && npm run typecheck

# 4. Frontend lint
cd frontend && npm run lint

# 5. Frontend build
cd frontend && npm run build

# 6. Frontend vitest
cd frontend && npm run test -- --run

# 7. Python smoke
cd /path/to/novelos && python3 scripts/verify.py smoke

# 8. Desktop secure keys test
cd /path/to/novelos && python3 -m pytest tests/test_v66_desktop_secure_keys.py -q
```

**Acceptance：**
- 以上全部通过，无任何失败。

---

## macOS 打包命令

### 一键完整验证（推荐）

```bash
cd /path/to/novelos
bash packaging/scripts/verify-desktop-mac.sh
```

该脚本顺序执行：
1. Build frontend
2. Build frozen sidecar
3. Build desktop TypeScript
4. Package Electron app（dir 模式）
5. Smoke-test frozen sidecar
6. Smoke-test packaged desktop app

成功后在终端输出 `ALL PASSED`，并生成：
- `desktop/release/verification-report.json`

### 仅生成 release manifest

在完整验证通过后：

```bash
bash packaging/scripts/write-desktop-release-manifest.sh
```

生成：
- `desktop/release/release-manifest.json`

---

## 首次启动验收步骤

1. **准备临时 userData 目录**：
   ```bash
   rm -rf /tmp/novelos-first-run-test
   mkdir -p /tmp/novelos-first-run-test/logs
   ```

2. **启动打包应用**：
   ```bash
   NOVELOS_DESKTOP_USER_DATA_DIR=/tmp/novelos-first-run-test \
     ./desktop/release/mac-arm64/Novelos.app/Contents/MacOS/Novelos
   ```

3. **验收项**：
   - [ ] 应用窗口正常打开，无白屏。
   - [ ] `/api/health` 返回 `status: ok`。
   - [ ] `data/novelos.db`、`config/local.yaml`、`logs/` 已创建在临时目录下。
   - [ ] 首次启动自动出现 LLM 设置向导（stub 模式下显示 demo / real 选择）。
   - [ ] Provider presets（OpenAI / DeepSeek / OpenRouter / 火山 Ark / Custom）可正常切换。

---

## 诊断包验收步骤

1. 在 Settings → 桌面运行时中点击 **导出诊断包**。
2. 或模拟 sidecar 失败后点击顶部 banner 的 **导出诊断包**。

**验收项**：
- [ ] 文件生成在 `<userData>/logs/diagnostics/novelos-diagnostics-<timestamp>.json`。
- [ ] JSON 包含 `runtime_status`、`api.health`、`paths`、`config_redacted`、`logs`。
- [ ] `config_redacted` 中不存在明文 API key。
- [ ] 不存在 `sk-` 开头的原文。
- [ ] 不存在 `secret`、`token`、`password` 的明文值。

---

## API Key 脱敏检查

1. 在前端 Settings → 桌面配置 → API Key 安全存储中输入一个假 key。
2. 点击保存。

**验收项**：
- [ ] 输入框在保存后清空或显示掩码状态。
- [ ] `<userData>/config/local.yaml` 中**不**包含 `api_key:` 明文字段。
- [ ] `<userData>/config/secrets.json` 存在（如果保存成功）。
- [ ] `secrets.json` 中的值不是可读的明文（被 Electron safeStorage 加密）。

---

## 真实 LLM 可选验收

如果环境中有真实 API key：

1. 配置真实 provider（base URL、model、api_key_env）。
2. 保存 key 到安全存储。
3. 切换为 real 模式。
4. 重启 sidecar（或重启应用）。
5. 运行 **测试 LLM 连接**。

**验收项**：
- [ ] 连接测试返回成功或明确的用户可读错误（非 500 崩溃）。
- [ ] `/api/health` 中 `llm_mode` 为 `real`。
- [ ] `local.yaml` 和日志中不泄露 raw key。

如果无真实 key，标记此项为 **SKIPPED**。

---

## 残留进程检查

关闭应用后执行：

```bash
ps aux | grep -i novelos | grep -v grep
lsof -ti tcp:<sidecar_port>
```

**验收项**：
- [ ] 无 `Novelos.app` 残留进程。
- [ ] 无 `novelos-sidecar` 残留进程。
- [ ] 未误杀用户其他正在运行的 Novelos 实例。

---

## 发布产物路径

验证完成后，产物位于：

| 产物 | 路径 |
|---|---|
| App bundle | `desktop/release/mac-arm64/Novelos.app` |
| DMG（如生成） | `desktop/release/Novelos-*.dmg` |
| Sidecar binary | `desktop/resources/sidecar/darwin-arm64/novelos-sidecar` |
| Verification report | `desktop/release/verification-report.json` |
| Release manifest | `desktop/release/release-manifest.json` |

---

## Blocker / Warning 分类

| 级别 | 定义 | 示例 |
|---|---|---|
| **BLOCKER** | 导致应用无法启动或核心功能不可用 | 打包后白屏、sidecar 无法启动、首次启动设置不显示、API key 明文写入 YAML |
| **WARNING** | 不影响核心功能，但影响发布质量 | 未做代码签名（已知限制）、Windows/Linux 未验证（已知限制）、vitest 中有 deprecation warning |
| **INFO** | 观察记录，不影响发布决策 | 某 lint rule 被禁用、某个测试在特定 Node 版本有差异 |

**规则：**
- 存在任何 BLOCKER 时，不得标记发布通过。
- WARNING 需记录并在发布说明中说明。
- INFO 仅用于排障参考。

---

## 回滚、清理、重新打包

### 回滚到上一稳定 commit

```bash
git log --oneline -5
git checkout <stable-commit-hash>
```

### 清理构建产物（不删源码）

```bash
rm -rf desktop/release/
rm -rf desktop/dist/
rm -rf desktop/resources/sidecar/darwin-*/
rm -rf frontend/dist/
rm -rf build/
```

### 重新打包

清理后重新执行：

```bash
bash packaging/scripts/verify-desktop-mac.sh
```

---

## 不提交 release 构建产物的规则

以下路径已在 `.gitignore` 中，**不要**手动提交：

- `desktop/release/`
- `desktop/dist/`
- `desktop/resources/sidecar/darwin-*/`
- `frontend/dist/`
- `build/`
- `*.dmg`

**只允许提交**：
- 源码（`desktop/src/`、`frontend/src/` 等）
- 构建脚本（`packaging/scripts/`）
- 文档（`docs/codex/release/`）
- 测试文件

---

## 相关文档

- [desktop-versioning-policy.md](desktop-versioning-policy.md) — 桌面客户端版本规则
- [desktop/README.md](../../../desktop/README.md) — 桌面客户端技术文档
- [../../planning/novel-factory-cross-platform-desktop-client-plan.md](../../planning/novel-factory-cross-platform-desktop-client-plan.md) — 桌面客户端总规划
