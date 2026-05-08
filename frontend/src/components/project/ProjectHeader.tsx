import { useState, useRef, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Download, FileText, BookOpen } from 'lucide-react'

interface ProjectHeaderProps {
  projectId: string
  projectName: string
  currentChapter: number
  publishedCount: number
  isStub: boolean
}

export default function ProjectHeader({
  projectId,
  projectName,
  currentChapter,
  publishedCount,
  isStub,
}: ProjectHeaderProps) {
  const [showExport, setShowExport] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!showExport) return
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setShowExport(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [showExport])

  const handleExport = (format: 'txt' | 'markdown') => {
    const a = document.createElement('a')
    a.href = `/api/projects/${projectId}/export?format=${format}`
    a.download = ''
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setShowExport(false)
  }

  return (
    <header className="project-header">
      <div className="project-header-main">
        <Link to="/projects" className="project-header-back">
          返回项目列表
        </Link>
        <div className="project-header-title">
          <h1>{projectName}</h1>
          <div className="project-header-meta">
            <span>第 {currentChapter} 章</span>
            <span>已发布 {publishedCount} 章</span>
          </div>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div ref={menuRef} style={{ position: 'relative' }}>
          <button
            type="button"
            onClick={() => setShowExport(!showExport)}
            style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '5px 10px', border: '1px solid rgba(15,118,110,0.15)', borderRadius: 7, background: '#fff', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 12 }}
          >
            <Download size={13} /> 导出
          </button>
          {showExport && (
            <div style={{ position: 'absolute', top: '100%', right: 0, marginTop: 4, background: '#fff', border: '1px solid rgba(15,118,110,0.12)', borderRadius: 8, boxShadow: '0 4px 12px rgba(0,0,0,0.08)', zIndex: 100, minWidth: 140 }}>
              <button
                type="button"
                onClick={() => handleExport('txt')}
                style={{ display: 'flex', alignItems: 'center', gap: 6, width: '100%', padding: '8px 12px', border: 'none', background: 'none', cursor: 'pointer', fontSize: 13, color: 'var(--text-primary)', textAlign: 'left' }}
                onMouseEnter={(e) => { e.currentTarget.style.background = '#f0fdfa' }}
                onMouseLeave={(e) => { e.currentTarget.style.background = 'none' }}
              >
                <FileText size={14} /> 纯文本 (.txt)
              </button>
              <button
                type="button"
                onClick={() => handleExport('markdown')}
                style={{ display: 'flex', alignItems: 'center', gap: 6, width: '100%', padding: '8px 12px', border: 'none', background: 'none', cursor: 'pointer', fontSize: 13, color: 'var(--text-primary)', textAlign: 'left' }}
                onMouseEnter={(e) => { e.currentTarget.style.background = '#f0fdfa' }}
                onMouseLeave={(e) => { e.currentTarget.style.background = 'none' }}
              >
                <BookOpen size={14} /> Markdown (.md)
              </button>
            </div>
          )}
        </div>
        <span className={`status-badge ${isStub ? 'status-stub' : 'status-real'}`}>
          {isStub ? '演示模式' : '真实 LLM'}
        </span>
      </div>
    </header>
  )
}
