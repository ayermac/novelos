import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Sparkles, Loader2, Play, Eye, FileText, XCircle, CheckCircle2, AlertCircle } from 'lucide-react'
import ChapterNav from '../ChapterNav'
import WorkflowTimeline from '../WorkflowTimeline'
import AttentionPanel, { ActionHintList } from '../AttentionPanel'
import { StepStatus } from '../../hooks/useSSEStream'
import { tWorkflowNodeLabel } from '../../lib/state-labels'
import { tWorkflowStatus, tChapterStatus } from '../../lib/i18n'
import { post } from '../../lib/api'
import { PROCESS_DRAFT_LABEL, formatArtifactSummary, getArtifactTitle } from '../../lib/artifacts'

interface Chapter {
  chapter_number: number
  status: string
  word_count: number
  quality_score?: number
  title?: string
}

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
  status: 'pending' | 'running' | 'completed' | 'failed' | 'blocked'
  error_message?: string
  artifacts?: {
    summary: string
    output_preview?: string
    artifact_labels?: unknown
    artifact_count?: unknown
    artifact_types?: unknown
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
  steps: Step[]
  error_message?: string | null
  total_tokens?: number | null
  duration_ms?: number | null
}

export type ChapterTabKey = 'content' | 'workflow' | 'artifacts' | 'history'

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


/* ------------------------------------------------------------------ */
/*  RunDetailSidebar — right panel showing current run status          */
/* ------------------------------------------------------------------ */

