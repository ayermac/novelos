import { useState, useEffect, useCallback } from 'react'
import { get, post, put, del } from '../../lib/api'
import { FileText, Plus, Pencil, Trash2 } from 'lucide-react'

interface Instruction {
  id: number
  project_id: string
  chapter_number: number
  objective?: string
  key_events?: string
  plots_to_resolve?: string
  plots_to_plant?: string
  emotion_tone?: string
  ending_hook?: string
  word_target?: number
  status: string
}

interface Props {
  projectId: string
}

export default function InstructionsModule({ projectId }: Props) {
  const [items, setItems] = useState<Instruction[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editingItem, setEditingItem] = useState<Instruction | null>(null)
  const [form, setForm] = useState({
    chapter_number: '', objective: '', key_events: '',
    plots_to_resolve: '', plots_to_plant: '', emotion_tone: '',
    ending_hook: '', word_target: '', status: 'pending',
  })

  const load = useCallback(async () => {
    setLoading(true)
    const res = await get(`/projects/${projectId}/instructions`)
    if (res.ok && Array.isArray(res.data)) setItems(res.data)
    setLoading(false)
  }, [projectId])

  useEffect(() => { load() }, [load])

  const handleSubmit = async () => {
    const payload = {
      ...form,
      chapter_number: Number(form.chapter_number),
      word_target: form.word_target ? Number(form.word_target) : null,
    }
    const url = editingItem
      ? `/projects/${projectId}/instructions/${editingItem.id}`
      : `/projects/${projectId}/instructions`
    const res = editingItem ? await put(url, payload) : await post(url, payload)
    if (res.ok) {
      setShowModal(false)
      setEditingItem(null)
      setForm({ chapter_number: '', objective: '', key_events: '', plots_to_resolve: '', plots_to_plant: '', emotion_tone: '', ending_hook: '', word_target: '', status: 'pending' })
      load()
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除此章节指令？')) return
    const res = await del(`/projects/${projectId}/instructions/${id}`)
    if (res.ok) load()
  }

  const openEdit = (item: Instruction) => {
    setEditingItem(item)
    setForm({
      chapter_number: item.chapter_number.toString(),
      objective: item.objective || '', key_events: item.key_events || '',
      plots_to_resolve: item.plots_to_resolve || '', plots_to_plant: item.plots_to_plant || '',
      emotion_tone: item.emotion_tone || '', ending_hook: item.ending_hook || '',
      word_target: item.word_target?.toString() || '', status: item.status,
    })
    setShowModal(true)
  }

  const openAdd = () => {
    setEditingItem(null)
    setForm({ chapter_number: '', objective: '', key_events: '', plots_to_resolve: '', plots_to_plant: '', emotion_tone: '', ending_hook: '', word_target: '', status: 'pending' })
    setShowModal(true)
  }

  if (loading) return <div className="module-loading">加载中...</div>

  return (
    <div className="project-module">
      <div className="module-header">
        <h3><FileText size={18} /> 章节指令</h3>
        <button className="btn btn-primary btn-sm" onClick={openAdd}><Plus size={14} /> 新增</button>
      </div>
      {items.length === 0 ? (
        <div className="data-empty">
          <div className="data-empty-icon"><FileText size={32} /></div>
          <div className="data-empty-title">暂无章节指令</div>
          <div className="data-empty-desc">为每个章节定义写作目标和关键事件</div>
          <button className="btn btn-secondary" onClick={openAdd} style={{ marginTop: 12 }}>创建第一条</button>
        </div>
      ) : (
        <div className="data-grid">
          {items.map((ins) => (
            <div key={ins.id} className="data-card">
              <div className="data-card-header">
                <span className="data-card-badge">第 {ins.chapter_number} 章</span>
                <div className="data-card-actions">
                  <button className="btn-icon" onClick={() => openEdit(ins)}><Pencil size={14} /></button>
                  <button className="btn-icon btn-icon-danger" onClick={() => handleDelete(ins.id)}><Trash2 size={14} /></button>
                </div>
              </div>
              {ins.objective && <div className="data-card-title">{ins.objective}</div>}
              {ins.key_events && <div className="data-card-content">{ins.key_events}</div>}
              <div className="data-card-traits">
                {ins.emotion_tone && <span>基调: {ins.emotion_tone} </span>}
                {ins.word_target && <span>目标字数: {ins.word_target}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>{editingItem ? '编辑章节指令' : '新增章节指令'}</h3>
            <div className="form-group">
              <label>章节号</label>
              <input type="number" value={form.chapter_number} onChange={(e) => setForm({ ...form, chapter_number: e.target.value })} placeholder="章节号" disabled={!!editingItem} />
            </div>
            <div className="form-group">
              <label>写作目标</label>
              <textarea value={form.objective} onChange={(e) => setForm({ ...form, objective: e.target.value })} placeholder="本章要达成的目标" rows={2} />
            </div>
            <div className="form-group">
              <label>关键事件</label>
              <textarea value={form.key_events} onChange={(e) => setForm({ ...form, key_events: e.target.value })} placeholder="本章关键事件" rows={2} />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>需回收伏笔</label>
                <input type="text" value={form.plots_to_resolve} onChange={(e) => setForm({ ...form, plots_to_resolve: e.target.value })} placeholder="伏笔编码，逗号分隔" />
              </div>
              <div className="form-group">
                <label>需埋设伏笔</label>
                <input type="text" value={form.plots_to_plant} onChange={(e) => setForm({ ...form, plots_to_plant: e.target.value })} placeholder="伏笔编码，逗号分隔" />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>情感基调</label>
                <input type="text" value={form.emotion_tone} onChange={(e) => setForm({ ...form, emotion_tone: e.target.value })} placeholder="如：紧张、温馨、悲壮" />
              </div>
              <div className="form-group">
                <label>目标字数</label>
                <input type="number" value={form.word_target} onChange={(e) => setForm({ ...form, word_target: e.target.value })} placeholder="如：3000" />
              </div>
            </div>
            <div className="form-group">
              <label>结尾钩子</label>
              <input type="text" value={form.ending_hook} onChange={(e) => setForm({ ...form, ending_hook: e.target.value })} placeholder="章节结尾的悬念或钩子" />
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
