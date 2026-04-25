# v1.2 质量与一致性增强开发规范

## 目标

v1.2 的目标是提升章节产出的质量稳定性和长篇一致性。

v1.1 已经解决工程稳定性问题：workflow run、artifact hash、版本幂等、超时标记、过期写入防护和 checkpoint 注入基础。v1.2 在此基础上增强质量门禁与上下文能力。

本轮重点：

- 完整 ContextBuilder。
- 更严格 death penalty。
- 更严格 state verifier。
- 更严格 plot verifier。
- learned_patterns 读取与写入。
- best_practices 读取。
- Editor 退回原因结构化分类。
- Polisher 事实变更风险增强。

## 当前前置条件

必须基于以下状态开发：

- v1 MVP 已通过。
- v1 review 返工闸门已通过。
- v1.1 工程稳定性已通过。
- 当前全量测试应为 `157/157` 或更多。
- 不允许破坏 v1 / v1r / v1.1 任何验收测试。

## 本轮允许实现

允许修改：

- `novel_factory/context/builder.py`
- `novel_factory/validators/death_penalty.py`
- `novel_factory/validators/state_verifier.py`
- `novel_factory/validators/plot_verifier.py`
- `novel_factory/validators/chapter_checker.py`
- `novel_factory/agents/author.py`
- `novel_factory/agents/polisher.py`
- `novel_factory/agents/editor.py`
- `novel_factory/db/repository.py`
- `novel_factory/db/migrations/*`
- `novel_factory/models/schemas.py`
- `tests/*`

允许新增：

- `novel_factory/validators/revision_classifier.py`
- `novel_factory/models/quality.py`
- `tests/test_quality.py`
- `tests/test_context_builder.py`

## 本轮禁止实现

- 不新增 Scout / Architect / Secretary。
- 不新增 ContinuityChecker 独立 Agent。
- 不新增多 Provider fallback。
- 不新增 Web UI / Web API。
- 不新增 Skill 热加载。
- 不引入 SQLModel 全量 ORM。
- 不新增章节状态枚举。
- 不改变主链路 `Planner -> Screenwriter -> Author -> Polisher -> Editor`。
- 不改变 v1 Agent 输出契约的核心字段；如需扩展，只能新增可选字段。

## 必修项

### Q1：完整 ContextBuilder

要求：

- `ContextBuilder` 必须按 Agent 类型构建上下文。
- 支持 token 预算。
- 必须片段不可裁剪。
- 可选片段按优先级裁剪。

优先级：

```text
P0 death_penalty / 质量红线
P1 当前章节 brief / instruction
P2 上一章状态卡
P3 scene_beats
P4 本章伏笔要求
P5 相关角色与势力
P6 世界观关键规则
P7 最近章节摘要
P8 learned_patterns
P9 best_practices
```

不同 Agent 必须有不同上下文：

- Author：instruction、scene_beats、state_card、角色、伏笔、death_penalty。
- Polisher：原稿、instruction、事实锁定清单、death_penalty。
- Editor：正文、instruction、state_card、伏笔要求、anti_patterns、learned_patterns。

验收：

- 测试覆盖 Author / Polisher / Editor 三种上下文。
- 测试覆盖 token 预算裁剪。
- 测试覆盖必须片段不被裁剪。

### Q2：death penalty 规则增强

要求：

- 禁用词规则从硬编码列表扩展为结构化规则。
- 至少支持：
  - 精确词。
  - 子串匹配。
  - 正则匹配。
  - 严重等级 `critical/high/medium/low`。
- `critical` 触发时 Author/Polisher 必须失败。
- Editor 遇到 `critical` 应强制低分或退回。

验收：

- 测试覆盖精确词、子串、正则。
- 测试覆盖 critical 触发 Author 失败。
- 测试覆盖 Polisher 输出 critical 词失败。
- 测试覆盖 Editor 对 critical 词退回。

### Q3：state verifier 增强

要求：

- 检查当前章节内容是否违反上一章状态卡。
- 至少支持：
  - 等级/数值不得无来源跳变。
  - 位置不得无过渡变化。
  - 已锁定角色关系不得反转。
- v1.2 可以先用规则和关键词近似，不要求完美 NLP。

验收：

- 测试覆盖状态卡等级为 Lv3，正文出现 Lv5 时违规。
- 测试覆盖状态卡位置为公司，正文无过渡直接到异地时 warning。
- 测试覆盖没有状态卡时返回 warning 而非崩溃。

