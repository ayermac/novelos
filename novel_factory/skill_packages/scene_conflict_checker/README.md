# Scene Conflict Checker

验证 Screenwriter 输出的场景 beat 是否具备目标、冲突、转折和钩子。

## 检查项

1. 每个 scene beat 必须包含 scene_goal
2. 每个 scene beat 必须包含 conflict
3. 每个 scene beat 必须包含 turn
4. 每个 scene beat 必须包含 hook
5. 建议声明 plot_refs（warning 级别）

## 输入

```json
{
  "scene_beats": [
    {
      "sequence": 1,
      "scene_goal": "主角进入拍卖场",
      "conflict": "王家子弟故意抬价",
      "turn": "主角亮出隐藏身份",
      "hook": "王家老祖暗中窥视",
      "plot_refs": ["P001"]
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
    "scene_count": 1,
    "issues": [],
    "warnings": [],
    "blocking": false
  }
}
```
