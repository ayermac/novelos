import { useState, useEffect, useCallback } from 'react'
import { get, post, put, del } from '../../lib/api'
import { Swords, Plus, Pencil, Trash2 } from 'lucide-react'

interface Faction {
  id: number
  project_id: string
  name: string
  type?: string
  description?: string
  relationship_with_protagonist?: string
}

interface Props {
  projectId: string
}

export default function FactionsModule({ projectId }: Props) {
  const [items, setItems] = useState<Faction[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editingItem, setEditingItem] = useState<Faction | null>(null)
  const [form, setForm] = useState({ name: '', type: '', description: '', relationship_with_protagonist: '' })

  const load = useCallback(async () => {
    setLoading(true)
    const res = await get(`/projects/${projectId}/factions`)
    if (res.ok && Array.isArray(res.data)) setItems(res.data)
    setLoading(false)
  }, [projectId])

  useEffect(() => { load() }, [load])

  const handleSubmit = async () => {
    const url = editingItem
      ? `/projects/${projectId}/factions/${editingItem.id}`
      : `/projects/${projectId}/factions`
    const res = editingItem ? await put(url, form) : await post(url, form)
    if (res.ok) {
      setShowModal(false)
      setEditingItem(null)
      setForm({ name: '', type: '', description: '', relationship_with_protagonist: '' })
      load()
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除此势力？')) return
    const res = await del(`/projects/${projectId}/factions/${id}`)
    if (res.ok) load()
  }

  const openEdit = (item: Faction) => {
    setEditingItem(item)
    setForm({
      name: item.name, type: item.type || '',
      description: item.description || '', relationship_with_protagonist: item.relationship_with_protagonist || '',
    })
    setShowModal(true)
  }

  const openAdd = () => {
    setEditingItem(null)
    setForm({ name: '', type: '', description: '', relationship_with_protagonist: '' })
    setShowModal(true)
  }

  if (loading) return <div className="module-loading">加载中...</div>

  return (
    <div className="project-module">
      <div className="module-header">
        <h3><Swords size={18} /> 势力设定</h3>
        <button className="btn btn-primary btn-sm" onClick={openAdd}><Plus size={14} /> 新增</button>
      </div>
      {items.length === 0 ? (
        <div className="data-empty">
          <div className="data-empty-icon"><Swords size={32} /></div>
          <div className="data-empty-title">暂无势力设定</div>
          <div className="data-empty-desc">添加势力信息，帮助 AI 理解阵营关系</div>
          <button className="btn btn-secondary" onClick={openAdd} style={{ marginTop: 12 }}>添加第一个</button>
        </div>
      ) : (
        <div className="data-grid">
          {items.map((f) => (
            <div key={f.id} className="data-card">
              <div className="data-card-header">
                {f.type && <span className="data-card-badge">{f.type}</span>}
                <div className="data-card-actions">
                  <button className="btn-icon" onClick={() => openEdit(f)}><Pencil size={14} /></button>
                  <button className="btn-icon btn-icon-danger" onClick={() => handleDelete(f.id)}><Trash2 size={14} /></button>
                </div>
              </div>
              <div className="data-card-title">{f.name}</div>
              {f.description && <div className="data-card-content">{f.description}</div>}
              {f.relationship_with_protagonist && (
                <div className="data-card-traits">与主角关系: {f.relationship_with_protagonist}</div>
              )}
            </div>
          ))}
        </div>
      )}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>{editingItem ? '编辑势力' : '新增势力'}</h3>
            <div className="form-group">
              <label>名称</label>
              <input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="势力名称" />
            </div>
            <div className="form-group">
              <label>类型</label>
              <input type="text" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} placeholder="如：宗门、国家、组织" />
            </div>
            <div className="form-group">
              <label>描述</label>
              <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="势力描述" rows={3} />
            </div>
            <div className="form-group">
              <label>与主角关系</label>
              <input type="text" value={form.relationship_with_protagonist} onChange={(e) => setForm({ ...form, relationship_with_protagonist: e.target.value })} placeholder="如：盟友、敌对、中立" />
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
