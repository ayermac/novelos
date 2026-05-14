import { forwardRef } from 'react'
import type { InputHTMLAttributes, ReactNode } from 'react'
import { Check } from 'lucide-react'

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: ReactNode
  helper?: ReactNode
  error?: ReactNode
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { className = '', label, helper, error, disabled, ...props },
  ref,
) {
  return (
    <label className={`ui-check ${disabled ? 'is-disabled' : ''} ${error ? 'is-invalid' : ''} ${className}`.trim()}>
      <input ref={ref} type="checkbox" className="ui-check-input" disabled={disabled} aria-invalid={Boolean(error) || props['aria-invalid']} {...props} />
      <span className="ui-check-box" aria-hidden="true">
        <Check size={13} />
      </span>
      <span className="ui-check-copy">
        {label ? <span className="ui-check-label">{label}</span> : null}
        {error ? <span className="ui-form-error">{error}</span> : helper ? <span className="ui-form-helper">{helper}</span> : null}
      </span>
    </label>
  )
})
