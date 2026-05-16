# v6.2 Desktop Client Completion Report

## 版本：v6.2 Desktop Client Foundation

### 状态：阶段完成

v6.2 将 Novelos 从 WebUI + 本地 API 的开发形态推进到 macOS 桌面客户端基础形态。该阶段重点不是重写创作主流程，而是建立 Electron 壳、冻结后端 sidecar、本地数据目录、真实 LLM 首次配置、安全密钥存储、打包验证、运行诊断和恢复闭环。

## 子版本范围

### M0：Electron 技术验证

- 新增 `desktop/` Electron 工程。
- Electron 主进程自动启动 Python sidecar。
- 前端通过 `window.__NOVELOS_DESKTOP__` 获取动态 API base URL。
- 支持单实例锁、动态端口、健康检查、窗口加载和优雅关闭。

### M1：Python Sidecar Freeze

- 新增 PyInstaller spec 和 sidecar 构建脚本。
- 打包 `novel_factory` 后端、DB schema/migrations、配置、skills、roles 等资源。
- Electron 在 packaged 模式下优先使用 frozen sidecar，dev 模式回退 `python3 -m novel_factory.desktop_sidecar`。
- 新增 sidecar smoke 测试脚本。

### M2：Electron App Packaging

- 新增 `electron-builder` 配置。
- 将 `frontend/dist` 与 frozen sidecar 打入 `.app` resources。
- 支持 macOS dir/dmg 打包。
- 验证 packaged app 使用用户目录数据库，不污染源码目录。

### M3：Desktop Runtime Settings

- 首次启动自动生成安全 stub 默认配置。
- 新增 `/api/desktop/runtime-info`、`/api/desktop/config`。
- Settings 增加桌面运行时页面，显示路径、LLM 模式、配置/DB 状态。
- 支持打开数据、配置、日志目录。
- 增加日志轮转。

### M4：Secure API Key Storage

- 新增 Electron `safeStorage` 封装。
- API Key 保存到本机安全存储，不写入 YAML。
- sidecar 启动时解密并注入对应环境变量。
- `/desktop/config` 返回 key source/status，但不返回明文。
- Settings 支持保存/删除 API Key。

### M5：Runtime Stability and Recovery

- `SidecarManager` 增加状态机和最近错误记录。
- 支持 Settings 中重启本地服务。
- 前端 API base URL 支持 sidecar 重启后动态更新。
- 新增桌面运行时故障 banner。
- 启动失败时显示自包含诊断窗口，而不是空白窗口或 native alert。
- 打包 app smoke 脚本验证启动、health、数据目录和进程清理。

### v6.2.1：Desktop Packaging Verification Pipeline

- 新增 `packaging/scripts/verify-desktop-mac.sh`。
- 一键执行 frontend build、sidecar freeze、desktop TS build、Electron pack、sidecar smoke、desktop app smoke。
- smoke 脚本支持 SKIP 语义，避免缺少 sidecar 时误报代码失败。
- 验证 macOS packaged app 可重复构建和 smoke。

### v6.2.2：Desktop First-Run Real LLM Setup

- 新增桌面首次运行真实 LLM 配置引导。
- 支持 OpenAI、DeepSeek、OpenRouter、火山 Ark、自定义 preset。
- `/desktop/config` 支持安全更新 provider/base_url/model/api_key_env 等非密钥字段。
- 新增 `/desktop/test-llm`，返回 `STUB_MODE`、`API_KEY_MISSING`、`AUTH_FAILED`、`MODEL_NOT_FOUND`、`TIMEOUT`、`NETWORK_ERROR` 等可读错误分类。
- 全局 Layout 仅在桌面模式挂载首次配置引导。

### v6.2.3：Packaged Desktop First-Run Acceptance

- 使用临时 userData 验收 packaged app 首次启动。
- 验证 app window、sidecar health、data/config/logs 创建、首次设置 UI、provider presets、demo skip、配置安全、错误分类、Settings compact flow、WebUI 分离和进程清理。
- 可选真实 LLM 验收因环境无 key 跳过。

