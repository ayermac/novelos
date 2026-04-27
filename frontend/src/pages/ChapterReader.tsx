import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { get } from '../lib/api'
import StatusBadge from '../components/StatusBadge'
import ErrorState from '../components/ErrorState'
import EmptyState from '../components/EmptyState'
import PageHeader from '../components/PageHeader'

interface ChapterData {
  project_id: string
  project_name: string
  chapter_number: number
  title: string
  status: string
  word_count: number
  quality_score: number | null
  content: string
  created_at: string
  updated_at: string
}

export default function ChapterReader() {
  const { projectId, chapterNumber } = useParams<{
    projectId: string
    chapterNumber: string
  }>()
  const [data, setData] = useState<ChapterData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = () => {
    if (!projectId || !chapterNumber) return
    setLoading(true)
    setError('')
    get<ChapterData>(`/projects/${projectId}/chapters/${chapterNumber}`).then((res) => {
      if (res.ok && res.data) {
        setData(res.data)
      } else {
        setError(res.error?.message || '获取章节失败')
      }
      setLoading(false)
    })
  }

  useEffect(() => {
    load()
  }, [projectId, chapterNumber])

  if (loading) {
    return <div>加载中...</div>
  }

  if (error || !data) {
    return (
      <ErrorState
        title="加载失败"
        message={error || '章节不存在'}
        onRetry={load}
      />
    )
  }

  const hasContent = data.content && data.word_count > 0

  return (
    <div>
      <PageHeader
        title={data.title || `第 ${data.chapter_number} 章`}
        backTo={`/projects/${data.project_id}`}
        backLabel="返回项目"
        actions={
          <div style={{ display: 'flex', gap: '8px' }}>
            {!hasContent && (
              <Link
                to={`/run?project_id=${data.project_id}&chapter=${data.chapter_number}`}
                className="btn btn-primary"
              >
                生成本章
              </Link>
            )}
            {data.chapter_number > 1 && (
              <Link
                to={`/projects/${data.project_id}/chapters/${data.chapter_number - 1}`}
                className="btn btn-secondary"
              >
                上一章
              </Link>
            )}
            <Link
              to={`/projects/${data.project_id}/chapters/${data.chapter_number + 1}`}
              className="btn btn-secondary"
            >
              下一章
            </Link>
          </div>
        }
      />

      {/* Chapter Meta */}
      <div className="card" style={{ marginBottom: 'var(--spacing-lg)' }}>
        <div className="card-body">
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
              gap: '16px',
            }}
          >
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>项目</div>
              <div style={{ fontWeight: 600 }}>{data.project_name}</div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>章节</div>
              <div style={{ fontWeight: 600 }}>第 {data.chapter_number} 章</div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>状态</div>
              <StatusBadge status={data.status} />
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>字数</div>
              <div style={{ fontWeight: 600 }}>{data.word_count.toLocaleString()}</div>
            </div>
            {data.quality_score != null && (
              <div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>质量分</div>
                <div style={{ fontWeight: 600 }}>{data.quality_score}</div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Chapter Content */}
      <div className="card">
        <div className="card-header">
          <h3>正文</h3>
        </div>
        <div className="card-body">
          {hasContent ? (
            <div
              style={{
                maxWidth: '680px',
                margin: '0 auto',
                fontSize: '16px',
                lineHeight: '1.9',
                color: 'var(--text-primary)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {data.content}
            </div>
          ) : (
            <EmptyState
              title="本章还没有正文"
              hint="章节尚未生成，点击下方按钮开始生成。"
              action={{
                label: '生成本章',
                to: `/run?project_id=${data.project_id}&chapter=${data.chapter_number}`,
              }}
            />
          )}
        </div>
      </div>
    </div>
  )
}
