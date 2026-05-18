# v6.1 Review

## 审查范围

v6.1 Agent Work Process Streaming & Auditable Execution Evidence

## 审查结论

通过，已完成二次 Review 修复。

## 审查项

### 1. 数据安全性
- 执行事件不存储原始 LLM 思考链
- payload_json 仅存储摘要、计数、ID
- 无敏感信息泄露风险

### 2. 向后兼容性
- timeline API 新增字段均为可选
- 无执行事件时返回空列表
- 现有 workflow_node_events 不受影响
- 现有测试全部通过

### 3. 性能影响
- 执行事件日志为 best-effort，try/except 保护
- SSE 轮询间隔 1.5 秒
- evidence_verified 仅在节点成功后执行一次

### 4. 测试覆盖
- 24 个后端测试覆盖：Repository、Helpers、Timeline、SSE、Agent ExecEvents、Evidence Verifiers
- 2 个前端测试覆盖：折叠态证据失败徽标、展开态工作过程事件

## 二次 Review 修复

1. MemoryCurator 证据校验不再调用不存在的 `chapter_number` 参数，改为按章节过滤批次，避免误报无记忆。
2. SSE 与 timeline 的显式 `run_id` 查询不再受最近运行列表限制，历史 run 可以稳定回放。
3. workflow tab 已接入 `workflow-stream` 长连接，运行中事件会合并到 timeline 节点。
4. 节点证据失败/警告在折叠态直接可见，避免“显示完成但证据失败被藏起来”。
5. SSE hook 在 run 切换时会重置 done/error/live events，避免新一轮运行不再连接。

## 残留风险

1. 证据校验失败当前为警告模式，后续版本可收紧
2. SSE 长连接在反向代理后可能被超时断开
