import { useState, useEffect, useCallback } from 'react'
import { get, post } from '../../lib/api'
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
  created_at: string
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

const STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  applied: '已应用',
  ignored: '已忽略',
  failed: '失败',
}

export default function MemoryUpdatesModule({ projectId }: Props) {
  const [batches, setBatches] = useState<MemoryBatch[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedBatchId, setExpandedBatchId] = useState<string | null>(null)
  const [batchDetail, setBatchDetail] = useState<BatchDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [applying, setApplying] = useState<string | null>(null)
  const [ignoring, setIgnoring] = useState<string | null>(null)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

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
    const res = await post('/memory/apply', { project_id: projectId, batch_id: batchId })
    if (res.ok) {
      setMessage({ type: 'success', text: '批次已应用' })
      await loadBatches()
      if (expandedBatchId === batchId) {
        await loadBatchDetail(batchId)
      }
    } else if (res.error?.code === 'NO_PENDING_MEMORY_ITEMS') {
      // Stale partial batch — refresh UI just like success so user sees current state
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

  if (loading) return <div className="module-loading">加载中...</div>

  const pendingBatches = batches.filter((b) => b.status === 'pending' || b.status === 'partial')
  const historyBatches = batches.filter((b) => b.status !== 'pending' && b.status !== 'partial')

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
          {pendingBatches.length > 0 && (
            <div className="memory-section">
              <h4 className="memory-section-title">待处理 ({pendingBatches.length})</h4>
              {pendingBatches.map((batch) => (
                <BatchCard
                  key={batch.id}
                  batch={batch}
                  expanded={expandedBatchId === batch.id}
                  detail={expandedBatchId === batch.id ? batchDetail : null}
                  detailLoading={detailLoading && expandedBatchId === batch.id}
                  onExpand={handleExpand}
                  onApply={handleApply}
                  onIgnore={handleIgnore}
                  applying={applying === batch.id}
                  ignoring={ignoring}
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
                  applying={applying === batch.id}
                  ignoring={ignoring}
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
        .memory-msg-success { background: #f0fdf4; border: 1px solid #bbf7d0; color: #065f46; }
        .memory-msg-error { background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; }
        .batch-card { border: 1px solid var(--border, #e5e7eb); border-radius: 8px; margin-bottom: 8px; overflow: hidden; }
        .batch-header { display: flex; align-items: center; gap: 10px; padding: 12px 14px; cursor: pointer; background: var(--bg-primary, #fff); transition: background 0.15s; }
        .batch-header:hover { background: var(--bg-hover, #f9fafb); }
        .batch-toggle { color: var(--text-muted, #9ca3af); flex-shrink: 0; }
        .batch-summary { flex: 1; font-size: 14px; color: var(--text-primary, #111827); }
        .batch-meta { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
        .batch-chapter { font-size: 12px; color: var(--text-muted, #9ca3af); }
        .batch-status { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 500; }
        .batch-status-pending { background: #fef3c7; color: #92400e; }
        .batch-status-partial { background: #fef3c7; color: #92400e; }
        .batch-status-applied { background: #d1fae5; color: #065f46; }
        .batch-status-ignored { background: #f3f4f6; color: #6b7280; }
        .batch-actions { display: flex; gap: 6px; flex-shrink: 0; }
        .batch-detail { padding: 14px; background: var(--bg-secondary, #f9fafb); border-top: 1px solid var(--border, #e5e7eb); }
        .batch-detail-loading { padding: 20px; text-align: center; color: var(--text-muted); font-size: 13px; }
        .item-card { background: var(--bg-primary, #fff); border: 1px solid var(--border, #e5e7eb); border-radius: 6px; padding: 12px; margin-bottom: 8px; }
        .item-card:last-child { margin-bottom: 0; }
        .item-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
        .item-table { font-size: 12px; padding: 2px 8px; border-radius: 4px; background: #dbeafe; color: #1d4ed8; font-weight: 500; }
        .item-op { font-size: 12px; padding: 2px 8px; border-radius: 4px; background: #f3f4f6; color: #374151; }
        .item-op-create { background: #d1fae5; color: #065f46; }
        .item-op-update { background: #dbeafe; color: #1d4ed8; }
        .item-op-resolve { background: #fef3c7; color: #92400e; }
        .item-op-deprecate { background: #fee2e2; color: #991b1b; }
        .item-confidence { font-size: 11px; color: var(--text-muted); margin-left: auto; }
        .item-status { font-size: 11px; padding: 2px 6px; border-radius: 4px; }
        .item-status-pending { background: #fef3c7; color: #92400e; }
        .item-status-applied { background: #d1fae5; color: #065f46; }
        .item-status-ignored { background: #f3f4f6; color: #6b7280; }
        .item-status-failed { background: #fee2e2; color: #991b1b; }
        .item-rationale { font-size: 13px; color: var(--text-secondary, #374151); margin-bottom: 4px; }
        .item-evidence { font-size: 12px; color: var(--text-muted, #9ca3af); line-height: 1.5; }
        .item-evidence-label { font-weight: 500; }
        .item-actions { display: flex; gap: 6px; margin-top: 8px; }
        .btn-xs { padding: 3px 8px; font-size: 11px; border-radius: 4px; border: 1px solid var(--border, #d1d5db); background: var(--bg-primary, #fff); color: var(--text-secondary, #374151); cursor: pointer; transition: all 0.15s; }
        .btn-xs:hover { background: var(--bg-hover, #f9fafb); }
        .btn-xs-danger { color: #dc2626; border-color: #fecaca; }
        .btn-xs-danger:hover { background: #fef2f2; }
      `}</style>
    </div>
  )
}

function BatchCard({
  batch, expanded, detail, detailLoading, onExpand, onApply, onIgnore, applying, ignoring,
}: {
  batch: MemoryBatch
  expanded: boolean
  detail: BatchDetail | null
  detailLoading: boolean
  onExpand: (id: string) => void
  onApply: (id: string) => void
  onIgnore: (itemId: string) => void
  applying: boolean
  ignoring: string | null
}) {
  const canApply = batch.status === 'pending' || batch.status === 'partial'

  return (
    <div className="batch-card">
      <div className="batch-header" onClick={() => onExpand(batch.id)}>
        <span className="batch-toggle">
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </span>
        <span className="batch-summary">{batch.summary}</span>
        <div className="batch-meta">
          <span className="batch-chapter">第{batch.chapter_number}章</span>
          <span className={`batch-status batch-status-${batch.status}`}>
            {STATUS_LABELS[batch.status] || batch.status}
          </span>
        </div>
        {canApply && (
          <div className="batch-actions">
            <button
              className="btn btn-primary btn-sm"
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
            detail.items.map((item) => (
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
                {item.status === 'pending' && (
                  <div className="item-actions">
                    <button
                      className="btn-xs btn-xs-danger"
                      onClick={() => onIgnore(item.id)}
                      disabled={ignoring === item.id}
                    >
                      {ignoring === item.id ? '忽略中...' : '忽略'}
                    </button>
                  </div>
                )}
              </div>
            ))
          ) : (
            <div className="batch-detail-loading">无详情</div>
          )}
        </div>
      )}
    </div>
  )
}
