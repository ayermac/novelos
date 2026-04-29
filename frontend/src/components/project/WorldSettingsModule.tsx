import { useState, useEffect, useCallback } from 'react'
import { get, post, put, del } from '../../lib/api'
import { Globe, Plus, Pencil, Trash2 } from 'lucide-react'

interface WorldSetting {
  id: number
  project_id: string
  category: string
  title: string
  content: string
}

interface Props {
  projectId: string
}

export default function WorldSettingsModule({ projectId }: Props) {
  const [items, setItems] = useState<WorldSetting[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editingItem, setEditingItem] = useState<WorldSetting | null>(null)
  const [form, setForm] = useState({ category: '', title: '', content: '' })

  const load = useCallback(async () => {
    setLoading(true)
    const res = await get(`/projects/${projectId}/world-settings`)
    if (res.ok && Array.isArray(res.data)) setItems(res.data)
    setLoading(false)
  }, [projectId])

  useEffect(() => { load() }, [load])

  const handleSubmit = async () => {
    const url = editingItem
      ? `/projects/${projectId}/world-settings/${editingItem.id}`
      : `/projects/${projectId}/world-settings`
    const res = editingItem ? await put(url, form) : await post(url, form)
    if (res.ok) {
      setShowModal(false)
      setEditingItem(null)
      setForm({ category: '', title: '', content: '' })
      load()
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除此世界观设定？')) return
    const res = await del(`/projects/${projectId}/world-settings/${id}`)
    if (res.ok) load()
  }

  const openEdit = (item: WorldSetting) => {
    setEditingItem(item)
    setForm({ category: item.category, title: item.title, content: item.content })
    setShowModal(true)
  }

  const openAdd = () => {
    setEditingItem(null)
    setForm({ category: '', title: '', content: '' })
    setShowModal(true)
  }

  if (loading) return <div className="module-loading">加载中...</div>

  return (
    <div className="project-module">
      <div className="module-header">
        <h3><Globe size={18} /> 世界观设定</h3>
        <button className="btn btn-primary btn-sm" onClick={openAdd}><Plus size={14} /> 新增</button>
      </div>
      {items.length === 0 ? (
        <div className="data-empty">
          <div className="data-empty-icon"><Globe size={32} /></div>
          <div className="data-empty-title">暂无世界观设定</div>
          <div className="data-empty-desc">添加世界观设定，帮助 AI 更好理解故事背景</div>
          <button className="btn btn-secondary" onClick={openAdd} style={{ marginTop: 12 }}>添加第一条</button>
        </div>
      ) : (
        <div className="data-grid">
          {items.map((ws) => (
            <div key={ws.id} className="data-card">
              <div className="data-card-header">
                <span className="data-card-category">{ws.category}</span>
                <div className="data-card-actions">
                  <button className="btn-icon" onClick={() => openEdit(ws)}><Pencil size={14} /></button>
                  <button className="btn-icon btn-icon-danger" onClick={() => handleDelete(ws.id)}><Trash2 size={14} /></button>
                </div>
              </div>
              <div className="data-card-title">{ws.title}</div>
              <div className="data-card-content">{ws.content}</div>
            </div>
          ))}
        </div>
      )}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>{editingItem ? '编辑世界观' : '新增世界观'}</h3>
            <div className="form-group">
              <label>分类</label>
              <input type="text" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="如：力量体系、社会结构" />
            </div>
            <div className="form-group">
              <label>标题</label>
              <input type="text" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="设定名称" />
            </div>
            <div className="form-group">
              <label>内容</label>
              <textarea value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} placeholder="详细描述" rows={4} />
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
