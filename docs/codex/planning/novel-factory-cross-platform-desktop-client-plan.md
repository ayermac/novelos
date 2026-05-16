# Novel Factory Cross-Platform Desktop Client Plan

## 目标

将 Novelos 打包为跨平台桌面客户端，覆盖：

- macOS
- Windows
- Linux

首版目标是本地单用户桌面应用：

- 用户安装后可以直接打开 Novelos
- React 工作台作为桌面窗口运行
- Python FastAPI 后端作为本地 sidecar 进程随应用启动
- SQLite 数据、配置、日志保存在系统应用数据目录
- 真实 LLM 仍使用用户配置的 OpenAI-compatible API
- 现有 CLI / API / LangGraph 工作流尽量不重写

## 推荐技术路线

采用：

```text
Electron + React/Vite renderer + PyInstaller Python sidecar
```

整体结构：

```text
Desktop App
├── Electron main process
│   ├── 查找可用本地端口
│   ├── 启动 Python sidecar
│   ├── 监听 sidecar 健康状态
│   ├── 管理窗口生命周期
│   ├── 管理日志、配置、数据目录
│   └── 关闭时清理后端进程
├── Electron renderer
│   └── frontend/dist React SPA
└── Python sidecar
    ├── FastAPI /api
    ├── LangGraph 工作流
    ├── SQLite repository
    ├── SSE streaming
    └── LLM provider
```

## 不采用的路线

### 纯浏览器客户端

不建议。当前核心依赖 Python、LangGraph、LangChain、SQLite 文件访问和后端 SSE 工作流。纯浏览器化会导致核心业务重写，并带来 API key 暴露风险。

### 完整云端 SaaS

不作为本阶段目标。它会引入账户体系、远程数据库、多租户隔离、队列、计费、安全合规和运维成本，偏离当前个人作者本地工作台方向。

### Tauri 优先

可行但不作为首选。Tauri 包体更小，但本项目 Python sidecar 较重，Electron 在跨平台安装器、WebView 一致性、调试和生态成熟度上更适合作为首版交付路线。

## 里程碑拆分

### M0：桌面化技术验证

状态：**已实现**（见 `desktop/` 目录和 `desktop/README.md`）

目标：证明 Electron 可以启动现有 FastAPI 后端，React 前端可以在桌面窗口里访问 `/api`。

实现步骤：

1. 在仓库新增 `desktop/` 目录。
2. 初始化 Electron 主进程工程。
3. 复用 `frontend/dist` 作为 renderer 静态资源。
4. Electron 启动时分配本地端口，例如 `127.0.0.1:<dynamic_port>`。
5. Electron 以子进程方式启动 Python API：

   ```bash
   novelos api --host 127.0.0.1 --port <dynamic_port> --db-path <app_data>/novelos.db --llm-mode stub
   ```

6. Electron 轮询 `/api/health`，成功后打开窗口。
7. 前端 API base 从固定 `/api` 兼容为桌面注入的后端地址。
8. 验证 dashboard、项目列表、章节页面、SSE stream 在桌面窗口中可用。

验收标准：

- macOS 本地开发环境能启动 Electron 窗口。
- Electron 能自动启动并关闭 Python 后端。
- 关闭窗口后没有残留 sidecar 进程。
- 前端主要页面可以访问 API。

### M1：Python sidecar 冻结

状态：**已实现**

目标：用 PyInstaller 把后端冻结为平台原生可执行文件。

实现步骤：

1. 新增 sidecar 专用入口：

   ```text
   novel_factory/desktop_sidecar.py
   ```

2. sidecar 入口只负责启动 API，不进入交互式 CLI。
3. 支持通过参数传入 host、port、db_path、config_path、llm_mode。
4. 新增 PyInstaller spec 文件：

   ```text
   packaging/pyinstaller/novelos-sidecar.spec
   ```

5. 显式收集 package data：

   - `novel_factory/db/schema/*.sql`
   - `novel_factory/db/migrations/*.sql`
   - `novel_factory/config/*.yaml`
   - `novel_factory/config/genre_strategies/*.yaml`
   - `novel_factory/config/skills/manifest/*.yaml`
   - `novel_factory/skill_packages/**/*`
   - `novel_factory/agent_runtime/roles/*.yaml`
   - `novel_factory/agent_runtime/contracts/*.yaml`

6. 处理 LangGraph、LangChain、FastAPI、uvicorn 的 hidden imports。
7. 生成平台侧 sidecar：

   ```text
   desktop/resources/sidecar/<platform-arch>/novelos-sidecar
   ```

8. Electron 开发环境优先使用源码 Python，打包环境使用冻结后的 sidecar。

文件清单：

- `packaging/pyinstaller/novelos-sidecar.spec`
- `packaging/scripts/build-sidecar.sh`
- `packaging/scripts/smoke-sidecar.sh`
- `desktop/resources/sidecar/.gitkeep`

