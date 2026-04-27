import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertCircle, ChevronRight, BookOpen } from 'lucide-react'
import { get } from '../lib/api'
import { tLlmMode, tWorkflowStatus, tChapterStatus } from '../lib/i18n'
import ErrorState from '../components/ErrorState'
import PageHeader from '../components/PageHeader'

interface RunItem {
  run_id: string
  project_id: string
  project_name: string
  chapter: number
  status: string
  created_at: string
}

interface Project {
  project_id: string
  name: string
  genre?: string
  chapter_count: number
  created_at: string
}

interface Chapter {
  chapter_number: number
  status: string
  run_id?: string
}

interface ProjectDetail extends Project {
  chapters: Chapter[]
}

interface DashboardData {
  project_count: number
  recent_runs: RunItem[]
  queue_count: number
  review_count: number
  llm_mode: string
}

function formatRelativeTime(ts: string): string {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return '刚刚'
    if (diffMins < 60) return `${diffMins} 分钟前`
    if (diffHours < 24) return `${diffHours} 小时前`
    if (diffDays < 7) return `${diffDays} 天前`
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  } catch {
    return ts
  }
}

function getStatusColor(status: string): string {
  switch (status) {
    case 'completed':
      return '#16a34a'
    case 'running':
      return '#2563eb'
    case 'failed':
      return '#dc2626'
    case 'blocked':
      return '#d97706'
    default:
      return '#9ca3af'
  }
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [attentionProjects, setAttentionProjects] = useState<Array<{ project: Project; chapters: Chapter[] }>>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [dashboardRes, projectsRes] = await Promise.all([
        get<DashboardData>('/dashboard'),
        get<Project[]>('/projects'),
      ])
      if (dashboardRes.ok && dashboardRes.data) {
        setData(dashboardRes.data)
      } else {
        setError(dashboardRes.error?.message || '获取仪表盘数据失败')
      }
      if (projectsRes.ok && projectsRes.data) {
        setProjects(projectsRes.data)
        // Fetch details for each project to find blocked/failed chapters
        const attentionItems: Array<{ project: Project; chapters: Chapter[] }> = []
        for (const project of projectsRes.data) {
          const detailRes = await get<ProjectDetail>(`/projects/${project.project_id}`)
          if (detailRes.ok && detailRes.data) {
            const blockedFailed = detailRes.data.chapters.filter(
              ch => ch.status === 'blocked' || ch.status === 'failed'
            )
            if (blockedFailed.length > 0) {
              attentionItems.push({ project, chapters: blockedFailed })
            }
          }
        }
        setAttentionProjects(attentionItems)
      }
    } catch {
      setError('网络错误')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  if (loading) {
    return <div><PageHeader title="创作中心" /><div className="card"><div className="card-body" style={{ textAlign: 'center', padding: '40px' }}>加载中...</div></div></div>
  }

  if (error || !data) {
    return (
      <div>
        <PageHeader title="创作中心" />
        <ErrorState
          title="加载失败"
          message={error || '无法获取仪表盘数据'}
          onRetry={load}
        />
      </div>
    )
  }

  const isStub = data.llm_mode === 'stub'
  const hasProjects = data.project_count > 0
  const hasRuns = data.recent_runs.length > 0
  const latestRun = hasRuns ? data.recent_runs[0] : null

  // Get first project for workspace navigation
  const firstProject = projects[0]

  // Determine hero content - CTA should lead to project workspace, NOT /run
  let heroTitle = ''
  let heroHint = ''
  let heroAction: { label: string; to: string } | undefined

  if (!hasProjects) {
    heroTitle = '开始你的创作之旅'
    heroHint = '创建第一个小说项目，开启 AI 辅助创作体验'
    heroAction = { label: '创建第一个项目', to: '/onboarding' }
  } else if (!hasRuns && firstProject) {
    // No runs yet - go to project workspace to start
    heroTitle = '项目已就绪'
    heroHint = `${firstProject.name || firstProject.project_id} 已创建，进入工作台开始创作`
    heroAction = { label: '进入工作台', to: `/projects/${firstProject.project_id}` }
  } else if (latestRun?.status === 'failed' || latestRun?.status === 'blocked') {
    heroTitle = latestRun.status === 'failed' ? '最近运行失败' : '最近运行被阻塞'
    heroHint = `${latestRun.project_name} 第 ${latestRun.chapter} 章${latestRun.status === 'failed' ? '生成失败' : '被阻塞'}，请检查后重试`
    heroAction = { label: '查看项目工作台', to: `/projects/${latestRun.project_id}` }
  } else if (latestRun) {
    // Latest run completed - continue in project workspace
    heroTitle = '继续创作'
    heroHint = `${latestRun.project_name} 第 ${latestRun.chapter} 章已完成，进入工作台继续创作`
    heroAction = { label: '进入工作台', to: `/projects/${latestRun.project_id}?chapter=${latestRun.chapter + 1}` }
  } else if (firstProject) {
    heroTitle = '继续创作'
    heroHint = `你有 ${data.project_count} 个项目，进入工作台继续创作`
    heroAction = { label: '进入工作台', to: `/projects/${firstProject.project_id}` }
  }

  return (
    <div>
      <PageHeader title="创作中心" />

      {/* Attention Section - Stub Mode Warning */}
      {isStub && (
        <div className="alert alert-warn" style={{ marginBottom: 'var(--spacing-lg)' }}>
          <strong>演示模式</strong>
          <div style={{ marginTop: '4px', fontSize: '14px' }}>
            当前为演示模式，内容由本地 Stub 模板生成，不代表真实创作质量。
            如需真实生成，请在配置中心设置 LLM 并以 <code style={{ background: 'rgba(0,0,0,0.1)', padding: '2px 6px', borderRadius: '3px' }}>--llm-mode real</code> 启动。
          </div>
        </div>
      )}

      {/* Hero Card */}
      <div className="hero-card" style={{
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        borderRadius: '12px',
        padding: '32px',
        marginBottom: 'var(--spacing-lg)',
        color: '#fff',
      }}>
        <div style={{ fontSize: '24px', fontWeight: 700, marginBottom: '8px' }}>{heroTitle}</div>
        <div style={{ fontSize: '15px', opacity: 0.9, marginBottom: '20px' }}>{heroHint}</div>
        {heroAction && (
          <Link
            to={heroAction.to}
            style={{
              display: 'inline-block',
              background: '#fff',
              color: '#667eea',
              padding: '10px 24px',
              borderRadius: '6px',
              fontWeight: 600,
              textDecoration: 'none',
              transition: 'transform 0.15s',
            }}
          >
            {heroAction.label}
          </Link>
        )}
        <div style={{ marginTop: '24px', display: 'flex', gap: '24px', fontSize: '13px', opacity: 0.85 }}>
          <div><span style={{ fontWeight: 600 }}>{data.project_count}</span> 个项目</div>
          <div><span style={{ fontWeight: 600 }}>{data.review_count}</span> 待审核</div>
          <div><span style={{ fontWeight: 600 }}>{data.queue_count}</span> 队列中</div>
        </div>
      </div>

      {/* My Projects - Horizontal Card List */}
      {projects.length > 0 && (
        <div className="card" style={{ marginBottom: 'var(--spacing-lg)' }}>
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0 }}>我的项目</h3>
            <Link to="/projects" style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '14px', color: 'var(--primary)', textDecoration: 'none' }}>
              查看全部 <ChevronRight size={16} />
            </Link>
          </div>
          <div className="card-body" style={{ padding: '12px' }}>
            <div style={{
              display: 'flex',
              gap: '12px',
              overflowX: 'auto',
              paddingBottom: '8px',
            }}>
              {projects.slice(0, 5).map((project) => (
                <Link
                  key={project.project_id}
                  to={`/projects/${project.project_id}`}
                  style={{
                    flex: '0 0 200px',
                    padding: '16px',
                    background: 'var(--bg-secondary)',
                    borderRadius: '8px',
                    textDecoration: 'none',
                    border: '1px solid var(--border-color)',
                    transition: 'border-color 0.15s',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                    <BookOpen size={18} style={{ color: 'var(--primary)' }} />
                    <span style={{ fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {project.name || project.project_id}
                    </span>
                  </div>
                  <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                    {project.chapter_count} 章节
                  </div>
                  {project.genre && (
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                      {project.genre}
                    </div>
                  )}
                </Link>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Needs Attention Section */}
      {attentionProjects.length > 0 && (
        <div className="card" style={{ marginBottom: 'var(--spacing-lg)', borderLeft: '4px solid var(--warning)' }}>
          <div className="card-header">
            <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
              <AlertCircle size={18} style={{ color: 'var(--warning)' }} />
              需要关注
            </h3>
          </div>
          <div className="card-body">
            {attentionProjects.map(({ project, chapters }) => (
              <div key={project.project_id} style={{ marginBottom: '12px' }}>
                <div style={{ fontWeight: 600, marginBottom: '4px', color: 'var(--text-primary)' }}>
                  {project.name || project.project_id}
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {chapters.map((ch) => (
                    <Link
                      key={ch.chapter_number}
                      to={`/projects/${project.project_id}?chapter=${ch.chapter_number}`}
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                        padding: '4px 10px',
                        background: ch.status === 'failed' ? 'rgba(220,38,38,0.1)' : 'rgba(217,119,6,0.1)',
                        color: ch.status === 'failed' ? 'var(--danger)' : 'var(--warning)',
                        borderRadius: '4px',
                        fontSize: '13px',
                        textDecoration: 'none',
                      }}
                    >
                      第 {ch.chapter_number} 章 · {tChapterStatus(ch.status)}
                    </Link>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Activity Timeline */}
      <div className="card">
        <div className="card-header">
          <h3>最近活动</h3>
          <span className="text-secondary">{tLlmMode(data.llm_mode)} 模式</span>
        </div>
        <div className="card-body">
          {hasRuns ? (
            <div className="activity-timeline">
              {data.recent_runs.slice(0, 5).map((run, idx) => (
                <div key={run.run_id} className="timeline-item" style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '12px',
                  padding: '12px 0',
                  borderBottom: idx < Math.min(data.recent_runs.length, 5) - 1 ? '1px solid var(--border-color)' : 'none',
                }}>
                  <div style={{
                    width: '10px',
                    height: '10px',
                    borderRadius: '50%',
                    background: getStatusColor(run.status),
                    marginTop: '5px',
                    flexShrink: 0,
                  }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '4px' }}>
                      <Link
                        to={`/projects/${run.project_id}?chapter=${run.chapter}&view=content`}
                        style={{ fontWeight: 500, color: 'var(--text-primary)', textDecoration: 'none' }}
                      >
                        {run.project_name} · 第 {run.chapter} 章
                      </Link>
                      <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                        {formatRelativeTime(run.created_at)}
                      </span>
                    </div>
                    <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                      <span style={{ color: getStatusColor(run.status) }}>
                        {tWorkflowStatus(run.status)}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
              {data.recent_runs.length > 5 && (
                <Link
                  to="/projects"
                  style={{
                    display: 'block',
                    textAlign: 'center',
                    padding: '12px',
                    color: 'var(--primary)',
                    textDecoration: 'none',
                    fontSize: '14px',
                  }}
                >
                  查看更多活动
                </Link>
              )}
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
              <div style={{ marginBottom: '8px' }}>暂无活动记录</div>
              <Link to="/onboarding" style={{ color: 'var(--primary)', textDecoration: 'none' }}>
                创建第一个项目
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
