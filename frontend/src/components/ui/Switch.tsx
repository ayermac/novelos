import { forwardRef } from 'react'
import type { InputHTMLAttributes, ReactNode } from 'react'

export interface SwitchProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: ReactNode
  helper?: ReactNode
}

export const Switch = forwardRef<HTMLInputElement, SwitchProps>(function Switch(
  { className = '', label, helper, disabled, ...props },
  ref,
) {
  return (
    <label className={`ui-switch ${disabled ? 'is-disabled' : ''} ${className}`.trim()}>
      <input ref={ref} type="checkbox" className="ui-switch-input" disabled={disabled} {...props} />
      <span className="ui-switch-track" aria-hidden="true">
        <span className="ui-switch-thumb" />
      </span>
      {label || helper ? (
        <span className="ui-switch-copy">
          {label ? <span className="ui-switch-label">{label}</span> : null}
          {helper ? <span className="ui-form-helper">{helper}</span> : null}
        </span>
      ) : null}
    </label>
  )
})
