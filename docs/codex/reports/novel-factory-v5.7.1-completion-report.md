# Novelos v5.7.1 Internal Hardening 完成报告

## 版本信息

- 版本：v5.7.1 Internal Hardening
- 日期：2026-05-14
- 分支：`v5.7.1`
- 类型：内部稳定化版本
- 基线：v5.7 Daily Writing Editing and Versioning

## 目标

v5.7.1 的目标不是扩展新功能，而是把现有个人作者工作台压实到可持续迭代状态：

1. 使用真实项目 `novel_3v2o` 验证生产链路。
2. 修复运行状态、恢复入口、已有正文保护和 production-next 推荐中的真实问题。
3. 确认编辑、版本、导出、记忆应用、章节继续生成等核心路径不回归。
4. 建立分层验证方式，避免每次小改都跑完整测试。
5. 为 v5.8 工作流可观测与恢复增强做准备。

## 完成内容

### 1. 真实项目验收完成

`novel_3v2o` 已完成真实生产链路验收：

- 第 4 章历史 stale running 已处理；
- 第 4 章显式清空后重新生成并发布；
- 第 5 到第 10 章已发布；
- 第 8、9、10 章记忆批次已处理；
- 当前无 pending memory updates；
- `production-next` 当前推荐继续生成第 11 章；
- Markdown 导出包含第 10 章。

详情见：

```text
docs/codex/reports/novel-factory-v5.7.1-real-project-acceptance.md
```

### 2. 运行状态与恢复一致性收敛

修复了以下真实项目暴露的问题：

- 项目级 stale running 优先级低于 pending memory；
- `health-summary` 与 `production-next` 推荐不一致；
- `planned + 有正文` 被误认为空白可生成章节；
- running target chapter 被错误推荐为继续生成；
- 第 10 章发布后已有第 11 章写作指令，但 `production-next` 仍推荐重复规划。

当前行为：

- stale running 优先进入恢复；
- running target chapter 优先展示工作流进度；
- planned 但已有正文时进入“检查已有正文”保护路径；
- 已有下一章指令但无章节行时，推荐 `continue_next_chapter`；
- 终态章节不会重复启动生成。

### 3. 本地长时间验收稳定性增强

API CLI 增加：

```bash
--log-level
--no-access-log
```

用于长时间本地验收时降低日志输出压力：

```bash
python3 -m novel_factory.cli api \
  --host 127.0.0.1 \
  --port 8765 \
  --db-path acceptance_novel_factory.db \
  --llm-mode stub \
  --log-level warning \
  --no-access-log
```

### 4. 验证脚本和测试稳定性

保留分层验证入口：

```bash
python3 scripts/verify.py smoke
python3 scripts/verify.py v57
python3 scripts/verify.py frontend
python3 scripts/verify.py full
python3 scripts/verify.py durations
```

修复了一个测试不稳定点：

- `tests/test_p1_error_handling.py` 不再使用 Python `hash()` 生成章节号，避免 hash 随机化导致偶发唯一键冲突。

## 最终验证

执行：

```bash
python3 scripts/verify.py full
```

结果：

```text
pytest: 1866 passed
frontend typecheck: passed
frontend lint: passed
frontend build: passed
vitest: 125 passed
```

## 关键提交

- `9e79c1e` — `fix(v5.7.1): prioritize stale run recovery and protect existing content`
- `3c7b22a` — `fix(v5.7.1): restore auto-run timeout threshold wiring`
- `a62ebc0` — `fix(v5.7.1): route running target chapters to workflow progress`
- `c85c172` — `fix(v5.7.1): stabilize production validation loop`

## 当前结论

v5.7.1 已完成，可以作为当前稳定分支。

下一阶段不建议继续堆叠无边界功能，应进入：

```text
v5.8 Workflow Observability and Recovery
```

重点是让每一次章节生产都能被作者理解：

- 每个节点做了什么；
- 当前卡在哪里；
- 哪个产物来自哪个节点；
- 能从哪里安全恢复；
- 为什么下一步推荐这个动作。
