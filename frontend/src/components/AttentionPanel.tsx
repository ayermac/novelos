import type { CSSProperties, ReactNode } from 'react'

type AttentionTone = 'error' | 'warning' | 'info' | 'success'

const TONE_CLASS: Record<AttentionTone, string> = {
  error: 'alert-error',
  warning: 'alert-warning',
  info: 'alert-info',
  success: 'alert-success',
}

interface AttentionPanelProps {
  title: string
  tone?: AttentionTone
  children?: ReactNode
  actions?: ReactNode
  style?: CSSProperties
}

export default function AttentionPanel({
  title,
  tone = 'info',
  children,
  actions,
  style,
}: AttentionPanelProps) {
  return (
    <div className={`alert ${TONE_CLASS[tone]}`} style={style}>
      <div style={{ fontWeight: 600 }}>{title}</div>
      {children && <div style={{ marginTop: '4px' }}>{children}</div>}
      {actions && <div style={{ marginTop: '12px' }}>{actions}</div>}
    </div>
  )
}

export function ActionHintList({ title, children }: {
  title: string
  children: ReactNode
}) {
  return (
    <div style={{ marginTop: '12px' }}>
      <div style={{ fontWeight: 600, fontSize: '13px' }}>{title}</div>
      <ul style={{ margin: '6px 0 0', paddingLeft: '18px' }}>
        {children}
      </ul>
    </div>
  )
}
