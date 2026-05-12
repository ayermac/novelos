import {
  Loader2,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Sparkles,
  Play,
  FileText,
  Eye,
} from 'lucide-react'
import { StepStatus } from '../../hooks/useSSEStream'
import { tWorkflowNodeLabel } from '../../lib/state-labels'
import { tWorkflowStatus, tChapterStatus } from '../../lib/i18n'

interface Run {
  run_id: string
  chapter_number: number
  status: string
  created_at: string
  error_message?: string
}

interface Step {
  key: string
  label: string
  description: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'blocked'
  error_message?: string
  artifacts?: {
    summary: string
    output_preview?: string
    [key: string]: unknown
  } | null
}

interface RunDetailData {
  run_id: string
  project_id: string
  chapter_number: number
  workflow_status: string
  chapter_status: string
  current_node?: string | null
  llm_mode: string
  started_at?: string
  completed_at?: string
  steps: Step[]
  error_message?: string | null
  total_tokens?: number | null
  duration_ms?: number | null
}

const STUCK_RUN_THRESHOLD_MINUTES = 30

function elapsedMinutesSince(value?: string | null): number | null {
  if (!value) return null
  const normalized = value.includes('T') ? value : value.replace(' ', 'T')
  const timestamp = new Date(normalized).getTime()
  if (Number.isNaN(timestamp)) return null
  return Math.max(0, Math.floor((Date.now() - timestamp) / 60000))
}

interface AuthorAgentPanelProps {
  currentChapter: number
  currentChapterRecord: { status: string; word_count: number; title?: string } | null
  llmMode: string
  runDetail: RunDetailData | null
  runsForChapter: Run[]
  isStreaming: boolean
  isWorkflowRunning?: boolean
  sseSteps: Record<string, StepStatus>
  genError: string
  onGenerate: () => void
  onPublish?: () => void
  onGenerateNext?: () => void
  onViewContent: () => void
  onViewWorkflow: (runId: string) => void
}

