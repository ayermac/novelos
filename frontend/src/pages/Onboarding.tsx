import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { post } from '../lib/api'

export default function Onboarding() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    project_id: '',
    name: '',
    genre: '',
    description: '',
    total_chapters_planned: 500,
    target_words: 1500000,
    style_template: 'default_web_serial',
    start_chapter: 1,
    initial_chapter_count: 10,
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    const res = await post('/onboarding/projects', form)

    if (res.ok && res.data) {
      navigate(`/projects/${form.project_id}`)
    } else {
      setError(res.error?.message || '创建失败')
      setLoading(false)
    }
  }

  return (
    <div>
      <h2 style={{ marginBottom: '24px' }}>创建新项目</h2>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="card">
        <div className="card-body">
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label>项目 ID</label>
              <input
                type="text"
                className="form-control"
                value={form.project_id}
                onChange={(e) => setForm({ ...form, project_id: e.target.value })}
                placeholder="例如：my_xianxia_novel"
                required
              />
              <div className="hint">唯一标识符，只能包含字母、数字、下划线</div>
            </div>

            <div className="form-group">
              <label>小说名称</label>
              <input
                type="text"
                className="form-control"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
              />
            </div>

            <div className="form-group">
              <label>类型 / 题材</label>
              <input
                type="text"
                className="form-control"
                value={form.genre}
                onChange={(e) => setForm({ ...form, genre: e.target.value })}
                placeholder="例如：玄幻、都市、科幻"
              />
            </div>

            <div className="form-group">
              <label>简介</label>
              <textarea
                className="form-control"
                rows={3}
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="简要描述故事背景和大纲"
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <div className="form-group">
                <label>计划总章节数</label>
                <input
                  type="number"
                  className="form-control"
                  value={form.total_chapters_planned}
                  onChange={(e) =>
                    setForm({ ...form, total_chapters_planned: parseInt(e.target.value) })
                  }
                  min={1}
                />
              </div>
              <div className="form-group">
                <label>目标总字数</label>
                <input
                  type="number"
                  className="form-control"
                  value={form.target_words}
                  onChange={(e) => setForm({ ...form, target_words: parseInt(e.target.value) })}
                  min={1}
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <div className="form-group">
                <label>起始章节号</label>
                <input
                  type="number"
                  className="form-control"
                  value={form.start_chapter}
                  onChange={(e) => setForm({ ...form, start_chapter: parseInt(e.target.value) })}
                  min={1}
                />
              </div>
              <div className="form-group">
                <label>初始章节数</label>
                <input
                  type="number"
                  className="form-control"
                  value={form.initial_chapter_count}
                  onChange={(e) =>
                    setForm({ ...form, initial_chapter_count: parseInt(e.target.value) })
                  }
                  min={1}
                />
                <div className="hint">创建项目时预生成的章节数量</div>
              </div>
            </div>

            <div className="flex gap-2 mt-3">
              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? '创建中...' : '创建项目'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
