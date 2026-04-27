import { useEffect, useState, useCallback } from 'react'
import { useParams, useSearchParams, useNavigate } from 'react-router-dom'
import { get, post } from '../lib/api'
import ChapterNav from '../components/ChapterNav'
import WorkflowTimeline from '../components/WorkflowTimeline'
import ContextSidebar from '../components/ContextSidebar'
import ErrorState from '../components/ErrorState'
import { tWorkflowStatus } from '../lib/i18n'

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

interface RunResult {
  run_id: string
  project_id: string
  chapter: number
  workflow_status: string
  chapter_status: string
  status: string
  requires_human: boolean
  error: string | null
  llm_mode: string
  message: string
}

type TabKey = 'content' | 'workflow' | 'artifacts' | 'history'

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
  const [error, setError] = useState('')

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

  const handleGenerate = async () => {
    if (!id) return
    setGenerating(true)
    setGenError('')
    setActiveTab('workflow')

    const res = await post<RunResult>('/run/chapter', { project_id: id, chapter: currentChapter })
    if (res.ok && res.data) {
      loadWorkspace()
      get<ChapterDetail>(`/projects/${id}/chapters/${currentChapter}`)
        .then((r) => {
          if (r.ok && r.data) setChapterDetail(r.data)
          setActiveTab('content')
        })
      loadRunDetail(res.data.run_id)
    } else {
      setGenError(res.error?.message || '生成章节失败')
    }
    setGenerating(false)
  }

  const handleViewWorkflow = (runId: string) => {
    loadRunDetail(runId)
    setActiveTab('workflow')
  }

  const handleViewContent = () => setActiveTab('content')

  const handleGenerateNext = async () => {
    const next = currentChapter + 1
    setSearchParams({ chapter: String(next) }, { replace: true })
    // Trigger generation for next chapter after URL update
    if (!id) return
    setGenerating(true)
    setGenError('')
    setActiveTab('workflow')
    const res = await post<RunResult>('/run/chapter', { project_id: id, chapter: next })
    if (res.ok && res.data) {
      loadWorkspace()
      get<ChapterDetail>(`/projects/${id}/chapters/${next}`)
        .then((r) => {
          if (r.ok && r.data) setChapterDetail(r.data)
          setActiveTab('content')
        })
      loadRunDetail(res.data.run_id)
    } else {
      setGenError(res.error?.message || '生成章节失败')
    }
    setGenerating(false)
  }

  const handleNavigateToRun = () => {
    navigate(`/run?project_id=${id}&chapter=${currentChapter}`)
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
          />
        </div>
        <div className="ws-center">
          <TabBar activeTab={activeTab} onTabChange={handleTabChange} hasRuns={runsForChapter.length > 0} />
          <div className="ws-tab-content">
            <TabContent
              activeTab={activeTab}
              generating={generating}
              genError={genError}
              chapterLoading={chapterLoading}
              hasContent={hasContent}
              isStub={isStub}
              currentChapter={currentChapter}
              chapterDetail={chapterDetail}
              runDetail={runDetail}
              runsForChapter={runsForChapter}
              onGenerate={handleGenerate}
              onViewWorkflow={handleViewWorkflow}
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
            onGenerate={handleGenerate}
            onViewWorkflow={handleViewWorkflow}
            onViewContent={handleViewContent}
            onGenerateNext={handleGenerateNext}
            onNavigateToRun={handleNavigateToRun}
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

function TabContent({ activeTab, generating, genError, chapterLoading, hasContent, isStub,
  currentChapter, chapterDetail, runDetail, runsForChapter, onGenerate, onViewWorkflow,
}: {
  activeTab: TabKey; generating: boolean; genError: string; chapterLoading: boolean
  hasContent: boolean; isStub: boolean; currentChapter: number
  chapterDetail: ChapterDetail | null; runDetail: RunDetailData | null
  runsForChapter: Run[]; onGenerate: () => void; onViewWorkflow: (runId: string) => void
}) {
  switch (activeTab) {
    case 'content':
      return (
        <ContentTab
          generating={generating} genError={genError} chapterLoading={chapterLoading}
          hasContent={hasContent} isStub={isStub} currentChapter={currentChapter}
          chapterDetail={chapterDetail} onGenerate={onGenerate}
        />
      )
    case 'workflow':
      return <WorkflowTab runDetail={runDetail} generating={generating} />
    case 'artifacts':
      return <ArtifactsTab runDetail={runDetail} />
    case 'history':
      return <HistoryTab runsForChapter={runsForChapter} onViewWorkflow={onViewWorkflow} currentChapter={currentChapter} />
    default:
      return null
  }
}

function ContentTab({ generating, genError, chapterLoading, hasContent, isStub,
  currentChapter, chapterDetail, onGenerate,
}: {
  generating: boolean; genError: string; chapterLoading: boolean; hasContent: boolean
  isStub: boolean; currentChapter: number; chapterDetail: ChapterDetail | null
  onGenerate: () => void
}) {
  return (
    <div>
      {generating && (
        <div style={{ marginBottom: '16px' }}>
          {GENERATING_STEPS.map((step, i) => (
            <div key={step.key} className="gen-step" style={{ animationDelay: `${i * 0.3}s` }}>
              <div className="gen-step-icon">●</div>
              <div className="gen-step-label">{step.label} — {i < 2 ? '处理中...' : '等待中...'}</div>
            </div>
          ))}
        </div>
      )}
      {genError && (
        <div className="alert alert-error" style={{ marginBottom: '16px' }}>
          <strong>生成失败</strong>
          <div style={{ marginTop: '4px' }}>{genError}</div>
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

function WorkflowTab({ runDetail, generating }: { runDetail: RunDetailData | null; generating: boolean }) {
  if (runDetail) return <WorkflowTimeline steps={runDetail.steps} />
  if (generating) {
    const steps: Step[] = GENERATING_STEPS.map((s, i) => ({
      key: s.key, label: s.label,
      description: i < 2 ? '处理中...' : '等待中...',
      status: (i < 2 ? 'running' : 'pending') as Step['status'],
    }))
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
      .gen-step-icon { width: 26px; height: 26px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 600; background: #dbeafe; color: #2563eb; animation: gen-pulse 1.5s infinite; }
      .gen-step-label { font-size: 14px; color: var(--text-secondary); }
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
    `}</style>
  )
}
