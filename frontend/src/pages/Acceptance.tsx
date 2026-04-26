import { useEffect, useState } from 'react'
import { get } from '../lib/api'

interface Capability {
  capability_id: string
  label: string
  web_route: string | null
  cli_command: string | null
  status: string
  notes: string
}

interface AcceptanceData {
  capabilities: Capability[]
  summary: {
    total: number
    passed: number
    failed: number
    pass_rate: string
  }
}

export default function Acceptance() {
  const [data, setData] = useState<AcceptanceData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    get<AcceptanceData>('/acceptance').then((res) => {
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
      <h2 style={{ marginBottom: '24px' }}>功能验收矩阵</h2>

      {/* Summary */}
      <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <div className="stat-card">
          <h3>总功能</h3>
          <div className="stat-value">{data.summary.total}</div>
        </div>
        <div className="stat-card">
          <h3>通过</h3>
          <div className="stat-value" style={{ color: 'var(--success)' }}>
            {data.summary.passed}
          </div>
        </div>
        <div className="stat-card">
          <h3>失败</h3>
          <div className="stat-value" style={{ color: 'var(--danger)' }}>
            {data.summary.failed}
          </div>
        </div>
        <div className="stat-card">
          <h3>通过率</h3>
          <div className="stat-value">{data.summary.pass_rate}</div>
        </div>
      </div>

      {/* Capabilities */}
      <div className="card">
        <div className="card-header">
          <h3>能力清单</h3>
        </div>
        <div className="card-body">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>标签</th>
                <th>路由</th>
                <th>CLI</th>
                <th>状态</th>
                <th>备注</th>
              </tr>
            </thead>
            <tbody>
              {data.capabilities.map((cap) => (
                <tr key={cap.capability_id}>
                  <td>{cap.capability_id}</td>
                  <td>{cap.label}</td>
                  <td className="text-secondary">{cap.web_route || '-'}</td>
                  <td className="text-secondary">{cap.cli_command || '-'}</td>
                  <td>
                    <span
                      className={`status-badge status-${cap.status === 'pass' ? 'approved' : 'rejected'}`}
                    >
                      {cap.status === 'pass' ? '通过' : '失败'}
                    </span>
                  </td>
                  <td className="text-secondary">{cap.notes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
