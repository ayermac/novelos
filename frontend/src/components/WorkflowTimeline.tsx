import { useState } from 'react'
import { formatArtifactSummary, WorkflowArtifacts } from '../lib/artifacts'
import { tWorkflowNodeNarrative, tEventNarrative } from '../lib/state-labels'
import { normalizeNodeStatus, isNodeBusinessSuccess, getNodeStatusBadge } from '../lib/statusSemantics'
import type { WorkflowExecutionEvent, WorkflowNodeEvidence } from '../lib/api'

interface Step {
  key: string
  label: string
  description: string
  node_group?: 'system' | 'creative_agent' | 'support_agent' | 'terminal' | 'router' | 'unknown'
  node_type?: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'blocked' | 'skipped'
  // v6.6.11: Node-level semantic fields
  node_status?: 'pending' | 'running' | 'succeeded' | 'warning' | 'failed' | 'skipped' | 'blocked'
  domain_status?: 'success' | 'partial_success' | 'fallback' | 'degraded' | 'failed' | 'blocked' | 'needs_human' | 'pending' | 'ignored'
  severity?: 'success' | 'info' | 'warning' | 'error'
  retryable?: boolean
  blocking?: boolean
  next_action?: string | null
  action_label?: string | null
  user_message?: string
  flags?: Record<string, boolean>
  error_message?: string
  error_is_legacy?: boolean
  logs?: {
    id?: string
    timestamp?: string
    level?: 'info' | 'success' | 'warning' | 'error'
    message: string
  }[]
  artifacts?: WorkflowArtifacts | null
  events?: WorkflowExecutionEvent[]
  evidence?: WorkflowNodeEvidence
}

export interface PreflightWarning {
  code: string
  message: string
  severity: 'warning' | 'info'
  details?: Record<string, unknown>
}

interface Props {
  steps: Step[]
  compact?: boolean
  preflightWarnings?: PreflightWarning[]
}

// v6.1.1: Event type label mapping (Chinese)
const EVENT_TYPE_LABELS: Record<string, string> = {
  context_loaded: '上下文加载',
  llm_started: 'LLM 调用开始',
  llm_request_detail: 'LLM 请求参数',
  llm_response_detail: 'LLM 响应详情',
  llm_completed: 'LLM 调用完成',
  llm_failed: 'LLM 调用失败',
  long_form_generation: '长文生成模式',
  artifact_saved: '产物保存',
  skill_completed: 'Skill 完成',
  self_check_completed: '自检完成',
  fallback_used: '降级兜底',
  diff_generated: '改动摘要',
  evidence_verified: '证据校验',
  revision_context_loaded: '返修依据',
  revision_diff_generated: '返修改动',
  revision_followup_verified: '返修复核',
  // v6.10.0: Knowledge Skill and Function Calling
  knowledge_injected: '知识注入',
  knowledge_agentic: '知识咨询',
  function_call_started: 'Function Calling',
  function_call_completed: 'Function Calling 完成',
  knowledge_tool_result: '知识工具调用',
  // v6.10.0: Streaming text
  text_chunk: '正文生成中',
}

function eventLabel(eventType: string): string {
  return EVENT_TYPE_LABELS[eventType] || tEventNarrative(eventType) || eventType
}

function eventMessage(ev: WorkflowExecutionEvent): string {
  if (ev.event_type === 'llm_completed') {
    return ev.message || '模型返回完成'
  }
  return ev.message || ''
}

function safePayload(ev: WorkflowExecutionEvent): Record<string, unknown> {
  if (ev.payload && typeof ev.payload === 'object') {
    return ev.payload as Record<string, unknown>
  }
  return {}
}

// v6.10.0: Event classification for visual hierarchy
function isQualityIssue(ev: WorkflowExecutionEvent): boolean {
  if (ev.status === 'error' || ev.status === 'warning') return true
  const type = ev.event_type
  return type === 'self_check_completed' || type === 'scene_beat_coverage_warning' || type === 'screenwriter_inheritance_check'
}

