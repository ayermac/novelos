import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Spinner } from './Spinner'

export interface LoadingButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  loading?: boolean
  loadingText?: ReactNode
  variant?: 'primary' | 'secondary' | 'accent' | 'ghost'
}

export function LoadingButton({
  loading = false,
  loadingText,
  variant = 'primary',
  className = '',
  children,
  disabled,
  type = 'button',
  ...props
}: LoadingButtonProps) {
  const variantClass = variant === 'ghost' ? 'btn-secondary ui-btn-ghost' : `btn-${variant}`
  const label = loading && loadingText ? loadingText : children

  return (
    <button
      type={type}
      className={`btn ${variantClass} ui-loading-button ${loading ? 'is-loading' : ''} ${className}`.trim()}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading ? <Spinner size="sm" label="" className="ui-loading-button-spinner" /> : null}
      <span>{label}</span>
    </button>
  )
}
