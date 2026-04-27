import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { get } from '../lib/api'
import { tChapterStatus } from '../lib/i18n'
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

interface Workspace {
  chapters: Array<{ chapter_number: number; status: string }>
  recent_runs: Array<{ run_id: string; chapter_number: number; status: string }>
}

export default function ChapterReader() {
  const { projectId, chapterNumber } = useParams<{
    projectId: string
    chapterNumber: string
  }>()
  const [data, setData] = useState<ChapterData | null>(null)
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [llmMode, setLlmMode] = useState<string>('stub')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = () => {
    if (!projectId || !chapterNumber) return
    setLoading(true)
    setError('')
    
    // Load chapter data
    get<ChapterData>(`/projects/${projectId}/chapters/${chapterNumber}`).then((res) => {
      if (res.ok && res.data) {
        setData(res.data)
      } else {
        setError(res.error?.message || '获取章节失败')
      }
      setLoading(false)
    })

    // Load workspace for navigation
    get<Workspace>(`/projects/${projectId}/workspace`).then((res) => {
      if (res.ok && res.data) {
        setWorkspace(res.data)
      }
    })

    // Get LLM mode
    get<{ llm_mode: string }>('/health').then((res) => {
      if (res.ok && res.data) {
        setLlmMode(res.data.llm_mode)
      }
    })
  }

  useEffect(() => {
    load()
  }, [projectId, chapterNumber])

  if (loading) {
    return <div className="loading-state">加载中...</div>
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
  const isStub = llmMode === 'stub'
  const currentChapterNum = parseInt(chapterNumber || '1', 10)
  const prevChapter = currentChapterNum > 1 ? currentChapterNum - 1 : null
  const nextChapter = workspace?.chapters.find(c => c.chapter_number === currentChapterNum + 1)
  const hasPrevChapter = workspace?.chapters.some(c => c.chapter_number === prevChapter)
  
  // Find recent run for this chapter
  const recentRun = workspace?.recent_runs.find(r => r.chapter_number === currentChapterNum)

  return (
    <div>
      <PageHeader
        title={data.title || `第 ${data.chapter_number} 章`}
        backTo={`/projects/${data.project_id}`}
        backLabel="返回项目"
        actions={
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {!hasContent && (
              <Link
                to={`/run?project_id=${data.project_id}&chapter=${data.chapter_number}`}
                className="btn btn-primary"
              >
                生成本章
              </Link>
            )}
            {hasContent && recentRun && (
              <Link
                to={`/runs/${recentRun.run_id}`}
                className="btn btn-secondary"
              >
                查看工作流
              </Link>
            )}
            {hasPrevChapter && prevChapter && (
              <Link
                to={`/projects/${data.project_id}/chapters/${prevChapter}`}
                className="btn btn-secondary"
              >
                上一章
              </Link>
            )}
            {nextChapter ? (
              nextChapter.status === 'published' ? (
                <Link
                  to={`/projects/${data.project_id}/chapters/${nextChapter.chapter_number}`}
                  className="btn btn-secondary"
                >
                  下一章
                </Link>
              ) : (
                <Link
                  to={`/run?project_id=${data.project_id}&chapter=${nextChapter.chapter_number}`}
                  className="btn btn-secondary"
                >
                  生成下一章
                </Link>
              )
            ) : null}
          </div>
        }
      />

      {/* Demo content notice */}
      {hasContent && isStub && (
        <div className="alert alert-info" style={{ marginBottom: '16px' }}>
          <strong>演示正文</strong>
          <div style={{ marginTop: '4px', fontSize: '14px' }}>
            本章为演示模式生成内容，由本地 Stub 模板生成，不代表真实创作质量。
          </div>
        </div>
      )}

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
              <span className={`status-badge status-${data.status}`}>
                {tChapterStatus(data.status)}
              </span>
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
            <div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>来源</div>
              <span className={`status-badge status-${llmMode}`}>
                {isStub ? '演示' : '真实'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Chapter Content */}
      <div className="card">
        <div className="card-header">
          <h3>{isStub ? '演示正文' : '正文'}</h3>
        </div>
        <div className="card-body">
          {hasContent ? (
            <div
              style={{
                maxWidth: '720px',
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

      <style>{`
        .loading-state {
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 200px;
          color: var(--text-secondary);
        }
        .alert-info {
          background: #eff6ff;
          border: 1px solid #bfdbfe;
          padding: 12px 16px;
          border-radius: 6px;
          color: #1e40af;
        }
      `}</style>
    </div>
  )
}
