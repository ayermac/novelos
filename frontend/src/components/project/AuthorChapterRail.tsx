import { useState, useRef, useEffect, useCallback } from 'react'
import { MoreHorizontal, FileText, Eye, History, Copy, Play, Sparkles, CheckCircle2, Loader2, AlertCircle } from 'lucide-react'
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
  isChapterWorkflowRunning?: (chapterNumber: number) => boolean
  onSelectChapter: (chapterNumber: number) => void
  onGenerateChapter?: (chapterNumber: number) => void
  onGenerateNextFromChapter?: (chapterNumber: number) => void
  onPublishChapter?: (chapterNumber: number) => void
  onResetRunRecoveryForChapter?: (chapterNumber: number) => Promise<void> | void
  onOpenChapterView?: (chapterNumber: number, tab: 'content' | 'workflow' | 'artifacts' | 'history') => void
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
    case 'published': return 'var(--wb-success)'
    case 'drafted':
    case 'polished':
    case 'reviewed':
    case 'scripted': return 'var(--wb-info)'
    case 'blocking':
    case 'revision':
    case 'review': return 'var(--wb-warning)'
    case 'failed':
    case 'blocked': return 'var(--wb-danger)'
    case 'planned':
    case 'pending': return 'var(--wb-ink-faint)'
    default: return 'var(--wb-ink-faint)'
  }
}

function isTerminalStatus(status: string): boolean {
  return ['reviewed', 'awaiting_publish', 'published'].includes(status)
}

function useClickOutside(ref: React.RefObject<HTMLElement>, onOutside: () => void) {
  useEffect(() => {
    function handleClick(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        onOutside()
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [ref, onOutside])
}

function ChapterMenu({
  chapter,
  llmMode,
  isWorkflowRunning,
  onClose,
  onGenerateChapter,
  onGenerateNextFromChapter,
  onPublishChapter,
  onResetRunRecoveryForChapter,
  onOpenChapterView,
}: {
  chapter: Chapter
  llmMode: string
  isWorkflowRunning?: boolean
  onClose: () => void
  onGenerateChapter?: (chapterNumber: number) => void
  onGenerateNextFromChapter?: (chapterNumber: number) => void
  onPublishChapter?: (chapterNumber: number) => void
  onResetRunRecoveryForChapter?: (chapterNumber: number) => Promise<void> | void
  onOpenChapterView?: (chapterNumber: number, tab: 'content' | 'workflow' | 'artifacts' | 'history') => void
}) {
  const menuRef = useRef<HTMLDivElement>(null)
  useClickOutside(menuRef, onClose)

  const status = chapter.status
  const isTerminal = isTerminalStatus(status)
  const isReviewedReal = status === 'reviewed' && llmMode === 'real'
  const isPublished = status === 'published'
  const isAwaiting = status === 'awaiting_publish'
  const hasPreservedPlannedContent = status === 'planned' && chapter.word_count > 0
  const title = chapter.title || `第 ${chapter.chapter_number} 章`

  const handleViewContent = () => {
    onOpenChapterView?.(chapter.chapter_number, 'content')
    onClose()
  }

  const handleViewWorkflow = () => {
    onOpenChapterView?.(chapter.chapter_number, 'workflow')
    onClose()
  }

  const handleViewHistory = () => {
    onOpenChapterView?.(chapter.chapter_number, 'history')
    onClose()
  }

  const handleGenerate = () => {
    onGenerateChapter?.(chapter.chapter_number)
    onClose()
  }

  const handleGenerateNext = () => {
    onGenerateNextFromChapter?.(chapter.chapter_number)
    onClose()
  }

  const handlePublish = () => {
    onPublishChapter?.(chapter.chapter_number)
    onClose()
  }

  const handleCopyInfo = async () => {
    const info = `${title} — ${tChapterStatusLabel(status, isReviewedReal)} — ${chapter.word_count.toLocaleString()} 字`
    try {
      await navigator.clipboard.writeText(info)
    } catch {
      // ignore
    }
    onClose()
  }

  return (
    <div
      ref={menuRef}
      className="author-rail-dropdown"
      role="menu"
      aria-label={`${title} 操作菜单`}
      onKeyDown={(e) => {
        if (e.key === 'Escape') onClose()
      }}
    >
      <button className="author-rail-dropdown-item" role="menuitem" onClick={handleViewContent}>
        <FileText size={13} /> 查看正文
      </button>
      <button className="author-rail-dropdown-item" role="menuitem" onClick={handleViewWorkflow}>
        <Eye size={13} /> 查看工作流
      </button>
      <button className="author-rail-dropdown-item" role="menuitem" onClick={handleViewHistory}>
        <History size={13} /> 查看历史
      </button>
      <button className="author-rail-dropdown-item" role="menuitem" onClick={handleCopyInfo}>
        <Copy size={13} /> 复制章节信息
      </button>

      <div className="author-rail-dropdown-divider" />

      {/* Generation actions - conditionally shown */}
      {isWorkflowRunning && (
        <div className="author-rail-dropdown-hint">
          <Loader2 size={11} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} className="spin" />
          已有运行中工作流
        </div>
      )}

      {!isWorkflowRunning && isReviewedReal && onPublishChapter && (
        <button className="author-rail-dropdown-item" role="menuitem" onClick={handlePublish}>
          <CheckCircle2 size={13} /> 确认发布
        </button>
      )}

      {!isWorkflowRunning && isPublished && onGenerateNextFromChapter && (
        <button className="author-rail-dropdown-item" role="menuitem" onClick={handleGenerateNext}>
          <Sparkles size={13} /> 生成下一章
        </button>
      )}

      {!isWorkflowRunning && (status === 'blocking' || status === 'revision') && onResetRunRecoveryForChapter && (
        <button className="author-rail-dropdown-item" role="menuitem" onClick={() => { onResetRunRecoveryForChapter(chapter.chapter_number); onClose(); }}>
          <AlertCircle size={13} /> 清除阻塞并重置
        </button>
      )}

      {!isWorkflowRunning && hasPreservedPlannedContent && (
        <button className="author-rail-dropdown-item" role="menuitem" onClick={handleViewContent}>
          <FileText size={13} /> 查看正文后确认覆盖
        </button>
      )}

      {!isWorkflowRunning && !hasPreservedPlannedContent && !isTerminal && status !== 'blocking' && onGenerateChapter && (
        <button className="author-rail-dropdown-item" role="menuitem" onClick={handleGenerate}>
          <Play size={13} /> {status === 'planned' ? '生成本章' : '继续生成'}
        </button>
      )}

      {!isWorkflowRunning && isAwaiting && (
        <div className="author-rail-dropdown-hint">
          <AlertCircle size={11} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} />
          等待发布
        </div>
      )}
    </div>
  )
}

