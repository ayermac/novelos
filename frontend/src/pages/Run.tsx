import { useState, useEffect } from 'react'
import { post, get } from '../lib/api'

interface Project {
  project_id: string
  name: string
}

export default function Run() {
  const [projects, setProjects] = useState<Project[]>([])
  const [form, setForm] = useState({
    project_id: '',
    chapter: 1,
  })
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{ run_id: string; message: string } | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    get<Project[]>('/projects').then((res) => {
      if (res.ok && res.data && res.data.length > 0) {
        setProjects(res.data)
        setForm((prev) => ({ ...prev, project_id: res.data![0].project_id }))
      }
    })
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    setResult(null)

    const res = await post('/run/chapter', form)

    if (res.ok && res.data) {
      setResult(res.data as { run_id: string; message: string })
    } else {
      setError(res.error?.message || '运行失败')
    }
    setLoading(false)
  }

  return (
    <div>
      <h2 style={{ marginBottom: '24px' }}>生成章节</h2>

      {error && <div className="alert alert-error">{error}</div>}
      {result && (
        <div className="alert alert-success">
          <strong>成功：</strong> {result.message}
          <br />
          运行 ID: {result.run_id}
        </div>
      )}

      <div className="card">
        <div className="card-body">
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label>项目</label>
              <select
                className="form-control"
                value={form.project_id}
                onChange={(e) => setForm({ ...form, project_id: e.target.value })}
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
                onChange={(e) => setForm({ ...form, chapter: parseInt(e.target.value) })}
                min={1}
                required
              />
            </div>

            <div className="flex gap-2 mt-3">
              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? '运行中...' : '生成章节'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