验收标准：

- macOS 上 sidecar 可执行文件可以独立启动 `/api/health`。
- sidecar 可自动初始化 SQLite schema 和 migrations。
- stub 模式可以完整跑通章节生成 smoke。
- real 模式缺少 API key 时返回结构化错误，不崩溃。

### M2：Electron 应用打包

状态：**已实现（macOS 已验证）**

目标：生成可安装或可分发的桌面应用。

实现步骤：

1. 引入 `electron-builder` 作为打包工具。
2. 配置 app 名称、app id、版权信息。
3. 将 `frontend/dist` 作为 `extraResources` 打进 app resources。
4. 将平台对应 sidecar 作为 `extraResources` 打进 app resources。
5. 主进程按平台解析 sidecar 路径（`process.resourcesPath/sidecar/<platform-arch>/novelos-sidecar`）。
6. 打包目标：

   - macOS：`dir`（本地验证） / `dmg`
   - Windows：`nsis`（配置待验证）
   - Linux：`AppImage`（配置待验证）

7. 打包后启动 app，验证后端启动、窗口打开、API 可用。

文件清单：

- `desktop/electron-builder.yml`
- `desktop/build/entitlements.mac.plist`
- `desktop/package.json`（新增 `pack:mac`、`dist:mac`、`pack:mac:full`、`dist:mac:full` 脚本）
- `packaging/scripts/build-desktop-mac.sh` — 一键串联 frontend build、sidecar freeze、Electron packaging

验收标准：

- macOS 可以打开打包后的 `.app`。
- 打包应用使用 frozen sidecar，不依赖本地 Python 环境。
- 应用数据写入 `~/Library/Application Support/novelos-desktop/`，不污染源码目录。
- 关闭应用后 sidecar 进程退出。
- Windows/Linux 打包结构已预留，待后续 CI 验证。
- 本地客户端验收可通过一条命令完成：`bash packaging/scripts/build-desktop-mac.sh --dir`。

### M3：本地数据目录与配置治理

状态：**已实现**

目标：将开发期路径迁移为客户端安全路径。

实现步骤：

1. 使用 Electron `app.getPath("userData")` 作为应用数据根目录。
2. 目录结构：

   ```text
   <userData>/
   ├── data/
   │   ├── novelos.db
   │   ├── novelos.db-wal
   │   └── novelos.db-shm
   ├── config/
   │   └── local.yaml
   ├── logs/
   │   ├── electron.log
   │   ├── sidecar.stdout.log
   │   └── sidecar.stderr.log
   └── backups/
   ```

3. 首次启动时创建目录（`ensureAppDirectories`）。
4. 首次启动时若 `local.yaml` 缺失，自动生成 stub 模式默认配置（`ensureDefaultConfig`），不含 API key。
5. Electron 向 sidecar 传递环境变量：

   - `NOVELOS_DESKTOP=1`
   - `NOVELOS_APP_DATA_DIR`
   - `NOVELOS_DATA_DIR`
   - `NOVELOS_CONFIG_DIR`
   - `NOVELOS_CONFIG_PATH`
   - `NOVELOS_LOGS_DIR`
   - `NOVELOS_BACKUPS_DIR`
   - `NOVELOS_PLATFORM`

6. 后端新增 `/api/desktop/runtime-info` 返回路径、文件存在性、LLM 模式等。
7. 后端新增 `/api/desktop/config` 支持安全字段读取和写入（不含 API key）。
8. Electron IPC 暴露 `openDataDir` / `openConfigDir` / `openLogsDir`，主进程调用 `shell.openPath`。
9. 前端「配置中心」新增「桌面运行时」tab，展示运行时信息并提供目录打开按钮。
10. 前端「桌面运行时」内嵌「桌面配置」卡片，支持修改 LLM mode、model、base_url、temperature。
11. 日志轮转：Electron 日志和 sidecar stdout/stderr 超过 5MB 时自动轮转，保留当前 + `.1` 备份。

文件清单：

- `desktop/src/paths.ts` — `ensureDefaultConfig`
- `desktop/src/logging.ts` — `rotateLogIfNeeded`, `getRotatedLogPath`
- `desktop/src/main.ts` — env vars, IPC handlers
- `desktop/src/preload.ts` — `openDataDir` / `openConfigDir` / `openLogsDir`
- `novel_factory/api/routes/desktop.py` — `runtime-info`, `config` GET/PUT
- `frontend/src/pages/Settings.tsx` — 新增 desktop section
- `frontend/src/components/settings/SettingsConsoleSections.tsx` — `DesktopRuntimeSection`, `DesktopConfigSection`
- `frontend/src/lib/api.ts` — window type 扩展

验收标准：