### v6.2.4：Desktop Release Diagnostics and Recovery

- Electron 主进程新增诊断包导出。
- Settings、runtime failure banner、启动失败页均可触发“导出诊断包”。
- 诊断包包含 runtime status、API health/runtime-info、路径、脱敏配置和日志尾部。
- `verify-desktop-mac.sh` 生成 `desktop/release/verification-report.json`。
- 首次配置弹窗 UI 做了桌面布局修正：稳定高度、内部滚动、固定 footer、双列响应式表单。

## 关键文件

- `desktop/src/main.ts` — Electron 主进程、sidecar 生命周期、安全 key 注入、诊断窗口、诊断包导出。
- `desktop/src/preload.ts` — 安全暴露 desktop runtime APIs。
- `desktop/src/sidecar.ts` — sidecar 进程管理。
- `desktop/src/runtimeStatus.ts` — runtime 状态与订阅。
- `desktop/src/secrets.ts` — safeStorage 密钥封装。
- `desktop/src/paths.ts` — userData 目录、默认配置。
- `novel_factory/desktop_sidecar.py` — FastAPI sidecar 入口。
- `novel_factory/api/routes/desktop.py` — desktop runtime/config/test-llm API。
- `frontend/src/components/desktop/DesktopFirstRunSetup.tsx` — 首次配置真实 LLM。
- `frontend/src/components/DesktopRuntimeBanner.tsx` — runtime 故障 banner。
- `frontend/src/components/settings/SettingsConsoleSections.tsx` — 桌面运行时设置页。
- `packaging/scripts/build-sidecar.sh` — frozen sidecar 构建。
- `packaging/scripts/build-desktop-mac.sh` — macOS 一键构建。
- `packaging/scripts/smoke-sidecar.sh` — sidecar smoke。
- `packaging/scripts/smoke-desktop-app-mac.sh` — packaged app smoke。
- `packaging/scripts/verify-desktop-mac.sh` — 桌面打包验证流水线。
- `docs/codex/planning/novel-factory-cross-platform-desktop-client-plan.md` — 桌面客户端规划与后续路线。

## 验收结果

v6.2.4 收口验收结果：

- `cd desktop && npm run typecheck`：通过。
- `cd desktop && npm run build`：通过。
- `cd frontend && npm run typecheck`：通过。
- `cd frontend && npm run lint`：通过。
- `cd frontend && npm run build`：通过。
- `cd frontend && npm run test -- --run`：169 passed。
- `python3 scripts/verify.py smoke`：通过。
- `python3 -m pytest tests/test_v66_desktop_secure_keys.py -q`：9 passed。
- `bash packaging/scripts/verify-desktop-mac.sh`：7 passed, 0 skipped, 0 failed。

诊断包验收：

- 诊断包生成于 `<userData>/logs/diagnostics/novelos-diagnostics-<timestamp>.json`。
- 包含 `runtime_status`、`api.health`、`api.runtime_info`、`paths`、`config_redacted` 和日志尾部。
- 未发现明文 API key、`sk-` 原文、secret/token/password 明文。

## 当前限制

- macOS `.app` 尚未签名/公证。
- Windows/Linux 打包结构已预留，但未完成验收。
- 无自动更新。
- 首次配置真实 LLM 的完整线上调用验收依赖用户提供真实 API key。
- 桌面基础设施已接近可信态，但创作主流程从 0 到 1 仍需 v6.3 专门收口。

## 下一步

### v6.2.5 Desktop Release Readiness Checklist

补齐 release checklist、version policy、release manifest、安装/升级/卸载说明，并增强 `verification-report.json` 的 commit/version 字段。

### v6.3 Creator Onboarding Closure

回到产品主流程：创建小说后进入创世设定、世界观、角色、大纲、章节规划和第一章生成，而不是直接跳章节。
