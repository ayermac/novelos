# Novel Factory v6.11.02 Chapter Revision Reliability Plan

Status: Partially implemented
Branch: `codex/chapter-revision-reliability`
Date: 2026-08-13
Evidence: project `novel_978q`, workflow run `280ce18a-2319-4a76-b0c6-02dd8ad1cc91`, chapter 43

## 结论

本次卡点不是单一模型质量问题，而是“上游场景事实错误、返修证据在内部重试中丢失、短稿错误消耗章节重试、确定性检测输入不完整”叠加后的闭环失效。

可以直接修复且回归边界清晰的项目已在本分支落地。涉及数据库历史模型、跨 Agent 事实契约和 LLM 调用审计的数据结构调整，按本文的后续阶段实施，不在缺少迁移与兼容验证时直接改生产表。

## 现场证据与根因

### 1. 上游 Screenwriter 已写入冲突时间

Screenwriter 的 scene beat 直接要求出现 `00:00:29`，但没有解释上一状态 `69:52:01` 到该值的转换。当前 Screenwriter self-check 只校验 beat 字段是否齐全，`validate_chapter_inheritance()` 的结果只记录 warning，不参与阻断或返修路由。因此时间冲突进入正文后，Editor 才首次发现，返修层级已经太晚。

### 2. 短稿内部修复错误消耗章节级 retry

Author 的短稿下限失败原先只返回 `word_count_fail`，未标记：

- `internal_repair=true`
- `consume_revision_retry=false`
- `repair_scope=internal_word_count_expansion`

工作流因此把一次字数补足当作完整章节返修，提前耗尽三次 retry。

### 3. Editor 返修证据在内部字数修复中被清空

Author 为避免普通内部修复携带陈旧 review，会统一清空 `_revision_review`。但 Editor 返修稿触发字数扩写时也经过同一路径，导致第二轮 Author 产物中的 `revision_source_review_id/issues/suggestions` 全为空。随后篇幅退化修复只能在没有修改依据的情况下盲目合并旧稿与候选稿。

### 4. Editor Skill 输入不完整制造误判

通用 `before_review` payload 缺少 `title`、`project_id` 和 `_repo`。`continuity-gate` 因而退化为“无仓库标题检查”，空标题可产生错误 warning；运行时 Repository 若直接进入持久化 payload 又不可 JSON 序列化。

### 5. 中文弯引号和 AI 表情变体存在规则缺口

`character-voice-check` 与 `pacing-profile-check` 未正确识别 `“……”`，会把含大量中文对白的正文误判为无对白或低对白。死亡红线只覆盖“嘴角……弯/抬”，未覆盖“弯起嘴角”等倒装表达，导致 LLM Editor 与确定性门禁结论不一致。

## 已直接落地的修改

### A. 返修会计与证据链

1. 短稿失败改为独立的 `internal_word_count_expansion`，不直接消耗章节 retry。
2. 质量门记录 `preserve_revision_feedback` 与 `revision_source_review_id`。
3. 仅当内部修复明确继承 Editor review 时保留返修意见；普通内部压缩/润色仍使用精简上下文。
4. 嵌套 Editor 返修使用 Editor revision 的知识预算，不再强制降到普通内部修复的 1200 token 预算。
5. 篇幅退化合并必须存在非空 issues 或 suggestions；没有可执行证据时直接跳过语义合并。

### B. 确定性质量检查

1. Editor `before_review` payload 补齐 title/project/repo。
2. Skill 审计持久化时过滤 `_repo` 运行时对象。
3. Character Voice 与 Pacing 统一支持直引号、中文弯引号、`「」`、`『』`。
4. 死亡红线新增 `DP_EXPR_03B`，覆盖“弯起嘴角/抬了一下嘴角”等受限倒装变体。

## 复杂改造方案

### Phase 1：Screenwriter 事实继承硬门（P0）

目标：事实冲突在 scene beat 生成后立即返修 Screenwriter，不进入 Author。

设计：

