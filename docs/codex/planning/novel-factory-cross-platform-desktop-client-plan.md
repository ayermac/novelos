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
   - `novel_factory/agents/roles/*.yaml`
   - `novel_factory/agents/contracts/*.yaml`
   - `novel_factory/web/design/*.html`

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

目标：避免真实密钥落在普通明文配置中。

实现步骤：

1. 短期方案：继续支持 `.env` / 环境变量，但桌面设置页提示风险。
2. 中期方案：引入 Electron 安全存储，例如系统 keychain 封装。
3. 后端 LLM env_getter 增加桌面密钥读取适配。
4. 配置文件中只保存 profile 名称、base_url、model、参数，不保存 API key 明文。
5. 日志脱敏：

   - API key
   - Authorization header
   - provider token
   - local config secrets

6. 禁止 renderer 直接持有 API key。
7. renderer 通过 IPC 请求 main process 保存或删除密钥。

验收标准：

- 前端 DevTools 中看不到 API key。
- sidecar 日志中看不到 API key。
- app 重启后真实 LLM 配置仍可用。
- 删除密钥后 real 模式给出可解释错误。

### M5：长任务、SSE 与进程恢复

目标：桌面壳不破坏当前生产工作流。

实现步骤：

1. 验证章节生成 SSE：

   - `/api/run/chapter/start`
   - `/api/run/chapter/stream`
   - workflow timeline stream
   - production auto-run stream

2. Electron sleep / wake 后检测 sidecar 健康。
3. sidecar 异常退出时：

   - 标记 UI 为后端离线
   - 尝试有限次数重启
   - 保留最后错误日志入口

4. 正在运行任务时关闭应用：

   - 弹出确认
   - 或先向后端发送 graceful shutdown 标记

5. 断连场景复用现有 `client_disconnected` / resume 机制。
6. 数据库锁定时提供明确恢复建议。

验收标准：

- 长章节生成时窗口不会假死。
- sidecar crash 后 UI 有明确提示。
- 断开 SSE 后可以重新进入项目页面恢复状态。
- 关闭应用不会留下 running 状态与实际数据库矛盾。

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