- 应用数据不写入源码目录。
- 卸载应用不默认删除用户小说数据。
- 数据库路径在 API、workflow checkpoint、logs 中一致。
- 用户可以在设置页看到当前数据目录并一键打开。
- 首次启动自动生成默认配置，不覆盖已有配置。
- 日志超过 5MB 自动轮转。
- API key 不会通过任何 API 返回或在前端显示。
- 默认不开放浏览器 Web 入口；sidecar 只监听 `127.0.0.1` 随机端口，并仅供 Electron 客户端使用。

### M4：API key 与安全

状态：**已实现**

目标：避免真实密钥落在普通明文配置中。

实现步骤：

1. **Electron `safeStorage` 加密存储**：新增 `desktop/src/secrets.ts`，提供 `setApiKey`、`deleteApiKey`、`hasApiKey`、`getApiKeyForSidecar`、`listSecretStatuses`。
2. 密钥文件 `<userData>/config/secrets.json` 只保存加密后的 base64，不保存明文。
3. **明文 key 只短暂存在于 Electron main process 内存中**：
   - UI 保存时写入加密存储。
   - Sidecar 启动时解密并注入子进程环境变量。
4. **Renderer 可以提交 key，但不能读取明文**：通过 IPC `novelos:set-api-key` / `novelos:delete-api-key` / `novelos:secret-status` 交互。
5. **后端 `/api/desktop/config` 增强**：
   - 每个 profile 返回 `api_key_env`、`api_key_configured`、`api_key_source`。
   - `api_key_source` 区分 `desktop_secure_storage` / `environment` / `missing`。
   - 通过 `NOVELOS_DESKTOP_SECRET_KEYS` 环境变量标记哪些 key 来自安全存储。
6. **`PUT /desktop/config` 安全约束**：如果请求体包含 `api_key`、`apiKey`、`secret`、`token`，返回 `SECURITY_REJECTED` 错误，不写入文件。
7. **日志脱敏**：
   - `Sidecar command:` 日志只打印命令和参数（不含 env 值）。
   - `raw_preview` 对 `api_key`、`secret`、`token`、`authorization`、`password` 递归脱敏为 `***REDACTED***`。
   - backend 错误消息不泄露 key 值。
8. 配置文件中只保存 profile 名称、base_url、model、参数，不保存 API key 明文。

文件清单：

- `desktop/src/secrets.ts` — **新增** safeStorage 封装
- `desktop/src/main.ts` — 启动 sidecar 前注入密钥，新增 IPC handlers
- `desktop/src/preload.ts` — 暴露 secrets IPC API
- `frontend/src/lib/api.ts` — Window 类型扩展
- `frontend/src/components/settings/SettingsConsoleSections.tsx` — 新增 `DesktopApiKeyCard`
- `novel_factory/api/routes/desktop.py` — 增强 config GET/PUT（key source、安全字段拒绝）
- `tests/test_v66_desktop_secure_keys.py` — **新增** 后端安全测试

验收标准：

- 前端 DevTools 中看不到 API key。
- sidecar 日志中看不到 API key。
- app 重启后真实 LLM 配置仍可用。
- 删除密钥后 real 模式给出可解释错误。
- `PUT /desktop/config` 拒绝写入任何含 `api_key` / `secret` / `token` 的字段。

### M5：运行稳定性、健康监控与崩溃恢复

状态：**已实现**

目标：把客户端从"能打包运行"推进到"用户遇到问题时能看懂、能恢复、能验收"。

实现步骤：

1. **SidecarManager 状态机**：

   - 状态：`starting` → `healthy` → `exited` / `failed` / `stopping`。
   - 记录最近错误：exit code、signal、command（不含 env）、stderr log path、timestamp、reason。
   - 异常退出时不让 Electron 主进程退出。

2. **主进程 IPC**：

   - `novelos:runtime-status` — 返回当前 sidecar 状态、pid、apiBaseUrl、最近错误、日志路径。
   - `novelos:restart-sidecar` — 停止当前 sidecar，重新选择端口，重建 env（含 safeStorage 注入），等待 health，成功后返回新 `apiBaseUrl`。
   - `novelos:quit-app` — 供诊断窗口调用退出应用。

3. **前端 API base 动态更新**：

   - `preload.ts` 暴露 `getApiBaseUrl()` getter，支持 sidecar 重启后动态获取新地址。
   - `api.ts` 优先调用 `getApiBaseUrl()`。

4. **客户端健康监控 UI**：

   - `DesktopRuntimeBanner` — 顶部非阻塞 banner，8 秒间隔 ping `/api/health`。
   - 连续失败 2 次后显示："本地后端服务连接中断"。
   - 操作：重试连接、重启本地服务（确认 dialog）、打开日志目录。
   - 恢复后 banner 自动消失。
   - Settings → 桌面运行时：显示 sidecar 状态、apiBaseUrl、pid、日志路径、最近错误、重启按钮。

