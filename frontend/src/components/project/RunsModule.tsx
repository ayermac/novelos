import { useState, useEffect, useCallback } from 'react'
import { get } from '../../lib/api'
import { History, ExternalLink } from 'lucide-react'
import { tWorkflowStatus } from '../../lib/i18n'

interface Run {
  run_id: string
  id: string
  chapter_number: number
  status: string
  started_at: string
  completed_at: string | null
  current_node: string | null
  error_message: string | null
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  duration_ms: number
}

interface Props {
  projectId: string
}

export default function RunsModule({ projectId }: Props) {
  const [runs, setRuns] = useState<Run[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    const res = await get<Run[]>(`/projects/${projectId}/runs`)
    if (res.ok && Array.isArray(res.data)) {
      setRuns(res.data)
    } else {
      setError(res.error?.message || '获取运行记录失败')
    }
    setLoading(false)
  }, [projectId])

  useEffect(() => { load() }, [load])

  if (loading) return <div className="module-loading">加载中...</div>

  return (
    <div className="project-module">
      <div className="module-header">
        <h3><History size={18} /> 运行记录</h3>
      </div>

      {error && <div className="alert alert-error" style={{ marginBottom: 12 }}>{error}</div>}

      {runs.length === 0 ? (
        <div className="data-empty">
          <div className="data-empty-icon"><History size={32} /></div>
          <div className="data-empty-title">暂无运行记录</div>
          <div className="data-empty-desc">生成章节后，工作流运行记录会显示在此处</div>
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid var(--border-color)', textAlign: 'left' }}>
                <th style={{ padding: '8px 10px' }}>章节</th>
                <th style={{ padding: '8px 10px' }}>状态</th>
                <th style={{ padding: '8px 10px' }}>当前节点</th>
                <th style={{ padding: '8px 10px' }}>Token</th>
                <th style={{ padding: '8px 10px' }}>耗时</th>
                <th style={{ padding: '8px 10px' }}>开始时间</th>
                <th style={{ padding: '8px 10px' }}>错误</th>
                <th style={{ padding: '8px 10px' }}>详情</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.run_id || run.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '8px 10px' }}>第 {run.chapter_number} 章</td>
                  <td style={{ padding: '8px 10px' }}>
                    <span className={`status-badge status-${run.status}`}>
                      {tWorkflowStatus(run.status)}
                    </span>
                  </td>
                  <td style={{ padding: '8px 10px', color: 'var(--text-secondary)' }}>
                    {run.current_node || '-'}
                  </td>
                  <td style={{ padding: '8px 10px', color: 'var(--text-secondary)' }}>
                    {run.total_tokens ? run.total_tokens.toLocaleString() : '-'}
                  </td>
                  <td style={{ padding: '8px 10px', color: 'var(--text-secondary)' }}>
                    {run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)}s` : '-'}
                  </td>
                  <td style={{ padding: '8px 10px', color: 'var(--text-muted)', fontSize: 12 }}>
                    {run.started_at || '-'}
                  </td>
                  <td style={{ padding: '8px 10px', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {run.error_message ? (
                      <span style={{ color: '#dc2626', fontSize: 12 }} title={run.error_message}>
                        {run.error_message}
                      </span>
                    ) : '-'}
                  </td>
                  <td style={{ padding: '8px 10px' }}>
                    <a
                      href={`/run?run_id=${run.run_id || run.id}`}
                      style={{ color: 'var(--primary)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}
                    >
                      详情 <ExternalLink size={12} />
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
