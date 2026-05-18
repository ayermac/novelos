# v6.4.1 Author Drafting Contract 完成报告

## 总体 verdict：PASS

## 改动文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `novel_factory/agents/author.py` | 修改 | 扩展 SYSTEM_PROMPT（Drafting Contract）、build_context（去AI味指南）、self-check（4 个 warning heuristic）、plain-text 约束 |
| `novel_factory/llm/stub_provider.py` | 修改 | 替换 ch1/ch2/ch3 直白内心描写为动作描写 |
| `tests/test_v64_author_drafting_contract.py` | 新增 | 18 个测试覆盖 prompt/context/self-check/stub/workflow |
| `docs/codex/planning/novel-factory-v6.4-chapter-quality-closure-spec.md` | 修改 | v6.4.1 状态更新为已实现 |

## Author SYSTEM_PROMPT 新增约束

- 禁止剧情摘要、设定说明、章节梗概；必须以场景为单位推进
- 情绪通过动作、神态、对话展现；禁止"感到/觉得/意识到/明白/心中暗想"等直白情绪词
- 每个场景至少包含 1 种视觉 + 1 种听觉/触觉/嗅觉细节
- 对白必须有角色目的、潜台词或冲突；禁止所有角色使用同一套礼貌/书面语
- 世界观和设定必须通过角色动作、对话或场景细节展现，禁止旁白式解释
- 章节结尾留悬念，禁止归纳人生道理、总结本章意义、发表作者评论

## build_context 新增"去AI味写作指南"

7 条硬编码规则，注入到每个 Author 调用中：
1. 禁止直白情绪动词，改为动作或神态
2. 禁止内心独白模板，改为动作推进
3. 禁止设定旁白，改为角色动作或对话展现
4. 禁止解释句式（"简单来说/说白了/所谓...是指"）
5. 每个场景至少包含一种视觉 + 一种其他感官细节
6. 对白要有冲突或潜台词，避免功能化问答
7. 章节结尾留悬念，禁止说教式总结

## self-check 新增 warning heuristic（不 hard fail）

| heuristic | 触发条件 | 输出 |
|---|---|---|
| `show_dont_tell` | 直白情绪词密度 > 5/千字 | warning |
| `sensory_detail` | 感官词密度 < 3/千字 | warning |
| `prose_like` | 摘要式表达 > 3 处 | warning |
| `dialogue` | 对白占比 < 5% | warning |

所有新增 heuristic 只输出到 `SelfCheckResult.warnings`，不影响 `passed` 和 `repair_needed`。

## 测试结果

| 命令 | 结果 |
|---|---|
| `python3 -m pytest tests/test_v64_author_drafting_contract.py -q` | **18 passed** |
| `python3 scripts/verify.py smoke` | **13 passed** |
| `python3 -m pytest tests/test_agents.py tests/test_quality.py tests/test_v64_author_drafting_contract.py -q` | **93 passed** |
| `python3 -m pytest -q` | **2008 passed, 0 failed** |

## 已知限制

- self-check heuristic 基于简单正则和统计，v6.4.3 将升级为更精准的 deterministic validator
- 角色语言特征摘要（从 characters 表提取）未在本版本实现，保留在 v6.4.2+ 计划
- scene beats `turn` 为空时的 context 标注警告未在本版本实现

## 安全继续开发：是
