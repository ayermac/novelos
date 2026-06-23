import { useState, useCallback } from 'react'
import { post } from '../../lib/api'
import { AlertCircle, AlertTriangle, Info, CheckCircle2, Activity, RefreshCw } from 'lucide-react'
import { InlineMessage, LoadingButton, useToast } from '../ui'

interface ArchitectureDiagnosisPanelProps {
  projectId: string
}

interface DiagnosisFinding {
  dimension: string
  severity: 'critical' | 'warning' | 'info'
  confidence: 'high' | 'medium' | 'low'
  message: string
  evidence?: string
  suggestion?: string
  auto_level?: string
}

interface DiagnosisResponse {
  project_id: string
  findings: DiagnosisFinding[]
  total: number
}

const DIMENSION_LABELS: Record<string, string> = {
  flow: '流程',
  quality: '质量',
  planning: '规划',
  memory: '记忆',
}

const SEVERITY_ICONS: Record<string, typeof AlertCircle> = {
  critical: AlertCircle,
  warning: AlertTriangle,
  info: Info,
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'text-red-500',
  warning: 'text-yellow-500',
  info: 'text-blue-500',
}

export function ArchitectureDiagnosisPanel({ projectId }: ArchitectureDiagnosisPanelProps) {
  const [findings, setFindings] = useState<DiagnosisFinding[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastRun, setLastRun] = useState<string | null>(null)
  const { showToast } = useToast()

  const runDiagnosis = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await post<DiagnosisResponse>('/api/v61013/diagnosis', {
        project_id: projectId,
      })

      if (response.ok && response.data) {
        setFindings(response.data.findings)
        setLastRun(new Date().toLocaleTimeString())

        if (response.data.findings.length === 0) {
          showToast({
            title: '诊断完成',
            message: '未发现任何问题',
            tone: 'success',
          })
        }
      } else {
        const message = response.error?.message || '诊断失败'
        setError(message)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '诊断失败'
      setError(message)
      showToast({
        title: '诊断失败',
        message,
        tone: 'danger',
      })
    } finally {
      setLoading(false)
    }
  }, [projectId, showToast])

  // Group findings by dimension
  const groupedFindings = findings.reduce((acc, finding) => {
    const dim = finding.dimension
    if (!acc[dim]) acc[dim] = []
    acc[dim].push(finding)
    return acc
  }, {} as Record<string, DiagnosisFinding[]>)

  // Count by severity
  const severityCounts = findings.reduce((acc, finding) => {
    acc[finding.severity] = (acc[finding.severity] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-purple-500" />
          <h3 className="text-lg font-semibold">架构诊断</h3>
          {lastRun && (
            <span className="text-sm text-gray-500">上次运行: {lastRun}</span>
          )}
        </div>
        <LoadingButton
          onClick={runDiagnosis}
          loading={loading}
          disabled={loading}
          className="flex items-center gap-2"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          运行诊断
        </LoadingButton>
      </div>

      {error && (
        <InlineMessage variant="danger" className="mb-4">
          {error}
        </InlineMessage>
      )}

      {loading && !findings.length ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-12 bg-gray-100 rounded animate-pulse" />
          ))}
        </div>
      ) : findings.length === 0 ? (
        <div className="text-center py-8 text-gray-500">
          <CheckCircle2 className="w-12 h-12 mx-auto mb-2 text-green-400" />
          <p>点击"运行诊断"检查项目状态</p>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Summary */}
          <div className="flex gap-4 p-3 bg-gray-50 rounded-lg">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">总计:</span>
              <span className="text-sm">{findings.length} 项</span>
            </div>
            {severityCounts.critical > 0 && (
              <div className="flex items-center gap-1 text-red-500">
                <AlertCircle className="w-4 h-4" />
                <span className="text-sm">{severityCounts.critical} 严重</span>
              </div>
            )}
            {severityCounts.warning > 0 && (
              <div className="flex items-center gap-1 text-yellow-500">
                <AlertTriangle className="w-4 h-4" />
                <span className="text-sm">{severityCounts.warning} 警告</span>
              </div>
            )}
            {severityCounts.info > 0 && (
              <div className="flex items-center gap-1 text-blue-500">
                <Info className="w-4 h-4" />
                <span className="text-sm">{severityCounts.info} 提示</span>
              </div>
            )}
          </div>

          {/* Findings by dimension */}
          {Object.entries(groupedFindings).map(([dimension, dimFindings]) => (
            <div key={dimension} className="border rounded-lg p-3">
              <h4 className="font-medium mb-2 flex items-center gap-2">
                <span className="text-sm bg-gray-100 px-2 py-1 rounded">
                  {DIMENSION_LABELS[dimension] || dimension}
                </span>
                <span className="text-sm text-gray-500">{dimFindings.length} 项</span>
              </h4>
              <div className="space-y-2">
                {dimFindings.map((finding, idx) => {
                  const Icon = SEVERITY_ICONS[finding.severity] || Info
                  const color = SEVERITY_COLORS[finding.severity] || 'text-gray-500'

                  return (
                    <div key={idx} className="flex gap-2 text-sm">
                      <Icon className={`w-4 h-4 mt-0.5 flex-shrink-0 ${color}`} />
                      <div>
                        <p className="text-gray-700">{finding.message}</p>
                        {finding.evidence && (
                          <p className="text-gray-500 text-xs mt-1">
                            证据: {finding.evidence}
                          </p>
                        )}
                        {finding.suggestion && (
                          <p className="text-blue-600 text-xs mt-1">
                            建议: {finding.suggestion}
                          </p>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
