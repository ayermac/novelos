# Novelos v5.7.1 Review 记录

## Review 信息

- 版本：v5.7.1 Internal Hardening
- 日期：2026-05-13
- 类型：内部构建完整与稳定 Review
- 范围：真实项目 `novel_3v2o`、production-next、health-summary、run guard、恢复链路、导出 smoke。

## 本轮发现

### P1：`production-next` 未优先处理项目级 stale running

`health-summary` 已报告第 4 章 stale running，但 `production-next` 仍推荐 pending memory updates。

影响：

- 主入口与健康摘要给出不同优先级；
- 作者容易忽略真正阻塞项；
- stale running 长时间残留，后续章节状态继续变乱。

修复：

- 新增项目级 stale running 检测；
- stale running 优先级高于 pending memory；
- `health-summary.next_action` 与 `production-next.next_action` 使用同一决策。

验证：

- `novel_3v2o` 真实项目验证通过；
- 新增测试覆盖非当前章节 stale running 抢占 pending memory。

### P1：`planned + 有正文` 会被误认为可生成空章

第 4 章 reset 后变成 `planned`，但正文和版本仍保留。直接生成存在覆盖已有正文风险。

修复：

- 统一 run guard 新增 `CHAPTER_HAS_EXISTING_CONTENT`；
- `production-next` 新增 `review_existing_chapter_content`；
- 前端 action label 增加“检查已有正文”。

验证：

- 真实项目第 4 章直接生成被拒绝；
- `production-next` 推荐检查第 4 章已有正文；
- 新增后端回归测试。

## 已验证

```bash
python3 -m pytest tests/test_v5515_production_readiness.py tests/test_v553_autonomous_production_loop.py -q
```

结果：

```text
39 passed
```

```bash
python3 scripts/verify.py smoke
```

结果：

```text
13 passed + 12 passed
```

```bash
cd frontend
npm run typecheck
npm run lint
```

结果：通过。

## 收尾 Review 补充（2026-05-14）

在后续真实项目验收中继续处理了以下问题：

1. 第 4 章已按用户要求显式清空并重新生成，当前真实项目已继续推进到第 10 章发布。
2. 第 8、9、10 章生成后的 memory batches 已处理，`production-next` 不再被 pending memory 抢占。
3. 修复第 10 章发布后已有第 11 章写作指令但未创建章节行时，`production-next` 错误推荐重复规划的问题。
4. 为本地长时间验收增加 API 低日志启动参数，降低 access log 堆积对本地服务稳定性的干扰。
5. 修复 `test_p1_error_handling.py` 中由 Python hash 随机化导致的偶发章节号冲突。

最终验证：

```bash
python3 scripts/verify.py full
```

结果：

```text
1866 passed
frontend typecheck passed
frontend lint passed
frontend build passed
vitest 125 passed
```

最终提交：

- `c85c172` — `fix(v5.7.1): stabilize production validation loop`

## 结论

v5.7.1 Review 通过。真实项目运行状态、恢复入口、已有正文保护、production-next 推荐、导出 smoke 和全量验证均已收敛。v5.7.1 可以作为当前稳定分支，下一阶段进入 v5.8 工作流可观测与恢复增强。
