import { tStatus, statusClass } from '../lib/i18n'

interface StatusBadgeProps {
  status: string | undefined | null
  className?: string
}

export default function StatusBadge({ status, className = '' }: StatusBadgeProps) {
  const cls = statusClass(status)
  const label = tStatus(status)

  return (
    <span className={`status-badge status-${cls} ${className}`}>
      {label}
    </span>
  )
}