### Q4：plot verifier 增强

要求：

- 检查 instruction 中 `plots_to_plant` 和 `plots_to_resolve` 是否在正文中有对应处理。
- 检查伏笔引用是否存在于 `plot_holes`。
- 检查兑现伏笔是否仍处于可兑现状态。
- 输出结构化结果：`missing_plants`、`missing_resolves`、`invalid_refs`、`warnings`。

验收：

- 测试覆盖要求埋设但正文未提及。
- 测试覆盖要求兑现但正文未提及。
- 测试覆盖引用不存在的伏笔。
- 测试覆盖无伏笔要求时通过。

### Q5：learned_patterns

要求：

- Repository 支持写入和读取 `learned_patterns`。
- Editor 在退回时，将高价值问题写入 `learned_patterns`。
- ContextBuilder 为 Author/Polisher/Editor 注入高频 enabled patterns。
- 不要求复杂学习算法，先做规则化积累。

验收：

- 测试覆盖 Editor 退回后写入 learned_patterns。
- 测试覆盖 disabled pattern 不进入上下文。
- 测试覆盖高频 pattern 优先进入上下文。

### Q6：best_practices

要求：

- Repository 支持读取 `best_practices`。
- ContextBuilder 将高分实践注入 Author 和 Polisher 上下文。
- v1.2 不要求自动提取 best_practices，只要求读取与注入。

验收：

- 测试覆盖 best_practices 进入 Author 上下文。
- 测试覆盖低分或不相关实践不进入上下文。
- 测试覆盖 token 预算不足时 best_practices 可被裁剪。

### Q7：Editor 退回原因结构化分类

要求：

- 新增退回原因分类器。
- Editor 输出或后处理应给每个 issue 分类。
- 分类至少包括：
  - `setting`
  - `logic`
  - `poison`
  - `text`
  - `pacing`
  - `plot`
  - `state`
- 根据分类决定 `revision_target`：
  - `text/pacing` 优先 Polisher。
  - `logic/plot/state/setting` 优先 Author。
  - 指令或设定源错误才 Planner。

验收：

- 测试覆盖 AI 味问题路由到 Polisher。
- 测试覆盖逻辑/伏笔/状态问题路由到 Author。
- 测试覆盖设定源冲突路由到 Planner。
- 测试覆盖分类结果写入 review 或 artifact。

### Q8：Polisher 事实变更风险增强

要求：

- Polisher 润色前生成事实锁定清单。
- 润色后对比锁定事实。
- 如果关键事实缺失或变化，`fact_change_risk` 不能为 `none`，并且 Polisher 必须失败。

事实锁定清单至少包含：

- 关键事件。
- 伏笔引用。
- 状态卡关键数值。
- 角色关系关键词。

验收：

- 测试覆盖 Polisher 删除关键事件时失败。
- 测试覆盖 Polisher 删除伏笔引用时失败。
- 测试覆盖正常句式润色通过。

## 数据库与迁移

如现有表已包含所需字段，优先复用。

允许新增 migration：

- learned_patterns 缺字段时补字段。
- best_practices 缺字段时补字段。
- reviews 需要结构化 issue 分类时可新增字段，例如 `issue_categories TEXT DEFAULT '[]'`。

迁移必须幂等，必须兼容旧库。

## 测试要求

新增测试建议：

- `tests/test_context_builder.py`
- `tests/test_quality.py`
- `tests/test_revision_classifier.py`

必须覆盖：

- ContextBuilder 三类 Agent 上下文。
- token 预算裁剪。
- death penalty 结构化规则。
- state verifier。
- plot verifier。
- learned_patterns 写入和读取。
- best_practices 注入。
- Editor 退回分类和 revision_target。
- Polisher 事实锁定。

完成后全量测试必须通过。

## 回归要求

开发 Agent 完成本轮后必须汇报：

- 修改文件列表。
- 新增 migration。
- 新增测试列表。
- 全量测试数量。
- 测试结果。
- 是否有未完成项或风险。

## 验收标准

- v1 / v1r / v1.1 所有测试仍通过。
- v1.2 新增测试全部通过。
- 没有新增 v2 能力。
- 质量规则失败时不能写入成功状态。
- Editor 退回目标更稳定，不再只依赖 LLM 自报。

## 通过后下一步

v1.2 通过后，进入 **v2 多 Agent 扩展**。

v2 才允许新增：

- Scout。
- Architect。
- Secretary。
- ContinuityChecker。
