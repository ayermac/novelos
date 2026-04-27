import { tChapterStatus } from '../lib/i18n'

interface Chapter {
  chapter_number: number
  status: string
  word_count?: number
  title?: string
}

interface Props {
  chapters: Chapter[]
  currentChapter: number
  onSelect: (chapterNumber: number) => void
}

function chapterStatusIcon(status: string): string {
  switch (status) {
    case 'published':
      return '✓'
    case 'drafted':
    case 'polished':
    case 'reviewed':
    case 'scripted':
      return '✎'
    case 'blocking':
    case 'revision':
    case 'review':
      return '⚠'
    case 'failed':
    case 'blocked':
      return '✗'
    case 'planned':
    case 'pending':
      return '○'
    default:
      return '-'
  }
}

function chapterStatusColor(status: string): string {
  switch (status) {
    case 'published':
      return '#16a34a'
    case 'drafted':
    case 'polished':
    case 'reviewed':
    case 'scripted':
      return '#2563eb'
    case 'blocking':
    case 'revision':
    case 'review':
      return '#d97706'
    case 'failed':
    case 'blocked':
      return '#dc2626'
    case 'planned':
    case 'pending':
      return '#9ca3af'
    default:
      return '#d1d5db'
  }
}

export default function ChapterNav({ chapters, currentChapter, onSelect }: Props) {
  if (chapters.length === 0) {
    return (
      <div style={{ padding: '16px', color: 'var(--text-muted)', fontSize: '13px', textAlign: 'center' }}>
        暂无章节
      </div>
    )
  }

  return (
    <div className="chapter-nav">
      <div className="chapter-nav-header">章节列表</div>
      <div className="chapter-nav-list">
        {chapters.map((ch) => {
          const isActive = ch.chapter_number === currentChapter
          const icon = chapterStatusIcon(ch.status)
          const color = chapterStatusColor(ch.status)
          const title = ch.title || `第 ${ch.chapter_number} 章`
          const statusLabel = tChapterStatus(ch.status)

          return (
            <button
              key={ch.chapter_number}
              className={`chapter-nav-item${isActive ? ' active' : ''}`}
              onClick={() => onSelect(ch.chapter_number)}
              title={`${title} — ${statusLabel}`}
            >
              <span className="chapter-nav-icon" style={{ color }}>{icon}</span>
              <span className="chapter-nav-label">{title}</span>
              <span className="chapter-nav-status">{statusLabel}</span>
            </button>
          )
        })}
      </div>

      <style>{`
        .chapter-nav {
          display: flex;
          flex-direction: column;
          height: 100%;
          border-right: 1px solid var(--border-color);
          background: var(--bg-primary);
        }
        .chapter-nav-header {
          padding: 12px 16px;
          font-size: 12px;
          font-weight: 600;
          color: var(--text-muted);
          text-transform: uppercase;
          border-bottom: 1px solid var(--border-color);
        }
        .chapter-nav-list {
          flex: 1;
          overflow-y: auto;
          padding: 4px 0;
        }
        .chapter-nav-item {
          display: flex;
          align-items: center;
          gap: 8px;
          width: 100%;
          padding: 8px 16px;
          border: none;
          background: none;
          cursor: pointer;
          font-size: 13px;
          color: var(--text-secondary);
          text-align: left;
          transition: background 0.15s;
        }
        .chapter-nav-item:hover {
          background: var(--bg-tertiary);
        }
        .chapter-nav-item.active {
          background: #eff6ff;
          color: var(--primary);
          font-weight: 500;
        }
        .chapter-nav-icon {
          width: 18px;
          font-size: 12px;
          flex-shrink: 0;
          text-align: center;
        }
        .chapter-nav-label {
          flex: 1;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .chapter-nav-status {
          font-size: 11px;
          color: var(--text-muted);
          flex-shrink: 0;
        }
        .chapter-nav-item.active .chapter-nav-status {
          color: var(--primary);
        }
      `}</style>
    </div>
  )
}
