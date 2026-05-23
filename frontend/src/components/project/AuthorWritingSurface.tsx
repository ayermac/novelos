import { useState, useCallback, useEffect, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  Sparkles,
  Loader2,
  Play,
  CheckCircle2,
  FileText,
  PenLine,
} from 'lucide-react'
import { StepStatus } from '../../hooks/useSSEStream'
import { useWorkflowStream } from '../../hooks/useWorkflowStream'
import { tWorkflowNodeLabel, tWorkflowNodeNarrative } from '../../lib/state-labels'
import { tWorkflowStatus, tChapterStatus } from '../../lib/i18n'
import { post } from '../../lib/api'
import type { WorkflowTimelineData, WorkflowExecutionEvent, WorkflowNodeEvidence } from '../../lib/api'
import { PROCESS_DRAFT_LABEL, formatArtifactSummary, getArtifactTitle, type WorkflowArtifacts } from '../../lib/artifacts'
import { LoadingButton, SkeletonStack, InlineMessage, useToast } from '../ui'
import AttentionPanel, { ActionHintList } from '../AttentionPanel'
import WorkflowTimeline from '../WorkflowTimeline'
import ChapterVersionPanel from './ChapterVersionPanel'
import ChapterDiffViewer from './ChapterDiffViewer'
import ChapterEditorSurface from './ChapterEditorSurface'
import QualityDiagnosisPanel from './QualityDiagnosisPanel'

export type SurfaceTabKey = 'content' | 'workflow' | 'artifacts' | 'history' | 'logs' | 'versions'

interface ChapterDetail {
  project_id: string
  project_name: string
  chapter_number: number
  title: string
  status: string
  word_count: number
  quality_score: number | null
  content: string
  created_at: string
  updated_at: string
}

interface Run {
  run_id: string
  chapter_number: number
  status: string
  created_at: string
  error_message?: string
}

interface Step {
  key: string
  label: string
  description: string
  node_group?: 'system' | 'creative_agent' | 'support_agent' | 'terminal' | 'router' | 'unknown'
  node_type?: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'blocked' | 'skipped'
  node_status?: 'pending' | 'running' | 'succeeded' | 'warning' | 'failed' | 'skipped' | 'blocked'
  domain_status?: 'success' | 'partial_success' | 'fallback' | 'degraded' | 'failed' | 'blocked' | 'needs_human' | 'pending' | 'ignored'
  severity?: 'success' | 'info' | 'warning' | 'error'
  retryable?: boolean
  blocking?: boolean
  next_action?: string | null
  action_label?: string | null
  user_message?: string
  flags?: Record<string, boolean>
  error_message?: string
  logs?: {
    id?: string
    timestamp?: string
    level?: 'info' | 'success' | 'warning' | 'error'
    message: string
  }[]
  artifacts?: {
    summary: string
    output_preview?: string
    artifact_labels?: unknown
    artifact_count?: unknown
    artifact_types?: unknown
    [key: string]: unknown
  } | null
  events?: WorkflowExecutionEvent[]
  evidence?: WorkflowNodeEvidence
}

interface RunDetailData {
  run_id: string
  project_id: string
  chapter_number: number
  workflow_status: string
  chapter_status: string
  current_node?: string | null
  llm_mode: string
  started_at?: string
  completed_at?: string
  steps: Step[]
  error_message?: string | null
  total_tokens?: number | null
  duration_ms?: number | null
}

interface WorkflowLogRow {
  id: string
  source: 'timeline' | 'live' | 'run_detail'
  timestamp?: string | null
  node: string
  nodeLabel: string
  category: 'agent' | 'flow' | 'revision' | 'artifact' | 'error'
  level: 'info' | 'success' | 'warning' | 'error'
  eventType: string
  message: string
  payload?: Record<string, unknown> | null
  tokenCount?: number | null
  latencyMs?: number | null
}

const STUCK_RUN_THRESHOLD_MINUTES = 30
const TERMINAL_CHAPTER_STATUSES = new Set(['reviewed', 'awaiting_publish', 'published'])

function isCompletedBeforeTerminal(runStatus?: string | null, chapterStatus?: string | null): boolean {
  return runStatus === 'completed' && !!chapterStatus && !TERMINAL_CHAPTER_STATUSES.has(chapterStatus)
}

function recoveryActionRank(key: string, recommendedAction?: string | null): number {
  if (key === recommendedAction || (key === 'generate' && recommendedAction === 'reset_explicitly')) return 0
  if (key === 'retry_node' || key === 'mark_stuck' || key === 'generate') return 1
  if (key === 'reset' || key === 'reset_chapter' || key === 'reset_explicitly') return 2
  return 3
}

function elapsedMinutesSince(value?: string | null): number | null {
  if (!value) return null
  const normalized = value.includes('T') ? value : value.replace(' ', 'T')
  const timestamp = new Date(normalized).getTime()
  if (Number.isNaN(timestamp)) return null
  return Math.max(0, Math.floor((Date.now() - timestamp) / 60000))
}

function mergeWorkflowEvents(
  existingEvents: WorkflowExecutionEvent[],
  liveEvents: WorkflowExecutionEvent[],
): WorkflowExecutionEvent[] {
  const merged: WorkflowExecutionEvent[] = []
  const seen = new Set<string>()
  for (const event of [...existingEvents, ...liveEvents]) {
    const key = event.id != null
      ? `id:${event.id}`
      : `${event.node_name || ''}:${event.event_type}:${event.status || ''}:${event.created_at || ''}:${event.message || ''}`
    if (seen.has(key)) continue
    seen.add(key)
    merged.push(event)
  }
  return merged
}

function buildLiveEvidence(
  events: WorkflowExecutionEvent[],
  fallback?: WorkflowNodeEvidence,
): WorkflowNodeEvidence | undefined {
  if (events.length === 0) return fallback

  let hasWarnings = false
  let hasEvidenceFailure = false
  let latestSummary = fallback?.latest_event_summary || ''

  for (const event of events) {
    const status = event.status || 'info'
    if (event.event_type === 'evidence_verified' && status === 'fail') {
      hasEvidenceFailure = true
    }
    if (status === 'warning' || status === 'error') {
      hasWarnings = true
    }
    if (
      event.message &&
      (event.event_type === 'evidence_verified' ||
        event.event_type === 'node_completed' ||
        event.event_type === 'llm_completed')
    ) {
      latestSummary = event.message
    }
  }

  return {
    has_evidence: true,
    has_warnings: hasWarnings || fallback?.has_warnings,
    has_evidence_failure: hasEvidenceFailure || fallback?.has_evidence_failure,
    latest_event_summary: latestSummary,
    event_count: events.length,
  }
}

function logLevelFromStatus(status?: string | null): WorkflowLogRow['level'] {
  if (status === 'error' || status === 'failed' || status === 'fail' || status === 'blocked') return 'error'
  if (status === 'warning' || status === 'degraded') return 'warning'
  if (status === 'success' || status === 'completed' || status === 'pass') return 'success'
  return 'info'
}

function logCategoryFromEvent(eventType: string, level: WorkflowLogRow['level']): WorkflowLogRow['category'] {
  if (level === 'error') return 'error'
  if (eventType.includes('revision') || eventType.includes('retry') || eventType.includes('quality_gate')) return 'revision'
  if (eventType.includes('llm') || eventType.includes('context') || eventType.includes('skill') || eventType.includes('evidence')) return 'agent'
  if (eventType.includes('artifact')) return 'artifact'
  return 'flow'
}

function logLevelLabel(level: WorkflowLogRow['level']): string {
  if (level === 'success') return '成功'
  if (level === 'warning') return '警告'
  if (level === 'error') return '错误'
  return '信息'
}

function logCategoryLabel(category: WorkflowLogRow['category']): string {
  if (category === 'agent') return 'Agent'
  if (category === 'revision') return '返修'
  if (category === 'artifact') return '产物'
  if (category === 'error') return '错误'
  return '流转'
}

function formatLogPayload(payload?: Record<string, unknown> | null): string {
  if (!payload || Object.keys(payload).length === 0) return ''
  try {
    return JSON.stringify(payload, null, 2)
  } catch {
    return String(payload)
  }
}

