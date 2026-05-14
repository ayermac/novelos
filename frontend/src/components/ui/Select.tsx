import { forwardRef } from 'react'
import type { SelectHTMLAttributes } from 'react'
import { ChevronDown } from 'lucide-react'

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  invalid?: boolean
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className = '', invalid = false, children, ...props },
  ref,
) {
  return (
    <span className={`ui-select-shell ${props.disabled ? 'is-disabled' : ''} ${invalid ? 'is-invalid' : ''}`.trim()}>
      <select
        ref={ref}
        className={`ui-control ui-select ${className}`.trim()}
        aria-invalid={invalid || props['aria-invalid']}
        {...props}
      >
        {children}
      </select>
      <ChevronDown aria-hidden="true" size={16} className="ui-select-icon" />
    </span>
  )
})
