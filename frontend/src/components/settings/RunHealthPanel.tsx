import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Activity, RefreshCw } from 'lucide-react'
import { get, post } from '../../lib/api'
import { tChapterStatus, tWorkflowStatus } from '../../lib/i18n'
import { useAppDialog } from '../AppDialogContext'
import { Checkbox, DataTable } from '../ui'

interface RunningTask {
  id: number
  task_type: string
  agent_id: string
  started_at: string
  elapsed_minutes?: number | null
  stuck: boolean
}

interface RunHealthItem {
  run_id: string
  project_id: string
  project_name: string
  chapter_number: number
  workflow_status: string
  chapter_status: string
  current_node?: string | null
  started_at?: string | null
  completed_at?: string | null
  error_message?: string | null
  elapsed_minutes?: number | null
  stuck: boolean
  stuck_reason?: string | null
  running_tasks: RunningTask[]
  actions: {
    mark_stuck_blocked: {
      enabled: boolean
      reason: string
    }
  }
}

interface RunHealthResponse {
  timeout_minutes: number
  project_id?: string | null
  limit: number
  summary: {
    total: number
    total_running: number
    healthy_running: number
    stuck: number
    blocked: number
    failed: number
    actionable: number
  }
  runs: RunHealthItem[]
}

interface BatchMarkResult {
  requested: number
  marked: number
  failed: number
  results: {
    ok: boolean
    run_id: string
    error_code?: string
    message?: string
  }[]
}