5. **启动诊断页增强**：

   - sidecar 启动超时或前端资源缺失时，显示诊断窗口（不依赖 React 资源）。
   - 内容：错误摘要、启动命令（不含 secret）、日志目录、stderr 路径。
   - 按钮：重试启动、打开日志目录、打开配置目录、退出应用。
   - 前端资源缺失时额外显示 expected dist path。

6. **真实 LLM 配置连通性验证**：

   - Settings → 桌面配置 增加"测试 LLM 连接"按钮。
   - stub 模式提示切换 real 并重启；key missing 提示保存并重启；否则调用 `/settings/validate` 做轻量连通性验证。

7. **一键客户端验收脚本**：

   - `packaging/scripts/smoke-desktop-app-mac.sh`：验证 `.app` 结构、启动、health、数据目录、无残留进程。
   - 使用 `NOVELOS_DESKTOP_USER_DATA_DIR` 避免污染真实用户数据。

8. **支持独立 userData 路径**：

   - 环境变量 `NOVELOS_DESKTOP_USER_DATA_DIR` 覆盖默认 userData。
   - 用于验收脚本和便携/调试场景。

验收标准：

- 前端 typecheck / lint / build / vitest 通过。
- desktop `tsc` 通过。
- sidecar 崩溃后主进程不退出，UI 显示明确提示。
- 用户可通过 Settings 一键重启 sidecar，renderer 自动使用新 apiBaseUrl。
- 诊断窗口包含可操作的日志和目录入口。
- 打包后 smoke 脚本 100% PASS。
- 不引入新 native dependency。
- 不泄露 API key。

### v6.2.1：桌面打包验证流水线

状态：**已实现**

目标：提供一键本地桌面打包验证，确保从源码到可运行 `.app` 的完整链路在本地可重复验证。

实现步骤：

1. **新增编排脚本** `packaging/scripts/verify-desktop-mac.sh`：
   - 6 步顺序执行：frontend build → sidecar freeze → desktop TS build → Electron pack → sidecar smoke → desktop app smoke。
   - 自动检测平台/arch，推导 Electron Builder 输出路径。
   - 任何实际构建/测试错误快速失败（`set -e`）。
   - 最终输出 concise PASS 摘要，包含 app bundle 和 sidecar 路径。

2. **改进 smoke 脚本 pipeline 友好性**：
   - `smoke-sidecar.sh`：缺少 frozen sidecar 时输出 `SKIP` 并退出 0。
   - `smoke-desktop-app-mac.sh`：
     - 缺少 frozen sidecar 时输出 `SKIP` 而非 `FAIL`。
     - 修复 port 检测逻辑，匹配 main.ts 实际日志格式 `--port [0-9]+`。
     - 使用 `NOVELOS_DESKTOP_USER_DATA_DIR` 隔离测试数据。
     - `cleanup` trap 确保残留 Electron 和 sidecar 进程被清理。

验收标准：

- `bash packaging/scripts/verify-desktop-mac.sh` 在干净 macOS 环境一次运行全部 PASS。
- 独立运行 smoke 脚本缺少 sidecar 时输出 SKIP 不报错。
- 不杀死用户正在运行的其他 Novelos 实例（通过 APP_PID + port 范围限制）。
- 脚本不提交构建产物到仓库。

已知限制：

- 仅验证 macOS（arm64 / x64）。
- 未做代码签名/公证。
- Windows/Linux 未验证。

### v6.2.4：桌面发布诊断与恢复闭环

状态：**已实现**

目标：解决"客户端启动失败或后端不可用时，用户只能看到加载失败、不知道该看哪里"的问题。该版本不引入分发开放能力，优先补齐本地排障证据、诊断导出和发布验证报告。

实现步骤：

1. **Electron 主进程诊断导出**：
   - 新增 `novelos:export-diagnostics` IPC。
   - 诊断包输出到 `<userData>/logs/diagnostics/novelos-diagnostics-<timestamp>.json`。
   - 内容包含 app 版本、平台、userData 路径、data/config/log/db 路径、sidecar runtime status、PID、端口、最近错误。
   - sidecar 可达时附带 `/api/health` 和 `/api/desktop/runtime-info` 响应。
   - 附带脱敏后的 `local.yaml` 和 electron/sidecar 日志尾部。
   - API key、token、secret、authorization、password 等字段写入前脱敏。

2. **启动失败页增强**：
   - sidecar 启动失败的自包含诊断窗口增加"导出诊断包"按钮。
   - 即使 React 前端资源缺失，也可以导出诊断包、打开日志/配置目录、重试启动或退出应用。

3. **桌面运行时设置页入口**：
   - Settings → 桌面运行时增加"导出诊断包"按钮。
   - 顶部 runtime failure banner 也提供"导出诊断包"，便于后端断连时立即收集证据。

4. **打包验证报告**：
   - `packaging/scripts/verify-desktop-mac.sh` 生成 `desktop/release/verification-report.json`。
   - 报告包含 schema version、status、message、generated_at、platform、pass/skip/fail 计数、app bundle 路径、sidecar binary 路径。
   - 为后续 CI 和发布 checklist 提供机器可读产物。

