# Codex 文档入口

本目录维护 Novelos 的规划、审查、验收和下一阶段方向文档。根目录只保留本入口页；具体文档按语义分目录，避免把历史规格、完成报告和未来草案混在一起。

## 目录约定

| 目录 | 内容 | 使用场景 |
| --- | --- | --- |
| `planning/` | 架构、路线图、历史版本规格、API 规范 | 做版本排期、开发实现、追溯历史决策 |
| `reports/` | 完成报告、真实项目验收、阶段总结 | 判断某个版本是否闭环、查看验收事实 |
| `reviews/` | Review 检查项、发现的问题、修复验证 | 代码/产品审查与回归验证 |
| `next/` | 下一阶段方向、候选路线、未锁定规划 | 讨论未来方向，不作为当前执行规格 |

## 当前稳定基线

- **版本**: v5.5.15 Production Readiness Closure
- **状态**: Review + 真实项目验收通过，项目进入短期收尾可用状态
- **测试基线**: pytest 1841/1841 passed；vitest 67/67 passed；frontend typecheck/lint/build passed
- **完成报告**: [reports/novel-factory-v5.5.15-completion-report.md](reports/novel-factory-v5.5.15-completion-report.md)
- **Review 记录**: [reviews/novel-factory-v5.5.15-review.md](reviews/novel-factory-v5.5.15-review.md)

## 当前执行规则

1. 当前执行真相源仍以 `planning/` 中被明确选定的版本规格为准。
2. `reports/` 和 `reviews/` 记录已经发生的事实，不再承载未来需求。
3. `next/` 只用于方向收口和候选路线，不应被开发 Agent 当作已锁定规格。
4. 历史规格不做大规模改写；如需改变方向，应新增下一阶段文档或新版本规格。

## 关键文档

- 总体架构: [planning/novel-content-factory-architecture.md](planning/novel-content-factory-architecture.md)
- 版本路线: [planning/novel-factory-roadmap.md](planning/novel-factory-roadmap.md)
- API 规范: [planning/novel-factory-api-contract-guidelines.md](planning/novel-factory-api-contract-guidelines.md)
- v5.5.15 规格: [planning/novel-factory-v5.5.15-production-readiness-closure-spec.md](planning/novel-factory-v5.5.15-production-readiness-closure-spec.md)
- 下一阶段方向: [next/personal-author-workbench-direction.md](next/personal-author-workbench-direction.md)

## 下一阶段方向

v5.5.15 完成后，下一阶段不优先展开多租户、企业权限或复杂商业化后台。项目方向先收敛为：

```text
个人创作者的 AI Agent 长篇内容生产工作台
```

近期优先级：

1. 每日创作工作台体验。
2. 长篇记忆与设定一致性。
3. 审核问题定位与局部返修。
4. 创作者资料库 / RAG。
5. AgentOps 运行复盘与评测。
6. 导出与发布流水线。

详细方向见 [next/personal-author-workbench-direction.md](next/personal-author-workbench-direction.md)。

## 本地启动与验收

日常开发建议使用仓库内服务脚本：

```bash
scripts/novelos-service.sh start
scripts/novelos-service.sh stop
scripts/novelos-service.sh restart
scripts/novelos-service.sh status
scripts/novelos-service.sh logs
```

默认使用 `acceptance_novel_factory.db`、`config/local.yaml`、`LLM_MODE=real`、API 端口 `8765` 和 WebUI 端口 `5173`。

也可以手动启动 API 与前端：

```bash
novelos api --host 127.0.0.1 --port 8765 --db-path acceptance_novel_factory.db --llm-mode stub
```

```bash
cd frontend
npm run dev
```

访问 http://localhost:5173 即可使用。