export default function RunHealthPanel() {
  const dialog = useAppDialog()
  const [data, setData] = useState<RunHealthResponse | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [marking, setMarking] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    const res = await get<RunHealthResponse>('/runs/health?limit=100')
    if (res.ok && res.data) {
      setData(res.data)
      setSelected((current) => current.filter((runId) => (
        res.data?.runs.some((run) => run.run_id === runId && run.actions.mark_stuck_blocked.enabled)
      )))
    } else {
      setError(res.error?.message || '获取运行健康状态失败')
    }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const actionableIds = useMemo(() => (
    data?.runs
      .filter((run) => run.actions.mark_stuck_blocked.enabled)
      .map((run) => run.run_id) || []
  ), [data])

  const toggleAll = () => {
    setSelected(selected.length === actionableIds.length ? [] : actionableIds)
  }

  const toggleOne = (runId: string) => {
    setSelected((current) => (
      current.includes(runId)
        ? current.filter((id) => id !== runId)
        : [...current, runId]
    ))
  }

  const handleBatchMark = async () => {
    if (selected.length === 0) return
    const ok = await dialog.confirm({
      title: '批量标记卡住运行',
      message: `确认将 ${selected.length} 条疑似卡住运行标记为阻塞？`,
      tone: 'warning',
      confirmLabel: '批量标记',
    })
    if (!ok) return

    setMarking(true)
    setError('')
    setMessage('')
    const res = await post<BatchMarkResult>('/runs/health/mark-stuck', {
      run_ids: selected,
      confirm: true,
    })
    setMarking(false)

    if (res.ok && res.data) {
      setMessage(`已标记 ${res.data.marked} 条，失败 ${res.data.failed} 条`)
      setSelected([])
      await load()
    } else {
      setError(res.error?.message || '批量标记失败')
    }
  }

  if (loading) {
    return <div className="module-loading">加载中...</div>
  }

  return (
    <div style={{
      background: 'var(--paper-surface)',
      borderRadius: 'var(--radius-lg)',
      boxShadow: 'var(--shadow-flat)',
      border: '1px solid rgba(30, 58, 95, 0.06)',
      overflow: 'hidden',
    }}>
      <div style={{
        padding: 'var(--space-4) var(--space-5)',
        borderBottom: '1px solid rgba(30, 58, 95, 0.04)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '12px',
        flexWrap: 'wrap',
      }}>
        <div>
          <h3 style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontFamily: 'var(--font-brand)',
            fontSize: 'var(--text-md)',
            fontWeight: 'var(--font-semibold)',
            margin: 0,
          }}>
            <Activity size={18} /> 运行健康
          </h3>
          <div style={{ marginTop: 4, fontSize: 13, color: 'var(--text-secondary)' }}>
            检测超过 {data?.timeout_minutes ?? 30} 分钟仍处于 running 的工作流
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn btn-secondary" onClick={load}>
            <RefreshCw size={14} /> 刷新
          </button>
          <button
            className="btn btn-primary"
            onClick={handleBatchMark}
            disabled={selected.length === 0 || marking}
          >
            {marking ? '处理中...' : `标记为阻塞 (${selected.length})`}
          </button>
        </div>
      </div>

      <div style={{ padding: 'var(--space-5)' }}>
        {error && <div className="alert alert-error" style={{ marginBottom: 12 }}>{error}</div>}
        {message && <div className="alert alert-success" style={{ marginBottom: 12 }}>{message}</div>}

        {data && (
          <>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
              gap: 12,
              marginBottom: 16,
            }}>
              <Metric label="疑似卡住" value={data.summary.stuck} tone={data.summary.stuck > 0 ? 'danger' : 'success'} />
              <Metric label="运行中健康" value={data.summary.healthy_running} />
              <Metric label="已阻塞" value={data.summary.blocked} tone={data.summary.blocked > 0 ? 'warning' : 'neutral'} />
              <Metric label="失败" value={data.summary.failed} tone={data.summary.failed > 0 ? 'danger' : 'neutral'} />
              <Metric label="可处理" value={data.summary.actionable} />
            </div>

            {data.runs.length === 0 ? (
              <div className="data-empty">
                <div className="data-empty-title">暂无异常运行</div>
                <div className="data-empty-desc">running / blocked / failed 运行会出现在这里</div>
              </div>
            ) : (
              <DataTable
                compact
                data={data.runs}
                getRowKey={(run) => run.run_id}
                columns={[
                  {
                    key: 'select',
                    header: (
                      <Checkbox
                        checked={actionableIds.length > 0 && selected.length === actionableIds.length}
                        onChange={toggleAll}
                        disabled={actionableIds.length === 0}
                        aria-label="选择全部可处理运行"
                      />
                    ),
                    render: (run) => {
                      const canMark = run.actions.mark_stuck_blocked.enabled
                      return (
                        <Checkbox
                          checked={selected.includes(run.run_id)}
                          onChange={() => toggleOne(run.run_id)}
                          disabled={!canMark}
                          aria-label={`选择运行 ${run.run_id}`}
                        />
                      )
                    },
                  },
                  {
                    key: 'project',
                    header: '项目 / 章节',
                    render: (run) => (
                      <>
                        <Link to={`/projects/${run.project_id}?module=chapters&chapter=${run.chapter_number}`}>
                          {run.project_name || run.project_id}
                        </Link>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                          第 {run.chapter_number} 章 · {tChapterStatus(run.chapter_status)}
                        </div>
                      </>
                    ),
                  },
                  {
                    key: 'status',
                    header: '运行状态',
                    render: (run) => (
                      <>
                        <span className={`status-badge status-${run.workflow_status}`}>
                          {tWorkflowStatus(run.workflow_status)}
                        </span>
                        {run.stuck && <div style={{ marginTop: 4, fontSize: 12, color: 'var(--danger)' }}>疑似卡住</div>}
                      </>
                    ),
                  },
                  { key: 'node', header: '节点', render: (run) => <span style={{ color: 'var(--text-secondary)' }}>{run.current_node || '-'}</span> },
                  {
                    key: 'elapsed',
                    header: '耗时',
                    render: (run) => <span style={{ color: 'var(--text-secondary)' }}>{typeof run.elapsed_minutes === 'number' ? `${run.elapsed_minutes.toFixed(1)} 分钟` : '-'}</span>,
                  },
                  {
                    key: 'tasks',
                    header: '任务',
                    render: (run) => (
                      <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
                        {run.running_tasks.length > 0 ? run.running_tasks.map((task) => `${task.agent_id}/${task.task_type}`).join(', ') : '-'}
                      </span>
                    ),
                  },
                  {
                    key: 'error',
                    header: '错误',
                    render: (run) => (
                      <span style={{ display: 'block', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {run.error_message || run.stuck_reason || '-'}
                      </span>
                    ),
                  },
                  {
                    key: 'detail',
                    header: '详情',
                    render: (run) => (
                      <Link to={`/runs/${run.run_id}`} className="btn btn-secondary">
                        详情
                      </Link>
                    ),
                  },
                ]}
              />
            )}
          </>
        )}
      </div>
    </div>
  )
}

function Metric({ label, value, tone = 'neutral' }: {
  label: string
  value: number
  tone?: 'neutral' | 'success' | 'warning' | 'danger'
}) {
  const colorMap = {
    neutral: 'var(--text-primary)',
    success: 'var(--success)',
    warning: 'var(--warning)',
    danger: 'var(--danger)',
  }
  return (
    <div style={{
      border: '1px solid rgba(30, 58, 95, 0.08)',
      borderRadius: 'var(--radius-md)',
      padding: '12px',
      background: 'var(--bg-secondary)',
    }}>
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: colorMap[tone] }}>{value}</div>
    </div>
  )
}
