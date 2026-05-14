import { forwardRef } from 'react'
import type { TextareaHTMLAttributes } from 'react'

export interface TextAreaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean
}

export const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(function TextArea(
  { className = '', invalid = false, ...props },
  ref,
) {
  return (
    <textarea
      ref={ref}
      className={`ui-control ui-text-area ${invalid ? 'is-invalid' : ''} ${className}`.trim()}
      aria-invalid={invalid || props['aria-invalid']}
      {...props}
    />
  )
})
