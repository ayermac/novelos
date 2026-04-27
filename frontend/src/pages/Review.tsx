import { useEffect, useState } from 'react'
import { get } from '../lib/api'
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
            <div style={{ overflowX: 'auto' }}>
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
                        <StatusBadge status={item.status} />
                      </td>
                      <td>{item.quality_score ?? '-'}</td>
                      <td>{item.issue_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="当前没有待审核章节"
              hint="当前流程下章节生成后会直接发布。已发布章节可在项目工作台查看正文。"
              action={{ label: '查看项目列表', to: '/projects' }}
            />
          )}
        </div>
      </div>
    </div>
  )
}
