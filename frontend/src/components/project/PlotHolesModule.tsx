import { useState, useEffect, useCallback } from 'react'
import { get, post, put, del } from '../../lib/api'
import { Sparkles, Plus, Pencil, Trash2 } from 'lucide-react'

interface PlotHole {
  id: number
  project_id: string
  code: string
  type?: string
  title: string
  description?: string
  planted_chapter?: number
  planned_resolve_chapter?: number
  resolved_chapter?: number
  status: string
  notes?: string
}

interface Props {
  projectId: string
}

const STATUS_LABELS: Record<string, string> = {
  planted: '已埋',
  resolved: '已收',
  abandoned: '已弃',
}

export default function PlotHolesModule({ projectId }: Props) {
  const [items, setItems] = useState<PlotHole[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editingItem, setEditingItem] = useState<PlotHole | null>(null)
  const [form, setForm] = useState({
    code: '', type: '', title: '', description: '',
    planted_chapter: '', planned_resolve_chapter: '', status: 'planted', notes: '',
  })

  const load = useCallback(async () => {
    setLoading(true)
    const res = await get(`/projects/${projectId}/plot-holes`)
    if (res.ok && Array.isArray(res.data)) setItems(res.data)
    setLoading(false)
  }, [projectId])

  useEffect(() => { load() }, [load])

  const handleSubmit = async () => {
    const payload = {
      ...form,
      planted_chapter: form.planted_chapter ? Number(form.planted_chapter) : null,
      planned_resolve_chapter: form.planned_resolve_chapter ? Number(form.planned_resolve_chapter) : null,
    }
    const url = editingItem
      ? `/projects/${projectId}/plot-holes/${editingItem.id}`
      : `/projects/${projectId}/plot-holes`
    const res = editingItem ? await put(url, payload) : await post(url, payload)
    if (res.ok) {
      setShowModal(false)
      setEditingItem(null)
      setForm({ code: '', type: '', title: '', description: '', planted_chapter: '', planned_resolve_chapter: '', status: 'planted', notes: '' })
      load()
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除此伏笔？')) return
    const res = await del(`/projects/${projectId}/plot-holes/${id}`)
    if (res.ok) load()
  }

  const openEdit = (item: PlotHole) => {
    setEditingItem(item)
    setForm({
      code: item.code, type: item.type || '', title: item.title,
      description: item.description || '',
      planted_chapter: item.planted_chapter?.toString() || '',
      planned_resolve_chapter: item.planned_resolve_chapter?.toString() || '',
      status: item.status, notes: item.notes || '',
    })
    setShowModal(true)
  }

  const openAdd = () => {
    setEditingItem(null)
    setForm({ code: '', type: '', title: '', description: '', planted_chapter: '', planned_resolve_chapter: '', status: 'planted', notes: '' })
    setShowModal(true)
  }

  if (loading) return <div className="module-loading">加载中...</div>

  return (
    <div className="project-module">
      <div className="module-header">
        <h3><Sparkles size={18} /> 伏笔管理</h3>
        <button className="btn btn-primary btn-sm" onClick={openAdd}><Plus size={14} /> 新增</button>
      </div>
      {items.length === 0 ? (
        <div className="data-empty">
          <div className="data-empty-icon"><Sparkles size={32} /></div>
          <div className="data-empty-title">暂无伏笔</div>
          <div className="data-empty-desc">管理伏笔的埋设与回收，保持故事连贯性</div>
          <button className="btn btn-secondary" onClick={openAdd} style={{ marginTop: 12 }}>创建第一条</button>
        </div>
      ) : (
        <div className="data-grid">
          {items.map((p) => (
            <div key={p.id} className="data-card">
              <div className="data-card-header">
                <span className="data-card-badge">{p.code}</span>
                <span className="data-card-category">{STATUS_LABELS[p.status] || p.status}</span>
                <div className="data-card-actions">
                  <button className="btn-icon" onClick={() => openEdit(p)}><Pencil size={14} /></button>
                  <button className="btn-icon btn-icon-danger" onClick={() => handleDelete(p.id)}><Trash2 size={14} /></button>
                </div>
              </div>
              <div className="data-card-title">{p.title}</div>
              {p.description && <div className="data-card-content">{p.description}</div>}
              <div className="data-card-traits">
                {p.planted_chapter && <span>埋设: 第{p.planted_chapter}章 </span>}
                {p.planned_resolve_chapter && <span>计划回收: 第{p.planned_resolve_chapter}章</span>}
              </div>
            </div>
          ))}
        </div>
      )}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>{editingItem ? '编辑伏笔' : '新增伏笔'}</h3>
            <div className="form-group">
              <label>编码</label>
              <input type="text" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="如：PH-001" />
            </div>
            <div className="form-group">
              <label>标题</label>
              <input type="text" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="伏笔标题" />
            </div>
            <div className="form-group">
              <label>类型</label>
              <input type="text" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} placeholder="如：悬念、铺垫、误导" />
            </div>
            <div className="form-group">
              <label>描述</label>
              <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="伏笔描述" rows={3} />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>埋设章节</label>
                <input type="number" value={form.planted_chapter} onChange={(e) => setForm({ ...form, planted_chapter: e.target.value })} placeholder="章节号" />
              </div>
              <div className="form-group">
                <label>计划回收章节</label>
                <input type="number" value={form.planned_resolve_chapter} onChange={(e) => setForm({ ...form, planned_resolve_chapter: e.target.value })} placeholder="章节号" />
              </div>
            </div>
            <div className="form-group">
              <label>状态</label>
              <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                <option value="planted">已埋</option>
                <option value="resolved">已收</option>
                <option value="abandoned">已弃</option>
              </select>
            </div>
            <div className="form-group">
              <label>备注</label>
              <textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="备注信息" rows={2} />
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
