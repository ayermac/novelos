import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { get } from '../lib/api'
import { tWorkflowStatus, tChapterStatus, tLlmMode } from '../lib/i18n'
import ErrorState from '../components/ErrorState'
import PageHeader from '../components/PageHeader'

interface Step {
  key: string
  label: string
  description: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'blocked'
  error_message?: string
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
}

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>()
  const [data, setData] = useState<RunDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    load()
  }, [runId])

  const load = async () => {
    if (!runId) return
    setLoading(true)
    setError(null)
    try {
      const result = await get<RunDetail>(`/runs/${runId}`)
      if (result.ok && result.data) {
        setData(result.data)
      } else {
        setError(result.error?.message || '获取运行详情失败')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '网络错误')
    } finally {
      setLoading(false)
    }
  }

  const stepStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return '✓'
      case 'running':
        return '●'
      case 'failed':
        return '✗'
      case 'blocked':
        return '!'
      default:
        return '○'
    }
  }

  const stepStatusClass = (status: string) => {
    switch (status) {
      case 'completed':
        return 'step-completed'
      case 'running':
        return 'step-running'
      case 'failed':
        return 'step-failed'
      case 'blocked':
        return 'step-blocked'
      default:
        return 'step-pending'
    }
  }

  if (loading) {
    return (
      <div>
        <PageHeader title="运行详情" />
        <div className="card">
          <div className="card-body" style={{ textAlign: 'center', padding: '40px' }}>
            加载中...
          </div>
        </div>
      </div>
    )
  }

  if (error && !data) {
    return (
      <div>
        <PageHeader title="运行详情" />
        <ErrorState title="加载失败" message={error} onRetry={load} />
      </div>
    )
  }

  if (!data) {
    return (
      <div>
        <PageHeader title="运行详情" />
        <ErrorState title="加载失败" message="无法获取运行详情" onRetry={load} />
      </div>
    )
  }

  const isStub = data.llm_mode === 'stub'

  return (
    <div>
      <PageHeader title="运行详情" />

      {/* Demo mode notice */}
      {isStub && (
        <div className="alert alert-warn" style={{ marginBottom: '16px' }}>
          <strong>演示模式</strong>
          <div style={{ marginTop: '4px', fontSize: '14px' }}>
            当前为演示模式，内容由本地 Stub 模板生成，不代表真实创作质量。
          </div>
        </div>
      )}

      {/* Run info card */}
      <div className="card" style={{ marginBottom: '16px' }}>
        <div className="card-header">
          <h3>基本信息</h3>
        </div>
        <div className="card-body">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
            <div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>项目</div>
              <div>
                <Link to={`/projects/${data.project_id}`}>{data.project_name || data.project_id}</Link>
              </div>
            </div>
            <div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>章节</div>
              <div>第 {data.chapter_number} 章</div>
            </div>
            <div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>运行状态</div>
              <div>
                <span className={`status-badge status-${data.workflow_status}`}>
                  {tWorkflowStatus(data.workflow_status)}
                </span>
              </div>
            </div>
            <div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>章节状态</div>
              <div>
                <span className={`status-badge status-${data.chapter_status}`}>
                  {tChapterStatus(data.chapter_status)}
                </span>
              </div>
            </div>
            <div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>生成模式</div>
              <div>
                <span className={`status-badge status-${data.llm_mode}`}>
                  {tLlmMode(data.llm_mode)}
                </span>
              </div>
            </div>
            <div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>开始时间</div>
              <div>{data.started_at || '-'}</div>
            </div>
            <div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '4px' }}>完成时间</div>
              <div>{data.completed_at || '-'}</div>
            </div>
          </div>

          {data.error_message && (
            <div style={{ marginTop: '16px', padding: '12px', background: '#fef2f2', borderRadius: '6px' }}>
              <div style={{ color: '#dc2626', fontWeight: 500, marginBottom: '4px' }}>错误信息</div>
              <div style={{ fontSize: '14px' }}>{data.error_message}</div>
            </div>
          )}
        </div>
      </div>

      {/* Steps timeline */}
      <div className="card" style={{ marginBottom: '16px' }}>
        <div className="card-header">
          <h3>工作流步骤</h3>
        </div>
        <div className="card-body">
          <div className="steps-timeline">
            {data.steps.map((step) => (
              <div key={step.key} className={`step-item ${stepStatusClass(step.status)}`}>
                <div className="step-icon">{stepStatusIcon(step.status)}</div>
                <div className="step-content">
                  <div className="step-label">{step.label}</div>
                  <div className="step-description">{step.description}</div>
                  {step.error_message && (
                    <div className="step-error">{step.error_message}</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="card">
        <div className="card-body">
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            {data.chapter_status === 'published' && (
              <>
                <Link
                  to={`/projects/${data.project_id}/chapters/${data.chapter_number}`}
                  className="btn btn-primary"
                >
                  查看正文
                </Link>
                <Link
                  to={`/run?project_id=${data.project_id}&chapter=${data.chapter_number + 1}`}
                  className="btn btn-secondary"
                >
                  继续生成下一章
                </Link>
              </>
            )}
            <Link to={`/projects/${data.project_id}`} className="btn btn-secondary">
              返回项目
            </Link>
          </div>
        </div>
      </div>

      <style>{`
        .steps-timeline {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .step-item {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          padding: 12px;
          border-radius: 6px;
          background: var(--bg-secondary);
        }

        .step-icon {
          width: 28px;
          height: 28px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 14px;
          font-weight: 600;
          flex-shrink: 0;
        }

        .step-completed .step-icon {
          background: #dcfce7;
          color: #16a34a;
        }

        .step-running .step-icon {
          background: #dbeafe;
          color: #2563eb;
          animation: pulse 1.5s infinite;
        }

        .step-failed .step-icon {
          background: #fef2f2;
          color: #dc2626;
        }

        .step-blocked .step-icon {
          background: #fef3c7;
          color: #d97706;
        }

        .step-pending .step-icon {
          background: #f3f4f6;
          color: #9ca3af;
        }

        .step-label {
          font-weight: 500;
          margin-bottom: 2px;
        }

        .step-description {
          font-size: 13px;
          color: var(--text-secondary);
        }

        .step-error {
          margin-top: 8px;
          padding: 8px;
          background: #fef2f2;
          border-radius: 4px;
          font-size: 13px;
          color: #dc2626;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
    </div>
  )
}
