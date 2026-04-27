import { Link } from 'react-router-dom'
import { AlertCircle } from 'lucide-react'

interface EmptyStateProps {
  title: string
  hint: string
  action?: {
    label: string
    to: string
  }
}

export default function EmptyState({ title, hint, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <AlertCircle size={40} className="empty-icon" />
      <div className="empty-title">{title}</div>
      <div className="empty-hint">{hint}</div>
      {action && (
        <div className="flex gap-2 mt-3" style={{ justifyContent: 'center' }}>
          <Link to={action.to} className="btn btn-primary">
            {action.label}
          </Link>
        </div>
      )}
    </div>
  )
}
