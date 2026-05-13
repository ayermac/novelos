import { useCallback, useEffect, useState } from 'react'
import { get, type VersionDiff } from '../../lib/api'

interface Props {
  projectId: string
  chapterNumber: number
  leftVersionId: number
  rightVersionId: number
  onClose?: () => void
}

export default function ChapterDiffViewer({ projectId, chapterNumber, leftVersionId, rightVersionId, onClose }: Props) {
  const [diff, setDiff] = useState<VersionDiff | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadDiff = useCallback(async () => {
    setLoading(true)
    setError('')
    const resp = await get<VersionDiff>(
      `/projects/${projectId}/chapters/${chapterNumber}/versions/${leftVersionId}/diff/${rightVersionId}`,
    )
    if (resp.ok && resp.data) {
      setDiff(resp.data)
    } else {
      setError(resp.error?.message || '获取版本对比失败')
    }
    setLoading(false)
  }, [projectId, chapterNumber, leftVersionId, rightVersionId])

  useEffect(() => { loadDiff() }, [loadDiff])

  if (loading) {
    return <div style={{ padding: 16, color: '#888' }}>加载版本对比…</div>
  }

  if (error) {
    return (
      <div style={{ padding: 16 }}>
        <div style={{ color: '#c62828', marginBottom: 8 }}>{error}</div>
        {onClose && <button onClick={onClose}>关闭</button>}
      </div>
    )
  }

  if (!diff) return null

  return (
    <div className="chapter-diff-viewer" style={{ padding: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h4 style={{ margin: 0 }}>
          版本对比：#{leftVersionId} → #{rightVersionId}
        </h4>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: diff.word_count_delta >= 0 ? '#2e7d32' : '#c62828' }}>
            {diff.word_count_delta >= 0 ? '+' : ''}{diff.word_count_delta} 字
          </span>
          {onClose && (
            <button onClick={onClose} style={{ border: 'none', background: '#f5f5f5', borderRadius: 4, padding: '4px 10px', cursor: 'pointer' }}>
              关闭
            </button>
          )}
        </div>
      </div>

      {/* Changed blocks */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {diff.changed_blocks.length === 0 ? (
          <div style={{ color: '#aaa', fontSize: 14 }}>两个版本内容完全相同</div>
        ) : (
          diff.changed_blocks.map((block, idx) => (
            <div key={idx} style={{ borderRadius: 4, overflow: 'hidden' }}>
              {block.type === 'removed' && block.lines && (
                <div style={{ background: '#fdecea', padding: '4px 8px', whiteSpace: 'pre-wrap', fontSize: 14, lineHeight: 1.6 }}>
                  {block.lines.join('')}
                </div>
              )}
              {block.type === 'added' && block.lines && (
                <div style={{ background: '#e8f5e9', padding: '4px 8px', whiteSpace: 'pre-wrap', fontSize: 14, lineHeight: 1.6 }}>
                  {block.lines.join('')}
                </div>
              )}
              {block.type === 'changed' && (
                <>
                  {block.removed_lines && (
                    <div style={{ background: '#fdecea', padding: '4px 8px', whiteSpace: 'pre-wrap', fontSize: 14, lineHeight: 1.6, textDecoration: 'line-through', opacity: 0.7 }}>
                      {block.removed_lines.join('')}
                    </div>
                  )}
                  {block.added_lines && (
                    <div style={{ background: '#e8f5e9', padding: '4px 8px', whiteSpace: 'pre-wrap', fontSize: 14, lineHeight: 1.6 }}>
                      {block.added_lines.join('')}
                    </div>
                  )}
                </>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