function isKnowledgeEvent(ev: WorkflowExecutionEvent): boolean {
  const type = ev.event_type
  return type === 'knowledge_injected' || type === 'knowledge_agentic' || type === 'function_call_started' || type === 'function_call_completed' || type === 'knowledge_tool_result'
}

function isNoiseEvent(ev: WorkflowExecutionEvent): boolean {
  // Filter out low-value events that clutter the timeline
  if (ev.event_type === 'node_message' && ev.message?.includes('跳过该节点')) return true
  // text_chunk events are rendered separately as streaming text
  if (ev.event_type === 'text_chunk') return true
  return false
}

// v6.10.0: Group consecutive LLM detail events into a collapsible block
function groupEvents(events: WorkflowExecutionEvent[]): Array<{
  type: 'single' | 'llm_group' | 'function_call_group'
  events: WorkflowExecutionEvent[]
}> {
  const groups: Array<{ type: 'single' | 'llm_group' | 'function_call_group'; events: WorkflowExecutionEvent[] }> = []
  let i = 0

  while (i < events.length) {
    const ev = events[i]

    // Group LLM request detail + response detail + completed into one block
    if (ev.event_type === 'llm_request_detail' || ev.event_type === 'llm_started') {
      const llmGroup: WorkflowExecutionEvent[] = [ev]
      i++
      while (i < events.length) {
        const next = events[i]
        if (next.event_type === 'llm_request_detail' || next.event_type === 'llm_response_detail' || next.event_type === 'llm_completed' || next.event_type === 'llm_failed') {
          llmGroup.push(next)
          i++
        } else {
          break
        }
      }
      if (llmGroup.length > 1) {
        groups.push({ type: 'llm_group', events: llmGroup })
      } else {
        groups.push({ type: 'single', events: llmGroup })
      }
      continue
    }

    // Group function calling events
    if (ev.event_type === 'function_call_started') {
      const fcGroup: WorkflowExecutionEvent[] = [ev]
      i++
      while (i < events.length) {
        const next = events[i]
        if (next.event_type === 'knowledge_tool_result' || next.event_type === 'function_call_completed') {
          fcGroup.push(next)
          i++
          if (next.event_type === 'function_call_completed') break
        } else {
          break
        }
      }
      groups.push({ type: 'function_call_group', events: fcGroup })
      continue
    }

    groups.push({ type: 'single', events: [ev] })
    i++
  }

  return groups
}

function stepStatusIcon(step: Step): string {
  const nodeStatus = normalizeNodeStatus(step)
  return getNodeStatusBadge(nodeStatus).icon
}

function stepStatusClass(step: Step): string {
  const nodeStatus = normalizeNodeStatus(step)
  return getNodeStatusBadge(nodeStatus).cssClass
}

const NODE_GROUP_LABELS: Record<string, string> = {
  system: '系统节点',
  creative_agent: '创作 Agent',
  support_agent: '支撑 Agent',
  terminal: '终态/人工节点',
  router: '路由节点',
  unknown: '其他节点',
}

const NODE_GROUP_ORDER = ['system', 'creative_agent', 'support_agent', 'terminal', 'router', 'unknown']

