import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { get } from '../lib/api'

interface Workspace {
  project: {
    project_id: string
    name: string
    genre?: string
    description?: string
  }
  chapters: Array<{
    chapter_number: number
    status: string
    word_count: number
    quality_score?: number
  }>
  recent_runs: Array<{
    run_id: string
    chapter_number: number
    status: string
    created_at: string
  }>
  stats: {
    total_chapters: number
    total_words: number
    status_counts: Record<string, number>
  }
}

export default function ProjectDetail() {
  const { id } = useParams<{ id: string }>()
  const [data, setData] = useState<Workspace | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (id) {
      get<Workspace>(`/projects/${id}/workspace`).then((res) => {
        if (res.ok && res.data) {
          setData(res.data)
        }
        setLoading(false)
      })
    }
  }, [id])

  if (loading) {
    return <div>加载中...</div>
  }

  if (!data) {
    return (
      <div>
        <div className="alert alert-error">项目不存在</div>
        <Link to="/projects" className="btn btn-secondary">
          返回项目列表
        </Link>
      </div>
    )
  }

  return (
    <div>
      <div className="flex justify-between items-center" style={{ marginBottom: '24px' }}>
        <h2>{data.project.name}</h2>
        <Link to="/run" className="btn btn-primary">
          生成章节
        </Link>
      </div>

      {/* Stats */}
      <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
        <div className="stat-card">
          <h3>总章节</h3>
          <div className="stat-value">{data.stats.total_chapters}</div>
        </div>
        <div className="stat-card">
          <h3>总字数</h3>
          <div className="stat-value">{data.stats.total_words.toLocaleString()}</div>
        </div>
        <div className="stat-card">
          <h3>待审核</h3>
          <div className="stat-value" style={{ color: 'var(--warning)' }}>
            {data.stats.status_counts['review'] || 0}
          </div>
        </div>
      </div>

      {/* Chapters */}
      <div className="card">
        <div className="card-header">
          <h3>章节列表</h3>
        </div>
        <div className="card-body">
          {data.chapters.length > 0 ? (
            <table className="data-table">
              <thead>
                <tr>
                  <th>章节</th>
                  <th>状态</th>
                  <th>字数</th>
                  <th>质量分</th>
                </tr>
              </thead>
              <tbody>
                {data.chapters.slice(0, 20).map((chapter) => (
                  <tr key={chapter.chapter_number}>
                    <td>第 {chapter.chapter_number} 章</td>
                    <td>
                      <span className={`status-badge status-${chapter.status}`}>
                        {chapter.status}
                      </span>
                    </td>
                    <td>{chapter.word_count}</td>
                    <td>{chapter.quality_score || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty-state">
              <div className="empty-title">暂无章节</div>
              <div className="empty-hint">开始生成第一章</div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
