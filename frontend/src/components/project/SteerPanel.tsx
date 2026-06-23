import { useState, useCallback } from 'react'
import { post } from '../../lib/api'
import { MessageSquare, Send, CheckCircle2, AlertCircle } from 'lucide-react'
import { LoadingButton, useToast } from '../ui'

interface SteerPanelProps {
  projectId: string
  isRunning?: boolean
  onSteerSubmitted?: () => void
}

interface SteerResponse {
  status: string
  message: string
}

export function SteerPanel({ projectId, isRunning = false, onSteerSubmitted }: SteerPanelProps) {
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [lastResult, setLastResult] = useState<SteerResponse | null>(null)
  const { showToast } = useToast()

  const handleSubmit = useCallback(async () => {
    if (!text.trim()) {
      showToast({
        title: '请输入干预内容',
        message: '干预内容不能为空',
        tone: 'danger',
      })
      return
    }

    setLoading(true)
    try {
      const response = await post<SteerResponse>('/api/v61013/steer', {
        project_id: projectId,
        text: text.trim(),
      })

      if (response.ok && response.data) {
        setLastResult(response.data)
        setText('')
        showToast({
          title: '干预已提交',
          message: response.data.message,
          tone: 'success',
        })
        onSteerSubmitted?.()
      } else {
        showToast({
          title: '提交失败',
          message: response.error?.message || '提交失败',
          tone: 'danger',
        })
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '提交失败'
      showToast({
        title: '提交失败',
        message,
        tone: 'danger',
      })
    } finally {
      setLoading(false)
    }
  }, [projectId, text, showToast, onSteerSubmitted])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <div className="flex items-center gap-2 mb-4">
        <MessageSquare className="w-5 h-5 text-blue-500" />
        <h3 className="text-lg font-semibold">用户干预</h3>
        {isRunning && (
          <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded">创作中</span>
        )}
      </div>

      <p className="text-sm text-gray-600 mb-3">
        {isRunning
          ? '创作过程中可以随时注入修改意见，系统会自动评估影响范围。'
          : '创作已停止，干预将在下次启动时生效。'}
      </p>

      <div className="mb-3">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isRunning ? '例如: 把感情线提前到第4章，增加男女主的对手戏' : '输入干预意见，下次启动时生效'}
          className="w-full px-3 py-2 border rounded-lg text-sm resize-none"
          rows={3}
          disabled={loading}
        />
        <p className="text-xs text-gray-500 mt-1">按 Ctrl+Enter (或 Cmd+Enter) 快速提交</p>
      </div>

      <div className="flex justify-end">
        <LoadingButton onClick={handleSubmit} loading={loading} disabled={!text.trim() || loading} className="flex items-center gap-2">
          <Send className="w-4 h-4" />
          {isRunning ? '注入干预' : '保存干预'}
        </LoadingButton>
      </div>

      {lastResult && (
        <div className={`mt-3 p-2 rounded-lg flex items-start gap-2 ${lastResult.status === 'injected' ? 'bg-green-50' : 'bg-blue-50'}`}>
          {lastResult.status === 'injected' ? (
            <CheckCircle2 className="w-4 h-4 text-green-500 mt-0.5" />
          ) : (
            <AlertCircle className="w-4 h-4 text-blue-500 mt-0.5" />
          )}
          <p className={`text-sm ${lastResult.status === 'injected' ? 'text-green-700' : 'text-blue-700'}`}>
            {lastResult.message}
          </p>
        </div>
      )}

      <div className="mt-4 border-t pt-3">
        <p className="text-xs font-medium text-gray-500 mb-2">干预示例：</p>
        <div className="flex flex-wrap gap-2">
          {['主角改成女性', '把感情线提前到第4章', '加入一个反派角色', '节奏太慢了，加快推进'].map((example) => (
            <button key={example} onClick={() => setText(example)} className="text-xs bg-gray-100 hover:bg-gray-200 px-2 py-1 rounded">
              {example}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
