import { useState, useCallback } from 'react'
import { get } from '../../lib/api'
import { ChevronDown, AlertCircle, AlertTriangle, Info, CheckCircle2, BarChart3 } from 'lucide-react'
import { InlineMessage, LoadingButton, SkeletonStack, useToast } from '../ui'

interface QualityDiagnosisPanelProps {
  projectId: string
  chapterNumber: number
  chapterStatus: string
}

interface QualityFinding {
  severity: 'critical' | 'high' | 'medium' | 'info'
  code: string
  message: string
  evidence?: unknown
  suggestion?: string | null
}

interface QualityDiagnosis {
  overall_score: number
  dimensions: Record<string, number>
  findings: QualityFinding[]
  metrics: {
    word_count: number
    paragraph_count: number
    sentence_count: number
    avg_sentence_length: number
    dialogue_ratio: number
    dialogue_count: number
  }
}

const DIMENSION_ORDER = [
  'death_penalty',
  'ai_trace',
  'narrative_quality',
  'conflict_intensity',
  'hook_strength',
  'pacing_control',
  'dialogue_naturalness',
  'scene_immersion',
  'character_motivation',
  'show_dont_tell',
  'info_dump',
  'information_density',
]

function dimensionLabel(key: string): string {
  const map: Record<string, string> = {
    death_penalty: '红线',
    ai_trace: 'AI 痕迹',
    narrative_quality: '叙事',
    conflict_intensity: '冲突',
    hook_strength: '钩子',
    information_density: '信息',
    pacing_control: '节奏',
    dialogue_naturalness: '对白',
    scene_immersion: '场景',
    character_motivation: '动机',
    show_dont_tell: '动作化',
    info_dump: '设定倾倒',
  }
  return map[key] || key
}

function scoreTone(score: number): 'strong' | 'ok' | 'weak' | 'bad' {
  if (score >= 85) return 'strong'
  if (score >= 70) return 'ok'
  if (score >= 55) return 'weak'
  return 'bad'
}

function scoreText(score: number): string {
  if (score >= 85) return '表现稳定'
  if (score >= 70) return '可以优化'
  if (score >= 55) return '需要修订'
  return '建议重写'
}

function scoreColor(score: number): string {
  if (score >= 85) return '#15803d'
  if (score >= 70) return '#b45309'
  if (score >= 55) return '#c2410c'
  return '#b91c1c'
}

function severityLabel(severity: QualityFinding['severity']): string {
  if (severity === 'critical') return '致命'
  if (severity === 'high') return '严重'
  if (severity === 'medium') return '注意'
  return '提示'
}

function severityIcon(severity: QualityFinding['severity']) {
  if (severity === 'critical') return AlertCircle
  if (severity === 'high' || severity === 'medium') return AlertTriangle
  return Info
}

function orderedDimensions(dimensions: Record<string, number>) {
  return Object.entries(dimensions).sort(([a], [b]) => {
    const ai = DIMENSION_ORDER.indexOf(a)
    const bi = DIMENSION_ORDER.indexOf(b)
    if (ai === -1 && bi === -1) return a.localeCompare(b)
    if (ai === -1) return 1
    if (bi === -1) return -1
    return ai - bi
  })
}

