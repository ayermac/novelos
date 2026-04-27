import { useState } from 'react'

interface Artifacts {
  summary: string
  output_preview?: string
  [key: string]: unknown
}

interface Step {
  key: string
  label: string
  description: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'blocked'
  error_message?: string
  artifacts?: Artifacts | null
}

interface Props {
  steps: Step[]
  compact?: boolean
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
    default:
      return 'step-pending'
  }
}

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

  return (
    <div className="wf-timeline">
      <div className="steps-timeline">
        {steps.map((step) => {
          const isExpanded = expandedStep === step.key
          const hasArtifacts = step.status === 'completed' && step.artifacts

          return (
            <div key={step.key} className={`step-item ${stepStatusClass(step.status)}`}>
              <div className="step-header">
                <div className="step-icon">{stepStatusIcon(step.status)}</div>
                <div className="step-content">
                  <div className="step-label">{step.label}</div>
                  {!compact && (
                    <div className="step-description">{step.description}</div>
                  )}
                  {step.error_message && (
                    <div className="step-error">{step.error_message}</div>
                  )}
                </div>
                {hasArtifacts && (
                  <button
                    className="step-expand-btn"
                    onClick={() => toggleExpand(step.key)}
                  >
                    {isExpanded ? '收起' : '查看产物'}
                  </button>
                )}
              </div>
              {hasArtifacts && isExpanded && (
                <div className="step-artifacts">
                  <div className="artifacts-summary">{step.artifacts!.summary}</div>
                  {step.artifacts!.output_preview && (
                    <div className="artifacts-preview">
                      <div className="preview-label">预览:</div>
                      <div className="preview-content">{step.artifacts!.output_preview}</div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <style>{`
        .wf-timeline .steps-timeline {
          display: flex;
          flex-direction: column;
          gap: 8px;
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
