import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'

interface PageHeaderProps {
  title: string
  backTo?: string
  backLabel?: string
  actions?: React.ReactNode
}

export default function PageHeader({ title, backTo, backLabel, actions }: PageHeaderProps) {
  return (
    <div className="page-header">
      <div className="page-header-left">
        {backTo && (
          <Link to={backTo} className="btn btn-sm btn-secondary">
            <ArrowLeft size={14} />
            {backLabel || '返回'}
          </Link>
        )}
        <h2>{title}</h2>
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </div>
  )
}