验收标准：

- 诊断包可以在 sidecar healthy 和 sidecar failed 两种状态下导出。
- 诊断包不包含明文 API key。
- 启动失败窗口不依赖 React bundle。
- Settings 和 runtime banner 都能触发诊断导出。
- `verify-desktop-mac.sh` 成功或失败时都产出 `verification-report.json`。

### v6.2.5：桌面发布准备清单

状态：**已实现**

目标：把当前 macOS 桌面客户端从"能打包验收"推进到"可被稳定发布和复验"。本版本不做代码签名、公证、自动更新，也不扩展 Windows/Linux；重点是发布前清单、版本规则、release manifest、安装/升级/卸载说明和机器可读验收产物。

实现范围：

1. **Release Checklist 文档**：
   - 新增 `docs/codex/release/desktop-release-checklist.md`。
   - 覆盖发布前环境要求、Git 状态检查、必跑验证命令、macOS 打包命令、首次启动验收、诊断包验收、API key 脱敏检查、真实 LLM 可选验收、残留进程检查、发布产物路径。
   - 明确 blocker / warning 分类。
   - 补回滚与清理说明。

2. **Versioning Policy**：
   - 新增 `docs/codex/release/desktop-versioning-policy.md`。
   - 说明 `desktop/package.json` version、`/api/desktop/runtime-info.version`、文档版本标识的同步规则。
   - 约定 release tag 命名建议。
   - 约定 commit hash 必须进入 verification report / release manifest。
   - 明确 `package-lock.json` 版本同步要求。

3. **Release Manifest**：
   - 新增 `packaging/scripts/write-desktop-release-manifest.sh`。
   - 生成 `desktop/release/release-manifest.json`。
   - manifest 包含 schema version、generated_at、commit、branch、desktop_version、platform、app bundle、dmg（可为空）、sidecar binary、verification report、关键存在性检查。
   - 不提交 release 构建产物，只提交脚本和文档。

4. **Verification Report 增强**：
   - `packaging/scripts/verify-desktop-mac.sh` 的 `verification-report.json` 增加 commit、branch、desktop_version、app_bundle_exists、sidecar_binary_exists。
   - 成功路径仍为 `status: passed`。
   - 失败路径仍能写 report。
   - 不破坏现有 PASS/FAIL 输出格式。

5. **文档索引更新**：
   - 更新 `desktop/README.md`，新增 Release Readiness 章节。
   - 更新 `docs/codex/README.md`。
   - 当前文档标记 v6.2.5 范围与非目标。

验收标准：

- `bash -n packaging/scripts/verify-desktop-mac.sh` 通过。
- `bash -n packaging/scripts/write-desktop-release-manifest.sh` 通过。
- desktop typecheck/build 通过。
- frontend typecheck/lint 通过。
- `python3 scripts/verify.py smoke` 通过。
- 若本地 PyInstaller 可用，`bash packaging/scripts/verify-desktop-mac.sh` 和 release manifest 生成脚本均通过。
- 产物 manifest 和 verification report 可被 release checklist 引用。

非目标：

- 不做 macOS signing/notarization。
- 不做自动更新。
- 不做 Windows/Linux 打包实现。
- 不改变桌面运行时架构。
- 不改创作主流程。

## 客户端完成态后续路线

v6.2.5 之后，桌面客户端不应继续只补打包工程；需要回到"用户安装后能不能真正完成一本小说"的产品闭环。建议后续版本如下：

### v6.3：Creator Onboarding Closure

状态：**已实现，v6.3.2 已回归干净**

目标：修复从 0 到 1 创建小说的真实用户体验。创建项目后不再直接跳章节 workflow，而是进入创作准备流程，支持一键 AI 补齐和明确的上下文就绪检查。

实现范围：

1. **创建后落点调整**：
   - 项目创建成功后默认进入 `module=overview`（准备工作台），不再自动带 `chapter=1&view=workflow&auto_generate=1`。
   - Onboarding 成功页文字已更新，明确建议先完成创世设定再生成章节。

2. **章节运行 Guard 增强（后端）**：
   - `_run_guards.py` 新增 Guard 4 `CONTEXT_INCOMPLETE`。
   - 缺少 approved genesis / world_settings / characters / outlines / instructions 时，阻止章节 workflow 启动。
   - 返回明确的用户可读错误，附带缺失项和修复提示。

3. **production-next health 增强**：
   - `_build_health` 新增 `ready_for_chapter_1` 布尔字段。
   - 当且仅当 approved genesis + world + characters + outlines + instructions 全部存在时为 `true`。

