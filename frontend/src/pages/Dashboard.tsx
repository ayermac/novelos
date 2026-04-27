import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { get } from '../lib/api'
import { tLlmMode } from '../lib/i18n'
import StatusBadge from '../components/StatusBadge'
import EmptyState from '../components/EmptyState'
import ErrorState from '../components/ErrorState'

interface RunItem {
  run_id: string
  project_id: string
  project_name: string
  chapter: number
  status: string
  created_at: string
}

interface DashboardData {
  project_count: number
  recent_runs: RunItem[]
  queue_count: number
  review_count: number
  llm_mode: string
}

function formatTime(ts: string): string {
  if (!ts) return '-'
  try {
    const d = new Date(ts)
    return d.toLocaleString('zh-CN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ts
  }
}

function NextActionCard({ data }: { data: DashboardData }) {
  let title = ''
  let hint = ''
  let action: { label: string; to: string } | undefined

  if (data.project_count === 0) {
    title = '开始创作'
    hint = '你还没有小说项目，创建第一个项目开始创作吧。'
    action = { label: '创建第一个项目', to: '/onboarding' }
  } else if (data.recent_runs.length === 0) {
    title = '生成第一章'
    hint = '项目已创建，生成第一章来启动创作流程。'
    action = { label: '生成第一章', to: '/run' }
  } else if (data.review_count > 0) {
    title = '有待审核章节'
    hint = `当前有 ${data.review_count} 个章节等待审核，请及时处理。`
    action = { label: '进入审核', to: '/review' }
  } else {
    const failed = data.recent_runs.filter((r) => r.status === 'failed')
    if (failed.length > 0) {
      title = '有失败运行'
      hint = '最近有运行失败，请查看详情并排查问题。'
      action = { label: '查看失败运行', to: '/run' }
    } else {
      title = '继续创作'
      hint = '一切正常，可以继续生成下一章。'
      action = { label: '生成章节', to: '/run' }
    }
  }

  return (
    <div className="card" style={{ marginBottom: 'var(--spacing-lg)' }}>
      <div className="card-header">
        <h3>下一步建议</h3>
      </div>
      <div className="card-body">
        <div style={{ fontSize: '16px', fontWeight: 600, marginBottom: '8px' }}>{title}</div>
        <div style={{ color: 'var(--text-secondary)', marginBottom: '16px' }}>{hint}</div>
        {action && (
          <Link to={action.to} className="btn btn-primary">
            {action.label}
          </Link>
        )}
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = () => {
    setLoading(true)
    setError('')
    get<DashboardData>('/dashboard').then((res) => {
      if (res.ok && res.data) {
        setData(res.data)
      } else {
        setError(res.error?.message || '获取仪表盘数据失败')
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

  if (error || !data) {
    return (
      <ErrorState
        title="加载失败"
        message={error || '无法获取仪表盘数据'}
        onRetry={load}
      />
    )
  }

  return (
    <div>
      <h2 style={{ marginBottom: '24px' }}>总览</h2>

      <NextActionCard data={data} />

      {/* Quick Actions */}
      <div className="quick-actions" style={{ marginBottom: 'var(--spacing-lg)' }}>
        <Link to="/onboarding" className="quick-action-card">
          <div className="qa-title">创建项目</div>
          <div className="qa-desc">新建小说项目</div>
        </Link>
        <Link to="/run" className="quick-action-card">
          <div className="qa-title">生成章节</div>
          <div className="qa-desc">运行章节生产</div>
        </Link>
        <Link to="/review" className="quick-action-card">
          <div className="qa-title">审核工作台</div>
          <div className="qa-desc">审核章节质量</div>
        </Link>
        <Link to="/settings" className="quick-action-card">
          <div className="qa-title">配置中心</div>
          <div className="qa-desc">LLM 与运行配置</div>
        </Link>
      </div>

      {/* Stats */}
      <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <div className="stat-card">
          <h3>项目数</h3>
          <div className="stat-value">{data.project_count}</div>
        </div>
        <div className="stat-card">
          <h3>待审核</h3>
          <div className="stat-value" style={{ color: 'var(--warning)' }}>
            {data.review_count}
          </div>
        </div>
        <div className="stat-card">
          <h3>队列项</h3>
          <div className="stat-value">{data.queue_count}</div>
        </div>
        <div className="stat-card">
          <h3>运行模式</h3>
          <div className="stat-value" style={{ fontSize: '16px' }}>
            {tLlmMode(data.llm_mode)}
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
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>项目</th>
                    <th>章节</th>
                    <th>状态</th>
                    <th>时间</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_runs.map((run) => (
                    <tr key={run.run_id}>
                      <td>
                        <Link to={`/projects/${run.project_id}`}>
                          {run.project_name}
                        </Link>
                      </td>
                      <td>第 {run.chapter} 章</td>
                      <td>
                        <StatusBadge status={run.status} />
                      </td>
                      <td className="text-secondary">{formatTime(run.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="暂无运行记录"
              hint="创建项目并生成第一章"
              action={{ label: '创建项目', to: '/onboarding' }}
            />
          )}
        </div>
      </div>
    </div>
  )
}
