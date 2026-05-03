import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { get } from '../lib/api'
import { tWorkflowStatus, tChapterStatus, tLlmMode } from '../lib/i18n'
import WorkflowTimeline from '../components/WorkflowTimeline'
import ErrorState from '../components/ErrorState'
import PageHeader from '../components/PageHeader'

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
}

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>()
  const [data, setData] = useState<RunDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    if (!runId) return
    setLoading(true)
    setError(null)
    try {
      const result = await get<RunDetail>(`/runs/${runId}`)
      if (result.ok && result.data) setData(result.data)
      else setError(result.error?.message || '获取运行详情失败')
    } catch (e) {
      setError(e instanceof Error ? e.message : '网络错误')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [runId]) // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <div><PageHeader title="运行详情" /><div className="card"><div className="card-body" style={{ textAlign: 'center', padding: '40px' }}>加载中...</div></div></div>
  if (error && !data) return <div><PageHeader title="运行详情" /><ErrorState title="加载失败" message={error} onRetry={load} /></div>
  if (!data) return <div><PageHeader title="运行详情" /><ErrorState title="加载失败" message="无法获取运行详情" onRetry={load} /></div>

  const isStub = data.llm_mode === 'stub'
  const workspaceHref = `/projects/${data.project_id}?chapter=${data.chapter_number}`
  const workflowHref = `/projects/${data.project_id}?module=chapters&chapter=${data.chapter_number}&view=workflow`
  const hasRunError = Boolean(data.error_message)

  return (
    <div>
      <PageHeader title="运行详情" />
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
      {/* v5.2: Token usage statistics - only show for real LLM mode */}
      {!isStub && (data.total_tokens || data.duration_ms) && (
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
