import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react'
import {
  AppDialogContext,
  BaseDialogOptions,
  DialogTone,
  PromptDialogOptions,
  normalizeDialogOptions,
  type AppDialogApi,
} from './AppDialogContext'

type DialogRequest =
  | (BaseDialogOptions & { kind: 'alert'; resolve: () => void })
  | (BaseDialogOptions & { kind: 'confirm'; resolve: (value: boolean) => void })
  | (PromptDialogOptions & { kind: 'prompt'; resolve: (value: string | null) => void })

function toneIcon(tone: DialogTone) {
  switch (tone) {
    case 'success':
      return <CheckCircle2 size={20} />
    case 'warning':
      return <AlertTriangle size={20} />
    case 'danger':
      return <XCircle size={20} />
    case 'info':
    case 'default':
    default:
      return <Info size={20} />
  }
}

export function AppDialogProvider({ children }: { children: ReactNode }) {
  const [dialog, setDialog] = useState<DialogRequest | null>(null)
  const [inputValue, setInputValue] = useState('')
  const confirmRef = useRef<HTMLButtonElement | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const close = useCallback(() => setDialog(null), [])

  const cancel = useCallback(() => {
    if (!dialog) return
    if (dialog.kind === 'alert') dialog.resolve()
    if (dialog.kind === 'confirm') dialog.resolve(false)
    if (dialog.kind === 'prompt') dialog.resolve(null)
    close()
  }, [close, dialog])

  const accept = useCallback(() => {
    if (!dialog) return
    if (dialog.kind === 'alert') dialog.resolve()
    if (dialog.kind === 'confirm') dialog.resolve(true)
    if (dialog.kind === 'prompt') dialog.resolve(inputValue.trim())
    close()
  }, [close, dialog, inputValue])

  const api = useMemo<AppDialogApi>(() => ({
    alert: (options) => new Promise<void>((resolve) => {
      setDialog({ ...normalizeDialogOptions(options), kind: 'alert', resolve })
    }),
    confirm: (options) => new Promise<boolean>((resolve) => {
      setDialog({ ...normalizeDialogOptions(options), kind: 'confirm', resolve })
    }),
    prompt: (options) => new Promise<string | null>((resolve) => {
      setInputValue(options.initialValue || '')
      setDialog({ ...options, kind: 'prompt', resolve })
    }),
  }), [])

  useEffect(() => {
    if (!dialog) return
    const id = window.setTimeout(() => {
      if (dialog.kind === 'prompt') inputRef.current?.focus()
      else confirmRef.current?.focus()
    }, 0)
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') cancel()
      if (event.key === 'Enter' && dialog.kind === 'prompt' && document.activeElement === inputRef.current) {
        accept()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.clearTimeout(id)
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [accept, cancel, dialog])

  const renderedDialog = dialog && typeof document !== 'undefined'
    ? createPortal(
      <div className="app-dialog-overlay" role="presentation" onMouseDown={cancel}>
        <div
          className={`app-dialog app-dialog-${dialog.tone || 'default'}`}
          role="dialog"
          aria-modal="true"
          aria-labelledby="app-dialog-title"
          onMouseDown={(event) => event.stopPropagation()}
        >
          <div className="app-dialog-head">
            <div className="app-dialog-icon" aria-hidden="true">{toneIcon(dialog.tone || 'default')}</div>
            <div className="app-dialog-copy">
              <h2 id="app-dialog-title">{dialog.title || (dialog.kind === 'alert' ? '提示' : '确认操作')}</h2>
              <div className="app-dialog-message">{dialog.message}</div>
            </div>
            <button className="app-dialog-close" type="button" aria-label="关闭弹窗" onClick={cancel}>
              <X size={16} />
            </button>
          </div>

          {dialog.details && <div className="app-dialog-details">{dialog.details}</div>}

          {dialog.kind === 'prompt' && (
            <label className="app-dialog-field">
              <span>项目 ID</span>
              <input
                ref={inputRef}
                value={inputValue}
                placeholder={dialog.placeholder}
                onChange={(event) => setInputValue(event.target.value)}
              />
            </label>
          )}

          <div className="app-dialog-actions">
            {dialog.kind !== 'alert' && (
              <button className="btn btn-secondary" type="button" onClick={cancel}>
                {dialog.cancelLabel || '取消'}
              </button>
            )}
            <button
              ref={confirmRef}
              className={`btn ${dialog.tone === 'danger' ? 'btn-danger' : 'btn-primary'}`}
              type="button"
              onClick={accept}
            >
              {dialog.confirmLabel || (dialog.kind === 'alert' ? '知道了' : '确认')}
            </button>
          </div>
        </div>
      </div>,
      document.body,
    )
    : null

  return (
    <AppDialogContext.Provider value={api}>
      {children}
      {renderedDialog}
    </AppDialogContext.Provider>
  )
}
