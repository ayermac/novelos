import { useEffect, useState, useCallback } from 'react'
import { useParams, useSearchParams, useNavigate } from 'react-router-dom'
import { get, post, del, put } from '../lib/api'
import ChapterNav from '../components/ChapterNav'
import WorkflowTimeline from '../components/WorkflowTimeline'
import ContextSidebar from '../components/ContextSidebar'
import ErrorState from '../components/ErrorState'
import { tWorkflowStatus } from '../lib/i18n'
import { useSSEStream, SSEEvent, StepStatus } from '../hooks/useSSEStream'

interface Chapter {
  chapter_number: number
  status: string
  word_count: number
  quality_score?: number
  title?: string
}

interface Run {
  run_id: string
  chapter_number: number
  status: string
  created_at: string
  error_message?: string
}

interface Workspace {
  project: {
    project_id: string
    name: string
    genre?: string
    description?: string
    total_chapters_planned: number
  }
  chapters: Chapter[]
  recent_runs: Run[]
  stats: {
    total_chapters: number
    total_words: number
    status_counts: Record<string, number>
  }
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
  llm_mode: string
  steps: Step[]
}

type TabKey = 'content' | 'workflow' | 'artifacts' | 'history' | 'worldview' | 'characters' | 'outline'

// World Setting interfaces
interface WorldSetting {
  id: number
  project_id: string
  category: string
  title: string
  content: string
  importance?: string
  created_at?: string
  updated_at?: string
}

// Character interfaces
interface Character {
  id: number
  project_id: string
  name: string
  alias?: string
  role: string
  description?: string
  traits?: string
  first_appearance?: number
  status?: string
  created_at?: string
  updated_at?: string
}

// Outline interfaces
interface Outline {
  id: number
  project_id: string
  level: string
  phase?: string
  chapters?: string
  summary?: string
  key_events?: string
  notes?: string
  parent_id?: number
  sort_order?: number
  created_at?: string
  updated_at?: string
}

const GENERATING_STEPS = [
  { key: 'screenwriter', label: '编剧' },
  { key: 'author', label: '执笔' },
  { key: 'polisher', label: '润色' },
  { key: 'editor', label: '审核' },
  { key: 'publish', label: '发布' },
]

