# Event Coverage Checker

验证 Author 输出的正文是否覆盖写作指令中的必需事件。

## 检查项

1. 正文非空
2. required_events 中的每个事件必须在正文中出现或通过 implemented_events 声明
3. coverage 计算覆盖率

## 输入

```json
{
  "content": "主角林动走进拍卖场...",
  "required_events": ["林动参加拍卖会", "夺得灵药"],
  "implemented_events": ["林动参加拍卖会", "夺得灵药"]
}
```

## 输出

```json
{
  "ok": true,
  "error": null,
  "data": {
    "coverage": 1.0,
    "missing_events": [],
    "issues": [],
    "warnings": [],
    "blocking": false
  }
}
```
