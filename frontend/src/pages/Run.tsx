import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { post, get } from '../lib/api'
import { tLlmMode, tChapterStatus } from '../lib/i18n'
import StatusBadge from '../components/StatusBadge'
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

export default function Run() {
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedProject, setSelectedProject] = useState<Project | null>(null)
  const [, setWorkspace] = useState<Workspace | null>(null)
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [form, setForm] = useState({
    project_id: '',
    chapter: 1,
  })
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<RunResult | null>(null)
  const [error, setError] = useState('')

  // Load projects list
  useEffect(() => {
    get<Project[]>('/projects').then((res) => {
      if (res.ok && res.data && res.data.length > 0) {
        setProjects(res.data)
        const first = res.data[0]
        setSelectedProject(first)
        loadWorkspace(first.project_id)
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
        setForm((prev) => ({
          ...prev,
          project_id: projectId,
          chapter: defaultCh ? defaultCh.chapter_number : 1,
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

  const runnableCount = chapters.filter(isRunnable).length
  const defaultChapter = findDefaultChapter(chapters)

  return (
    <div>
      <PageHeader title="生成章节" />

      {error && !result && (
        <ErrorState
          title="运行失败"
          message={error}
          onRetry={handleRetry}
        />
      )}

      {result && (
        <div className="card" style={{ marginBottom: 'var(--spacing-lg)' }}>
          <div className="card-header">
            <h3>运行结果</h3>
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
                <StatusBadge status={result.workflow_status} />
              </div>
              <div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>章节状态</div>
                <div style={{ fontWeight: 600 }}>{tChapterStatus(result.chapter_status)}</div>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>运行 ID</div>
                <div style={{ fontWeight: 600, fontSize: '12px' }}>{result.run_id}</div>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>项目</div>
                <div style={{ fontWeight: 600 }}>{result.project_id}</div>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>章节</div>
                <div style={{ fontWeight: 600 }}>第 {result.chapter} 章</div>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>运行模式</div>
                <div style={{ fontWeight: 600 }}>{tLlmMode(result.llm_mode)}</div>
              </div>
              {result.requires_human && (
                <div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>需人工处理</div>
                  <div style={{ fontWeight: 600, color: 'var(--warning)' }}>是</div>
                </div>
              )}
              {result.error && (
                <div style={{ gridColumn: '1 / -1' }}>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>错误</div>
                  <div style={{ fontWeight: 600, color: 'var(--danger)' }}>{result.error}</div>
                </div>
              )}
            </div>
            <div style={{ color: 'var(--text-secondary)', marginBottom: '16px' }}>
              {result.message}
            </div>
            <div className="flex gap-2">
              <Link
                to={`/projects/${result.project_id}`}
                className="btn btn-primary"
              >
                查看项目
              </Link>
              {result.workflow_status === 'blocked' || result.workflow_status === 'failed' ? (
                <>
                  <Link to="/review" className="btn btn-secondary">
                    进入审核
                  </Link>
                  <button
                    onClick={handleRetry}
                    className="btn btn-secondary"
                  >
                    重新运行
                  </button>
                </>
              ) : (
                <>
                  <Link to="/review" className="btn btn-secondary">
                    进入审核
                  </Link>
                  <button
                    onClick={handleRetry}
                    className="btn btn-secondary"
                  >
                    重新生成
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Project Info */}
      {selectedProject && (
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
                  {loading ? '运行中...' : '生成章节'}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