function PreflightWarningBanner({ warnings }: { warnings: PreflightWarning[] }) {
  if (!warnings || warnings.length === 0) return null

  return (
    <div
      style={{
        marginBottom: 16,
        padding: '12px 16px',
        borderRadius: 8,
        background: 'var(--wb-warning-soft, #fff8e6)',
        border: '1px solid var(--wb-warning, #f5a623)',
        fontSize: 13,
        lineHeight: 1.6,
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: 8, color: 'var(--wb-warning, #d4890c)' }}>
        预检提示
      </div>
      {warnings.map((w, i) => (
        <div key={i} style={{ marginBottom: i < warnings.length - 1 ? 8 : 0 }}>
          <div style={{ color: 'var(--wb-text-dark-secondary)' }}>{w.message}</div>
          {w.details && ((w.details.examples as string[] | undefined)?.length || (w.details.groups as unknown[])?.length) && (
            <div style={{ marginTop: 4, fontSize: 12, color: 'var(--wb-text-dark-muted)' }}>
              {((w.details.examples as string[] | undefined) || []).join(', ')}
            </div>
          )}
          {w.details && (w.details.recommended_actions as Array<{ label: string; severity: string }>) && (
            <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {(w.details.recommended_actions as Array<{ label: string; severity: string }>).map((action, j) => (
                <span
                  key={j}
                  style={{
                    display: 'inline-block',
                    padding: '2px 8px',
                    borderRadius: 4,
                    background: action.severity === 'warning' ? 'var(--wb-warning-soft)' : 'var(--wb-paper-muted)',
                    color: action.severity === 'warning' ? 'var(--wb-warning)' : 'var(--wb-text-dark-muted)',
                    fontSize: 11,
                  }}
                >
                  {action.label}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export default function WorkflowTimeline({ steps, compact = false, preflightWarnings }: Props) {
  const [expandedStep, setExpandedStep] = useState<string | null>(null)

  const toggleExpand = (stepKey: string) => {
    setExpandedStep(expandedStep === stepKey ? null : stepKey)
  }

  if (steps.length === 0 && (!preflightWarnings || preflightWarnings.length === 0)) {
    return (
      <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '14px' }}>
        暂无工作流数据
      </div>
    )
  }

  const hasGroups = steps.some((step) => step.node_group)
  const groupedSteps = hasGroups
    ? NODE_GROUP_ORDER.map((group) => ({
        group,
        label: NODE_GROUP_LABELS[group] || group,
        steps: steps.filter((step) => (step.node_group || 'unknown') === group),
      })).filter((group) => group.steps.length > 0)
    : [{ group: 'ungrouped', label: '', steps }]

  return (
    <div className="wf-timeline">
      <PreflightWarningBanner warnings={preflightWarnings || []} />
      <div className="steps-timeline">
        {groupedSteps.map((group) => (
          <div key={group.group} className="step-group">
            {hasGroups && <div className="step-group-title">{group.label}</div>}
            {group.steps.map((step) => {
              const isExpanded = expandedStep === step.key
              const hasArtifacts = step.status === 'completed' && step.artifacts
              const hasExecutionEvents = Boolean(step.events && step.events.length > 0)
              // v6.6.21: Stable sort — null timestamps last, then ascending
              const logs = (step.logs || []).slice().sort((a, b) => {
                const ta = a.timestamp || ''
                const tb = b.timestamp || ''
                if (!ta && !tb) return 0
                if (!ta) return 1
                if (!tb) return -1
                return ta.localeCompare(tb)
              })

              return (
                <div key={step.key} className={`step-item ${stepStatusClass(step)}`}>
                  <div className="step-header">
                    <div className="step-icon">{stepStatusIcon(step)}</div>
                    <div className="step-content">
                      <div className="step-label">
                        {step.label}
                        {/* v6.6.11: Node-level warning/fallback badge */}
                        {step.node_status === 'warning' && (
                          <span className="evidence-badge evidence-warn" style={{ marginLeft: 8 }}>
                            {step.domain_status === 'fallback' ? '记忆未可信' : step.domain_status === 'degraded' ? '降级' : '警告'}
                          </span>
                        )}
                        {step.evidence?.has_evidence_failure && (
                          <span className="evidence-badge evidence-fail" style={{ marginLeft: 8 }}>证据校验失败</span>
                        )}
                        {step.evidence?.has_warnings && !step.evidence?.has_evidence_failure && step.node_status !== 'warning' && (
                          <span className="evidence-badge evidence-warn" style={{ marginLeft: 8 }}>有警告</span>
                        )}
                        {isNodeBusinessSuccess(step) && step.evidence?.has_evidence && !step.evidence?.has_warnings && !step.evidence?.has_evidence_failure && (
                          <span className="evidence-badge evidence-pass" style={{ marginLeft: 8 }}>已验证</span>
                        )}
                        {step.retryable && step.node_status !== 'succeeded' && step.action_label && (
                          <span className="evidence-badge evidence-warn" style={{ marginLeft: 8, cursor: 'pointer' }} title={step.user_message || ''}>{step.action_label}</span>
                        )}
                      </div>
                      {!compact && (
                        <div className="step-description">{step.description}</div>
                      )}
                      {step.error_message && (
                        <div className={`step-error ${step.error_is_legacy ? 'step-error-legacy' : ''}`}>
                          {step.error_message}
                          {step.error_is_legacy && (
                            <span className="legacy-tag">（历史记录）</span>
                          )}
                        </div>
                      )}
                      {(logs.length > 0 || step.status === 'running') && (
                        <div className="step-logs" aria-live={step.status === 'running' ? 'polite' : undefined}>
                          <div className="step-logs-title">节点日志</div>
                          {logs.map((log, index) => (
                            <div key={log.id || `${step.key}-log-${index}`} className={`step-log step-log-${log.level || 'info'}`}>
                              <span className="step-log-dot" />
                              <span className="step-log-message">{log.message}</span>
                              {log.timestamp && <span className="step-log-time">{log.timestamp}</span>}
                            </div>
                          ))}
                          {step.status === 'running' && logs.length === 0 && (
                            <div className="step-log step-log-info">
                              <span className="step-log-dot step-log-dot-pulse" />
                              <span className="step-log-message">{tWorkflowNodeNarrative(step.key)}</span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                    {(hasArtifacts || hasExecutionEvents) && (
                      <button
                        className="step-expand-btn"
                        onClick={() => toggleExpand(step.key)}
                      >
                        {isExpanded ? '收起' : hasExecutionEvents ? '查看过程' : '查看过程稿'}
                      </button>
                    )}
                  </div>
                  {isExpanded && hasExecutionEvents && (
                    <div className="step-exec-events">
                      <div className="exec-events-title">
                        实时工作过程
                        {step.evidence?.has_evidence_failure && (
                          <span className="evidence-badge evidence-fail">证据校验失败</span>
                        )}
                        {step.evidence?.has_warnings && !step.evidence?.has_evidence_failure && (
                          <span className="evidence-badge evidence-warn">有警告</span>
                        )}
                        {step.evidence?.has_evidence && !step.evidence?.has_warnings && !step.evidence?.has_evidence_failure && (
                          <span className="evidence-badge evidence-pass">证据校验通过</span>
                        )}
                      </div>
                      {(() => {
                        // Filter noise and group events
                        const filtered = step.events!.filter((ev) => !isNoiseEvent(ev))
                        const grouped = groupEvents(filtered)

                        return grouped.map((group, gIdx) => {
                          if (group.type === 'llm_group') {
                            // Collapsed LLM group: show summary
                            const request = group.events.find((e) => e.event_type === 'llm_request_detail')
                            const response = group.events.find((e) => e.event_type === 'llm_response_detail')
                            const failed = group.events.find((e) => e.event_type === 'llm_failed')
                            const reqPayload = request ? safePayload(request) : {}
                            const resPayload = response ? safePayload(response) : {}
                            const usage = (resPayload.usage || {}) as Record<string, unknown>

                            return (
                              <div key={`llm-${gIdx}`} className="exec-event exec-event-info exec-event-llm-group">
                                <span className="exec-event-dot" />
                                <span className="exec-event-main">
                                  <span className="exec-event-type">LLM 调用</span>
                                  <span className="exec-event-msg">
                                    {reqPayload.model ? `${reqPayload.model}` : ''}
                                    {reqPayload.call_type ? ` (${reqPayload.call_type})` : ''}
                                    {usage.total_tokens ? ` · ${usage.total_tokens} tokens` : ''}
                                    {usage.duration_ms ? ` · ${((usage.duration_ms as number) / 1000).toFixed(1)}s` : ''}
                                  </span>
                                  {failed && <span className="exec-event-warn-tag">失败</span>}
                                </span>
                              </div>
                            )
                          }

                          if (group.type === 'function_call_group') {
                            // Function calling group
                            const completed = group.events.find((e) => e.event_type === 'function_call_completed')
                            const toolResults = group.events.filter((e) => e.event_type === 'knowledge_tool_result')
                            const completePayload = completed ? safePayload(completed) : {}

                            return (
                              <div key={`fc-${gIdx}`} className="exec-event exec-event-knowledge exec-event-fc-group">
                                <span className="exec-event-dot" />
                                <span className="exec-event-main">
                                  <span className="exec-event-type">知识咨询</span>
                                  <span className="exec-event-msg">
                                    {toolResults.length} 个工具 · {String(completePayload.rounds_used || '?')} 轮
                                    {completePayload.total_tokens ? ` · ${String(completePayload.total_tokens)} tokens` : ''}
                                  </span>
                                </span>
                                <div className="exec-event-fc-tools">
                                  {toolResults.map((tr, tIdx) => {
                                    const trPayload = safePayload(tr)
                                    return (
                                      <div key={tIdx} className="exec-event-fc-tool">
                                        <span className="exec-event-fc-tool-name">{String(trPayload.skill_id || '')}</span>
                                        <span className="exec-event-fc-tool-size">{String(trPayload.content_length || 0)} 字符</span>
                                      </div>
                                    )
                                  })}
                                </div>
                              </div>
                            )
                          }

                          // Single event
                          const ev = group.events[0]
                          const payload = safePayload(ev)
                          const isLowChange = payload.low_change_warning === true
                          const hasMeta = (ev.latency_ms != null && ev.latency_ms > 0) || (ev.token_count != null && ev.token_count > 0)
                          const isQuality = isQualityIssue(ev)
                          const isKnowledge = isKnowledgeEvent(ev)

                          return (
                            <div
                              key={ev.id || `ev-${gIdx}`}
                              className={`exec-event exec-event-${ev.status || 'info'}${isLowChange ? ' exec-event-low-change' : ''}${isQuality ? ' exec-event-quality' : ''}${isKnowledge ? ' exec-event-knowledge' : ''}`}
                            >
                              <span className="exec-event-dot" />
                              <span className="exec-event-main">
                                <span className="exec-event-type">{eventLabel(ev.event_type)}</span>
                                <span className="exec-event-msg">{eventMessage(ev)}</span>
                                {isLowChange && (
                                  <span className="exec-event-warn-tag">内容几乎未变</span>
                                )}
                                {isQuality && ev.status === 'warning' && (
                                  <span className="exec-event-warn-tag">需关注</span>
                                )}
                              </span>
                              {hasMeta && (
                                <span className="exec-event-metas">
                                  {ev.token_count != null && ev.token_count > 0 && (
                                    <span className="exec-event-meta">{ev.token_count} tokens</span>
                                  )}
                                  {ev.latency_ms != null && ev.latency_ms > 0 && (
                                    <span className="exec-event-meta">{(ev.latency_ms / 1000).toFixed(1)}s</span>
                                  )}
                                </span>
                              )}
                            </div>
                          )
                        })
                      })()}
                      {/* v6.10.0: Streaming text display */}
                      {(() => {
                        const textChunks = step.events!.filter((ev) => ev.event_type === 'text_chunk')
                        if (textChunks.length === 0) return null
                        const streamingText = textChunks.map((ev) => ev.message || '').join('')
                        return (
                          <div className="exec-event-streaming-text">
                            <div className="exec-event-streaming-header">
                              <span className="exec-event-type">实时生成</span>
                              <span className="exec-event-meta">{streamingText.length} 字</span>
                            </div>
                            <div className="exec-event-streaming-content">
                              {streamingText.slice(-500)}
                              {step.status === 'running' && <span className="streaming-cursor">|</span>}
                            </div>
                          </div>
                        )
                      })()}
                    </div>
                  )}
                  {isExpanded && hasArtifacts && (
                    <div className="step-artifacts">
                      <div className="artifacts-summary">{formatArtifactSummary(step.artifacts)}</div>
                      {step.artifacts!.output_preview && (
                        <div className="artifacts-preview">
                          <div className="preview-label">内容预览:</div>
                          <div className="preview-content">{step.artifacts!.output_preview}</div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        ))}
      </div>

      <style>{`
        .wf-timeline .steps-timeline {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .wf-timeline .step-group {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .wf-timeline .step-group + .step-group {
          margin-top: 8px;
        }
        .wf-timeline .step-group-title {
          font-size: 12px;
          font-weight: 600;
          color: var(--text-muted);
          padding: 2px 2px 0;
        }
        .wf-timeline .step-item {
          display: flex;
          flex-direction: column;
          border-radius: 6px;
          background: var(--bg-secondary);
          overflow: hidden;
        }
        .wf-timeline .step-header {
          display: flex;
          align-items: flex-start;
          gap: 10px;
          padding: 10px 12px;
        }
        .wf-timeline .step-icon {
          width: 26px;
          height: 26px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 13px;
          font-weight: 600;
          flex-shrink: 0;
        }
        .wf-timeline .step-completed .step-icon {
          background: color-mix(in srgb, var(--success) 14%, transparent);
          color: var(--success);
        }
        .wf-timeline .step-running .step-icon {
          background: var(--accent-soft);
          color: var(--primary);
          animation: wf-pulse 1.5s infinite;
        }
        .wf-timeline .step-failed .step-icon {
          background: color-mix(in srgb, var(--danger) 14%, transparent);
          color: var(--danger);
        }
        .wf-timeline .step-blocked .step-icon {
          background: color-mix(in srgb, var(--warning) 14%, transparent);
          color: var(--warning);
        }
        .wf-timeline .step-skipped .step-icon {
          background: var(--bg-tertiary);
          color: var(--text-secondary);
        }
        .wf-timeline .step-warning .step-icon {
          background: color-mix(in srgb, var(--warning) 14%, transparent);
          color: var(--warning);
        }
        .wf-timeline .step-pending .step-icon {
          background: var(--bg-tertiary);
          color: var(--text-muted);
        }
        .wf-timeline .step-content {
          flex: 1;
          min-width: 0;
        }
        .wf-timeline .step-label {
          font-weight: 500;
          font-size: 14px;
          margin-bottom: 2px;
        }
        .wf-timeline .step-description {
          font-size: 13px;
          color: var(--text-secondary);
        }
        .wf-timeline .step-error {
          margin-top: 6px;
          padding: 6px 8px;
          background: color-mix(in srgb, var(--danger) 12%, var(--bg-primary));
          border-radius: 4px;
          font-size: 12px;
          color: var(--danger);
        }
        .wf-timeline .step-error-legacy {
          background: color-mix(in srgb, var(--warning) 12%, var(--bg-primary));
          color: var(--warning);
        }
        .wf-timeline .step-logs {
          margin-top: 8px;
          display: flex;
          flex-direction: column;
          gap: 5px;
          padding: 8px 10px;
          border-radius: 6px;
          background: color-mix(in srgb, var(--bg-primary) 82%, transparent);
          border: 1px solid var(--border-color);
        }
        .wf-timeline .step-logs-title {
          font-size: 11px;
          font-weight: 600;
          color: var(--text-muted);
          margin-bottom: 1px;
        }
        .wf-timeline .step-log {
          display: grid;
          grid-template-columns: auto minmax(0, 1fr) auto;
          align-items: center;
          gap: 7px;
          font-size: 12px;
          line-height: 1.5;
          color: var(--text-secondary);
        }
        .wf-timeline .step-log-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: var(--text-muted);
        }
        .wf-timeline .step-log-success .step-log-dot {
          background: var(--success);
        }
        .wf-timeline .step-log-warning .step-log-dot {
          background: var(--warning);
        }
        .wf-timeline .step-log-error .step-log-dot {
          background: var(--danger);
        }
        .wf-timeline .step-log-info .step-log-dot {
          background: var(--primary);
        }
        .wf-timeline .step-log-dot-pulse {
          animation: wf-pulse 1.5s infinite;
        }
        .wf-timeline .step-log-message {
          min-width: 0;
          overflow-wrap: anywhere;
        }
        .wf-timeline .step-log-time {
          font-size: 11px;
          color: var(--text-muted);
          font-variant-numeric: tabular-nums;
        }
        .wf-timeline .legacy-tag {
          margin-left: 6px;
          font-size: 11px;
          opacity: 0.8;
        }
        .wf-timeline .step-expand-btn {
          padding: 4px 10px;
          font-size: 12px;
          border: 1px solid var(--border-color);
          border-radius: 4px;
          background: var(--bg-primary);
          color: var(--text-secondary);
          cursor: pointer;
          flex-shrink: 0;
          transition: all 0.15s;
        }
        .wf-timeline .step-expand-btn:hover {
          background: var(--bg-tertiary);
          color: var(--primary);
        }
        .wf-timeline .step-artifacts {
          padding: 0 12px 12px 48px;
          border-top: 1px solid var(--border-color);
          margin-top: 0;
        }
        .wf-timeline .step-exec-events {
          padding: 0 12px 10px 48px;
          border-top: 1px solid var(--border-color);
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .wf-timeline .exec-events-title {
          font-size: 11px;
          font-weight: 600;
          color: var(--text-muted);
          padding: 8px 0 4px;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .wf-timeline .evidence-badge {
          font-size: 10px;
          font-weight: 500;
          padding: 1px 6px;
          border-radius: 3px;
        }
        .wf-timeline .evidence-pass {
          background: color-mix(in srgb, var(--success) 14%, transparent);
          color: var(--success);
        }
        .wf-timeline .evidence-warn {
          background: color-mix(in srgb, var(--warning) 14%, transparent);
          color: var(--warning);
        }
        .wf-timeline .evidence-fail {
          background: color-mix(in srgb, var(--danger) 14%, transparent);
          color: var(--danger);
        }
        .wf-timeline .exec-event {
          display: grid;
          grid-template-columns: auto minmax(0, 1fr) auto;
          align-items: start;
          gap: 7px;
          font-size: 12px;
          line-height: 1.5;
          color: var(--text-secondary);
          padding: 2px 0;
        }
        .wf-timeline .exec-event-dot {
          width: 5px;
          height: 5px;
          border-radius: 50%;
          background: var(--text-muted);
          flex-shrink: 0;
        }
        .wf-timeline .exec-event-pass .exec-event-dot,
        .wf-timeline .exec-event-info .exec-event-dot {
          background: var(--primary);
        }
        .wf-timeline .exec-event-warning .exec-event-dot {
          background: var(--warning);
        }
        .wf-timeline .exec-event-error .exec-event-dot {
          background: var(--danger);
        }
        .wf-timeline .exec-event-msg {
          min-width: 0;
          overflow-wrap: anywhere;
        }
        .wf-timeline .exec-event-main {
          min-width: 0;
          display: flex;
          align-items: center;
          gap: 7px;
          flex-wrap: wrap;
        }
        .wf-timeline .exec-event-type {
          font-size: 11px;
          font-weight: 500;
          color: var(--text-muted);
          white-space: nowrap;
          padding: 1px 5px;
          background: rgba(148, 163, 184, 0.1);
          border-radius: 3px;
          flex-shrink: 0;
        }
        .wf-timeline .exec-event-low-change {
          background: color-mix(in srgb, var(--warning) 8%, transparent);
          border-radius: 4px;
          padding: 3px 6px;
          margin: 1px -6px;
        }
        .wf-timeline .exec-event-warn-tag {
          font-size: 10px;
          font-weight: 500;
          color: var(--warning);
          padding: 1px 5px;
          background: color-mix(in srgb, var(--warning) 14%, transparent);
          border-radius: 3px;
          white-space: nowrap;
        }
        .wf-timeline .exec-event-metas {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 7px;
          white-space: nowrap;
        }
        .wf-timeline .exec-event-meta {
          font-size: 10px;
          color: var(--text-muted);
          font-variant-numeric: tabular-nums;
          white-space: nowrap;
        }
        /* v6.10.0: LLM group style */
        .wf-timeline .exec-event-llm-group {
          padding: 4px 6px;
          background: color-mix(in srgb, var(--primary) 6%, transparent);
          border-radius: 4px;
          margin: 2px -6px;
        }
        /* v6.10.0: Quality issue highlight */
        .wf-timeline .exec-event-quality {
          padding: 4px 6px;
          background: color-mix(in srgb, var(--warning) 8%, transparent);
          border-radius: 4px;
          margin: 2px -6px;
        }
        .wf-timeline .exec-event-quality.exec-event-error {
          background: color-mix(in srgb, var(--danger) 8%, transparent);
        }
        /* v6.10.0: Knowledge event style */
        .wf-timeline .exec-event-knowledge {
          padding: 4px 6px;
          background: color-mix(in srgb, var(--success) 8%, transparent);
          border-radius: 4px;
          margin: 2px -6px;
        }
        .wf-timeline .exec-event-knowledge .exec-event-type {
          color: var(--success);
          background: color-mix(in srgb, var(--success) 14%, transparent);
        }
        /* v6.10.0: Function calling group */
        .wf-timeline .exec-event-fc-group {
          flex-direction: column;
          align-items: flex-start;
          gap: 4px;
        }
        .wf-timeline .exec-event-fc-tools {
          display: flex;
          flex-wrap: wrap;
          gap: 4px;
          padding-left: 12px;
          margin-top: 2px;
        }
        .wf-timeline .exec-event-fc-tool {
          display: flex;
          align-items: center;
          gap: 4px;
          padding: 1px 6px;
          background: color-mix(in srgb, var(--success) 12%, transparent);
          border-radius: 3px;
          font-size: 11px;
        }
        .wf-timeline .exec-event-fc-tool-name {
          font-weight: 500;
          color: var(--success);
        }
        .wf-timeline .exec-event-fc-tool-size {
          color: var(--text-muted);
          font-size: 10px;
        }
        /* v6.10.0: Streaming text display */
        .wf-timeline .exec-event-streaming-text {
          padding: 8px 10px;
          background: color-mix(in srgb, var(--primary) 5%, transparent);
          border: 1px solid color-mix(in srgb, var(--primary) 15%, transparent);
          border-radius: 6px;
          margin-top: 6px;
        }
        .wf-timeline .exec-event-streaming-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 6px;
        }
        .wf-timeline .exec-event-streaming-content {
          font-size: 12px;
          line-height: 1.8;
          color: var(--text-primary);
          white-space: pre-wrap;
          max-height: 300px;
          overflow-y: auto;
          font-family: 'Georgia', 'Noto Serif SC', serif;
        }
        .wf-timeline .streaming-cursor {
          animation: blink 1s step-end infinite;
          color: var(--primary);
          font-weight: bold;
        }
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
        .wf-timeline .artifacts-summary {
          padding: 10px 12px;
          background: color-mix(in srgb, var(--success) 10%, var(--bg-primary));
          border-radius: 4px;
          font-size: 13px;
          color: var(--text-primary);
          line-height: 1.6;
          margin-top: 10px;
        }
        .wf-timeline .artifacts-preview {
          margin-top: 8px;
          padding: 8px 12px;
          background: var(--bg-tertiary);
          border-radius: 4px;
        }
        .wf-timeline .preview-label {
          font-size: 12px;
          color: var(--text-muted);
          margin-bottom: 4px;
        }
        .wf-timeline .preview-content {
          font-size: 12px;
          color: var(--text-secondary);
          white-space: pre-wrap;
          line-height: 1.6;
        }
        @keyframes wf-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
    </div>
  )
}
