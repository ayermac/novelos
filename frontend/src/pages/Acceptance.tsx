import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { get } from '../lib/api'
import { tCapabilityLabel, tCapabilityNotes, tAcceptanceStatus } from '../lib/i18n'
import ErrorState from '../components/ErrorState'
import PageHeader from '../components/PageHeader'

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
    partial: number
    pass_rate: string
  }
}

export default function Acceptance() {
  const [data, setData] = useState<AcceptanceData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    setError('')
    get<AcceptanceData>('/acceptance').then((res) => {
      if (res.ok && res.data) {
        setData(res.data)
      } else {
        setError(res.error?.message || '获取验收矩阵失败')
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
        message="无法获取验收数据"
        onRetry={load}
      />
    )
  }

  return (
    <div>
      <PageHeader title="功能验收" />

      {/* Summary */}
      <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(5, 1fr)' }}>
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
          <h3>迁移中</h3>
          <div className="stat-value" style={{ color: 'var(--warning)' }}>
            {data.summary.partial || 0}
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

      {/* Capabilities — Card List */}
      <div className="card">
        <div className="card-header">
          <h3>能力清单</h3>
        </div>
        <div className="card-body">
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
              gap: '16px',
            }}
          >
            {data.capabilities.map((cap) => {
              const statusInfo = tAcceptanceStatus(cap.status)
              const isExpanded = expandedId === cap.capability_id
              return (
                <div
                  key={cap.capability_id}
                  style={{
                    border: '1px solid var(--border)',
                    borderRadius: '8px',
                    padding: '16px',
                    background: 'var(--bg-secondary)',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      marginBottom: '8px',
                    }}
                  >
                    <div style={{ fontWeight: 600, fontSize: '14px' }}>
                      {tCapabilityLabel(cap.label)}
                    </div>
                    <span className={`status-badge ${statusInfo.className}`}>
                      {statusInfo.label}
                    </span>
                  </div>
                  <div
                    style={{
                      fontSize: '13px',
                      color: 'var(--text-primary)',
                      marginBottom: '8px',
                      minHeight: '20px',
                    }}
                  >
                    {tCapabilityNotes(cap.notes)}
                  </div>
                  <button
                    onClick={() => setExpandedId(isExpanded ? null : cap.capability_id)}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: 'var(--primary)',
                      cursor: 'pointer',
                      fontSize: '12px',
                      padding: 0,
                    }}
                  >
                    {isExpanded ? '收起详情' : '查看详情'}
                  </button>
                  {isExpanded && (
                    <div
                      style={{
                        marginTop: '8px',
                        paddingTop: '8px',
                        borderTop: '1px solid var(--border)',
                        fontSize: '12px',
                        color: 'var(--text-secondary)',
                      }}
                    >
                      <div>技术 ID: {cap.capability_id}</div>
                      {cap.web_route && (
                        <div>
                          Web 路由:{' '}
                          <Link to={cap.web_route} style={{ color: 'var(--primary)' }}>
                            {cap.web_route}
                          </Link>
                        </div>
                      )}
                      {cap.cli_command && <div>CLI 命令: {cap.cli_command}</div>}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
