# v6.2 Desktop Client Review

## 结论

**PASS WITH KNOWN LIMITATIONS**

v6.2 桌面客户端基础设施已经形成闭环：Electron packaged app、frozen sidecar、本地 userData、真实 LLM 首次配置、安全 API Key、运行健康监控、sidecar 重启、启动失败诊断页、诊断包导出和打包验证流水线均已实现并通过 macOS 验收。

## 已验证能力

- packaged `.app` 可以使用 frozen sidecar 启动，不依赖手动启动 API / Vite。
- 用户数据写入桌面 userData 目录，不污染源码目录。
- 首次启动配置只在桌面模式显示，WebUI 浏览器模式不显示桌面专属控件。
- API Key 使用 Electron safeStorage，不写入 YAML。
- `/desktop/config` 不返回明文 key。
- sidecar 健康异常时 UI 可提示、可重启、可打开日志。
- 启动失败时显示自包含诊断页。
- 诊断包可导出且脱敏。
- `verify-desktop-mac.sh` 可完整构建并 smoke packaged app。

## 验收命令

- `cd desktop && npm run typecheck`
- `cd desktop && npm run build`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- `cd frontend && npm run test -- --run`
- `python3 scripts/verify.py smoke`
- `python3 -m pytest tests/test_v66_desktop_secure_keys.py -q`
- `bash packaging/scripts/verify-desktop-mac.sh`

最终验收结果：

- Frontend vitest：169 passed。
- Desktop typecheck/build：通过。
- Backend smoke：通过。
- Secure key tests：9 passed。
- Desktop packaging verification：7 passed, 0 skipped, 0 failed。

## 已知限制

- macOS 未签名/未公证，Gatekeeper 仍可能拦截。
- 未实现自动更新。
- Windows/Linux 未完成真实打包验收。
- 真实 LLM 端到端创作验收依赖可用 API key，不属于 v6.2 桌面基础设施的强制项。
- v6.2 解决的是“客户端能安装/启动/配置/诊断”，不是“创作主流程完全产品化”。

## 后续 Review 重点

v6.2.5 应关注：

- release checklist 是否覆盖发布前所有必跑命令。
- version policy 是否避免 `desktop/package.json`、runtime-info、文档版本漂移。
- release manifest 是否包含 commit、branch、desktop version、artifact 路径和存在性检查。
- install/upgrade/uninstall 文档是否能让非开发用户理解数据位置和风险。

v6.3 应关注：

- 新建小说后是否还会直接跳章节。
- 创世设定、世界观、角色、大纲、章节规划是否形成清晰路径。
- “全 AI 生成”和“用户手动填写”是否都能走通。