export default function AuthorChapterRail({
  chapters,
  currentChapter,
  llmMode,
  isChapterWorkflowRunning,
  onSelectChapter,
  onGenerateChapter,
  onGenerateNextFromChapter,
  onPublishChapter,
  onResetRunRecoveryForChapter,
  onOpenChapterView,
}: AuthorChapterRailProps) {
  const publishedCount = chapters.filter((c) => c.status === 'published').length
  const progress = chapters.length > 0 ? Math.round((publishedCount / chapters.length) * 100) : 0
  const [openMenuChapter, setOpenMenuChapter] = useState<number | null>(null)

  const handleSelect = useCallback((chapterNumber: number) => {
    setOpenMenuChapter(null)
    onSelectChapter(chapterNumber)
  }, [onSelectChapter])

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
          const menuOpen = openMenuChapter === ch.chapter_number
          const isWorkflowRunning = isChapterWorkflowRunning?.(ch.chapter_number) ?? false

          return (
            <div
              key={ch.chapter_number}
              role="button"
              tabIndex={0}
              className={`author-rail-item${isActive ? ' active' : ''}`}
              onClick={() => handleSelect(ch.chapter_number)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  handleSelect(ch.chapter_number)
                }
              }}
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
                <button
                  className="author-rail-menu-btn"
                  type="button"
                  aria-label={`第 ${ch.chapter_number} 章操作`}
                  onClick={(e) => {
                    e.stopPropagation()
                    setOpenMenuChapter(menuOpen ? null : ch.chapter_number)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      e.stopPropagation()
                      setOpenMenuChapter(menuOpen ? null : ch.chapter_number)
                    }
                  }}
                >
                  <MoreHorizontal size={16} />
                </button>
              </span>
              {menuOpen && (
                <ChapterMenu
                  chapter={ch}
                  llmMode={llmMode}
                  isWorkflowRunning={isWorkflowRunning}
                  onClose={() => setOpenMenuChapter(null)}
                  onGenerateChapter={onGenerateChapter}
                  onGenerateNextFromChapter={onGenerateNextFromChapter}
                  onPublishChapter={onPublishChapter}
                  onResetRunRecoveryForChapter={onResetRunRecoveryForChapter}
                  onOpenChapterView={onOpenChapterView}
                />
              )}
            </div>
          )
        })}
      </div>
    </aside>
  )
}
