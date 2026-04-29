import { useEffect, useState, useCallback } from 'react'
import { useParams, useSearchParams, useNavigate, Link } from 'react-router-dom'
import { get, post } from '../lib/api'
import ChapterNav from '../components/ChapterNav'
import WorkflowTimeline from '../components/WorkflowTimeline'
import ContextSidebar from '../components/ContextSidebar'
import ErrorState from '../components/ErrorState'
import { tWorkflowStatus } from '../lib/i18n'
import { useSSEStream, SSEEvent, StepStatus } from '../hooks/useSSEStream'
import ProjectModuleNav, { ProjectModule } from '../components/project/ProjectModuleNav'
import WorldSettingsModule from '../components/project/WorldSettingsModule'
import CharactersModule from '../components/project/CharactersModule'
import FactionsModule from '../components/project/FactionsModule'
import OutlinesModule from '../components/project/OutlinesModule'
import PlotHolesModule from '../components/project/PlotHolesModule'
import InstructionsModule from '../components/project/InstructionsModule'
import ProjectOverviewModule from '../components/project/ProjectOverviewModule'
import ProjectSettingsModule from '../components/project/ProjectSettingsModule'
import GenesisModule from '../components/project/GenesisModule'
import MemoryUpdatesModule from '../components/project/MemoryUpdatesModule'
import FactLedgerModule from '../components/project/FactLedgerModule'
import StyleGuideModule from '../components/project/StyleGuideModule'
import ReviewModule from '../components/project/ReviewModule'
import RunsModule from '../components/project/RunsModule'

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
    target_words: number
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

type TabKey = 'content' | 'workflow' | 'artifacts' | 'history'

const GENERATABLE_CHAPTER_STATUSES = new Set([
  'planned',
  'pending',
  'scripted',
  'drafted',
  'polished',
  'revision',
  'blocking',
])

const GENERATING_STEPS = [
  { key: 'screenwriter', label: '编剧' },
  { key: 'author', label: '执笔' },
  { key: 'polisher', label: '润色' },
  { key: 'editor', label: '审核' },
  { key: 'publish', label: '发布' },
]

function getNextGeneratableChapter(chapters: Chapter[], currentChapter: number): number | null {
  const nextChapter = chapters
    .filter((chapter) => (
      chapter.chapter_number > currentChapter
      && GENERATABLE_CHAPTER_STATUSES.has(chapter.status)
      && chapter.status !== 'published'
    ))
    .sort((a, b) => a.chapter_number - b.chapter_number)[0]

  return nextChapter?.chapter_number ?? null
}

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
  const [sseSteps, setSseSteps] = useState<Record<string, StepStatus>>({})

  const currentChapter = parseInt(searchParams.get('chapter') || '1', 10)
  const activeModule: ProjectModule = (searchParams.get('module') as ProjectModule) || 'chapters'

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
      setSearchParams({ chapter: String(workspace.chapters[0].chapter_number), module: activeModule }, { replace: true })
    }
  }, [workspace]) // eslint-disable-line react-hooks/exhaustive-deps

  // Load chapter detail when chapter changes (only for chapters module)
  useEffect(() => {
    if (!id || !currentChapter || activeModule !== 'chapters') return
    setChapterLoading(true)
    setChapterDetail(null)
    setRunDetail(null)
    setGenError('')
    get<ChapterDetail>(`/projects/${id}/chapters/${currentChapter}`)
      .then((res) => {
        if (res.ok && res.data) setChapterDetail(res.data)
        setChapterLoading(false)
      })
  }, [id, currentChapter, activeModule])

  const loadRunDetail = (runId: string) => {
    get<RunDetailData>(`/runs/${runId}`)
      .then((res) => { if (res.ok && res.data) setRunDetail(res.data) })
  }

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
    setSearchParams({ chapter: String(chapterNumber), module: 'chapters' }, { replace: true })
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
    startStream(id, currentChapter)
  }

  const handleViewWorkflow = (runId: string) => {
    loadRunDetail(runId)
    setActiveTab('workflow')
  }

  const handleViewContent = () => setActiveTab('content')

  const handleGenerateNext = () => {
    const next = getNextGeneratableChapter(workspace?.chapters || [], currentChapter)
    if (!next) return
    setSearchParams({ chapter: String(next), module: 'chapters' }, { replace: true })
    if (!id) return
    setGenerating(true)
    setGenError('')
    setGenErrorDetails(null)
    setSseSteps({})
    setActiveTab('workflow')
    startStream(id, next)
  }

  const handleNavigateToRun = () => {
    navigate(`/run?project_id=${id}&chapter=${currentChapter}`)
  }

  const handlePublishChapter = () => {
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

  const handleModuleChange = (module: ProjectModule) => {
    setSearchParams({ module, ...(module === 'chapters' ? { chapter: String(currentChapter) } : {}) }, { replace: true })
  }

  if (loading) return <div style={{ padding: '40px', textAlign: 'center' }}>加载中...</div>
  if (error || !workspace) return <ErrorState title="加载失败" message={error || '项目不存在'} onRetry={loadWorkspace} />

  const currentCh = workspace.chapters.find((c) => c.chapter_number === currentChapter) || null
  const hasContent = (chapterDetail?.word_count || 0) > 0
  const isStub = llmMode === 'stub'
  const runsForChapter = workspace.recent_runs.filter((r) => r.chapter_number === currentChapter)
  const nextGeneratableChapter = getNextGeneratableChapter(workspace.chapters, currentChapter)

  return (
    <div className="workspace-layout">
      <WorkspaceTopbar
        projectName={workspace.project.name}
        currentChapter={currentChapter}
        publishedCount={workspace.stats.status_counts?.published || 0}
        isStub={isStub}
      />
      <ProjectModuleNav activeModule={activeModule} onModuleChange={handleModuleChange} />
      {activeModule === 'chapters' ? (
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
            <ChapterTabBar activeTab={activeTab} onTabChange={handleTabChange} hasRuns={runsForChapter.length > 0} />
            <div className="ws-tab-content">
              <ChapterTabContent
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
                sseSteps={sseSteps}
                isStreaming={isStreaming}
                projectId={id || ''}
              />
            </div>
          </div>
          <div className="ws-right">
            <ContextSidebar
              currentChapter={currentCh}
              chapterNumber={currentChapter}
              llmMode={llmMode}
              recentRuns={runsForChapter}
              totalChapters={workspace.project.total_chapters_planned}
              nextChapterNumber={nextGeneratableChapter}
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
      ) : (
        <div className="ws-module-content">
          <ModuleRouter
            module={activeModule}
            projectId={id || ''}
            project={workspace.project}
            stats={workspace.stats}
            onWorkspaceChange={loadWorkspace}
          />
        </div>
      )}
      <WorkspaceStyles />
    </div>
  )
}

