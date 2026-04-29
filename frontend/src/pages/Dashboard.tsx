import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertCircle, ChevronRight, BookOpen, Sparkles, Clock, FileText } from 'lucide-react'
import { get } from '../lib/api'
import { tLlmMode, tWorkflowStatus, tChapterStatus } from '../lib/i18n'
import ErrorState from '../components/ErrorState'

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

interface DashboardData {
  project_count: number
  recent_runs: RunItem[]
  queue_count: number
  review_count: number
  llm_mode: string
  attention_items: Array<{
    project_id: string
    project_name: string
    chapters: Array<{ chapter_number: number; status: string }>
  }>
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
    case 'completed': return '#10b981'
    case 'running': return '#4f46e5'
    case 'failed': return '#ef4444'
    case 'blocked': return '#f59e0b'
    default: return '#94a3b8'
  }
}

function getStatusBadgeClass(status: string): string {
  switch (status) {
    case 'completed': return 'success'
    case 'running': return 'info'
    case 'failed': return 'danger'
    case 'blocked': return 'warning'
    default: return 'neutral'
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
        // Use server-side attention_items instead of N+1 queries
        const items = dashboardRes.data.attention_items || []
        const mapped = items.map((item) => ({
          project: { project_id: item.project_id, name: item.project_name, chapter_count: 0, created_at: '' },
          chapters: item.chapters,
        }))
        setAttentionProjects(mapped)
      } else {
        setError(dashboardRes.error?.message || '获取仪表盘数据失败')
      }
      if (projectsRes.ok && projectsRes.data) {
        setProjects(projectsRes.data)
      }
    } catch {
      setError('网络错误')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  if (loading) {
    return (
      <div className="loading-state">
        <div className="loading-spinner" />
        <span>加载中...</span>
      </div>
    )
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

  const isStub = data.llm_mode === 'stub'
  const hasProjects = data.project_count > 0
  const hasRuns = data.recent_runs.length > 0
  const latestRun = hasRuns ? data.recent_runs[0] : null
  const firstProject = projects[0]

  let heroTitle = ''
  let heroHint = ''
  let heroAction: { label: string; to: string } | undefined

  if (!hasProjects) {
    heroTitle = '开始你的创作之旅'
    heroHint = '创建第一个小说项目，开启 AI 辅助创作体验'
    heroAction = { label: '创建第一个项目', to: '/onboarding' }
  } else if (!hasRuns && firstProject) {
    heroTitle = '项目已就绪'
    heroHint = `${firstProject.name} 已创建，进入工作台开始创作`
    heroAction = { label: '进入工作台', to: `/projects/${firstProject.project_id}` }
  } else if (latestRun?.status === 'failed' || latestRun?.status === 'blocked') {
    heroTitle = latestRun.status === 'failed' ? '最近运行失败' : '最近运行被阻塞'
    heroHint = `${latestRun.project_name} 第 ${latestRun.chapter} 章${latestRun.status === 'failed' ? '生成失败' : '被阻塞'}，请检查后重试`
    heroAction = { label: '查看项目工作台', to: `/projects/${latestRun.project_id}` }
  } else if (latestRun) {
    heroTitle = '继续创作'
    heroHint = `${latestRun.project_name} 第 ${latestRun.chapter} 章已完成，进入工作台继续创作`
    heroAction = { label: '进入工作台', to: `/projects/${latestRun.project_id}?chapter=${latestRun.chapter + 1}` }
  } else if (firstProject) {
    heroTitle = '继续创作'
    heroHint = `你有 ${data.project_count} 个项目，进入工作台继续创作`
    heroAction = { label: '进入工作台', to: `/projects/${firstProject.project_id}` }
  }

  return (
    <div className="dashboard">
      {/* Hero Card */}
      <div className="hero-card">
        <div className="hero-decoration" />
        <div className="hero-content">
          <div className="hero-badge-float">
            {isStub ? (
              <span className="badge-ds badge-warning-ds">
                <span className="badge-dot-ds" />
                演示模式
              </span>
            ) : (
              <span className="badge-ds badge-success-ds">
                <span className="badge-dot-ds" />
                真实模式
              </span>
            )}
          </div>
          <h1 className="hero-title">{heroTitle}</h1>
          <p className="hero-hint">{heroHint}</p>
          {heroAction && (
            <Link to={heroAction.to} className="btn-ds btn-accent-ds btn-lg-ds">
              {heroAction.label}
              <ChevronRight size={18} />
            </Link>
          )}
        </div>
      </div>

      {/* Stats Row */}
      <div className="stats-row">
        <div className="stat-card-ds">
          <div className="stat-icon-ds stat-icon-primary">
            <BookOpen size={20} />
          </div>
          <div className="stat-info">
            <span className="stat-value">{data.project_count}</span>
            <span className="stat-label">项目</span>
          </div>
        </div>
        <div className="stat-card-ds">
          <div className="stat-icon-ds stat-icon-success">
            <FileText size={20} />
          </div>
          <div className="stat-info">
            <span className="stat-value">{data.review_count}</span>
            <span className="stat-label">待审核</span>
          </div>
        </div>
        <div className="stat-card-ds">
          <div className="stat-icon-ds stat-icon-info">
            <Clock size={20} />
          </div>
          <div className="stat-info">
            <span className="stat-value">{data.queue_count}</span>
            <span className="stat-label">队列中</span>
          </div>
        </div>
        <div className="stat-card-ds">
          <div className="stat-icon-ds stat-icon-accent">
            <Sparkles size={20} />
          </div>
          <div className="stat-info">
            <span className="stat-value">{tLlmMode(data.llm_mode)}</span>
            <span className="stat-label">模式</span>
          </div>
        </div>
      </div>

      {/* Content Grid */}
      <div className="content-grid">
        {/* My Projects */}
        {projects.length > 0 && (
          <div className="card-ds">
            <div className="card-header-ds">
              <h3>我的项目</h3>
              <Link to="/projects" className="link-arrow">
                查看全部 <ChevronRight size={16} />
              </Link>
            </div>
            <div className="projects-list">
              {projects.slice(0, 5).map((project) => (
                <Link
                  key={project.project_id}
                  to={`/projects/${project.project_id}`}
                  className="project-row"
                >
                  <div className="project-row-icon">
                    <BookOpen size={16} />
                  </div>
                  <div className="project-row-info">
                    <span className="project-row-name">{project.name || project.project_id}</span>
                    <span className="project-row-meta">{project.chapter_count} 章节</span>
                  </div>
                  {project.genre && (
                    <span className="project-row-genre">{project.genre}</span>
                  )}
                </Link>
              ))}
            </div>
          </div>
        )}

        {/* Needs Attention */}
        {attentionProjects.length > 0 && (
          <div className="card-ds attention-card">
            <div className="card-header-ds">
              <h3>
                <AlertCircle size={18} className="attention-icon" />
                需要关注
              </h3>
            </div>
            <div className="card-body-ds">
              {attentionProjects.map(({ project, chapters }) => (
                <div key={project.project_id} className="attention-item">
                  <div className="attention-project">{project.name || project.project_id}</div>
                  <div className="attention-chapters">
                    {chapters.map((ch) => (
                      <Link
                        key={ch.chapter_number}
                        to={`/projects/${project.project_id}?chapter=${ch.chapter_number}`}
                        className={`attention-tag ${getStatusBadgeClass(ch.status)}`}
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
      </div>

      {/* Activity Timeline */}
      <div className="card-ds">
        <div className="card-header-ds">
          <h3>最近活动</h3>
          <span className="text-muted-ds">近 5 次运行</span>
        </div>
        <div className="activity-list">
          {hasRuns ? (
            <>
              {data.recent_runs.slice(0, 5).map((run) => (
                <div key={run.run_id} className="activity-item">
                  <div className="activity-dot" style={{ background: getStatusColor(run.status) }} />
                  <div className="activity-content">
                    <div className="activity-main">
                      <Link to={`/projects/${run.project_id}?chapter=${run.chapter}&view=content`}>
                        {run.project_name} · 第 {run.chapter} 章
                      </Link>
                      <span className="activity-time">{formatRelativeTime(run.created_at)}</span>
                    </div>
                    <span className={`badge-ds badge-${getStatusBadgeClass(run.status)}-ds`}>
                      <span className="badge-dot-ds" />
                      {tWorkflowStatus(run.status)}
                    </span>
                  </div>
                </div>
              ))}
              {data.recent_runs.length > 5 && (
                <Link to="/projects" className="activity-more">
                  查看更多活动
                </Link>
              )}
            </>
          ) : (
            <div className="empty-activity">
              <Clock size={32} />
              <p>暂无活动记录</p>
              <Link to="/onboarding" className="btn-ds btn-primary-ds">创建第一个项目</Link>
            </div>
          )}
        </div>
      </div>

      <style>{`
        .dashboard {
          display: flex;
          flex-direction: column;
          gap: var(--space-6);
        }

        /* Loading */
        .loading-state {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: var(--space-12);
          gap: var(--space-3);
          color: var(--text-charcoal);
        }

        .loading-spinner {
          width: 32px;
          height: 32px;
          border: 2px solid var(--paper-elevated);
          border-top-color: var(--ink-accent);
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }

        @keyframes spin { to { transform: rotate(360deg); } }

        /* Hero Card */
        .hero-card {
          position: relative;
          background: var(--gradient-ink);
          border-radius: var(--radius-xl);
          padding: var(--space-8);
          color: white;
          overflow: hidden;
        }

        .hero-decoration {
          position: absolute;
          top: -50%;
          right: -10%;
          width: 400px;
          height: 400px;
          background: radial-gradient(circle, rgba(129, 140, 248, 0.3) 0%, transparent 70%);
          pointer-events: none;
        }

        .hero-content {
          position: relative;
          z-index: 1;
        }

        .hero-badge-float {
          margin-bottom: var(--space-4);
        }

        .hero-title {
          font-family: var(--font-brand);
          font-size: var(--text-2xl);
          font-weight: var(--font-bold);
          margin-bottom: var(--space-2);
        }

        .hero-hint {
          font-size: var(--text-md);
          opacity: 0.9;
          margin-bottom: var(--space-5);
          max-width: 480px;
        }

        /* Stats Row */
        .stats-row {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: var(--space-4);
        }

        .stat-card-ds {
          display: flex;
          align-items: center;
          gap: var(--space-4);
          padding: var(--space-5);
          background: var(--paper-surface);
          border-radius: var(--radius-lg);
          box-shadow: var(--shadow-flat);
          border: 1px solid rgba(30, 58, 95, 0.06);
          transition: all var(--duration-normal) var(--ease-out);
        }

        .stat-card-ds:hover {
          box-shadow: var(--shadow-md);
          transform: translateY(-2px);
        }

        .stat-icon-ds {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 48px;
          height: 48px;
          border-radius: var(--radius-lg);
        }

        .stat-icon-primary { background: rgba(30, 58, 95, 0.08); color: var(--ink-primary); }
        .stat-icon-success { background: rgba(16, 185, 129, 0.1); color: var(--status-success); }
        .stat-icon-info { background: rgba(79, 70, 229, 0.1); color: var(--ink-accent); }
        .stat-icon-accent { background: rgba(245, 158, 11, 0.1); color: var(--status-warning); }

        .stat-info { display: flex; flex-direction: column; }
        .stat-value {
          font-family: var(--font-brand);
          font-size: var(--text-xl);
          font-weight: var(--font-bold);
          color: var(--text-ink);
        }
        .stat-label { font-size: var(--text-sm); color: var(--text-charcoal); }

        /* Content Grid */
        .content-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
          gap: var(--space-6);
        }

        /* Card Design System */
        .card-ds {
          background: var(--paper-surface);
          border-radius: var(--radius-lg);
          box-shadow: var(--shadow-flat);
          border: 1px solid rgba(30, 58, 95, 0.06);
          overflow: hidden;
        }

        .card-header-ds {
          padding: var(--space-4) var(--space-5);
          border-bottom: 1px solid rgba(30, 58, 95, 0.04);
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .card-header-ds h3 {
          font-family: var(--font-brand);
          font-size: var(--text-md);
          font-weight: var(--font-semibold);
          display: flex;
          align-items: center;
          gap: var(--space-2);
          margin: 0;
        }

        .card-body-ds { padding: var(--space-4) var(--space-5); }

        /* Badges */
        .badge-ds {
          display: inline-flex;
          align-items: center;
          gap: var(--space-1);
          padding: var(--space-1) var(--space-3);
          font-size: var(--text-xs);
          font-weight: var(--font-medium);
          border-radius: var(--radius-full);
        }

        .badge-dot-ds {
          width: 6px;
          height: 6px;
          border-radius: 50%;
        }

        .badge-success-ds { background: rgba(16, 185, 129, 0.1); color: #065f46; }
        .badge-warning-ds { background: rgba(245, 158, 11, 0.1); color: #92400e; }
        .badge-info-ds { background: rgba(79, 70, 229, 0.1); color: var(--ink-accent); }
        .badge-danger-ds { background: rgba(239, 68, 68, 0.1); color: #991b1b; }
        .badge-neutral-ds { background: rgba(148, 163, 184, 0.1); color: var(--text-charcoal); }

        .badge-success-ds .badge-dot-ds { background: var(--status-success); }
        .badge-warning-ds .badge-dot-ds { background: var(--status-warning); }
        .badge-info-ds .badge-dot-ds { background: var(--ink-accent); }
        .badge-danger-ds .badge-dot-ds { background: var(--status-danger); }
        .badge-neutral-ds .badge-dot-ds { background: var(--text-gray); }

        /* Buttons */
        .btn-ds {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: var(--space-2);
          padding: var(--space-2) var(--space-4);
          font-family: var(--font-body);
          font-size: var(--text-base);
          font-weight: var(--font-medium);
          border-radius: var(--radius-md);
          border: 1px solid transparent;
          cursor: pointer;
          transition: all var(--duration-fast) var(--ease-out);
          text-decoration: none;
        }

        .btn-primary-ds {
          background: var(--gradient-ink);
          color: white;
        }

        .btn-accent-ds {
          background: var(--gradient-glow);
          color: white;
        }

        .btn-accent-ds:hover {
          box-shadow: var(--shadow-glow);
          transform: translateY(-1px);
        }

        .btn-lg-ds {
          padding: var(--space-3) var(--space-6);
          font-size: var(--text-md);
        }

        /* Projects List */
        .projects-list { padding: var(--space-2); }

        .project-row {
          display: flex;
          align-items: center;
          gap: var(--space-3);
          padding: var(--space-3) var(--space-4);
          border-radius: var(--radius-md);
          text-decoration: none;
          transition: all var(--duration-fast) var(--ease-out);
        }

        .project-row:hover { background: var(--paper-hover); }

        .project-row-icon {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 32px;
          height: 32px;
          background: rgba(79, 70, 229, 0.1);
          border-radius: var(--radius-md);
          color: var(--ink-accent);
        }

        .project-row-info { flex: 1; min-width: 0; }
        .project-row-name {
          display: block;
          font-weight: var(--font-medium);
          color: var(--text-ink);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .project-row-meta { font-size: var(--text-xs); color: var(--text-gray); }
        .project-row-genre {
          font-size: var(--text-xs);
          padding: var(--space-1) var(--space-2);
          background: var(--paper-bg);
          border-radius: var(--radius-full);
          color: var(--text-charcoal);
        }

        /* Link Arrow */
        .link-arrow {
          display: flex;
          align-items: center;
          gap: var(--space-1);
          font-size: var(--text-sm);
          color: var(--ink-accent);
          text-decoration: none;
          transition: gap var(--duration-fast) var(--ease-out);
        }
        .link-arrow:hover { gap: var(--space-2); }

        /* Attention */
        .attention-card .attention-icon { color: var(--status-warning); }

        .attention-item { margin-bottom: var(--space-4); }
        .attention-item:last-child { margin-bottom: 0; }

        .attention-project {
          font-weight: var(--font-semibold);
          color: var(--text-ink);
          margin-bottom: var(--space-2);
        }

        .attention-chapters {
          display: flex;
          flex-wrap: wrap;
          gap: var(--space-2);
        }

        .attention-tag {
          padding: var(--space-1) var(--space-3);
          border-radius: var(--radius-md);
          font-size: var(--text-sm);
          text-decoration: none;
          transition: all var(--duration-fast) var(--ease-out);
        }

        .attention-tag:hover { transform: translateY(-1px); }
        .attention-tag.success { background: rgba(16, 185, 129, 0.1); color: #065f46; }
        .attention-tag.warning { background: rgba(245, 158, 11, 0.1); color: #92400e; }
        .attention-tag.danger { background: rgba(239, 68, 68, 0.1); color: #991b1b; }
        .attention-tag.info { background: rgba(79, 70, 229, 0.1); color: var(--ink-accent); }
        .attention-tag.neutral { background: rgba(148, 163, 184, 0.1); color: var(--text-charcoal); }

        /* Activity List */
        .activity-list { padding: 0; }

        .activity-item {
          display: flex;
          align-items: flex-start;
          gap: var(--space-3);
          padding: var(--space-4) var(--space-5);
          border-bottom: 1px solid rgba(30, 58, 95, 0.04);
        }

        .activity-item:last-child { border-bottom: none; }

        .activity-dot {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          margin-top: 5px;
          flex-shrink: 0;
        }

        .activity-content {
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: var(--space-2);
        }

        .activity-main {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
        }

        .activity-main a {
          color: var(--text-ink);
          text-decoration: none;
          font-weight: var(--font-medium);
        }

        .activity-main a:hover { color: var(--ink-accent); }

        .activity-time {
          font-size: var(--text-sm);
          color: var(--text-gray);
        }

        .activity-more {
          display: block;
          text-align: center;
          padding: var(--space-4);
          color: var(--ink-accent);
          text-decoration: none;
          font-size: var(--text-sm);
          border-top: 1px solid rgba(30, 58, 95, 0.04);
        }

        .activity-more:hover { background: var(--paper-hover); }

        /* Empty Activity */
        .empty-activity {
          display: flex;
          flex-direction: column;
          align-items: center;
          padding: var(--space-10);
          text-align: center;
          color: var(--text-charcoal);
        }

        .empty-activity > svg { color: var(--text-muted); margin-bottom: var(--space-3); }
        .empty-activity p { margin-bottom: var(--space-4); }

        /* Text Muted */
        .text-muted-ds { color: var(--text-gray); font-size: var(--text-sm); }

        /* Responsive */
        @media (max-width: 1024px) {
          .stats-row { grid-template-columns: repeat(2, 1fr); }
        }

        @media (max-width: 768px) {
          .stats-row { grid-template-columns: 1fr; }
          .hero-card { padding: var(--space-6); }
          .content-grid { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  )
}