4. **GenesisModule 体验优化**：
   - `premise`（创意/前提）改为可选字段，允许留空让 AI 自动推断。
   - 标签和 helper 文案已更新，明确说明"可留空"。
   - 已继承的项目基础信息（标题、类型、全书规模）继续显示为只读上下文。
   - "首批规划章数" 和 "首批规划字数" 的 helper 文案已存在，保持不变。

5. **ProjectOverview 主动作调整**：
   - `generate_chapter` 的 primary action 不再导航到 `auto_generate=1`。
   - 改为只导航到章节内容页，让用户手动点击"生成"。
   - `auto_generate` URL 参数的自动触发 effect 已移除。

6. **默认章节标题改进**：
   - `onboarding.py` 创建章节时默认标题从 `第 N 章` 改为 `第 N 章（待命名）`。
   - 避免用户看到无意义的默认标题。

小修摘要：

- **v6.3.1**：统一 `ready_for_chapter_1` 与 run guard 的检查逻辑，均要求 `approved_genesis`；production-next 不再写入 `auto_generate=1`；修复空 premise 测试覆盖不完整的问题。
- **v6.3.2**：修复 review findings——旧静态测试仍断言 `auto_generate=1`、空 premise 测试未真正传空字符串、CONTEXT_INCOMPLETE guard 文案误导；修复 Screenwriter stub 缺少 `turn`/`plot_refs` 和 instruction `key_events` 与 stub author `implemented_events` 不匹配导致的 workflow 回归失败。

验收标准：

- 新项目 production-next 返回 `generate_genesis`，不是 `generate_chapter`。
- 缺少 context 时调用 `/run/chapter` 返回 `CONTEXT_INCOMPLETE` 错误。
- context ready 后 production-next 返回 `generate_chapter`，且 `ready_for_chapter_1=true`。
- 前端 `auto_generate` 不再自动触发 workflow。
- Genesis premise 可留空生成。
- 创建项目后默认标题包含"待命名"。
- backend full suite 1980 passed, 0 failed。

非目标：

- 不做营销 landing page。
- 不做大卡片堆叠式 UI。
- 不改动创作主流程 Agent 节点。
- 不改后端数据库 schema。

### v6.4：Chapter Generation Quality Closure

状态：**已实现，v6.4.6 已封版**（见 [planning/novel-factory-v6.4-chapter-quality-closure-spec.md](planning/novel-factory-v6.4-chapter-quality-closure-spec.md)）

目标：解决生成章节"AI 味重"的核心问题，优先提升正文可读性、人物对白自然度、场景颗粒度、叙事节奏和风格一致性。

重点：

- Author prompt 增强：Show-Don't-Tell 铁律、感官细节要求、对白人物化、设定戏剧化、章末禁止说教
- Polisher 专项：对白自然化、场景质感增强、节奏调整、去直白情绪
- 新增 4 个 deterministic validator skill：`ShowDontTellValidator`、`DialogueNaturalizer`、`SceneConflictChecker`、`InfoDumpDetector`
- 增强现有 skill：`HumanizerZh` 新增规则、`AIStyleDetector` 新增维度、`death_penalty` 新增规则
- Editor 五维评分中"文字质量"拆分为 AI 痕迹/叙事质感/节奏控制子维度
- QualityHub 新增统一 `diagnose` 方法和质量诊断 API
- Frontend 章节详情页新增"质量诊断"折叠面板
- 版本拆分：v6.4.0 诊断基线 → v6.4.1 Author prompt → v6.4.2 Polisher 改写 → v6.4.3 新增 skills → v6.4.4 Editor gate + 测试闭环 → v6.4.5 Real LLM 可选验收 → v6.4.6 封版

### v6.5：Interaction Excellence Closure

状态：**已实现，v6.5.6 已封版**（见 [planning/novel-factory-v6.5-interaction-excellence-spec.md](planning/novel-factory-v6.5-interaction-excellence-spec.md)）

目标：解决桌面客户端当前"像后台系统"的问题，先把操作反馈、等待状态、错误恢复和微交互底座做稳，再交给后续 Agent 逐页升级。

重点：

- v6.5.0：交互审计和规格收口，明确"工作台但要有极致体验"的标准。
- v6.5.1：新增 `ToastProvider`、`LoadingButton`、`Skeleton` / `SkeletonStack`，接入 Onboarding 和 Quality Diagnosis 两个样板场景。
- v6.5.2：Project Overview 从信息堆叠改为下一步创作驾驶舱。
- v6.5.3：Chapter Writing Surface 生成/发布/返修/恢复体验升级。
- v6.5.4：Agent Process Narrative，把执行日志变成用户能理解的创作过程。
- v6.5.5：Settings / Desktop Runtime polish，优化 LLM 配置、sidecar 状态、诊断包和连接测试。
- v6.5.6：Interaction Excellence Closure，完成最终 review、文档基线和回归验证。

已实现文件：