function ModuleRouter({
  module,
  projectId,
  project,
  stats,
  onWorkspaceChange,
}: {
  module: ProjectModule
  projectId: string
  project: Workspace['project']
  stats: Workspace['stats']
  onWorkspaceChange: () => void
}) {
  switch (module) {
    case 'overview':
      return <ProjectOverviewModule project={project} stats={stats} />
    case 'genesis':
      return <GenesisModule projectId={projectId} />
    case 'worldview':
      return <WorldSettingsModule projectId={projectId} />
    case 'characters':
      return <CharactersModule projectId={projectId} />
    case 'factions':
      return <FactionsModule projectId={projectId} />
    case 'outline':
      return <OutlinesModule projectId={projectId} />
    case 'plots':
      return <PlotHolesModule projectId={projectId} />
    case 'instructions':
      return <InstructionsModule projectId={projectId} />
    case 'memory':
      return <MemoryUpdatesModule projectId={projectId} />
    case 'facts':
      return <FactLedgerModule projectId={projectId} />
    case 'style':
      return <StyleGuideModule projectId={projectId} />
    case 'review':
      return <ReviewModule projectId={projectId} />
    case 'runs':
      return <RunsModule projectId={projectId} />
    case 'settings':
      return <ProjectSettingsModule projectId={projectId} onSaved={onWorkspaceChange} />
    default:
      return null
  }
}

function WorkspaceTopbar({ projectName, currentChapter, publishedCount, isStub }: {
  projectName: string; currentChapter: number; publishedCount: number; isStub: boolean
}) {
  return (
    <div className="ws-topbar">
      <div className="ws-topbar-left">
        <a href="/projects" className="ws-back-link">&larr; 返回项目列表</a>
        <span className="ws-project-name">{projectName}</span>
        <span className="ws-chapter-info">第 {currentChapter} 章 &middot; 已发布 {publishedCount} 章</span>
      </div>
      <div className="ws-topbar-right">
        <span className={`status-badge ${isStub ? 'status-stub' : 'status-real'}`}>
          {isStub ? '演示模式' : '真实 LLM'}
        </span>
      </div>
    </div>
  )
}