export default function ProjectDetail() {
  const { id } = useParams<{ id: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()

  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [chapterDetail, setChapterDetail] = useState<ChapterDetail | null>(null)
  const [runDetail, setRunDetail] = useState<RunDetailData | null>(null)
  const [llmMode, setLlmMode] = useState<string>('stub')
  const [activeTab, setActiveTab] = useState<TabKey>('content')
  const [loading, setLoading] = useState(true)
  const [chapterLoading, setChapterLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [genError, setGenError] = useState('')
  const [genErrorDetails, setGenErrorDetails] = useState<{ missing?: string[]; actions?: string[] } | null>(null)
  const [error, setError] = useState('')

  // World settings, characters, outlines
  const [worldSettings, setWorldSettings] = useState<WorldSetting[]>([])
  const [characters, setCharacters] = useState<Character[]>([])
  const [outlines, setOutlines] = useState<Outline[]>([])
  const [dataLoading, setDataLoading] = useState(false)
  const [sseSteps, setSseSteps] = useState<Record<string, StepStatus>>({})

  const currentChapter = parseInt(searchParams.get('chapter') || '1', 10)

  const loadWorkspace = useCallback(() => {
    if (!id) return
    setLoading(true)
    setError('')
    get<Workspace>(`/projects/${id}/workspace`)
      .then((res) => {
        if (res.ok && res.data) setWorkspace(res.data)
        else setError(res.error?.message || '获取项目工作台失败')
        setLoading(false)
      })
    get<{ llm_mode: string }>('/health')
      .then((res) => { if (res.ok && res.data) setLlmMode(res.data.llm_mode) })
  }, [id])

  useEffect(() => { loadWorkspace() }, [loadWorkspace])

  // Set initial chapter
  useEffect(() => {
    if (workspace && !searchParams.get('chapter') && workspace.chapters.length > 0) {
      setSearchParams({ chapter: String(workspace.chapters[0].chapter_number) }, { replace: true })
    }
  }, [workspace])

  // Load chapter detail when chapter changes
  useEffect(() => {
    if (!id || !currentChapter) return
    setChapterLoading(true)
    setChapterDetail(null)
    setRunDetail(null)
    setGenError('')
    get<ChapterDetail>(`/projects/${id}/chapters/${currentChapter}`)
      .then((res) => {
        if (res.ok && res.data) setChapterDetail(res.data)
        setChapterLoading(false)
      })
  }, [id, currentChapter])

  // Set tab from view param on first load
  useEffect(() => {
    const view = searchParams.get('view')
    if (view === 'workflow' || view === 'content' || view === 'artifacts' || view === 'history') {
      setActiveTab(view)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const loadRunDetail = (runId: string) => {
    get<RunDetailData>(`/runs/${runId}`)
      .then((res) => { if (res.ok && res.data) setRunDetail(res.data) })
  }

  // Load world settings, characters, outlines
  const loadProjectData = useCallback(() => {
    if (!id) return
    setDataLoading(true)
    Promise.all([
      get<WorldSetting[]>(`/projects/${id}/world-settings`),
      get<Character[]>(`/projects/${id}/characters`),
      get<Outline[]>(`/projects/${id}/outlines`),
    ]).then(([wsRes, chRes, olRes]) => {
      if (wsRes.ok && wsRes.data) setWorldSettings(wsRes.data)
      if (chRes.ok && chRes.data) setCharacters(chRes.data)
      if (olRes.ok && olRes.data) setOutlines(olRes.data)
      setDataLoading(false)
    })
  }, [id])

  useEffect(() => { loadProjectData() }, [loadProjectData])

  // SSE streaming hook for real-time generation progress
  const handleSSEComplete = useCallback((event: SSEEvent) => {
    setGenerating(false)
    setGenErrorDetails(null)
    if (event.run_id) {
      loadRunDetail(event.run_id)
    }
    loadWorkspace()
    get<ChapterDetail>(`/projects/${id}/chapters/${currentChapter}`)
      .then((r) => {
        if (r.ok && r.data) setChapterDetail(r.data)
        setActiveTab('content')
      })
  }, [id, currentChapter, loadWorkspace])

  const handleSSEError = useCallback((error: string, event?: SSEEvent) => {
    setGenerating(false)
    setGenError(error)
    if (event?.context_incomplete) {
      setGenErrorDetails({
        missing: event.missing || [],
        actions: event.actions || [],
      })
    } else {
      setGenErrorDetails(null)
    }
  }, [])

  const { isStreaming, steps: sseHookSteps, startStream } = useSSEStream(
    handleSSEComplete,
    handleSSEError
  )

  // Sync SSE steps to local state for rendering
  useEffect(() => {
    setSseSteps(sseHookSteps)
  }, [sseHookSteps])

  const handleSelectChapter = (chapterNumber: number) => {
    setSearchParams({ chapter: String(chapterNumber) }, { replace: true })
    setActiveTab('content')
  }

  const handleTabChange = (tab: TabKey) => {
    setActiveTab(tab)
    if (tab === 'workflow' || tab === 'artifacts') {
      const runsForChapter = (workspace?.recent_runs || [])
        .filter((r) => r.chapter_number === currentChapter)
      const latestRun = runsForChapter.length > 0 ? runsForChapter[0] : null
      if (latestRun) loadRunDetail(latestRun.run_id)
    }
  }

  const handleGenerate = () => {
    if (!id) return
    setGenerating(true)
    setGenError('')
    setGenErrorDetails(null)
    setSseSteps({})
    setActiveTab('workflow')

    // Use SSE streaming for real-time progress
    startStream(id, currentChapter)
  }

  const handleViewWorkflow = (runId: string) => {
    loadRunDetail(runId)
    setActiveTab('workflow')
  }

  const handleViewContent = () => setActiveTab('content')

  const handleGenerateNext = () => {
    const next = currentChapter + 1
    setSearchParams({ chapter: String(next) }, { replace: true })
    if (!id) return
    setGenerating(true)
    setGenError('')
    setGenErrorDetails(null)
    setSseSteps({})
    setActiveTab('workflow')

    // Use SSE streaming for real-time progress
    startStream(id, next)
  }

  const handleNavigateToRun = () => {
    navigate(`/run?project_id=${id}&chapter=${currentChapter}`)
  }

  const handlePublishChapter = () => {
    // Refresh workspace after publish
    loadWorkspace()
    get<ChapterDetail>(`/projects/${id}/chapters/${currentChapter}`)
      .then((r) => {
        if (r.ok && r.data) setChapterDetail(r.data)
      })
  }

  const handleResetChapter = async (chapterNumber: number) => {
    if (!id) return
    const res = await post<{ reset: boolean; previous_status: string; new_status: string }>(
      `/projects/${id}/chapters/${chapterNumber}/reset`
    )
    if (res.ok && res.data) {
      loadWorkspace()
      get<ChapterDetail>(`/projects/${id}/chapters/${chapterNumber}`)
        .then((r) => {
          if (r.ok && r.data) setChapterDetail(r.data)
        })
    } else {
      alert(res.error?.message || '重置章节失败')
    }
  }

  if (loading) return <div style={{ padding: '40px', textAlign: 'center' }}>加载中...</div>
  if (error || !workspace) return <ErrorState title="加载失败" message={error || '项目不存在'} onRetry={loadWorkspace} />

  const currentCh = workspace.chapters.find((c) => c.chapter_number === currentChapter) || null
  const hasContent = (chapterDetail?.word_count || 0) > 0
  const isStub = llmMode === 'stub'
  const runsForChapter = workspace.recent_runs.filter((r) => r.chapter_number === currentChapter)

  return (
    <div className="workspace-layout">
      <WorkspaceTopbar
        projectName={workspace.project.name}
        currentChapter={currentChapter}
        publishedCount={workspace.stats.status_counts?.published || 0}
        isStub={isStub}
      />
      <div className="ws-body">
        <div className="ws-left">
          <ChapterNav
            chapters={workspace.chapters}
            currentChapter={currentChapter}
            onSelect={handleSelectChapter}
            onReset={handleResetChapter}
            llmMode={llmMode}
          />
        </div>
        <div className="ws-center">
          <TabBar activeTab={activeTab} onTabChange={handleTabChange} hasRuns={runsForChapter.length > 0} />
          <div className="ws-tab-content">
            <TabContent
              activeTab={activeTab}
              generating={generating || isStreaming}
              genError={genError}
              genErrorDetails={genErrorDetails}
              chapterLoading={chapterLoading}
              hasContent={hasContent}
              isStub={isStub}
              currentChapter={currentChapter}
              chapterDetail={chapterDetail}
              runDetail={runDetail}
              runsForChapter={runsForChapter}
              onGenerate={handleGenerate}
              onViewWorkflow={handleViewWorkflow}
              worldSettings={worldSettings}
              characters={characters}
              outlines={outlines}
              dataLoading={dataLoading}
              onLoadData={loadProjectData}
              projectId={id || ''}
              sseSteps={sseSteps}
              isStreaming={isStreaming}
            />
          </div>
        </div>
        <div className="ws-right">
          <ContextSidebar
            currentChapter={currentCh}
            chapterNumber={currentChapter}
            llmMode={llmMode}
            recentRuns={workspace.recent_runs}
            totalChapters={workspace.project.total_chapters_planned}
            projectId={id || ''}
            onGenerate={handleGenerate}
            onViewWorkflow={handleViewWorkflow}
            onViewContent={handleViewContent}
            onGenerateNext={handleGenerateNext}
            onNavigateToRun={handleNavigateToRun}
            onPublish={handlePublishChapter}
          />
        </div>
      </div>
      <WorkspaceStyles />
    </div>
  )
}

function WorkspaceTopbar({ projectName, currentChapter, publishedCount, isStub }: {
  projectName: string; currentChapter: number; publishedCount: number; isStub: boolean
}) {
  return (
    <div className="ws-topbar">
      <div className="ws-topbar-left">
        <a href="/projects" className="ws-back-link">← 返回项目列表</a>
        <span className="ws-project-name">{projectName}</span>
        <span className="ws-chapter-info">第 {currentChapter} 章 · 已发布 {publishedCount} 章</span>
      </div>
      <div className="ws-topbar-right">
        <span className={`status-badge ${isStub ? 'status-stub' : 'status-real'}`}>
          {isStub ? '演示模式' : '真实 LLM'}
        </span>
      </div>
    </div>
  )
}

function TabBar({ activeTab, onTabChange, hasRuns }: {
  activeTab: TabKey; onTabChange: (t: TabKey) => void; hasRuns: boolean
}) {
  const tabs: { key: TabKey; label: string; disabled?: boolean }[] = [
    { key: 'content', label: '正文' },
    { key: 'workflow', label: '工作流', disabled: !hasRuns },
    { key: 'artifacts', label: '产物' },
    { key: 'history', label: '历史', disabled: !hasRuns },
    { key: 'worldview', label: '世界观' },
    { key: 'characters', label: '角色' },
    { key: 'outline', label: '大纲' },
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

function TabContent({ activeTab, generating, genError, genErrorDetails, chapterLoading, hasContent, isStub,
  currentChapter, chapterDetail, runDetail, runsForChapter, onGenerate, onViewWorkflow,
  worldSettings, characters, outlines, dataLoading, onLoadData, projectId, sseSteps, isStreaming,
}: {
  activeTab: TabKey; generating: boolean; genError: string
  genErrorDetails: { missing?: string[]; actions?: string[] } | null
  chapterLoading: boolean; hasContent: boolean; isStub: boolean; currentChapter: number
  chapterDetail: ChapterDetail | null; runDetail: RunDetailData | null
  runsForChapter: Run[]; onGenerate: () => void; onViewWorkflow: (runId: string) => void
  worldSettings: WorldSetting[]; characters: Character[]; outlines: Outline[]
  dataLoading: boolean; onLoadData: () => void; projectId: string
  sseSteps: Record<string, StepStatus>; isStreaming: boolean
}) {
  switch (activeTab) {
    case 'content':
      return (
        <ContentTab
          generating={generating} genError={genError} genErrorDetails={genErrorDetails} chapterLoading={chapterLoading}
          hasContent={hasContent} isStub={isStub} currentChapter={currentChapter}
          chapterDetail={chapterDetail} onGenerate={onGenerate}
          sseSteps={sseSteps}
        />
      )
    case 'workflow':
      return <WorkflowTab runDetail={runDetail} generating={generating} sseSteps={sseSteps} isStreaming={isStreaming} />
    case 'artifacts':
      return <ArtifactsTab runDetail={runDetail} />
    case 'history':
      return <HistoryTab runsForChapter={runsForChapter} onViewWorkflow={onViewWorkflow} currentChapter={currentChapter} />
    case 'worldview':
      return <WorldViewTab worldSettings={worldSettings} loading={dataLoading} onLoad={onLoadData} projectId={projectId} />
    case 'characters':
      return <CharactersTab characters={characters} loading={dataLoading} onLoad={onLoadData} projectId={projectId} />
    case 'outline':
      return <OutlineTab outlines={outlines} loading={dataLoading} onLoad={onLoadData} projectId={projectId} />
    default:
      return null
  }
}

function ContentTab({ generating, genError, genErrorDetails, chapterLoading, hasContent, isStub,
  currentChapter, chapterDetail, onGenerate, sseSteps,
}: {
  generating: boolean; genError: string
  genErrorDetails: { missing?: string[]; actions?: string[] } | null
  chapterLoading: boolean; hasContent: boolean; isStub: boolean; currentChapter: number; chapterDetail: ChapterDetail | null
  onGenerate: () => void; sseSteps: Record<string, StepStatus>
}) {
  // Build real-time step display from SSE events
  const getStepStatusText = (status: StepStatus, index: number): string => {
    if (status.status === 'running') return '处理中...'
    if (status.status === 'completed') return `完成 (${status.duration_ms || 0}ms)`
    if (status.status === 'failed') return '失败'
    // Pending steps
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
                <div className="gen-step-label">{step.label} — {statusText}</div>
              </div>
            )
          })}
        </div>
      )}
      {genError && (
        <div className="alert alert-error" style={{ marginBottom: '16px' }}>
          <strong>生成失败</strong>
          <div style={{ marginTop: '4px' }}>{genError}</div>
          {genErrorDetails?.missing && genErrorDetails.missing.length > 0 && (
            <div style={{ marginTop: '12px' }}>
              <div style={{ fontWeight: 600, fontSize: '13px' }}>缺失项</div>
              <ul style={{ margin: '6px 0 0', paddingLeft: '18px' }}>
                {genErrorDetails.missing.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          {genErrorDetails?.actions && genErrorDetails.actions.length > 0 && (
            <div style={{ marginTop: '12px' }}>
              <div style={{ fontWeight: 600, fontSize: '13px' }}>建议操作</div>
              <ul style={{ margin: '6px 0 0', paddingLeft: '18px' }}>
                {genErrorDetails.actions.map((action, i) => (
                  <li key={i}>{action}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
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
            预计字数: 2,000-4,000 · 生成模式: {isStub ? '演示模式' : '真实 LLM'}
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

function WorkflowTab({ runDetail, generating, sseSteps, isStreaming }: {
  runDetail: RunDetailData | null; generating: boolean; sseSteps: Record<string, StepStatus>; isStreaming: boolean
}) {
  // If we have run detail from a completed run, show that
  if (runDetail && !isStreaming) return <WorkflowTimeline steps={runDetail.steps} />

  // During SSE streaming, show real-time progress
  if (generating || isStreaming) {
    // Build steps from SSE data
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
        // Find the current running step to determine pending status
        const currentIndex = stepKeys.findIndex(k => sseSteps[k]?.status === 'running')
        const myIndex = stepKeys.indexOf(s.key)
        if (currentIndex >= 0 && myIndex > currentIndex) {
          status = 'pending'
          description = '等待中...'
        }
      }

      return {
        key: s.key,
        label: s.label,
        description,
        status,
      }
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

  // Compact text marks keep the UI consistent with the non-emoji design system.
  const agentMarks: Record<string, string> = {
    screenwriter: '编',
    author: '执',
    polisher: '润',
    editor: '审',
    publish: '发',
  }

  // No run detail
  if (!runDetail) {
    return (
      <div className="artifacts-empty">
        <div className="artifacts-empty-icon">产物</div>
        <div className="artifacts-empty-title">尚未生成章节</div>
        <div className="artifacts-empty-desc">生成章节后，可在此查看各 Agent 的产出摘要</div>
      </div>
    )
  }

  // Filter steps with artifacts
  const stepsWithArtifacts = runDetail.steps.filter(
    (step) => step.status === 'completed' && step.artifacts
  )

  // No artifacts available
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
              <span className="artifact-status">✓</span>
            </div>
            <div className="artifact-summary">{step.artifacts!.summary}</div>
            {step.artifacts!.output_preview && (
              <div className="artifact-preview-section">
                {isExpanded ? (
                  <div className="artifact-preview-expanded">
                    <div className="preview-content">{step.artifacts!.output_preview}</div>
                    <button
                      className="preview-toggle"
                      onClick={() => setExpandedKey(null)}
                    >
                      收起
                    </button>
                  </div>
                ) : (
                  <button
                    className="preview-toggle"
                    onClick={() => setExpandedKey(step.key)}
                  >
                    展开预览
                  </button>
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

// Modal component for editing
function EditModal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{title}</h3>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  )
}

// World Settings Tab
function WorldViewTab({ worldSettings, loading, onLoad, projectId }: {
  worldSettings: WorldSetting[]; loading: boolean; onLoad: () => void; projectId: string
}) {
  const [showModal, setShowModal] = useState(false)
  const [editingItem, setEditingItem] = useState<WorldSetting | null>(null)
  const [form, setForm] = useState({ category: '', title: '', content: '' })

  const handleSubmit = async () => {
    const url = editingItem
      ? `/projects/${projectId}/world-settings/${editingItem.id}`
      : `/projects/${projectId}/world-settings`
    const res = editingItem
      ? await put(url, form)
      : await post(url, form)
    if (res.ok) {
      setShowModal(false)
      setEditingItem(null)
      setForm({ category: '', title: '', content: '' })
      onLoad()
    } else {
      alert(res.error?.message || '操作失败')
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除此世界观设定？')) return
    const res = await del(`/projects/${projectId}/world-settings/${id}`)
    if (res.ok) onLoad()
    else alert(res.error?.message || '删除失败')
  }

  const openEdit = (item: WorldSetting) => {
    setEditingItem(item)
    setForm({ category: item.category, title: item.title, content: item.content })
    setShowModal(true)
  }

  const openAdd = () => {
    setEditingItem(null)
    setForm({ category: '', title: '', content: '' })
    setShowModal(true)
  }

  if (loading) return <div style={{ padding: '24px', textAlign: 'center' }}>加载中...</div>

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <h3 style={{ margin: 0, fontSize: '16px' }}>世界观设定</h3>
        <button className="btn btn-primary btn-sm" onClick={openAdd}>+ 新增</button>
      </div>
      {worldSettings.length === 0 ? (
        <div className="data-empty">
          <div className="data-empty-icon">世</div>
          <div className="data-empty-title">暂无世界观设定</div>
          <div className="data-empty-desc">添加世界观设定，帮助 AI 更好理解故事背景</div>
          <button className="btn btn-secondary" onClick={openAdd} style={{ marginTop: '12px' }}>添加第一条</button>
        </div>
      ) : (
        <div className="data-grid">
          {worldSettings.map((ws) => (
            <div key={ws.id} className="data-card">
              <div className="data-card-header">
                <span className="data-card-category">{ws.category}</span>
                <div className="data-card-actions">
                  <button className="btn-text" onClick={() => openEdit(ws)}>编辑</button>
                  <button className="btn-text btn-text-danger" onClick={() => handleDelete(ws.id)}>删除</button>
                </div>
              </div>
              <div className="data-card-title">{ws.title}</div>
              <div className="data-card-content">{ws.content}</div>
            </div>
          ))}
        </div>
      )}
      {showModal && (
        <EditModal title={editingItem ? '编辑世界观' : '新增世界观'} onClose={() => setShowModal(false)}>
          <div className="form-group">
            <label>分类</label>
            <input type="text" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="如：力量体系、社会结构" />
          </div>
          <div className="form-group">
            <label>标题</label>
            <input type="text" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="设定名称" />
          </div>
          <div className="form-group">
            <label>内容</label>
            <textarea value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} placeholder="详细描述" rows={4} />
          </div>
          <div className="form-actions">
            <button className="btn btn-secondary" onClick={() => setShowModal(false)}>取消</button>
            <button className="btn btn-primary" onClick={handleSubmit}>保存</button>
          </div>
        </EditModal>
      )}
    </div>
  )
}

// Characters Tab
function CharactersTab({ characters, loading, onLoad, projectId }: {
  characters: Character[]; loading: boolean; onLoad: () => void; projectId: string
}) {
  const [showModal, setShowModal] = useState(false)
  const [editingItem, setEditingItem] = useState<Character | null>(null)
  const [form, setForm] = useState({ name: '', role: 'protagonist', description: '', traits: '', alias: '' })

  const handleSubmit = async () => {
    const url = editingItem
      ? `/projects/${projectId}/characters/${editingItem.id}`
      : `/projects/${projectId}/characters`
    const res = editingItem
      ? await put(url, form)
      : await post(url, form)
    if (res.ok) {
      setShowModal(false)
      setEditingItem(null)
      setForm({ name: '', role: 'protagonist', description: '', traits: '', alias: '' })
      onLoad()
    } else {
      alert(res.error?.message || '操作失败')
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除此角色？')) return
    const res = await del(`/projects/${projectId}/characters/${id}`)
    if (res.ok) onLoad()
    else alert(res.error?.message || '删除失败')
  }

  const openEdit = (item: Character) => {
    setEditingItem(item)
    setForm({ name: item.name, role: item.role, description: item.description || '', traits: item.traits || '', alias: item.alias || '' })
    setShowModal(true)
  }

  const openAdd = () => {
    setEditingItem(null)
    setForm({ name: '', role: 'protagonist', description: '', traits: '', alias: '' })
    setShowModal(true)
  }

  const roleLabels: Record<string, string> = { protagonist: '主角', antagonist: '反派', supporting: '配角' }

  if (loading) return <div style={{ padding: '24px', textAlign: 'center' }}>加载中...</div>

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <h3 style={{ margin: 0, fontSize: '16px' }}>角色设定</h3>
        <button className="btn btn-primary btn-sm" onClick={openAdd}>+ 新增</button>
      </div>
      {characters.length === 0 ? (
        <div className="data-empty">
          <div className="data-empty-icon">角</div>
          <div className="data-empty-title">暂无角色设定</div>
          <div className="data-empty-desc">添加角色信息，帮助 AI 保持人物一致性</div>
          <button className="btn btn-secondary" onClick={openAdd} style={{ marginTop: '12px' }}>添加第一个</button>
        </div>
      ) : (
        <div className="data-grid">
          {characters.map((ch) => (
            <div key={ch.id} className="data-card">
              <div className="data-card-header">
                <span className="data-card-badge">{roleLabels[ch.role] || ch.role}</span>
                <div className="data-card-actions">
                  <button className="btn-text" onClick={() => openEdit(ch)}>编辑</button>
                  <button className="btn-text btn-text-danger" onClick={() => handleDelete(ch.id)}>删除</button>
                </div>
              </div>
              <div className="data-card-title">{ch.name}{ch.alias ? ` (${ch.alias})` : ''}</div>
              {ch.description && <div className="data-card-content">{ch.description}</div>}
              {ch.traits && <div className="data-card-traits">特征: {ch.traits}</div>}
            </div>
          ))}
        </div>
      )}
      {showModal && (
        <EditModal title={editingItem ? '编辑角色' : '新增角色'} onClose={() => setShowModal(false)}>
          <div className="form-group">
            <label>名称</label>
            <input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="角色名称" />
          </div>
          <div className="form-group">
            <label>别名</label>
            <input type="text" value={form.alias} onChange={(e) => setForm({ ...form, alias: e.target.value })} placeholder="别名/外号（可选）" />
          </div>
          <div className="form-group">
            <label>角色</label>
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="protagonist">主角</option>
              <option value="antagonist">反派</option>
              <option value="supporting">配角</option>
            </select>
          </div>
          <div className="form-group">
            <label>描述</label>
            <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="角色描述" rows={3} />
          </div>
          <div className="form-group">
            <label>特征</label>
            <input type="text" value={form.traits} onChange={(e) => setForm({ ...form, traits: e.target.value })} placeholder="性格特征，用逗号分隔" />
          </div>
          <div className="form-actions">
            <button className="btn btn-secondary" onClick={() => setShowModal(false)}>取消</button>
            <button className="btn btn-primary" onClick={handleSubmit}>保存</button>
          </div>
        </EditModal>
      )}
    </div>
  )
}

// Outline Tab
function OutlineTab({ outlines, loading, onLoad, projectId }: {
  outlines: Outline[]; loading: boolean; onLoad: () => void; projectId: string
}) {
  const [showModal, setShowModal] = useState(false)
  const [editingItem, setEditingItem] = useState<Outline | null>(null)
  const [form, setForm] = useState({ level: 'volume', phase: '', chapters: '', summary: '', key_events: '', notes: '' })

  const handleSubmit = async () => {
    const url = editingItem
      ? `/projects/${projectId}/outlines/${editingItem.id}`
      : `/projects/${projectId}/outlines`
    const res = editingItem
      ? await put(url, form)
      : await post(url, form)
    if (res.ok) {
      setShowModal(false)
      setEditingItem(null)
      setForm({ level: 'volume', phase: '', chapters: '', summary: '', key_events: '', notes: '' })
      onLoad()
    } else {
      alert(res.error?.message || '操作失败')
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除此大纲条目？')) return
    const res = await del(`/projects/${projectId}/outlines/${id}`)
    if (res.ok) onLoad()
    else alert(res.error?.message || '删除失败')
  }

  const openEdit = (item: Outline) => {
    setEditingItem(item)
    setForm({ level: item.level, phase: item.phase || '', chapters: item.chapters || '', summary: item.summary || '', key_events: item.key_events || '', notes: item.notes || '' })
    setShowModal(true)
  }

  const openAdd = () => {
    setEditingItem(null)
    setForm({ level: 'volume', phase: '', chapters: '', summary: '', key_events: '', notes: '' })
    setShowModal(true)
  }

  const levelLabels: Record<string, string> = { volume: '卷', arc: '篇章', chapter: '章节' }

  if (loading) return <div style={{ padding: '24px', textAlign: 'center' }}>加载中...</div>

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <h3 style={{ margin: 0, fontSize: '16px' }}>故事大纲</h3>
        <button className="btn btn-primary btn-sm" onClick={openAdd}>+ 新增</button>
      </div>
      {outlines.length === 0 ? (
        <div className="data-empty">
          <div className="data-empty-icon">纲</div>
          <div className="data-empty-title">暂无大纲设定</div>
          <div className="data-empty-desc">添加故事大纲，帮助 AI 理解整体剧情走向</div>
          <button className="btn btn-secondary" onClick={openAdd} style={{ marginTop: '12px' }}>添加第一条</button>
        </div>
      ) : (
        <div className="data-grid">
          {outlines.map((ol) => (
            <div key={ol.id} className="data-card">
              <div className="data-card-header">
                <span className="data-card-badge">{levelLabels[ol.level] || ol.level}</span>
                {ol.chapters && <span className="data-card-chapters">章节: {ol.chapters}</span>}
                <div className="data-card-actions">
                  <button className="btn-text" onClick={() => openEdit(ol)}>编辑</button>
                  <button className="btn-text btn-text-danger" onClick={() => handleDelete(ol.id)}>删除</button>
                </div>
              </div>
              {ol.phase && <div className="data-card-title">{ol.phase}</div>}
              {ol.summary && <div className="data-card-content">{ol.summary}</div>}
              {ol.key_events && <div className="data-card-events">关键事件: {ol.key_events}</div>}
            </div>
          ))}
        </div>
      )}
      {showModal && (
        <EditModal title={editingItem ? '编辑大纲' : '新增大纲'} onClose={() => setShowModal(false)}>
          <div className="form-group">
            <label>层级</label>
            <select value={form.level} onChange={(e) => setForm({ ...form, level: e.target.value })}>
              <option value="volume">卷</option>
              <option value="arc">篇章</option>
              <option value="chapter">章节</option>
            </select>
          </div>
          <div className="form-group">
            <label>阶段名称</label>
            <input type="text" value={form.phase} onChange={(e) => setForm({ ...form, phase: e.target.value })} placeholder="如：第一卷" />
          </div>
          <div className="form-group">
            <label>章节范围</label>
            <input type="text" value={form.chapters} onChange={(e) => setForm({ ...form, chapters: e.target.value })} placeholder="如：1-10" />
          </div>
          <div className="form-group">
            <label>剧情概述</label>
            <textarea value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} placeholder="剧情概述" rows={3} />
          </div>
          <div className="form-group">
            <label>关键事件</label>
            <textarea value={form.key_events} onChange={(e) => setForm({ ...form, key_events: e.target.value })} placeholder="关键事件，用逗号分隔" rows={2} />
          </div>
          <div className="form-group">
            <label>备注</label>
            <input type="text" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="备注（可选）" />
          </div>
          <div className="form-actions">
            <button className="btn btn-secondary" onClick={() => setShowModal(false)}>取消</button>
            <button className="btn btn-primary" onClick={handleSubmit}>保存</button>
          </div>
        </EditModal>
      )}
    </div>
  )
}

function WorkspaceStyles() {
  return (
    <style>{`
      .workspace-layout { display: flex; flex-direction: column; height: calc(100vh - var(--topbar-height)); margin: calc(-1 * var(--spacing-lg)); }
      .ws-topbar { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; background: var(--bg-primary); border-bottom: 1px solid var(--border-color); min-height: 44px; }
      .ws-topbar-left { display: flex; align-items: center; gap: 16px; }
      .ws-back-link { color: var(--text-secondary); text-decoration: none; font-size: 13px; }
      .ws-back-link:hover { color: var(--primary); }
      .ws-project-name { font-weight: 600; font-size: 15px; }
      .ws-chapter-info { font-size: 13px; color: var(--text-muted); }
      .ws-topbar-right { display: flex; align-items: center; gap: 8px; }
      .ws-body { display: flex; flex: 1; overflow: hidden; }
      .ws-left { width: 220px; flex-shrink: 0; overflow-y: auto; }
      .ws-center { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
      .ws-right { width: 260px; flex-shrink: 0; overflow-y: auto; }
      .ws-tabs { display: flex; border-bottom: 1px solid var(--border-color); background: var(--bg-primary); padding: 0 16px; }
      .ws-tab { padding: 10px 16px; border: none; background: none; cursor: pointer; font-size: 14px; color: var(--text-secondary); border-bottom: 2px solid transparent; transition: all 0.15s; }
      .ws-tab:hover { color: var(--text-primary); }
      .ws-tab.active { color: var(--primary); border-bottom-color: var(--primary); font-weight: 500; }
      .ws-tab-disabled { color: var(--text-muted); cursor: default; }
      .ws-tab-content { flex: 1; overflow-y: auto; padding: 16px; }
      .empty-chapter { text-align: center; padding: 60px 20px; }
      .empty-chapter-num { font-size: 24px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px; }
      .empty-chapter-title { font-size: 18px; color: var(--text-secondary); margin-bottom: 16px; }
      .empty-chapter-hint { font-size: 16px; color: var(--text-secondary); margin-bottom: 8px; }
      .empty-chapter-desc { font-size: 14px; color: var(--text-muted); }
      .chapter-meta { display: flex; gap: 16px; font-size: 12px; color: var(--text-muted); margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--border-color); }
      .chapter-content-title { font-size: 22px; font-weight: 600; margin-bottom: 24px; text-align: center; }
      .chapter-content-body { max-width: 720px; margin: 0 auto; font-size: 16px; line-height: 1.9; color: var(--text-primary); white-space: pre-wrap; word-break: break-word; }
      .gen-step { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 6px; background: var(--bg-secondary); margin-bottom: 6px; }
      .gen-step-icon { width: 26px; height: 26px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 600; background: #e5e7eb; color: #6b7280; }
      .gen-step-active .gen-step-icon { background: #dbeafe; color: #2563eb; animation: gen-pulse 1.5s infinite; }
      .gen-step-complete .gen-step-icon { background: #dcfce7; color: #16a34a; }
      .gen-step-failed .gen-step-icon { background: #fee2e2; color: #dc2626; }
      .gen-step-label { font-size: 14px; color: var(--text-secondary); }
      .gen-step-complete .gen-step-label { color: var(--text-primary); }
      .gen-step-failed .gen-step-label { color: #dc2626; }
      @keyframes gen-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
      .artifacts-empty { text-align: center; padding: 60px 20px; }
      .artifacts-empty-icon { display: inline-flex; align-items: center; justify-content: center; min-width: 52px; height: 28px; padding: 0 10px; border-radius: 999px; background: var(--bg-tertiary); color: var(--text-secondary); font-size: 13px; margin-bottom: 16px; }
      .artifacts-empty-title { font-size: 16px; font-weight: 500; margin-bottom: 8px; }
      .artifacts-empty-desc { font-size: 14px; color: var(--text-muted); max-width: 480px; margin: 0 auto; line-height: 1.7; }
      .artifacts-grid { display: flex; flex-direction: column; gap: 12px; }
      .artifact-card { padding: 16px; border-radius: 8px; background: var(--bg-secondary); border: 1px solid var(--border-color); }
      .artifact-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
      .artifact-icon { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 50%; background: var(--bg-tertiary); color: var(--primary); font-size: 12px; font-weight: 600; }
      .artifact-label { font-weight: 500; font-size: 14px; flex: 1; }
      .artifact-status { color: #16a34a; font-size: 14px; }
      .artifact-summary { font-size: 13px; color: var(--text-primary); line-height: 1.6; padding: 10px 12px; background: #f0fdf4; border-radius: 4px; }
      .artifact-preview-section { margin-top: 10px; }
      .preview-toggle { padding: 4px 12px; font-size: 12px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--bg-primary); color: var(--text-secondary); cursor: pointer; transition: all 0.15s; }
      .preview-toggle:hover { background: var(--bg-tertiary); color: var(--primary); }
      .artifact-preview-expanded { background: var(--bg-tertiary); border-radius: 4px; padding: 10px 12px; }
      .artifact-preview-expanded .preview-content { font-size: 12px; color: var(--text-secondary); white-space: pre-wrap; line-height: 1.6; }
      .artifact-preview-expanded .preview-toggle { margin-top: 8px; }
      .history-item { display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; border-radius: 6px; background: var(--bg-secondary); margin-bottom: 6px; }
      .history-item-left { display: flex; align-items: center; gap: 12px; }
      .history-item-time { font-size: 12px; color: var(--text-muted); }
      .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
      .modal-content { background: var(--bg-primary); border-radius: 8px; width: 90%; max-width: 480px; max-height: 80vh; overflow-y: auto; }
      .modal-header { display: flex; align-items: center; justify-content: space-between; padding: 16px; border-bottom: 1px solid var(--border-color); }
      .modal-header h3 { margin: 0; font-size: 16px; }
      .modal-close { border: none; background: none; font-size: 24px; cursor: pointer; color: var(--text-muted); line-height: 1; }
      .modal-close:hover { color: var(--text-primary); }
      .modal-body { padding: 16px; }
      .data-empty { text-align: center; padding: 40px 20px; }
      .data-empty-icon { display: inline-flex; align-items: center; justify-content: center; width: 48px; height: 48px; border-radius: 50%; background: var(--bg-tertiary); color: var(--text-muted); font-size: 20px; margin-bottom: 16px; }
      .data-empty-title { font-size: 16px; font-weight: 500; margin-bottom: 8px; }
      .data-empty-desc { font-size: 14px; color: var(--text-muted); }
      .data-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
      .data-card { padding: 14px; border-radius: 8px; background: var(--bg-secondary); border: 1px solid var(--border-color); }
      .data-card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
      .data-card-category { font-size: 12px; padding: 2px 8px; border-radius: 4px; background: var(--bg-tertiary); color: var(--text-secondary); }
      .data-card-badge { font-size: 12px; padding: 2px 8px; border-radius: 4px; background: #dbeafe; color: #1d4ed8; }
      .data-card-chapters { font-size: 12px; color: var(--text-muted); margin-left: auto; }
      .data-card-actions { margin-left: auto; display: flex; gap: 8px; }
      .data-card-title { font-weight: 500; font-size: 15px; margin-bottom: 6px; }
      .data-card-content { font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 6px; }
      .data-card-traits, .data-card-events { font-size: 12px; color: var(--text-muted); }
      .btn-text { border: none; background: none; color: var(--primary); cursor: pointer; font-size: 13px; padding: 0; }
      .btn-text:hover { text-decoration: underline; }
      .btn-text-danger { color: #dc2626; }
      .form-group { margin-bottom: 14px; }
      .form-group label { display: block; font-size: 13px; font-weight: 500; margin-bottom: 6px; color: var(--text-secondary); }
      .form-group input, .form-group textarea, .form-group select { width: 100%; padding: 8px 10px; border: 1px solid var(--border-color); border-radius: 6px; font-size: 14px; background: var(--bg-primary); color: var(--text-primary); }
      .form-group input:focus, .form-group textarea:focus, .form-group select:focus { outline: none; border-color: var(--primary); }
      .form-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; }
    `}</style>
  )
}
