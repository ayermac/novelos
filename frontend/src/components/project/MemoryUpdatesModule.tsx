import { useState, useEffect, useCallback } from 'react'
import { get, post, put } from '../../lib/api'
import { normalizeOperationResult, isBusinessSuccess } from '../../lib/statusSemantics'
import {
  Database, ChevronDown, ChevronRight, CheckCircle2,
  Loader2, AlertCircle,
} from 'lucide-react'

interface MemoryBatch {
  id: string
  project_id: string
  chapter_number: number
  run_id: string | null
  status: string
  summary: string
  created_at: string
  updated_at: string
}

interface MemoryItem {
  id: string
  batch_id: string
  project_id: string
  target_table: string
  operation: string
  target_id: string | null
  before_json: string | null
  after_json: string
  confidence: number
  evidence_text: string
  rationale: string
  status: string
  error_message: string | null
  created_at: string
}

interface MemoryItemEditForm {
  target_table: string
  target_id: string
  operation: string
  before_json: string
  after_json: string
  confidence: string
  evidence_text: string
  rationale: string
}

interface BatchDetail extends MemoryBatch {
  items: MemoryItem[]
}

interface Props {
  projectId: string
}

const TABLE_LABELS: Record<string, string> = {
  characters: '角色',
  world_settings: '世界观',
  factions: '势力',
  outlines: '大纲',
  plot_holes: '伏笔',
  instructions: '章节指令',
  story_facts: '故事事实',
  project: '项目',
}

const OPERATION_LABELS: Record<string, string> = {
  create: '新建',
  update: '更新',
  resolve: '解决',
  deprecate: '废弃',
}

const TABLE_OPTIONS = Object.keys(TABLE_LABELS)
const OPERATION_OPTIONS = Object.keys(OPERATION_LABELS)

function formatJsonForEdit(value: string | null | undefined): string {
  if (!value) return '{}'
  try {
    return JSON.stringify(JSON.parse(value), null, 2)
  } catch {
    return value
  }
}

function compactJsonPreview(value: string | null | undefined): string {
  if (!value) return '{}'
  try {
    return JSON.stringify(JSON.parse(value), null, 2)
  } catch {
    return value
  }
}

function validateJsonObjectText(value: string, label: string): string | null {
  const text = value.trim()
  if (!text) return null
  try {
    const parsed = JSON.parse(text)
    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
      return `${label} 必须是 JSON 对象`
    }
  } catch {
    return `${label} 不是合法 JSON`
  }
  return null
}

const STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  applied: '已应用',
  ignored: '已忽略',
  failed: '失败',
  mixed: '混合',
}

