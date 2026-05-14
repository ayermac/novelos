import { forwardRef } from 'react'
import type { InputHTMLAttributes } from 'react'

export interface NumberInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  invalid?: boolean
}

export const NumberInput = forwardRef<HTMLInputElement, NumberInputProps>(function NumberInput(
  { className = '', invalid = false, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      type="number"
      className={`ui-control ui-number-input ${invalid ? 'is-invalid' : ''} ${className}`.trim()}
      aria-invalid={invalid || props['aria-invalid']}
      {...props}
    />
  )
})
