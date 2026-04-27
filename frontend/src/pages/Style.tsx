import { useEffect, useState } from 'react'
import { get } from '../lib/api'
import StatusBadge from '../components/StatusBadge'
import EmptyState from '../components/EmptyState'
import ErrorState from '../components/ErrorState'
import PageHeader from '../components/PageHeader'

interface StyleBible {
  project_id: string
  project_name: string
  status: string
  version: number
  updated_at: string
}

interface StyleGateConfig {
  project_id: string
  project_name: string
  enabled: boolean
  threshold: number
}

interface StyleSample {
  project_id: string
  sample_id: string
  source: string
  word_count: number
}

interface StyleData {
  style_bibles: StyleBible[]
  style_gate_configs: StyleGateConfig[]
  style_samples: StyleSample[]
  health: {
    total_projects: number
    projects_with_bible: number
    gate_configs: number
  }
}

export default function Style() {
  const [data, setData] = useState<StyleData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = () => {
    setLoading(true)
    setError('')
    get<StyleData>('/style/console').then((res) => {
      if (res.ok && res.data) {
        setData(res.data)
      } else {
        setError(res.error?.message || '获取风格管理数据失败')
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
        message="无法获取风格数据"
        onRetry={load}
      />
    )
  }

  const hasAnyData =
    data.style_bibles.length > 0 ||
    data.style_gate_configs.length > 0 ||
    data.style_samples.length > 0

  return (
    <div>
      <PageHeader title="风格管理" />

      {/* Health Summary */}
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
          <h3>风格门禁配置</h3>
          <div className="stat-value">{data.health.gate_configs}</div>
        </div>
      </div>

      {!hasAnyData ? (
        <div className="card">
          <div className="card-body">
            <EmptyState
              title="暂无风格数据"
              hint="生成章节或初始化风格后会出现数据。风格圣经用于统一项目写作风格。"
              action={{ label: '去生成章节', to: '/run' }}
            />
          </div>
        </div>
      ) : (
        <>
          {/* Style Bibles */}
          <div className="card" style={{ marginBottom: 'var(--spacing-lg)' }}>
            <div className="card-header">
              <h3>风格圣经</h3>
            </div>
            <div className="card-body">
              {data.style_bibles.length > 0 ? (
                <div style={{ overflowX: 'auto' }}>
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
                            <StatusBadge status={bible.status} />
                          </td>
                          <td>v{bible.version}</td>
                          <td className="text-secondary">{bible.updated_at}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyState
                  title="暂无风格圣经"
                  hint="生成章节后自动建立风格圣经"
                />
              )}
            </div>
          </div>

          {/* Style Gate */}
          {data.style_gate_configs.length > 0 && (
            <div className="card" style={{ marginBottom: 'var(--spacing-lg)' }}>
              <div className="card-header">
                <h3>风格门禁</h3>
              </div>
              <div className="card-body">
                <div style={{ overflowX: 'auto' }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>项目</th>
                        <th>启用</th>
                        <th>阈值</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.style_gate_configs.map((config) => (
                        <tr key={config.project_id}>
                          <td>{config.project_name}</td>
                          <td>
                            <span
                              className={`status-badge ${config.enabled ? 'status-active' : 'status-inactive'}`}
                            >
                              {config.enabled ? '已启用' : '已停用'}
                            </span>
                          </td>
                          <td>{config.threshold}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* Style Samples */}
          {data.style_samples.length > 0 && (
            <div className="card">
              <div className="card-header">
                <h3>风格样本</h3>
              </div>
              <div className="card-body">
                <div style={{ overflowX: 'auto' }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>来源</th>
                        <th>字数</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.style_samples.map((sample) => (
                        <tr key={sample.sample_id}>
                          <td>{sample.source}</td>
                          <td>{sample.word_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
