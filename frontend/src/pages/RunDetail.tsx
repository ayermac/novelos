import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { get, post } from '../lib/api'
import { tWorkflowStatus, tChapterStatus, tLlmMode } from '../lib/i18n'
import WorkflowTimeline from '../components/WorkflowTimeline'
import ErrorState from '../components/ErrorState'
import PageHeader from '../components/PageHeader'
import { useAppDialog } from '../components/AppDialogContext'
import { ArrowLeft, DatabaseZap } from 'lucide-react'

interface Step {
  key: string
  label: string
  description: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'blocked'
  error_message?: string
  artifacts?: {
    summary: string
    output_preview?: string
    [key: string]: unknown
  } | null
}

interface RunDetail {
  run_id: string
  project_id: string
  project_name: string
  chapter_number: number
  workflow_status: string
  chapter_status: string
  current_node?: string | null
  llm_mode: string
  started_at: string
  completed_at: string
  error_message?: string
  steps: Step[]
  // v5.2: Token usage statistics
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
  duration_ms?: number
  // v6.6.7: Memory status
  memory_status?: {
    memory_status: string
    memory_trusted: boolean
    latest_memory_batch_id: string | null
    batch_count: number
    trusted_batch_count: number
    fallback_batch_count: number
  }
}

interface RunRecovery {
  run_id: string
  project_id: string
  chapter_number: number
  workflow_status: string
  chapter_status: string
  error_message?: string
  retry_count: number
  max_retries: number
  timeout_minutes: number
  elapsed_minutes?: number | null
  stuck: boolean
  stuck_reason?: string | null
  running_tasks: {
    id: number
    task_type: string
    agent_id: string
    started_at: string
    elapsed_minutes?: number | null
    stuck: boolean
  }[]
  checkpoint_exists: boolean
  can_reset: boolean
  actions: {
    reset_to_planned: {
      enabled: boolean
      label: string
      reason: string
    }
    mark_stuck_blocked: {
      enabled: boolean
      label: string
      reason: string
    }
  }
}

interface RunRecoveryResetResult {
  recovered: boolean
  previous_status: string
  new_status: string
  retry_count_before: number
  retry_count_after: number
  retries_cleared: number
  checkpoint_before: boolean
  checkpoint_cleared: boolean
  recovery: RunRecovery
}

interface RunRecoveryMarkStuckResult {
  marked: boolean
  previous_chapter_status: string
  new_chapter_status: string
  workflow_status: string
  message: string
  closed_running_tasks: number
  recovery: RunRecovery
}

