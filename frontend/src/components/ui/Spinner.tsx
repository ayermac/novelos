interface SpinnerProps {
  size?: 'sm' | 'md'
  label?: string
  className?: string
}

export function Spinner({ size = 'md', label = '加载中', className = '' }: SpinnerProps) {
  return (
    <span className={`ui-spinner-wrap ui-spinner-${size} ${className}`.trim()} role="status" aria-label={label}>
      <span className="ui-spinner" aria-hidden="true" />
      {label ? <span>{label}</span> : null}
    </span>
  )
}