function RunDetailSidebar({
  runDetail,
  isStreaming,
  sseSteps,
  currentChapter,
  currentChapterRecord,
  runsForChapter,
  isWorkflowRunning,
  onGenerate,
  onPublish,
  onGenerateNext,
  onViewContent,
  onViewWorkflow,
}: {
  runDetail: RunDetailData | null
  isStreaming: boolean
  sseSteps: Record<string, StepStatus>
  currentChapter: number
  currentChapterRecord: Chapter | null
  runsForChapter: Run[]
  isWorkflowRunning?: boolean
  onGenerate: () => void
  onPublish?: () => void
  onGenerateNext?: () => void
  onViewContent: () => void
  onViewWorkflow: (runId: string) => void
}) {
  const hasContent = (currentChapterRecord?.word_count || 0) > 0
  const currentNode = runDetail?.current_node
  const workflowStatus = runDetail?.workflow_status
  const sseStepEntries = Object.entries(sseSteps)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Current run status */}
      <div className="data-card" style={{ padding: 12 }}>
        <div className="data-card-title" style={{ fontSize: 13, marginBottom: 8 }}>
          第 {currentChapter} 章 · 运行状态
        </div>

        {runDetail ? (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              {workflowStatus === 'running' && <Loader2 size={14} className="spin" color="#3b82f6" />}
              {workflowStatus === 'completed' && <CheckCircle2 size={14} color="#10b981" />}
              {workflowStatus === 'failed' && <XCircle size={14} color="#ef4444" />}
              {workflowStatus === 'blocked' && <AlertCircle size={14} color="#f59e0b" />}
              <span style={{ fontSize: 13, fontWeight: 500 }}>
                {workflowStatus === 'running' ? '执行中'
                  : workflowStatus === 'completed' ? '已完成'
                  : workflowStatus === 'failed' ? '失败'
                  : workflowStatus === 'blocked' ? '阻塞'
                  : workflowStatus || '—'}
              </span>
            </div>
            {currentNode && (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
                当前节点：{tWorkflowNodeLabel(currentNode)}
              </div>
            )}
            {runDetail.chapter_status && (
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                章节状态：{tChapterStatus(runDetail.chapter_status)}
              </div>
            )}
          </>
        ) : (
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>暂无运行记录</div>
        )}

        {/* Streaming indicator */}
        {isStreaming && sseStepEntries.length > 0 && (
          <div style={{ marginTop: 8, borderTop: '1px solid var(--border-color)', paddingTop: 8 }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>实时进度</div>
            {sseStepEntries.map(([key, step]) => (
              <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                {step.status === 'running' && <Loader2 size={11} className="spin" color="#3b82f6" />}
                {step.status === 'completed' && <CheckCircle2 size={11} color="#10b981" />}
                {step.status === 'failed' && <XCircle size={11} color="#ef4444" />}
                <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{key}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Error/stop reason */}
      {runDetail?.error_message && (workflowStatus === 'failed' || workflowStatus === 'blocked') && (
        <div className="data-card" style={{ padding: 12, borderLeft: '3px solid #ef4444' }}>
          <div style={{ fontSize: 12, color: '#991b1b' }}>{runDetail.error_message}</div>
        </div>
      )}

      {/* Run stats */}
      {runDetail && (runDetail.total_tokens || runDetail.duration_ms) && (
        <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--text-muted)' }}>
          {runDetail.total_tokens ? <span>Token: {runDetail.total_tokens.toLocaleString()}</span> : null}
          {runDetail.duration_ms ? <span>耗时: {Math.round(runDetail.duration_ms / 1000)}s</span> : null}
        </div>
      )}

      {/* Action buttons */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {runDetail && (
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => onViewWorkflow(runDetail.run_id)}
            style={{ fontSize: 12, justifyContent: 'flex-start' }}
          >
            <Eye size={12} /> 查看运行详情
          </button>
        )}
        {hasContent && (
          <button
            className="btn btn-secondary btn-sm"
            onClick={onViewContent}
            style={{ fontSize: 12, justifyContent: 'flex-start' }}
          >
            <FileText size={12} /> 查看正文
          </button>
        )}
        {/* Publish: when reviewed and workflow completed (real mode) */}
        {currentChapterRecord?.status === 'reviewed' && workflowStatus === 'completed' && onPublish && (
          <button
            className="btn btn-primary btn-sm"
            onClick={onPublish}
            style={{ fontSize: 12, justifyContent: 'flex-start' }}
          >
            <CheckCircle2 size={12} /> 确认发布
          </button>
        )}
        {/* Generate: when not published and not awaiting publish */}
        {currentChapterRecord?.status !== 'published' && currentChapterRecord?.status !== 'awaiting_publish' && currentChapterRecord?.status !== 'reviewed' && (
          <button
            className="btn btn-primary btn-sm"
            onClick={onGenerate}
            disabled={isStreaming || workflowStatus === 'running' || isWorkflowRunning}
            style={{ fontSize: 12, justifyContent: 'flex-start' }}
          >
            <Play size={12} /> {isStreaming || workflowStatus === 'running' || isWorkflowRunning ? '生成中...' : '生成本章'}
          </button>
        )}
        {/* Generate next: when current chapter is published */}
        {currentChapterRecord?.status === 'published' && onGenerateNext && (
          <button
            className="btn btn-primary btn-sm"
            onClick={onGenerateNext}
            style={{ fontSize: 12, justifyContent: 'flex-start' }}
          >
            <Sparkles size={12} /> 生成下一章
          </button>
        )}
      </div>

      {/* Recent runs */}
      {runsForChapter.length > 0 && (
        <div className="data-card" style={{ padding: 12 }}>
          <div className="data-card-title" style={{ fontSize: 13, marginBottom: 8 }}>
            近期运行
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 200, overflowY: 'auto' }}>
            {runsForChapter.slice(0, 5).map((run) => (
              <div
                key={run.run_id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 8,
                  padding: '6px 8px',
                  background: 'var(--bg-tertiary)',
                  borderRadius: 6,
                  cursor: 'pointer',
                }}
                onClick={() => onViewWorkflow(run.run_id)}
              >
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {run.run_id.slice(0, 8)}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{run.created_at}</div>
                </div>
                <span
                  style={{
                    fontSize: 10,
                    padding: '2px 6px',
                    borderRadius: 4,
                    background: run.status === 'completed'
                      ? 'color-mix(in srgb, var(--success) 16%, transparent)'
                      : run.status === 'failed'
                        ? 'color-mix(in srgb, var(--danger) 16%, transparent)'
                        : 'var(--accent-soft)',
                    color: run.status === 'completed'
                      ? 'var(--success)'
                      : run.status === 'failed'
                        ? 'var(--danger)'
                        : 'var(--primary)',
                    flexShrink: 0,
                  }}
                >
                  {tWorkflowStatus(run.status)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}


interface ChapterWorkspaceProps {
  activeTab: ChapterTabKey
  chapterDetail: ChapterDetail | null
  chapterLoading: boolean
  chapters: Chapter[]
  currentChapter: number
  currentChapterRecord: Chapter | null
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
  onResetChapter: (chapterNumber: number) => void
  onSelectChapter: (chapterNumber: number) => void
  onTabChange: (tab: ChapterTabKey) => void
  onViewContent: () => void
  onViewWorkflow: (runId: string) => void
}

export default function ChapterWorkspace({
  activeTab,
  chapterDetail,
  chapterLoading,
  chapters,
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
  onResetChapter,
  onSelectChapter,
  onTabChange,
  onViewContent,
  onViewWorkflow,
}: ChapterWorkspaceProps) {
  const hasContent = (chapterDetail?.word_count || 0) > 0

  return (
    <div className="ws-body">
      <div className="ws-left">
        <ChapterNav
          chapters={chapters}
          currentChapter={currentChapter}
          onSelect={onSelectChapter}
          onReset={onResetChapter}
          llmMode={llmMode}
        />
      </div>
      <div className="ws-center">
        <ChapterTabBar
          activeTab={activeTab}
          onTabChange={onTabChange}
          hasRuns={runsForChapter.length > 0}
        />
        <div className="ws-tab-content">
          <ChapterTabContent
            activeTab={activeTab}
            generating={isStreaming}
            genError={genError}
            genErrorDetails={genErrorDetails}
            chapterLoading={chapterLoading}
            hasContent={hasContent}
            isLaunching={isLaunching}
            isStub={isStub}
            currentChapter={currentChapter}
            chapterDetail={chapterDetail}
            runDetail={runDetail}
            runsForChapter={runsForChapter}
            onGenerate={onGenerate}
            onViewWorkflow={onViewWorkflow}
            sseSteps={sseSteps}
            isStreaming={isStreaming}
            projectId={projectId}
            isWorkflowRunning={isWorkflowRunning}
          />
        </div>
      </div>
      <div className="ws-right">
        <RunDetailSidebar
          runDetail={runDetail}
          isStreaming={isStreaming}
          sseSteps={sseSteps}
          currentChapter={currentChapter}
          currentChapterRecord={currentChapterRecord}
          runsForChapter={runsForChapter}
          isWorkflowRunning={isWorkflowRunning}
          onGenerate={onGenerate}
          onPublish={onPublish}
          onGenerateNext={onGenerateNext}
          onViewContent={onViewContent}
          onViewWorkflow={onViewWorkflow}
        />
      </div>
    </div>
  )
}

function ChapterTabBar({ activeTab, onTabChange, hasRuns }: {
  activeTab: ChapterTabKey; onTabChange: (t: ChapterTabKey) => void; hasRuns: boolean
}) {
  const tabs: { key: ChapterTabKey; label: string; disabled?: boolean }[] = [
    { key: 'content', label: '正文' },
    { key: 'workflow', label: '工作流', disabled: !hasRuns },
    { key: 'artifacts', label: PROCESS_DRAFT_LABEL },
    { key: 'history', label: '历史', disabled: !hasRuns },
  ]
  return (
    <div className="ws-tabs">
      {tabs.map((t) => (
        <button
          key={t.key}
          className={`ws-tab${activeTab === t.key ? ' active' : ''}${t.disabled ? ' ws-tab-disabled' : ''}`}
          onClick={() => !t.disabled && onTabChange(t.key)}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

function ChapterTabContent({ activeTab, generating, genError, genErrorDetails, chapterLoading, hasContent, isLaunching, isStub,
  currentChapter, chapterDetail, runDetail, runsForChapter, onGenerate, onViewWorkflow,
  sseSteps, isStreaming, projectId, isWorkflowRunning,
}: {
  activeTab: ChapterTabKey; generating: boolean; genError: string
  genErrorDetails: { missing?: string[]; actions?: string[] } | null
  chapterLoading: boolean; hasContent: boolean; isLaunching: boolean; isStub: boolean; currentChapter: number
  chapterDetail: ChapterDetail | null; runDetail: RunDetailData | null
  runsForChapter: Run[]; onGenerate: () => void; onViewWorkflow: (runId: string) => void
  sseSteps: Record<string, StepStatus>; isStreaming: boolean; projectId: string
  isWorkflowRunning?: boolean
}) {
  switch (activeTab) {
    case 'content':
      return (
        <ContentTab
          generating={generating} genError={genError} genErrorDetails={genErrorDetails} chapterLoading={chapterLoading}
          hasContent={hasContent} isStub={isStub} currentChapter={currentChapter}
          chapterDetail={chapterDetail} onGenerate={onGenerate}
          sseSteps={sseSteps} projectId={projectId} isWorkflowRunning={isWorkflowRunning}
        />
      )
    case 'workflow':
      return <WorkflowTab runDetail={runDetail} generating={generating} isLaunching={isLaunching} sseSteps={sseSteps} isStreaming={isStreaming} />
    case 'artifacts':
      return <ArtifactsTab runDetail={runDetail} />
    case 'history':
      return <HistoryTab runsForChapter={runsForChapter} onViewWorkflow={onViewWorkflow} currentChapter={currentChapter} />
    default:
      return null
  }
}

function ContentTab({ generating, genError, genErrorDetails, chapterLoading, hasContent, isStub,
  currentChapter, chapterDetail, onGenerate, sseSteps, projectId, isWorkflowRunning,
}: {
  generating: boolean; genError: string
  genErrorDetails: { missing?: string[]; actions?: string[] } | null
  chapterLoading: boolean; hasContent: boolean; isStub: boolean; currentChapter: number; chapterDetail: ChapterDetail | null
  onGenerate: () => void; sseSteps: Record<string, StepStatus>; projectId: string
  isWorkflowRunning?: boolean
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
    const stepKeys = getGeneratingStepKeys(sseSteps)
    const currentRunningIndex = stepKeys.findIndex(k => sseSteps[k]?.status === 'running')
    if (currentRunningIndex >= 0 && index > currentRunningIndex) return '等待中...'
    return '等待中...'
  }

  return (
    <div>
      {generating && (
        <div style={{ marginBottom: '16px' }}>
          {getGeneratingSteps(sseSteps).map((step, i) => {
            const stepStatus = sseSteps[step.key]
            const isActive = stepStatus?.status === 'running'
            const isCompleted = stepStatus?.status === 'completed'
            const isFailed = stepStatus?.status === 'failed'
            const statusText = stepStatus
              ? getStepStatusText(stepStatus, i)
              : '等待中...'

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
        <AttentionPanel title="生成失败" tone="error" style={{ marginBottom: '16px' }}>
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
      {chapterLoading && !generating && (
        <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>加载中...</div>
      )}
      {!chapterLoading && !hasContent && !generating && (
        <div className="empty-chapter">
          <div className="empty-chapter-num">第 {currentChapter} 章</div>
          {chapterDetail?.title && <div className="empty-chapter-title">{chapterDetail.title}</div>}
          <div className="empty-chapter-hint">本章尚未生成</div>
          <div className="empty-chapter-desc">编剧将规划章节场景和情节，执笔将撰写章节正文</div>
          <button className="btn btn-primary" onClick={onGenerate} style={{ marginTop: '16px' }}
            disabled={isWorkflowRunning}>
            {isWorkflowRunning ? '生成中...' : '生成本章'}
          </button>
          <div style={{ marginTop: '12px', fontSize: '12px', color: 'var(--text-muted)' }}>
            预计字数: 2,000-4,000 &middot; 生成模式: {isStub ? '演示模式' : '真实 LLM'}
          </div>
        </div>
      )}
      {!chapterLoading && hasContent && (
        <div>
          {isStub && (
            <div className="alert alert-warn" style={{ marginBottom: '12px' }}>
              <strong>演示正文</strong>
              <div style={{ marginTop: '4px', fontSize: '13px' }}>
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

function WorkflowTab({ runDetail, generating, isLaunching, sseSteps, isStreaming }: {
  runDetail: RunDetailData | null; generating: boolean; isLaunching: boolean; sseSteps: Record<string, StepStatus>; isStreaming: boolean
}) {
  if (runDetail && !isStreaming) {
    const nodeLabel = tWorkflowNodeLabel(runDetail.current_node)
    const statusLabel = tWorkflowStatus(runDetail.workflow_status)
    const chapterStatusLabel = tChapterStatus(runDetail.chapter_status)
    const statusTone = runDetail.workflow_status === 'blocked' ? 'warning' : runDetail.workflow_status === 'failed' ? 'error' : 'info'
    const statusHeadline = runDetail.workflow_status === 'running'
      ? '工作流正在推进'
      : runDetail.workflow_status === 'blocked'
        ? '工作流已阻塞'
        : runDetail.workflow_status === 'completed' && runDetail.chapter_status === 'reviewed'
          ? '审核已完成'
          : '最近一次运行'
    const statusDescription = runDetail.workflow_status === 'running'
      ? `当前节点：${nodeLabel}。这表示工作流仍在推进，不是静态卡死。`
      : runDetail.workflow_status === 'blocked'
        ? `本次运行已阻塞，需要先处理最近的失败或返修原因。`
        : runDetail.workflow_status === 'completed' && runDetail.chapter_status === 'reviewed'
          ? 'AI 审核已完成，当前等待人工发布。'
          : '最近一次运行记录如下。'

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div
          className={`alert ${statusTone === 'warning' ? 'alert-warn' : statusTone === 'error' ? 'alert-error' : 'alert-info'}`}
          style={{ marginBottom: 0 }}
        >
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
                {statusHeadline}
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                当前节点：{nodeLabel}
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>{statusDescription}</div>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              <span className={`status-badge status-${runDetail.workflow_status}`}>{statusLabel}</span>
              <span className={`status-badge status-${runDetail.chapter_status}`}>{chapterStatusLabel}</span>
            </div>
          </div>
          <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-muted)' }}>
            节点是流程里的具体步骤名，审核节点亮起时表示正在审稿，不一定代表失败。
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

  if (generating || isStreaming) {
    const hasSseData = Object.keys(sseSteps).length > 0
    const stepKeys = getGeneratingStepKeys(sseSteps)

    const steps: Step[] = getGeneratingSteps(sseSteps).map((s) => {
      const stepStatus = sseSteps[s.key] || (s.key === 'publisher' ? sseSteps.publish : undefined)
      let status: Step['status'] = 'pending'
      let description = '等待中...'

      if (stepStatus) {
        status = stepStatus.status as Step['status']
        if (status === 'running') description = '处理中...'
        else if (status === 'completed') description = `完成 (${stepStatus.duration_ms || 0}ms)`
        else if (status === 'failed') description = '失败'
      } else if (hasSseData) {
        const currentIndex = stepKeys.findIndex(k => sseSteps[k]?.status === 'running')
        const myIndex = stepKeys.indexOf(s.key)
        if (currentIndex >= 0 && myIndex > currentIndex) {
          status = 'pending'
          description = '等待中...'
        }
      }

      return { key: s.key, label: s.label, node_group: s.node_group, description, status }
    })

    return <WorkflowTimeline steps={steps} />
  }

  return (
    <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
      暂无工作流数据。生成章节后可查看工作流步骤。
    </div>
  )
}

function ArtifactsTab({ runDetail }: { runDetail: RunDetailData | null }) {
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

  const stepsWithArtifacts = runDetail.steps.filter(
    (step) => step.status === 'completed' && step.artifacts
  )

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

function HistoryTab({ runsForChapter, onViewWorkflow, currentChapter }: {
  runsForChapter: Run[]; onViewWorkflow: (runId: string) => void; currentChapter: number
}) {
  if (runsForChapter.length === 0) {
    return (
      <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
        暂无运行历史。生成章节后可查看记录。
      </div>
    )
  }
  return (
    <div>
      <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '12px' }}>
        第 {currentChapter} 章相关运行记录
      </div>
      {runsForChapter.map((run) => (
        <div key={run.run_id} className="history-item">
          <div className="history-item-left">
            <span className={`status-badge status-${run.status}`}>
              {tWorkflowStatus(run.status)}
            </span>
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
