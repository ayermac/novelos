# v6.4.1 Author Drafting Contract Review

## 总体 verdict：PASS

## Review 检查项

### 1. 只改 Author，不改 Polisher/Editor/Workflow
- [x] `AUTHOR_SYSTEM_PROMPT` 只在 `author.py` 中修改
- [x] 未修改 `polisher.py`、`editor.py` 的 prompt 或逻辑
- [x] 未修改 `workflow/graph.py`、`workflow/nodes.py` 的拓扑
- [x] `workflow/execution_events.py` 未修改（除 v6.4.0 已添加的 `EVENT_QUALITY_DIAGNOSED`）

### 2. Drafting Contract 完整性
- [x] SYSTEM_PROMPT 包含"禁止剧情摘要/设定说明/章节梗概"
- [x] SYSTEM_PROMPT 包含 Show-Don't-Tell 铁律
- [x] SYSTEM_PROMPT 包含感官细节要求
- [x] SYSTEM_PROMPT 包含对白人物化要求
- [x] SYSTEM_PROMPT 包含设定戏剧化要求
- [x] SYSTEM_PROMPT 包含章末禁止说教
- [x] build_context 注入"去AI味写作指南"（7 条规则）
- [x] plain-text fallback 系统提示也增加约束

### 3. self-check 行为正确
- [x] 新增 4 个 warning heuristic（show_dont_tell, sensory_detail, prose_like, dialogue）
- [x] warning 只添加到 `SelfCheckResult.warnings`，不影响 `passed`
- [x] hard fail 仍由 event_coverage、death_penalty、word_count 控制
- [x] key_events 缺失时仍 hard fail
- [x] repairable 仍只判断 word_count/death_penalty

### 4. Stub provider 同步
- [x] ch1/ch2/ch3 的"心中一凛/心中涌起/心中一动"已替换为动作描写
- [x] stub content 不触发 critical death penalty
- [x] stub 标题和内容多样性保持

### 5. 代码质量
- [x] 新增测试 18/18 通过
- [x] backend smoke 通过
- [x] backend full suite 2008 passed, 0 failed
- [x] 无前端改动，无需前端验证
- [x] 无 desktop 改动，无需 desktop 验证

### 6. 文档
- [x] 规格文档 v6.4.1 状态已更新
- [x] 新增 completion report
- [x] 新增 review

## Review Findings

- 无阻塞问题。
- 角色语言特征摘要（从 characters 表提取）和 scene beats `turn` 为空警告未在本版本实现，属于已知限制，不影响 v6.4.1 目标达成。
- self-check heuristic 基于正则统计，v6.4.3 将升级为 Skill-based validator。

## 安全继续开发：是
