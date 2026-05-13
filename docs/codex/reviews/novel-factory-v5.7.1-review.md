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

## 当前风险

1. 第 4 章仍处于 `planned + 有正文` 的保护态，需要作者决策下一步。
2. v5.7 编辑器 UI 的完整人工验收尚未全部执行。
3. pending memory updates 仍存在，可能影响后续 production-next 推荐。
4. 尚未跑 full 基线，不能声明 v5.7.1 完成。

## 结论

本轮 Review 修复了真实项目暴露出的两个 P1 稳定性问题。v5.7.1 还不能宣布完成，但内部状态已经从“幽灵 running + 错误 next action”收敛到“明确保护态 + 可解释下一步”。