- `frontend/src/components/ui/Toast.tsx`
- `frontend/src/components/ui/LoadingButton.tsx`
- `frontend/src/components/ui/Skeleton.tsx`
- `frontend/src/components/ui/__tests__/interaction-primitives.test.tsx`
- `frontend/src/App.tsx`
- `frontend/src/pages/Onboarding.tsx`
- `frontend/src/components/project/QualityDiagnosisPanel.tsx`
- `docs/codex/planning/novel-factory-v6.5-interaction-excellence-spec.md`
- `docs/codex/reports/novel-factory-v6.5.6-interaction-excellence-closure-report.md`
- `docs/codex/reviews/novel-factory-v6.5.6-interaction-excellence-closure-review.md`

### v6.6：Agent Evidence UX Closure

状态：**候选规划**

目标：让用户能看懂并信任每个 Agent 的工作过程。当前 v6.1 已有执行事件基础，v6.6 要把它产品化成可审计的创作证据链。

重点：

- 每个 Agent 展示输入摘要、输出摘要、工具调用、Skill 检查、memory 读写、LLM 请求状态。
- Author/Polisher 显示生成或改写差异。
- Editor 显示审核维度、返修依据、通过/失败证据。
- 明确标出 fallback、跳过、低变化返修、超时、无 LLM 请求等异常状态。
- 支持长连接实时刷新，不让用户只看到"运行中/完成"。

### v6.7：Structured Memory Canonicalization

状态：**候选规划**

目标：先把结构化记忆、事实、伏笔、角色状态做准。角色事实、世界观设定、伏笔位置、时间线事件不依赖向量检索作为真相来源。

重点：

- 明确 canonical source：story facts、agent memory、memory updates、foreshadowing、characters、world settings。
- 给事实增加 entity、source chapter/version、source span、confidence、status。
- Memory 写入需要可确认、可编辑、可禁用、可删除。
- Agent 使用事实时必须在 trace 中显示引用来源。
- Editor 能指出违反了哪个事实或伏笔状态。

### v6.8：Author Editing & Revision Closure

状态：**候选规划**

目标：把人工编辑、AI 改写、返修、版本 diff、回滚做成顺滑作者工作流。

重点：

- 章节正文可持续人工编辑。
- AI 生成、润色、返修、局部改写都产生版本。
- 支持 diff、回滚、局部替换。
- 返修意见能明确进入 Author/Polisher 的下一轮上下文。
- 人工写作和 AI 协作之间切换自然。

### v6.9：Desktop Distribution Closure

状态：**候选规划**

目标：让客户端达到可对外分发的发布级状态。

重点：

- macOS signing / notarization。
- DMG 发布验证。
- 安装、升级、卸载、数据迁移路径明确。
- 发布产物校验和 release checklist 强制执行。
- Windows/Linux 打包进入后续分支或并行规划。

### v6.10：Reference Library + Genre/Style RAG

状态：**候选规划**

目标：建立"参考作品研究系统"，用于题材研究、结构分析和风格样本检索。该功能不用于复制或复写他人作品。

重点：

- 用户导入自己有权使用的 TXT/EPUB/Markdown/样本资料。
- 记录 source、license/right note、allowed use。
- Reference Analyst Agent 输出抽象分析：题材套路、章节节奏、冲突模式、角色原型、章节钩子、语言风格。
- 向量检索仅用于风格/氛围/节奏相似样本召回，不作为角色事实、伏笔、设定的真相来源。
- 增加原创性保护：相似片段告警、n-gram 重合检测、引用来源可见。

### M6：跨平台 CI 与发布流水线

目标：让 macOS、Windows、Linux 可重复构建。

实现步骤：

1. 建立 GitHub Actions 或本地等价 CI 矩阵：

   - macOS runner
   - Windows runner
   - Linux runner

2. 每个平台执行：

   ```bash
   python3 -m pytest -q <desktop smoke subset>
   cd frontend && npm run typecheck && npm run build
   pyinstaller packaging/pyinstaller/novelos-sidecar.spec
   cd desktop && npm run dist
   ```

3. 上传构建产物。
4. 产物命名包含：

   - app version
   - platform
   - architecture
   - git commit

5. 后续补充：

   - macOS signing / notarization
   - Windows code signing
   - auto update
   - release notes

验收标准：

- 三个平台都能从干净环境构建安装包。
- 构建产物可追溯到 commit。
- 失败日志能定位到 frontend、sidecar 或 electron packaging。

## 建议目录结构

```text
desktop/
├── package.json
├── electron-builder.yml
├── src/
│   ├── main.ts
│   ├── preload.ts
│   ├── sidecar.ts
│   ├── paths.ts
│   └── logging.ts
├── resources/
│   └── sidecar/
│       ├── darwin-arm64/
│       ├── darwin-x64/
│       ├── win32-x64/
│       └── linux-x64/
└── README.md

packaging/
├── pyinstaller/
│   ├── novelos-sidecar.spec
│   └── hooks/
└── scripts/
    ├── build-sidecar.sh
    ├── build-sidecar.ps1
    └── collect-desktop-artifacts.py

novel_factory/
└── desktop_sidecar.py
```