interface MemoryBackfillResult {
  skipped: boolean
  run_id?: string
  memory_batch_id?: string
  memory_items_count?: number
  extraction_success?: boolean
  fallback_created?: boolean
  memory_curator_degraded?: boolean
  memory_curator_fallback?: string | null
  message?: string
}

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>()
  const navigate = useNavigate()
  const dialog = useAppDialog()
  const [data, setData] = useState<RunDetail | null>(null)
  const [recovery, setRecovery] = useState<RunRecovery | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [recoveryError, setRecoveryError] = useState<string | null>(null)
  const [recoveryMessage, setRecoveryMessage] = useState<string | null>(null)
  const [recovering, setRecovering] = useState(false)
  const [markingStuck, setMarkingStuck] = useState(false)
  const [memoryBackfilling, setMemoryBackfilling] = useState(false)

  const load = async () => {
    if (!runId) return
    setLoading(true)
    setError(null)
    setRecoveryError(null)
    try {
      const [result, recoveryResult] = await Promise.all([
        get<RunDetail>(`/runs/${runId}`),
        get<RunRecovery>(`/runs/${runId}/recovery`),
      ])
      if (result.ok && result.data) setData(result.data)
      else setError(result.error?.message || '获取运行详情失败')

      if (recoveryResult.ok && recoveryResult.data) {
        setRecovery(recoveryResult.data)
      } else {
        setRecovery(null)
        setRecoveryError(recoveryResult.error?.message || '获取恢复状态失败')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '网络错误')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [runId]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleResetRecovery = async () => {
    if (!runId || !recovery?.can_reset) return
    const ok = await dialog.confirm({
      title: '清除阻塞并重置',
      message: '确认清除本章阻塞/返修状态并回到 planned？正文、运行记录和 artifacts 会保留。',
      tone: 'warning',
      confirmLabel: '清除并重置',
    })
    if (!ok) return

    setRecovering(true)
    setRecoveryError(null)
    setRecoveryMessage(null)
    const result = await post<RunRecoveryResetResult>(`/runs/${runId}/recovery/reset`, { confirm: true })
    setRecovering(false)

    if (result.ok && result.data) {
      setRecovery(result.data.recovery)
      setRecoveryMessage(
        `已恢复：${result.data.previous_status} → ${result.data.new_status}，清除 ${result.data.retries_cleared} 次返修计数`
      )
      await load()
    } else {
      setRecoveryError(result.error?.message || '恢复失败')
    }
  }

  const handleMarkStuck = async () => {
    if (!runId || !recovery?.stuck) return
    const ok = await dialog.confirm({
      title: '标记卡住运行',
      message: '确认将该 running 运行标记为阻塞？之后可以使用恢复操作回到 planned。',
      tone: 'warning',
      confirmLabel: '标记为阻塞',
    })
    if (!ok) return

    setMarkingStuck(true)
    setRecoveryError(null)
    setRecoveryMessage(null)
    const result = await post<RunRecoveryMarkStuckResult>(`/runs/${runId}/recovery/mark-stuck`, { confirm: true })
    setMarkingStuck(false)

    if (result.ok && result.data) {
      setRecovery(result.data.recovery)
      setRecoveryMessage(`已标记为阻塞：${result.data.previous_chapter_status} → ${result.data.new_chapter_status}`)
      await load()
    } else {
      setRecoveryError(result.error?.message || '标记卡住运行失败')
    }
  }

  const handleMemoryBackfill = async (force = false) => {
    if (!runId || memoryBackfilling) return
    const ok = await dialog.confirm({
      title: force ? '强制重新提取记忆' : '补跑记忆提取',
      message: force
        ? '确认强制重新提取？这会忽略旧的低可信候选，重新调用 Memory Curator。'
        : '确认为本章补跑 Memory Curator？如果已有可信记忆提取，系统会自动跳过。',
      tone: 'warning',
      confirmLabel: force ? '强制提取' : '补跑记忆',
    })
    if (!ok) return

    setMemoryBackfilling(true)
    setRecoveryError(null)
    setRecoveryMessage(null)
    const result = await post<MemoryBackfillResult>(`/runs/${runId}/memory/backfill`, { confirm: true, force })
    setMemoryBackfilling(false)

    if (result.ok && result.data) {
      if (
        result.data.extraction_success === false ||
        result.data.fallback_created ||
        result.data.memory_curator_degraded ||
        result.data.memory_curator_fallback
      ) {
        // v6.6.7: Never show success toast for fallback/failure
        setRecoveryError(result.data.message || '补跑未生成可信记忆，请检查 MemoryCurator 配置后重试。')
      } else {
        setRecoveryMessage(result.data.message || (result.data.skipped ? '已有可信记忆批次，未重复补跑。' : '记忆提取补跑完成。'))
      }
      await load()
    } else {
      const details = result.error?.details
      const suffix = details?.memory_batch_id
        ? `\n候选批次：${String(details.memory_batch_id)}`
        : ''
      setRecoveryError((result.error?.message || '补跑记忆提取失败') + suffix)
    }
  }

  if (loading) return <div><PageHeader title="运行详情" /><div className="card"><div className="card-body module-loading">加载运行详情...</div></div></div>
  if (error && !data) return <div><PageHeader title="运行详情" /><ErrorState title="加载失败" message={error} onRetry={load} /></div>
  if (!data) return <div><PageHeader title="运行详情" /><ErrorState title="加载失败" message="无法获取运行详情" onRetry={load} /></div>

  const isStub = data.llm_mode === 'stub'
  const workspaceHref = `/projects/${data.project_id}?chapter=${data.chapter_number}`
  const workflowHref = `/projects/${data.project_id}?module=chapters&chapter=${data.chapter_number}&view=workflow`
  const hasRunError = Boolean(data.error_message)

  return (
    <div>
      <PageHeader title="运行详情" />
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
        <button className="btn btn-secondary" onClick={() => navigate(-1)}>
          <ArrowLeft size={14} /> 返回上一级
        </button>
        <Link to={workflowHref} className="btn btn-secondary">返回本章工作流</Link>
      </div>
      {isStub && (
        <div className="alert alert-warn" style={{ marginBottom: '16px' }}>
          <strong>演示模式</strong>
          <div style={{ marginTop: '4px', fontSize: '14px' }}>
            当前为演示模式，内容由本地 Stub 模板生成，不代表真实创作质量。
          </div>
        </div>
      )}
      {hasRunError && (
        <div className="alert alert-error" style={{ marginBottom: '16px' }}>
          <strong>运行失败原因</strong>
          <div style={{ marginTop: '6px', fontSize: '14px', whiteSpace: 'pre-wrap' }}>
            {data.error_message}
          </div>
          <div style={{ marginTop: '12px' }}>
            <Link to={workflowHref} className="btn btn-secondary">返回本章工作流</Link>
          </div>
        </div>
      )}
      <div className="card" style={{ marginBottom: '16px' }}>
        <div className="card-header"><h3>基本信息</h3></div>
        <div className="card-body">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
            <div><div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>项目</div>
              <div><Link to={workspaceHref}>{data.project_name || data.project_id}</Link></div></div>
            <div><div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>章节</div>
              <div>第 {data.chapter_number} 章</div></div>
            <div><div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>运行状态</div>
              <div><span className={`status-badge status-${data.workflow_status}`}>{tWorkflowStatus(data.workflow_status)}</span></div></div>
            <div><div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>章节状态</div>
              <div><span className={`status-badge status-${data.chapter_status}`}>{tChapterStatus(data.chapter_status)}</span></div></div>
            <div><div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>生成模式</div>
              <div><span className={`status-badge status-${data.llm_mode}`}>{tLlmMode(data.llm_mode)}</span></div></div>
            <div><div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>开始时间</div>
              <div>{data.started_at || '-'}</div></div>
            <div><div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>完成时间</div>
              <div>{data.completed_at || '-'}</div></div>
          </div>
        </div>
      </div>
      <div className="card" style={{ marginBottom: '16px' }}>
        <div className="card-header"><h3>运行恢复</h3></div>
        <div className="card-body">
          {recovery ? (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '16px', marginBottom: '14px' }}>
                <div>
                  <div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>返修计数</div>
                  <div style={{ fontWeight: 600 }}>{recovery.retry_count} / {recovery.max_retries}</div>
                </div>
                <div>
                  <div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>Checkpoint</div>
                  <div style={{ fontWeight: 600 }}>{recovery.checkpoint_exists ? '存在' : '无'}</div>
                </div>
                <div>
                  <div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>恢复状态</div>
                  <div style={{ fontWeight: 600, color: recovery.can_reset ? 'var(--warning)' : 'var(--success)' }}>
                    {recovery.can_reset ? '可恢复' : '无需恢复'}
                  </div>
                </div>
                <div>
                  <div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>运行耗时</div>
                  <div style={{ fontWeight: 600 }}>
                    {typeof recovery.elapsed_minutes === 'number' ? `${recovery.elapsed_minutes.toFixed(1)} 分钟` : '-'}
                  </div>
                </div>
              </div>
              {recovery.stuck && (
                <div className="alert alert-warning" style={{ marginBottom: '12px' }}>
                  <strong>疑似卡住</strong>
                  <div style={{ marginTop: '4px', fontSize: '14px' }}>
                    {recovery.stuck_reason || `超过 ${recovery.timeout_minutes} 分钟仍未完成。`}
                  </div>
                </div>
              )}
              {recovery.running_tasks.length > 0 && (
                <div style={{ marginBottom: '12px', fontSize: '13px', color: 'var(--text-secondary)' }}>
                  {recovery.running_tasks.map((task) => (
                    <div key={task.id}>
                      {task.agent_id}/{task.task_type} · {typeof task.elapsed_minutes === 'number' ? `${task.elapsed_minutes.toFixed(1)} 分钟` : '-'}
                      {task.stuck ? ' · 已超时' : ''}
                    </div>
                  ))}
                </div>
              )}
              <div style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '12px', whiteSpace: 'pre-wrap' }}>
                {recovery.actions.reset_to_planned.reason}
              </div>
              {recoveryMessage && (
                <div className="alert alert-success" style={{ marginBottom: '12px' }}>
                  {recoveryMessage}
                </div>
              )}
              {recoveryError && (
                <div className="alert alert-error" style={{ marginBottom: '12px' }}>
                  {recoveryError}
                </div>
              )}
              {/* v6.6.7: Memory status display */}
              {data.memory_status && data.chapter_status !== 'planned' && data.chapter_status !== 'drafted' && (
                <div className={`alert alert-${data.memory_status.memory_trusted ? 'success' : 'warn'}`} style={{ marginBottom: '12px' }}>
                  <strong>记忆状态：</strong>
                  {data.memory_status.memory_trusted
                    ? `可信记忆已提取（${data.memory_status.trusted_batch_count} 批次）`
                    : data.memory_status.memory_status === 'fallback'
                      ? `低可信候选（${data.memory_status.fallback_batch_count} 批次），需人工确认或重新提取`
                      : data.memory_status.memory_status === 'missing'
                        ? '尚未提取记忆'
                        : '记忆提取失败'}
                </div>
              )}
              <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                {/* v6.6.7: Memory backfill button with state-aware labels */}
                {(() => {
                  const ms = data.memory_status
                  const hasTrusted = ms?.memory_trusted
                  const hasFallback = ms?.memory_status === 'fallback'
                  const isTerminal = ['reviewed', 'awaiting_publish', 'published'].includes(data.chapter_status)
                  if (!isTerminal) return null
                  return (
                    <>
                      <button
                        className={`btn ${hasTrusted ? 'btn-secondary' : 'btn-primary'}`}
                        onClick={() => handleMemoryBackfill(hasFallback)}
                        disabled={memoryBackfilling || hasTrusted}
                        title={hasTrusted ? '已存在可信记忆批次' : hasFallback ? '重新提取可信记忆' : '补跑记忆提取'}
                      >
                        <DatabaseZap size={14} />
                        {memoryBackfilling ? '补跑中...' : hasTrusted ? '已存在可信记忆' : hasFallback ? '重新提取可信记忆' : '补跑记忆提取'}
                      </button>
                      {hasTrusted && (
                        <button
                          className="btn btn-secondary"
                          onClick={() => handleMemoryBackfill(true)}
                          disabled={memoryBackfilling}
                          title="强制重新提取（会忽略旧候选）"
                        >
                          <DatabaseZap size={14} /> 强制重跑
                        </button>
                      )}
                    </>
                  )
                })()}
                <button
                  className="btn btn-secondary"
                  onClick={handleMarkStuck}
                  disabled={!recovery.actions.mark_stuck_blocked.enabled || markingStuck}
                >
                  {markingStuck ? '标记中...' : recovery.actions.mark_stuck_blocked.label}
                </button>
                <button
                  className="btn btn-primary"
                  onClick={handleResetRecovery}
                  disabled={!recovery.actions.reset_to_planned.enabled || recovering}
                >
                  {recovering ? '恢复中...' : recovery.actions.reset_to_planned.label}
                </button>
                <Link to={workflowHref} className="btn btn-secondary">打开章节工作流</Link>
              </div>
            </>
          ) : (
            <div style={{ color: 'var(--text-secondary)' }}>
              {recoveryError || '暂无恢复信息'}
            </div>
          )}
        </div>
      </div>
      {/* v5.2: Token usage statistics - only show for real LLM mode */}
      {!isStub && Boolean(data.total_tokens || data.duration_ms) && (
        <div className="card" style={{ marginBottom: '16px' }}>
          <div className="card-header"><h3>Token 统计</h3></div>
          <div className="card-body">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '16px' }}>
              <div><div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>输入 Tokens</div>
                <div style={{ fontSize: '18px', fontWeight: 600 }}>{(data.prompt_tokens || 0).toLocaleString()}</div></div>
              <div><div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>输出 Tokens</div>
                <div style={{ fontSize: '18px', fontWeight: 600 }}>{(data.completion_tokens || 0).toLocaleString()}</div></div>
              <div><div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>总 Tokens</div>
                <div style={{ fontSize: '18px', fontWeight: 600 }}>{(data.total_tokens || 0).toLocaleString()}</div></div>
              <div><div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>耗时</div>
                <div style={{ fontSize: '18px', fontWeight: 600 }}>{data.duration_ms ? `${(data.duration_ms / 1000).toFixed(1)}s` : '-'}</div></div>
            </div>
          </div>
        </div>
      )}
      <div className="card" style={{ marginBottom: '16px' }}>
        <div className="card-header"><h3>工作流步骤</h3></div>
        <div className="card-body">
          <WorkflowTimeline steps={data.steps} />
        </div>
      </div>
      <div className="card">
        <div className="card-body">
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            {data.chapter_status === 'published' && (
              <>
                <Link to={`/projects/${data.project_id}?chapter=${data.chapter_number}&view=content`} className="btn btn-primary">查看正文</Link>
                <Link to={`/projects/${data.project_id}?chapter=${data.chapter_number + 1}`} className="btn btn-secondary">继续生成下一章</Link>
              </>
            )}
            <Link to={workspaceHref} className="btn btn-secondary">返回项目工作台</Link>
          </div>
        </div>
      </div>
    </div>
  )
}
