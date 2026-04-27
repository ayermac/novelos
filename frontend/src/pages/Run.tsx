import { useState, useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { post, get } from '../lib/api'
import { tLlmMode, tChapterStatus } from '../lib/i18n'
import ErrorState from '../components/ErrorState'
import PageHeader from '../components/PageHeader'

interface Project {
  project_id: string
  name: string
  chapter_count: number
}

interface Chapter {
  chapter_number: number
  status: string
  title?: string
}

interface Workspace {
  project: Project
  chapters: Chapter[]
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

const RUNNABLE_STATUSES = ['planned', 'pending', 'scripted', 'drafted', 'polished', 'revision']

function isRunnable(ch: Chapter): boolean {
  return RUNNABLE_STATUSES.includes(ch.status)
}

function findDefaultChapter(chapters: Chapter[]): Chapter | null {
  const runnable = chapters.filter(isRunnable)
  if (runnable.length === 0) return null
  return runnable.reduce((min, ch) => (ch.chapter_number < min.chapter_number ? ch : min))
}

const WORKFLOW_STEPS = [
  { key: 'screenwriter', label: '编剧' },
  { key: 'author', label: '执笔' },
  { key: 'polisher', label: '润色' },
  { key: 'editor', label: '审核' },
  { key: 'publish', label: '发布' },
]

export default function Run() {
  const [searchParams] = useSearchParams()
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedProject, setSelectedProject] = useState<Project | null>(null)
  const [, setWorkspace] = useState<Workspace | null>(null)
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [llmMode, setLlmMode] = useState<string>('stub')
  const [form, setForm] = useState({
    project_id: '',
    chapter: 1,
  })
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<RunResult | null>(null)
  const [error, setError] = useState('')

  // Read query params for pre-selection
  const queryProjectId = searchParams.get('project_id')
  const queryChapter = searchParams.get('chapter')

  // Load projects list and LLM mode
  useEffect(() => {
    // Get LLM mode
    get<{ llm_mode: string }>('/health').then((res) => {
      if (res.ok && res.data) {
        setLlmMode(res.data.llm_mode)
      }
    })

    // Get projects
    get<Project[]>('/projects').then((res) => {
      if (res.ok && res.data && res.data.length > 0) {
        const projectList = res.data
        setProjects(projectList)
        // Use query param project if valid, else first project
        const targetId = queryProjectId && projectList.some(p => p.project_id === queryProjectId)
          ? queryProjectId
          : projectList[0].project_id
        const target = projectList.find(p => p.project_id === targetId) || projectList[0]
        setSelectedProject(target)
        loadWorkspace(target.project_id)
      }
    })
  }, [])

  const loadWorkspace = (projectId: string) => {
    get<Workspace>(`/projects/${projectId}/workspace`).then((res) => {
      if (res.ok && res.data) {
        setWorkspace(res.data)
        const chs = res.data.chapters || []
        setChapters(chs)
        const defaultCh = findDefaultChapter(chs)
        // Use query param chapter if valid and runnable, else default
        const qCh = queryChapter ? parseInt(queryChapter) : null
        const useQueryChapter = qCh && chs.some((c: Chapter) => c.chapter_number === qCh && isRunnable(c))
        setForm((prev) => ({
          ...prev,
          project_id: projectId,
          chapter: useQueryChapter ? qCh : (defaultCh ? defaultCh.chapter_number : 1),
        }))
      }
    })
  }

  const handleProjectChange = (projectId: string) => {
    const p = projects.find((x) => x.project_id === projectId)
    if (p) {
      setSelectedProject(p)
      setResult(null)
      setError('')
      loadWorkspace(p.project_id)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    setResult(null)

    const res = await post('/run/chapter', form)

    if (res.ok && res.data) {
      setResult(res.data as RunResult)
      // Refresh workspace to update chapter statuses
      if (selectedProject) {
        loadWorkspace(selectedProject.project_id)
      }
    } else {
      setError(res.error?.message || '运行章节失败')
    }
    setLoading(false)
  }

  const handleRetry = () => {
    setError('')
    setResult(null)
  }

  const handleNextChapter = () => {
    const nextChapter = form.chapter + 1
    const nextCh = chapters.find(c => c.chapter_number === nextChapter)
    if (nextCh && isRunnable(nextCh)) {
      setForm({ ...form, chapter: nextChapter })
    } else {
      // Find next runnable chapter
      const runnable = chapters.filter(isRunnable).filter(c => c.chapter_number > form.chapter)
      if (runnable.length > 0) {
        const next = runnable.reduce((min, ch) => (ch.chapter_number < min.chapter_number ? ch : min))
        setForm({ ...form, chapter: next.chapter_number })
      }
    }
    setResult(null)
    setError('')
  }

  const runnableCount = chapters.filter(isRunnable).length
  const defaultChapter = findDefaultChapter(chapters)
  const isStub = llmMode === 'stub'

  return (
    <div>
      <PageHeader title="生成章节" />

      {/* Demo mode notice */}
      {isStub && (
        <div className="alert alert-warn" style={{ marginBottom: '16px' }}>
          <strong>当前为演示模式</strong>
          <div style={{ marginTop: '4px', fontSize: '14px' }}>
            生成速度快，内容由本地 Stub 模板生成，不代表真实创作质量。如需真实生成，请在配置中心配置 LLM 并以 <code>--llm-mode real</code> 启动。
          </div>
        </div>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="card" style={{ marginBottom: '16px' }}>
          <div className="card-header">
            <h3>正在生成第 {form.chapter} 章...</h3>
          </div>
          <div className="card-body">
            <div className="steps-timeline">
              {WORKFLOW_STEPS.map((step, i) => (
                <div key={step.key} className="step-item step-running" style={{ animationDelay: `${i * 0.5}s` }}>
                  <div className="step-icon">●</div>
                  <div className="step-content">
                    <div className="step-label">{step.label}</div>
                    <div className="step-description">
                      {i < 2 ? '处理中...' : '等待中...'}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {error && !result && !loading && (
        <ErrorState
          title="运行失败"
          message={error}
          onRetry={handleRetry}
        />
      )}

      {result && !loading && (
        <div className={`card ${result.workflow_status === 'completed' ? 'border-success' : result.workflow_status === 'failed' ? 'border-danger' : 'border-warning'}`} style={{ marginBottom: 'var(--spacing-lg)' }}>
          <div className="card-header">
            <h3>
              {result.workflow_status === 'completed' ? '演示生成完成' : 
               result.workflow_status === 'failed' ? '生成失败' : '生成阻塞'}
            </h3>
          </div>
          <div className="card-body">
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
                gap: '16px',
                marginBottom: '16px',
              }}
            >
              <div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>工作流状态</div>
                <span className={`status-badge status-${result.workflow_status}`}>
                  {result.workflow_status === 'completed' ? '已完成' : 
                   result.workflow_status === 'failed' ? '失败' : '阻塞'}
                </span>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>章节状态</div>
                <div style={{ fontWeight: 600 }}>{tChapterStatus(result.chapter_status)}</div>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>章节</div>
                <div style={{ fontWeight: 600 }}>第 {result.chapter} 章</div>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>生成模式</div>
                <span className={`status-badge status-${result.llm_mode}`}>
                  {tLlmMode(result.llm_mode)}
                </span>
              </div>
            </div>
            <div style={{ color: 'var(--text-secondary)', marginBottom: '16px' }}>
              {isStub ? '演示生成完成，内容为本地模拟。' : result.message}
            </div>
            <div className="flex gap-2">
              {result.chapter_status === 'published' && (
                <>
                  <Link
                    to={`/projects/${result.project_id}/chapters/${result.chapter}`}
                    className="btn btn-primary"
                  >
                    查看正文
                  </Link>
                  <Link
                    to={`/runs/${result.run_id}`}
                    className="btn btn-secondary"
                  >
                    查看工作流
                  </Link>
                  <button onClick={handleNextChapter} className="btn btn-secondary">
                    继续生成下一章
                  </button>
                </>
              )}
              {(result.chapter_status === 'review' || result.requires_human) && (
                <Link to="/review" className="btn btn-primary">
                  进入审核
                </Link>
              )}
              {(result.workflow_status === 'blocked' || result.workflow_status === 'failed') && (
                <button onClick={handleRetry} className="btn btn-secondary">
                  重新运行
                </button>
              )}
              <Link
                to={`/projects/${result.project_id}`}
                className="btn btn-secondary"
              >
                返回项目
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Project Info */}
      {selectedProject && !loading && (
        <div className="card" style={{ marginBottom: 'var(--spacing-lg)' }}>
          <div className="card-header">
            <h3>项目信息</h3>
          </div>
          <div className="card-body">
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
                gap: '16px',
              }}
            >
              <div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>项目名</div>
                <div style={{ fontWeight: 600 }}>{selectedProject.name}</div>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>当前章节数</div>
                <div style={{ fontWeight: 600 }}>{chapters.length}</div>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>可生成章节数</div>
                <div style={{ fontWeight: 600 }}>{runnableCount}</div>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>下一可生成章节</div>
                <div style={{ fontWeight: 600 }}>
                  {defaultChapter ? `第 ${defaultChapter.chapter_number} 章` : '无'}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Run Form */}
      {!loading && (
        <div className="card">
          <div className="card-header">
            <h3>生成配置</h3>
          </div>
          <div className="card-body">
            {projects.length === 0 ? (
              <div>
                <ErrorState
                  title="暂无项目"
                  message="请先在项目列表中创建一个项目"
                />
                <div className="mt-3">
                  <Link to="/onboarding" className="btn btn-primary">
                    创建项目
                  </Link>
                </div>
              </div>
            ) : runnableCount === 0 ? (
              <div>
                <ErrorState
                  title="暂无可生成章节"
                  message="当前项目所有章节都已进入阻塞或发布状态，没有可自动生成的章节。"
                />
                <div className="mt-3">
                  <Link
                    to={`/projects/${selectedProject?.project_id}`}
                    className="btn btn-primary"
                  >
                    返回项目工作台
                  </Link>
                  <Link to="/onboarding" className="btn btn-secondary ml-2">
                    创建新项目
                  </Link>
                </div>
              </div>
            ) : (
              <form onSubmit={handleSubmit}>
                <div className="form-group">
                  <label>项目</label>
                  <select
                    className="form-control"
                    value={form.project_id}
                    onChange={(e) => handleProjectChange(e.target.value)}
                    required
                    disabled={loading}
                  >
                    {projects.map((p) => (
                      <option key={p.project_id} value={p.project_id}>
                        {p.name} ({p.project_id})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label>章节</label>
                  <select
                    className="form-control"
                    value={form.chapter}
                    onChange={(e) =>
                      setForm({ ...form, chapter: parseInt(e.target.value) })
                    }
                    required
                    disabled={loading}
                  >
                    {chapters.filter(isRunnable).map((ch) => (
                      <option key={ch.chapter_number} value={ch.chapter_number}>
                        第 {ch.chapter_number} 章（{tChapterStatus(ch.status)}）
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex gap-2 mt-3">
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={loading}
                  >
                    {loading ? '生成中...' : '生成章节'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      <style>{`
        .border-success { border-left: 4px solid #16a34a; }
        .border-danger { border-left: 4px solid #dc2626; }
        .border-warning { border-left: 4px solid #d97706; }
        
        .steps-timeline {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .step-item {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          padding: 12px;
          border-radius: 6px;
          background: var(--bg-secondary);
        }

        .step-icon {
          width: 28px;
          height: 28px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 14px;
          font-weight: 600;
          flex-shrink: 0;
        }

        .step-running .step-icon {
          background: #dbeafe;
          color: #2563eb;
          animation: pulse 1.5s infinite;
        }

        .step-label {
          font-weight: 500;
          margin-bottom: 2px;
        }

        .step-description {
          font-size: 13px;
          color: var(--text-secondary);
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
    </div>
  )
}