1. 将 `validate_chapter_inheritance()` 的结构化结果接入 Screenwriter self-check，而不是只写日志。
2. 增加 `numeric_state_transition` 检查：若 beat 同时出现同一指标的新旧数值，必须有显式变化原因或转换表达。
3. 对 hard constraint / previous state card 的明确冲突升级为 blocking；信息不足、可能是闪回或视角差异的情况保持 advisory。
4. blocking 路由目标固定为 `screenwriter`，不得让 Author 用正文补丁掩盖场景设计错误。
5. 在 artifact 中保存 inheritance evidence，供 Run Doctor 展示“哪条旧事实与哪个 beat 冲突”。

验收：构造 `69:52:01 → 00:00:29` 无解释场景时 Screenwriter 不得进入 scripted；有“计时器重置/切换另一计时器”证据时允许通过。

### Phase 2：Review Attempt 不可变历史（P1）

现状：`reviews.chapter_id` 唯一，`save_review()` 会覆盖/删除上一轮评审，导致只能看到最新结果，无法还原 65 → 44 的评分变化与问题漂移。

迁移方案：

1. 新增不可变 `review_attempts` 表，主键独立，包含 project/chapter/workflow_run/attempt/score/pass/revision_target/issues/suggestions/policy_snapshot/created_at。
2. 保留 `reviews` 作为 latest projection，避免一次性改动全部读取 API。
3. Editor 事务内先插入 attempt，再 upsert latest projection。
4. API 增加按 run/chapter 查询 attempts；现有 `get_latest_review()` 保持兼容。
5. 回填历史数据时只能生成 latest attempt，不伪造不存在的历史轮次。

迁移必须覆盖桌面端既有 SQLite 数据、幂等升级、降级读取和并发 Editor 写入测试。

### Phase 3：LLM Attempt 级调用追踪（P1）

现状：`last_token_usage` 与 `last_call_trace` 可能来自不同调用，内部扩写/合并超时后日志会混合，难以确认究竟哪一步卡住。

设计：

1. 每次 provider 调用生成 `llm_call_id`，记录 agent/stage/purpose/model/started_at/ended_at/status/timeout/token_usage。
2. Author 明确区分 `draft`、`expand_short`、`merge_length_regression`、`compress_overflow`。
3. 工作流事件只引用 call id，不复制易漂移的“最后一次调用”字段。
4. 流式调用在开始、首 token、结束/超时三个节点更新同一条 attempt。
5. 敏感 prompt 不默认落库，只保存 hash、长度和经过裁剪的诊断摘要。

### Phase 4：Human Review Session 原子化（P1）

当 retry 达上限时，同一事务内创建 human review session、关联最后一次 review attempt、记录未解决问题和推荐动作。UI 不再只显示 `requires_human`，而能展示“哪三轮失败、最后卡在哪个问题、建议从 Screenwriter 还是 Author 恢复”。

## 实施顺序

1. 合入本分支直接修复并做真实项目 dry-run。
2. 单独分支实施 Phase 1；这是减少无效 Author 重写的最高收益项。
3. Phase 2 数据迁移独立发布，先写双轨再切读路径。
4. Phase 3 与 Phase 4 在 review attempts 稳定后接入，避免审计字段再次迁移。

## 验收门槛

- 本分支相关 Python 回归全部通过。
- `internal_word_count_expansion` 前两次只增加 internal repair 计数，不增加 chapter retry。
- Editor 返修触发字数扩写后，下一次 Author artifact 仍包含 source review id、issues、suggestions。
- 普通内部压缩不会意外加载陈旧 Editor review。
- 中文弯引号对白的 Character Voice/Pacing 检测与直引号结果一致。
- `弯起嘴角` 被确定性死亡红线捕获。
- Skill run input JSON 不包含 Repository 对象。

## 风险与回滚

- 保留返修反馈会增加嵌套内部修复 prompt 长度；通过 6000 字符上下文上限和 Editor revision 知识预算控制。
- 新死亡红线规则限制了动词与中间词集合，避免把“抬手擦去嘴角血迹”等正常动作误判。
- 直接修复不改表结构，可按文件级 revert 回滚；Phase 2 必须使用正式 migration，不允许手工改用户数据库。
