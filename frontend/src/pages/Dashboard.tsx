import { useEffect, useState } from 'react'
import { get } from '../lib/api'

interface DashboardData {
  project_count: number
  recent_runs: Array<{
    run_id: string
    project_id: string
    project_name: string
    chapter: number
    status: string
    created_at: string
  }>
  queue_count: number
  review_count: number
  llm_mode: string
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    get<DashboardData>('/dashboard').then((res) => {
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
      <h2 style={{ marginBottom: '24px' }}>总览</h2>

      {/* Stats */}
      <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <div className="stat-card">
          <h3>项目数</h3>
          <div className="stat-value">{data.project_count}</div>
        </div>
        <div className="stat-card">
          <h3>队列项</h3>
          <div className="stat-value">{data.queue_count}</div>
        </div>
        <div className="stat-card">
          <h3>待审核</h3>
          <div className="stat-value" style={{ color: 'var(--warning)' }}>
            {data.review_count}
          </div>
        </div>
        <div className="stat-card">
          <h3>运行模式</h3>
          <div className="stat-value" style={{ fontSize: '16px' }}>
            {data.llm_mode === 'real' ? '真实 LLM' : '演示模式'}
          </div>
        </div>
      </div>

      {/* Recent Runs */}
      <div className="card">
        <div className="card-header">
          <h3>最近运行</h3>
        </div>
        <div className="card-body">
          {data.recent_runs.length > 0 ? (
            <table className="data-table">
              <thead>
                <tr>
                  <th>运行 ID</th>
                  <th>项目</th>
                  <th>章节</th>
                  <th>状态</th>
                  <th>时间</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_runs.map((run) => (
                  <tr key={run.run_id}>
                    <td>{run.run_id.slice(0, 12)}</td>
                    <td>{run.project_name}</td>
                    <td>第 {run.chapter} 章</td>
                    <td>
                      <span className={`status-badge status-${run.status}`}>
                        {run.status}
                      </span>
                    </td>
                    <td className="text-secondary">{run.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty-state">
              <div className="empty-title">暂无运行记录</div>
              <div className="empty-hint">创建项目并生成第一章</div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
