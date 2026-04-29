import { useState, useEffect, useCallback } from 'react'
import { get, post, put, del } from '../../lib/api'
import { Users, Plus, Pencil, Trash2 } from 'lucide-react'

interface Character {
  id: number
  project_id: string
  name: string
  alias?: string
  role: string
  description?: string
  traits?: string
}

interface Props {
  projectId: string
}

const ROLE_LABELS: Record<string, string> = {
  protagonist: '主角',
  antagonist: '反派',
  supporting: '配角',
}

export default function CharactersModule({ projectId }: Props) {
  const [items, setItems] = useState<Character[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editingItem, setEditingItem] = useState<Character | null>(null)
  const [form, setForm] = useState({ name: '', role: 'protagonist', description: '', traits: '', alias: '' })

  const load = useCallback(async () => {
    setLoading(true)
    const res = await get(`/projects/${projectId}/characters`)
    if (res.ok && Array.isArray(res.data)) setItems(res.data)
    setLoading(false)
  }, [projectId])

  useEffect(() => { load() }, [load])

  const handleSubmit = async () => {
    const url = editingItem
      ? `/projects/${projectId}/characters/${editingItem.id}`
      : `/projects/${projectId}/characters`
    const res = editingItem ? await put(url, form) : await post(url, form)
    if (res.ok) {
      setShowModal(false)
      setEditingItem(null)
      setForm({ name: '', role: 'protagonist', description: '', traits: '', alias: '' })
      load()
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除此角色？')) return
    const res = await del(`/projects/${projectId}/characters/${id}`)
    if (res.ok) load()
  }

  const openEdit = (item: Character) => {
    setEditingItem(item)
    setForm({ name: item.name, role: item.role, description: item.description || '', traits: item.traits || '', alias: item.alias || '' })
    setShowModal(true)
  }

  const openAdd = () => {
    setEditingItem(null)
    setForm({ name: '', role: 'protagonist', description: '', traits: '', alias: '' })
    setShowModal(true)
  }

  if (loading) return <div className="module-loading">加载中...</div>

  return (
    <div className="project-module">
      <div className="module-header">
        <h3><Users size={18} /> 角色设定</h3>
        <button className="btn btn-primary btn-sm" onClick={openAdd}><Plus size={14} /> 新增</button>
      </div>
      {items.length === 0 ? (
        <div className="data-empty">
          <div className="data-empty-icon"><Users size={32} /></div>
          <div className="data-empty-title">暂无角色设定</div>
          <div className="data-empty-desc">添加角色信息，帮助 AI 保持人物一致性</div>
          <button className="btn btn-secondary" onClick={openAdd} style={{ marginTop: 12 }}>添加第一个</button>
        </div>
      ) : (
        <div className="data-grid">
          {items.map((ch) => (
            <div key={ch.id} className="data-card">
              <div className="data-card-header">
                <span className="data-card-badge">{ROLE_LABELS[ch.role] || ch.role}</span>
                <div className="data-card-actions">
                  <button className="btn-icon" onClick={() => openEdit(ch)}><Pencil size={14} /></button>
                  <button className="btn-icon btn-icon-danger" onClick={() => handleDelete(ch.id)}><Trash2 size={14} /></button>
                </div>
              </div>
              <div className="data-card-title">{ch.name}{ch.alias ? ` (${ch.alias})` : ''}</div>
              {ch.description && <div className="data-card-content">{ch.description}</div>}
              {ch.traits && <div className="data-card-traits">特征: {ch.traits}</div>}
            </div>
          ))}
        </div>
      )}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>{editingItem ? '编辑角色' : '新增角色'}</h3>
            <div className="form-group">
              <label>名称</label>
              <input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="角色名称" />
            </div>
            <div className="form-group">
              <label>别名</label>
              <input type="text" value={form.alias} onChange={(e) => setForm({ ...form, alias: e.target.value })} placeholder="别名/外号（可选）" />
            </div>
            <div className="form-group">
              <label>角色</label>
              <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                <option value="protagonist">主角</option>
                <option value="antagonist">反派</option>
                <option value="supporting">配角</option>
              </select>
            </div>
            <div className="form-group">
              <label>描述</label>
              <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="角色描述" rows={3} />
            </div>
            <div className="form-group">
              <label>特征</label>
              <input type="text" value={form.traits} onChange={(e) => setForm({ ...form, traits: e.target.value })} placeholder="性格特征，用逗号分隔" />
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
