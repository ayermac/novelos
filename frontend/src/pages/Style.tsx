import { useEffect, useState } from 'react'
import { get } from '../lib/api'

interface StyleData {
  style_bibles: Array<{
    project_id: string
    project_name: string
    status: string
    version: number
    updated_at: string
  }>
  health: {
    total_projects: number
    projects_with_bible: number
    pending_gates: number
  }
}

export default function Style() {
  const [data, setData] = useState<StyleData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    get<StyleData>('/style/console').then((res) => {
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
      <h2 style={{ marginBottom: '24px' }}>风格管理</h2>

      {/* Health */}
      <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
        <div className="stat-card">
          <h3>总项目</h3>
          <div className="stat-value">{data.health.total_projects}</div>
        </div>
        <div className="stat-card">
          <h3>已建立风格圣经</h3>
          <div className="stat-value">{data.health.projects_with_bible}</div>
        </div>
        <div className="stat-card">
          <h3>待审核风格</h3>
          <div className="stat-value">{data.health.pending_gates}</div>
        </div>
      </div>

      {/* Style Bibles */}
      <div className="card">
        <div className="card-header">
          <h3>风格圣经</h3>
        </div>
        <div className="card-body">
          {data.style_bibles.length > 0 ? (
            <table className="data-table">
              <thead>
                <tr>
                  <th>项目</th>
                  <th>状态</th>
                  <th>版本</th>
                  <th>更新时间</th>
                </tr>
              </thead>
              <tbody>
                {data.style_bibles.map((bible) => (
                  <tr key={bible.project_id}>
                    <td>{bible.project_name}</td>
                    <td>
                      <span className={`status-badge status-${bible.status}`}>
                        {bible.status}
                      </span>
                    </td>
                    <td>v{bible.version}</td>
                    <td className="text-secondary">{bible.updated_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty-state">
              <div className="empty-title">暂无风格圣经</div>
              <div className="empty-hint">生成章节后自动建立风格圣经</div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
