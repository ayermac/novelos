import { useCallback, useEffect, useState } from 'react'
import { get, post, type VersionSummary, type VersionDetail } from '../../lib/api'
import { tVersionSource } from '../../lib/state-labels'
import { useAppDialog } from '../AppDialogContext'

interface Props {
  projectId: string
  chapterNumber: number
  onRestore?: () => void
  onViewDiff?: (leftId: number, rightId: number) => void
}

export default function ChapterVersionPanel({ projectId, chapterNumber, onRestore, onViewDiff }: Props) {
  const [versions, setVersions] = useState<VersionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [detailVersion, setDetailVersion] = useState<VersionDetail | null>(null)
  const [restoring, setRestoring] = useState(false)
  const [error, setError] = useState('')
  const dialog = useAppDialog()

  const loadVersions = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const resp = await get<{ project_id: string; chapter_number: number; current_version_id: number | null; versions: VersionSummary[] }>(
        `/projects/${projectId}/chapters/${chapterNumber}/versions`,
      )
      if (resp.ok && resp.data) {
        setVersions(resp.data.versions)
      } else {
        setError(resp.error?.message || '加载版本列表失败')
      }
    } catch {
      setError('网络异常，加载版本列表失败')
    } finally {
      setLoading(false)
    }
  }, [projectId, chapterNumber])

  useEffect(() => { loadVersions() }, [loadVersions])

  const handleViewDetail = useCallback(async (versionId: number) => {
    setError('')
    try {
      const resp = await get<VersionDetail>(
        `/projects/${projectId}/chapters/${chapterNumber}/versions/${versionId}`,
      )
      if (resp.ok && resp.data) {
        setDetailVersion(resp.data)
      } else {
        setError(resp.error?.message || '加载版本详情失败')
      }
    } catch {
      setError('网络异常，加载版本详情失败')
    }
  }, [projectId, chapterNumber])

  const handleRestore = useCallback(async (versionId: number) => {
    if (restoring) return
    const confirmed = await dialog.confirm({
      title: '确认回滚',
      message: '确认回滚到此版本？当前正文将被替换，历史版本不会丢失。',
      tone: 'warning',
      confirmLabel: '确认回滚',
    })
    if (!confirmed) return

    setRestoring(true)
    setError('')
    try {
      const resp = await post(
        `/projects/${projectId}/chapters/${chapterNumber}/versions/${versionId}/restore`,
        { confirm: true },
      )
      if (resp.ok) {
        setDetailVersion(null)
        await loadVersions()
        onRestore?.()
      } else {
        await dialog.alert({
          title: '回滚失败',
          message: resp.error?.message || '回滚版本失败，请重试',
          tone: 'danger',
        })
      }
    } catch {
      await dialog.alert({
        title: '回滚失败',
        message: '网络异常，请重试',
        tone: 'danger',
      })
    } finally {
      setRestoring(false)
    }
  }, [projectId, chapterNumber, restoring, loadVersions, onRestore, dialog])

  const handleDiffWithCurrent = useCallback((versionId: number) => {
    if (versions.length > 0) {
      const currentVid = versions.find(v => v.is_current)?.version_id
      if (currentVid && currentVid !== versionId) {
        onViewDiff?.(versionId, currentVid)
      }
    }
  }, [versions, onViewDiff])

  if (loading) {
    return <div className="chapter-version-loading">加载版本列表…</div>
  }

  return (
    <div className="chapter-version-panel">
      <h4 className="chapter-version-title">版本历史</h4>

      {error && (
        <div className="chapter-version-error">
          {error}
        </div>
      )}

      {versions.length === 0 ? (
        <div className="chapter-version-empty">暂无版本记录</div>
      ) : (
        <div className="version-list">
          {versions.map(v => (
            <div
              key={v.version_id}
              className={`version-item ${v.is_current ? 'current' : ''}`}
            >
              <div className="version-item-header">
                <div>
                  <span className="version-number">V{v.version}</span>
                  <span className="version-source">{tVersionSource(v.source)}</span>
                  {v.is_current && <span className="version-current-badge">当前</span>}
                </div>
                <span className="version-word-count">{v.word_count} 字</span>
              </div>
              {v.summary && <div className="version-summary">{v.summary}</div>}
              <div className="version-time">{v.created_at}</div>
              <div className="version-actions">
                <button
                  className="btn btn-sm btn-secondary"
                  onClick={() => handleViewDetail(v.version_id)}
                >
                  查看
                </button>
                {!v.is_current && (
                  <>
                    <button
                      className="btn btn-sm btn-secondary"
                      onClick={() => handleDiffWithCurrent(v.version_id)}
                    >
                      对比
                    </button>
                    <button
                      className="btn btn-sm btn-danger"
                      onClick={() => handleRestore(v.version_id)}
                      disabled={restoring}
                    >
                      {restoring ? '回滚中…' : '回滚'}
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Version detail modal/panel */}
      {detailVersion && (
        <div className="version-detail-panel">
          <div className="version-detail-header">
            <span>版本 #{detailVersion.version_id} 详情</span>
            <button className="version-detail-close" onClick={() => setDetailVersion(null)}>✕</button>
          </div>
          <div className="version-detail-meta">
            {tVersionSource(detailVersion.source)} · {detailVersion.word_count} 字 · {detailVersion.created_at}
          </div>
          <div className="version-detail-content">
            {detailVersion.content}
          </div>
        </div>
      )}
    </div>
  )
}