function ChapterTabBar({ activeTab, onTabChange, hasRuns }: {
  activeTab: TabKey; onTabChange: (t: TabKey) => void; hasRuns: boolean
}) {
  const tabs: { key: TabKey; label: string; disabled?: boolean }[] = [
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

function ChapterTabContent({ activeTab, generating, genError, genErrorDetails, chapterLoading, hasContent, isStub,
  currentChapter, chapterDetail, runDetail, runsForChapter, onGenerate, onViewWorkflow,
  sseSteps, isStreaming, projectId,
}: {
  activeTab: TabKey; generating: boolean; genError: string
  genErrorDetails: { missing?: string[]; actions?: string[] } | null
  chapterLoading: boolean; hasContent: boolean; isStub: boolean; currentChapter: number
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
      return <WorkflowTab runDetail={runDetail} generating={generating} sseSteps={sseSteps} isStreaming={isStreaming} />
    case 'artifacts':
      return <ArtifactsTab runDetail={runDetail} />
    case 'history':
      return <HistoryTab runsForChapter={runsForChapter} onViewWorkflow={onViewWorkflow} currentChapter={currentChapter} />
    default:
      return null
  }
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

function ContentTab({ generating, genError, genErrorDetails, chapterLoading, hasContent, isStub,
  currentChapter, chapterDetail, onGenerate, sseSteps, projectId,
}: {
  generating: boolean; genError: string
  genErrorDetails: { missing?: string[]; actions?: string[] } | null
  chapterLoading: boolean; hasContent: boolean; isStub: boolean; currentChapter: number; chapterDetail: ChapterDetail | null
  onGenerate: () => void; sseSteps: Record<string, StepStatus>; projectId: string
}) {
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
        <div className="alert alert-error" style={{ marginBottom: '16px' }}>
          <strong>生成失败</strong>
          <div style={{ marginTop: '4px' }}>{genError}</div>
          {genErrorDetails?.missing && genErrorDetails.missing.length > 0 && (
            <div style={{ marginTop: '12px' }}>
              <div style={{ fontWeight: 600, fontSize: '13px' }}>缺失项</div>
              <ul style={{ margin: '6px 0 0', paddingLeft: '18px' }}>
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

function WorkflowTab({ runDetail, generating, sseSteps, isStreaming }: {
  runDetail: RunDetailData | null; generating: boolean; sseSteps: Record<string, StepStatus>; isStreaming: boolean
}) {
  if (runDetail && !isStreaming) return <WorkflowTimeline steps={runDetail.steps} />

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
      .ws-module-content { flex: 1; overflow-y: auto; padding: 20px 24px; }
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
      .project-module { max-width: 960px; }
      .module-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
      .module-header h3 { display: flex; align-items: center; gap: 8px; margin: 0; font-size: 16px; font-weight: 600; }
      .module-loading { padding: 40px; text-align: center; color: var(--text-muted); }
      .data-empty { text-align: center; padding: 40px 20px; }
      .data-empty-icon { display: inline-flex; align-items: center; justify-content: center; width: 48px; height: 48px; border-radius: 50%; background: var(--bg-tertiary); color: var(--text-muted); margin-bottom: 16px; }
      .data-empty-title { font-size: 16px; font-weight: 500; margin-bottom: 8px; }
      .data-empty-desc { font-size: 14px; color: var(--text-muted); }
      .data-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
      .data-card { padding: 14px; border-radius: 8px; background: var(--bg-secondary); border: 1px solid var(--border-color); }
      .data-card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
      .data-card-category { font-size: 12px; padding: 2px 8px; border-radius: 4px; background: var(--bg-tertiary); color: var(--text-secondary); }
      .data-card-badge { font-size: 12px; padding: 2px 8px; border-radius: 4px; background: #dbeafe; color: #1d4ed8; }
      .data-card-range { font-size: 12px; color: var(--text-muted); }
      .data-card-actions { margin-left: auto; display: flex; gap: 4px; }
      .data-card-title { font-weight: 500; font-size: 15px; margin-bottom: 6px; }
      .data-card-content { font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 6px; }
      .data-card-traits { font-size: 12px; color: var(--text-muted); }
      .btn-icon { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: none; background: none; cursor: pointer; border-radius: 4px; color: var(--text-secondary); transition: all 0.15s; }
      .btn-icon:hover { background: var(--bg-tertiary); color: var(--primary); }
      .btn-icon-danger:hover { background: #fee2e2; color: #dc2626; }
      .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
      .modal { background: var(--bg-primary); border-radius: 8px; width: 90%; max-width: 520px; max-height: 80vh; overflow-y: auto; padding: 24px; }
      .modal h3 { margin: 0 0 20px; font-size: 16px; }
      .form-group { margin-bottom: 14px; }
      .form-group label { display: block; font-size: 13px; font-weight: 500; margin-bottom: 6px; color: var(--text-secondary); }
      .form-group input, .form-group textarea, .form-group select { width: 100%; padding: 8px 10px; border: 1px solid var(--border-color); border-radius: 6px; font-size: 14px; background: var(--bg-primary); color: var(--text-primary); box-sizing: border-box; }
      .form-group input:focus, .form-group textarea:focus, .form-group select:focus { outline: none; border-color: var(--primary); }
      .form-group input:disabled { opacity: 0.6; cursor: not-allowed; }
      .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
      .form-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; }
      .status-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; }
      .status-stub { background: #fef3c7; color: #92400e; }
      .status-real { background: #dcfce7; color: #166534; }
    `}</style>
  )
}
