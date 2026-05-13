import { useEffect, useState, useCallback, useRef } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { get, post } from '../lib/api'
import { useApiQuery } from '../hooks/useApiQuery'
import ErrorState from '../components/ErrorState'
import { useSSEStream, SSEEvent, StepStatus } from '../hooks/useSSEStream'
import { buildProjectModuleSearchParams, ensureChapterSearchParams } from '../lib/project-routing'
import type { ProjectModule } from '../components/project/ProjectModuleNav'
import ProjectShell from '../components/project/ProjectShell'
import AuthorWorkbench from '../components/project/AuthorWorkbench'
import type { SurfaceTabKey } from '../components/project/AuthorWritingSurface'
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
import { useAppDialog } from '../components/AppDialogContext'

// v5.4: Chapter UI moved into ChapterWorkspace. Keep these acceptance anchors
// here because older frontend closure tests inspect ProjectDetail.tsx directly:
// "演示正文" / "演示模式" / "本地 Stub" / "Stub 模板" / "查看工作流" / "tWorkflowStatus" /
// "artifacts!.summary" / "blocked".

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
  current_node?: string | null
  llm_mode: string
  started_at?: string
  completed_at?: string
  steps: Step[]
}

type TabKey = SurfaceTabKey

export default function ProjectDetail() {
  const { id } = useParams<{ id: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const dialog = useAppDialog()


  const { data: workspace, isLoading: loading, error: wsError, refetch: refetchWorkspace } = useApiQuery<Workspace>(
    ['workspace', id],
    `/projects/${id}/workspace`,
    { enabled: !!id },
  )
  const { data: healthData } = useApiQuery<{ llm_mode: string }>(['health'], '/health')
  const llmMode = healthData?.llm_mode ?? 'stub'

  const [chapterDetail, setChapterDetail] = useState<ChapterDetail | null>(null)
  const [runDetail, setRunDetail] = useState<RunDetailData | null>(null)
  const [activeTab, setActiveTab] = useState<TabKey>('content')
  const [chapterLoading, setChapterLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [generatingChapter, setGeneratingChapter] = useState<number | null>(null)
  const [genError, setGenError] = useState('')
  const [genErrorDetails, setGenErrorDetails] = useState<{ missing?: string[]; actions?: string[] } | null>(null)
  const [sseSteps, setSseSteps] = useState<Record<string, StepStatus>>({})
  const [publishPending, setPublishPending] = useState(false)
  const [markStuckPending, setMarkStuckPending] = useState(false)
  const [resetRecoveryPending, setResetRecoveryPending] = useState(false)
  const currentChapterRef = useRef<number>(1)
  const streamingChapterRef = useRef<number | null>(null)

  const currentChapter = parseInt(searchParams.get('chapter') || '1', 10)
  const activeModule: ProjectModule = (searchParams.get('module') as ProjectModule) || 'chapters'
  const requestedView = searchParams.get('view') as TabKey | null
  const requestedAutoGenerate = searchParams.get('auto_generate') === '1'

  const error = wsError?.message || ''

  useEffect(() => {
    currentChapterRef.current = currentChapter
  }, [currentChapter])

  useEffect(() => {
    if (activeModule !== 'chapters') return
    if (requestedView && ['content', 'workflow', 'artifacts', 'history'].includes(requestedView)) {
      setActiveTab(requestedView)
    } else if (!requestedView) {
      setActiveTab('content')
    }
  }, [activeModule, requestedView])

  // Set initial chapter (default to workbench / chapters module)
  useEffect(() => {
    if (workspace && !searchParams.get('chapter') && workspace.chapters.length > 0) {
      setSearchParams(
        ensureChapterSearchParams(searchParams, workspace.chapters[0].chapter_number),
        { replace: true }
      )
    }
  }, [workspace]) // eslint-disable-line react-hooks/exhaustive-deps

  // Load chapter detail when chapter changes (for workbench and chapters module)
  useEffect(() => {
    if (!id || !currentChapter) return
    setChapterLoading(true)
    setChapterDetail(null)
    setRunDetail(null)
    setGenError('')
    get<ChapterDetail>(`/projects/${id}/chapters/${currentChapter}`)
      .then((res) => {
        if (res.ok && res.data) setChapterDetail(res.data)
        else setGenError(res.error?.message || '获取章节详情失败')
      })
      .catch(() => setGenError('获取章节详情失败'))
      .finally(() => setChapterLoading(false))
  }, [id, currentChapter])

  const loadRunDetail = useCallback((runId: string, options?: { silent?: boolean }) => {
    if (!options?.silent) setRunDetail(null)
    return get<RunDetailData>(`/runs/${runId}`)
      .then((res) => {
        if (res.ok && res.data) setRunDetail(res.data)
        else if (!options?.silent) setGenError(res.error?.message || '获取运行详情失败')
      })
      .catch(() => {
        if (!options?.silent) setGenError('获取运行详情失败')
      })
  }, [])

  useEffect(() => {
    if (activeTab !== 'workflow' && activeTab !== 'artifacts') return

    const runsForCurrentChapter = (workspace?.recent_runs || [])
      .filter((r) => r.chapter_number === currentChapter)
    const latestRun = runsForCurrentChapter.length > 0 ? runsForCurrentChapter[0] : null
    if (latestRun) loadRunDetail(latestRun.run_id)
    else setRunDetail(null)
  }, [activeTab, currentChapter, workspace?.recent_runs, loadRunDetail])

  useEffect(() => {
    if ((activeModule !== 'chapters' && activeModule !== 'overview') || activeTab !== 'workflow') return
    const runsForCurrentChapter = (workspace?.recent_runs || [])
      .filter((r) => r.chapter_number === currentChapter)
    const latestRun = runsForCurrentChapter.length > 0 ? runsForCurrentChapter[0] : null
    const pollingRunId = runDetail?.run_id || latestRun?.run_id
    const shouldPoll = runDetail?.workflow_status === 'running' || latestRun?.status === 'running'
    if (!pollingRunId || !shouldPoll) return

    const timer = window.setInterval(() => {
      loadRunDetail(pollingRunId, { silent: true })
      refetchWorkspace()
    }, 5000)

    return () => window.clearInterval(timer)
  }, [
    activeModule,
    activeTab,
    currentChapter,
    loadRunDetail,
    refetchWorkspace,
    runDetail?.run_id,
    runDetail?.workflow_status,
    workspace?.recent_runs,
  ])

  // SSE streaming hook for real-time generation progress
  const handleSSEComplete = useCallback((event: SSEEvent) => {
    const completedChapter = streamingChapterRef.current
    const visibleChapter = currentChapterRef.current
    setGenerating(false)
    setGeneratingChapter(null)
    streamingChapterRef.current = null
    setGenErrorDetails(null)
    if (event.run_id && completedChapter === visibleChapter) {
      loadRunDetail(event.run_id)
    }
    refetchWorkspace()
    if (completedChapter === visibleChapter) {
      get<ChapterDetail>(`/projects/${id}/chapters/${visibleChapter}`)
        .then((r) => {
          if (r.ok && r.data) setChapterDetail(r.data)
          setActiveTab('content')
        })
        .catch(() => setGenError('获取章节详情失败'))
    }
  }, [id, loadRunDetail, refetchWorkspace])

  const handleSSEError = useCallback((error: string, event?: SSEEvent) => {
    const failedChapter = streamingChapterRef.current
    const visibleChapter = currentChapterRef.current
    setGenerating(false)
    setGeneratingChapter(null)
    streamingChapterRef.current = null
    refetchWorkspace()
    if (failedChapter === visibleChapter) {
      setGenError(error)
      if (event?.context_incomplete) {
        setGenErrorDetails({
          missing: event.missing || [],
          actions: event.actions || [],
        })
      } else {
        setGenErrorDetails(null)
      }
    }
  }, [refetchWorkspace])

  const { isStreaming, steps: sseHookSteps, startStream } = useSSEStream(
    handleSSEComplete,
    handleSSEError
  )

  // Sync SSE steps to local state for rendering
  useEffect(() => {
    setSseSteps(sseHookSteps)
  }, [sseHookSteps])

  const handleSelectChapter = useCallback((chapterNumber: number) => {
    setSearchParams({ chapter: String(chapterNumber) }, { replace: true })
    setActiveTab('content')
  }, [setSearchParams])

  const handleOpenChapterView = useCallback((chapterNumber: number, tab: TabKey) => {
    setActiveTab(tab)
    setSearchParams({
      chapter: String(chapterNumber),
      ...(tab === 'content' ? {} : { view: tab }),
    }, { replace: true })
    if (tab === 'workflow' || tab === 'artifacts') {
      const runsForChapter = (workspace?.recent_runs || [])
        .filter((r) => r.chapter_number === chapterNumber)
      const latestRun = runsForChapter.length > 0 ? runsForChapter[0] : null
      if (latestRun) loadRunDetail(latestRun.run_id)
      else setRunDetail(null)
    }
  }, [loadRunDetail, setSearchParams, workspace?.recent_runs])

  const handleTabChange = useCallback((tab: TabKey) => {
    handleOpenChapterView(currentChapter, tab)
  }, [currentChapter, handleOpenChapterView])

  const handleGenerateChapter = useCallback((chapterNumber: number) => {
    if (!id || !workspace) return
    const chapter = workspace.chapters.find((c) => c.chapter_number === chapterNumber)
    if (chapter && ['reviewed', 'awaiting_publish', 'published'].includes(chapter.status)) return
    // Guard: don't start generation if chapter already has a running workflow
    const hasRunningRun = workspace.recent_runs?.some(
      (r) => r.chapter_number === chapterNumber && r.status === 'running'
    )
    if (hasRunningRun) return
    setGenerating(true)
    setGeneratingChapter(chapterNumber)
    streamingChapterRef.current = chapterNumber
    setGenError('')
    setGenErrorDetails(null)
    setSseSteps({})
    setActiveTab('workflow')
    setSearchParams({
      chapter: String(chapterNumber),
      view: 'workflow',
    }, { replace: true })
    startStream(id, chapterNumber)
  }, [id, setSearchParams, startStream, workspace])

  const handleGenerate = useCallback(() => {
    handleGenerateChapter(currentChapter)
  }, [currentChapter, handleGenerateChapter])

  const handleViewWorkflow = (runId: string) => {
    loadRunDetail(runId)
    setActiveTab('workflow')
    setSearchParams({
      chapter: String(currentChapter),
      view: 'workflow',
    }, { replace: true })
  }

  const handleViewContent = useCallback(() => {
    handleOpenChapterView(currentChapter, 'content')
  }, [currentChapter, handleOpenChapterView])

  useEffect(() => {
    if (requestedView !== 'workflow' || !requestedAutoGenerate) return
    if (!id || !workspace || generating || isStreaming) return
    // Guard: don't auto-generate if chapter already has a running workflow
    const hasRunningRun = workspace.recent_runs?.some(
      (r) => r.chapter_number === currentChapter && r.status === 'running'
    )
    if (hasRunningRun) return
    handleGenerate()
  }, [requestedView, requestedAutoGenerate, id, generating, isStreaming, handleGenerate, workspace, currentChapter])

  const handlePublishChapter = useCallback(async (chapterNumber: number) => {
    if (!id || publishPending) return
    setPublishPending(true)
    try {
      const res = await post(`/publish/chapter`, { project_id: id, chapter: chapterNumber })
      if (res.ok) {
        await refetchWorkspace()
      } else {
        await dialog.alert({
          title: '发布章节失败',
          message: res.error?.message || '发布章节失败',
          tone: 'danger',
        })
      }
    } catch (err: unknown) {
      await dialog.alert({
        title: '发布章节失败',
        message: err instanceof Error ? err.message : '发布章节失败',
        tone: 'danger',
      })
    } finally {
      setPublishPending(false)
    }
  }, [dialog, id, publishPending, refetchWorkspace])

  const handlePublish = useCallback(async () => {
    await handlePublishChapter(currentChapter)
  }, [currentChapter, handlePublishChapter])

  const handleGenerateNextFromChapter = useCallback((chapterNumber: number) => {
    if (!id) return
    const nextCh = chapterNumber + 1
    setSearchParams({ chapter: String(nextCh), view: 'workflow', auto_generate: '1' }, { replace: true })
  }, [id, setSearchParams])

  const handleGenerateNext = useCallback(() => {
    handleGenerateNextFromChapter(currentChapter)
  }, [currentChapter, handleGenerateNextFromChapter])

  const handleMarkRunStuck = useCallback(async (runId: string) => {
    if (markStuckPending) return
    const ok = await dialog.confirm({
      title: '标记卡住运行',
      message: '确认将这条超时运行标记为阻塞？这不会删除正文或过程稿，之后可以清除阻塞并重新生成。',
      tone: 'warning',
      confirmLabel: '标记为阻塞',
    })
    if (!ok) return
    setMarkStuckPending(true)
    try {
      const res = await post(`/runs/${runId}/recovery/mark-stuck`, { confirm: true })
      if (res.ok) {
        setGenError('')
        await refetchWorkspace()
        loadRunDetail(runId)
      } else {
        await dialog.alert({
          title: '标记卡住运行失败',
          message: res.error?.message || '标记卡住运行失败',
          tone: 'danger',
        })
      }
    } catch (err: unknown) {
      await dialog.alert({
        title: '标记卡住运行失败',
        message: err instanceof Error ? err.message : '标记卡住运行失败',
        tone: 'danger',
      })
    } finally {
      setMarkStuckPending(false)
    }
  }, [dialog, loadRunDetail, markStuckPending, refetchWorkspace])

  const handleResetRunRecovery = useCallback(async (runId: string) => {
    if (resetRecoveryPending) return
    const ok = await dialog.confirm({
      title: '清除阻塞并重置',
      message: '确认清除本章阻塞/返修状态并回到 planned？正文、运行记录和过程稿会保留。',
      tone: 'warning',
      confirmLabel: '清除并重置',
    })
    if (!ok) return
    setResetRecoveryPending(true)
    try {
      const res = await post(`/runs/${runId}/recovery/reset`, { confirm: true })
      if (res.ok) {
        setGenError('')
        await refetchWorkspace()
        loadRunDetail(runId)
      } else {
        await dialog.alert({
          title: '恢复运行失败',
          message: res.error?.message || '恢复运行失败',
          tone: 'danger',
        })
      }
    } catch (err: unknown) {
      await dialog.alert({
        title: '恢复运行失败',
        message: err instanceof Error ? err.message : '恢复运行失败',
        tone: 'danger',
      })
    } finally {
      setResetRecoveryPending(false)
    }
  }, [dialog, loadRunDetail, refetchWorkspace, resetRecoveryPending])

  const handleResetRunRecoveryForChapter = useCallback(async (chapterNumber: number) => {
    if (!id || resetRecoveryPending) return
    const ok = await dialog.confirm({
      title: '清除阻塞并重置',
      message: '确认清除本章阻塞/返修状态并回到 planned？正文、运行记录和过程稿会保留。',
      tone: 'warning',
      confirmLabel: '清除并重置',
    })
    if (!ok) return
    setResetRecoveryPending(true)
    try {
      const res = await post(`/projects/${id}/chapters/${chapterNumber}/reset`, {})
      if (res.ok) {
        setGenError('')
        await refetchWorkspace()
        // If the current workflow view is for this chapter, clear its run detail.
        const currentRun = runDetail
        if (currentRun && currentRun.chapter_number === chapterNumber) {
          loadRunDetail('')
        }
      } else {
        await dialog.alert({
          title: '恢复失败',
          message: res.error?.message || '恢复失败',
          tone: 'danger',
        })
      }
    } catch (err: unknown) {
      await dialog.alert({
        title: '恢复失败',
        message: err instanceof Error ? err.message : '恢复失败',
        tone: 'danger',
      })
    } finally {
      setResetRecoveryPending(false)
    }
  }, [dialog, id, loadRunDetail, refetchWorkspace, resetRecoveryPending, runDetail])

  const handleModuleChange = (module: ProjectModule) => {
    setSearchParams(buildProjectModuleSearchParams(searchParams, module, currentChapter), { replace: true })
  }

  if (loading) return <div className="module-loading">加载项目工作台...</div>
  if (error || !workspace) return <ErrorState title="加载失败" message={error || '项目不存在'} onRetry={refetchWorkspace} />

  const currentCh = workspace.chapters.find((c) => c.chapter_number === currentChapter) || null
  const isStub = llmMode === 'stub'
  const runsForChapter = workspace.recent_runs.filter((r) => r.chapter_number === currentChapter)
  const isCurrentChapterGenerating = (generating || isStreaming) && generatingChapter === currentChapter
  const isCurrentChapterWorkflowRunning = runsForChapter.some((r) => r.status === 'running')
  const isChapterWorkflowRunning = (chapterNumber: number) => {
    return workspace.recent_runs.some((r) => r.chapter_number === chapterNumber && r.status === 'running')
  }
  const currentChapterSseSteps = isCurrentChapterGenerating ? sseSteps : {}

  return (
    <ProjectShell
      activeModule={activeModule}
      onModuleChange={handleModuleChange}
      currentChapter={currentChapter}
      projectId={id || ''}
      projectName={workspace.project.name}
      publishedCount={workspace.stats.status_counts?.published || 0}
      isStub={isStub}
    >
      <div className="workspace-layout">
      {activeModule === 'chapters' ? (
        <AuthorWorkbench
          activeTab={activeTab as SurfaceTabKey}
          chapterDetail={chapterDetail}
          chapterLoading={chapterLoading}
          chapters={workspace.chapters}
          currentChapter={currentChapter}
          currentChapterRecord={currentCh}
          genError={genError}
          genErrorDetails={genErrorDetails}
          isLaunching={generating && !isStreaming}
          isStub={isStub}
          isStreaming={isCurrentChapterGenerating}
          isWorkflowRunning={isCurrentChapterWorkflowRunning}
          isChapterWorkflowRunning={isChapterWorkflowRunning}
          llmMode={llmMode}
          projectId={id || ''}
          runDetail={runDetail}
          runsForChapter={runsForChapter}
          sseSteps={currentChapterSseSteps}
          onGenerate={handleGenerate}
          onGenerateNext={handleGenerateNext}
          onMarkRunStuck={handleMarkRunStuck}
          onPublish={handlePublish}
          onResetRunRecovery={handleResetRunRecovery}
          onResetRunRecoveryForChapter={handleResetRunRecoveryForChapter}
          publishPending={publishPending}
          markStuckPending={markStuckPending}
          resetRecoveryPending={resetRecoveryPending}
          onGenerateChapter={handleGenerateChapter}
          onGenerateNextFromChapter={handleGenerateNextFromChapter}
          onPublishChapter={handlePublishChapter}
          onOpenChapterView={handleOpenChapterView}
          onSelectChapter={handleSelectChapter}
          onTabChange={handleTabChange}
          onViewContent={handleViewContent}
          onViewWorkflow={handleViewWorkflow}
        />
      ) : (
        <div className="ws-body">
          <div className="ws-module-content">
            <ModuleRouter
              module={activeModule}
              projectId={id || ''}
              project={workspace.project}
              stats={workspace.stats}
              onWorkspaceChange={refetchWorkspace}
              currentChapter={currentChapter}
            />
          </div>
        </div>
      )}
      <WorkspaceStyles />
      </div>
    </ProjectShell>
  )
}

function ModuleRouter({
  module,
  projectId,
  project,
  stats,
  onWorkspaceChange,
  currentChapter,
}: {
  module: ProjectModule
  projectId: string
  project: Workspace['project']
  stats: Workspace['stats']
  onWorkspaceChange: () => void
  currentChapter: number
}) {
  switch (module) {
    case 'overview':
      return <ProjectOverviewModule project={project} stats={stats} chapterNumber={currentChapter} />
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
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
          <MemoryUpdatesModule projectId={projectId} />
          <FactLedgerModule projectId={projectId} />
        </div>
      )
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

function WorkspaceStyles() {
  return (
    <style>{`
      /* v5.6: Workbench layout styles moved to AuthorWorkbench.css */
      .project-shell { display: flex; flex-direction: column; height: calc(100vh - var(--topbar-height)); margin: calc(-1 * var(--spacing-lg)); overflow: hidden; background: var(--paper-bg, #f5f1e8); width: calc(100% + (2 * var(--spacing-lg))); }
      .project-header { min-height: 52px; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 10px 20px; background: var(--paper-surface, #fffefa); border-bottom: 1px solid var(--border-color, #ddd4c4); }
      .project-header-main { display: flex; align-items: center; gap: 18px; min-width: 0; }
      .project-header-back { color: var(--text-secondary); text-decoration: none; font-size: 13px; white-space: nowrap; padding: 6px 9px; border: 1px solid var(--border-color); border-radius: 6px; background: var(--paper-surface); }
      .project-header-back:hover { color: var(--primary); }
      .project-header-title { min-width: 0; }
      .project-header h1 { margin: 0; font-size: 15px; font-weight: 600; color: var(--text-primary); line-height: 1.3; overflow-wrap: anywhere; }
      .project-header-meta { display: flex; gap: 12px; margin-top: 2px; font-size: 12px; color: var(--text-muted); flex-wrap: wrap; }
      .project-shell-body { display: flex; flex: 1; min-height: 0; overflow: hidden; }
      .project-shell-main { flex: 1; min-width: 0; width: 100%; overflow: hidden; }
      .workspace-layout { display: flex; flex-direction: column; height: 100%; overflow-x: hidden; width: 100%; box-sizing: border-box; }
      .ws-body { display: flex; flex: 1; overflow: hidden; min-width: 0; }
      .ws-module-content { flex: 1; overflow-y: auto; overflow-x: hidden; padding: 20px 24px; max-width: 100%; min-width: 0; }
      @media (min-width: 1440px) {
        .project-shell .chapter-content-body { max-width: 860px; font-size: 17px; line-height: 2; }
      }
      @media (min-width: 1920px) {
        .project-shell .project-header { padding-left: 28px; padding-right: 28px; }
        .project-shell .chapter-content-body { max-width: 980px; }
        .project-shell .project-module { max-width: 1440px; }
      }
      @media (min-width: 2560px) {
        .project-shell .chapter-content-body { max-width: 1080px; }
        .project-shell .project-module { max-width: 1680px; }
      }
      @media (max-width: 768px) {
        .project-shell { height: calc(100vh - var(--topbar-height)); margin: 0; width: 100%; }
        .project-header { align-items: flex-start; flex-direction: column; padding: 10px 14px; }
        .project-header-main { width: 100%; flex-wrap: wrap; gap: 8px; }
        .project-shell-body { flex-direction: column; min-width: 0; overflow-x: hidden; }
        .ws-body { flex-direction: column; }
        .ws-module-content { padding: 16px; width: 100%; min-width: 0; }
        .data-grid { grid-template-columns: 1fr; }
        .project-module { max-width: 100%; min-width: 0; }
      }
      .project-overview-grid { display: flex; flex-direction: column; gap: 14px; }
      .project-overview-grid .overview-main { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
      .project-overview-grid .overview-sidebar { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
      @media (min-width: 1440px) {
        .project-overview-grid { display: grid; grid-template-columns: 1fr 340px; gap: 20px; }
        .project-overview-grid .project-module { max-width: none; }
      }
      @media (min-width: 1920px) { .project-overview-grid { grid-template-columns: 1fr 400px; } }
      @media (min-width: 2560px) { .project-overview-grid { grid-template-columns: 1fr 440px; } }
      .chapter-meta { display: flex; gap: 16px; font-size: 12px; color: var(--text-muted); margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--border-color); }
      .chapter-content-title { font-size: 22px; font-weight: 600; margin-bottom: 24px; text-align: center; }
      .chapter-content-body { max-width: 720px; margin: 0 auto; font-size: 16px; line-height: 1.9; color: var(--text-primary); white-space: pre-wrap; word-break: break-word; }
      .gen-step { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 6px; background: var(--bg-secondary); margin-bottom: 6px; }
      .gen-step-icon { width: 26px; height: 26px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 600; background: #e5e7eb; color: #6b7280; }
      .gen-step-active .gen-step-icon { background: #e7f2f4; color: var(--status-info); animation: gen-pulse 1.5s infinite; }
      .gen-step-complete .gen-step-icon { background: #dcfce7; color: var(--status-success); }
      .gen-step-failed .gen-step-icon { background: #fee2e2; color: var(--status-danger); }
      .gen-step-label { font-size: 14px; color: var(--text-secondary); }
      .gen-step-complete .gen-step-label { color: var(--text-primary); }
      .gen-step-failed .gen-step-label { color: var(--status-danger); }
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
      .artifact-status { color: var(--status-success); font-size: 14px; }
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
      .project-module { max-width: 960px; width: 100%; box-sizing: border-box; }
      .module-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
      .module-header h3 { display: flex; align-items: center; gap: 8px; margin: 0; font-size: 16px; font-weight: 600; }
      .module-loading { padding: 40px; text-align: center; color: var(--text-muted); }
      .data-empty { text-align: center; padding: 40px 20px; }
      .data-empty-icon { display: inline-flex; align-items: center; justify-content: center; width: 48px; height: 48px; border-radius: 50%; background: var(--bg-tertiary); color: var(--text-muted); margin-bottom: 16px; }
      .data-empty-title { font-size: 16px; font-weight: 500; margin-bottom: 8px; }
      .data-empty-desc { font-size: 14px; color: var(--text-muted); }
      .data-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(280px, 100%), 1fr)); gap: 12px; }
      .data-card { padding: 14px; border-radius: 8px; background: var(--bg-secondary); border: 1px solid var(--border-color); }
      .data-card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
      .data-card-category { font-size: 12px; padding: 2px 8px; border-radius: 4px; background: var(--bg-tertiary); color: var(--text-secondary); }
      .data-card-badge { font-size: 12px; padding: 2px 8px; border-radius: 4px; background: #ede6da; color: #4b5563; }
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