function buildWorkflowLogJsonList(
  rows: WorkflowLogRow[],
  runDetail: RunDetailData | null,
  timeline?: WorkflowTimelineData | null,
): string {
  const runId = timeline?.run_id || runDetail?.run_id || null
  const runStatus = timeline?.run_status || runDetail?.workflow_status || null
  const currentNode = timeline?.current_node || runDetail?.current_node || null
  const projectId = timeline?.project_id || runDetail?.project_id || null
  const chapterNumber = timeline?.chapter_number || runDetail?.chapter_number || null

  return JSON.stringify(
    rows.map((row, index) => ({
      index: index + 1,
      run_id: runId,
      project_id: projectId,
      chapter_number: chapterNumber,
      run_status: runStatus,
      current_node: currentNode,
      source: row.source,
      timestamp: row.timestamp || null,
      level: row.level,
      category: row.category,
      event_type: row.eventType,
      node: row.node,
      node_label: row.nodeLabel,
      message: row.message,
      token_count: row.tokenCount ?? null,
      latency_ms: row.latencyMs ?? null,
      payload: row.payload ?? null,
    })),
    null,
    2,
  )
}

function buildWorkflowLogRows(
  runDetail: RunDetailData | null,
  timeline?: WorkflowTimelineData | null,
  sseSteps?: Record<string, StepStatus>,
): WorkflowLogRow[] {
  const rows: WorkflowLogRow[] = []
  const seen = new Set<string>()

  const pushRow = (row: WorkflowLogRow) => {
    const dedupe = `${row.timestamp || ''}:${row.node}:${row.eventType}:${row.message}:${row.tokenCount || ''}:${row.latencyMs || ''}`
    if (seen.has(dedupe)) return
    seen.add(dedupe)
    rows.push(row)
  }

  for (const node of timeline?.nodes || []) {
    if (node.started_at) {
      pushRow({
        id: `node-start:${node.node_name}:${node.started_at}`,
        source: 'timeline',
        timestamp: node.started_at,
        node: node.node_name,
        nodeLabel: node.label || tWorkflowNodeLabel(node.node_name),
        category: 'flow',
        level: node.status === 'failed' || node.status === 'blocked' ? 'error' : 'info',
        eventType: 'node_started',
        message: `${node.label || tWorkflowNodeLabel(node.node_name)} 节点开始执行`,
      })
    }
    if (node.completed_at) {
      const level = logLevelFromStatus(node.status)
      pushRow({
        id: `node-complete:${node.node_name}:${node.completed_at}`,
        source: 'timeline',
        timestamp: node.completed_at,
        node: node.node_name,
        nodeLabel: node.label || tWorkflowNodeLabel(node.node_name),
        category: logCategoryFromEvent('node_completed', level),
        level,
        eventType: 'node_completed',
        message: `${node.label || tWorkflowNodeLabel(node.node_name)} 节点${level === 'error' ? '失败或阻塞' : '执行完成'}`,
        latencyMs: node.duration_ms,
      })
    }
    for (const message of node.messages || []) {
      const level = logLevelFromStatus(node.status)
      pushRow({
        id: `node-message:${node.node_name}:${message}`,
        source: 'timeline',
        timestamp: node.completed_at || node.started_at,
        node: node.node_name,
        nodeLabel: node.label || tWorkflowNodeLabel(node.node_name),
        category: logCategoryFromEvent('node_message', level),
        level,
        eventType: 'node_message',
        message,
      })
    }
    for (const event of node.events || []) {
      const level = logLevelFromStatus(event.status)
      const eventType = event.event_type || 'execution_event'
      pushRow({
        id: `exec:${event.id ?? `${node.node_name}:${eventType}:${event.created_at || ''}`}`,
        source: 'timeline',
        timestamp: event.created_at,
        node: node.node_name,
        nodeLabel: node.label || tWorkflowNodeLabel(node.node_name),
        category: logCategoryFromEvent(eventType, level),
        level,
        eventType,
        message: event.message || eventType,
        payload: event.payload,
        tokenCount: event.token_count,
        latencyMs: event.latency_ms,
      })
    }
  }

  for (const [nodeKey, step] of Object.entries(sseSteps || {})) {
    const nodeLabel = tWorkflowNodeLabel(nodeKey)
    if (step.started_at) {
      pushRow({
        id: `live-start:${nodeKey}:${step.started_at}`,
        source: 'live',
        timestamp: step.started_at,
        node: nodeKey,
        nodeLabel,
        category: 'flow',
        level: step.status === 'failed' ? 'error' : 'info',
        eventType: 'live_node_started',
        message: `${nodeLabel} 节点开始执行`,
      })
    }
    for (const log of step.logs || []) {
      const level = log.level || 'info'
      pushRow({
        id: `live-log:${nodeKey}:${log.id || `${log.timestamp}:${log.message}`}`,
        source: 'live',
        timestamp: log.timestamp,
        node: nodeKey,
        nodeLabel,
        category: logCategoryFromEvent(log.message || 'live_task_log', level),
        level,
        eventType: 'live_task_log',
        message: log.message,
      })
    }
    if (step.completed_at) {
      const level = step.status === 'failed' ? 'error' : 'success'
      pushRow({
        id: `live-complete:${nodeKey}:${step.completed_at}`,
        source: 'live',
        timestamp: step.completed_at,
        node: nodeKey,
        nodeLabel,
        category: logCategoryFromEvent('live_node_completed', level),
        level,
        eventType: 'live_node_completed',
        message: `${nodeLabel} 节点${level === 'error' ? '失败' : '执行完成'}`,
        latencyMs: step.duration_ms,
      })
    }
  }

  for (const step of runDetail?.steps || []) {
    for (const log of step.logs || []) {
      const level = log.level || 'info'
      pushRow({
        id: `step-log:${step.key}:${log.timestamp || ''}:${log.message}`,
        source: 'run_detail',
        timestamp: log.timestamp,
        node: step.key,
        nodeLabel: step.label || tWorkflowNodeLabel(step.key),
        category: logCategoryFromEvent('task_log', level),
        level,
        eventType: 'task_log',
        message: log.message,
      })
    }
    if (step.error_message) {
      pushRow({
        id: `step-error:${step.key}:${step.error_message}`,
        source: 'run_detail',
        timestamp: runDetail?.completed_at || runDetail?.started_at,
        node: step.key,
        nodeLabel: step.label || tWorkflowNodeLabel(step.key),
        category: 'error',
        level: 'error',
        eventType: 'step_error',
        message: step.error_message,
      })
    }
  }

  return rows.sort((a, b) => {
    const ta = a.timestamp ? new Date(a.timestamp.replace(' ', 'T')).getTime() : 0
    const tb = b.timestamp ? new Date(b.timestamp.replace(' ', 'T')).getTime() : 0
    if (Number.isNaN(ta) || Number.isNaN(tb) || ta === tb) return a.id.localeCompare(b.id)
    return ta - tb
  })
}

const CANONICAL_GENERATING_STEPS = [
  { key: 'health_check', label: '预检', node_group: 'system' as const },
  { key: 'task_discovery', label: '任务识别', node_group: 'system' as const },
  { key: 'planner', label: '规划', node_group: 'creative_agent' as const },
  { key: 'screenwriter', label: '编剧', node_group: 'creative_agent' as const },
  { key: 'author', label: '执笔', node_group: 'creative_agent' as const },
  { key: 'polisher', label: '润色', node_group: 'creative_agent' as const },
  { key: 'editor', label: '审核', node_group: 'creative_agent' as const },
  { key: 'memory_curator', label: '记忆整理', node_group: 'support_agent' as const },
  { key: 'publisher', label: '发布', node_group: 'terminal' as const },
  { key: 'awaiting_publish', label: '等待发布', node_group: 'terminal' as const },
  { key: 'archive', label: '归档', node_group: 'terminal' as const },
  { key: 'revision_router', label: '返修路由', node_group: 'router' as const },
  { key: 'human_review', label: '人工审核', node_group: 'terminal' as const },
]

function getGeneratingSteps(sseSteps: Record<string, StepStatus>) {
  const activeKeys = Object.keys(sseSteps)
  if (activeKeys.length === 0) return CANONICAL_GENERATING_STEPS
  const knownKeys = new Set(CANONICAL_GENERATING_STEPS.map((step) => step.key))
  const customSteps = activeKeys
    .filter((key) => key !== 'publish' && !knownKeys.has(key))
    .map((key) => ({ key, label: tWorkflowNodeLabel(key), node_group: 'unknown' as const }))
  return [...CANONICAL_GENERATING_STEPS, ...customSteps]
}

function getGeneratingStepKeys(sseSteps: Record<string, StepStatus>) {
  return getGeneratingSteps(sseSteps).map((step) => step.key)
}

