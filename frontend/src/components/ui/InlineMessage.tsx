import type { ReactNode } from 'react'
import { AlertCircle, CheckCircle2, Info, XCircle } from 'lucide-react'

type InlineMessageVariant = 'info' | 'success' | 'warning' | 'danger'

interface InlineMessageProps {
  variant?: InlineMessageVariant
  title?: ReactNode
  children: ReactNode
  className?: string
}

const icons = {
  info: Info,
  success: CheckCircle2,
  warning: AlertCircle,
  danger: XCircle,
}

export function InlineMessage({ variant = 'info', title, children, className = '' }: InlineMessageProps) {
  const Icon = icons[variant]
  return (
    <div className={`ui-inline-message ui-inline-${variant} ${className}`.trim()} role={variant === 'danger' ? 'alert' : 'status'}>
      <Icon size={16} aria-hidden="true" />
      <div>
        {title ? <strong>{title}</strong> : null}
        <div>{children}</div>
      </div>
    </div>
  )
}
