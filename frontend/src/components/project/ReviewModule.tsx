import { useState, useEffect, useCallback } from 'react'
import { get, post } from '../../lib/api'
import { CheckCircle2, AlertTriangle, Clock } from 'lucide-react'

interface Chapter {
  chapter_number: number
  status: string
  word_count: number
  title?: string
  awaiting_publish?: boolean
}

interface Run {
  run_id: string
  chapter_number: number
  status: string
  error_message: string | null
}

interface Workspace {
  project: { project_id: string; name: string }
  chapters: Chapter[]
  stats: { status_counts: Record<string, number> }
  recent_runs?: Run[]
}

interface Props {
  projectId: string
}

export default function ReviewModule({ projectId }: Props) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [loading, setLoading] = useState(true)
  const [publishingChapter, setPublishingChapter] = useState<number | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    const res = await get<Workspace>(`/projects/${projectId}/workspace`)
    if (res.ok && res.data) setWorkspace(res.data)
    else setError(res.error?.message || '获取审核数据失败')
    setLoading(false)
  }, [projectId])

  useEffect(() => { load() }, [load])

  const handlePublish = async (chapterNumber: number) => {
    setPublishingChapter(chapterNumber)
    setError('')
    const res = await post('/publish/chapter', { project_id: projectId, chapter: chapterNumber })
    if (res.ok) {
      load()
    } else {
      setError(res.error?.message || '发布失败')
    }
    setPublishingChapter(null)
  }

  if (loading) return <div className="module-loading">加载中...</div>
  if (!workspace) return <div className="module-loading">加载失败</div>

  const statusCounts = workspace.stats.status_counts || {}
  const blockingChapters = workspace.chapters.filter((c) => c.status === 'blocking')
  const reviewedChapters = workspace.chapters.filter((c) => c.status === 'reviewed')
  const revisionChapters = workspace.chapters.filter((c) => c.status === 'revision')
  const recentRuns = workspace.recent_runs || []

  // Get error messages for blocking chapters
  const blockingErrors: Record<number, string> = {}
  for (const run of recentRuns) {
    if (run.status === 'blocked' || run.status === 'failed') {
      if (run.error_message && !blockingErrors[run.chapter_number]) {
        blockingErrors[run.chapter_number] = run.error_message
      }
    }
  }

  // Build summary stats
  const summaryItems = [
    { label: '已发布', count: statusCounts.published || 0, color: '#16a34a', icon: <CheckCircle2 size={16} /> },
    { label: '待发布', count: reviewedChapters.length, color: '#2563eb', icon: <Clock size={16} /> },
    { label: '已阻塞', count: blockingChapters.length, color: '#dc2626', icon: <AlertTriangle size={16} /> },
    { label: '返修中', count: revisionChapters.length, color: '#d97706', icon: <AlertTriangle size={16} /> },
  ]

  return (
    <div className="project-module">
      <div className="module-header">
        <h3><CheckCircle2 size={18} /> 审核中心</h3>
      </div>

      {error && <div className="alert alert-error" style={{ marginBottom: 12 }}>{error}</div>}

      {/* Summary stats */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        {summaryItems.map((item) => (
          <div key={item.label} className="data-card" style={{ minWidth: 120, textAlign: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, color: item.color, marginBottom: 4 }}>
              {item.icon}
              <span style={{ fontSize: 20, fontWeight: 600 }}>{item.count}</span>
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{item.label}</div>
          </div>
        ))}
      </div>

      {/* Blocking chapters */}
      {blockingChapters.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: '#dc2626', display: 'flex', alignItems: 'center', gap: 6 }}>
            <AlertTriangle size={16} /> 已阻塞章节
          </h4>
          {blockingChapters.map((ch) => (
            <div key={ch.chapter_number} className="data-card" style={{ marginBottom: 8, borderLeft: '3px solid #dc2626' }}>
              <div className="data-card-header">
                <span className="data-card-category" style={{ background: '#fee2e2', color: '#dc2626' }}>阻塞</span>
                <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>第 {ch.chapter_number} 章</span>
              </div>
              <div className="data-card-title">{ch.title || `第 ${ch.chapter_number} 章`}</div>
              {blockingErrors[ch.chapter_number] && (
                <div style={{ marginTop: 6, padding: '6px 8px', background: '#fef2f2', borderRadius: '4px', fontSize: 12, color: '#dc2626' }}>
                  {blockingErrors[ch.chapter_number]}
                </div>
              )}
              <div className="data-card-content">
                章节生成过程中遇到问题，需要人工处理。可在章节工作区中查看错误详情并重置。
              </div>
              <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                <a
                  href={`/projects/${projectId}?module=chapters&chapter=${ch.chapter_number}`}
                  className="btn btn-secondary btn-sm"
                  style={{ textDecoration: 'none', fontSize: 12 }}
                >
                  查看详情
                </a>
                <button
                  className="btn btn-secondary btn-sm"
                  style={{ fontSize: 12 }}
                  onClick={async () => {
                    const res = await post(`/projects/${projectId}/chapters/${ch.chapter_number}/reset`)
                    if (res.ok) load()
                    else setError(res.error?.message || '重置失败')
                  }}
                >
                  重置章节
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Reviewed chapters (awaiting publish) */}
      {reviewedChapters.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: '#2563eb', display: 'flex', alignItems: 'center', gap: 6 }}>
            <Clock size={16} /> 待发布章节
          </h4>
          {reviewedChapters.map((ch) => (
            <div key={ch.chapter_number} className="data-card" style={{ marginBottom: 8, borderLeft: '3px solid #2563eb' }}>
              <div className="data-card-header">
                <span className="data-card-badge">待发布</span>
                <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>第 {ch.chapter_number} 章 · {ch.word_count.toLocaleString()} 字</span>
              </div>
              <div className="data-card-title">{ch.title || `第 ${ch.chapter_number} 章`}</div>
              <div className="data-card-content">AI 审核已通过，等待人工确认发布</div>
              <div style={{ marginTop: 8 }}>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => handlePublish(ch.chapter_number)}
                  disabled={publishingChapter === ch.chapter_number}
                >
                  {publishingChapter === ch.chapter_number ? '发布中...' : '确认发布'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Revision chapters */}
      {revisionChapters.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: '#d97706' }}>
            返修中章节
          </h4>
          {revisionChapters.map((ch) => (
            <div key={ch.chapter_number} className="data-card" style={{ marginBottom: 8, borderLeft: '3px solid #d97706' }}>
              <div className="data-card-header">
                <span className="data-card-category" style={{ background: '#fef3c7', color: '#92400e' }}>返修</span>
                <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>第 {ch.chapter_number} 章</span>
              </div>
              <div className="data-card-title">{ch.title || `第 ${ch.chapter_number} 章`}</div>
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {blockingChapters.length === 0 && reviewedChapters.length === 0 && revisionChapters.length === 0 && (
        <div className="data-empty">
          <div className="data-empty-icon"><CheckCircle2 size={32} /></div>
          <div className="data-empty-title">无需审核的章节</div>
          <div className="data-empty-desc">当章节需要人工审核或发布时，会显示在此处</div>
        </div>
      )}
    </div>
  )
}
