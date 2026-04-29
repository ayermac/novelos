import { useCallback, useEffect, useState } from 'react'
import { Save, Settings } from 'lucide-react'
import { get, put } from '../../lib/api'

interface ProjectSettings {
  project_id: string
  name: string
  genre?: string
  description?: string
  target_words: number
  total_chapters_planned: number
}

interface Props {
  projectId: string
  onSaved?: () => void
}

export default function ProjectSettingsModule({ projectId, onSaved }: Props) {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [form, setForm] = useState({
    name: '',
    genre: '',
    description: '',
    target_words: '',
    total_chapters_planned: '',
  })

  const load = useCallback(async () => {
    setLoading(true)
    const res = await get<ProjectSettings>(`/projects/${projectId}`)
    if (res.ok && res.data) {
      setForm({
        name: res.data.name || '',
        genre: res.data.genre || '',
        description: res.data.description || '',
        target_words: String(res.data.target_words || ''),
        total_chapters_planned: String(res.data.total_chapters_planned || ''),
      })
    }
    setLoading(false)
  }, [projectId])

  useEffect(() => { load() }, [load])

  const handleSubmit = async () => {
    setSaving(true)
    setMessage('')
    const res = await put(`/projects/${projectId}`, {
      name: form.name,
      genre: form.genre,
      description: form.description,
      target_words: Number(form.target_words),
      total_chapters_planned: Number(form.total_chapters_planned),
    })
    setSaving(false)
    if (res.ok) {
      setMessage('项目设置已保存')
      onSaved?.()
    } else {
      setMessage(res.error?.message || '保存失败')
    }
  }

  if (loading) return <div className="module-loading">加载中...</div>

  return (
    <div className="project-module">
      <div className="module-header">
        <h3><Settings size={18} /> 项目设置</h3>
        <button className="btn btn-primary btn-sm" onClick={handleSubmit} disabled={saving}>
          <Save size={14} />
          {saving ? '保存中...' : '保存'}
        </button>
      </div>

      {message && (
        <div className="data-card" style={{ marginBottom: 16 }}>
          <div className="data-card-content">{message}</div>
        </div>
      )}

      <div className="data-card">
        <div className="form-group">
          <label>项目名称</label>
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        <div className="form-group">
          <label>类型</label>
          <input value={form.genre} onChange={(e) => setForm({ ...form, genre: e.target.value })} />
        </div>
        <div className="form-group">
          <label>项目简介</label>
          <textarea
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            rows={5}
            placeholder="写清故事类型、主角处境、核心冲突和长期目标。Context Gate 会检查这里。"
          />
        </div>
        <div className="form-row">
          <div className="form-group">
            <label>目标总字数</label>
            <input
              type="number"
              value={form.target_words}
              onChange={(e) => setForm({ ...form, target_words: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label>预计章节数</label>
            <input
              type="number"
              value={form.total_chapters_planned}
              onChange={(e) => setForm({ ...form, total_chapters_planned: e.target.value })}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
