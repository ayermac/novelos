import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertCircle, BookOpen, CheckCircle2, FileText } from 'lucide-react'
import { get } from '../../lib/api'

interface ProjectSummary {
  project_id: string
  name: string
  genre?: string
  description?: string
  total_chapters_planned: number
  target_words: number
}

interface WorkspaceStats {
  total_chapters: number
  total_words: number
  status_counts: Record<string, number>
}

interface ContextStatus {
  ready: boolean
  score: number
  missing: string[]
  actions: { label: string; path: string }[]
}

interface Props {
  project: ProjectSummary
  stats: WorkspaceStats
}

export default function ProjectOverviewModule({ project, stats }: Props) {
  const [contextStatus, setContextStatus] = useState<ContextStatus | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    const res = await get<ContextStatus>(`/projects/${project.project_id}/context-status`)
    if (res.ok && res.data) setContextStatus(res.data)
    setLoading(false)
  }, [project.project_id])

  useEffect(() => { load() }, [load])

  const published = stats.status_counts?.published || 0
  const planned = stats.status_counts?.planned || 0

  return (
    <div className="project-module">
      <div className="module-header">
        <h3><BookOpen size={18} /> 项目总览</h3>
      </div>

      <div className="data-grid">
        <div className="data-card">
          <div className="data-card-title">项目简介</div>
          <div className="data-card-content">
            {project.description || '尚未填写项目简介。'}
          </div>
          {!project.description && (
            <Link className="btn btn-secondary btn-sm" to={`/projects/${project.project_id}?module=settings`}>
              填写简介
            </Link>
          )}
        </div>

        <div className="data-card">
          <div className="data-card-title">章节进度</div>
          <div className="data-card-content">
            已发布 {published} 章，已规划 {planned} 章，共 {stats.total_chapters} 个章节槽位。
          </div>
          <div className="data-card-traits">当前字数：{stats.total_words.toLocaleString()}</div>
        </div>

        <div className="data-card">
          <div className="data-card-title">创作目标</div>
          <div className="data-card-content">
            预计 {project.total_chapters_planned} 章，目标 {project.target_words.toLocaleString()} 字。
          </div>
        </div>
      </div>

      <div className="data-card" style={{ marginTop: 16 }}>
        <div className="data-card-header">
          {contextStatus?.ready ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
          <div className="data-card-title" style={{ marginBottom: 0 }}>上下文准备度</div>
          {contextStatus && <span className="data-card-badge">{contextStatus.score}%</span>}
        </div>

        {loading ? (
          <div className="data-card-content">检查中...</div>
        ) : contextStatus?.ready ? (
          <div className="data-card-content">项目资料已满足章节生成的最低要求。</div>
        ) : (
          <>
            <div className="data-card-content">
              生成前还需要补齐这些资料：
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {(contextStatus?.actions || []).map((action) => (
                <Link key={`${action.label}-${action.path}`} className="btn btn-secondary btn-sm" to={action.path}>
                  <FileText size={14} />
                  {action.label}
                </Link>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
