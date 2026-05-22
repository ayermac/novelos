# Memory Patch Validator

验证 Memory Curator 抽取的记忆 patch 结构是否完整合法。

## 检查项

1. target_table 必须在允许列表内
2. operation 必须是 create/update/resolve/deprecate
3. data 必须是非空 dict
4. confidence 必须在 0-1 范围内
5. confidence < 0.5 时警告
6. evidence_text 必须非空

## 输入

```json
{
  "patches": [
    {
      "target_table": "characters",
      "operation": "create",
      "target_name": "林动",
      "data": {"name": "林动", "role": "主角"},
      "confidence": 0.9,
      "evidence_text": "林动走出家门...",
      "rationale": "新角色"
    }
  ]
}
```

## 输出

```json
{
  "ok": true,
  "error": null,
  "data": {
    "patch_count": 1,
    "issues": [],
    "warnings": [],
    "blocking": false
  }
}
```
