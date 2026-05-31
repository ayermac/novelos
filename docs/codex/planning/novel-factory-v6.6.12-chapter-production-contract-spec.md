# v6.6.12 Chapter Production Result Contract Closure

**Version**: 6.6.12  
**Status**: Completed  
**Date**: 2026-05-19

## 概述

v6.6.12 将 `domain_result` 语义集成到章节生产相关的所有 API 端点，确保前端能够正确区分 HTTP 请求成功与业务操作成功。

## 核心原则

1. **HTTP `ok` 只表示请求处理成功，不表示业务成功**
2. **业务成功/失败由 `domain_result.domain_status` 决定**
3. **`fallback/degraded/partial_success` 绝不能显示为 `success`**
4. **Memory fallback、review revision、human_review、blocked、failed 必须有明确的 `next_action/action_label`**

## Domain Status 值

| domain_status | severity | 含义 |
|---------------|----------|------|
| success | success | 业务操作完全成功 |
| partial_success | warning | 业务操作部分成功（如 awaiting_publish + memory fallback） |
| fallback | warning | 使用降级结果完成 |
| degraded | warning | 降级模式完成（如 MemoryCurator no-op） |
| failed | error | 业务操作失败 |
| blocked | error | 业务操作被阻塞（如 death penalty、max retries） |
| needs_human | warning | 需要人工介入 |
| pending | info | 操作进行中 |
| ignored | info | 操作已忽略 |

## 已集成端点

### 1. POST /run/chapter

**场景映射**:
- 工作流失败 → `failed`
- 工作流阻塞 + revision → `needs_human`
- 工作流阻塞 → `blocked`
- 完成 + awaiting_publish + memory 问题 → `partial_success`
- 完成 → `success`

### 2. POST /run/chapter/start

**场景映射**:
- 启动成功 → `pending`（工作流运行中）

### 3. POST /publish/chapter

**场景映射**:
- 发布成功 + 可信记忆 → `success`
- 发布成功 + memory 问题 → `partial_success`

### 4. POST /runs/{run_id}/recovery/reset

**场景映射**:
- 重置成功 → `success`（附带 `next_action="start_workflow"`）

### 5. POST /runs/{run_id}/recovery/mark-stuck

**场景映射**:
- 标记卡住 → `blocked`（附带 `next_action="reset_chapter"`）

### 6. POST /runs/{run_id}/recovery/retry-node

**场景映射**:
- 节点重试成功 → `success`（附带 `next_action="start_workflow"`）

### 7. POST /memory/apply

**场景映射**:
- 全部应用成功 → `success`
- 部分失败 → `partial_success`
- 全部忽略 → `ignored`

### 8. GET /projects/{project_id}/production-next

**场景映射**:
- 项目就绪 → `success`
- 存在阻塞章节 → `needs_human`
- 资料不完整 → `blocked`
- 工作流运行中 → `pending`

### 9. POST /projects/{project_id}/production/run-auto

**场景映射**:
- 完成且有章节 → `success`
- 需要审核 → `needs_human`
- 被阻塞 → `blocked`
- 失败 → `failed`
- 完成但无章节 → `partial_success`

## 前端集成要求

### Toast/Alert 显示

```typescript
function showToast(response: ApiResponse) {
  const { domain_result } = response.data;
  
  // 根据 severity 选择 toast 类型
  switch (domain_result.severity) {
    case 'success':
      toast.success(domain_result.user_message);
      break;
    case 'warning':
      toast.warning(domain_result.user_message);
      break;
    case 'error':
      toast.error(domain_result.user_message);
      break;
    case 'info':
      toast.info(domain_result.user_message);
      break;
  }
}
```

### 按钮状态

```typescript
function getButtonState(domain_result: DomainResult) {
  return {
    disabled: domain_result.blocking,
    loading: domain_result.domain_status === 'pending',
    variant: domain_result.severity === 'error' ? 'danger' : 'default',
    label: domain_result.action_label || '确定',
  };
}
```

## 测试覆盖

- `test_v6612_chapter_production_contract.py` 包含所有端点的契约测试
- 验证 `domain_result` 必须字段存在
- 验证 degraded 状态绝不会有 severity='success'
- 验证 actionable 状态必须有 next_action/action_label

## 向后兼容

- 所有现有端点保持向后兼容
- `domain_result` 作为新增字段，不影响现有字段
- 前端可以渐进式迁移到使用 `domain_result`

## 相关版本

- v6.6.10: API Contract State Semantics（定义 `OperationResult`）
- v6.6.11: Workflow Timeline Node Semantics（定义 `NodeOperationResult`）
- v6.6.12: Chapter Production Result Contract Closure（本版本）
