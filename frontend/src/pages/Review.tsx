import { useEffect, useState } from 'react'
import { get, post } from '../lib/api'
import StatusBadge from '../components/StatusBadge'
import EmptyState from '../components/EmptyState'
import ErrorState from '../components/ErrorState'
import PageHeader from '../components/PageHeader'

interface ReviewItem {
  project_id: string
  project_name: string
  chapter_number: number
  status: string
  quality_score?: number
  issue_count: number
  last_run_id: string
}

interface ReviewData {
  queue: ReviewItem[]
  stats: {
    review: number
    blocking: number
    approved: number
    rejected: number
  }
}

export default function Review() {
  const [data, setData] = useState<ReviewData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [rejectModal, setRejectModal] = useState<ReviewItem | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  const load = () => {
    setLoading(true)
    setError('')
    get<ReviewData>('/review/workbench').then((res) => {
      if (res.ok && res.data) {
        setData(res.data)
      } else {
        setError(res.error?.message || '获取审核工作台失败')
      }
      setLoading(false)
    })
  }

  const handleApprove = async (item: ReviewItem) => {
    const key = `${item.project_id}-${item.chapter_number}`
    setActionLoading(key)
    try {
      const res = await post('/review/approve', {
        project_id: item.project_id,
        chapter_number: item.chapter_number,
      })
      if (res.ok) {
        load()
      } else {
        setError(res.error?.message || '审核通过失败')
      }
    } catch {
      setError('操作失败')
    } finally {
      setActionLoading(null)
    }
  }

  const handleReject = async () => {
    if (!rejectModal || !rejectReason.trim()) return
    const key = `${rejectModal.project_id}-${rejectModal.chapter_number}`
    setActionLoading(key)
    try {
      const res = await post('/review/reject', {
        project_id: rejectModal.project_id,
        chapter_number: rejectModal.chapter_number,
        reason: rejectReason,
        target: 'author',
      })
      if (res.ok) {
        setRejectModal(null)
        setRejectReason('')
        load()
      } else {
        setError(res.error?.message || '驳回失败')
      }
    } catch {
      setError('操作失败')
    } finally {
      setActionLoading(null)
    }
  }

  useEffect(() => {
    load()
  }, [])

  if (loading) {
    return <div>加载中...</div>
  }

  if (error) {
    return (
      <ErrorState
        title="加载失败"
        message={error}
        onRetry={load}
      />
    )
  }

  if (!data) {
    return (
      <ErrorState
        title="加载失败"
        message="无法获取审核数据"
        onRetry={load}
      />
    )
  }

  return (
    <div>
      <PageHeader title="审核工作台" />

      {/* Info Banner */}
      <div className="alert alert-info" style={{ marginBottom: 'var(--spacing-lg)' }}>
        <strong>审核工作台说明</strong>
        <div style={{ marginTop: '4px', fontSize: '14px' }}>
          审核队列用于人工复核章节质量。当前流程下，章节生成后会直接发布，可在项目工作台查看正文。
          如需启用人工审核流程，请在配置中心调整发布策略。
        </div>
      </div>

      {/* Stats */}
      <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)', marginBottom: 'var(--spacing-lg)' }}>
        <div className="stat-card">
          <h3>待审核</h3>
          <div className="stat-value">{data.stats.review}</div>
        </div>
        <div className="stat-card">
          <h3>阻塞</h3>
          <div className="stat-value" style={{ color: 'var(--danger)' }}>
            {data.stats.blocking}
          </div>
        </div>
        <div className="stat-card">
          <h3>已通过</h3>
          <div className="stat-value" style={{ color: 'var(--success)' }}>
            {data.stats.approved}
          </div>
        </div>
        <div className="stat-card">
          <h3>需返修</h3>
          <div className="stat-value" style={{ color: 'var(--warning)' }}>
            {data.stats.rejected}
          </div>
        </div>
      </div>

      {/* Queue */}
      <div className="card">
        <div className="card-header">
          <h3>审核队列</h3>
        </div>
        <div className="card-body">
          {data.queue.length > 0 ? (
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>章节</th>
                    <th>项目</th>
                    <th>状态</th>
                    <th>质量分</th>
                    <th>问题数</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {data.queue.map((item) => {
                    const actionKey = `${item.project_id}-${item.chapter_number}`
                    const isActionLoading = actionLoading === actionKey
                    const canAction = item.status === 'review'
                    return (
                      <tr key={actionKey}>
                        <td>第 {item.chapter_number} 章</td>
                        <td>{item.project_name}</td>
                        <td>
                          <StatusBadge status={item.status} />
                        </td>
                        <td>{item.quality_score ?? '-'}</td>
                        <td>{item.issue_count}</td>
                        <td>
                          {canAction ? (
                            <div style={{ display: 'flex', gap: '8px' }}>
                              <button
                                className="btn btn-primary btn-sm"
                                onClick={() => handleApprove(item)}
                                disabled={isActionLoading}
                              >
                                {isActionLoading ? '处理中...' : '通过'}
                              </button>
                              <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => setRejectModal(item)}
                                disabled={isActionLoading}
                              >
                                驳回
                              </button>
                            </div>
                          ) : (
                            <span className="text-secondary">-</span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="暂无待审核章节"
              hint="当前流程下章节生成后会直接发布。已发布章节可在项目工作台查看正文和运行记录。如需启用人工审核流程，请在配置中心调整发布策略。"
              actions={[
                { label: '查看项目列表', to: '/projects' },
                { label: '前往配置中心', to: '/settings' },
              ]}
            />
          )}
        </div>
      </div>

      {/* Reject Modal */}
      {rejectModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setRejectModal(null)}
        >
          <div
            className="card"
            style={{ width: '400px', maxWidth: '90%' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="card-header">
              <h3>驳回章节</h3>
            </div>
            <div className="card-body">
              <p style={{ marginBottom: '12px' }}>
                驳回 <strong>{rejectModal.project_name}</strong> 第{' '}
                <strong>{rejectModal.chapter_number}</strong> 章
              </p>
              <div className="form-group">
                <label className="form-label">驳回原因</label>
                <textarea
                  className="form-input"
                  rows={3}
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="请输入驳回原因，将发送给作者进行修改"
                />
              </div>
              <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '16px' }}>
                <button className="btn btn-secondary" onClick={() => setRejectModal(null)}>
                  取消
                </button>
                <button
                  className="btn btn-danger"
                  onClick={handleReject}
                  disabled={!rejectReason.trim() || actionLoading !== null}
                >
                  {actionLoading ? '处理中...' : '确认驳回'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
