import { Link } from 'react-router-dom'
import { AlertCircle } from 'lucide-react'

interface EmptyStateProps {
  title: string
  hint: string
  action?: {
    label: string
    to: string
  }
  actions?: Array<{
    label: string
    to: string
  }>
}

export default function EmptyState({ title, hint, action, actions }: EmptyStateProps) {
  // Use actions if provided, otherwise fall back to single action
  const buttonActions = actions && actions.length > 0 ? actions : action ? [action] : []

  return (
    <div className="empty-state">
      <AlertCircle size={40} className="empty-icon" />
      <div className="empty-title">{title}</div>
      <div className="empty-hint">{hint}</div>
      {buttonActions.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '12px', alignItems: 'center' }}>
          {buttonActions.map((btn, idx) => (
            <Link
              key={idx}
              to={btn.to}
              className={idx === 0 ? 'btn btn-primary' : 'btn btn-secondary'}
            >
              {btn.label}
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
