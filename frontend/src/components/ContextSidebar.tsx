import { tChapterStatusLabel, tWorkflowStatus } from '../lib/i18n'
import { post } from '../lib/api'
import { useState } from 'react'

interface Chapter {
  chapter_number: number
  status: string
  word_count: number
  quality_score?: number
  title?: string
}

interface Run {
  run_id: string
  chapter_number: number
  status: string
  created_at: string
  error_message?: string
}

interface Props {
  currentChapter: Chapter | null
  chapterNumber: number
  llmMode: string
  recentRuns: Run[]
  totalChapters: number
  projectId: string
  onGenerate: () => void
  onViewWorkflow: (runId: string) => void
  onViewContent: () => void
  onGenerateNext: () => void
  onNavigateToRun: () => void
  onPublish: () => void
}

export default function ContextSidebar({
  currentChapter,
  chapterNumber,
  llmMode,
  recentRuns,
  totalChapters,
  projectId,
  onGenerate,
  onViewWorkflow,
  onViewContent,
  onGenerateNext,
  onNavigateToRun,
  onPublish,
}: Props) {
  const isStub = llmMode === 'stub'
  const hasContent = (currentChapter?.word_count || 0) > 0
  const isPublished = currentChapter?.status === 'published'
  const isReviewed = currentChapter?.status === 'reviewed'
  const isAwaitingPublish = isReviewed && !isStub  // v5.3.0: Real mode reviewed = awaiting publish
  const latestRun = recentRuns.length > 0 ? recentRuns[0] : null
  const latestRunFailed = latestRun !== null && (latestRun.status === 'failed' || latestRun.status === 'blocked')
  const [publishing, setPublishing] = useState(false)

  let nextTitle = ''
  let nextHint = ''
  let nextAction: { label: string; onClick: () => void } | null = null

  if (currentChapter?.status === 'blocking' || latestRun?.status === 'blocked') {
    nextTitle = '章节已阻塞'
    nextHint = '需要人工检查状态后重新运行。'
    nextAction = { label: '重新生成本章', onClick: onGenerate }
  } else if (latestRunFailed) {
    nextTitle = '最近运行失败'
    nextHint = '建议检查后重试。'
    nextAction = { label: '重新生成本章', onClick: onGenerate }
  } else if (isAwaitingPublish) {
    nextTitle = '待人工发布'
    nextHint = 'AI 审核已通过，请确认发布。'
    nextAction = { label: '确认发布', onClick: () => handlePublish() }
  } else if (!hasContent) {
    nextTitle = '本章尚未生成'
    nextHint = '点击下方按钮开始生成。'
    nextAction = { label: '生成本章', onClick: onGenerate }
  } else if (isPublished && chapterNumber < totalChapters) {
    nextTitle = '继续创作'
    nextHint = `下一章：第 ${chapterNumber + 1} 章`
    nextAction = { label: '生成下一章', onClick: onGenerateNext }
  } else {
    nextTitle = '继续创作'
    nextHint = '返回创作流程'
    nextAction = { label: '生成本章', onClick: onGenerate }
  }

  const handlePublish = async () => {
    setPublishing(true)
    const res = await post('/publish/chapter', {
      project_id: projectId,
      chapter: chapterNumber,
    })
    if (res.ok) {
      onPublish()
    } else {
      alert(res.error?.message || '发布失败')
    }
    setPublishing(false)
  }

  return (
    <div className="ctx-sidebar">
      {/* Mode indicator */}
      <div className={`ctx-mode-badge ${isStub ? 'ctx-stub' : 'ctx-real'}`}>
        {isStub ? '演示模式' : '真实 LLM'}
        <div className="ctx-mode-hint">
          {isStub
            ? '内容由本地 Stub 模板生成，速度快但不代表真实创作质量'
            : '调用真实 LLM API 生成内容'}
        </div>
      </div>

      {/* Next action */}
      <div className="ctx-section">
        <div className="ctx-section-title">下一步建议</div>
        <div className="ctx-next-title">{nextTitle}</div>
        <div className="ctx-next-hint">{nextHint}</div>
        {nextAction && (
          <button className="btn btn-primary" style={{ width: '100%', marginTop: '8px' }} onClick={nextAction.onClick}>
            {nextAction.label}
          </button>
        )}
      </div>

      {/* Current chapter status */}
      <div className="ctx-section">
        <div className="ctx-section-title">当前章节</div>
        <div className="ctx-stat-row">
          <span className="ctx-stat-label">章节</span>
          <span className="ctx-stat-value">第 {chapterNumber} 章</span>
        </div>
        <div className="ctx-stat-row">
          <span className="ctx-stat-label">状态</span>
          <span className="ctx-stat-value">
            {currentChapter ? tChapterStatusLabel(currentChapter.status, isAwaitingPublish) : '未知'}
          </span>
        </div>
        <div className="ctx-stat-row">
          <span className="ctx-stat-label">字数</span>
          <span className="ctx-stat-value">
            {(currentChapter?.word_count || 0).toLocaleString()}
          </span>
        </div>
        {currentChapter?.quality_score != null && (
          <div className="ctx-stat-row">
            <span className="ctx-stat-label">质量分</span>
            <span className="ctx-stat-value">{currentChapter.quality_score}</span>
          </div>
        )}
        <div className="ctx-stat-row">
          <span className="ctx-stat-label">来源</span>
          <span className="ctx-stat-value">{isStub ? '演示' : '真实'}</span>
        </div>
      </div>

      {/* Generate actions */}
      <div className="ctx-section">
        <div className="ctx-section-title">操作</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {isAwaitingPublish && (
            <button className="btn btn-primary" style={{ width: '100%' }} onClick={() => handlePublish()} disabled={publishing}>
              {publishing ? '发布中...' : '确认发布'}
            </button>
          )}
          {!hasContent && !isAwaitingPublish && (
            <button className="btn btn-primary" style={{ width: '100%' }} onClick={onGenerate}>
              生成本章
            </button>
          )}
          {hasContent && (
            <button className="btn btn-secondary" style={{ width: '100%' }} onClick={onViewContent}>
              查看正文
            </button>
          )}
          {latestRun && (
            <button
              className="btn btn-secondary"
              style={{ width: '100%' }}
              onClick={() => onViewWorkflow(latestRun.run_id)}
            >
              查看工作流
            </button>
          )}
          {isPublished && chapterNumber < totalChapters && (
            <button className="btn btn-secondary" style={{ width: '100%' }} onClick={onGenerateNext}>
              生成下一章
            </button>
          )}
          <button className="btn btn-secondary" style={{ width: '100%' }} onClick={onNavigateToRun}>
            高级运行
          </button>
        </div>
      </div>

      {/* Recent run status */}
      {latestRun && (
        <div className="ctx-section">
          <div className="ctx-section-title">最近运行</div>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            <span className={`status-badge status-${latestRun.status}`}>
              {tWorkflowStatus(latestRun.status)}
            </span>
            <div style={{ marginTop: '4px', fontSize: '12px', color: 'var(--text-muted)' }}>
              {latestRun.created_at || ''}
            </div>
          </div>
        </div>
      )}

      <style>{`
        .ctx-sidebar {
          padding: 12px;
          height: 100%;
          overflow-y: auto;
          background: var(--bg-primary);
          border-left: 1px solid var(--border-color);
        }
        .ctx-mode-badge {
          padding: 10px 12px;
          border-radius: 6px;
          margin-bottom: 12px;
          font-size: 13px;
          font-weight: 600;
        }
        .ctx-stub {
          background: #fef3c7;
          color: #92400e;
          border: 1px solid #fcd34d;
        }
        .ctx-real {
          background: #d1fae5;
          color: #065f46;
          border: 1px solid #6ee7b7;
        }
        .ctx-mode-hint {
          font-weight: 400;
          font-size: 12px;
          margin-top: 4px;
        }
        .ctx-section {
          margin-bottom: 12px;
          padding-bottom: 12px;
          border-bottom: 1px solid var(--border-color);
        }
        .ctx-section:last-child {
          border-bottom: none;
        }
        .ctx-section-title {
          font-size: 11px;
          font-weight: 600;
          color: var(--text-muted);
          text-transform: uppercase;
          margin-bottom: 8px;
        }
        .ctx-next-title {
          font-size: 14px;
          font-weight: 600;
          margin-bottom: 4px;
        }
        .ctx-next-hint {
          font-size: 12px;
          color: var(--text-secondary);
        }
        .ctx-stat-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 3px 0;
          font-size: 13px;
        }
        .ctx-stat-label {
          color: var(--text-muted);
        }
        .ctx-stat-value {
          font-weight: 500;
        }
      `}</style>
    </div>
  )
}
