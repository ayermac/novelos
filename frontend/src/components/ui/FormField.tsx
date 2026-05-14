import { cloneElement, isValidElement, useId } from 'react'
import type { ReactElement, ReactNode } from 'react'

interface FormFieldProps {
  label?: ReactNode
  htmlFor?: string
  helper?: ReactNode
  error?: ReactNode
  required?: boolean
  children: ReactNode
  className?: string
}

export function FormField({ label, htmlFor, helper, error, required = false, children, className = '' }: FormFieldProps) {
  const generatedId = useId()
  const child = isValidElement(children) ? children as ReactElement<{
    id?: string
    invalid?: boolean
    'aria-describedby'?: string
    'aria-invalid'?: boolean | 'true' | 'false' | 'grammar' | 'spelling'
  }> : null
  const controlId = htmlFor || child?.props.id || generatedId
  const descriptionId = error ? `${controlId}-error` : helper ? `${controlId}-helper` : undefined
  const describedBy = [
    child?.props['aria-describedby'],
    descriptionId,
  ].filter(Boolean).join(' ') || undefined
  const control = child
    ? cloneElement(child, {
        id: child.props.id || controlId,
        invalid: error ? true : child.props.invalid,
        'aria-describedby': describedBy,
        'aria-invalid': error ? true : child.props['aria-invalid'],
      })
    : children

  return (
    <div className={`ui-form-field ${className}`.trim()}>
      {label ? (
        <label className="ui-form-label" htmlFor={controlId}>
          <span>{label}</span>
          {required ? <span className="ui-form-required" aria-hidden="true">*</span> : null}
        </label>
      ) : null}
      {control}
      {error ? (
        <div id={descriptionId} className="ui-form-error">{error}</div>
      ) : helper ? (
        <div id={descriptionId} className="ui-form-helper">{helper}</div>
      ) : null}
    </div>
  )
}
