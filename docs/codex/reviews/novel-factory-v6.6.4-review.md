# v6.6.4 Genesis Initialization Depth & Specificity Closure Review

## 总体 verdict：PASS

## Review 检查项

### 1. Prompt 深化
- [x] `_generate_real_draft` prompt 要求每章包含 `ending_hook`、`continuity_seed`
- [x] prompt 要求角色包含目标、矛盾、利益关系
- [x] prompt 要求势力包含资源/手段、态度、阶段行动
- [x] prompt 要求伏笔包含触发场景、表象、真相方向、预计兑现章节
- [x] prompt 要求大纲包含阶段冲突、转折、阶段结果
- [x] completion prompt 同步更新

### 2. Normalization 扩展
- [x] `_coerce_instruction` 支持 `ending_hook`、`continuity_seed`
- [x] `key_events` 数组规范化不丢信息
- [x] 角色/势力/伏笔/大纲额外字段合并到 `description`/`content`
- [x] `_apply_genesis_to_project` 将 `ending_hook`/`continuity_seed` 合并到 `key_events`/`emotion_tone`

### 3. Quality Gate 加强
- [x] `SHALLOW_INSTRUCTION` blocker 生效
- [x] `ABSTRACT_OBJECTIVE` blocker 生效
- [x] `MISSING_CONTINUITY_SEED` warning 生效
- [x] `WEAK_KEY_EVENTS` warning 生效
- [x] `SHALLOW_CHARACTER_MOTIVATION` warning 生效
- [x] `SHALLOW_FACTION_ACTION` warning 生效
- [x] `WEAK_PLOT_HOLE_DESIGN` warning 生效
- [x] `OUTLINE_TOO_ABSTRACT` blocker 生效
- [x] `CONSECUTIVE_OBJECTIVE` 扩展为检测同义模板（字符集相似度 >= 0.65）
- [x] 没有把 scaffold fallback 伪装成高质量
- [x] 没有放宽质量门让测试通过

### 4. 前端体验
- [x] 质量报告按 section 分组展示
- [x] blocker 显示行动建议
- [x] warning/advisory 不禁用批准按钮但显示风险
- [x] scaffold_fallback 禁用批准
- [x] UI 未开放 force apply 按钮

### 5. API 语义
- [x] `latest` 重新计算 `quality_report`
- [x] `latest` 保留 `_meta.forced_quality_apply`
- [x] 错误文案明确为"创世草案质量不足"
- [x] `force_apply + confirm_quality_risk` 后端能力保留

### 6. 测试覆盖
- [x] `tests/test_v664_genesis_depth_quality.py` 13/13 通过
- [x] v6.6.3 测试 18/18 通过
- [x] v5.3.2/v6.3/v5.5.3 回归测试 56/56 通过
- [x] 后端全量 pytest 2239/2239 通过
- [x] 前端 lint/typecheck/build 通过

### 7. 文档
- [x] spec、completion report、review 已新增
- [x] `docs/codex/README.md` 已更新
- [x] `README.md` / `README.zh-CN.md` 已更新

## Review Findings

### 设计取舍

1. **has_result 正则范围**：结果变化检查依赖一组中文结果关键词（导致、因此、从而、使得...）。如果 LLM 使用其他同义表达（如"于是""终于""最终"），可能漏检。当前已覆盖最常见表达，后续可根据真实 LLM 输出迭代扩充。

2. **相似度阈值 0.65**：Jaccard 字符集相似度 >= 0.65 被标记为同义模板。这个阈值在"地点相同、结构相同、仅换动词"的 objective 上有效，但对于更复杂的 paraphrase 可能不够敏感。当前作为第一层防护已足够。

3. **warning 不阻断批准**：`SHALLOW_CHARACTER_MOTIVATION`、`SHALLOW_FACTION_ACTION` 等设为 warning 而非 blocker，是因为真实 LLM 可能在某些字段上略有缺失但总体可用。如果用户坚持使用，可以批准但会看到风险提示。

## 剩余风险

1. **真实 LLM 输出不可预测**：prompt 增加了深度要求，但真实 LLM 仍可能忽略部分字段或生成看似具体实则空洞的内容。需要持续收集真实使用反馈并迭代关键词正则。
2. **关键词覆盖不完全**：location/action/result 的正则词表基于常见网文场景，对于科幻、历史、悬疑等特殊类型可能不够全面。
3. **前端未开放 force apply**：当前 blocker / scaffold fallback 草案在前端禁用批准按钮；后端仍保留 `force_apply + confirm_quality_risk` 能力，供受控工具或测试路径使用。后续如果产品需要，可以增加明确的"强制应用"确认流程。

## 安全继续开发：是