## 需要改造的现有代码点

### 前端 API base

当前默认 `/api` 适合 Vite proxy 和同源部署。桌面端需要支持：

```text
window.__NOVELOS_DESKTOP__.apiBaseUrl
```

优先级：

1. desktop injected apiBaseUrl
2. `VITE_API_BASE_URL`
3. 默认 `/api`

### FastAPI 静态资源

可选两种方案：

1. Electron 直接加载 `frontend/dist/index.html`
2. FastAPI 同时服务 `frontend/dist`

首版建议用 Electron 加载前端资源，FastAPI 只负责 `/api`，边界更清晰。

### 配置加载

当前配置会读项目根目录 `.env` 和 YAML。桌面端需要增加：

- app data config path
- app data env path
- secure store adapter

不要移除现有行为，以免破坏 CLI 和开发模式。

### 数据库路径

所有桌面端运行必须显式传入 `--db-path`，不能使用 package 内默认路径。

### 日志

sidecar 不应只输出到 stdout。需要将日志写入 app data logs，同时保留 Electron 捕获 stdout/stderr 用于诊断。

## 风险与处理

| 风险 | 影响 | 处理 |
| --- | --- | --- |
| PyInstaller hidden imports 不完整 | sidecar 启动失败 | 先用 smoke tests 固定导入清单，再补 hook |
| LangGraph checkpoint DB 路径不一致 | 恢复失败或状态错乱 | sidecar 必须显式传入主 DB path，并沿用当前 derive checkpoint 逻辑 |
| SSE 在 Electron 下断连 | 长任务 UI 卡住 | 保留现有 resume 机制，增加桌面端健康检查 |
| Windows 路径和空格 | sidecar 找不到资源 | 所有路径通过 argv 数组传递，不拼 shell 字符串 |
| macOS signing 后 sidecar 权限问题 | 发布包打不开 | sidecar 放 app resources，签名时一并签 |
| API key 明文落盘 | 安全问题 | 第一版可提示，产品版必须接 keychain |
| SQLite 被多进程占用 | 数据损坏或锁错误 | Electron 只启动一个 sidecar，应用单实例锁 |

## 推荐排期

### MVP：5-8 周

```text
第 1 周：M0 技术验证
第 2 周：M1 PyInstaller sidecar
第 3 周：M2 Electron 打包基础
第 4 周：M3 数据目录与配置
第 5 周：M5 长任务/SSE/恢复验证
第 6 周：Windows + Linux 补齐
第 7-8 周：修复跨平台问题、整理发布包
```

### 产品级：10-14 周

在 MVP 基础上增加：

- 系统 keychain
- 自动更新
- macOS signing / notarization
- Windows code signing
- Linux deb/rpm
- 崩溃诊断包
- 数据备份/恢复
- 完整跨平台 CI

## 第一阶段具体任务清单

1. 新建 `desktop/` Electron 工程。
2. 新建 `novel_factory/desktop_sidecar.py`。
3. 新建 `packaging/pyinstaller/novelos-sidecar.spec`。
4. 修改前端 API client 支持 desktop-injected `apiBaseUrl`。
5. Electron main process 实现：

   - app single instance lock
   - userData path 初始化
   - dynamic port selection
   - sidecar spawn
   - health check wait loop
   - graceful shutdown
   - stderr/stdout log capture

6. PyInstaller build script 收集 package data。
7. Electron build 配置把 sidecar 放进 resources。
8. 新增 desktop smoke tests：

   - sidecar health
   - database init
   - stub run chapter
   - renderer loads dashboard
   - SSE stream connects

9. 在 macOS 跑通开发启动。
10. 在 macOS 跑通 packaged app。
11. 补 Windows 构建。
12. 补 Linux AppImage 构建。

## 首版验收标准

首版跨平台客户端可以认为完成，当满足：

- macOS、Windows、Linux 均有可启动安装包或可执行分发包。
- 打开应用后无需手动启动 API 或前端开发服务器。
- 首次启动能自动创建本地 SQLite 数据库。
- Stub 模式能完成新建项目、生成章节、查看 workflow timeline。
- Real 模式能读取用户配置并进行真实 LLM 调用。
- SSE 长任务在桌面窗口里正常显示进度。
- 关闭应用后没有残留 sidecar 进程。
- 用户数据不写入源码目录或安装目录。
- 缺少 API key、端口冲突、sidecar 崩溃都有可理解错误提示。

## 后续产品增强

MVP 之后再规划：

- 数据库备份 / 恢复 / 导出
- 多项目文件夹管理
- DOCX / EPUB 桌面导出体验
- 一键诊断包
- 自动更新
- 主题、菜单栏、快捷键
- 最近项目
- 离线写作模式
- 本地模型 provider
