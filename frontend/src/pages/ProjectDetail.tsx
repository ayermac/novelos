import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { get } from '../lib/api'
import { tGenre } from '../lib/i18n'
import StatusBadge from '../components/StatusBadge'
import EmptyState from '../components/EmptyState'
import ErrorState from '../components/ErrorState'
import PageHeader from '../components/PageHeader'

interface Chapter {
  chapter_number: number
  status: string
  word_count: number
  quality_score?: number
}

interface Run {
  run_id: string
  chapter_number: number
  status: string
  created_at: string
  error_message?: string
}

interface Workspace {
  project: {
    project_id: string
    name: string
    genre?: string
    description?: string
  }
  chapters: Chapter[]
  recent_runs: Run[]
  stats: {
    total_chapters: number
    total_words: number
    status_counts: Record<string, number>
  }
}

function NextAction({ data }: { data: Workspace }) {
  const reviewCount = data.stats.status_counts['review'] || 0
  const blockingCount = data.stats.status_counts['blocking'] || 0
  // Only check the latest run (first in list, assumed sorted by time desc)
  // Historical failed runs should not override a successful latest run
  const latestRun = data.recent_runs.length > 0 ? data.recent_runs[0] : null
  const latestRunFailed = latestRun !== null && (latestRun.status === 'failed' || latestRun.status === 'blocked')

  let title = ''
  let hint = ''
  let action: { label: string; to: string } | undefined

  if (blockingCount > 0) {
    title = '有章节已阻塞'
    hint = `${blockingCount} 个章节处于阻塞状态，需要人工介入。`
    action = { label: '进入审核', to: '/review' }
  } else if (reviewCount > 0) {
    title = '有待审核章节'
    hint = `${reviewCount} 个章节等待审核。`
    action = { label: '进入审核', to: '/review' }
  } else if (latestRunFailed) {
    title = latestRun!.status === 'blocked' ? '最近运行被阻塞' : '最近运行失败'
    hint = latestRun!.status === 'blocked'
      ? '最近一次运行被阻塞，建议检查章节状态后重试。'
      : '最近一次运行失败，建议检查配置后重试。'
    action = { label: '重新生成', to: '/run' }
  } else if (data.chapters.length === 0) {
    title = '开始创作'
    hint = '项目暂无章节，生成第一章启动创作流程。'
    action = { label: '生成第一章', to: '/run' }
  } else {
    title = '继续创作'
    hint = `当前共 ${data.chapters.length} 章，可以继续生成下一章。`
    action = { label: '生成章节', to: '/run' }
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

export default function ProjectDetail() {
  const { id } = useParams<{ id: string }>()
  const [data, setData] = useState<Workspace | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = () => {
    if (!id) return
    setLoading(true)
    setError('')
    get<Workspace>(`/projects/${id}/workspace`).then((res) => {
      if (res.ok && res.data) {
        setData(res.data)
      } else {
        setError(res.error?.message || '获取项目工作台失败')
      }
      setLoading(false)
    })
  }

  useEffect(() => {
    load()
  }, [id])

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
        title="项目不存在"
        message="找不到指定的项目"
      />
    )
  }

  const statusEntries = Object.entries(data.stats.status_counts)
    .filter(([status]) => status !== 'unknown')
    .sort((a, b) => b[1] - a[1])

  return (
    <div>
      <PageHeader
        title={data.project.name}
        backTo="/projects"
        backLabel="返回列表"
        actions={
          <Link to="/run" className="btn btn-primary">
            生成章节
          </Link>
        }
      />

      {/* Project Overview */}
      <div className="card" style={{ marginBottom: 'var(--spacing-lg)' }}>
        <div className="card-body">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '16px' }}>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>类型</div>
              <div style={{ fontWeight: 600 }}>{tGenre(data.project.genre)}</div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>总章节</div>
              <div style={{ fontWeight: 600 }}>{data.stats.total_chapters}</div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>总字数</div>
              <div style={{ fontWeight: 600 }}>{data.stats.total_words.toLocaleString()}</div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>待审核</div>
              <div style={{ fontWeight: 600, color: 'var(--warning)' }}>
                {data.stats.status_counts['review'] || 0}
              </div>
            </div>
          </div>
          {data.project.description && (
            <div style={{ marginTop: '12px', color: 'var(--text-secondary)', fontSize: '14px' }}>
              {data.project.description}
            </div>
          )}
        </div>
      </div>

      <NextAction data={data} />

      {/* Chapter Progress */}
      <div className="card" style={{ marginBottom: 'var(--spacing-lg)' }}>
        <div className="card-header">
          <h3>章节进度</h3>
        </div>
        <div className="card-body">
          {statusEntries.length > 0 ? (
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '16px' }}>
              {statusEntries.map(([status, count]) => (
                <div key={status} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <StatusBadge status={status} />
                  <span style={{ fontWeight: 600 }}>{count}</span>
                </div>
              ))}
            </div>
          ) : null}

          {data.chapters.length > 0 ? (
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>章节</th>
                    <th>状态</th>
                    <th>字数</th>
                    <th>质量分</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {data.chapters.slice(0, 20).map((chapter) => {
                    const hasContent = (chapter.word_count || 0) > 0
                    return (
                      <tr key={chapter.chapter_number}>
                        <td>第 {chapter.chapter_number} 章</td>
                        <td>
                          <StatusBadge status={chapter.status} />
                        </td>
                        <td>{chapter.word_count}</td>
                        <td>{chapter.quality_score ?? '-'}</td>
                        <td>
                          {hasContent ? (
                            <Link
                              to={`/projects/${data.project.project_id}/chapters/${chapter.chapter_number}`}
                              className="btn btn-secondary"
                              style={{ fontSize: '13px', padding: '4px 12px' }}
                            >
                              查看正文
                            </Link>
                          ) : (
                            <Link
                              to={`/run?project_id=${data.project.project_id}&chapter=${chapter.chapter_number}`}
                              className="btn btn-primary"
                              style={{ fontSize: '13px', padding: '4px 12px' }}
                            >
                              生成本章
                            </Link>
                          )}
                        </td>
                      </tr>
                    )
                  })
                  }
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="暂无章节"
              hint="开始生成第一章"
              action={{ label: '生成章节', to: '/run' }}
            />
          )}
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
                    <th>章节</th>
                    <th>状态</th>
                    <th>说明</th>
                    <th>时间</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_runs.slice(0, 10).map((run) => {
                    const blockedFallback =
                      run.status === 'blocked' && !run.error_message
                        ? '工作流被阻塞，请检查章节状态或重新运行。'
                        : run.error_message || ''
                    return (
                      <tr key={run.run_id}>
                        <td>第 {run.chapter_number} 章</td>
                        <td>
                          <StatusBadge status={run.status} />
                        </td>
                        <td className="text-secondary">{blockedFallback}</td>
                        <td className="text-secondary">{run.created_at}</td>
                        <td>
                          <Link
                            to={`/runs/${run.run_id}`}
                            style={{ fontSize: '13px' }}
                          >
                            查看工作流
                          </Link>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="暂无运行记录" hint="生成章节后会显示运行记录" />
          )}
        </div>
      </div>
    </div>
  )
}
