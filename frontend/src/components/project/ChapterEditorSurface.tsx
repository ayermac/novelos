import { useCallback, useEffect, useRef, useState } from 'react'
import { Check, Edit3, Loader2, Maximize2, Minimize2, Save, Sparkles, X } from 'lucide-react'
import { get, post, type EditorState, type LocalRevisionResult } from '../../lib/api'
import { tVersionSource, tRevisionMode } from '../../lib/state-labels'

interface Props {
  projectId: string
  chapterNumber: number
  onContentSaved?: () => void
  initialContent?: string
  initialWordCount?: number
  initialStatus?: string
  initialVersionLabel?: string
}

type ViewMode = 'read' | 'edit' | 'diff' | 'revision'

function getEditorFallbackMessage(error: string): string {
  if (error.includes('HTTP_404') || error.includes('404') || error.includes('Not Found')) {
    return '当前 API 服务未启用编辑器接口，已切换为只读正文视图。重启后端或启用版本接口后可恢复编辑。'
  }
  return '编辑接口暂时不可用，已切换为只读正文视图。'
}

export default function ChapterEditorSurface({
  projectId,
  chapterNumber,
  onContentSaved,
  initialContent,
  initialWordCount,
  initialStatus,
  initialVersionLabel,
}: Props) {
  const [editorState, setEditorState] = useState<EditorState | null>(null)
  const [loading, setLoading] = useState(true)
  const [editContent, setEditContent] = useState('')
  const [viewMode, setViewMode] = useState<ViewMode>('read')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [fullscreen, setFullscreen] = useState(false)

  // Local revision state
  const [selectedText, setSelectedText] = useState('')
  const [selectionStart, setSelectionStart] = useState(0)
  const [selectionEnd, setSelectionEnd] = useState(0)
  const [revisionInstruction, setRevisionInstruction] = useState('')
  const [revisionMode, setRevisionMode] = useState<string>('polish')
  const [revisionResult, setRevisionResult] = useState<LocalRevisionResult | null>(null)
  const [revisionLoading, setRevisionLoading] = useState(false)

  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const hasUnsavedChanges = viewMode === 'edit' && editContent !== (editorState?.content || '')

  // Load editor state
  const loadEditor = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const resp = await get<EditorState>(`/projects/${projectId}/chapters/${chapterNumber}/editor`)
      if (resp.ok && resp.data) {
        setEditorState(resp.data)
        setEditContent(resp.data.content || '')
      } else {
        setError(`${resp.error?.code || 'EDITOR_UNAVAILABLE'}: ${resp.error?.message || '编辑器接口不可用'}`)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '网络异常，加载编辑器失败'
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [projectId, chapterNumber])

  useEffect(() => { loadEditor() }, [loadEditor])

  useEffect(() => {
    if (!fullscreen) return
    const previousOverflow = document.body.style.overflow
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setFullscreen(false)
    }
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [fullscreen])

  // Save content
  const handleSave = useCallback(async () => {
    if (!editorState || saving) return
    setSaving(true)
    setError('')
    try {
      const resp = await post(`/projects/${projectId}/chapters/${chapterNumber}/content`, {
        content: editContent,
        summary: '人工编辑保存',
        base_version_id: editorState.current_version_id,
      })
      if (resp.ok) {
        setViewMode('read')
        await loadEditor()
        onContentSaved?.()
      } else {
        setError(resp.error?.message || '保存失败')
      }
    } catch {
      setError('网络异常，保存失败')
    } finally {
      setSaving(false)
    }
  }, [projectId, chapterNumber, editContent, editorState, saving, loadEditor, onContentSaved])

  // Create revision draft for published chapters
  const handleCreateRevisionDraft = useCallback(async () => {
    if (saving) return
    setSaving(true)
    setError('')
    try {
      const resp = await post(`/projects/${projectId}/chapters/${chapterNumber}/revision-draft`, {
        confirm: true,
      })
      if (resp.ok) {
        await loadEditor()
        onContentSaved?.()
      } else {
        setError(resp.error?.message || '创建修订版失败')
      }
    } catch {
      setError('网络异常，创建修订版失败')
    } finally {
      setSaving(false)
    }
  }, [projectId, chapterNumber, saving, loadEditor, onContentSaved])

  // Handle text selection for local revision
  const handleTextSelect = useCallback(() => {
    const ta = textareaRef.current
    if (!ta) return
    const start = ta.selectionStart
    const end = ta.selectionEnd
    if (start !== end) {
      setSelectedText(ta.value.substring(start, end))
      setSelectionStart(start)
      setSelectionEnd(end)
    } else {
      setSelectedText('')
    }
  }, [])

  // Submit local revision
  const handleSubmitRevision = useCallback(async () => {
    if (!selectedText || revisionLoading) return
    setRevisionLoading(true)
    setError('')
    try {
      const resp = await post<LocalRevisionResult>(
        `/projects/${projectId}/chapters/${chapterNumber}/local-revision`,
        {
          selected_text: selectedText,
          selection_start: selectionStart,
          selection_end: selectionEnd,
          instruction: revisionInstruction || undefined,
          mode: revisionMode,
        },
      )
      if (resp.ok && resp.data) {
        setRevisionResult(resp.data)
      } else {
        setError(resp.error?.message || '局部返修失败')
      }
    } catch {
      setError('网络异常，局部返修失败')
    } finally {
      setRevisionLoading(false)
    }
  }, [projectId, chapterNumber, selectedText, selectionStart, selectionEnd, revisionInstruction, revisionMode, revisionLoading])

  // Accept local revision
  const handleAcceptRevision = useCallback(() => {
    if (!revisionResult) return
    const before = editContent.substring(0, revisionResult.selection_start)
    const after = editContent.substring(revisionResult.selection_end)
    setEditContent(before + revisionResult.replacement_text + after)
    setRevisionResult(null)
    setSelectedText('')
    setRevisionInstruction('')
  }, [revisionResult, editContent])

  // Reject local revision
  const handleRejectRevision = useCallback(() => {
    setRevisionResult(null)
  }, [])

  if (loading) {
    return <div className="chapter-editor-loading">加载中...</div>
  }

  if (!editorState) {
    if (initialContent) {
      return (
        <div className={`chapter-editor-surface${fullscreen ? ' chapter-editor-surface--fullscreen' : ''}`}>
          <div className="chapter-editor-toolbar">
            <button
              type="button"
              className="chapter-editor-action chapter-editor-action-secondary"
              onClick={() => setFullscreen((value) => !value)}
              aria-pressed={fullscreen}
            >
              {fullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
              {fullscreen ? '退出全屏' : '全屏'}
            </button>
            <span className="chapter-editor-meta">
              {initialWordCount?.toLocaleString() ?? '—'} 字 · {initialStatus || 'readonly'}
            </span>
          </div>
          <div className="chapter-editor-readonly-note">{getEditorFallbackMessage(error)}</div>
          <div className="chapter-editor-read">{initialContent}</div>
          {initialVersionLabel && <div className="chapter-editor-version">{initialVersionLabel}</div>}
        </div>
      )
    }
    return <div className="chapter-editor-error">{error || '无法加载编辑器'}</div>
  }

  const isPublished = editorState.status === 'published' || editorState.status === 'awaiting_publish'

  return (
    <div className={`chapter-editor-surface${fullscreen ? ' chapter-editor-surface--fullscreen' : ''}`}>
      {/* Toolbar */}
      <div className="chapter-editor-toolbar">
        {isPublished ? (
          <button
            className="chapter-editor-action chapter-editor-action-primary"
            onClick={handleCreateRevisionDraft}
            disabled={saving}
          >
            {saving ? <Loader2 size={13} className="spin" /> : <Edit3 size={13} />}
            {saving ? '处理中...' : '创建修订版'}
          </button>
        ) : viewMode === 'read' ? (
          <button
            className="chapter-editor-action chapter-editor-action-primary"
            onClick={() => { setEditContent(editorState.content || ''); setViewMode('edit') }}
            disabled={!editorState.editable}
          >
            <Edit3 size={13} />
            编辑
          </button>
        ) : viewMode === 'edit' ? (
          <>
            <button
              className="chapter-editor-action chapter-editor-action-primary"
              onClick={handleSave}
              disabled={saving || !hasUnsavedChanges}
            >
              {saving ? <Loader2 size={13} className="spin" /> : <Save size={13} />}
              {saving ? '保存中...' : '保存'}
            </button>
            <button
              className="chapter-editor-action chapter-editor-action-secondary"
              onClick={() => { setEditContent(editorState.content || ''); setViewMode('read'); setRevisionResult(null) }}
              disabled={saving}
            >
              <X size={13} />
              放弃修改
            </button>
          </>
        ) : null}

        <button
          type="button"
          className="chapter-editor-action chapter-editor-action-secondary"
          onClick={() => setFullscreen((value) => !value)}
          aria-pressed={fullscreen}
        >
          {fullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
          {fullscreen ? '退出全屏' : '全屏'}
        </button>

        <span className="chapter-editor-meta">
          {editorState.word_count} 字 · {editorState.status}
          {editorState.edit_restriction && <span>{editorState.edit_restriction}</span>}
        </span>
      </div>

      {/* Unsaved indicator */}
      {hasUnsavedChanges && (
        <div className="chapter-editor-unsaved">
          有未保存的修改
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="chapter-editor-error">
          {error}
        </div>
      )}

      {/* Content area */}
      {viewMode === 'edit' ? (
        <div className="chapter-editor-editing">
          <textarea
            ref={textareaRef}
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            onSelect={handleTextSelect}
            onMouseUp={handleTextSelect}
            onKeyUp={handleTextSelect}
            className="chapter-editor-textarea"
          />

          {/* Local revision panel */}
          {selectedText && !revisionResult && (
            <div className="chapter-revision-panel">
              <div className="chapter-revision-title">局部返修</div>
              <div className="chapter-revision-subtitle">
                已选中 {selectedText.length} 字
              </div>
              <div className="chapter-revision-modes">
                {['rewrite', 'polish', 'shorten', 'expand', 'tone'].map(mode => (
                  <button
                    key={mode}
                    onClick={() => setRevisionMode(mode)}
                    className={`chapter-revision-mode${revisionMode === mode ? ' active' : ''}`}
                  >
                    {tRevisionMode(mode)}
                  </button>
                ))}
              </div>
              <input
                type="text"
                value={revisionInstruction}
                onChange={(e) => setRevisionInstruction(e.target.value)}
                placeholder="输入返修要求（可选）"
                className="chapter-revision-input"
              />
              <button
                className="chapter-editor-action chapter-editor-action-primary"
                onClick={handleSubmitRevision}
                disabled={revisionLoading}
              >
                {revisionLoading ? <Loader2 size={13} className="spin" /> : <Sparkles size={13} />}
                {revisionLoading ? 'AI 处理中...' : '提交返修'}
              </button>
            </div>
          )}

          {/* Revision result preview */}
          {revisionResult && (
            <div className="chapter-revision-result">
              <div className="chapter-revision-title">AI 返修结果（{tRevisionMode(revisionResult.mode)}）</div>
              <div className="chapter-revision-copy">
                {revisionResult.replacement_text}
              </div>
              {revisionResult.change_summary && (
                <div className="chapter-revision-subtitle">{revisionResult.change_summary}</div>
              )}
              {revisionResult.risk_notes.length > 0 && (
                <div className="chapter-revision-warning">
                  注意：{revisionResult.risk_notes.join('；')}
                </div>
              )}
              <div className="chapter-revision-actions">
                <button className="chapter-editor-action chapter-editor-action-primary" onClick={handleAcceptRevision}>
                  <Check size={13} />
                  接受替换
                </button>
                <button className="chapter-editor-action chapter-editor-action-secondary" onClick={handleRejectRevision}>
                  <X size={13} />
                  放弃
                </button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="chapter-editor-read">
          {editorState.content || <span className="chapter-editor-placeholder">暂无正文</span>}
        </div>
      )}

      {/* Version info */}
      {editorState.current_version_id && (
        <div className="chapter-editor-version">
          当前版本 #{editorState.current_version_id}
          {editorState.recent_versions.length > 0 && ` · ${tVersionSource(editorState.recent_versions[0]?.source)}`}
        </div>
      )}
    </div>
  )
}
