import { useEffect, useState } from 'react'
import { get } from '../lib/api'

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

const statusLabels: Record<string, string> = {
  review: '待审核',
  blocking: '已阻塞',
  approved: '已通过',
  rejected: '需返修',
}

export default function Review() {
  const [data, setData] = useState<ReviewData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    get<ReviewData>('/review/workbench').then((res) => {
      if (res.ok && res.data) {
        setData(res.data)
      }
      setLoading(false)
    })
  }, [])

  if (loading) {
    return <div>加载中...</div>
  }

  if (!data) {
    return <div>加载失败</div>
  }

  return (
    <div>
      <h2 style={{ marginBottom: '24px' }}>审核工作台</h2>

      {/* Stats */}
      <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
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
            <table className="data-table">
              <thead>
                <tr>
                  <th>章节</th>
                  <th>项目</th>
                  <th>状态</th>
                  <th>质量分</th>
                  <th>问题数</th>
                </tr>
              </thead>
              <tbody>
                {data.queue.map((item) => (
                  <tr key={`${item.project_id}-${item.chapter_number}`}>
                    <td>第 {item.chapter_number} 章</td>
                    <td>{item.project_name}</td>
                    <td>
                      <span className={`status-badge status-${item.status}`}>
                        {statusLabels[item.status] || item.status}
                      </span>
                    </td>
                    <td>{item.quality_score || '-'}</td>
                    <td>{item.issue_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty-state">
              <div className="empty-title">当前没有待审核章节</div>
              <div className="empty-hint">可以先生成第一章</div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
