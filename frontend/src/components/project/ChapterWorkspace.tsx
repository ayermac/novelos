import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Sparkles, Loader2 } from 'lucide-react'
import ChapterNav from '../ChapterNav'
import ContextSidebar from '../ContextSidebar'
import WorkflowTimeline from '../WorkflowTimeline'
import AttentionPanel, { ActionHintList } from '../AttentionPanel'
import { StepStatus } from '../../hooks/useSSEStream'
import { tChapterStatus, tWorkflowStatus } from '../../lib/i18n'
import { post } from '../../lib/api'

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
  steps: Step[]
}

export type ChapterTabKey = 'content' | 'workflow' | 'artifacts' | 'history'

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

const NODE_LABEL_MAP: Record<string, string> = {
  screenwriter: '编剧',
  author: '执笔',
  polisher: '润色',
  editor: '审核',
  publish: '发布',
  human_review: '人工复盘',
}

function getModuleForMissing(item: string): string {
  for (const [label, mod] of Object.entries(MISSING_TO_MODULE)) {
    if (item.startsWith(label) || item === label) return mod
  }
  return 'settings'
}

function getNodeLabel(node?: string | null): string {
  if (!node) return '未知节点'
  return NODE_LABEL_MAP[node] || node
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
  llmMode: string
  nextChapterNumber: number | null
  projectId: string
  runDetail: RunDetailData | null
  runsForChapter: Run[]
  sseSteps: Record<string, StepStatus>
  totalChapters: number
  onGenerate: () => void
  onGenerateNext: () => void
  onNavigateToRun: () => void
  onPublish: () => void
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
  llmMode,
  nextChapterNumber,
  projectId,
  runDetail,
  runsForChapter,
  sseSteps,
  totalChapters,
  onGenerate,
  onGenerateNext,
  onNavigateToRun,
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
          />
        </div>
      </div>
      <div className="ws-right">
        <ContextSidebar
          currentChapter={currentChapterRecord}
          chapterNumber={currentChapter}
          llmMode={llmMode}
          recentRuns={runsForChapter}
          totalChapters={totalChapters}
          nextChapterNumber={nextChapterNumber}
          projectId={projectId}
          onGenerate={onGenerate}
          onViewWorkflow={onViewWorkflow}
          onViewContent={onViewContent}
          onGenerateNext={onGenerateNext}
          onNavigateToRun={onNavigateToRun}
          onPublish={onPublish}
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
    { key: 'artifacts', label: '产物' },
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
  sseSteps, isStreaming, projectId,
}: {
  activeTab: ChapterTabKey; generating: boolean; genError: string
  genErrorDetails: { missing?: string[]; actions?: string[] } | null
  chapterLoading: boolean; hasContent: boolean; isLaunching: boolean; isStub: boolean; currentChapter: number
  chapterDetail: ChapterDetail | null; runDetail: RunDetailData | null
  runsForChapter: Run[]; onGenerate: () => void; onViewWorkflow: (runId: string) => void
  sseSteps: Record<string, StepStatus>; isStreaming: boolean; projectId: string
}) {
  switch (activeTab) {
    case 'content':
      return (
        <ContentTab
          generating={generating} genError={genError} genErrorDetails={genErrorDetails} chapterLoading={chapterLoading}
          hasContent={hasContent} isStub={isStub} currentChapter={currentChapter}
          chapterDetail={chapterDetail} onGenerate={onGenerate}
          sseSteps={sseSteps} projectId={projectId}
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
  currentChapter, chapterDetail, onGenerate, sseSteps, projectId,
}: {
  generating: boolean; genError: string
  genErrorDetails: { missing?: string[]; actions?: string[] } | null
  chapterLoading: boolean; hasContent: boolean; isStub: boolean; currentChapter: number; chapterDetail: ChapterDetail | null
  onGenerate: () => void; sseSteps: Record<string, StepStatus>; projectId: string
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
    const currentRunningIndex = stepKeys.findIndex(k => sseSteps[k]?.status === 'running')
    if (currentRunningIndex >= 0 && index > currentRunningIndex) return '等待中...'
    return '等待中...'
  }

  return (
    <div>
      {generating && (
        <div style={{ marginBottom: '16px' }}>
          {GENERATING_STEPS.map((step, i) => {
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
          <button className="btn btn-primary" onClick={onGenerate} style={{ marginTop: '16px' }}>
            生成本章
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
    const nodeLabel = getNodeLabel(runDetail.current_node)
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
    const stepKeys = ['screenwriter', 'author', 'polisher', 'editor', 'publish']

    const steps: Step[] = GENERATING_STEPS.map((s) => {
      const stepStatus = sseSteps[s.key]
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

      return { key: s.key, label: s.label, description, status }
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

  const stepsWithArtifacts = runDetail.steps.filter(
    (step) => step.status === 'completed' && step.artifacts
  )

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
