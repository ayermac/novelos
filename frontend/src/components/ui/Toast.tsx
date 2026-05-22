import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { AlertCircle, CheckCircle2, Info, X, XCircle } from 'lucide-react'
import { ToastContext } from './ToastContext'
import type { ToastInput, ToastTone } from './ToastContext'

interface ToastRecord extends ToastInput {
  id: number
  tone: ToastTone
}

const icons = {
  success: CheckCircle2,
  info: Info,
  warning: AlertCircle,
  danger: XCircle,
}

function ToastItem({ toast, onDismiss }: { toast: ToastRecord; onDismiss: (id: number) => void }) {
  const Icon = icons[toast.tone]

  useEffect(() => {
    if (toast.durationMs === 0) return undefined
    const timer = window.setTimeout(() => onDismiss(toast.id), toast.durationMs ?? 4200)
    return () => window.clearTimeout(timer)
  }, [toast.durationMs, toast.id, onDismiss])

  return (
    <div className={`ui-toast ui-toast-${toast.tone}`} role={toast.tone === 'danger' ? 'alert' : 'status'}>
      <Icon size={18} aria-hidden="true" />
      <div className="ui-toast-copy">
        <strong>{toast.title}</strong>
        {toast.message ? <div>{toast.message}</div> : null}
      </div>
      <button type="button" className="ui-toast-close" onClick={() => onDismiss(toast.id)} aria-label="关闭通知">
        <X size={16} aria-hidden="true" />
      </button>
    </div>
  )
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastRecord[]>([])
  const idRef = useRef(0)

  const dismissToast = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const showToast = useCallback((toast: ToastInput) => {
    const id = idRef.current + 1
    idRef.current = id
    setToasts((current) => [
      ...current.slice(-3),
      {
        ...toast,
        id,
        tone: toast.tone ?? 'info',
      },
    ])
    return id
  }, [])

  const value = useMemo(() => ({ showToast, dismissToast }), [dismissToast, showToast])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="ui-toast-region" aria-live="polite" aria-relevant="additions text">
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onDismiss={dismissToast} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}
