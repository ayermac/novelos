import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { post, get } from '../lib/api'
import { tLlmMode } from '../lib/i18n'
import StatusBadge from '../components/StatusBadge'
import ErrorState from '../components/ErrorState'
import PageHeader from '../components/PageHeader'

interface Project {
  project_id: string
  name: string
  chapter_count: number
}

interface RunResult {
  run_id: string
  project_id: string
  chapter: number
  status: string
  llm_mode: string
  message: string
}

export default function Run() {
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedProject, setSelectedProject] = useState<Project | null>(null)
  const [form, setForm] = useState({
    project_id: '',
    chapter: 1,
  })
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<RunResult | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    get<Project[]>('/projects').then((res) => {
      if (res.ok && res.data && res.data.length > 0) {
        setProjects(res.data)
        const first = res.data[0]
        setSelectedProject(first)
        setForm((prev) => ({
          ...prev,
          project_id: first.project_id,
          chapter: (first.chapter_count || 0) + 1,
        }))
      }
    })
  }, [])

  const handleProjectChange = (projectId: string) => {
    const p = projects.find((x) => x.project_id === projectId)
    if (p) {
      setSelectedProject(p)
      setForm((prev) => ({
        ...prev,
        project_id: p.project_id,
        chapter: (p.chapter_count || 0) + 1,
      }))
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
    } else {
      setError(res.error?.message || '运行章节失败')
    }
    setLoading(false)
  }

  const handleRetry = () => {
    setError('')
    setResult(null)
  }

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
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>状态</div>
                <StatusBadge status={result.status} />
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
              <Link to="/review" className="btn btn-secondary">
                进入审核
              </Link>
              <button
                onClick={handleRetry}
                className="btn btn-secondary"
              >
                重新生成
              </button>
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
                <div style={{ fontWeight: 600 }}>{selectedProject.chapter_count}</div>
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
            <ErrorState
              title="暂无项目"
              message="请先在项目列表中创建一个项目"
            />
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
                <label>章节号</label>
                <input
                  type="number"
                  className="form-control"
                  value={form.chapter}
                  onChange={(e) =>
                    setForm({ ...form, chapter: parseInt(e.target.value) })
                  }
                  min={1}
                  required
                />
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
