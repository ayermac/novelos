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
    return <div style={{ padding: 16, color: '#888' }}>加载版本列表…</div>
  }

  return (
    <div className="chapter-version-panel">
      <h4 style={{ margin: '0 0 12px 0' }}>版本历史</h4>

      {error && (
        <div style={{ padding: '8px 12px', background: '#fdecea', color: '#c62828', borderRadius: 4, marginBottom: 8, fontSize: 14 }}>
          {error}
        </div>
      )}

      {versions.length === 0 ? (
        <div style={{ color: '#aaa', fontSize: 14 }}>暂无版本记录</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {versions.map(v => (
            <div
              key={v.version_id}
              style={{
                padding: '8px 12px',
                border: `1px solid ${v.is_current ? '#1a73e8' : '#e0e0e0'}`,
                borderRadius: 4,
                background: v.is_current ? '#e8f0fe' : '#fff',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <span style={{ fontWeight: 600 }}>V{v.version}</span>
                  <span style={{ marginLeft: 8, fontSize: 13, color: '#1a73e8' }}>{tVersionSource(v.source)}</span>
                  {v.is_current && <span style={{ marginLeft: 8, fontSize: 12, color: '#1a73e8' }}>当前</span>}
                </div>
                <span style={{ fontSize: 12, color: '#999' }}>{v.word_count} 字</span>
              </div>
              {v.summary && <div style={{ fontSize: 13, color: '#666', marginTop: 4 }}>{v.summary}</div>}
              <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>{v.created_at}</div>
              <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                <button
                  onClick={() => handleViewDetail(v.version_id)}
                  style={{ padding: '2px 8px', fontSize: 12, border: '1px solid #ddd', borderRadius: 3, background: '#fff', cursor: 'pointer' }}
                >
                  查看
                </button>
                {!v.is_current && (
                  <>
                    <button
                      onClick={() => handleDiffWithCurrent(v.version_id)}
                      style={{ padding: '2px 8px', fontSize: 12, border: '1px solid #ddd', borderRadius: 3, background: '#fff', cursor: 'pointer' }}
                    >
                      对比
                    </button>
                    <button
                      onClick={() => handleRestore(v.version_id)}
                      disabled={restoring}
                      style={{ padding: '2px 8px', fontSize: 12, border: '1px solid #e65100', borderRadius: 3, background: '#fff', color: '#e65100', cursor: restoring ? 'wait' : 'pointer' }}
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
        <div style={{ marginTop: 16, padding: 12, background: '#f5f5f5', borderRadius: 4, border: '1px solid #e0e0e0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ fontWeight: 600 }}>版本 #{detailVersion.version_id} 详情</span>
            <button onClick={() => setDetailVersion(null)} style={{ border: 'none', background: 'none', cursor: 'pointer', fontSize: 16 }}>✕</button>
          </div>
          <div style={{ fontSize: 13, color: '#666', marginBottom: 8 }}>
            {tVersionSource(detailVersion.source)} · {detailVersion.word_count} 字 · {detailVersion.created_at}
          </div>
          <div style={{ whiteSpace: 'pre-wrap', fontSize: 14, lineHeight: 1.8, maxHeight: 400, overflow: 'auto', background: '#fff', padding: 8, borderRadius: 4 }}>
            {detailVersion.content}
          </div>
        </div>
      )}
    </div>
  )
}
