/**
 * Unified state mapping for auto-run sessions, workflow nodes, action keys,
 * and step results. Used across ProjectOverviewModule and ChapterWorkspace
 * to ensure consistent author-facing Chinese labels.
 *
 * v5.5.13: Separated from i18n.ts which handles chapter/workflow statuses.
 */

// ── Auto-run session status + stop_reason ─────────────────────────

/**
 * Translate auto-run session status + stop_reason into author-facing Chinese.
 * Takes BOTH values because the same stop_reason means different things
 * in different session statuses (e.g. "paused" + "client_disconnected"
 * vs "paused" + manual pause).
 */
export function tSessionStopLabel(status: string, stopReason?: string): string {
  if (status === 'running') return '正在生产'
  if (status === 'completed') return '已完成'
  if (status === 'cancelled') return '已取消'
  if (status === 'dry_run') return '试运行完成'

  if (status === 'paused') {
    if (stopReason === 'client_disconnected') return '连接已断开，可重新接入'
    return '已暂停'
  }

  if (status === 'stopped') {
    switch (stopReason) {
      case 'token_budget_exceeded': return '已因预算上限停止'
      case 'repeated_failure': return '同一步多次失败，已停止'
      case 'consecutive_no_progress': return '连续无进展，已停止'
      case 'review_required': return '需要人工审核'
      case 'blocked': return '被阻塞'
      case 'max_steps_reached': return '已达最大步数'
      case 'completed': return '已完成'
      case 'dry_run_preview': return '试运行完成'
      case 'unsupported_action': return '遇到不支持的操作，已停止'
      case 'obsolete': return '旧会话已过期'
      default: return '已停止'
    }
  }

  if (status === 'failed') return '运行失败'

  return status
}

// ── Workflow node labels ──────────────────────────────────────────

export const WORKFLOW_NODE_LABEL: Record<string, string> = {
  health_check: '预检',
  task_discovery: '任务识别',
  planner: '规划',
  screenwriter: '编剧',
  author: '执笔',
  polisher: '润色',
  editor: '审稿',
  memory_curator: '记忆整理',
  publisher: '发布',
  publish: '发布',
  awaiting_publish: '等待发布',
  archive: '归档',
  revision_router: '返修路由',
  human_review: '人工审核',
}

export function tWorkflowNodeLabel(node: string | null | undefined): string {
  if (!node) return '—'
  return WORKFLOW_NODE_LABEL[node] || node
}

// ── Production action key labels ──────────────────────────────────

export const ACTION_KEY_LABEL: Record<string, string> = {
  generate_genesis: '生成创世设定',
  review_genesis: '审核创世设定',
  wait_genesis: '等待创世设定完成',
  repair_title_contract: '修复书名契约',
  generate_missing_context: '补全缺失上下文',
  apply_memory_updates: '应用记忆更新',
  generate_chapter: '生成章节',
  continue_next_chapter: '继续下一章',
  review_chapter: '审核章节',
  recover_blocked_run: '恢复阻塞运行',
  generate_arc_plan: '生成弧线规划',
  none: '无待办',
}

export function tActionKey(key: string | undefined | null): string {
  if (!key) return '—'
  return ACTION_KEY_LABEL[key] || key
}

// ── Auto-run step result labels ───────────────────────────────────

export const STEP_RESULT_LABEL: Record<string, string> = {
  success: '成功',
  failed: '失败',
  skipped: '跳过',
  dry_run: '试运行',
  blocked: '阻塞',
  unsupported: '不支持',
  unknown: '未知',
}

export function tStepResult(result: string | undefined | null): string {
  if (!result) return '—'
  return STEP_RESULT_LABEL[result] || result
}
