# Novelos v6.0 Real LLM Acceptance Report

## 验收范围

- 日期：2026-05-15
- 模式：真实 LLM，`llm_mode=real`
- API：`http://127.0.0.1:8765`
- 数据库：`acceptance_novel_factory.db`
- 验收项目：`real_acceptance_v60_neon_rain`
- 项目名：`霓虹雨档案`
- 类型：近未来都市悬疑

本次验收不用旧 demo 项目，不用 stub mode。目标是模拟创作者真实使用：新建小说、生成章节、查看工作流、处理阻塞、人工编辑、局部 AI 返修、保存版本。

## 真实流程结果

### 第 1 章

- Screenwriter 真实生成完成。
- Author 真实生成完成，写入正文和版本。
- Polisher 在原 45 秒超时配置下失败，workflow run 进入 `blocked`。
- 验收暴露问题：章节已有正文，但章节状态仍显示 `planned`，导致 workspace / production-next 无法把它作为需要恢复的阻塞章节处理。

### 第 2 章

- Screenwriter / Author / Polisher / Editor 均完成真实 LLM 调用。
- Polisher 在 120 秒配置下运行成功，未再出现第 1 章的超时问题。
- Editor 多轮返修后仍进入 `blocking`，评分在 68 到 74 区间波动。
- 人工编辑保存成功，blocking/revision/reviewed 保存后会转为 `polished`，需要重新审核。
- 局部 AI 返修真实调用成功：
  - 原选区：`太顺利了。`
  - 候选替换：`这顺利得反常。`
  - 接受候选后保存版本成功。

## 已修复问题

1. Polisher 真实模式超时过短
   - `config/local.yaml` 本地验收配置新增独立 `polisher` profile。
   - Polisher / Editor 超时从 45 秒调整到 120 秒，重试次数调整为 2。
   - 新增可提交模板 `config/local.real.example.yaml`，避免真实验收配置只留在本机 ignored 文件中。

2. Local revision 绕过 Agent LLM routing
   - 局部返修从旧 `get_llm_provider()` 改为通过 `_build_llm_router(...).for_agent("author")` 获取模型。
   - 避免真实模式下绕过 `config/local.yaml`，误走旧默认模型。

3. Workflow timeline 语义不准确
   - 支持 `skipped` 状态。
   - 从中途状态继续时，上游节点显示“跳过”，不再显示 pending。
   - 同一节点多轮返修时按最后一个事件判断状态。
   - 当前 run 不再挂载旧 run 的 artifacts，避免产物泄漏。

4. QualityHub 返修目标错误
   - `editor_rejected` 的 `revision_target` 从无意义的 `editor` 改为 `author`。

5. 中文叙事评分过硬
   - 中文弯引号 `“”` 可被识别为对话。
   - 章末反转、警告、追问类钩子不再被机械判 0。
   - 增加都市悬疑/技术冲突相关关键词。

6. Blocked run 与章节状态不一致
   - 新增 `reconcile_latest_blocked_runs_with_chapters()`。
   - 当某章最新 workflow run 是 `blocked`，但章节仍处于 `planned/drafted/polished` 等非终态时，章节自动纠正为 `blocking`。
   - 只看最新 run，避免旧 blocked run 污染后来已重置或成功的章节。
   - 接入 workspace、workflow timeline、production-next。

## 当前真实项目状态

- `GET /api/health` 返回 `llm_mode=real`。
- `霓虹雨档案` 第 1 章：`blocking`，timeline 推荐“清除阻塞并重置”。
- `霓虹雨档案` 第 2 章：`blocking`，有真实生成正文、人工编辑版本、局部返修版本。
- `production-next` 推荐恢复第 1 章阻塞运行。

这说明系统没有假阳性地声明“真实链路通过”；真实链路可运行，但质量门禁和恢复闭环仍需要创作者参与。

## 验证结果

- `python3 -m pytest tests/test_v58_workflow_observability.py -q`：23 passed
- `python3 -m pytest tests/test_v57_chapter_editing_versions.py tests/test_qualityhub.py -q`：23 passed
- `python3 scripts/verify.py smoke`：passed
- 前端此前同轮验证：
  - `npm run typecheck`：passed
  - `npm run lint`：passed
  - `npm run build`：passed
  - `npm run test -- --run`：148 passed

## 剩余产品判断

真实 LLM 生成的内容会被当前 Editor / narrative quality gate 多次打回。这里不是运行链路崩溃，而是质量策略偏硬：

- 对话比例、章末钩子、商业爽点等指标适合作为建议项，但不一定都应该硬阻塞。
- 建议下一轮把质量门禁拆成：
  - 硬错误：事实矛盾、缺失关键事件、严重逻辑断裂、禁用表达。
  - 建议改进：对话偏少、钩子偏弱、节奏偏平、商业吸引力不足。

这样更符合个人创作者工作台：系统帮作者定位问题，但不替作者僵硬地卡死生产。
