import { useState, useEffect, useCallback } from 'react'
import { get, post, put, del } from '../../lib/api'
import { ListTree, Plus, Pencil, Trash2 } from 'lucide-react'

interface Outline {
  id: number
  project_id: string
  level: string
  phase?: string
  chapters?: string
  summary?: string
  key_events?: string
  notes?: string
}

interface Props {
  projectId: string
}

export default function OutlinesModule({ projectId }: Props) {
  const [items, setItems] = useState<Outline[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editingItem, setEditingItem] = useState<Outline | null>(null)
  const [form, setForm] = useState({ level: 'volume', phase: '', chapters: '', summary: '', key_events: '', notes: '' })

  const load = useCallback(async () => {
    setLoading(true)
    const res = await get(`/projects/${projectId}/outlines`)
    if (res.ok && Array.isArray(res.data)) setItems(res.data)
    setLoading(false)
  }, [projectId])

  useEffect(() => { load() }, [load])

  const handleSubmit = async () => {
    const url = editingItem
      ? `/projects/${projectId}/outlines/${editingItem.id}`
      : `/projects/${projectId}/outlines`
    const res = editingItem ? await put(url, form) : await post(url, form)
    if (res.ok) {
      setShowModal(false)
      setEditingItem(null)
      setForm({ level: 'volume', phase: '', chapters: '', summary: '', key_events: '', notes: '' })
      load()
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除此大纲？')) return
    const res = await del(`/projects/${projectId}/outlines/${id}`)
    if (res.ok) load()
  }

  const openEdit = (item: Outline) => {
    setEditingItem(item)
    setForm({
      level: item.level, phase: item.phase || '', chapters: item.chapters || '',
      summary: item.summary || '', key_events: item.key_events || '', notes: item.notes || '',
    })
    setShowModal(true)
  }

  const openAdd = () => {
    setEditingItem(null)
    setForm({ level: 'volume', phase: '', chapters: '', summary: '', key_events: '', notes: '' })
    setShowModal(true)
  }

  if (loading) return <div className="module-loading">加载中...</div>

  return (
    <div className="project-module">
      <div className="module-header">
        <h3><ListTree size={18} /> 大纲</h3>
        <button className="btn btn-primary btn-sm" onClick={openAdd}><Plus size={14} /> 新增</button>
      </div>
      {items.length === 0 ? (
        <div className="data-empty">
          <div className="data-empty-icon"><ListTree size={32} /></div>
          <div className="data-empty-title">暂无大纲</div>
          <div className="data-empty-desc">创建大纲帮助规划故事结构</div>
          <button className="btn btn-secondary" onClick={openAdd} style={{ marginTop: 12 }}>创建第一条</button>
        </div>
      ) : (
        <div className="data-grid">
          {items.map((o) => (
            <div key={o.id} className="data-card">
              <div className="data-card-header">
                <span className="data-card-badge">{o.level === 'volume' ? '卷' : o.level === 'arc' ? '篇章' : '章节'}</span>
                {o.chapters && <span className="data-card-range">第 {o.chapters} 章</span>}
                <div className="data-card-actions">
                  <button className="btn-icon" onClick={() => openEdit(o)}><Pencil size={14} /></button>
                  <button className="btn-icon btn-icon-danger" onClick={() => handleDelete(o.id)}><Trash2 size={14} /></button>
                </div>
              </div>
              {o.phase && <div className="data-card-title">{o.phase}</div>}
              {o.summary && <div className="data-card-content">{o.summary}</div>}
              {o.key_events && <div className="data-card-traits">关键事件: {o.key_events}</div>}
            </div>
          ))}
        </div>
      )}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>{editingItem ? '编辑大纲' : '新增大纲'}</h3>
            <div className="form-group">
              <label>层级</label>
              <select value={form.level} onChange={(e) => setForm({ ...form, level: e.target.value })}>
                <option value="volume">卷</option>
                <option value="arc">篇章</option>
                <option value="chapter">章节</option>
              </select>
            </div>
            <div className="form-group">
              <label>阶段名称</label>
              <input type="text" value={form.phase} onChange={(e) => setForm({ ...form, phase: e.target.value })} placeholder="如：第一卷 起源" />
            </div>
            <div className="form-group">
              <label>章节范围</label>
              <input type="text" value={form.chapters} onChange={(e) => setForm({ ...form, chapters: e.target.value })} placeholder="如：1-10" />
            </div>
            <div className="form-group">
              <label>概要</label>
              <textarea value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} placeholder="本段落主要内容" rows={3} />
            </div>
            <div className="form-group">
              <label>关键事件</label>
              <textarea value={form.key_events} onChange={(e) => setForm({ ...form, key_events: e.target.value })} placeholder="重要事件节点" rows={2} />
            </div>
            <div className="form-actions">
              <button className="btn btn-secondary" onClick={() => setShowModal(false)}>取消</button>
              <button className="btn btn-primary" onClick={handleSubmit}>保存</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
