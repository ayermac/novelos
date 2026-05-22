# Chapter Objective Checker

验证 Planner 输出的章节目标是否具体、可执行。

## 检查项

1. objective 非空且长度 >= 8
2. 避免抽象词汇（成长、变强、推进剧情等）
3. required_events 至少包含 1 个可落地事件
4. constraints 建议提供（warning 级别）

## 输入

```json
{
  "objective": "本章目标",
  "required_events": ["事件1", "事件2"],
  "constraints": ["约束1"]
}
```

## 输出

```json
{
  "ok": true,
  "error": null,
  "data": {
    "score": 100,
    "issues": [],
    "warnings": [],
    "blocking": false
  }
}
```
