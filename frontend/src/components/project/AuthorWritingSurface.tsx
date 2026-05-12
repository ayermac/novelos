import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Sparkles,
  Loader2,
  Play,
  CheckCircle2,
} from 'lucide-react'
import { StepStatus } from '../../hooks/useSSEStream'
import { tWorkflowNodeLabel } from '../../lib/state-labels'
import { tWorkflowStatus, tChapterStatus } from '../../lib/i18n'
import { post } from '../../lib/api'
import AttentionPanel, { ActionHintList } from '../AttentionPanel'
import WorkflowTimeline from '../WorkflowTimeline'

export type SurfaceTabKey = 'content' | 'workflow' | 'artifacts' | 'history'

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
  status: 'pending' | 'running' | 'completed' | 'failed' | 'blocked'
  error_message?: string
  artifacts?: {
    summary: string
    output_preview?: string
    [key: string]: unknown
  } | null
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

const GENERATING_STEPS = [
  { key: 'screenwriter', label: '编剧' },
  { key: 'author', label: '执笔' },
  { key: 'polisher', label: '润色' },
  { key: 'editor', label: '审核' },
  { key: 'publish', label: '发布' },
]

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

interface AuthorWritingSurfaceProps {
  activeTab: SurfaceTabKey
  chapterDetail: ChapterDetail | null
  chapterLoading: boolean
  currentChapter: number
  currentChapterRecord: { status: string; word_count: number; title?: string } | null
  genError: string
  genErrorDetails: { missing?: string[]; actions?: string[] } | null
  isLaunching: boolean
  isStub: boolean
  isStreaming: boolean
  isWorkflowRunning?: boolean
  llmMode: string
  projectId: string
  runDetail: RunDetailData | null
  runsForChapter: Run[]
  sseSteps: Record<string, StepStatus>
  onGenerate: () => void
  onGenerateNext?: () => void
  onPublish?: () => void
  onTabChange: (tab: SurfaceTabKey) => void
  onViewContent: () => void
  onViewWorkflow: (runId: string) => void
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
  onGenerate,
  onGenerateNext,
  onPublish,
  onTabChange,
  onViewWorkflow,
}: AuthorWritingSurfaceProps) {
  const hasContent = (chapterDetail?.word_count || 0) > 0
  const status = currentChapterRecord?.status || ''
  const isTerminal = ['reviewed', 'awaiting_publish', 'published'].includes(status)
  const isReviewedReal = status === 'reviewed' && llmMode === 'real'

  const tabs: { key: SurfaceTabKey; label: string; disabled?: boolean }[] = [
    { key: 'content', label: '正文' },
    { key: 'workflow', label: '工作流', disabled: runsForChapter.length === 0 && !isStreaming },
    { key: 'artifacts', label: '产物' },
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
                  ? '#d1fae5'
                  : '#fef3c7'
                : '#dbeafe',
              color: isTerminal
                ? status === 'published'
                  ? '#065f46'
                  : '#92400e'
                : '#1e40af',
            }}
          >
            {tChapterStatus(status)}
          </span>
        </div>
        <div className="author-surface-actions">
          {isReviewedReal && onPublish && (
            <button className="btn btn-primary btn-sm" onClick={onPublish}>
              <CheckCircle2 size={12} /> 确认发布
            </button>
          )}
          {status === 'published' && onGenerateNext && (
            <button className="btn btn-primary btn-sm" onClick={onGenerateNext}>
              <Sparkles size={12} /> 生成下一章
            </button>
          )}
          {!isTerminal && (
            <button
              className="btn btn-primary btn-sm"
              onClick={onGenerate}
              disabled={isStreaming || isWorkflowRunning}
            >
              {isStreaming || isWorkflowRunning ? (
                <><Loader2 size={12} className="spin" /> 生成中...</>
              ) : (
                <><Play size={12} /> 生成本章</>
              )}
            </button>
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
            sseSteps={sseSteps}
            onGenerate={onGenerate}
          />
        )}
        {activeTab === 'workflow' && (
          <WorkflowBody
            runDetail={runDetail}
            isLaunching={isLaunching}
            isStreaming={isStreaming}
            sseSteps={sseSteps}
          />
        )}
        {activeTab === 'artifacts' && (
          <ArtifactsBody runDetail={runDetail} />
        )}
        {activeTab === 'history' && (
          <HistoryBody runsForChapter={runsForChapter} onViewWorkflow={onViewWorkflow} />
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
  sseSteps,
  onGenerate,
}: {
  chapterDetail: ChapterDetail | null
  chapterLoading: boolean
  currentChapter: number
  isTerminal: boolean
  genError: string
  genErrorDetails: { missing?: string[]; actions?: string[] } | null
  hasContent: boolean
  isStub: boolean
  isStreaming: boolean
  isWorkflowRunning?: boolean
  projectId: string
  sseSteps: Record<string, StepStatus>
  onGenerate: () => void
}) {
  const [filling, setFilling] = useState(false)
  const [fillMsg, setFillMsg] = useState('')

  const handleAutoFill = async () => {
    setFilling(true)
    setFillMsg('')
    const start = currentChapter
    const end = currentChapter + 9
    const res = await post<{ filled: boolean; created: Record<string, number>; warnings: string[] }>(
      `/projects/${projectId}/production/auto-fill`,
      { scope: 'missing_context', chapter_start: start, chapter_end: end, confirm: true }
    )
    if (res.ok && res.data) {
      const total = Object.values(res.data.created).reduce((a, b) => a + b, 0)
      setFillMsg(`已自动补齐 ${total} 项资料，请刷新页面查看。`)
    } else {
      setFillMsg(res.error?.message || '补齐失败')
    }
    setFilling(false)
  }

  const getStepStatusText = (status: StepStatus, index: number): string => {
    if (status.status === 'running') return '处理中...'
    if (status.status === 'completed') return `完成 (${status.duration_ms || 0}ms)`
    if (status.status === 'failed') return '失败'
    const stepKeys = ['screenwriter', 'author', 'polisher', 'editor', 'publish']
    const currentRunningIndex = stepKeys.findIndex((k) => sseSteps[k]?.status === 'running')
    if (currentRunningIndex >= 0 && index > currentRunningIndex) return '等待中...'
    return '等待中...'
  }

  return (
    <div>
      {isStreaming && (
        <div style={{ marginBottom: 16 }}>
          {GENERATING_STEPS.map((step, i) => {
            const stepStatus = sseSteps[step.key]
            const isActive = stepStatus?.status === 'running'
            const isCompleted = stepStatus?.status === 'completed'
            const isFailed = stepStatus?.status === 'failed'
            const statusText = stepStatus ? getStepStatusText(stepStatus, i) : '等待中...'
            return (
              <div
                key={step.key}
                className={`gen-step ${isActive ? 'gen-step-active' : ''} ${isCompleted ? 'gen-step-complete' : ''} ${isFailed ? 'gen-step-failed' : ''}`}
              >
                <div className="gen-step-icon">
                  {isCompleted ? '✓' : isFailed ? '✗' : '●'}
                </div>
                <div className="gen-step-label">{step.label} &mdash; {statusText}</div>
              </div>
            )
          })}
        </div>
      )}

      {genError && (
        <AttentionPanel title="生成失败" tone="error" style={{ marginBottom: 16 }}>
          <div>{genError}</div>
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
              <button className="btn btn-primary btn-sm" onClick={handleAutoFill} disabled={filling}>
                {filling ? <><Loader2 size={12} className="spin" /> 补齐中...</> : <><Sparkles size={12} /> 让 AI 补齐缺失资料</>}
              </button>
              {fillMsg && (
                <div style={{ marginTop: 6, fontSize: 12, color: fillMsg.includes('失败') ? '#dc2626' : '#16a34a' }}>
                  {fillMsg}
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
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>加载中...</div>
      )}

      {!chapterLoading && !hasContent && !isStreaming && (
        <div className="author-surface-empty">
          <h3>第 {currentChapter} 章</h3>
          {chapterDetail?.title && <p style={{ fontSize: 16, color: 'var(--text-secondary)', marginBottom: 8 }}>{chapterDetail.title}</p>}
          <p>本章尚未生成</p>
          <p style={{ fontSize: 13 }}>编剧将规划章节场景和情节，执笔将撰写章节正文</p>
          {!isTerminal && (
            <button className="btn btn-primary" onClick={onGenerate} style={{ marginTop: 16 }} disabled={isWorkflowRunning}>
              {isWorkflowRunning ? '生成中...' : '生成本章'}
            </button>
          )}
          <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-muted)' }}>
            预计字数: 2,000-4,000 &middot; 生成模式: {isStub ? '演示模式' : '真实 LLM'}
          </div>
        </div>
      )}

      {!chapterLoading && hasContent && (
        <div>
          {isStub && (
            <div className="alert alert-warn" style={{ marginBottom: 12 }}>
              <strong>演示正文</strong>
              <div style={{ marginTop: 4, fontSize: 13 }}>
                本章为演示模式生成内容，由本地 Stub 模板生成，不代表真实创作质量。
              </div>
            </div>
          )}
          <div className="chapter-meta">
            <span>来源: {isStub ? '演示' : '真实'}</span>
            <span>字数: {(chapterDetail?.word_count || 0).toLocaleString()}</span>
            <span>生成时间: {chapterDetail?.updated_at || chapterDetail?.created_at || '-'}</span>
          </div>
          <h2 className="chapter-content-title">{chapterDetail?.title || `第 ${currentChapter} 章`}</h2>
          <div className="chapter-content-body">{chapterDetail?.content || ''}</div>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Workflow Body                                                     */
/* ------------------------------------------------------------------ */

function WorkflowBody({
  runDetail,
  isLaunching,
  isStreaming,
  sseSteps,
}: {
  runDetail: RunDetailData | null
  isLaunching: boolean
  isStreaming: boolean
  sseSteps: Record<string, StepStatus>
}) {
  if (runDetail && !isStreaming) {
    const nodeLabel = tWorkflowNodeLabel(runDetail.current_node)
    const statusLabel = tWorkflowStatus(runDetail.workflow_status)
    const chapterStatusLabel = tChapterStatus(runDetail.chapter_status)
    const elapsedMinutes = elapsedMinutesSince(runDetail.started_at)
    const isStaleRunning = runDetail.workflow_status === 'running' && elapsedMinutes !== null && elapsedMinutes >= STUCK_RUN_THRESHOLD_MINUTES
    const statusTone = isStaleRunning || runDetail.workflow_status === 'blocked' ? 'warning' : runDetail.workflow_status === 'failed' ? 'error' : 'info'
    const statusHeadline = isStaleRunning
      ? '工作流疑似卡住'
      : runDetail.workflow_status === 'running'
        ? '工作流正在推进'
      : runDetail.workflow_status === 'blocked'
        ? '工作流已阻塞'
        : runDetail.workflow_status === 'completed' && runDetail.chapter_status === 'reviewed'
          ? '审核已完成'
          : '最近一次运行'
    const statusDescription = isStaleRunning
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
                <div style={{ fontSize: 12, color: '#92400e', marginTop: 4 }}>
                  已运行约 {elapsedMinutes} 分钟，超过卡住阈值 {STUCK_RUN_THRESHOLD_MINUTES} 分钟。
                </div>
              )}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              <span className={`status-badge status-${runDetail.workflow_status}`}>{statusLabel}</span>
              <span className={`status-badge status-${runDetail.chapter_status}`}>{chapterStatusLabel}</span>
            </div>
          </div>
        </div>
        <WorkflowTimeline steps={runDetail.steps} />
      </div>
    )
  }

  if (isLaunching && !isStreaming) {
    return (
      <div style={{ padding: '48px 24px', textAlign: 'center' }}>
        <Loader2 size={24} className="spin" style={{ color: 'var(--primary)', marginBottom: 12 }} />
        <div style={{ fontSize: 15, fontWeight: 500, marginBottom: 6 }}>正在启动生成流程...</div>
        <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>准备章节数据和 AI 模型，即将开始</div>
      </div>
    )
  }

  if (isStreaming) {
    const hasSseData = Object.keys(sseSteps).length > 0
    const stepKeys = ['screenwriter', 'author', 'polisher', 'editor', 'publish']
    const steps = GENERATING_STEPS.map((s) => {
      const stepStatus = sseSteps[s.key]
      let status: Step['status'] = 'pending'
      let description = '等待中...'
      if (stepStatus) {
        status = stepStatus.status as Step['status']
        if (status === 'running') description = '处理中...'
        else if (status === 'completed') description = `完成 (${stepStatus.duration_ms || 0}ms)`
        else if (status === 'failed') description = '失败'
      } else if (hasSseData) {
        const currentIndex = stepKeys.findIndex((k) => sseSteps[k]?.status === 'running')
        const myIndex = stepKeys.indexOf(s.key)
        if (currentIndex >= 0 && myIndex > currentIndex) {
          status = 'pending'
          description = '等待中...'
        }
      }
      return { key: s.key, label: s.label, description, status }
    })
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {steps.map((step) => (
          <div
            key={step.key}
            className={`gen-step ${step.status === 'running' ? 'gen-step-active' : ''} ${step.status === 'completed' ? 'gen-step-complete' : ''} ${step.status === 'failed' ? 'gen-step-failed' : ''}`}
          >
            <div className="gen-step-icon">
              {step.status === 'completed' ? '✓' : step.status === 'failed' ? '✗' : '●'}
            </div>
            <div className="gen-step-label">{step.label} &mdash; {step.description}</div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)' }}>
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
    screenwriter: '编',
    author: '执',
    polisher: '润',
    editor: '审',
    publish: '发',
  }

  if (!runDetail) {
    return (
      <div className="artifacts-empty">
        <div className="artifacts-empty-icon">产物</div>
        <div className="artifacts-empty-title">尚未生成章节</div>
        <div className="artifacts-empty-desc">生成章节后，可在此查看各 Agent 的产出摘要</div>
      </div>
    )
  }

  const stepsWithArtifacts = runDetail.steps.filter((step) => step.status === 'completed' && step.artifacts)
  if (stepsWithArtifacts.length === 0) {
    return (
      <div className="artifacts-empty">
        <div className="artifacts-empty-icon">产物</div>
        <div className="artifacts-empty-title">暂无产物数据</div>
        <div className="artifacts-empty-desc">当前章节尚未完成生成流程，完成后可查看产物</div>
      </div>
    )
  }

  return (
    <div className="artifacts-grid">
      {stepsWithArtifacts.map((step) => {
        const isExpanded = expandedKey === step.key
        const mark = agentMarks[step.key] || '文'
        return (
          <div key={step.key} className="artifact-card">
            <div className="artifact-header">
              <span className="artifact-icon">{mark}</span>
              <span className="artifact-label">{step.label}产物</span>
              <span className="artifact-status">{'✓'}</span>
            </div>
            <div className="artifact-summary">{step.artifacts!.summary}</div>
            {step.artifacts!.output_preview && (
              <div className="artifact-preview-section">
                {isExpanded ? (
                  <div className="artifact-preview-expanded">
                    <div className="preview-content">{step.artifacts!.output_preview}</div>
                    <button className="preview-toggle" onClick={() => setExpandedKey(null)}>收起</button>
                  </div>
                ) : (
                  <button className="preview-toggle" onClick={() => setExpandedKey(step.key)}>展开预览</button>
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
      <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)' }}>
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