export default function MemoryUpdatesModule({ projectId }: Props) {
  const [batches, setBatches] = useState<MemoryBatch[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedBatchId, setExpandedBatchId] = useState<string | null>(null)
  const [batchDetail, setBatchDetail] = useState<BatchDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [applying, setApplying] = useState<string | null>(null)
  const [ignoring, setIgnoring] = useState<string | null>(null)
  const [retrying, setRetrying] = useState<string | null>(null)
  const [editingItemId, setEditingItemId] = useState<string | null>(null)
  const [savingItemId, setSavingItemId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<MemoryItemEditForm | null>(null)
  const [editError, setEditError] = useState<string | null>(null)
  const [message, setMessage] = useState<{ type: 'success' | 'warning' | 'error'; text: string } | null>(null)

  const loadBatches = useCallback(async () => {
    setLoading(true)
    const res = await get<MemoryBatch[]>(`/projects/${projectId}/memory-batches`)
    if (res.ok && res.data) {
      setBatches(res.data)
    }
    setLoading(false)
  }, [projectId])

  useEffect(() => { loadBatches() }, [loadBatches])

  const loadBatchDetail = async (batchId: string) => {
    setDetailLoading(true)
    const res = await get<BatchDetail>(`/projects/${projectId}/memory-batches/${batchId}`)
    if (res.ok && res.data) {
      setBatchDetail(res.data)
    }
    setDetailLoading(false)
  }

  const handleExpand = (batchId: string) => {
    if (expandedBatchId === batchId) {
      setExpandedBatchId(null)
      setBatchDetail(null)
    } else {
      setExpandedBatchId(batchId)
      loadBatchDetail(batchId)
    }
  }

  const handleApply = async (batchId: string) => {
    setApplying(batchId)
    setMessage(null)
    const res = await post<Record<string, unknown>>('/memory/apply', { project_id: projectId, batch_id: batchId })
    if (res.ok) {
      const domainResult = normalizeOperationResult(res.data ?? {})
      if (isBusinessSuccess(domainResult)) {
        setMessage({ type: 'success', text: domainResult.user_message || '批次已应用' })
      } else if (domainResult.domain_status !== 'pending') {
        // Non-success with real domain info (partial_success, fallback, degraded, etc.)
        const type = domainResult.severity === 'error' ? 'error' : 'warning'
        setMessage({ type, text: domainResult.user_message || domainResult.message || '部分应用完成，请检查结果' })
      } else {
        // Legacy endpoint without domain_result — show success as before
        setMessage({ type: 'success', text: '批次已应用' })
      }
      await loadBatches()
      if (expandedBatchId === batchId) {
        await loadBatchDetail(batchId)
      }
    } else if (res.error?.code === 'NO_PENDING_MEMORY_ITEMS') {
      // Stale partial batch — refresh UI so user sees current state
      setMessage({ type: 'error', text: res.error?.message || '无待处理项' })
      await loadBatches()
      if (expandedBatchId === batchId) {
        await loadBatchDetail(batchId)
      }
    } else {
      setMessage({ type: 'error', text: res.error?.message || '应用失败' })
    }
    setApplying(null)
  }

  const handleIgnore = async (itemId: string) => {
    setIgnoring(itemId)
    setMessage(null)
    const res = await post('/memory/ignore', { project_id: projectId, item_id: itemId })
    if (res.ok) {
      setMessage({ type: 'success', text: '已忽略' })
      if (expandedBatchId) {
        await loadBatchDetail(expandedBatchId)
      }
      await loadBatches()
    } else {
      setMessage({ type: 'error', text: res.error?.message || '忽略失败' })
    }
    setIgnoring(null)
  }

  const handleRetry = async (batchId: string) => {
    setRetrying(batchId)
    setMessage(null)
    const res = await post('/memory/retry-failed', { project_id: projectId, batch_id: batchId })
    if (res.ok) {
      const retryData = res.data as { reset_count?: number } | undefined
      setMessage({ type: 'success', text: `已重置 ${retryData?.reset_count || 0} 个失败项` })
      await loadBatches()
      if (expandedBatchId === batchId) {
        await loadBatchDetail(batchId)
      }
    } else {
      setMessage({ type: 'error', text: res.error?.message || '重试失败' })
    }
    setRetrying(null)
  }

  const beginEditItem = (item: MemoryItem) => {
    setEditingItemId(item.id)
    setEditError(null)
    setEditForm({
      target_table: item.target_table,
      target_id: item.target_id || '',
      operation: item.operation,
      before_json: formatJsonForEdit(item.before_json),
      after_json: formatJsonForEdit(item.after_json),
      confidence: String(item.confidence ?? 0.8),
      evidence_text: item.evidence_text || '',
      rationale: item.rationale || '',
    })
  }

  const cancelEditItem = () => {
    setEditingItemId(null)
    setEditForm(null)
    setEditError(null)
  }

  const updateEditForm = (patch: Partial<MemoryItemEditForm>) => {
    setEditForm((current) => current ? { ...current, ...patch } : current)
    setEditError(null)
  }

  const saveEditItem = async (itemId: string) => {
    if (!editForm) return
    const afterJsonError = validateJsonObjectText(editForm.after_json, 'after_json')
    if (afterJsonError) {
      setEditError(afterJsonError)
      return
    }
    const beforeJsonError = validateJsonObjectText(editForm.before_json, 'before_json')
    if (beforeJsonError) {
      setEditError(beforeJsonError)
      return
    }
    const confidence = Number(editForm.confidence)
    if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
      setEditError('confidence 必须在 0 到 1 之间')
      return
    }

    setSavingItemId(itemId)
    setMessage(null)
    const res = await put<MemoryItem>(`/projects/${projectId}/memory-items/${itemId}`, {
      target_table: editForm.target_table,
      target_id: editForm.target_id.trim() || null,
      operation: editForm.operation,
      before_json: editForm.before_json.trim() || '{}',
      after_json: editForm.after_json.trim() || '{}',
      confidence,
      evidence_text: editForm.evidence_text,
      rationale: editForm.rationale,
    })
    if (res.ok) {
      setMessage({ type: 'success', text: '记忆项已保存，可重新应用' })
      cancelEditItem()
      if (expandedBatchId) {
        await loadBatchDetail(expandedBatchId)
      }
      await loadBatches()
    } else {
      setEditError(res.error?.message || '保存失败')
    }
    setSavingItemId(null)
  }

  if (loading) return <div className="module-loading">加载中...</div>

  // v6.6.7: Separate trusted vs fallback batches visually
  const isFallbackBatch = (batch: MemoryBatch) =>
    batch.summary.includes('状态卡兜底') ||
    batch.summary.toLowerCase().includes('fallback')

  const pendingBatches = batches.filter((b) => b.status === 'pending' || b.status === 'partial')
  const historyBatches = batches.filter((b) => b.status !== 'pending' && b.status !== 'partial')
  const fallbackBatches = pendingBatches.filter(isFallbackBatch)
  const trustedPendingBatches = pendingBatches.filter((b) => !isFallbackBatch(b))

  return (
    <div className="project-module">
      <div className="module-header">
        <h3><Database size={18} /> 记忆更新</h3>
        <button className="btn btn-secondary btn-sm" onClick={loadBatches}>刷新</button>
      </div>

      {message && (
        <div className={`memory-msg memory-msg-${message.type}`}>
          {message.type === 'success' ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
          {message.text}
        </div>
      )}

      {batches.length === 0 ? (
        <div className="data-empty">
          <div className="data-empty-icon"><Database size={32} /></div>
          <div className="data-empty-title">暂无记忆更新</div>
          <div className="data-empty-desc">Memory Curator 在章节审核通过后会自动提取项目资料变更建议</div>
        </div>
      ) : (
        <>
          {/* v6.6.7: Trusted pending batches */}
          {trustedPendingBatches.length > 0 && (
            <div className="memory-section">
              <h4 className="memory-section-title">待处理 ({trustedPendingBatches.length})</h4>
              {trustedPendingBatches.map((batch) => (
                <BatchCard
                  key={batch.id}
                  batch={batch}
                  expanded={expandedBatchId === batch.id}
                  detail={expandedBatchId === batch.id ? batchDetail : null}
                  detailLoading={detailLoading && expandedBatchId === batch.id}
                  onExpand={handleExpand}
                  onApply={handleApply}
                  onIgnore={handleIgnore}
                  onRetry={handleRetry}
                  onBeginEdit={beginEditItem}
                  onCancelEdit={cancelEditItem}
                  onEditChange={updateEditForm}
                  onSaveEdit={saveEditItem}
                  applying={applying === batch.id}
                  ignoring={ignoring}
                  retrying={retrying === batch.id}
                  editingItemId={editingItemId}
                  savingItemId={savingItemId}
                  editForm={editForm}
                  editError={editError}
                />
              ))}
            </div>
          )}

          {/* v6.6.7: Fallback batches — visually distinct */}
          {fallbackBatches.length > 0 && (
            <div className="memory-section">
              <h4 className="memory-section-title" style={{ color: 'var(--warning)' }}>
                待人工确认候选 ({fallbackBatches.length})
              </h4>
              <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
                以下批次来自状态卡兜底或低置信度提取，未经过 LLM 可信验证，请人工确认后再应用。
              </div>
              {fallbackBatches.map((batch) => (
                <BatchCard
                  key={batch.id}
                  batch={batch}
                  isFallback
                  expanded={expandedBatchId === batch.id}
                  detail={expandedBatchId === batch.id ? batchDetail : null}
                  detailLoading={detailLoading && expandedBatchId === batch.id}
                  onExpand={handleExpand}
                  onApply={handleApply}
                  onIgnore={handleIgnore}
                  onRetry={handleRetry}
                  onBeginEdit={beginEditItem}
                  onCancelEdit={cancelEditItem}
                  onEditChange={updateEditForm}
                  onSaveEdit={saveEditItem}
                  applying={applying === batch.id}
                  ignoring={ignoring}
                  retrying={retrying === batch.id}
                  editingItemId={editingItemId}
                  savingItemId={savingItemId}
                  editForm={editForm}
                  editError={editError}
                />
              ))}
            </div>
          )}

          {historyBatches.length > 0 && (
            <div className="memory-section">
              <h4 className="memory-section-title">历史 ({historyBatches.length})</h4>
              {historyBatches.map((batch) => (
                <BatchCard
                  key={batch.id}
                  batch={batch}
                  expanded={expandedBatchId === batch.id}
                  detail={expandedBatchId === batch.id ? batchDetail : null}
                  detailLoading={detailLoading && expandedBatchId === batch.id}
                  onExpand={handleExpand}
                  onApply={handleApply}
                  onIgnore={handleIgnore}
                  onRetry={handleRetry}
                  onBeginEdit={beginEditItem}
                  onCancelEdit={cancelEditItem}
                  onEditChange={updateEditForm}
                  onSaveEdit={saveEditItem}
                  applying={applying === batch.id}
                  ignoring={ignoring}
                  retrying={retrying === batch.id}
                  editingItemId={editingItemId}
                  savingItemId={savingItemId}
                  editForm={editForm}
                  editError={editError}
                />
              ))}
            </div>
          )}
        </>
      )}

      <style>{`
        .memory-section { margin-bottom: 24px; }
        .memory-section-title { font-size: 14px; font-weight: 600; color: var(--text-secondary, #6b7280); margin-bottom: 12px; }
        .memory-msg { display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-radius: 6px; font-size: 13px; margin-bottom: 16px; }
        .memory-msg-success { background: color-mix(in srgb, var(--success) 12%, var(--bg-primary)); border: 1px solid color-mix(in srgb, var(--success) 28%, transparent); color: var(--success); }
        .memory-msg-warning { background: color-mix(in srgb, var(--warning) 12%, var(--bg-primary)); border: 1px solid color-mix(in srgb, var(--warning) 28%, transparent); color: var(--warning); }
        .memory-msg-error { background: color-mix(in srgb, var(--danger) 12%, var(--bg-primary)); border: 1px solid color-mix(in srgb, var(--danger) 28%, transparent); color: var(--danger); }
        .batch-card { border: 1px solid var(--border-color, #e5e7eb); border-radius: 8px; margin-bottom: 8px; overflow: hidden; background: var(--bg-primary); }
        .batch-header { display: flex; align-items: center; gap: 10px; padding: 12px 14px; cursor: pointer; background: var(--bg-primary); transition: background 0.15s; }
        .batch-header:hover { background: var(--bg-tertiary); }
        .batch-toggle { color: var(--text-muted, #9ca3af); flex-shrink: 0; }
        .batch-summary { flex: 1; font-size: 14px; color: var(--text-primary, #111827); }
        .batch-meta { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
        .batch-chapter { font-size: 12px; color: var(--text-muted, #9ca3af); }
        .batch-status { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 500; }
        .batch-status-pending { background: color-mix(in srgb, var(--warning) 16%, transparent); color: var(--warning); }
        .batch-status-partial { background: color-mix(in srgb, var(--warning) 16%, transparent); color: var(--warning); }
        .batch-status-applied { background: color-mix(in srgb, var(--success) 16%, transparent); color: var(--success); }
        .batch-status-ignored { background: var(--bg-tertiary); color: var(--text-secondary); }
        .batch-actions { display: flex; gap: 6px; flex-shrink: 0; }
        .batch-detail { padding: 14px; background: var(--bg-secondary); border-top: 1px solid var(--border-color); }
        .batch-detail-loading { padding: 20px; text-align: center; color: var(--text-muted); font-size: 13px; }
        .item-card { background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 6px; padding: 12px; margin-bottom: 8px; }
        .item-card:last-child { margin-bottom: 0; }
        .item-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
        .item-table { font-size: 12px; padding: 2px 8px; border-radius: 4px; background: var(--accent-soft); color: var(--primary); font-weight: 500; }
        .item-op { font-size: 12px; padding: 2px 8px; border-radius: 4px; background: var(--bg-tertiary); color: var(--text-secondary); }
        .item-op-create { background: color-mix(in srgb, var(--success) 16%, transparent); color: var(--success); }
        .item-op-update { background: var(--accent-soft); color: var(--primary); }
        .item-op-resolve { background: color-mix(in srgb, var(--warning) 16%, transparent); color: var(--warning); }
        .item-op-deprecate { background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger); }
        .item-confidence { font-size: 11px; color: var(--text-muted); margin-left: auto; }
        .item-status { font-size: 11px; padding: 2px 6px; border-radius: 4px; }
        .item-status-pending { background: color-mix(in srgb, var(--warning) 16%, transparent); color: var(--warning); }
        .item-status-applied { background: color-mix(in srgb, var(--success) 16%, transparent); color: var(--success); }
        .item-status-ignored { background: var(--bg-tertiary); color: var(--text-secondary); }
        .item-status-failed { background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger); }
        .item-rationale { font-size: 13px; color: var(--text-secondary, #374151); margin-bottom: 4px; }
        .item-evidence { font-size: 12px; color: var(--text-muted, #9ca3af); line-height: 1.5; }
        .item-evidence-label { font-weight: 500; }
        .item-json { margin-top: 8px; padding: 8px; border-radius: 4px; background: var(--bg-secondary); border: 1px solid var(--border-color); font-size: 12px; line-height: 1.45; overflow-x: auto; white-space: pre-wrap; color: var(--text-secondary); }
        .item-error { font-size: 12px; color: var(--danger); line-height: 1.5; margin-top: 4px; background: color-mix(in srgb, var(--danger) 12%, var(--bg-primary)); padding: 6px 8px; border-radius: 4px; }
        .item-error-label { font-weight: 500; }
        .item-actions { display: flex; gap: 6px; margin-top: 8px; }
        .item-edit-form { margin-top: 10px; padding: 10px; border: 1px solid var(--border-color); border-radius: 6px; background: var(--bg-secondary); display: grid; gap: 10px; }
        .item-edit-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
        .item-edit-field { display: grid; gap: 4px; font-size: 12px; color: var(--text-secondary); }
        .item-edit-field input, .item-edit-field select, .item-edit-field textarea { width: 100%; box-sizing: border-box; border: 1px solid var(--border-color); border-radius: 4px; background: var(--bg-primary); color: var(--text-primary); padding: 6px 8px; font-size: 12px; font-family: inherit; }
        .item-edit-field textarea { min-height: 74px; resize: vertical; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
        .item-edit-field-wide { grid-column: 1 / -1; }
        .item-edit-error { font-size: 12px; color: var(--danger); }
        .btn-xs { padding: 3px 8px; font-size: 11px; border-radius: 4px; border: 1px solid var(--border-color); background: var(--bg-primary); color: var(--text-secondary); cursor: pointer; transition: all 0.15s; }
        .btn-xs:hover { background: var(--bg-tertiary); }
        .btn-xs-primary { color: var(--primary); border-color: color-mix(in srgb, var(--primary) 28%, transparent); }
        .btn-xs-primary:hover { background: color-mix(in srgb, var(--primary) 12%, var(--bg-primary)); }
        .btn-xs-danger { color: var(--danger); border-color: color-mix(in srgb, var(--danger) 28%, transparent); }
        .btn-xs-danger:hover { background: color-mix(in srgb, var(--danger) 12%, var(--bg-primary)); }
      `}</style>
    </div>
  )
}

function BatchCard({
  batch,
  expanded,
  detail,
  detailLoading,
  onExpand,
  onApply,
  onIgnore,
  onRetry,
  onBeginEdit,
  onCancelEdit,
  onEditChange,
  onSaveEdit,
  applying,
  ignoring,
  retrying,
  editingItemId,
  savingItemId,
  editForm,
  editError,
  isFallback,
}: {
  batch: MemoryBatch
  expanded: boolean
  detail: BatchDetail | null
  detailLoading: boolean
  onExpand: (id: string) => void
  onApply: (id: string) => void
  onIgnore: (itemId: string) => void
  onRetry: (id: string) => void
  onBeginEdit: (item: MemoryItem) => void
  onCancelEdit: () => void
  onEditChange: (patch: Partial<MemoryItemEditForm>) => void
  onSaveEdit: (itemId: string) => void
  applying: boolean
  ignoring: string | null
  retrying: boolean
  editingItemId: string | null
  savingItemId: string | null
  editForm: MemoryItemEditForm | null
  editError: string | null
  isFallback?: boolean
}) {
  const canApply = batch.status === 'pending' || batch.status === 'partial'
  const failedCount = detail?.items?.filter((i) => i.status === 'failed').length ?? 0

  return (
    <div className="batch-card" style={isFallback ? { borderLeft: '3px solid var(--warning)' } : undefined}>
      <div className="batch-header" onClick={() => onExpand(batch.id)}>
        <span className="batch-toggle">
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </span>
        <span className="batch-summary">
          {batch.summary}
          {isFallback && <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--warning)', fontWeight: 500 }}>[低可信]</span>}
        </span>
        <div className="batch-meta">
          <span className="batch-chapter">第{batch.chapter_number}章</span>
          <span className={`batch-status batch-status-${batch.status}`}>
            {STATUS_LABELS[batch.status] || batch.status}
            {failedCount > 0 && ` (${failedCount}项失败)`}
          </span>
        </div>
        {canApply && (
          <div className="batch-actions">
            {batch.status === 'partial' && failedCount > 0 && (
              <button
                className="btn btn-secondary btn-sm"
                onClick={(e) => { e.stopPropagation(); onRetry(batch.id) }}
                disabled={retrying}
              >
                {retrying ? <Loader2 size={12} className="spin" /> : <AlertCircle size={12} />}
                {retrying ? '重置中...' : '重试失败项'}
              </button>
            )}
            <button
              className={`btn ${isFallback ? 'btn-secondary' : 'btn-primary'} btn-sm`}
              onClick={(e) => { e.stopPropagation(); onApply(batch.id) }}
              disabled={applying}
            >
              {applying ? <Loader2 size={12} className="spin" /> : <CheckCircle2 size={12} />}
              {applying ? '应用中...' : '全部应用'}
            </button>
          </div>
        )}
      </div>

      {expanded && (
        <div className="batch-detail">
          {detailLoading ? (
            <div className="batch-detail-loading">加载详情...</div>
          ) : detail?.items ? (
            detail.items.map((item) => {
              const activeEditForm = editingItemId === item.id ? editForm : null
              const isEditing = Boolean(activeEditForm)
              const canEdit = item.status === 'pending' || item.status === 'failed'
              return (
                <div key={item.id} className="item-card">
                  <div className="item-header">
                    <span className="item-table">{TABLE_LABELS[item.target_table] || item.target_table}</span>
                    <span className={`item-op item-op-${item.operation}`}>
                      {OPERATION_LABELS[item.operation] || item.operation}
                    </span>
                    {item.confidence < 1 && (
                      <span className="item-confidence">
                        置信度 {Math.round(item.confidence * 100)}%
                      </span>
                    )}
                    <span className={`item-status item-status-${item.status}`}>
                      {STATUS_LABELS[item.status] || item.status}
                    </span>
                  </div>
                  <div className="item-rationale">{item.rationale}</div>
                  {item.evidence_text && (
                    <div className="item-evidence">
                      <span className="item-evidence-label">证据: </span>
                      {item.evidence_text}
                    </div>
                  )}
                  <pre className="item-json">{compactJsonPreview(item.after_json)}</pre>
                  {item.error_message && (
                    <div className="item-error">
                      <span className="item-error-label">失败原因: </span>
                      {item.error_message}
                    </div>
                  )}

                  {isEditing && (
                    <div className="item-edit-form">
                      <div className="item-edit-grid">
                        <label className="item-edit-field">
                          目标表
                          <select
                            value={activeEditForm?.target_table || item.target_table}
                            onChange={(e) => onEditChange({ target_table: e.target.value })}
                          >
                            {TABLE_OPTIONS.map((option) => (
                              <option key={option} value={option}>{TABLE_LABELS[option] || option}</option>
                            ))}
                          </select>
                        </label>
                        <label className="item-edit-field">
                          操作
                          <select
                            value={activeEditForm?.operation || item.operation}
                            onChange={(e) => onEditChange({ operation: e.target.value })}
                          >
                            {OPERATION_OPTIONS.map((option) => (
                              <option key={option} value={option}>{OPERATION_LABELS[option] || option}</option>
                            ))}
                          </select>
                        </label>
                        <label className="item-edit-field">
                          target_id
                          <input
                            value={activeEditForm?.target_id || ''}
                            onChange={(e) => onEditChange({ target_id: e.target.value })}
                            placeholder="可留空，由系统匹配"
                          />
                        </label>
                        <label className="item-edit-field">
                          置信度
                          <input
                            value={activeEditForm?.confidence || String(item.confidence ?? 0.8)}
                            onChange={(e) => onEditChange({ confidence: e.target.value })}
                            inputMode="decimal"
                          />
                        </label>
                        <label className="item-edit-field item-edit-field-wide">
                          after_json
                          <textarea
                            value={activeEditForm?.after_json || '{}'}
                            onChange={(e) => onEditChange({ after_json: e.target.value })}
                            rows={8}
                          />
                        </label>
                        <label className="item-edit-field item-edit-field-wide">
                          before_json
                          <textarea
                            value={activeEditForm?.before_json || '{}'}
                            onChange={(e) => onEditChange({ before_json: e.target.value })}
                            rows={4}
                          />
                        </label>
                        <label className="item-edit-field item-edit-field-wide">
                          证据
                          <textarea
                            value={activeEditForm?.evidence_text || ''}
                            onChange={(e) => onEditChange({ evidence_text: e.target.value })}
                            rows={3}
                          />
                        </label>
                        <label className="item-edit-field item-edit-field-wide">
                          理由
                          <textarea
                            value={activeEditForm?.rationale || ''}
                            onChange={(e) => onEditChange({ rationale: e.target.value })}
                            rows={3}
                          />
                        </label>
                      </div>
                      {editError && <div className="item-edit-error">{editError}</div>}
                      <div className="item-actions">
                        <button
                          className="btn-xs btn-xs-primary"
                          onClick={() => onSaveEdit(item.id)}
                          disabled={savingItemId === item.id}
                        >
                          {savingItemId === item.id ? '保存中...' : '保存校正'}
                        </button>
                        <button className="btn-xs" onClick={onCancelEdit} disabled={savingItemId === item.id}>
                          取消
                        </button>
                      </div>
                    </div>
                  )}

                  {canEdit && !isEditing && (
                    <div className="item-actions">
                      <button
                        className="btn-xs btn-xs-primary"
                        onClick={() => onBeginEdit(item)}
                      >
                        校正
                      </button>
                      {item.status === 'pending' && (
                        <button
                          className="btn-xs btn-xs-danger"
                          onClick={() => onIgnore(item.id)}
                          disabled={ignoring === item.id}
                        >
                          {ignoring === item.id ? '忽略中...' : '忽略'}
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )
            })
          ) : (
            <div className="batch-detail-loading">无详情</div>
          )}
        </div>
      )}
    </div>
  )
}
