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

// ── Workflow node narrative (running-state human-readable action) ─

export const WORKFLOW_NODE_NARRATIVE: Record<string, string> = {
  health_check: '正在检查运行环境...',
  task_discovery: '正在识别创作任务...',
  planner: '正在规划章节结构...',
  screenwriter: '正在编排场景与情节...',
  author: '正在撰写章节正文...',
  polisher: '正在润色文字表达...',
  editor: '正在审核内容质量...',
  memory_curator: '正在整理章节记忆...',
  publisher: '正在发布章节...',
  publish: '正在发布章节...',
  awaiting_publish: '等待人工确认发布',
  archive: '正在归档本章...',
  revision_router: '正在分析返修方向...',
  human_review: '等待人工审核',
}

export function tWorkflowNodeNarrative(node: string | null | undefined): string {
  if (!node) return '正在处理...'
  return WORKFLOW_NODE_NARRATIVE[node] || '正在处理...'
}

// ── Execution event narrative (human-readable event descriptions) ─

export const EVENT_NARRATIVE: Record<string, string> = {
  node_started: '节点开始处理',
  context_loaded: '读取上下文完成',
  llm_started: '开始调用 AI 模型',
  llm_completed: 'AI 模型调用完成',
  llm_failed: 'AI 模型调用失败',
  artifact_saved: '产物已保存',
  skill_started: 'Skill 开始处理',
  skill_completed: 'Skill 处理完成',
  tool_called: '工具调用完成',
  self_check_completed: '自检完成',
  fallback_used: '使用了降级方案继续创作',
  diff_generated: '生成改动摘要',
  evidence_verified: '质量检查',
  node_completed: '节点处理完成',
  node_failed: '处理失败',
  node_skipped: '该步骤已跳过',
  quality_diagnosed: '质量诊断完成',
  revision_context_loaded: '读取返修依据',
  revision_diff_generated: '生成返修改动',
  revision_followup_verified: '返修复核',
}

export function tEventNarrative(eventType: string | undefined | null): string {
  if (!eventType) return ''
  return EVENT_NARRATIVE[eventType] || eventType
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
  view_running_workflow: '查看运行进度',
  review_chapter: '审核章节',
  recover_blocked_run: '恢复阻塞运行',
  review_existing_chapter_content: '检查已有正文',
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

// ── Artifact type labels ────────────────────────────────────────

export const ARTIFACT_TYPE_LABEL: Record<string, string> = {
  chapter_brief: '章节规划',
  scene_plan: '章节场景规划',
  draft: '章节初稿',
  polished_draft: '润色稿',
  polished_content: '润色稿',
  review: '审核报告',
  published_chapter: '发布记录',
  memory_update: '记忆更新',
  style_report: '风格报告',
  fact_snapshot: '事实快照',
}

export function tArtifactType(type: string | null | undefined): string {
  if (!type) return '产物'
  return ARTIFACT_TYPE_LABEL[type] || type
}

// ── v5.7 Version source labels ───────────────────────────────────

export const VERSION_SOURCE_LABEL: Record<string, string> = {
  ai_generation: 'AI 生成',
  manual_edit: '人工编辑',
  local_revision: '局部返修',
  rollback: '回滚',
  publish_snapshot: '发布快照',
}

export function tVersionSource(source: string | null | undefined): string {
  if (!source) return '未知'
  return VERSION_SOURCE_LABEL[source] || source
}

export const LOCAL_REVISION_MODE_LABEL: Record<string, string> = {
  rewrite: '重写',
  polish: '润色',
  shorten: '精简',
  expand: '扩写',
  tone: '调整语气',
}

export function tRevisionMode(mode: string | null | undefined): string {
  if (!mode) return '返修'
  return LOCAL_REVISION_MODE_LABEL[mode] || mode
}
