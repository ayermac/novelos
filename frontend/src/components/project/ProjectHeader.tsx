import { useState, useRef, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Activity, Download, FileText, BookOpen, ChevronDown, Copy, Check } from 'lucide-react'
import { apiUrl } from '../../lib/api'

interface ProjectHeaderProps {
  projectId: string
  projectName: string
  isStub: boolean
}

export default function ProjectHeader({
  projectId,
  projectName,
  isStub,
}: ProjectHeaderProps) {
  const [showExport, setShowExport] = useState(false)
  const [copiedProjectId, setCopiedProjectId] = useState(false)
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
    a.href = apiUrl(`/projects/${projectId}/export?format=${format}`)
    a.download = ''
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setShowExport(false)
  }

  const handleCopyProjectId = async () => {
    try {
      await navigator.clipboard?.writeText(projectId)
      setCopiedProjectId(true)
      window.setTimeout(() => setCopiedProjectId(false), 1600)
    } catch {
      setCopiedProjectId(false)
    }
  }

  return (
    <header className="project-header">
      <div className="project-header-main">
        <div className="project-console-lockup">
          <span className="project-console-title">生产控制台</span>
          <span className="project-console-subtitle">Auto-Run Resilience</span>
        </div>
        <div className="project-header-title">
          <h1>{projectName}</h1>
          <div className="project-header-meta">
            <span className="project-id-chip" title={`project_id: ${projectId}`}>
              <span className="project-id-chip-label">ID</span>
              <code>{projectId}</code>
              <button
                type="button"
                className="project-id-copy"
                onClick={handleCopyProjectId}
                aria-label="复制项目 ID"
                title={copiedProjectId ? '已复制' : '复制项目 ID'}
              >
                {copiedProjectId ? <Check size={12} /> : <Copy size={12} />}
              </button>
            </span>
          </div>
        </div>
      </div>
      <div className="project-header-actions">
        <Link to="/projects" className="project-header-back">
          返回项目列表
        </Link>
        <span className="badge badge-neutral project-header-runtime">
          <Activity size={13} />
          工厂在线
        </span>
        <div ref={menuRef} style={{ position: 'relative' }}>
          <button
            type="button"
            onClick={() => setShowExport(!showExport)}
            className="project-export-button"
          >
            <Download size={13} /> 导出 <ChevronDown size={12} />
          </button>
          {showExport && (
            <div className="project-export-menu">
              <button
                type="button"
                onClick={() => handleExport('txt')}
                className="project-export-menu-item"
              >
                <FileText size={14} /> 纯文本 (.txt)
              </button>
              <button
                type="button"
                onClick={() => handleExport('markdown')}
                className="project-export-menu-item"
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
