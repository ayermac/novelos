import { useState } from 'react'
import { formatArtifactSummary, WorkflowArtifacts } from '../lib/artifacts'
import { tWorkflowNodeNarrative, tEventNarrative } from '../lib/state-labels'
import type { WorkflowExecutionEvent, WorkflowNodeEvidence } from '../lib/api'

interface Step {
  key: string
  label: string
  description: string
  node_group?: 'system' | 'creative_agent' | 'support_agent' | 'terminal' | 'router' | 'unknown'
  node_type?: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'blocked' | 'skipped'
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

interface Props {
  steps: Step[]
  compact?: boolean
}

// v6.1.1: Event type label mapping (Chinese)
const EVENT_TYPE_LABELS: Record<string, string> = {
  context_loaded: '上下文加载',
  llm_started: 'LLM 调用开始',
  llm_completed: 'LLM 调用完成',
  llm_failed: 'LLM 调用失败',
  artifact_saved: '产物保存',
  skill_completed: 'Skill 完成',
  self_check_completed: '自检完成',
  fallback_used: '降级兜底',
  diff_generated: '改动摘要',
  evidence_verified: '证据校验',
  revision_context_loaded: '返修依据',
  revision_diff_generated: '返修改动',
  revision_followup_verified: '返修复核',
}

function eventLabel(eventType: string): string {
  return EVENT_TYPE_LABELS[eventType] || tEventNarrative(eventType) || eventType
}

function eventMessage(ev: WorkflowExecutionEvent): string {
  if (ev.event_type === 'llm_completed') {
    return '模型返回完成'
  }
  return ev.message || ''
}

function stepStatusIcon(status: string): string {
  switch (status) {
    case 'completed':
      return '✓'
    case 'running':
      return '●'
    case 'failed':
      return '✗'
    case 'blocked':
      return '!'
    case 'skipped':
      return '↷'
    default:
      return '○'
  }
}

function stepStatusClass(status: string): string {
  switch (status) {
    case 'completed':
      return 'step-completed'
    case 'running':
      return 'step-running'
    case 'failed':
      return 'step-failed'
    case 'blocked':
      return 'step-blocked'
    case 'skipped':
      return 'step-skipped'
    default:
      return 'step-pending'
  }
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

export default function WorkflowTimeline({ steps, compact = false }: Props) {
  const [expandedStep, setExpandedStep] = useState<string | null>(null)

  const toggleExpand = (stepKey: string) => {
    setExpandedStep(expandedStep === stepKey ? null : stepKey)
  }

  if (steps.length === 0) {
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
      <div className="steps-timeline">
        {groupedSteps.map((group) => (
          <div key={group.group} className="step-group">
            {hasGroups && <div className="step-group-title">{group.label}</div>}
            {group.steps.map((step) => {
              const isExpanded = expandedStep === step.key
              const hasArtifacts = step.status === 'completed' && step.artifacts
              const hasExecutionEvents = Boolean(step.events && step.events.length > 0)
              const logs = step.logs || []

              return (
                <div key={step.key} className={`step-item ${stepStatusClass(step.status)}`}>
                  <div className="step-header">
                    <div className="step-icon">{stepStatusIcon(step.status)}</div>
                    <div className="step-content">
                      <div className="step-label">
                        {step.label}
                        {step.evidence?.has_evidence_failure && (
                          <span className="evidence-badge evidence-fail" style={{ marginLeft: 8 }}>证据校验失败</span>
                        )}
                        {step.evidence?.has_warnings && !step.evidence?.has_evidence_failure && (
                          <span className="evidence-badge evidence-warn" style={{ marginLeft: 8 }}>有警告</span>
                        )}
                        {step.status === 'completed' && step.evidence?.has_evidence && !step.evidence?.has_warnings && !step.evidence?.has_evidence_failure && (
                          <span className="evidence-badge evidence-pass" style={{ marginLeft: 8 }}>已验证</span>
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
                      {step.events!.map((ev, idx) => {
                        const isLowChange = ev.payload && (ev.payload as Record<string, unknown>).low_change_warning === true
                        const hasMeta = (ev.latency_ms != null && ev.latency_ms > 0) || (ev.token_count != null && ev.token_count > 0)
                        return (
                          <div key={ev.id || `ev-${idx}`} className={`exec-event exec-event-${ev.status || 'info'}${isLowChange ? ' exec-event-low-change' : ''}`}>
                            <span className="exec-event-dot" />
                            <span className="exec-event-main">
                              <span className="exec-event-type">{eventLabel(ev.event_type)}</span>
                              <span className="exec-event-msg">{eventMessage(ev)}</span>
                              {isLowChange && (
                                <span className="exec-event-warn-tag">内容几乎未变</span>
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
                      })}
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
          background: #dcfce7;
          color: #16a34a;
        }
        .wf-timeline .step-running .step-icon {
          background: #dbeafe;
          color: #2563eb;
          animation: wf-pulse 1.5s infinite;
        }
        .wf-timeline .step-failed .step-icon {
          background: #fef2f2;
          color: #dc2626;
        }
        .wf-timeline .step-blocked .step-icon {
          background: #fef3c7;
          color: #d97706;
        }
        .wf-timeline .step-skipped .step-icon {
          background: #f1f5f9;
          color: #64748b;
        }
        .wf-timeline .step-pending .step-icon {
          background: #f3f4f6;
          color: #9ca3af;
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
          background: #fef2f2;
          border-radius: 4px;
          font-size: 12px;
          color: #dc2626;
        }
        .wf-timeline .step-error-legacy {
          background: #fffbeb;
          color: #b45309;
        }
        .wf-timeline .step-logs {
          margin-top: 8px;
          display: flex;
          flex-direction: column;
          gap: 5px;
          padding: 8px 10px;
          border-radius: 6px;
          background: rgba(255, 255, 255, 0.64);
          border: 1px solid rgba(148, 163, 184, 0.2);
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
          background: #94a3b8;
        }
        .wf-timeline .step-log-success .step-log-dot {
          background: #16a34a;
        }
        .wf-timeline .step-log-warning .step-log-dot {
          background: #d97706;
        }
        .wf-timeline .step-log-error .step-log-dot {
          background: #dc2626;
        }
        .wf-timeline .step-log-info .step-log-dot {
          background: #2563eb;
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
          background: #dcfce7;
          color: #16a34a;
        }
        .wf-timeline .evidence-warn {
          background: #fef3c7;
          color: #d97706;
        }
        .wf-timeline .evidence-fail {
          background: #fef2f2;
          color: #dc2626;
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
          background: #94a3b8;
          flex-shrink: 0;
        }
        .wf-timeline .exec-event-pass .exec-event-dot,
        .wf-timeline .exec-event-info .exec-event-dot {
          background: #2563eb;
        }
        .wf-timeline .exec-event-warning .exec-event-dot {
          background: #d97706;
        }
        .wf-timeline .exec-event-error .exec-event-dot {
          background: #dc2626;
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
          background: rgba(251, 191, 36, 0.06);
          border-radius: 4px;
          padding: 3px 6px;
          margin: 1px -6px;
        }
        .wf-timeline .exec-event-warn-tag {
          font-size: 10px;
          font-weight: 500;
          color: #d97706;
          padding: 1px 5px;
          background: #fef3c7;
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
        .wf-timeline .artifacts-summary {
          padding: 10px 12px;
          background: #f0fdf4;
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
