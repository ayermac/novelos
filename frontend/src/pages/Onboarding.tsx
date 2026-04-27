import { useState } from 'react'
import { Link } from 'react-router-dom'
import { post } from '../lib/api'
import PageHeader from '../components/PageHeader'

interface ProjectResult {
  project: {
    project_id: string
    name: string
  }
  chapters: Array<{ chapter_number: number }>
}

export default function Onboarding() {
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
  const [result, setResult] = useState<ProjectResult | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    const res = await post('/onboarding/projects', form)

    if (res.ok && res.data) {
      setResult(res.data as ProjectResult)
    } else {
      setError(res.error?.message || '创建失败')
    }
    setLoading(false)
  }

  if (result) {
    return (
      <div>
        <PageHeader title="创建成功" />
        <div className="card">
          <div className="card-body" style={{ textAlign: 'center', padding: '48px' }}>
            <div
              style={{
                width: '64px',
                height: '64px',
                borderRadius: '50%',
                background: 'var(--success)',
                color: 'white',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '32px',
                margin: '0 auto 24px',
              }}
            >
              ✓
            </div>
            <h3 style={{ marginBottom: '8px' }}>项目创建成功</h3>
            <p style={{ color: 'var(--text-secondary)', marginBottom: '24px' }}>
              「{result.project.name}」已创建，共规划 {result.chapters.length} 个初始章节。
            </p>
            <div className="flex gap-2" style={{ justifyContent: 'center' }}>
              <Link
                to={`/projects/${result.project.project_id}`}
                className="btn btn-primary"
              >
                进入项目工作台
              </Link>
              <Link to="/run" className="btn btn-secondary">
                生成第一章
              </Link>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div>
      <PageHeader title="创建新项目" backTo="/projects" backLabel="返回列表" />

      {error && (
        <div className="alert alert-error" style={{ marginBottom: '16px' }}>
          {error}
        </div>
      )}

      <div className="card">
        <div className="card-body">
          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: '24px' }}>
              <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '16px', color: 'var(--primary)' }}>
                第一步：基础信息
              </div>
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
                <select
                  className="form-control"
                  value={form.genre}
                  onChange={(e) => setForm({ ...form, genre: e.target.value })}
                >
                  <option value="">请选择</option>
                  <option value="fantasy">奇幻</option>
                  <option value="urban">都市</option>
                  <option value="sci-fi">科幻</option>
                  <option value="xianxia">仙侠</option>
                  <option value="romance">言情</option>
                  <option value="mystery">悬疑</option>
                </select>
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
            </div>

            <div style={{ marginBottom: '24px' }}>
              <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '16px', color: 'var(--primary)' }}>
                第二步：规模设置
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
                    onChange={(e) =>
                      setForm({ ...form, target_words: parseInt(e.target.value) })
                    }
                    min={1}
                  />
                </div>
              </div>
            </div>

            <div style={{ marginBottom: '24px' }}>
              <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '16px', color: 'var(--primary)' }}>
                第三步：初始章节
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div className="form-group">
                  <label>起始章节号</label>
                  <input
                    type="number"
                    className="form-control"
                    value={form.start_chapter}
                    onChange={(e) =>
                      setForm({ ...form, start_chapter: parseInt(e.target.value) })
                    }
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
