import { AlertTriangle, RefreshCw } from 'lucide-react'

interface ErrorStateProps {
  title?: string
  message: string
  onRetry?: () => void
}

export default function ErrorState({
  title = '加载失败',
  message,
  onRetry,
}: ErrorStateProps) {
  return (
    <div className="error-state">
      <AlertTriangle size={40} className="error-icon" />
      <div className="error-title">{title}</div>
      <div className="error-message">{message}</div>
      {onRetry && (
        <button onClick={onRetry} className="btn btn-secondary mt-3">
          <RefreshCw size={14} />
          重试
        </button>
      )}
    </div>
  )
}
