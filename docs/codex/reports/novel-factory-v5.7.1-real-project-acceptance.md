# Novelos v5.7.1 真实项目验收记录

## 验收信息

- 日期：2026-05-13
- 项目：`novel_3v2o`
- 数据库：`acceptance_novel_factory.db`
- 后端模式：`stub`
- 验收目标：验证 v5.7.1 内部构建完整与稳定，优先处理真实项目状态污染、恢复入口一致性和已有正文保护。

## 当前真实项目状态

| 项 | 结果 |
| --- | --- |
| 项目可打开 | 通过 |
| workspace API | 通过 |
| 第 4 章编辑器 API | 通过 |
| 第 4 章版本列表 | 通过，当前版本 `148` |
| Markdown 导出 | 通过，中文文件名使用 `filename*` |
| Smoke 回归 | 通过 |

## 发现的问题

### 1. `production-next` 被记忆更新抢占

真实状态：

- 第 4 章存在 stale running workflow：`3cb99798-fb8d-4aee-bd97-5d0cb6090fa7`
- `health-summary` 正确报告“第 4 章运行疑似卡住”
- `production-next` 却推荐“应用记忆更新”

影响：

- 主入口和健康摘要互相打架；
- 作者会先处理低优先级记忆更新，而不是处理阻塞运行；
- 真实项目会继续保留幽灵 running。

修复：

- `production-next` 纳入项目级 stale running workflow；
- stale running 优先级高于 pending memory updates；
- `health-summary.next_action` 与 `production-next.next_action` 保持一致。

验证：

- `production-next` 推荐变为“处理卡住运行（第 4 章）”；
- `health-summary` 同步返回同一 next_action；
- 新增回归测试覆盖“非当前章节 stale running + pending memory”场景。

### 2. 第 4 章 stale running 恢复链路验证

执行：

```text
POST /api/runs/3cb99798-fb8d-4aee-bd97-5d0cb6090fa7/recovery/mark-stuck
POST /api/projects/novel_3v2o/chapters/4/reset
```

结果：

- run 从 `running` 转为 `blocked`；
- 第 4 章从 `scripted` 转为 `blocking`；
- 再 reset 后第 4 章从 `blocking` 转为 `planned`；
- checkpoint 清理成功；
- health-summary 不再报告 stale running。

### 3. `planned + 有正文` 会被当成空章生成

真实状态：

- reset 后第 4 章状态为 `planned`；
- 但正文仍保留，`word_count=2848`；
- 如果直接生成，会有覆盖已有正文风险。

修复：

- 统一 run guard 新增 `CHAPTER_HAS_EXISTING_CONTENT`；
- `planned` 但已有正文/字数时禁止直接生成；
- `production-next` 推荐“检查第 N 章已有正文”，不再推荐生成；
- 前端 action label 新增 `review_existing_chapter_content`。

验证：

```text
POST /api/run/chapter {"project_id":"novel_3v2o","chapter":4}
```

返回：

```text
CHAPTER_HAS_EXISTING_CONTENT
```

`production-next` 返回：

```text
review_existing_chapter_content
```

## 验收结果

| 验收项 | 结果 |
| --- | --- |
| 打开项目工作台 API | 通过 |
| 第 4 章 stale running 可识别 | 通过 |
| stale running 优先于 pending memory | 通过 |
| stale running 可标记阻塞 | 通过 |
| blocking 章节可 reset | 通过 |
| reset 不清空正文 | 通过 |
| planned + 有正文不允许直接生成 | 通过 |
| production-next 推荐检查已有正文 | 通过 |
| 第 4 章版本列表可读 | 通过 |
| Markdown 导出可用 | 通过 |

## 验证命令

```bash
python3 scripts/verify.py smoke
```

结果：

```text
tests/test_v5515_production_readiness.py: 13 passed
tests/test_v57_chapter_editing_versions.py: 12 passed
```

定向回归：

```bash
python3 -m pytest tests/test_v5515_production_readiness.py tests/test_v553_autonomous_production_loop.py -q
```

结果：

```text
39 passed
```

前端验证：

```bash
npm run typecheck
npm run lint
```

结果：通过。

## 收尾验收补充（2026-05-14）

后续继续对 `novel_3v2o` 执行真实项目验收：

1. 第 4 章已按用户要求显式清空后重新生成并发布。
2. 第 5 到第 10 章均已发布。
3. 第 8、9、10 章生成后的记忆批次已处理。
4. Markdown 导出包含第 10 章内容。
5. `production-next` 当前推荐 `continue_next_chapter`，目标第 11 章，不再重复推荐规划。
6. 本地 API 使用 `--log-level warning --no-access-log` 后可稳定支撑长时间验收。

最终真实项目状态：

| 项 | 结果 |
| --- | --- |
| 当前章节 | 第 10 章 |
| 已发布章节 | 1-10 |
| pending memory updates | 0 |
| production-next | `continue_next_chapter`，目标第 11 章 |
| Markdown 导出 | 通过，包含第 10 章 |
| API health | 通过 |

最终全量验证：

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

## 相关提交

- `9e79c1e` — `fix(v5.7.1): prioritize stale run recovery and protect existing content`
- `a62ebc0` — `fix(v5.7.1): route running target chapters to workflow progress`
- `c85c172` — `fix(v5.7.1): stabilize production validation loop`