export default function AuthorAgentPanel({
  currentChapterRecord,
  llmMode,
  runDetail,
  runsForChapter,
  isStreaming,
  isWorkflowRunning,
  sseSteps,
  genError,
  onGenerate,
  onPublish,
  onGenerateNext,
  onViewContent,
  onViewWorkflow,
}: AuthorAgentPanelProps) {
  const status = currentChapterRecord?.status || ''
  const hasContent = (currentChapterRecord?.word_count || 0) > 0
  const workflowStatus = runDetail?.workflow_status
  const currentNode = runDetail?.current_node
  const sseStepEntries = Object.entries(sseSteps)
  const isReviewedReal = status === 'reviewed' && llmMode === 'real'
  const elapsedMinutes = elapsedMinutesSince(runDetail?.started_at)
  const isStaleRunning = runDetail?.workflow_status === 'running' && elapsedMinutes !== null && elapsedMinutes >= STUCK_RUN_THRESHOLD_MINUTES

  return (
    <aside className="author-agent" aria-label="AI 助手面板">
      <div className="author-agent-header">
        <h3>AI 助手</h3>
      </div>
      <div className="author-agent-body">
        {/* Next recommended action */}
        {isReviewedReal && onPublish && (
          <div className="author-agent-next-action">
            <div className="action-label">等待人工发布</div>
            <div className="action-desc">本章已通过 AI 审核，点击确认发布。</div>
            <button className="btn btn-primary btn-sm" onClick={onPublish} style={{ marginTop: 8, width: '100%' }}>
              <CheckCircle2 size={12} /> 确认发布
            </button>
          </div>
        )}

        {status === 'published' && onGenerateNext && (
          <div className="author-agent-next-action">
            <div className="action-label">本章已发布</div>
            <div className="action-desc">可以继续生成下一章。</div>
            <button className="btn btn-primary btn-sm" onClick={onGenerateNext} style={{ marginTop: 8, width: '100%' }}>
              <Sparkles size={12} /> 生成下一章
            </button>
          </div>
        )}

        {!isReviewedReal && status !== 'published' && status !== 'awaiting_publish' && (
          <div className="author-agent-next-action">
            <div className="action-label">
              {isStaleRunning ? '运行疑似卡住' : isStreaming || isWorkflowRunning ? '正在生成...' : hasContent ? '本章已有内容' : '准备生成'}
            </div>
            <div className="action-desc">
              {isStaleRunning
                ? `当前运行已超过 ${STUCK_RUN_THRESHOLD_MINUTES} 分钟未完成，建议进入运行恢复处理。`
                : isStreaming || isWorkflowRunning
                ? 'AI 正在处理本章，请稍候。'
                : hasContent
                  ? '本章已完成生成，可以查看正文或重新生成。'
                  : '本章尚未生成，点击下方按钮开始。'}
            </div>
            <button
              className="btn btn-primary btn-sm"
              onClick={onGenerate}
              disabled={isStreaming || isWorkflowRunning}
              style={{ marginTop: 8, width: '100%' }}
            >
              {isStreaming || isWorkflowRunning ? (
                <><Loader2 size={12} className="spin" /> 生成中...</>
              ) : (
                <><Play size={12} /> 生成本章</>
              )}
            </button>
          </div>
        )}

        {status === 'awaiting_publish' && (
          <div className="author-agent-next-action">
            <div className="action-label">等待发布</div>
            <div className="action-desc">本章已完成全部流程，等待最终发布。</div>
          </div>
        )}

        {/* Current run status */}
        <div className="author-agent-card">
          <div className="author-agent-card-title">运行状态</div>
          {runDetail ? (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                {workflowStatus === 'running' && !isStaleRunning && <Loader2 size={14} className="spin" color="#3b82f6" />}
                {isStaleRunning && <AlertCircle size={14} color="#f59e0b" />}
                {workflowStatus === 'completed' && <CheckCircle2 size={14} color="#10b981" />}
                {workflowStatus === 'failed' && <XCircle size={14} color="#ef4444" />}
                {workflowStatus === 'blocked' && <AlertCircle size={14} color="#f59e0b" />}
                <span style={{ fontSize: 13, fontWeight: 500 }}>
                  {isStaleRunning ? '疑似卡住'
                    : workflowStatus === 'running' ? '执行中'
                    : workflowStatus === 'completed' ? '已完成'
                    : workflowStatus === 'failed' ? '失败'
                    : workflowStatus === 'blocked' ? '阻塞'
                    : workflowStatus || '—'}
                </span>
              </div>
              {currentNode && (
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
                  当前节点：{tWorkflowNodeLabel(currentNode)}
                </div>
              )}
              {runDetail.chapter_status && (
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  章节状态：{tChapterStatus(runDetail.chapter_status)}
                </div>
              )}
              {isStaleRunning && elapsedMinutes !== null && (
                <div style={{ fontSize: 12, color: '#92400e', marginTop: 6 }}>
                  已运行约 {elapsedMinutes} 分钟，超过卡住阈值 {STUCK_RUN_THRESHOLD_MINUTES} 分钟。
                </div>
              )}
            </>
          ) : (
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>暂无运行记录</div>
          )}

          {/* Streaming indicator */}
          {isStreaming && sseStepEntries.length > 0 && (
            <div style={{ marginTop: 8, borderTop: '1px solid var(--border-color)', paddingTop: 8 }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>实时进度</div>
              {sseStepEntries.map(([key, step]) => (
                <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  {step.status === 'running' && <Loader2 size={11} className="spin" color="#3b82f6" />}
                  {step.status === 'completed' && <CheckCircle2 size={11} color="#10b981" />}
                  {step.status === 'failed' && <XCircle size={11} color="#ef4444" />}
                  <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{key}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Error */}
        {genError && (
          <div className="author-agent-error">
            <div style={{ fontWeight: 500, marginBottom: 2 }}>生成失败</div>
            <div>{genError}</div>
          </div>
        )}

        {runDetail?.error_message && (workflowStatus === 'failed' || workflowStatus === 'blocked') && (
          <div className="author-agent-error">
            {runDetail.error_message}
          </div>
        )}

        {/* Run stats */}
        {runDetail && (runDetail.total_tokens || runDetail.duration_ms) && (
          <div className="author-agent-card">
            <div className="author-agent-card-title">运行统计</div>
            <div style={{ display: 'flex', gap: 12, fontSize: 12, color: 'var(--text-muted)' }}>
              {runDetail.total_tokens ? <span>Token: {runDetail.total_tokens.toLocaleString()}</span> : null}
              {runDetail.duration_ms ? <span>耗时: {Math.round(runDetail.duration_ms / 1000)}s</span> : null}
            </div>
          </div>
        )}

        {/* Secondary actions */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {hasContent && (
            <button className="btn btn-secondary btn-sm" onClick={onViewContent} style={{ justifyContent: 'flex-start' }}>
              <FileText size={12} /> 查看正文
            </button>
          )}
          {runDetail && (
            <button className="btn btn-secondary btn-sm" onClick={() => onViewWorkflow(runDetail.run_id)} style={{ justifyContent: 'flex-start' }}>
              <Eye size={12} /> 查看运行详情
            </button>
          )}
        </div>

        {/* Recent runs */}
        {runsForChapter.length > 0 && (
          <div className="author-agent-card">
            <div className="author-agent-card-title">近期运行</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 200, overflowY: 'auto' }}>
              {runsForChapter.slice(0, 5).map((run) => (
                <div
                  key={run.run_id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 8,
                    padding: '6px 8px',
                    background: 'var(--bg-tertiary)',
                    borderRadius: 6,
                    cursor: 'pointer',
                  }}
                  onClick={() => onViewWorkflow(run.run_id)}
                >
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {run.run_id.slice(0, 8)}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{run.created_at}</div>
                  </div>
                  <span
                    style={{
                      fontSize: 10,
                      padding: '2px 6px',
                      borderRadius: 4,
                      background: run.status === 'completed' ? '#d1fae5' : run.status === 'failed' ? '#fee2e2' : '#dbeafe',
                      color: run.status === 'completed' ? '#065f46' : run.status === 'failed' ? '#991b1b' : '#1e40af',
                      flexShrink: 0,
                    }}
                  >
                    {tWorkflowStatus(run.status)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </aside>
  )
}
