import { useState, useCallback, useEffect } from 'react'
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
import { PROCESS_DRAFT_LABEL, formatArtifactSummary, getArtifactTitle } from '../../lib/artifacts'
import { LoadingButton, SkeletonStack, InlineMessage, useToast } from '../ui'
import AttentionPanel, { ActionHintList } from '../AttentionPanel'
import WorkflowTimeline from '../WorkflowTimeline'
import ChapterVersionPanel from './ChapterVersionPanel'
import ChapterDiffViewer from './ChapterDiffViewer'
import ChapterEditorSurface from './ChapterEditorSurface'
import QualityDiagnosisPanel from './QualityDiagnosisPanel'

export type SurfaceTabKey = 'content' | 'workflow' | 'artifacts' | 'history' | 'versions'

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

const STUCK_RUN_THRESHOLD_MINUTES = 30

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
  onViewContent: _onViewContent,
  onViewWorkflow,
  onRefreshContent,
}: AuthorWritingSurfaceProps) {
  void _onViewContent
  const hasContent = (chapterDetail?.word_count || 0) > 0
  const status = currentChapterRecord?.status || ''
  const isTerminal = ['reviewed', 'awaiting_publish', 'published'].includes(status)
  const isReviewedReal = status === 'reviewed' && llmMode === 'real'
  const hasPreservedPlannedContent = status === 'planned' && (currentChapterRecord?.word_count || chapterDetail?.word_count || 0) > 0
  const persistedQualityScore = chapterDetail?.quality_score ?? currentChapterRecord?.quality_score ?? null
  const qualityScore = persistedQualityScore
  const statusLabel = tChapterStatus(status)

  const tabs: { key: SurfaceTabKey; label: string; disabled?: boolean }[] = [
    { key: 'content', label: '正文' },
    { key: 'versions', label: '版本' },
    { key: 'workflow', label: '工作流', disabled: runsForChapter.length === 0 && !isStreaming },
    { key: 'artifacts', label: PROCESS_DRAFT_LABEL },
    { key: 'history', label: '历史', disabled: runsForChapter.length === 0 },
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
              disabled={isStreaming || isWorkflowRunning}
            >
              <CheckCircle2 size={12} /> 确认发布
            </LoadingButton>
          )}
          {hasPreservedPlannedContent && onConfirmRegenerate ? (
            <LoadingButton
              className="btn btn-primary btn-sm"
              variant="primary"
              loading={!!regeneratePending}
              loadingText="确认中..."
              onClick={onConfirmRegenerate}
              disabled={isStreaming || isWorkflowRunning}
            >
              <Play size={12} /> 覆盖重生成
            </LoadingButton>
          ) : !isTerminal && (
            <LoadingButton
              className="btn btn-primary btn-sm"
              variant="primary"
              loading={isStreaming || isWorkflowRunning}
              loadingText="生成中..."
              onClick={onGenerate}
              disabled={isStreaming || isWorkflowRunning}
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
          <strong>质量</strong>
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
          <strong>发布就绪</strong>
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
            timelineError={timelineError}
            isLaunching={isLaunching}
            isStreaming={isStreaming}
            sseSteps={sseSteps}
            onMarkRunStuck={onMarkRunStuck}
            onResetRunRecovery={onResetRunRecovery}
            onRetryRunNode={onRetryRunNode}
            onWorkflowDone={onWorkflowDone}
            markStuckPending={markStuckPending}
            resetRecoveryPending={resetRecoveryPending}
          />
        )}
        {activeTab === 'artifacts' && (
          <ArtifactsBody runDetail={runDetail} />
        )}
        {activeTab === 'history' && (
          <HistoryBody runsForChapter={runsForChapter} onViewWorkflow={onViewWorkflow} />
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
  timelineError,
  isLaunching,
  isStreaming,
  sseSteps,
  onMarkRunStuck,
  onResetRunRecovery,
  onRetryRunNode,
  onWorkflowDone,
  markStuckPending,
  resetRecoveryPending,
}: {
  runDetail: RunDetailData | null
  timeline?: WorkflowTimelineData | null
  timelineError?: string
  isLaunching: boolean
  isStreaming: boolean
  sseSteps: Record<string, StepStatus>
  onMarkRunStuck?: (runId: string) => Promise<void> | void
  onResetRunRecovery?: (runId: string) => Promise<void> | void
  onRetryRunNode?: (runId: string) => Promise<void> | void
  onWorkflowDone?: (runId: string, status: string | null) => void
  markStuckPending?: boolean
  resetRecoveryPending?: boolean
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
    const isStale = timeline.is_stale
    const isRunning = timeline.run_status === 'running'

    const statusTone = isStale || timeline.run_status === 'blocked' ? 'warning' : timeline.run_status === 'failed' ? 'error' : 'info'
    const statusHeadline = isStale
      ? '工作流疑似卡住'
      : isRunning
        ? '工作流正在推进'
        : timeline.run_status === 'blocked'
          ? '工作流已阻塞'
          : timeline.run_status === 'completed'
            ? '工作流已完成'
            : '最近一次运行'
    const statusDescription = isStale
      ? `当前节点：${nodeLabel} 已超过 ${STUCK_RUN_THRESHOLD_MINUTES} 分钟未完成，建议进入运行恢复处理卡住运行。`
      : isRunning
        ? `当前节点：${nodeLabel}，仍在处理。若超过 ${STUCK_RUN_THRESHOLD_MINUTES} 分钟未变化，请按卡住运行处理。`
        : timeline.run_status === 'blocked'
          ? `本次运行已阻塞，需要先处理最近的失败或返修原因。`
          : timeline.run_status === 'completed'
            ? '工作流已完成，可查看产物或继续下一章。'
            : '最近一次运行记录如下。'

    const recovery = timeline.recovery
    const checkpoint = timeline.checkpoint

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
          {recovery.recommended_action && recovery.safe_actions.length > 0 && (
            <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid rgba(0,0,0,0.06)' }}>
              <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 6 }}>恢复建议：{recovery.reason}</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {recovery.safe_actions.map((action) => (
                  <span key={action.key} style={{ fontSize: 12, color: 'var(--text-secondary)', padding: '2px 8px', background: 'var(--bg-tertiary)', borderRadius: 4 }}>
                    {action.label}
                    {action.note && <span style={{ color: 'var(--text-muted)', marginLeft: 4 }}>({action.note})</span>}
                  </span>
                ))}
              </div>
            </div>
          )}
          {(isStale || recovery.recommended_action === 'mark_stuck') && onMarkRunStuck && timeline.run_id && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
              <LoadingButton
                className="btn btn-secondary btn-sm"
                variant="secondary"
                loading={!!markStuckPending}
                loadingText="处理中..."
                onClick={() => onMarkRunStuck(timeline.run_id!)}
              >
                标记为阻塞
              </LoadingButton>
              {onResetRunRecovery && (
                <LoadingButton
                  className="btn btn-primary btn-sm"
                  variant="primary"
                  loading={!!resetRecoveryPending}
                  loadingText="处理中..."
                  onClick={() => onResetRunRecovery(timeline.run_id!)}
                >
                  清除阻塞并重置
                </LoadingButton>
              )}
            </div>
          )}
          {recovery.recommended_action === 'retry_node' && onRetryRunNode && timeline.run_id && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
              <LoadingButton
                className="btn btn-primary btn-sm"
                variant="primary"
                loading={!!resetRecoveryPending}
                loadingText="处理中..."
                onClick={() => onRetryRunNode(timeline.run_id!)}
              >
                {recovery.safe_actions.find((a) => a.key === 'retry_node')?.label || '重试当前节点'}
              </LoadingButton>
              {onResetRunRecovery && (
                <LoadingButton
                  className="btn btn-secondary btn-sm"
                  variant="secondary"
                  loading={!!resetRecoveryPending}
                  loadingText="处理中..."
                  onClick={() => onResetRunRecovery(timeline.run_id!)}
                >
                  完整重置
                </LoadingButton>
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
    const isTerminalChapter = ['published', 'awaiting_publish', 'reviewed'].includes(runDetail.chapter_status)
    const isRunning = runDetail.workflow_status === 'running'
    const isContradictory = isTerminalChapter && isRunning
    const statusTone = isContradictory || isStaleRunning || runDetail.workflow_status === 'blocked' ? 'warning' : runDetail.workflow_status === 'failed' ? 'error' : 'info'
    const statusHeadline = isContradictory
      ? '状态矛盾：终态章节仍有运行中工作流'
      : isStaleRunning
        ? '工作流疑似卡住'
        : runDetail.workflow_status === 'running'
          ? '工作流正在推进'
          : runDetail.workflow_status === 'blocked'
            ? '工作流已阻塞'
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
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
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

function ArtifactsBody({ runDetail }: { runDetail: RunDetailData | null }) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null)
  const agentMarks: Record<string, string> = {
    planner: '规',
    screenwriter: '编',
    author: '执',
    polisher: '润',
    editor: '审',
    publish: '发',
  }

  if (!runDetail) {
    return (
      <div className="artifacts-empty">
        <div className="artifacts-empty-icon">{PROCESS_DRAFT_LABEL}</div>
        <div className="artifacts-empty-title">尚未生成章节</div>
        <div className="artifacts-empty-desc">生成章节后，可在此查看每一步 AI 的中间结果，例如分场大纲、初稿、润色稿和审稿意见。</div>
      </div>
    )
  }

  const stepsWithArtifacts = runDetail.steps.filter((step) => step.status === 'completed' && step.artifacts)
  if (stepsWithArtifacts.length === 0) {
    return (
      <div className="artifacts-empty">
        <div className="artifacts-empty-icon">{PROCESS_DRAFT_LABEL}</div>
        <div className="artifacts-empty-title">暂无过程稿数据</div>
        <div className="artifacts-empty-desc">当前章节尚未完成生成流程，完成后可查看过程稿。</div>
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
