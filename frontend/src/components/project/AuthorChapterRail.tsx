import { tChapterStatusLabel } from '../../lib/i18n'

interface Chapter {
  chapter_number: number
  status: string
  word_count: number
  quality_score?: number
  title?: string
}

interface AuthorChapterRailProps {
  chapters: Chapter[]
  currentChapter: number
  llmMode: string
  isWorkflowRunning?: boolean
  onSelectChapter: (chapterNumber: number) => void
}

function chapterStatusIcon(status: string): string {
  switch (status) {
    case 'published': return '✓'
    case 'drafted':
    case 'polished':
    case 'reviewed':
    case 'scripted': return '✎'
    case 'blocking':
    case 'revision':
    case 'review': return '⚠'
    case 'failed':
    case 'blocked': return '✗'
    case 'planned':
    case 'pending': return '○'
    default: return '-'
  }
}

function chapterStatusColor(status: string): string {
  switch (status) {
    case 'published': return '#16a34a'
    case 'drafted':
    case 'polished':
    case 'reviewed':
    case 'scripted': return '#2563eb'
    case 'blocking':
    case 'revision':
    case 'review': return '#d97706'
    case 'failed':
    case 'blocked': return '#dc2626'
    case 'planned':
    case 'pending': return '#9ca3af'
    default: return '#d1d5db'
  }
}

export default function AuthorChapterRail({
  chapters,
  currentChapter,
  llmMode,
  isWorkflowRunning,
  onSelectChapter,
}: AuthorChapterRailProps) {
  const publishedCount = chapters.filter((c) => c.status === 'published').length
  const progress = chapters.length > 0 ? Math.round((publishedCount / chapters.length) * 100) : 0

  return (
    <aside className="author-rail" aria-label="章节导航">
      <div className="author-rail-header">
        <h3>章节</h3>
        <div className="author-rail-progress">
          <span>{publishedCount}/{chapters.length}</span>
          <div className="author-rail-progress-bar">
            <div className="author-rail-progress-fill" style={{ width: `${progress}%` }} />
          </div>
          <span>{progress}%</span>
        </div>
      </div>
      <div className="author-rail-list">
        {chapters.map((ch) => {
          const isActive = ch.chapter_number === currentChapter
          const icon = chapterStatusIcon(ch.status)
          const color = chapterStatusColor(ch.status)
          const title = ch.title || `第 ${ch.chapter_number} 章`
          const statusLabel = tChapterStatusLabel(ch.status, ch.status === 'reviewed' && llmMode === 'real')

          return (
            <button
              key={ch.chapter_number}
              className={`author-rail-item${isActive ? ' active' : ''}`}
              onClick={() => onSelectChapter(ch.chapter_number)}
              title={`${title} — ${statusLabel}`}
            >
              <span className="author-rail-icon" style={{ color }}>{icon}</span>
              <span className="author-rail-label">{title}</span>
              <span className="author-rail-meta">
                {isWorkflowRunning && isActive && (
                  <span className="author-rail-running" />
                )}
                {ch.word_count > 0 && (
                  <span className="author-rail-wordcount">{ch.word_count.toLocaleString()}</span>
                )}
                <span className="author-rail-status">{statusLabel}</span>
              </span>
            </button>
          )
        })}
      </div>
    </aside>
  )
}
