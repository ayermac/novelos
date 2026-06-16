# Novel Factory v6.10.8 Agent Robustness Hardening Plan

Status: Approved
Branch: feature/v6.10.8-agent-robustness-hardening
Date: 2026-06-16

## 背景

v6.10.7 完成核心循环证据治理后，对 `novel_factory/agents/` 全部 7 个 agent 及 workflow 编排层（约 17000 行）做了一次系统审查，发现一批影响路由正确性、数据完整性与生产稳定性的问题。这些问题大多潜伏已久，部分被 v6.10.7 的修复间接暴露（如 target_name fallback 遗漏 instructions 表）。

本版本聚焦**高影响、低回归风险**的稳健性修复，不引入新功能，不动需要架构级改造的根因缺陷（DB 事务、Repository 重构等明确推迟到 v6.11+）。

## 目标

1. 消除路由层因 `quality_gate` 字段名分裂（`passed` vs `pass`）导致的误判。
2. 让 SelfCheckLoop 修复后必须重新自检，避免未校验产物直接入库。
3. 把三处与 `ChapterStatus` 枚举脱钩的硬编码状态排序收口到单一真相源。
4. 修复 Editor 的 `final_gate` revision_target 缺失枚举校验、seam blocking 计数错误。
5. 收尾 v6.10.7：补全 Memory Curator 的 instructions 表 fallback、非数字 target_name 处理、并发锁竞态。
6. 修复 Author 的中文 `_scene_terms` 分词 bug（直接导致生产误返修），清除硬编码小说专属词。
7. 补齐小项：CreativeLedgerCurator 的 `agent_id`、node_recovery 的节点覆盖。

## 范围

### P0：路由与数据完整性

- **quality_gate 字段统一**（`workflow/conditions.py`）：新增 `gate_passed(gate)` helper，三个路由函数 `route_by_quality_gate` / `route_by_review_result` / `route_after_agent` 统一调用，兼容 `passed` 与 `pass` 两种字段名。
- **SelfCheckLoop 修复后重新校验**（`agent_runtime/self_check.py`）：修复成功路径对 `repaired_output` 再调一次 `self_check_fn`；仍未通过 → `ask_human`；通过 → continue。兑现 docstring 承诺的 `final_check`。
- **状态排序共享工具**（`models/state.py`）：新增 `STATUS_ORDER` 字典与 `status_order(s) -> int`，替换 `screenwriter.py` / `author.py` / `polisher.py` 三处局部硬编码 `_STATUS_ORDER`。

### P0/P1：Editor 正确性

- **final_gate revision_target 枚举校验**（`agents/editor.py`）：`_run_final_gate` 读取 `gate_data.get("revision_target")` 后用 `VALID_REVISION_TARGETS` 白名单校验，非法值回退 `normalize_revision_target`，避免路由到不存在的 agent。
- **seam blocking_count 精确计数**（`agents/editor.py`）：从 `len(blocking_issues)` 改为按"章间衔接"子串精确统计，避免污染 `build_policy_input` 的 seam 分类。

### P1：Memory Curator 完整性（v6.10.7 收尾）

- **instructions 表 target_name fallback**（`agents/memory_curator.py`）：补全 v6.10.7 "unified fallback" 遗漏的 instructions 分支，从 `data.get("chapter_number")` 或 `data.get("chapter")` 兜底。
- **_find_existing int() 非数字处理**（`agents/memory_curator.py`）：对 instructions 分支的 `target_name` 用正则提取数字，提取失败记 warning 并返回 None，不再被裸 `except` 静默吞掉。
- **并发锁竞态修复**（`db/repositories/memory_update.py`）：区分异常类型——主键冲突（`sqlite3.IntegrityError`）直接返回未获取；仅对连接类异常走删旧锁重试路径，避免第二个并发请求强占仍在运行的锁。

### P1：Author 分词与死代码

- **_scene_terms 中文匹配重构**（`agents/author.py`）：从"整段中文当一个超长 token"改为"滑窗子串匹配"——对 beat 文本提取所有 N 字符连续子串，检查是否出现在正文 tail。对中英文均健壮，不依赖外部分词库。消除"正常草稿被反复判为 beat 未覆盖"的误返修。
- **移除硬编码小说专属词**（`agents/author.py`）：删除"宴会厅/云澜/会馆/公司走廊"等写死在通用 agent 里的项目专属词，`required_anchor_groups` / `stale_opening_terms` 初始化为空。守卫退化为基于字数/结构的通用回归检测，不再对其他项目产生死代码。

### P1：杂项低风险

- **CreativeLedgerCurator agent_id**（`agents/creative_ledger_curator.py`）：补 `agent_id = "creative_ledger_curator"` 类属性，让 role profile / trace / memory 注入用正确 ID。
- **node_retry_targets 覆盖补全**（`workflow/node_recovery.py`）：`NODE_RETRY_TARGETS` 新增 `quality_gate`(→polished)、`memory_curator`(→reviewed)、`creative_ledger_curator`(→published)，消除 v6.8.5+ 新节点的恢复盲区。

## 非目标

以下问题明确推迟到 v6.11+，本版本不动：

- **DB 多步写入事务化**（所有 creative agent 的"状态推进 + 产物保存"非原子）：需 Repository 层引入事务上下文，回归风险高。
- **forbidden_moves 数据流持久化**：需改 Planner schema + instruction 持久化。
- **修订路由 expected_status 乐观锁**：需审慎设计 expected_status 矩阵。
- **quiet period 基线重构**：需事件心跳基础设施。
- **ContinuityChecker 迁移 BaseAgent**：较大重构，涉及调用契约变更。
- **Editor classify_issues 路由逻辑反转**：逻辑微妙，需专项验证，避免引入错误"修复"。
- **Author `_execute` 方法拆分（940+ 行）**：纯重构，不修 bug，留作技术债清理。

## 验收标准

- 全量 `python3 -m pytest -q` 通过（基线 2616+，不引入回归）。
- 新增 `tests/test_v6108_agent_robustness.py` 覆盖上述 12 项修复的关键路径。
- `version.py = 6.10.8`。
- 规划文档（本文件）与完成报告齐全。

## 风险

- **Author `_scene_terms` 重构**改动覆盖检查的核心匹配逻辑，可能影响 stub 模式下的返修行为。缓解：保持"只检查最后一个 beat"的保守策略不变，仅改 token 提取方式，并加专项回归测试。
- **memory_update 锁异常分流**需正确区分 `IntegrityError` 与 `OperationalError`，避免把连接类异常误判为主键冲突导致锁永久不可获取。缓解：在 `except` 链中精确匹配异常类型，并加并发场景测试。
- **SelfCheckLoop 重新校验**可能让原本"修复后静默通过"的低质量产物进入 human_review，增加人工负担。这是预期行为（数据质量优先），但需在完成报告中说明。

## Follow-Up

- v6.11：Repository 事务上下文 + DB 写入原子化（系统性根因）。
- v6.11：forbidden_moves 全链路持久化。
- v6.11：修订路由 expected_status 矩阵 + quiet period 心跳。