const MISSING_TO_MODULE: Record<string, string> = {
  '项目简介': 'settings',
  '世界观设定': 'worldview',
  '主角角色': 'characters',
  '大纲': 'outline',
  '写作指令': 'instructions',
  '目标字数': 'settings',
}

function getModuleForMissing(item: string): string {
  for (const [label, mod] of Object.entries(MISSING_TO_MODULE)) {
    if (item.startsWith(label) || item === label) return mod
  }
  return 'settings'
}

export interface GenerationErrorDetails {
  missing?: string[]
  actions?: string[]
  hint?: string
  word_count?: number
  chapter_status?: string
}

interface AuthorWritingSurfaceProps {
  activeTab: SurfaceTabKey
  chapterDetail: ChapterDetail | null
  chapterLoading: boolean
  currentChapter: number
  currentChapterRecord: { status: string; word_count: number; title?: string; quality_score?: number } | null
  genError: string
  genErrorDetails: GenerationErrorDetails | null
  isLaunching: boolean
  isStub: boolean
  isStreaming: boolean
  isWorkflowRunning?: boolean
  llmMode: string
  projectId: string
  runDetail: RunDetailData | null
  runsForChapter: Run[]
  sseSteps: Record<string, StepStatus>
  timeline?: WorkflowTimelineData | null
  timelineError?: string
  onGenerate: () => void
  onConfirmRegenerate?: () => void
  onGenerateNext?: () => void
  onMarkRunStuck?: (runId: string) => Promise<void> | void
  onPublish?: () => void
  onResetRunRecovery?: (runId: string) => Promise<void> | void
  onRetryRunNode?: (runId: string) => Promise<void> | void
  onWorkflowDone?: (runId: string, status: string | null) => void
  publishPending?: boolean
  markStuckPending?: boolean
  resetRecoveryPending?: boolean
  regeneratePending?: boolean
  onTabChange: (tab: SurfaceTabKey) => void
  onViewContent: () => void
  onViewWorkflow: (runId: string) => void
  onRefreshContent?: () => void
}

