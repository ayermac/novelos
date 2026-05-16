import {
  CheckCircle2,
  Sparkles,
  Play,
  FileText,
  Eye,
} from 'lucide-react'
import { StepStatus } from '../../hooks/useSSEStream'
import { tWorkflowNodeLabel, tWorkflowNodeNarrative } from '../../lib/state-labels'
import { tWorkflowStatus, tChapterStatus } from '../../lib/i18n'
import { LoadingButton, InlineMessage } from '../ui'
import type { WorkflowTimelineData } from '../../lib/api'

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
  timeline?: WorkflowTimelineData | null
  onGenerate: () => void
  onConfirmRegenerate?: () => void
  onMarkRunStuck?: (runId: string) => Promise<void> | void
  onPublish?: () => void
  onGenerateNext?: () => void
  onResetRunRecovery?: (runId: string) => Promise<void> | void
  publishPending?: boolean
  markStuckPending?: boolean
  resetRecoveryPending?: boolean
  regeneratePending?: boolean
  onViewContent: () => void
  onViewWorkflow: (runId: string) => void
}

function getAgentActionDesc(node: string | null | undefined): string {
  switch (node) {
    case 'planner':
      return 'AI 正在分析章节目标、角色关系和伏笔，规划本章结构。'
    case 'screenwriter':
      return 'AI 正在将规划分解为具体场景，设计情节转折和节奏。'
    case 'author':
      return 'AI 正在根据场景规划撰写章节正文。'
    case 'polisher':
      return 'AI 正在优化文字表达，提升可读性和风格一致性。'
    case 'editor':
      return 'AI 正在从设定一致性、逻辑、毒点、文字质量、爽点五个维度审核。'
    case 'memory_curator':
      return 'AI 正在提取本章关键事实和角色状态，更新项目记忆。'
    case 'publisher':
    case 'publish':
      return 'AI 正在完成最终发布步骤。'
    case 'health_check':
      return 'AI 正在检查上下文和运行环境是否满足创作条件。'
    case 'task_discovery':
      return 'AI 正在识别本章需要处理的具体创作任务。'
    case 'revision_router':
      return 'AI 正在分析审核结果，决定返修方向。'
    case 'human_review':
      return '等待人工审核和确认。'
    default:
      return 'AI 正在处理本章，请稍候。'
  }
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
  timeline,
  onGenerate,
  onConfirmRegenerate,
  onMarkRunStuck,
  onPublish,
  onGenerateNext,
  onResetRunRecovery,
  publishPending,
  markStuckPending,
  resetRecoveryPending,
  regeneratePending,
  onViewContent,
  onViewWorkflow,
}: AuthorAgentPanelProps) {
  const status = currentChapterRecord?.status || ''
  const hasContent = (currentChapterRecord?.word_count || 0) > 0
  // v5.8: Prefer timeline for status info
  const effectiveRunStatus = timeline?.run_status || runDetail?.workflow_status
  const effectiveElapsed = timeline?.elapsed_minutes !== undefined && timeline?.elapsed_minutes !== null
    ? timeline.elapsed_minutes
    : elapsedMinutesSince(runDetail?.started_at)
  const workflowStatus = runDetail?.workflow_status
  const currentNode = runDetail?.current_node
  const sseStepEntries = Object.entries(sseSteps)
  const isReviewedReal = status === 'reviewed' && llmMode === 'real'
  const elapsedMinutes = elapsedMinutesSince(runDetail?.started_at)
  const isStaleRunning = effectiveRunStatus === 'running' && effectiveElapsed !== null && effectiveElapsed >= STUCK_RUN_THRESHOLD_MINUTES
  const hasPreservedPlannedContent = status === 'planned' && hasContent
  const needsRecovery = status === 'blocking' || status === 'revision'
  const canDirectGenerate = !hasPreservedPlannedContent && !needsRecovery

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
            <LoadingButton
              className="btn btn-primary btn-sm"
              variant="primary"
              loading={!!publishPending}
              loadingText="发布中..."
              onClick={onPublish}
              disabled={isStreaming || isWorkflowRunning}
              style={{ marginTop: 8, width: '100%' }}
            >
              <CheckCircle2 size={12} /> 确认发布
            </LoadingButton>
          </div>
        )}

        {status === 'published' && onGenerateNext && (
          <div className="author-agent-next-action">
            <div className="action-label">本章已发布</div>
            <div className="action-desc">可以继续生成下一章。</div>
            <LoadingButton
              className="btn btn-primary btn-sm"
              variant="primary"
              loading={false}
              onClick={onGenerateNext}
              style={{ marginTop: 8, width: '100%' }}
            >
              <Sparkles size={12} /> 生成下一章
            </LoadingButton>
          </div>
        )}

        {!isReviewedReal && status !== 'published' && status !== 'awaiting_publish' && (
          <div className="author-agent-next-action">
            <div className="action-label">
              {isStaleRunning
                ? '运行疑似卡住'
                : isStreaming || isWorkflowRunning
                  ? tWorkflowNodeNarrative(currentNode || timeline?.current_node)
                  : hasPreservedPlannedContent
                    ? '已有正文待确认'
                    : needsRecovery
                      ? '需要先恢复运行'
                  : hasContent
                    ? '本章已有内容'
                    : '准备生成'}
            </div>
            <div className="action-desc">
              {isStaleRunning
                ? `当前运行已超过 ${STUCK_RUN_THRESHOLD_MINUTES} 分钟未完成，建议进入运行恢复处理。`
                : isStreaming || isWorkflowRunning
                  ? getAgentActionDesc(currentNode || timeline?.current_node)
                  : hasPreservedPlannedContent
                    ? '本章保留了已有正文。请先查看正文，或明确确认覆盖后再重新生成。'
                    : needsRecovery
                      ? '本章处于阻塞或返修状态，先清除阻塞/恢复运行，再决定是否继续生成。'
                  : hasContent
                    ? '本章已完成生成，可以查看正文或重新生成。'
                    : '本章尚未生成，点击下方按钮开始。'}
            </div>
            {hasPreservedPlannedContent && onConfirmRegenerate ? (
              <LoadingButton
                className="btn btn-primary btn-sm"
                variant="primary"
                loading={!!regeneratePending}
                loadingText="确认中..."
                onClick={onConfirmRegenerate}
                disabled={isStreaming || isWorkflowRunning}
                style={{ marginTop: 8, width: '100%' }}
              >
                <Sparkles size={12} /> 覆盖重生成
              </LoadingButton>
            ) : canDirectGenerate && (
              <LoadingButton
                className="btn btn-primary btn-sm"
                variant="primary"
                loading={isStreaming || isWorkflowRunning}
                loadingText="生成中..."
                onClick={onGenerate}
                disabled={isStreaming || isWorkflowRunning}
                style={{ marginTop: 8, width: '100%' }}
              >
                <Play size={12} /> 生成本章
              </LoadingButton>
            )}
            {isStaleRunning && runDetail && onMarkRunStuck && (
              <LoadingButton
                className="btn btn-secondary btn-sm"
                variant="secondary"
                loading={!!markStuckPending}
                loadingText="处理中..."
                onClick={() => onMarkRunStuck(runDetail.run_id)}
                style={{ marginTop: 8, width: '100%' }}
              >
                标记为阻塞
              </LoadingButton>
            )}
            {needsRecovery && runDetail && onResetRunRecovery && (
              <LoadingButton
                className="btn btn-secondary btn-sm"
                variant="secondary"
                loading={!!resetRecoveryPending}
                loadingText="处理中..."
                onClick={() => onResetRunRecovery(runDetail.run_id)}
                style={{ marginTop: 8, width: '100%' }}
              >
                清除阻塞并重置
              </LoadingButton>
            )}
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
                {workflowStatus === 'running' && !isStaleRunning && <span className="author-agent-status-light info pulse" />}
                {isStaleRunning && <span className="author-agent-status-light warning" />}
                {workflowStatus === 'completed' && <span className="author-agent-status-light success" />}
                {workflowStatus === 'failed' && <span className="author-agent-status-light danger" />}
                {workflowStatus === 'blocked' && <span className="author-agent-status-light warning" />}
                <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--wb-text)' }}>
                  {isStaleRunning ? '疑似卡住'
                    : workflowStatus === 'running' ? '执行中'
                    : workflowStatus === 'completed' ? '已完成'
                    : workflowStatus === 'failed' ? '失败'
                    : workflowStatus === 'blocked' ? '阻塞'
                    : workflowStatus || '—'}
                </span>
              </div>
              {currentNode && (
                <div style={{ fontSize: 12, color: 'var(--wb-text-muted)', marginBottom: 4 }}>
                  当前节点：{tWorkflowNodeLabel(currentNode)}
                </div>
              )}
              {runDetail.chapter_status && (
                <div style={{ fontSize: 12, color: 'var(--wb-text-muted)' }}>
                  章节状态：{tChapterStatus(runDetail.chapter_status)}
                </div>
              )}
              {isStaleRunning && elapsedMinutes !== null && (
                <div style={{ fontSize: 12, color: 'var(--wb-warning)', marginTop: 6 }}>
                  已运行约 {elapsedMinutes} 分钟，超过卡住阈值 {STUCK_RUN_THRESHOLD_MINUTES} 分钟。
                </div>
              )}
            </>
          ) : (
            <div style={{ fontSize: 12, color: 'var(--wb-text-muted)' }}>暂无运行记录</div>
          )}

          {/* Streaming indicator */}
          {isStreaming && (
            <div style={{ marginTop: 8, borderTop: '1px solid var(--wb-panel-border)', paddingTop: 8 }}>
              <div style={{ fontSize: 11, color: 'var(--wb-text-muted)', marginBottom: 6 }}>实时进度</div>
              {sseStepEntries.length === 0 ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--wb-text-muted)' }}>
                  <span className="author-agent-status-light info pulse" />
                  正在启动创作流程...
                </div>
              ) : (
                sseStepEntries.map(([key, step]) => (
                  <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    {step.status === 'running' && <span className="author-agent-status-light info pulse" />}
                    {step.status === 'completed' && <span className="author-agent-status-light success" />}
                    {step.status === 'failed' && <span className="author-agent-status-light danger" />}
                    <span style={{ fontSize: 11, color: 'var(--wb-text-muted)' }}>
                      {step.status === 'running' ? tWorkflowNodeNarrative(key) : tWorkflowNodeLabel(key)}
                    </span>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Error */}
        {genError && (
          <div style={{ marginTop: 8 }}>
            <InlineMessage variant="danger">
              <div style={{ fontWeight: 500, marginBottom: 2 }}>生成失败</div>
              <div>{genError}</div>
            </InlineMessage>
          </div>
        )}

        {runDetail?.error_message && (workflowStatus === 'failed' || workflowStatus === 'blocked') && (
          <div style={{ marginTop: 8 }}>
            <InlineMessage variant="danger">{runDetail.error_message}</InlineMessage>
          </div>
        )}

          {/* Run stats */}
        {runDetail && (Boolean(runDetail.total_tokens) || Boolean(runDetail.duration_ms)) && (
          <div className="author-agent-card">
            <div className="author-agent-card-title">运行统计</div>
            <div style={{ display: 'flex', gap: 12, fontSize: 12, color: 'var(--wb-text-muted)' }}>
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
                  className="author-agent-run-item"
                  onClick={() => onViewWorkflow(run.run_id)}
                >
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--wb-text)' }}>
                      {run.run_id.slice(0, 8)}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--wb-text-muted)' }}>{run.created_at}</div>
                  </div>
                  <span
                    className="author-agent-run-badge"
                    style={{
                      background: run.status === 'completed' ? 'var(--wb-success-soft)' : run.status === 'failed' ? 'var(--wb-danger-soft)' : 'rgba(255,255,255,0.06)',
                      color: run.status === 'completed' ? 'var(--wb-success)' : run.status === 'failed' ? 'var(--wb-danger)' : 'var(--wb-text-muted)',
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