export default function QualityDiagnosisPanel({
  projectId,
  chapterNumber,
  chapterStatus,
}: QualityDiagnosisPanelProps) {
  const { showToast } = useToast()
  const [open, setOpen] = useState(false)
  const [diagnosis, setDiagnosis] = useState<QualityDiagnosis | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async (showSuccess = false) => {
    if (!open) {
      setOpen(true)
      if (diagnosis) return
    }
    setLoading(true)
    setError('')
    try {
      const res = await get<QualityDiagnosis>(
        `/projects/${projectId}/chapters/${chapterNumber}/quality-diagnosis`,
      )
      if (res.ok && res.data) {
        setDiagnosis(res.data)
        if (showSuccess) {
          showToast({
            tone: 'success',
            title: '质量诊断已刷新',
            message: `综合评分 ${res.data.overall_score.toFixed(1)} / 100`,
          })
        }
      } else {
        const msg = res.error?.message || '诊断失败'
        setError(msg)
        showToast({ tone: 'danger', title: '诊断失败', message: msg })
      }
    } catch {
      const msg = '请求失败，请稍后重试。'
      setError(msg)
      showToast({ tone: 'danger', title: '诊断失败', message: msg })
    } finally {
      setLoading(false)
    }
  }, [open, diagnosis, projectId, chapterNumber, showToast])

  const toggle = () => {
    if (!open) load()
    else setOpen(false)
  }

  if (chapterStatus === 'planned' || chapterStatus === 'scripted') {
    return null
  }

  const overall = diagnosis?.overall_score ?? null
  const tone = overall === null ? 'idle' : scoreTone(overall)
  const findings = diagnosis?.findings ?? []
  const blockingFindings = findings.filter((f) => f.severity === 'critical' || f.severity === 'high')
  const dimensions = diagnosis ? orderedDimensions(diagnosis.dimensions) : []

  return (
    <section className={`quality-diagnosis qd-${tone}`} aria-label="质量诊断">
      <button type="button" onClick={toggle} className="qd-header" aria-expanded={open}>
        <span className="qd-header-main">
          <span className="qd-icon">
            {overall === null ? <BarChart3 size={18} /> : <CheckCircle2 size={18} />}
          </span>
          <span>
            <span className="qd-title">质量诊断</span>
            <span className="qd-subtitle">
              {overall === null
                ? '按需查看本章文本质量'
                : `${scoreText(overall)} · ${findings.length} 个提示`}
            </span>
          </span>
        </span>
        <span className="qd-header-side">
          {overall !== null && <span className="qd-score-chip">{overall.toFixed(1)}</span>}
          <ChevronDown className={`qd-chevron${open ? ' open' : ''}`} size={18} />
        </span>
      </button>

      {open && (
        <div className="qd-body">
          {loading && !diagnosis && (
            <div className="qd-loading">
              <SkeletonStack rows={4} />
            </div>
          )}

          {error && (
            <InlineMessage variant="danger" title="质量诊断失败">
              {error}
            </InlineMessage>
          )}

          {diagnosis && (
            <>
              <div className="qd-summary">
                <div
                  className="qd-score-ring"
                  style={{
                    background: `conic-gradient(${scoreColor(diagnosis.overall_score)} ${Math.min(diagnosis.overall_score, 100)}%, rgba(148, 163, 184, 0.18) 0)`,
                  }}
                >
                  <span>{diagnosis.overall_score.toFixed(0)}</span>
                </div>
                <div className="qd-summary-copy">
                  <div className="qd-summary-title">{scoreText(diagnosis.overall_score)}</div>
                  <div className="qd-summary-meta">
                    {blockingFindings.length > 0
                      ? `${blockingFindings.length} 个高优先级问题需要先处理`
                      : '未发现高优先级阻断项'}
                  </div>
                </div>
                <LoadingButton
                  variant="secondary"
                  loading={loading}
                  loadingText="刷新中"
                  onClick={() => load(true)}
                >
                  重新诊断
                </LoadingButton>
              </div>

              <div className="qd-metrics">
                <span><strong>{diagnosis.metrics.word_count}</strong> 字</span>
                <span><strong>{diagnosis.metrics.paragraph_count}</strong> 段</span>
                <span><strong>{diagnosis.metrics.sentence_count}</strong> 句</span>
                <span>均句 <strong>{diagnosis.metrics.avg_sentence_length.toFixed(1)}</strong></span>
                <span>对白 <strong>{(diagnosis.metrics.dialogue_ratio * 100).toFixed(1)}%</strong></span>
              </div>

              <div className="qd-dimensions">
                {dimensions.map(([key, score]) => (
                  <div key={key} className={`qd-dimension qd-dimension-${scoreTone(score)}`}>
                    <div className="qd-dimension-top">
                      <span>{dimensionLabel(key)}</span>
                      <strong>{score.toFixed(0)}</strong>
                    </div>
                    <div className="qd-bar">
                      <span style={{ width: `${Math.min(Math.max(score, 0), 100)}%` }} />
                    </div>
                  </div>
                ))}
              </div>

              {findings.length > 0 ? (
                <div className="qd-findings">
                  <div className="qd-section-title">发现的问题</div>
                  {findings.slice(0, 6).map((finding, index) => {
                    const Icon = severityIcon(finding.severity)
                    return (
                      <div key={`${finding.code}-${index}`} className={`qd-finding qd-finding-${finding.severity}`}>
                        <Icon size={16} />
                        <div className="qd-finding-copy">
                          <div className="qd-finding-title">
                            <span>{severityLabel(finding.severity)}</span>
                            {finding.message}
                          </div>
                          {finding.suggestion && (
                            <div className="qd-finding-suggestion">{finding.suggestion}</div>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="qd-empty">暂无明显问题。</div>
              )}
            </>
          )}
        </div>
      )}

      <style>{`
        .quality-diagnosis {
          margin: 0 0 16px;
          border: 1px solid rgba(148, 163, 184, 0.28);
          border-radius: 8px;
          background: #fff;
          overflow: hidden;
          box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
        }
        .qd-header {
          width: 100%;
          border: 0;
          background: #fff;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
          padding: 14px 16px;
          cursor: pointer;
          text-align: left;
        }
        .qd-header:hover {
          background: rgba(248, 250, 252, 0.9);
        }
        .qd-header-main,
        .qd-header-side {
          display: flex;
          align-items: center;
          gap: 10px;
          min-width: 0;
        }
        .qd-icon {
          width: 34px;
          height: 34px;
          border-radius: 50%;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          background: rgba(148, 163, 184, 0.13);
          color: #64748b;
          flex-shrink: 0;
        }
        .qd-title {
          display: block;
          font-size: 14px;
          font-weight: 700;
          color: var(--text-primary);
        }
        .qd-subtitle {
          display: block;
          margin-top: 2px;
          font-size: 12px;
          color: var(--text-muted);
        }
        .qd-score-chip {
          min-width: 52px;
          padding: 4px 8px;
          border-radius: 999px;
          font-size: 13px;
          font-weight: 800;
          text-align: center;
          background: rgba(148, 163, 184, 0.12);
          color: var(--text-primary);
        }
        .qd-chevron {
          color: var(--text-muted);
          transition: transform 0.16s ease;
        }
        .qd-chevron.open {
          transform: rotate(180deg);
        }
        .qd-strong .qd-icon,
        .qd-strong .qd-score-chip {
          background: #dcfce7;
          color: #15803d;
        }
        .qd-ok .qd-icon,
        .qd-ok .qd-score-chip {
          background: #fef3c7;
          color: #b45309;
        }
        .qd-weak .qd-icon,
        .qd-weak .qd-score-chip {
          background: #ffedd5;
          color: #c2410c;
        }
        .qd-bad .qd-icon,
        .qd-bad .qd-score-chip {
          background: #fee2e2;
          color: #b91c1c;
        }
        .qd-body {
          border-top: 1px solid rgba(148, 163, 184, 0.22);
          padding: 16px;
          display: flex;
          flex-direction: column;
          gap: 14px;
        }
        .qd-loading {
          padding: 6px 0;
        }
        .qd-summary {
          display: grid;
          grid-template-columns: auto minmax(0, 1fr) auto;
          gap: 14px;
          align-items: center;
          padding: 14px;
          border: 1px solid rgba(148, 163, 184, 0.18);
          border-radius: 8px;
          background: linear-gradient(180deg, rgba(248, 250, 252, 0.92), rgba(255, 255, 255, 0.95));
        }
        .qd-score-ring {
          width: 58px;
          height: 58px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          position: relative;
          flex-shrink: 0;
        }
        .qd-score-ring::after {
          content: '';
          position: absolute;
          inset: 6px;
          border-radius: 50%;
          background: #fff;
        }
        .qd-score-ring span {
          position: relative;
          z-index: 1;
          font-size: 19px;
          font-weight: 850;
          color: var(--text-primary);
        }
        .qd-summary-title {
          font-size: 15px;
          font-weight: 750;
          color: var(--text-primary);
        }
        .qd-summary-meta {
          margin-top: 3px;
          font-size: 12px;
          color: var(--text-secondary);
        }
        .qd-metrics {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        .qd-metrics span {
          padding: 5px 8px;
          border-radius: 999px;
          background: rgba(148, 163, 184, 0.1);
          color: var(--text-secondary);
          font-size: 12px;
        }
        .qd-metrics strong {
          color: var(--text-primary);
        }
        .qd-dimensions {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 10px;
        }
        .qd-dimension {
          padding: 10px;
          border: 1px solid rgba(148, 163, 184, 0.18);
          border-radius: 8px;
          background: #fff;
        }
        .qd-dimension-top {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
          font-size: 12px;
          color: var(--text-secondary);
        }
        .qd-dimension-top strong {
          font-size: 13px;
          color: var(--text-primary);
          font-variant-numeric: tabular-nums;
        }
        .qd-bar {
          margin-top: 8px;
          height: 5px;
          border-radius: 999px;
          overflow: hidden;
          background: rgba(148, 163, 184, 0.16);
        }
        .qd-bar span {
          display: block;
          height: 100%;
          border-radius: inherit;
          background: #16a34a;
        }
        .qd-dimension-ok .qd-bar span { background: #f59e0b; }
        .qd-dimension-weak .qd-bar span { background: #f97316; }
        .qd-dimension-bad .qd-bar span { background: #ef4444; }
        .qd-section-title {
          font-size: 12px;
          font-weight: 750;
          color: var(--text-secondary);
          margin-bottom: 8px;
        }
        .qd-findings {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .qd-finding {
          display: grid;
          grid-template-columns: auto minmax(0, 1fr);
          gap: 9px;
          padding: 10px 12px;
          border-radius: 8px;
          background: rgba(248, 250, 252, 0.92);
          color: var(--text-secondary);
        }
        .qd-finding svg {
          margin-top: 2px;
          color: #64748b;
        }
        .qd-finding-critical,
        .qd-finding-high {
          background: #fff7ed;
        }
        .qd-finding-critical svg,
        .qd-finding-high svg {
          color: #c2410c;
        }
        .qd-finding-medium {
          background: #fffbeb;
        }
        .qd-finding-medium svg {
          color: #d97706;
        }
        .qd-finding-title {
          font-size: 13px;
          color: var(--text-primary);
          line-height: 1.45;
        }
        .qd-finding-title span {
          margin-right: 7px;
          font-size: 11px;
          font-weight: 800;
          color: #92400e;
        }
        .qd-finding-suggestion {
          margin-top: 4px;
          font-size: 12px;
          line-height: 1.45;
          color: var(--text-secondary);
        }
        .qd-empty {
          padding: 12px;
          border-radius: 8px;
          background: #f0fdf4;
          color: #166534;
          font-size: 13px;
        }
        @media (max-width: 920px) {
          .qd-dimensions {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
          .qd-summary {
            grid-template-columns: auto minmax(0, 1fr);
          }
          .qd-summary button {
            grid-column: 1 / -1;
            width: fit-content;
          }
        }
      `}</style>
    </section>
  )
}
