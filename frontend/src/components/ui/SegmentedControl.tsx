export interface SegmentedOption<T extends string> {
  value: T
  label: string
  disabled?: boolean
}

interface SegmentedControlProps<T extends string> {
  value: T
  options: SegmentedOption<T>[]
  onChange: (value: T) => void
  label?: string
  className?: string
  disabled?: boolean
}

export function SegmentedControl<T extends string>({ value, options, onChange, label, className = '', disabled = false }: SegmentedControlProps<T>) {
  return (
    <div className={`ui-segmented ${className}`.trim()} role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={`ui-segmented-option ${option.value === value ? 'is-active' : ''}`.trim()}
          disabled={disabled || option.disabled}
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
