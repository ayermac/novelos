import { useState, useCallback } from 'react'
import { get } from '../../lib/api'
import { ChevronDown, ChevronUp, AlertCircle, AlertTriangle, Info, CheckCircle2 } from 'lucide-react'

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

const severityConfig: Record<string, { icon: typeof AlertCircle; color: string; label: string }> = {
  critical: { icon: AlertCircle, color: 'text-red-600', label: '致命' },
  high: { icon: AlertTriangle, color: 'text-orange-500', label: '严重' },
  medium: { icon: AlertTriangle, color: 'text-yellow-500', label: '中等' },
  info: { icon: Info, color: 'text-blue-500', label: '提示' },
}

function dimensionLabel(key: string): string {
  const map: Record<string, string> = {
    death_penalty: '死刑红线',
    ai_trace: 'AI 痕迹',
    narrative_quality: '叙事质量',
    conflict_intensity: '冲突强度',
    hook_strength: '钩子强度',
    information_density: '信息密度',
    pacing_control: '节奏控制',
    dialogue_naturalness: '对白自然度',
    scene_immersion: '场景沉浸',
    character_motivation: '人物动机',
    show_dont_tell: "Show-Don't-Tell",
    info_density: '信息密度(设定)',
  }
  return map[key] || key
}

function scoreColor(score: number): string {
  if (score >= 80) return 'text-green-600'
  if (score >= 60) return 'text-yellow-600'
  if (score >= 40) return 'text-orange-500'
  return 'text-red-500'
}

function scoreBarColor(score: number): string {
  if (score >= 80) return 'bg-green-500'
  if (score >= 60) return 'bg-yellow-500'
  if (score >= 40) return 'bg-orange-400'
  return 'bg-red-500'
}

export default function QualityDiagnosisPanel({
  projectId,
  chapterNumber,
  chapterStatus,
}: QualityDiagnosisPanelProps) {
  const [open, setOpen] = useState(false)
  const [diagnosis, setDiagnosis] = useState<QualityDiagnosis | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
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
      } else {
        setError(res.error?.message || '诊断失败')
      }
    } catch {
      setError('请求失败')
    } finally {
      setLoading(false)
    }
  }, [open, diagnosis, projectId, chapterNumber])

  const toggle = () => {
    if (!open) {
      load()
    } else {
      setOpen(false)
    }
  }

  // Don't show for chapters without content
  if (chapterStatus === 'planned' || chapterStatus === 'scripted') {
    return null
  }

  return (
    <div className="quality-diagnosis-panel mt-4 border rounded-lg bg-white">
      <button
        onClick={toggle}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-2">
          {diagnosis ? (
            <CheckCircle2 className={`w-4 h-4 ${scoreColor(diagnosis.overall_score)}`} />
          ) : (
            <Info className="w-4 h-4 text-gray-400" />
          )}
          <span className="font-medium text-sm">质量诊断</span>
          {diagnosis && (
            <span className={`text-sm font-bold ${scoreColor(diagnosis.overall_score)}`}>
              {diagnosis.overall_score.toFixed(1)}
            </span>
          )}
        </div>
        {open ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
      </button>

      {open && (
        <div className="px-4 pb-4 border-t">
          {loading && <div className="py-4 text-sm text-gray-500">正在诊断...</div>}
          {error && <div className="py-4 text-sm text-red-500">{error}</div>}
          {diagnosis && (
            <div className="space-y-4 pt-3">
              {/* Overall score */}
              <div className="flex items-center gap-3">
                <div className="text-2xl font-bold ${scoreColor(diagnosis.overall_score)}">
                  {diagnosis.overall_score.toFixed(1)}
                </div>
                <div className="text-xs text-gray-500">
                  综合评分 / 100
                </div>
              </div>

              {/* Dimensions */}
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(diagnosis.dimensions).map(([key, score]) => (
                  <div key={key} className="flex items-center gap-2">
                    <div className="text-xs text-gray-600 w-20 truncate">{dimensionLabel(key)}</div>
                    <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className={`h-full ${scoreBarColor(score)} rounded-full`}
                        style={{ width: `${Math.min(score, 100)}%` }}
                      />
                    </div>
                    <div className={`text-xs font-medium w-8 text-right ${scoreColor(score)}`}>
                      {score.toFixed(0)}
                    </div>
                  </div>
                ))}
              </div>

              {/* Metrics */}
              <div className="flex flex-wrap gap-3 text-xs text-gray-500">
                <span>字数 {diagnosis.metrics.word_count}</span>
                <span>段落 {diagnosis.metrics.paragraph_count}</span>
                <span>句子 {diagnosis.metrics.sentence_count}</span>
                <span>平均句长 {diagnosis.metrics.avg_sentence_length}</span>
                <span>对话占比 {(diagnosis.metrics.dialogue_ratio * 100).toFixed(1)}%</span>
              </div>

              {/* Findings */}
              {diagnosis.findings.length > 0 && (
                <div className="space-y-2">
                  <div className="text-xs font-medium text-gray-700">发现的问题</div>
                  {diagnosis.findings.map((f, i) => {
                    const cfg = severityConfig[f.severity] || severityConfig.info
                    const Icon = cfg.icon
                    return (
                      <div key={i} className="flex gap-2 text-sm p-2 rounded bg-gray-50">
                        <Icon className={`w-4 h-4 flex-shrink-0 mt-0.5 ${cfg.color}`} />
                        <div className="flex-1 min-w-0">
                          <div className="text-gray-800">{f.message}</div>
                          {f.suggestion && (
                            <div className="text-xs text-gray-500 mt-1">建议：{f.suggestion}</div>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
