import { forwardRef } from 'react'
import type { InputHTMLAttributes } from 'react'

export interface TextInputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean
}

export const TextInput = forwardRef<HTMLInputElement, TextInputProps>(function TextInput(
  { className = '', invalid = false, type = 'text', ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      type={type}
      className={`ui-control ui-text-input ${invalid ? 'is-invalid' : ''} ${className}`.trim()}
      aria-invalid={invalid || props['aria-invalid']}
      {...props}
    />
  )
})
