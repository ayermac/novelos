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
    return <div className="chapter-diff-state">加载版本对比…</div>
  }

  if (error) {
    return (
      <div className="chapter-diff-state">
        <div className="chapter-diff-error">{error}</div>
        {onClose && <button className="chapter-diff-close" onClick={onClose}>关闭</button>}
      </div>
    )
  }

  if (!diff) return null

  return (
    <div className="chapter-diff-viewer">
      <div className="chapter-diff-header">
        <h4>
          版本对比：#{leftVersionId} → #{rightVersionId}
        </h4>
        <div className="chapter-diff-actions">
          <span className={diff.word_count_delta >= 0 ? 'chapter-diff-delta positive' : 'chapter-diff-delta negative'}>
            {diff.word_count_delta >= 0 ? '+' : ''}{diff.word_count_delta} 字
          </span>
          {onClose && (
            <button onClick={onClose} className="chapter-diff-close">
              关闭
            </button>
          )}
        </div>
      </div>

      {/* Changed blocks */}
      <div className="chapter-diff-blocks">
        {diff.changed_blocks.length === 0 ? (
          <div className="chapter-diff-empty">两个版本内容完全相同</div>
        ) : (
          diff.changed_blocks.map((block, idx) => (
            <div key={idx} className="chapter-diff-block">
              {block.type === 'removed' && block.lines && (
                <div className="chapter-diff-line removed">
                  {block.lines.join('')}
                </div>
              )}
              {block.type === 'added' && block.lines && (
                <div className="chapter-diff-line added">
                  {block.lines.join('')}
                </div>
              )}
              {block.type === 'changed' && (
                <>
                  {block.removed_lines && (
                    <div className="chapter-diff-line removed changed">
                      {block.removed_lines.join('')}
                    </div>
                  )}
                  {block.added_lines && (
                    <div className="chapter-diff-line added">
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
