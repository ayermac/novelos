import { useState, useEffect, useCallback } from 'react'
import { get, post } from '../../lib/api'
import {
  BookOpen, ChevronDown, ChevronRight, Edit3, Save, X,
  CheckCircle2, AlertCircle, Filter,
} from 'lucide-react'

interface StoryFact {
  id: string
  project_id: string
  fact_key: string
  fact_type: string
  subject: string | null
  attribute: string | null
  value_json: string
  unit: string | null
  scope: string | null
  confidence: number
  source_chapter: number | null
  source_agent: string | null
  last_changed_chapter: number | null
  status: string
  created_at: string
  updated_at: string
}

interface FactEvent {
  id: string
  chapter_number: number
  agent_id: string
  event_type: string
  fact_id: string
  before_json: string | null
  after_json: string | null
  rationale: string
  validation_status: string
  created_at: string
}

interface Props {
  projectId: string
}

const FACT_TYPE_LABELS: Record<string, string> = {
  character_state: '角色状态',
  world_rule: '世界规则',
  relationship: '关系',
  inventory: '物品',
  timeline: '时间线',
  power_level: '实力等级',
  location: '地点',
  organization: '组织',
  event: '事件',
}

const STATUS_LABELS: Record<string, string> = {
  active: '有效',
  deprecated: '已废弃',
  corrected: '已修正',
}

