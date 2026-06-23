import { useState, useCallback, useEffect } from 'react'
import { get, put } from '../../lib/api'
import { DollarSign, AlertTriangle, Settings, Save } from 'lucide-react'
import { LoadingButton, useToast } from '../ui'

interface BudgetMonitorPanelProps {
  projectId: string
}

interface BudgetStatus {
  state: string
  total_cost: number
  limit_usd: number
  remaining_usd: number
  usage_percent: number
  zero_streak: number
}

const STATE_LABELS: Record<string, { label: string; color: string }> = {
  normal: { label: '正常', color: 'text-green-500' },
  warned: { label: '已警告', color: 'text-yellow-500' },
  stop_pending: { label: '即将停机', color: 'text-orange-500' },
  stopped: { label: '已停机', color: 'text-red-500' },
}

export function BudgetMonitorPanel({ projectId }: BudgetMonitorPanelProps) {
  const [status, setStatus] = useState<BudgetStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState(false)
  const [newLimit, setNewLimit] = useState('')
  const [saving, setSaving] = useState(false)
  const { showToast } = useToast()

  const fetchStatus = useCallback(async () => {
    setLoading(true)
    try {
      const response = await get<BudgetStatus>(`/api/v61013/budget/${projectId}`)
      if (response.ok && response.data) {
        setStatus(response.data)
      }
    } catch (err) {
      console.error('Failed to fetch budget status:', err)
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(fetchStatus, 30000)
    return () => clearInterval(interval)
  }, [fetchStatus])

  const handleSaveLimit = useCallback(async () => {
    const limit = parseFloat(newLimit)
    if (isNaN(limit) || limit <= 0) {
      showToast({
        title: '无效金额',
        message: '请输入有效的预算金额',
        tone: 'danger',
      })
      return
    }

    setSaving(true)
    try {
      const response = await put(`/api/v61013/budget/${projectId}`, { limit_usd: limit })
      if (response.ok) {
        showToast({
          title: '预算已更新',
          message: `预算上限已设置为 $${limit.toFixed(2)}`,
          tone: 'success',
        })
        setEditing(false)
        setNewLimit('')
        fetchStatus()
      } else {
        showToast({
          title: '更新失败',
          message: response.error?.message || '无法更新预算设置',
          tone: 'danger',
        })
      }
    } catch (err) {
      showToast({
        title: '更新失败',
        message: '无法更新预算设置',
        tone: 'danger',
      })
    } finally {
      setSaving(false)
    }
  }, [projectId, newLimit, showToast, fetchStatus])

  if (!status) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <div className="flex items-center gap-2 mb-4">
          <DollarSign className="w-5 h-5 text-green-500" />
          <h3 className="text-lg font-semibold">预算监控</h3>
        </div>
        <div className="text-center py-4 text-gray-500">
          {loading ? '加载中...' : '无法加载预算信息'}
        </div>
      </div>
    )
  }

  const stateInfo = STATE_LABELS[status.state] || { label: status.state, color: 'text-gray-500' }
  const isWarning = status.state === 'warned' || status.state === 'stop_pending'
  const isStopped = status.state === 'stopped'

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <DollarSign className="w-5 h-5 text-green-500" />
          <h3 className="text-lg font-semibold">预算监控</h3>
        </div>
        <button
          onClick={() => setEditing(!editing)}
          className="p-1 hover:bg-gray-100 rounded"
        >
          <Settings className="w-4 h-4 text-gray-500" />
        </button>
      </div>

      <div className="flex items-center gap-2 mb-3">
        <span className="text-sm font-medium">状态:</span>
        <span className={`text-sm font-semibold ${stateInfo.color}`}>
          {stateInfo.label}
        </span>
        {status.zero_streak >= 5 && (
          <span className="text-xs text-yellow-600 bg-yellow-50 px-2 py-0.5 rounded">
            计费盲区
          </span>
        )}
      </div>

      <div className="mb-3">
        <div className="flex justify-between text-sm mb-1">
          <span>使用量</span>
          <span>{status.usage_percent.toFixed(1)}%</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className={`h-2 rounded-full transition-all ${
              isStopped ? 'bg-red-500' : isWarning ? 'bg-yellow-500' : 'bg-green-500'
            }`}
            style={{ width: `${Math.min(100, status.usage_percent)}%` }}
          />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 text-center mb-3">
        <div className="bg-gray-50 rounded p-2">
          <p className="text-xs text-gray-500">已花费</p>
          <p className="text-sm font-semibold">${status.total_cost.toFixed(2)}</p>
        </div>
        <div className="bg-gray-50 rounded p-2">
          <p className="text-xs text-gray-500">剩余</p>
          <p className={`text-sm font-semibold ${status.remaining_usd < 10 ? 'text-red-500' : ''}`}>
            ${status.remaining_usd.toFixed(2)}
          </p>
        </div>
        <div className="bg-gray-50 rounded p-2">
          <p className="text-xs text-gray-500">上限</p>
          <p className="text-sm font-semibold">${status.limit_usd.toFixed(2)}</p>
        </div>
      </div>

      {editing && (
        <div className="border-t pt-3 mt-3">
          <label className="block text-sm font-medium mb-1">设置新预算上限</label>
          <div className="flex gap-2">
            <input
              type="number"
              value={newLimit}
              onChange={(e) => setNewLimit(e.target.value)}
              placeholder="输入金额 (USD)"
              className="flex-1 px-3 py-2 border rounded-lg text-sm"
              min="0"
              step="10"
            />
            <LoadingButton onClick={handleSaveLimit} loading={saving} className="flex items-center gap-1">
              <Save className="w-4 h-4" />
              保存
            </LoadingButton>
          </div>
        </div>
      )}

      {isWarning && (
        <div className="mt-3 p-2 bg-yellow-50 rounded-lg flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-yellow-500 mt-0.5" />
          <p className="text-sm text-yellow-700">
            {status.state === 'stop_pending'
              ? '预算即将耗尽，当前子代理完成后将停止创作'
              : '预算已使用超过 80%，请注意控制成本'}
          </p>
        </div>
      )}

      {isStopped && (
        <div className="mt-3 p-2 bg-red-50 rounded-lg flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5" />
          <p className="text-sm text-red-700">预算已耗尽，创作已停止。请增加预算后重试。</p>
        </div>
      )}

      {status.zero_streak >= 5 && (
        <div className="mt-3 p-2 bg-yellow-50 rounded-lg flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-yellow-500 mt-0.5" />
          <p className="text-sm text-yellow-700">
            模型未返回 usage 数据，成本统计为 0，预算上限不会触发。请确认模型配置或上游 include_usage 设置。
          </p>
        </div>
      )}
    </div>
  )
}