export default function AuthorWritingSurface({
  activeTab,
  chapterDetail,
  chapterLoading,
  currentChapter,
  currentChapterRecord,
  genError,
  genErrorDetails,
  isLaunching,
  isStub,
  isStreaming,
  isWorkflowRunning,
  llmMode,
  projectId,
  runDetail,
  runsForChapter,
  sseSteps,
  timeline,
  timelineError,
  onGenerate,
  onConfirmRegenerate,
  onMarkRunStuck,
  onPublish,
  onResetRunRecovery,
  onRetryRunNode,
  onWorkflowDone,
  publishPending,
  markStuckPending,
  resetRecoveryPending,
  regeneratePending,
  onTabChange,
  onViewContent,
  onViewWorkflow,
  onRefreshContent,
}: AuthorWritingSurfaceProps) {
  const hasContent = (chapterDetail?.word_count || 0) > 0
  const status = currentChapterRecord?.status || ''
  const isTerminal = TERMINAL_CHAPTER_STATUSES.has(status)
  const isReviewedReal = status === 'reviewed' && llmMode === 'real'
  const hasPreservedPlannedContent = status === 'planned' && (currentChapterRecord?.word_count || chapterDetail?.word_count || 0) > 0
  const persistedQualityScore = chapterDetail?.quality_score ?? currentChapterRecord?.quality_score ?? null
  const qualityScore = persistedQualityScore
  const statusLabel = tChapterStatus(status)
  const memoryCuratorNode = timeline?.nodes?.find((node) => node.node_name === 'memory_curator')
  const memoryCuratorRunning = Boolean(
    timeline?.memory_curator_running ||
    memoryCuratorNode?.status === 'running' ||
    (
      timeline?.run_status === 'running' &&
      (timeline.current_node === 'memory_curator' || memoryCuratorNode?.flags?.memory_curator_running)
    )
  )
  const isWorkflowActive = isStreaming || isWorkflowRunning || timeline?.run_status === 'running' || memoryCuratorRunning
  const showHeaderGenerationAction = activeTab !== 'workflow'

  const tabs: { key: SurfaceTabKey; label: string; disabled?: boolean }[] = [
    { key: 'content', label: '正文' },
    { key: 'versions', label: '版本' },
    { key: 'workflow', label: '工作流', disabled: runsForChapter.length === 0 && !isStreaming },
    { key: 'artifacts', label: PROCESS_DRAFT_LABEL },
    { key: 'history', label: '历史', disabled: runsForChapter.length === 0 },
    { key: 'logs', label: '日志', disabled: runsForChapter.length === 0 && !isStreaming },
  ]

  return (
    <main className="author-surface" aria-label="写作区">
      {/* Header */}
      <div className="author-surface-header">
        <div className="author-surface-title">
          <h2>{chapterDetail?.title || `第 ${currentChapter} 章`}</h2>
          <span
            className="author-surface-status"
            style={{
              background: isTerminal
                ? status === 'published'
                  ? 'var(--wb-success-soft)'
                  : 'var(--wb-warning-soft)'
                : 'var(--wb-paper-muted)',
              color: isTerminal
                ? status === 'published'
                  ? 'var(--wb-success)'
                  : 'var(--wb-warning)'
                : 'var(--wb-text-dark-secondary)',
            }}
          >
            {statusLabel}
          </span>
        </div>
        <div className="author-surface-actions">
          {isReviewedReal && onPublish && (
            <LoadingButton
              className="btn btn-primary btn-sm"
              variant="primary"
              loading={!!publishPending}
              loadingText="发布中..."
              onClick={onPublish}
              disabled={isWorkflowActive}
            >
              <CheckCircle2 size={12} /> 确认发布
            </LoadingButton>
          )}
          {showHeaderGenerationAction && hasPreservedPlannedContent && onConfirmRegenerate ? (
            <LoadingButton
              className="btn btn-primary btn-sm"
              variant="primary"
              loading={!!regeneratePending}
              loadingText="确认中..."
              onClick={onConfirmRegenerate}
              disabled={isWorkflowActive}
            >
              <Play size={12} /> 覆盖重生成
            </LoadingButton>
          ) : showHeaderGenerationAction && !isTerminal && (
            <LoadingButton
              className="btn btn-primary btn-sm"
              variant="primary"
              loading={isWorkflowActive}
              loadingText="生成中..."
              onClick={onGenerate}
              disabled={isWorkflowActive}
            >
              <Play size={12} /> 生成本章
            </LoadingButton>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="author-surface-tabs">
        {tabs.map((t) => (
          <button
            key={t.key}
            className={`author-surface-tab${activeTab === t.key ? ' active' : ''}`}
            onClick={() => !t.disabled && onTabChange(t.key)}
            disabled={t.disabled}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="author-readiness-strip" aria-label="章节质量状态">
        <div className="author-readiness-score">
          <span>{qualityScore ?? '—'}</span>
        </div>
        <div className="author-readiness-cell">
          <strong>审核分</strong>
          <span>{qualityScore !== null ? (qualityScore >= 85 ? '优秀' : qualityScore >= 70 ? '稳定' : '待增强') : '待评估'}</span>
        </div>
        <div className="author-readiness-cell">
          <strong>结构</strong>
          <span>{hasContent ? '稳固' : '待生成'}</span>
        </div>
        <div className="author-readiness-cell">
          <strong>风格</strong>
          <span>{hasContent ? '一致' : '未采样'}</span>
        </div>
        <div className="author-readiness-cell">
          <strong>节奏</strong>
          <span>{hasContent ? '可读' : '待评估'}</span>
        </div>
        <div className="author-readiness-state">
          <strong>章节状态</strong>
          <span>{statusLabel}</span>
        </div>
      </div>

      {/* Body */}
      <div className="author-surface-body">
        {activeTab === 'content' && (
          <ContentBody
            chapterDetail={chapterDetail}
            chapterLoading={chapterLoading}
            currentChapter={currentChapter}
            isTerminal={isTerminal}
            genError={genError}
            genErrorDetails={genErrorDetails}
            hasContent={hasContent}
            isStub={isStub}
            isStreaming={isStreaming}
            isWorkflowRunning={isWorkflowRunning}
            projectId={projectId}
            onGenerate={onGenerate}
            onConfirmRegenerate={onConfirmRegenerate}
            onRefreshContent={onRefreshContent}
            regeneratePending={regeneratePending}
          />
        )}
        {activeTab === 'workflow' && (
          <WorkflowBody
            runDetail={runDetail}
            timeline={timeline}
            currentChapterStatus={status}
            timelineError={timelineError}
            isLaunching={isLaunching}
            isStreaming={isStreaming}
            sseSteps={sseSteps}
            onGenerate={onGenerate}
            onConfirmRegenerate={onConfirmRegenerate}
            onMarkRunStuck={onMarkRunStuck}
            onResetRunRecovery={onResetRunRecovery}
            onRetryRunNode={onRetryRunNode}
            onWorkflowDone={onWorkflowDone}
            markStuckPending={markStuckPending}
            resetRecoveryPending={resetRecoveryPending}
            regeneratePending={regeneratePending}
            onTabChange={onTabChange}
            onViewContent={onViewContent}
          />
        )}
        {activeTab === 'artifacts' && (
          <ArtifactsBody runDetail={runDetail} timeline={timeline} timelineError={timelineError} />
        )}
        {activeTab === 'history' && (
          <HistoryBody runsForChapter={runsForChapter} onViewWorkflow={onViewWorkflow} />
        )}
        {activeTab === 'logs' && (
          <LogsBody runDetail={runDetail} timeline={timeline} timelineError={timelineError} sseSteps={sseSteps} />
        )}
        {activeTab === 'versions' && (
          <VersionBody
            projectId={projectId}
            chapterNumber={currentChapter}
            onRestore={() => { onRefreshContent?.() }}
          />
        )}
      </div>
    </main>
  )
}

/* ------------------------------------------------------------------ */
/*  Content Body                                                      */
/* ------------------------------------------------------------------ */

function ContentBody({
  chapterDetail,
  chapterLoading,
  currentChapter,
  isTerminal,
  genError,
  genErrorDetails,
  hasContent,
  isStub,
  isStreaming,
  isWorkflowRunning,
  projectId,
  onGenerate,
  onConfirmRegenerate,
  onRefreshContent,
  regeneratePending,
}: {
  chapterDetail: ChapterDetail | null
  chapterLoading: boolean
  currentChapter: number
  isTerminal: boolean
  genError: string
  genErrorDetails: GenerationErrorDetails | null
  hasContent: boolean
  isStub: boolean
  isStreaming: boolean
  isWorkflowRunning?: boolean
  projectId: string
  onGenerate: () => void
  onConfirmRegenerate?: () => void
  onRefreshContent?: () => void
  regeneratePending?: boolean
}) {
  const { showToast } = useToast()
  const [filling, setFilling] = useState(false)
  const [inlineMsg, setInlineMsg] = useState<{ variant: 'success' | 'danger'; text: string } | null>(null)

  const handleAutoFill = async () => {
    setFilling(true)
    setInlineMsg(null)
    const start = currentChapter
    const end = currentChapter + 9
    try {
      const res = await post<{ filled: boolean; created: Record<string, number>; warnings: string[] }>(
        `/projects/${projectId}/production/auto-fill`,
        { scope: 'missing_context', chapter_start: start, chapter_end: end, confirm: true }
      )
      if (res.ok && res.data) {
        const total = Object.values(res.data.created).reduce((a, b) => a + b, 0)
        const msg = `已自动补齐 ${total} 项资料，请刷新页面查看。`
        setInlineMsg({ variant: 'success', text: msg })
        showToast({ tone: 'success', title: '补齐完成', message: msg })
      } else {
        const msg = res.error?.message || '补齐失败'
        setInlineMsg({ variant: 'danger', text: msg })
        showToast({ tone: 'danger', title: '补齐失败', message: msg })
      }
    } catch {
      const msg = '网络异常，补齐失败'
      setInlineMsg({ variant: 'danger', text: msg })
      showToast({ tone: 'danger', title: '请求失败', message: msg })
    } finally {
      setFilling(false)
    }
  }

  const handleEditorContentSaved = useCallback(() => {
    onRefreshContent?.()
  }, [onRefreshContent])
  const hasExistingContentGuard = genErrorDetails?.hint === 'review_existing_content'

  return (
    <div>
      {isStreaming && (
        <div className="content-generation-banner">
          <Loader2 size={16} className="spin" />
          <div>
            <div className="content-generation-title">正文生成中</div>
            <div className="content-generation-desc">完成后会自动刷新正文内容。</div>
          </div>
        </div>
      )}

      {genError && (
        <AttentionPanel title="生成失败" tone="error" style={{ marginBottom: 16 }}>
          <div>{genError}</div>
          {hasExistingContentGuard && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
              <LoadingButton
                className="btn btn-secondary btn-sm"
                variant="secondary"
                onClick={onRefreshContent}
              >
                <FileText size={12} /> 查看已有正文
              </LoadingButton>
              {onConfirmRegenerate && (
                <LoadingButton
                  className="btn btn-primary btn-sm"
                  variant="primary"
                  loading={!!regeneratePending}
                  loadingText="确认中..."
                  onClick={onConfirmRegenerate}
                >
                  <Sparkles size={12} /> 确认覆盖并重新生成
                </LoadingButton>
              )}
            </div>
          )}
          {genErrorDetails?.missing && genErrorDetails.missing.length > 0 && (
            <ActionHintList title="缺失项">
              {genErrorDetails.missing.map((item, i) => (
                <li key={i}>
                  <Link
                    to={`/projects/${projectId}?module=${getModuleForMissing(item)}`}
                    style={{ color: 'var(--primary)', textDecoration: 'underline' }}
                  >
                    {item}
                  </Link>
                </li>
              ))}
            </ActionHintList>
          )}
          {genErrorDetails?.missing && genErrorDetails.missing.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <LoadingButton
                className="btn btn-primary btn-sm"
                variant="primary"
                loading={filling}
                loadingText="补齐中..."
                onClick={handleAutoFill}
              >
                <Sparkles size={12} /> 让 AI 补齐缺失资料
              </LoadingButton>
              {inlineMsg && (
                <div style={{ marginTop: 8 }}>
                  <InlineMessage variant={inlineMsg.variant}>{inlineMsg.text}</InlineMessage>
                </div>
              )}
            </div>
          )}
          {genErrorDetails?.actions && genErrorDetails.actions.length > 0 && (
            <ActionHintList title="建议操作">
              {genErrorDetails.actions.map((action, i) => (
                <li key={i}>{action}</li>
              ))}
            </ActionHintList>
          )}
        </AttentionPanel>
      )}

      {chapterLoading && !isStreaming && (
        <div style={{ padding: 24 }}>
          <SkeletonStack rows={6} />
        </div>
      )}

      {!chapterLoading && !hasContent && !isStreaming && (
        <div className="author-surface-empty">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, marginBottom: 12 }}>
            <FileText size={24} color="var(--wb-text-dark-muted)" />
          </div>
          <h3>{chapterDetail?.title ? `第 ${currentChapter} 章：${chapterDetail.title}` : `第 ${currentChapter} 章`}</h3>
          <p style={{ fontSize: 14, color: 'var(--wb-text-dark-secondary)', marginTop: 4, marginBottom: 8 }}>
            本章还没有正文内容
          </p>
          <div style={{ fontSize: 13, color: 'var(--wb-text-dark-muted)', lineHeight: 1.6, maxWidth: 420, margin: '0 auto' }}>
            <p style={{ marginBottom: 6 }}>下一步：</p>
            <ul style={{ textAlign: 'left', paddingLeft: 18, margin: 0 }}>
              <li>编剧将规划章节场景和情节</li>
              <li>执笔将撰写章节正文</li>
              <li>润色、审核后生成最终版本</li>
            </ul>
          </div>
          {!isTerminal && (
            <LoadingButton
              className="btn btn-primary"
              variant="primary"
              loading={isWorkflowRunning}
              loadingText="生成中..."
              onClick={onGenerate}
              disabled={isWorkflowRunning}
              style={{ marginTop: 20, minWidth: 160 }}
            >
              <PenLine size={14} /> 生成本章
            </LoadingButton>
          )}
          <div style={{ marginTop: 14, fontSize: 12, color: 'var(--wb-text-dark-muted)' }}>
            预计字数: 2,000-4,000 &middot; 生成模式: {isStub ? '演示模式' : '真实 LLM'}
          </div>
        </div>
      )}

      {!chapterLoading && hasContent && !isStreaming && (
        <>
          <QualityDiagnosisPanel
            projectId={projectId}
            chapterNumber={currentChapter}
            chapterStatus={chapterDetail?.status || ''}
          />
          <ChapterEditorSurface
            projectId={projectId}
            chapterNumber={currentChapter}
            onContentSaved={handleEditorContentSaved}
            initialContent={chapterDetail?.content || ''}
            initialWordCount={chapterDetail?.word_count || 0}
            initialStatus={chapterDetail?.status || ''}
            initialVersionLabel={`更新时间 ${chapterDetail?.updated_at || chapterDetail?.created_at || '-'}`}
          />
        </>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Workflow Body                                                     */
/* ------------------------------------------------------------------ */

function WorkflowBody({
  runDetail,
  timeline,
  currentChapterStatus,
  timelineError,
  isLaunching,
  isStreaming,
  sseSteps,
  onGenerate,
  onConfirmRegenerate,
  onMarkRunStuck,
  onResetRunRecovery,
  onRetryRunNode,
  onWorkflowDone,
  markStuckPending,
  resetRecoveryPending,
  regeneratePending,
  onTabChange,
  onViewContent,
}: {
  runDetail: RunDetailData | null
  timeline?: WorkflowTimelineData | null
  currentChapterStatus: string
  timelineError?: string
  isLaunching: boolean
  isStreaming: boolean
  sseSteps: Record<string, StepStatus>
  onGenerate: () => void
  onConfirmRegenerate?: () => void
  onMarkRunStuck?: (runId: string) => Promise<void> | void
  onResetRunRecovery?: (runId: string) => Promise<void> | void
  onRetryRunNode?: (runId: string) => Promise<void> | void
  onWorkflowDone?: (runId: string, status: string | null) => void
  markStuckPending?: boolean
  resetRecoveryPending?: boolean
  regeneratePending?: boolean
  onTabChange: (tab: SurfaceTabKey) => void
  onViewContent: () => void
}) {
  // v6.1: Connect to SSE stream for live execution events while running
  const isRunActive = timeline?.run_status === 'running'
  const { liveEvents, doneStatus } = useWorkflowStream(
    isRunActive ? timeline?.project_id ?? null : null,
    isRunActive ? timeline?.chapter_number ?? null : null,
    isRunActive ? timeline?.run_id ?? null : null,
    isRunActive,
  )

  useEffect(() => {
    if (doneStatus && timeline?.run_id) {
      onWorkflowDone?.(timeline.run_id, doneStatus)
    }
  }, [doneStatus, onWorkflowDone, timeline?.run_id])

  // v5.8.2: Timeline API is the primary workflow truth when available.
  if (timeline) {
    const nodeLabel = tWorkflowNodeLabel(timeline.current_node)
    const statusLabel = timeline.run_status ? tWorkflowStatus(timeline.run_status) : '—'
    const timelineChapterStatus = timeline.chapter_status || currentChapterStatus || ''
    const incompleteCompletedRun = isCompletedBeforeTerminal(timeline.run_status, timelineChapterStatus)
    const isStale = timeline.is_stale
    const isRunning = timeline.run_status === 'running'

    const statusTone = isStale || incompleteCompletedRun || timeline.run_status === 'blocked' ? 'warning' : timeline.run_status === 'failed' ? 'error' : 'info'
    const statusHeadline = isStale
      ? '工作流疑似卡住'
      : isRunning
        ? '工作流正在推进'
        : timeline.run_status === 'blocked'
          ? '工作流已阻塞'
          : incompleteCompletedRun
            ? '工作流提前结束'
          : timeline.run_status === 'completed'
            ? '工作流已完成'
            : '最近一次运行'
    const statusDescription = isStale
      ? `当前节点：${nodeLabel} 已超过 ${STUCK_RUN_THRESHOLD_MINUTES} 分钟未完成，建议进入运行恢复处理卡住运行。`
      : isRunning
        ? `当前节点：${nodeLabel}，仍在处理。若超过 ${STUCK_RUN_THRESHOLD_MINUTES} 分钟未变化，请按卡住运行处理。`
        : timeline.run_status === 'blocked'
          ? `本次运行已阻塞，需要先处理最近的失败或返修原因。`
          : incompleteCompletedRun
            ? `本次运行没有到达发布终态，章节仍停在 ${tChapterStatus(timelineChapterStatus)}，当前节点：${nodeLabel}。请继续生成或进入运行详情排查。`
          : timeline.run_status === 'completed'
            ? '工作流已完成，可查看产物或继续下一章。'
            : '最近一次运行记录如下。'

    const recovery = timeline.recovery
    const checkpoint = timeline.checkpoint
    const hasExplicitResetAction = recovery.safe_actions.some((action) => action.key === 'reset_explicitly')
    const hasGenerateAction = recovery.safe_actions.some((action) => action.key === 'generate')
    const visibleRecoveryActions = recovery.safe_actions.filter((action) => (
      action.key !== 'view_detail' &&
      !(action.key === 'reset_explicitly' && hasGenerateAction)
    ))
    const recoveryQuickActions = visibleRecoveryActions.filter((action) => action.key === 'view_content' || action.key === 'view_artifacts')
    const recoveryDecisionActions = visibleRecoveryActions
      .filter((action) => action.key !== 'view_content' && action.key !== 'view_artifacts')
      .sort((a, b) => recoveryActionRank(a.key, recovery.recommended_action) - recoveryActionRank(b.key, recovery.recommended_action))
    const shouldShowRecoveryPanel = Boolean(
      recovery.recommended_action &&
      visibleRecoveryActions.length > 0 &&
      !(isRunning && !isStale),
    )

    const renderRecoveryQuickAction = (action: WorkflowTimelineData['recovery']['safe_actions'][number]) => {
      switch (action.key) {
        case 'view_content':
          return (
            <button key={action.key} type="button" className="workflow-recovery-link-button" onClick={onViewContent}>
              {action.label}
            </button>
          )
        case 'view_artifacts':
          return (
            <button key={action.key} type="button" className="workflow-recovery-link-button" onClick={() => onTabChange('artifacts')}>
              {action.label}
            </button>
          )
        default:
          return null
      }
    }

    const renderRecoveryAction = (action: WorkflowTimelineData['recovery']['safe_actions'][number]) => {
      const isRecommended = action.key === recovery.recommended_action || (action.key === 'generate' && recovery.recommended_action === 'reset_explicitly')
      const actionRow = (button: ReactNode, note = action.note) => (
        <div key={action.key} className={`workflow-recovery-action${isRecommended ? ' recommended' : ''}`}>
          {button}
          {note && <span className="workflow-recovery-note">{note}</span>}
        </div>
      )
      const staticHint = (
        <div key={action.key} className="workflow-recovery-hint">
          <span className="workflow-recovery-hint-label">{action.label}</span>
          {action.note && <span className="workflow-recovery-hint-note">{action.note}</span>}
        </div>
      )

      switch (action.key) {
        case 'mark_stuck':
          return onMarkRunStuck && timeline.run_id ? actionRow(
            <LoadingButton
              className="btn btn-secondary btn-sm"
              variant="secondary"
              loading={!!markStuckPending}
              loadingText="处理中..."
              onClick={() => onMarkRunStuck(timeline.run_id!)}
            >
              {action.label}
            </LoadingButton>
          ) : staticHint
        case 'retry_node':
          return onRetryRunNode && timeline.run_id ? actionRow(
            <LoadingButton
              className="btn btn-primary btn-sm"
              variant="primary"
              loading={!!resetRecoveryPending}
              loadingText="处理中..."
              onClick={() => onRetryRunNode(timeline.run_id!)}
            >
              {action.label}
            </LoadingButton>
          ) : staticHint
        case 'reset':
        case 'reset_chapter':
          return onResetRunRecovery && timeline.run_id ? actionRow(
            <LoadingButton
              className="btn btn-secondary btn-sm workflow-recovery-reset-button"
              variant="secondary"
              loading={!!resetRecoveryPending}
              loadingText="处理中..."
              onClick={() => onResetRunRecovery(timeline.run_id!)}
            >
              {action.label}
            </LoadingButton>
          ) : staticHint
        case 'reset_explicitly':
          return onConfirmRegenerate ? actionRow(
            <LoadingButton
              className="btn btn-danger btn-sm"
              variant="danger"
              loading={!!regeneratePending}
              loadingText="确认中..."
              onClick={onConfirmRegenerate}
            >
              覆盖重生成
            </LoadingButton>
          ) : staticHint
        case 'generate': {
          const generateIsContinue = incompleteCompletedRun
          return actionRow(
            <LoadingButton
              className={`btn ${generateIsContinue ? 'btn-primary' : 'btn-danger'} btn-sm`}
              variant={generateIsContinue ? 'primary' : 'danger'}
              loading={!!regeneratePending}
              loadingText="确认中..."
              onClick={hasExplicitResetAction && onConfirmRegenerate ? onConfirmRegenerate : onGenerate}
            >
              {generateIsContinue ? '继续生成' : '覆盖重生成'}
            </LoadingButton>,
            generateIsContinue ? '从当前章节状态继续，不覆盖已保存正文' : '会覆盖当前正文并启动新一轮生成',
          )
        }
        default:
          return staticHint
      }
    }

    // Convert timeline nodes to WorkflowTimeline Step format
    // v6.1: Merge live SSE events into nodes while running
    const liveEventsByNode: Record<string, WorkflowExecutionEvent[]> = {}
    for (const ev of liveEvents) {
      const nodeName = ev.node_name
      if (nodeName) {
        if (!liveEventsByNode[nodeName]) liveEventsByNode[nodeName] = []
        liveEventsByNode[nodeName].push(ev)
      }
    }

    const timelineSteps: Step[] = timeline.nodes.map((n) => {
      const existingEvents = n.events || []
      const live = liveEventsByNode[n.node_name] || []
      const mergedEvents = live.length > 0
        ? mergeWorkflowEvents(existingEvents, live)
        : existingEvents
      return {
        key: n.node_name,
        label: n.label,
        description: n.messages[0] || '',
        node_group: n.node_group,
        node_type: n.node_type,
        status: n.status as Step['status'],
        node_status: n.node_status,
        domain_status: n.domain_status,
        severity: n.severity,
        retryable: n.retryable,
        blocking: n.blocking,
        next_action: n.next_action,
        action_label: n.action_label,
        user_message: n.user_message,
        flags: n.flags,
        logs: n.messages.map((m) => ({ level: 'info' as const, message: m })),
        artifacts: n.artifacts.length > 0 ? {
          summary: n.artifacts.map((a) => a.label).join('、'),
          artifact_labels: n.artifacts.map((a) => a.label),
          artifact_count: n.artifacts.length,
          artifact_types: n.artifacts.map((a) => a.type),
        } : null,
        events: mergedEvents.length > 0 ? mergedEvents : undefined,
        evidence: buildLiveEvidence(mergedEvents, n.evidence),
      }
    })

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {timelineError && (
          <div className="alert alert-error" style={{ marginBottom: 0 }}>
            <div style={{ fontSize: 13 }}>刷新失败：{timelineError}</div>
          </div>
        )}
        <div className={`alert ${statusTone === 'warning' ? 'alert-warn' : statusTone === 'error' ? 'alert-error' : 'alert-info'}`} style={{ marginBottom: 0 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>{statusHeadline}</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>当前节点：{nodeLabel}</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>{statusDescription}</div>
              {timeline.elapsed_minutes !== null && timeline.elapsed_minutes >= 0 && (
                <div style={{ fontSize: 12, color: 'var(--wb-text-muted)', marginTop: 4 }}>
                  已运行约 {Math.round(timeline.elapsed_minutes)} 分钟
                </div>
              )}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'flex-end', gap: 8 }}>
              <span className={`status-badge status-${timeline.run_status || 'unknown'}`}>{statusLabel}</span>
            </div>
          </div>
          {shouldShowRecoveryPanel && (
            <div className="workflow-recovery-panel">
              <div className="workflow-recovery-title">恢复建议</div>
              {recovery.reason && <div className="workflow-recovery-reason">{recovery.reason}</div>}
              {recoveryQuickActions.length > 0 && (
                <div className="workflow-recovery-quick-actions">
                  {recoveryQuickActions.map(renderRecoveryQuickAction)}
                </div>
              )}
              {recoveryDecisionActions.length > 0 && (
                <div className="workflow-recovery-actions">
                  {recoveryDecisionActions.map(renderRecoveryAction)}
                </div>
              )}
            </div>
          )}
        </div>
        <div className="workflow-checkpoint-panel">
          <div className="workflow-checkpoint-item">
            <span>当前节点</span>
            <strong>{nodeLabel}</strong>
          </div>
          <div className="workflow-checkpoint-item">
            <span>运行状态</span>
            <strong>{statusLabel}</strong>
          </div>
          <div className="workflow-checkpoint-item">
            <span>Checkpoint</span>
            <strong>{checkpoint?.checkpoint_exists ? '存在' : '不可用'}</strong>
          </div>
          <div className="workflow-checkpoint-item">
            <span>恢复能力</span>
            <strong>{checkpoint?.recovery_available ? '可从 checkpoint 恢复' : '无 checkpoint 恢复'}</strong>
          </div>
          {(checkpoint?.checkpoint_node || checkpoint?.checkpoint_summary || (checkpoint?.state_keys?.length || 0) > 0) && (
            <div className="workflow-checkpoint-summary">
              {checkpoint?.checkpoint_node && <span>checkpoint 节点：{tWorkflowNodeLabel(checkpoint.checkpoint_node)}</span>}
              {checkpoint?.checkpoint_summary && <span>{checkpoint.checkpoint_summary}</span>}
              {(checkpoint?.state_keys?.length || 0) > 0 && <span>state keys：{checkpoint?.state_keys.slice(0, 8).join('、')}</span>}
            </div>
          )}
        </div>
        <WorkflowTimeline steps={timelineSteps} />
      </div>
    )
  }

  // v5.8: Show timeline error even when no run or timeline data
  if (timelineError && !isStreaming) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="alert alert-error" style={{ marginBottom: 0 }}>
          <div style={{ fontSize: 13 }}>刷新失败：{timelineError}</div>
        </div>
        <div style={{ padding: 24, textAlign: 'center', color: 'var(--wb-text-dark-muted)' }}>
          暂无工作流数据。生成章节后可查看工作流步骤。
        </div>
      </div>
    )
  }

  if (runDetail && !isStreaming) {
    const nodeLabel = tWorkflowNodeLabel(runDetail.current_node)
    const statusLabel = tWorkflowStatus(runDetail.workflow_status)
    const chapterStatusLabel = tChapterStatus(runDetail.chapter_status)
    const elapsedMinutes = elapsedMinutesSince(runDetail.started_at)
    const isStaleRunning = runDetail.workflow_status === 'running' && elapsedMinutes !== null && elapsedMinutes >= STUCK_RUN_THRESHOLD_MINUTES
    const isTerminalChapter = TERMINAL_CHAPTER_STATUSES.has(runDetail.chapter_status)
    const isRunning = runDetail.workflow_status === 'running'
    const isContradictory = isTerminalChapter && isRunning
    const incompleteCompletedRun = isCompletedBeforeTerminal(runDetail.workflow_status, runDetail.chapter_status)
    const statusTone = isContradictory || isStaleRunning || incompleteCompletedRun || runDetail.workflow_status === 'blocked' ? 'warning' : runDetail.workflow_status === 'failed' ? 'error' : 'info'
    const statusHeadline = isContradictory
      ? '状态矛盾：终态章节仍有运行中工作流'
      : isStaleRunning
        ? '工作流疑似卡住'
        : runDetail.workflow_status === 'running'
          ? '工作流正在推进'
          : runDetail.workflow_status === 'blocked'
            ? '工作流已阻塞'
            : incompleteCompletedRun
              ? '工作流提前结束'
            : runDetail.workflow_status === 'completed' && runDetail.chapter_status === 'reviewed'
              ? '审核已完成'
              : '最近一次运行'
    const statusDescription = isContradictory
      ? `本章状态已经是 ${chapterStatusLabel}，但工作流仍在运行。这通常是状态不同步导致的，建议先标记为阻塞，再清除并重置。`
      : isStaleRunning
        ? `当前节点：${nodeLabel} 已超过 ${STUCK_RUN_THRESHOLD_MINUTES} 分钟未完成，建议进入运行恢复处理卡住运行。`
        : runDetail.workflow_status === 'running'
          ? `当前节点：${nodeLabel}，仍在处理。若超过 ${STUCK_RUN_THRESHOLD_MINUTES} 分钟未变化，请按卡住运行处理。`
          : runDetail.workflow_status === 'blocked'
            ? `本次运行已阻塞，需要先处理最近的失败或返修原因。`
            : incompleteCompletedRun
              ? `本次运行没有到达发布终态，章节仍停在 ${chapterStatusLabel}，当前节点：${nodeLabel}。请继续生成或进入运行详情排查。`
            : runDetail.workflow_status === 'completed' && runDetail.chapter_status === 'reviewed'
              ? 'AI 审核已完成，当前等待人工发布。'
              : '最近一次运行记录如下。'

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className={`alert ${statusTone === 'warning' ? 'alert-warn' : statusTone === 'error' ? 'alert-error' : 'alert-info'}`} style={{ marginBottom: 0 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>{statusHeadline}</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>当前节点：{nodeLabel}</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>{statusDescription}</div>
              {isStaleRunning && elapsedMinutes !== null && (
                <div style={{ fontSize: 12, color: 'var(--wb-warning)', marginTop: 4 }}>
                  已运行约 {elapsedMinutes} 分钟，超过卡住阈值 {STUCK_RUN_THRESHOLD_MINUTES} 分钟。
                </div>
              )}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'flex-end', gap: 8 }}>
              <span className={`status-badge status-${runDetail.workflow_status}`}>{statusLabel}</span>
              <span className={`status-badge status-${runDetail.chapter_status}`}>{chapterStatusLabel}</span>
            </div>
          </div>
          {(isStaleRunning || isContradictory || runDetail.chapter_status === 'blocking' || runDetail.chapter_status === 'revision') && (
            <div className="run-detail-recovery-actions">
              {(isStaleRunning || isContradictory) && onMarkRunStuck && (
                <LoadingButton
                  className="btn btn-secondary btn-sm"
                  variant="secondary"
                  loading={!!markStuckPending}
                  loadingText="处理中..."
                  onClick={() => onMarkRunStuck(runDetail.run_id)}
                >
                  标记为阻塞
                </LoadingButton>
              )}
              {(runDetail.chapter_status === 'blocking' || runDetail.chapter_status === 'revision') && onResetRunRecovery && (
                <LoadingButton
                  className="btn btn-primary btn-sm"
                  variant="primary"
                  loading={!!resetRecoveryPending}
                  loadingText="处理中..."
                  onClick={() => onResetRunRecovery(runDetail.run_id)}
                  >
                  清除阻塞并重置
                </LoadingButton>
              )}
              <div className="run-detail-recovery-links">
                {(runDetail.chapter_status === 'blocking' || runDetail.chapter_status === 'revision') && onRetryRunNode && ['author', 'polisher', 'editor'].includes(runDetail.current_node || '') && (
                  <LoadingButton
                    className="btn btn-primary btn-sm"
                    variant="primary"
                    loading={!!resetRecoveryPending}
                    loadingText="处理中..."
                    onClick={() => onRetryRunNode(runDetail.run_id)}
                  >
                    重试当前节点
                  </LoadingButton>
                )}
                <Link to={`/runs/${runDetail.run_id}`} className="btn btn-secondary btn-sm">
                  打开恢复详情
                </Link>
              </div>
            </div>
          )}
        </div>
        <div className="alert alert-warn" style={{ marginBottom: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>Legacy fallback：正在显示运行详情旧版步骤</div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
            工作流时间线暂不可用，此视图可能缺少 memory_curator、awaiting_publish、archive 等 LangGraph 节点。
          </div>
        </div>
        <WorkflowTimeline steps={runDetail.steps} />
      </div>
    )
  }

  if (isLaunching && !isStreaming) {
    return (
      <div style={{ padding: '48px 24px', textAlign: 'center' }}>
        <Loader2 size={24} className="spin" style={{ color: 'var(--wb-accent)', marginBottom: 12 }} />
        <div style={{ fontSize: 15, fontWeight: 500, marginBottom: 6 }}>正在启动生成流程...</div>
        <div style={{ fontSize: 13, color: 'var(--wb-text-dark-muted)' }}>准备章节数据和 AI 模型，即将开始</div>
      </div>
    )
  }

  if (isStreaming) {
    const hasSseData = Object.keys(sseSteps).length > 0
    const stepKeys = getGeneratingStepKeys(sseSteps)
    const steps = getGeneratingSteps(sseSteps).map((s) => {
      const stepStatus = sseSteps[s.key] || (s.key === 'publisher' ? sseSteps.publish : undefined)
      let status: Step['status'] = 'pending'
      let description = '等待中...'
      let logs: Step['logs'] = []
      if (stepStatus) {
        status = stepStatus.status as Step['status']
        if (status === 'running') description = tWorkflowNodeNarrative(s.key)
        else if (status === 'completed') description = `完成 (${stepStatus.duration_ms || 0}ms)`
        else if (status === 'failed') description = '失败'
        logs = stepStatus.logs
      } else if (hasSseData) {
        const currentIndex = stepKeys.findIndex((k) => sseSteps[k]?.status === 'running')
        const myIndex = stepKeys.indexOf(s.key)
        if (currentIndex >= 0 && myIndex > currentIndex) {
          status = 'pending'
          description = '等待中...'
        }
      }
      if (status === 'running' && (!logs || logs.length === 0)) {
        logs = [{ level: 'info', message: tWorkflowNodeNarrative(s.key) }]
      }
      return { key: s.key, label: s.label, node_group: s.node_group, description, status, logs }
    })
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="workflow-running-banner">
          <Loader2 size={16} className="spin" />
          <div>
            <div className="workflow-running-title">工作流运行中</div>
            <div className="workflow-running-desc">每个节点的开始、完成和失败信息会实时写入节点日志。</div>
          </div>
        </div>
        <div className="alert alert-warn" style={{ marginBottom: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>实时事件备用视图</div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
            正在等待工作流时间线刷新，先按 canonical 节点骨架显示实时事件。
          </div>
        </div>
        <WorkflowTimeline steps={steps} />
      </div>
    )
  }

  return (
    <div style={{ padding: 24, textAlign: 'center', color: 'var(--wb-text-dark-muted)' }}>
      暂无工作流数据。生成章节后可查看工作流步骤。
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Artifacts Body                                                    */
/* ------------------------------------------------------------------ */

interface ProcessDraftStep {
  key: string
  label: string
  artifacts: WorkflowArtifacts
}

function ArtifactsBody({
  runDetail,
  timeline,
  timelineError,
}: {
  runDetail: RunDetailData | null
  timeline?: WorkflowTimelineData | null
  timelineError?: string
}) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null)
  const agentMarks: Record<string, string> = {
    planner: '规',
    screenwriter: '编',
    author: '执',
    polisher: '润',
    editor: '审',
    publish: '发',
  }

  const runDetailSteps = runDetail?.steps || []
  const runDetailArtifacts: ProcessDraftStep[] = runDetailSteps
    .filter((step) => step.status === 'completed' && step.artifacts)
    .map((step) => ({
      key: step.key,
      label: step.label,
      artifacts: step.artifacts!,
    }))

  const timelineArtifacts: ProcessDraftStep[] = (timeline?.nodes || [])
    .filter((node) => node.status === 'completed' && node.artifacts && node.artifacts.length > 0)
    .map((node) => ({
      key: node.node_name,
      label: node.label,
      artifacts: {
        artifact_count: node.artifacts.length,
        artifact_labels: node.artifacts.map((artifact) => artifact.label || artifact.type).filter(Boolean),
        artifact_types: node.artifacts.map((artifact) => artifact.type).filter(Boolean),
      },
    }))

  const stepsWithArtifacts = runDetailArtifacts.length > 0 ? runDetailArtifacts : timelineArtifacts

  if (!runDetail && !timeline) {
    return (
      <div className="artifacts-empty">
        <div className="artifacts-empty-icon">{PROCESS_DRAFT_LABEL}</div>
        <div className="artifacts-empty-title">尚未生成章节</div>
        <div className="artifacts-empty-desc">生成章节后，可在此查看每一步 AI 的中间结果，例如分场大纲、初稿、润色稿和审稿意见。</div>
      </div>
    )
  }

  if (stepsWithArtifacts.length === 0) {
    return (
      <div className="artifacts-empty">
        <div className="artifacts-empty-icon">{PROCESS_DRAFT_LABEL}</div>
        <div className="artifacts-empty-title">暂无过程稿数据</div>
        <div className="artifacts-empty-desc">
          {timelineError ? `刷新失败：${timelineError}` : '当前章节尚未完成生成流程，完成后可查看过程稿。'}
        </div>
      </div>
    )
  }

  return (
    <div className="artifacts-grid">
      {stepsWithArtifacts.map((step) => {
        const isExpanded = expandedKey === step.key
        const mark = agentMarks[step.key] || '文'
        const title = getArtifactTitle(step.key, step.label)
        const summary = formatArtifactSummary(step.artifacts)
        return (
          <div key={step.key} className="artifact-card">
            <div className="artifact-header">
              <span className="artifact-icon">{mark}</span>
              <span className="artifact-label">{title}</span>
              <span className="artifact-status">{'✓'}</span>
            </div>
            <div className="artifact-summary">{summary}</div>
            {step.artifacts!.output_preview && (
              <div className="artifact-preview-section">
                {isExpanded ? (
                  <div className="artifact-preview-expanded">
                    <div className="preview-content">{step.artifacts!.output_preview}</div>
                    <button className="preview-toggle" onClick={() => setExpandedKey(null)}>收起</button>
                  </div>
                ) : (
                  <button className="preview-toggle" onClick={() => setExpandedKey(step.key)}>展开内容预览</button>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  History Body                                                      */
/* ------------------------------------------------------------------ */

function HistoryBody({
  runsForChapter,
  onViewWorkflow,
}: {
  runsForChapter: Run[]
  onViewWorkflow: (runId: string) => void
}) {
  if (runsForChapter.length === 0) {
    return (
      <div style={{ padding: 24, textAlign: 'center', color: 'var(--wb-text-dark-muted)' }}>
        暂无运行历史。生成章节后可查看记录。
      </div>
    )
  }
  return (
    <div>
      {runsForChapter.map((run) => (
        <div key={run.run_id} className="history-item">
          <div className="history-item-left">
            <span className={`status-badge status-${run.status}`}>{tWorkflowStatus(run.status)}</span>
            <span className="history-item-time">{run.created_at}</span>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={() => onViewWorkflow(run.run_id)}>
            查看工作流
          </button>
        </div>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Logs Body                                                         */
/* ------------------------------------------------------------------ */

function LogsBody({
  runDetail,
  timeline,
  timelineError,
  sseSteps,
}: {
  runDetail: RunDetailData | null
  timeline?: WorkflowTimelineData | null
  timelineError?: string
  sseSteps?: Record<string, StepStatus>
}) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [jsonExpanded, setJsonExpanded] = useState(false)
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle')
  const rows = buildWorkflowLogRows(runDetail, timeline, sseSteps)
  const runId = timeline?.run_id || runDetail?.run_id
  const runStatus = timeline?.run_status || runDetail?.workflow_status
  const currentNode = timeline?.current_node || runDetail?.current_node
  const totalTokens = runDetail?.total_tokens || rows.reduce((sum, row) => sum + (row.tokenCount || 0), 0)
  const revisionCount = rows.filter((row) => row.category === 'revision').length
  const warningCount = rows.filter((row) => row.level === 'warning' || row.level === 'error').length
  const jsonList = buildWorkflowLogJsonList(rows, runDetail, timeline)

  const handleCopyJson = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(jsonList)
      setCopyState('copied')
      window.setTimeout(() => setCopyState('idle'), 1600)
    } catch {
      setCopyState('failed')
      setJsonExpanded(true)
      window.setTimeout(() => setCopyState('idle'), 2200)
    }
  }, [jsonList])

  if (!runDetail && !timeline && rows.length === 0) {
    return (
      <div className="artifacts-empty">
        <div className="artifacts-empty-icon">日志</div>
        <div className="artifacts-empty-title">暂无工作流日志</div>
        <div className="artifacts-empty-desc">生成章节后，可在此查看 agent 工作日志、节点流转、返修原因和质量门 payload。</div>
      </div>
    )
  }

  return (
    <div className="workflow-log-view">
      {timelineError && (
        <div className="alert alert-error" style={{ marginBottom: 0 }}>
          <div style={{ fontSize: 13 }}>刷新失败：{timelineError}</div>
        </div>
      )}

      <div className="workflow-log-summary">
        <div>
          <span>运行 ID</span>
          <strong title={runId || undefined}>{runId ? runId.slice(0, 8) : '—'}</strong>
        </div>
        <div>
          <span>状态</span>
          <strong>{runStatus ? tWorkflowStatus(runStatus) : '—'}</strong>
        </div>
        <div>
          <span>当前节点</span>
          <strong>{tWorkflowNodeLabel(currentNode)}</strong>
        </div>
        <div>
          <span>日志</span>
          <strong>{rows.length}</strong>
        </div>
        <div>
          <span>返修</span>
          <strong>{revisionCount}</strong>
        </div>
        <div>
          <span>告警</span>
          <strong>{warningCount}</strong>
        </div>
        <div>
          <span>Tokens</span>
          <strong>{totalTokens || '—'}</strong>
        </div>
      </div>

      {rows.length > 0 && (
        <div className="workflow-log-export" aria-label="可复制 JSON 日志">
          <div className="workflow-log-export-head">
            <div>
              <strong>JSON list</strong>
              <span>可直接复制给排查人员，包含 run、节点、事件、tokens、耗时和 payload。</span>
            </div>
            <div className="workflow-log-export-actions">
              <button type="button" className="btn btn-secondary btn-sm" onClick={handleCopyJson}>
                {copyState === 'copied' ? '已复制' : copyState === 'failed' ? '复制失败' : '复制 JSON'}
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setJsonExpanded((prev) => !prev)}
              >
                {jsonExpanded ? '收起 JSON' : '展开 JSON'}
              </button>
            </div>
          </div>
          {jsonExpanded && <pre>{jsonList}</pre>}
        </div>
      )}

      {rows.length === 0 ? (
        <div className="artifacts-empty">
          <div className="artifacts-empty-icon">日志</div>
          <div className="artifacts-empty-title">日志尚未写入</div>
          <div className="artifacts-empty-desc">当前运行没有可展示的节点日志或 agent 执行事件。</div>
        </div>
      ) : (
        <div className="workflow-log-list" aria-label="工作流详细日志">
          {rows.map((row) => {
            const payloadText = formatLogPayload(row.payload)
            const isExpanded = !!expanded[row.id]
            return (
              <div key={row.id} className={`workflow-log-row ${row.level}`}>
                <div className="workflow-log-time">{row.timestamp || '—'}</div>
                <div className="workflow-log-main">
                  <div className="workflow-log-head">
                    <span className={`workflow-log-level ${row.level}`}>{logLevelLabel(row.level)}</span>
                    <span className="workflow-log-category">{logCategoryLabel(row.category)}</span>
                    <span className="workflow-log-node">{row.nodeLabel}</span>
                    <span className="workflow-log-event">{row.eventType}</span>
                  </div>
                  <div className="workflow-log-message">{row.message}</div>
                  {(row.tokenCount || row.latencyMs) && (
                    <div className="workflow-log-metrics">
                      {row.tokenCount ? <span>{row.tokenCount} tokens</span> : null}
                      {row.latencyMs ? <span>{(row.latencyMs / 1000).toFixed(1)}s</span> : null}
                    </div>
                  )}
                  {payloadText && (
                    <div className="workflow-log-payload">
                      <button
                        type="button"
                        className="workflow-log-payload-toggle"
                        onClick={() => setExpanded((prev) => ({ ...prev, [row.id]: !prev[row.id] }))}
                      >
                        {isExpanded ? '收起 payload' : '展开 payload'}
                      </button>
                      {isExpanded && <pre>{payloadText}</pre>}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Version Body (v5.7)                                               */
/* ------------------------------------------------------------------ */

function VersionBody({
  projectId,
  chapterNumber,
  onRestore,
}: {
  projectId: string
  chapterNumber: number
  onRestore?: () => void
}) {
  const [diffLeftId, setDiffLeftId] = useState<number | null>(null)
  const [diffRightId, setDiffRightId] = useState<number | null>(null)

  const handleViewDiff = useCallback((leftId: number, rightId: number) => {
    setDiffLeftId(leftId)
    setDiffRightId(rightId)
  }, [])

  return (
    <div style={{ padding: '0 4px' }}>
      {diffLeftId !== null && diffRightId !== null ? (
        <div>
          <ChapterDiffViewer
            projectId={projectId}
            chapterNumber={chapterNumber}
            leftVersionId={diffLeftId}
            rightVersionId={diffRightId}
            onClose={() => { setDiffLeftId(null); setDiffRightId(null) }}
          />
        </div>
      ) : (
        <ChapterVersionPanel
          projectId={projectId}
          chapterNumber={chapterNumber}
          onRestore={onRestore}
          onViewDiff={handleViewDiff}
        />
      )}
    </div>
  )
}