export default function FactLedgerModule({ projectId }: Props) {
  const [facts, setFacts] = useState<StoryFact[]>([])
  const [loading, setLoading] = useState(true)
  const [filterType, setFilterType] = useState<string>('')
  const [filterStatus, setFilterStatus] = useState<string>('active')
  const [expandedFactId, setExpandedFactId] = useState<string | null>(null)
  const [events, setEvents] = useState<FactEvent[]>([])
  const [eventsLoading, setEventsLoading] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [editNote, setEditNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const loadFacts = useCallback(async () => {
    setLoading(true)
    const params = new URLSearchParams()
    params.set('project_id', projectId)
    if (filterType) params.set('fact_type', filterType)
    if (filterStatus) params.set('status', filterStatus)
    const res = await get<StoryFact[]>(`/facts?${params.toString()}`)
    if (res.ok && res.data) {
      setFacts(res.data)
    }
    setLoading(false)
  }, [projectId, filterType, filterStatus])

  useEffect(() => { loadFacts() }, [loadFacts])

  const loadEvents = async (factKey: string) => {
    setEventsLoading(true)
    const res = await get<StoryFact & { events?: FactEvent[] }>(
      `/facts/${factKey}/history?project_id=${projectId}`,
    )
    if (res.ok && res.data) {
      setEvents(res.data.events || [])
    }
    setEventsLoading(false)
  }

  const handleExpand = (factId: string) => {
    if (expandedFactId === factId) {
      setExpandedFactId(null)
      setEvents([])
    } else {
      setExpandedFactId(factId)
      const fact = facts.find((f) => f.id === factId)
      if (fact) loadEvents(fact.fact_key)
    }
  }

  const handleEdit = (fact: StoryFact) => {
    setEditingId(fact.id)
    setEditValue(fact.value_json)
    setEditNote('')
  }

  const handleCancelEdit = () => {
    setEditingId(null)
    setEditValue('')
    setEditNote('')
  }

  const handleSave = async (factId: string) => {
    setSaving(true)
    setMessage(null)
    const res = await post('/facts/correct', {
      project_id: projectId,
      fact_id: factId,
      value_json: editValue,
      correction_note: editNote || '用户手动修正',
    })
    if (res.ok) {
      setMessage({ type: 'success', text: '事实已修正' })
      setEditingId(null)
      loadFacts()
      if (expandedFactId === factId) {
        const fact = facts.find((f) => f.id === factId)
        if (fact) loadEvents(fact.fact_key)
      }
    } else {
      setMessage({ type: 'error', text: res.error?.message || '保存失败' })
    }
    setSaving(false)
  }

  const parseValue = (valueJson: string): string => {
    try {
      const parsed = JSON.parse(valueJson)
      if (typeof parsed === 'string') return parsed
      return JSON.stringify(parsed, null, 2)
    } catch {
      return valueJson
    }
  }

  if (loading) return <div className="module-loading">加载中...</div>

  const factTypes = [...new Set(facts.map((f) => f.fact_type))].sort()

  return (
    <div className="project-module">
      <div className="module-header">
        <h3><BookOpen size={18} /> 事实账本</h3>
        <button className="btn btn-secondary btn-sm" onClick={loadFacts}>刷新</button>
      </div>

      {message && (
        <div className={`fact-msg fact-msg-${message.type}`}>
          {message.type === 'success' ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
          {message.text}
        </div>
      )}

      {/* Filters */}
      <div className="fact-filters">
        <Filter size={14} />
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className="fact-filter-select"
        >
          <option value="">全部类型</option>
          {factTypes.map((t) => (
            <option key={t} value={t}>{FACT_TYPE_LABELS[t] || t}</option>
          ))}
        </select>
        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          className="fact-filter-select"
        >
          <option value="">全部状态</option>
          <option value="active">有效</option>
          <option value="deprecated">已废弃</option>
          <option value="corrected">已修正</option>
        </select>
        <span className="fact-count">{facts.length} 条事实</span>
      </div>

      {facts.length === 0 ? (
        <div className="data-empty">
          <div className="data-empty-icon"><BookOpen size={32} /></div>
          <div className="data-empty-title">暂无故事事实</div>
          <div className="data-empty-desc">Memory Curator 在章节审核通过后会自动提取故事事实</div>
        </div>
      ) : (
        <div className="fact-list">
          {facts.map((fact) => (
            <div key={fact.id} className="fact-card">
              <div className="fact-header" onClick={() => handleExpand(fact.id)}>
                <span className="fact-toggle">
                  {expandedFactId === fact.id ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                </span>
                <div className="fact-key-info">
                  <span className="fact-key">{fact.fact_key}</span>
                  <span className="fact-type-badge">{FACT_TYPE_LABELS[fact.fact_type] || fact.fact_type}</span>
                </div>
                <div className="fact-sa">
                  {fact.subject && <span className="fact-subject">{fact.subject}</span>}
                  {fact.attribute && <span className="fact-attr">.{fact.attribute}</span>}
                </div>
                <span className={`fact-status fact-status-${fact.status}`}>
                  {STATUS_LABELS[fact.status] || fact.status}
                </span>
                {fact.source_chapter && (
                  <span className="fact-source">Ch.{fact.source_chapter}</span>
                )}
                {fact.status === 'active' && editingId !== fact.id && (
                  <button
                    className="btn-icon"
                    onClick={(e) => { e.stopPropagation(); handleEdit(fact) }}
                    title="修正"
                  >
                    <Edit3 size={14} />
                  </button>
                )}
              </div>

              {editingId === fact.id ? (
                <div className="fact-edit">
                  <label>
                    <span>值 (JSON)</span>
                    <textarea
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      rows={3}
                    />
                  </label>
                  <label>
                    <span>修正说明</span>
                    <input
                      type="text"
                      value={editNote}
                      onChange={(e) => setEditNote(e.target.value)}
                      placeholder="修正原因..."
                    />
                  </label>
                  <div className="fact-edit-actions">
                    <button className="btn-xs" onClick={handleCancelEdit}>
                      <X size={12} /> 取消
                    </button>
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => handleSave(fact.id)}
                      disabled={saving}
                    >
                      {saving ? '保存中...' : <><Save size={12} /> 保存</>}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="fact-value">
                  <code>{parseValue(fact.value_json)}</code>
                  {fact.unit && <span className="fact-unit">{fact.unit}</span>}
                  <span className="fact-confidence">置信度 {Math.round(fact.confidence * 100)}%</span>
                </div>
              )}

              {expandedFactId === fact.id && (
                <div className="fact-events">
                  <h5>变更历史</h5>
                  {eventsLoading ? (
                    <div className="fact-events-loading">加载中...</div>
                  ) : events.length === 0 ? (
                    <div className="fact-events-empty">暂无变更记录</div>
                  ) : (
                    events.map((evt) => (
                      <div key={evt.id} className="event-item">
                        <div className="event-header">
                          <span className="event-type">{evt.event_type}</span>
                          <span className="event-agent">{evt.agent_id}</span>
                          {evt.chapter_number > 0 && (
                            <span className="event-chapter">Ch.{evt.chapter_number}</span>
                          )}
                          <span className="event-time">{new Date(evt.created_at).toLocaleString('zh-CN')}</span>
                        </div>
                        <div className="event-rationale">{evt.rationale}</div>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <style>{`
        .fact-msg { display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-radius: 6px; font-size: 13px; margin-bottom: 16px; }
        .fact-msg-success { background: #f0fdf4; border: 1px solid #bbf7d0; color: #065f46; }
        .fact-msg-error { background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; }
        .fact-filters { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; color: var(--text-muted, #9ca3af); }
        .fact-filter-select { padding: 6px 10px; border: 1px solid var(--border, #d1d5db); border-radius: 6px; font-size: 13px; background: var(--bg-primary, #fff); color: var(--text-primary, #111827); }
        .fact-count { font-size: 13px; color: var(--text-muted, #9ca3af); margin-left: auto; }
        .fact-list { display: flex; flex-direction: column; gap: 8px; }
        .fact-card { border: 1px solid var(--border, #e5e7eb); border-radius: 8px; overflow: hidden; }
        .fact-header { display: flex; align-items: center; gap: 8px; padding: 10px 14px; cursor: pointer; background: var(--bg-primary, #fff); transition: background 0.15s; }
        .fact-header:hover { background: var(--bg-hover, #f9fafb); }
        .fact-toggle { color: var(--text-muted, #9ca3af); flex-shrink: 0; }
        .fact-key-info { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
        .fact-key { font-weight: 600; font-size: 13px; color: var(--text-primary, #111827); }
        .fact-type-badge { font-size: 11px; padding: 1px 6px; border-radius: 4px; background: #dbeafe; color: #1d4ed8; }
        .fact-sa { font-size: 13px; color: var(--text-secondary, #374151); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .fact-subject { font-weight: 500; }
        .fact-attr { color: var(--text-muted, #9ca3af); }
        .fact-status { font-size: 11px; padding: 2px 6px; border-radius: 4px; flex-shrink: 0; }
        .fact-status-active { background: #d1fae5; color: #065f46; }
        .fact-status-deprecated { background: #f3f4f6; color: #6b7280; }
        .fact-status-corrected { background: #fef3c7; color: #92400e; }
        .fact-source { font-size: 11px; color: var(--text-muted, #9ca3af); flex-shrink: 0; }
        .fact-value { padding: 8px 14px 10px 38px; font-size: 13px; color: var(--text-secondary, #374151); display: flex; align-items: baseline; gap: 8px; }
        .fact-value code { font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px; background: var(--bg-secondary, #f3f4f6); padding: 2px 6px; border-radius: 4px; max-width: 500px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .fact-unit { font-size: 12px; color: var(--text-muted, #9ca3af); }
        .fact-confidence { font-size: 11px; color: var(--text-muted, #9ca3af); margin-left: auto; }
        .fact-edit { padding: 12px 14px 12px 38px; background: var(--bg-secondary, #f9fafb); border-top: 1px solid var(--border, #e5e7eb); }
        .fact-edit label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-secondary, #6b7280); margin-bottom: 10px; }
        .fact-edit textarea, .fact-edit input { padding: 6px 8px; border: 1px solid var(--border, #d1d5db); border-radius: 4px; font-size: 13px; background: var(--bg-primary, #fff); font-family: inherit; }
        .fact-edit textarea { font-family: 'SF Mono', 'Fira Code', monospace; resize: vertical; }
        .fact-edit-actions { display: flex; gap: 6px; justify-content: flex-end; }
        .fact-events { padding: 12px 14px 12px 38px; background: var(--bg-secondary, #f9fafb); border-top: 1px solid var(--border, #e5e7eb); }
        .fact-events h5 { font-size: 13px; font-weight: 600; margin: 0 0 10px; color: var(--text-secondary, #374151); }
        .fact-events-loading, .fact-events-empty { font-size: 12px; color: var(--text-muted, #9ca3af); padding: 8px 0; }
        .event-item { padding: 8px 0; border-bottom: 1px solid var(--border-light, #f3f4f6); }
        .event-item:last-child { border-bottom: none; }
        .event-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
        .event-type { font-size: 11px; padding: 1px 6px; border-radius: 4px; background: #f3f4f6; color: #374151; }
        .event-agent { font-size: 11px; color: var(--text-muted, #9ca3af); }
        .event-chapter { font-size: 11px; color: var(--text-muted, #9ca3af); }
        .event-time { font-size: 11px; color: var(--text-muted, #9ca3af); margin-left: auto; }
        .event-rationale { font-size: 12px; color: var(--text-secondary, #6b7280); line-height: 1.5; }
      `}</style>
    </div>
  )
}
